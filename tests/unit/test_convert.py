"""End-to-end ``convert`` / ``convert_async`` guardrails (mirrors PHP ConvertTest)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from api2convert import Api2Convert, Api2ConvertError, OutputFile

from ..conftest import MockAPI

REMOTE_URL = "https://example.com/photo.png"
DOWNLOAD_URL = "https://dl.example.com/result.png"


def test_remote_url_creates_started_job_polls_and_downloads(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    api.add_json(201, {"id": "job-1", "status": {"code": "incomplete", "info": "Queued"}})
    api.add_json(
        200,
        {
            "id": "job-1",
            "status": {"code": "completed"},
            "output": [
                {
                    "id": "out-1",
                    "uri": DOWNLOAD_URL,
                    "filename": "result.png",
                    "content_type": "image/png",
                }
            ],
        },
    )
    api.add_text(200, "PNGDATA")

    client = make_client()
    result = client.convert(REMOTE_URL, "png")

    create = api.request_at(0)
    assert create.method == "POST"
    assert str(create.url).endswith("/jobs")
    assert create.headers["X-Oc-Api-Key"] == "test-key"
    body = api.json_at(0)
    assert body["process"] is True
    assert body["conversion"][0]["target"] == "png"
    assert body["input"][0]["type"] == "remote"
    assert body["input"][0]["source"] == REMOTE_URL

    poll = api.request_at(1)
    assert poll.method == "GET"
    assert str(poll.url).endswith("/jobs/job-1")

    assert result.url() == DOWNLOAD_URL
    written = result.save(tmp_path)
    assert written.read_bytes() == b"PNGDATA"
    assert written.name == "result.png"
    assert str(api.request_at(2).url) == DOWNLOAD_URL


def test_local_file_stages_uploads_then_starts(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    source = tmp_path / "in.txt"
    source.write_text("hello world")

    api.add_json(
        201,
        {
            "id": "job-9",
            "token": "tok-abc",
            "server": "https://www2.api2convert.com/v2",
            "status": {"code": "incomplete"},
        },
    )
    api.add_json(200, {"id": "in-1", "type": "upload", "status": "downloaded"})
    api.add_json(200, {"id": "job-9", "status": {"code": "processing"}})
    api.add_json(
        200,
        {
            "id": "job-9",
            "status": {"code": "completed"},
            "output": [{"id": "o", "uri": "https://dl/out.pdf", "filename": "out.pdf"}],
        },
    )

    client = make_client()
    result = client.convert(source, "pdf")

    assert api.json_at(0)["process"] is False

    upload = api.request_at(1)
    assert upload.method == "POST"
    assert str(upload.url) == "https://www2.api2convert.com/v2/upload-file/job-9"
    assert upload.headers["X-Oc-Token"] == "tok-abc"
    assert "x-oc-api-key" not in upload.headers  # the account key must NOT leak to the upload
    assert "multipart/form-data" in upload.headers["content-type"]
    assert b'name="file"' in api.body_at(1)

    start = api.request_at(2)
    assert start.method == "PATCH"
    assert api.json_at(2)["process"] is True

    assert result.output().filename == "out.pdf"


def test_async_returns_immediately_with_callback(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "job-async", "status": {"code": "incomplete"}})

    client = make_client()
    job = client.convert_async(REMOTE_URL, "mp4", callback="https://app.example.com/hook")

    assert job.id == "job-async"
    assert len(api.requests) == 1  # no polling
    body = api.json_at(0)
    assert body["callback"] == "https://app.example.com/hook"
    assert body["notify_status"] is True


def test_forwards_options_as_conversion_options(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(200, {"id": "j", "status": {"code": "completed"}, "output": []})

    client = make_client()
    client.convert(REMOTE_URL, "jpg", {"quality": 85, "width": 1280})

    body = api.json_at(0)
    assert body["conversion"][0]["target"] == "jpg"
    assert body["conversion"][0]["options"] == {"quality": 85, "width": 1280}


def test_contents_downloads_body(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(
        200,
        {"id": "j", "status": {"code": "completed"}, "output": [{"id": "o", "uri": DOWNLOAD_URL}]},
    )
    api.add_text(200, "RAWBYTES")

    client = make_client()
    result = client.convert(REMOTE_URL, "png")

    assert result.contents() == b"RAWBYTES"
    assert str(api.request_at(2).url) == DOWNLOAD_URL


def test_download_password_set_and_sent_transparently(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(
        200,
        {"id": "j", "status": {"code": "completed"}, "output": [{"id": "o", "uri": DOWNLOAD_URL}]},
    )
    api.add_text(200, "SECRET")

    client = make_client()
    result = client.convert(REMOTE_URL, "pdf", download_password="hunter2")

    assert api.json_at(0)["download_passwords"] == ["hunter2"]
    assert result.contents() == b"SECRET"
    assert api.request_at(2).headers["X-Oc-Download-Password"] == "hunter2"


def test_explicit_download_password_overrides_remembered(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(
        200,
        {"id": "j", "status": {"code": "completed"}, "output": [{"id": "o", "uri": DOWNLOAD_URL}]},
    )
    api.add_text(200, "X")

    client = make_client()
    result = client.convert(REMOTE_URL, "pdf", download_password="hunter2")
    result.contents("override-pw")

    assert api.request_at(2).headers["X-Oc-Download-Password"] == "override-pw"


def test_download_helper_carries_password(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_text(200, "BYTES")

    client = make_client()
    output = OutputFile(id="o", uri=DOWNLOAD_URL)
    assert client.download(output, "hunter2").contents() == b"BYTES"
    assert api.request_at(0).headers["X-Oc-Download-Password"] == "hunter2"


def test_async_sets_download_password_on_create(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})

    client = make_client()
    client.convert_async(REMOTE_URL, "pdf", download_password="hunter2")

    assert api.json_at(0)["download_passwords"] == ["hunter2"]


def test_without_download_password_sends_no_field_or_header(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(
        200,
        {"id": "j", "status": {"code": "completed"}, "output": [{"id": "o", "uri": DOWNLOAD_URL}]},
    )
    api.add_text(200, "DATA")

    client = make_client()
    result = client.convert(REMOTE_URL, "png")
    result.contents()

    assert "download_passwords" not in api.json_at(0)
    assert "x-oc-download-password" not in api.request_at(2).headers


def test_options_discovery_queries_by_target_only(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, [{"target": "jpg", "options": {"quality": {"type": "integer"}}}])

    client = make_client()
    options = client.options("jpg")

    assert "quality" in options
    url = str(api.request_at(0).url)
    assert "target=jpg" in url
    assert "category=" not in url


def test_output_raises_when_job_has_no_outputs(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(200, {"id": "j", "status": {"code": "completed"}, "output": []})

    result = make_client().convert(REMOTE_URL, "png")
    with pytest.raises(Api2ConvertError, match="produced no output"):
        result.output()


def test_negative_output_index_raises_like_php(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(201, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(
        200,
        {"id": "j", "status": {"code": "completed"}, "output": [{"id": "o", "uri": DOWNLOAD_URL}]},
    )

    # A negative index is a "missing" index in PHP and raises; it must not wrap around.
    result = make_client().convert(REMOTE_URL, "png", output_index=-1)
    with pytest.raises(Api2ConvertError, match="produced no output"):
        result.output()


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("API2CONVERT_API_KEY", raising=False)
    with pytest.raises(ValueError, match="No API key provided"):
        Api2Convert("")
