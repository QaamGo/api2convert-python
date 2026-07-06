"""Client construction + input-dispatch behaviors."""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import httpx
import pytest

from api2convert import Api2Convert, Api2ConvertError, ConfigurationError
from api2convert._config import Config

from ..conftest import MockAPI


def _client_with(api: MockAPI, **opts: object) -> Api2Convert:
    http_client = httpx.Client(transport=httpx.MockTransport(api.handler))
    return Api2Convert(http_client=http_client, sleeper=api.slept.append, **opts)  # type: ignore[arg-type]


def test_api_key_falls_back_to_env(api: MockAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API2CONVERT_API_KEY", "env-key")
    api.add_json(200, {"id": "j", "status": {"code": "completed"}})

    client = _client_with(api)  # no explicit key
    client.jobs.get("j")

    assert api.request_at(0).headers["X-Oc-Api-Key"] == "env-key"


def test_explicit_key_wins_over_env(api: MockAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API2CONVERT_API_KEY", "env-key")
    api.add_json(200, {"id": "j", "status": {"code": "completed"}})

    http_client = httpx.Client(transport=httpx.MockTransport(api.handler))
    client = Api2Convert("explicit-key", http_client=http_client)
    client.jobs.get("j")

    assert api.request_at(0).headers["X-Oc-Api-Key"] == "explicit-key"


def test_bring_your_own_client_must_be_httpx_client() -> None:
    with pytest.raises(TypeError, match=r"httpx\.Client"):
        Api2Convert("k", http_client="not-a-client")  # type: ignore[arg-type]


def test_empty_api_key_raises_typed_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API2CONVERT_API_KEY", raising=False)

    with pytest.raises(ConfigurationError):
        Api2Convert("")

    # It stays catchable as an SDK error and, for back-compat, as a ValueError.
    assert issubclass(ConfigurationError, Api2ConvertError)
    assert issubclass(ConfigurationError, ValueError)


def test_config_create_rejects_an_empty_key() -> None:
    # The low-level path must also refuse to build an empty-key config.
    with pytest.raises(ConfigurationError):
        Config.create("")


def test_default_client_is_created_and_closed() -> None:
    client = Api2Convert("k")  # constructs a default httpx.Client
    client.close()  # owns the client, so this closes it
    with Api2Convert("k") as ctx:
        assert isinstance(ctx, Api2Convert)


def test_base_url_override(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "completed"}})
    client = make_client(base_url="https://custom.test/v9/")

    client.jobs.get("j")
    assert str(api.request_at(0).url) == "https://custom.test/v9/jobs/j"


def test_stream_input_uploads_with_default_filename(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(
        201,
        {"id": "job-s", "token": "t", "server": "https://s/v2", "status": {"code": "incomplete"}},
    )
    api.add_json(200, {"id": "in", "type": "upload"})
    api.add_json(200, {"id": "job-s", "status": {"code": "processing"}})  # start (PATCH) response
    api.add_json(200, {"id": "job-s", "status": {"code": "completed"}, "output": []})  # poll

    client = make_client()
    client.convert(BytesIO(b"raw-bytes"), "pdf")

    upload = api.request_at(1)
    assert str(upload.url) == "https://s/v2/upload-file/job-s"
    assert b'filename="file"' in api.body_at(1)  # default advertised name for a stream
