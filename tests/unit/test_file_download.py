"""Download-to-disk + path-traversal defense (mirrors PHP FileDownloadTest)."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from api2convert import Api2Convert, Api2ConvertError, OutputFile

from ..conftest import MockAPI

URI = "https://dl.example.com/x"


def test_saving_to_directory_uses_the_api_filename(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    api.add_text(200, "PDF-BYTES")
    client = make_client()

    written = client.download(OutputFile(id="o", uri=URI, filename="result.pdf")).save(tmp_path)

    assert written == tmp_path / "result.pdf"
    assert written.read_bytes() == b"PDF-BYTES"


def test_traversal_filename_cannot_escape_the_target_directory(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    api.add_text(200, "DATA")
    client = make_client()

    written = client.download(OutputFile(id="o", uri=URI, filename="../../evil.txt")).save(tmp_path)

    assert written == tmp_path / "evil.txt"
    assert written.exists()
    assert not (tmp_path.parent.parent / "evil.txt").exists()


def test_falls_back_to_output_when_filename_is_dot_only(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    api.add_text(200, "DATA")
    client = make_client()

    written = client.download(OutputFile(id=None, uri=URI, filename="..")).save(tmp_path)

    assert written == tmp_path / "output"


def test_explicit_file_path_is_used_verbatim(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    api.add_text(200, "DATA")
    client = make_client()
    target = tmp_path / "custom.bin"

    written = client.download(OutputFile(id="o", uri=URI, filename="ignored.pdf")).save(target)

    assert written == target
    assert written.read_bytes() == b"DATA"


def test_save_raises_when_directory_cannot_be_created(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("x")  # a file where a directory is needed
    client = make_client()

    with pytest.raises(Api2ConvertError, match="Could not create directory"):
        client.download(OutputFile(id="o", uri=URI)).save(blocker / "sub" / "out.pdf")

    assert len(api.requests) == 0  # fails before any download request


def test_malformed_download_uri_raises_network_error_before_any_request(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    # output.uri comes from API JSON; a syntactically malformed value (here a NUL
    # byte) makes httpx.URL() reject it. It must surface as the SDK's NetworkError
    # before any request is sent, not a raw httpx.InvalidURL escaping the hierarchy.
    client = make_client()

    with pytest.raises(Api2ConvertError, match="Invalid download URL"):
        client.download(OutputFile(id="o", uri="https://dl.example.com/\x00bad")).contents()

    assert len(api.requests) == 0  # rejected before send


class _ExplodingStream(httpx.SyncByteStream):
    """A body that yields one chunk, then fails — simulating a dropped connection."""

    def __iter__(self) -> Iterator[bytes]:
        yield b"PARTIAL-BYTES"
        raise httpx.ReadError("connection dropped mid-stream")


def test_mid_stream_error_leaves_no_partial_file(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_ExplodingStream())

    target = tmp_path / "out.bin"
    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with (
        Api2Convert("k", http_client=http_client) as client,
        pytest.raises(httpx.ReadError),
    ):
        client.download(OutputFile(id="o", uri=URI)).save(target)

    # The truncated download must be removed, not left to masquerade as complete.
    assert not target.exists()
