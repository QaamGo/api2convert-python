"""Security guardrails that need a URL-aware transport (redirect handling)."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

from api2convert import Api2Convert, NetworkError, OutputFile
from api2convert._config import Config
from api2convert._transport import Transport


def _client(handler: object) -> Api2Convert:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return Api2Convert("SECRET-KEY", http_client=httpx.Client(transport=transport))


def test_api_key_is_not_followed_across_a_redirect_on_the_authenticated_path() -> None:
    hosts_seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hosts_seen.append(request.url.host)
        if request.url.host == "api.api2convert.com":
            # An API host that (or an intermediary that) 302s to another host must not
            # cause the account key to be forwarded there.
            return httpx.Response(302, headers={"Location": "https://evil.example.net/steal"})
        return httpx.Response(200, json={"grabbed": request.headers.get("X-Oc-Api-Key")})

    # An authenticated 3xx is surfaced as a typed error, not silently swallowed.
    with pytest.raises(NetworkError):
        _client(handler).jobs.get("j")

    # The redirect was NOT followed: the evil host never received a request (so the key
    # never left the API host).
    assert hosts_seen == ["api.api2convert.com"]
    assert "evil.example.net" not in hosts_seen


def test_download_follows_storage_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "dl.api2convert.com":
            return httpx.Response(302, headers={"Location": "https://storage.example.net/file"})
        return httpx.Response(200, content=b"REDIRECTED-BYTES")

    client = _client(handler)
    output = OutputFile(id="o", uri="https://dl.api2convert.com/result.bin")
    assert client.download(output).contents() == b"REDIRECTED-BYTES"


def test_download_password_is_not_resent_to_a_different_host_on_redirect() -> None:
    seen: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers.get("X-Oc-Download-Password")))
        if request.url.host == "dl.api2convert.com":
            # Storage layer 302s the (password-bearing) download to another host.
            return httpx.Response(302, headers={"Location": "https://storage.example.net/file"})
        return httpx.Response(200, content=b"BYTES")

    client = _client(handler)
    output = OutputFile(id="o", uri="https://dl.api2convert.com/result.bin")
    assert client.download(output).contents(download_password="s3cret") == b"BYTES"

    # The redirect WAS followed (storage URLs legitimately redirect)...
    assert [host for host, _ in seen] == ["dl.api2convert.com", "storage.example.net"]
    # ...but the password went only to the original download host, never the redirect target.
    assert ("dl.api2convert.com", "s3cret") in seen
    assert ("storage.example.net", None) in seen


def test_download_password_survives_a_same_origin_redirect() -> None:
    passwords: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        passwords.append(request.headers.get("X-Oc-Download-Password"))
        if request.url.path == "/result.bin":
            # Same host, different path — the secret may (and must) still be sent.
            return httpx.Response(302, headers={"Location": "/moved/result.bin"})
        return httpx.Response(200, content=b"BYTES")

    client = _client(handler)
    output = OutputFile(id="o", uri="https://dl.api2convert.com/result.bin")
    assert client.download(output).contents(download_password="s3cret") == b"BYTES"

    assert passwords == ["s3cret", "s3cret"]


def test_control_plane_body_over_the_cap_is_rejected_without_buffering_it() -> None:
    cap = Transport.MAX_RESPONSE_BYTES
    chunk = b"x" * (1024 * 1024)  # 1 MiB
    produced = 0

    def body() -> Iterator[bytes]:
        nonlocal produced
        # Far more than the cap: an unbounded read would materialize all of this in
        # memory (the OOM this guard exists to prevent).
        for _ in range(cap // len(chunk) + 8):
            produced += len(chunk)
            yield chunk

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    with pytest.raises(NetworkError, match="16 MiB"):
        _client(handler).jobs.get("j")

    # The SDK stopped reading at the cap instead of draining the whole (over-cap)
    # stream: the body was never buffered unboundedly into memory.
    assert produced <= cap + len(chunk)


def test_error_body_over_the_cap_surfaces_as_a_network_error() -> None:
    cap = Transport.MAX_RESPONSE_BYTES

    def handler(request: httpx.Request) -> httpx.Response:
        # A non-retryable status so the error body is read once, without real backoff.
        return httpx.Response(400, content=b"E" * (cap + 1))

    with pytest.raises(NetworkError, match="16 MiB"):
        _client(handler).jobs.get("j")


def test_control_plane_body_at_the_cap_is_still_accepted() -> None:
    cap = Transport.MAX_RESPONSE_BYTES
    # A body exactly at the cap: a job payload padded to the limit with insignificant
    # JSON whitespace before the closing brace (still valid JSON).
    payload = b'{"id":"j"' + b" " * (cap - 10) + b"}"
    assert len(payload) == cap

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=payload, headers={"content-type": "application/json"})

    job = _client(handler).jobs.get("j")
    assert job.id == "j"


def test_a_mid_body_network_drop_on_a_success_response_surfaces_as_a_typed_error() -> None:
    # Streaming the control-plane body (so the cap can bound it before httpx buffers) moves
    # the read out of send()'s httpx-error guard into the interpret path. A mid-body transport
    # failure on a 2xx must therefore still be converted to the SDK's typed NetworkError, never
    # leak a raw httpx.ReadError out of the exception hierarchy.
    def body() -> Iterator[bytes]:
        yield b'{"id":'
        raise httpx.ReadError("connection reset mid-stream")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body())

    with pytest.raises(NetworkError):
        _client(handler).jobs.get("j")


def test_config_repr_does_not_leak_the_api_key() -> None:
    config = Config.create("SUPER-SECRET-KEY")

    assert "SUPER-SECRET-KEY" not in repr(config)
    assert "SUPER-SECRET-KEY" not in str(config)
    # The key is still usable programmatically — only its printed form is masked.
    assert config.api_key == "SUPER-SECRET-KEY"
