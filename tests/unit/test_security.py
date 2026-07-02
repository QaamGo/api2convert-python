"""Security guardrails that need a URL-aware transport (redirect handling)."""

from __future__ import annotations

import httpx

from api2convert import Api2Convert, OutputFile


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
