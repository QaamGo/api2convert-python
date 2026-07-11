"""Download-to-disk + path-traversal defense (mirrors PHP FileDownloadTest)."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest

from api2convert import Api2Convert, Api2ConvertError, NetworkError, OutputFile

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


def test_mid_stream_read_failure_is_typed_and_leaves_no_partial_file(tmp_path: Path) -> None:
    # A read failure part-way through streaming is a network error — a typed NetworkError, not a
    # raw httpx error escaping the hierarchy — and must leave no partial file at the target.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_ExplodingStream())

    target = tmp_path / "out.bin"
    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with (
        Api2Convert("k", http_client=http_client) as client,
        pytest.raises(NetworkError),
    ):
        client.download(OutputFile(id="o", uri=URI)).save(target)

    # The truncated download must be removed, not left to masquerade as complete.
    assert not target.exists()


def test_failed_download_preserves_a_pre_existing_file(tmp_path: Path) -> None:
    # Temp-file + atomic rename means a mid-stream failure must not destroy a previously-complete
    # file at the target path (streaming straight into the target used to truncate it up front).
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_ExplodingStream())

    target = tmp_path / "out.bin"
    target.write_bytes(b"PREEXISTING COMPLETE FILE")
    http_client = httpx.Client(transport=httpx.MockTransport(handler))

    with (
        Api2Convert("k", http_client=http_client) as client,
        pytest.raises(NetworkError),
    ):
        client.download(OutputFile(id="o", uri=URI)).save(target)

    assert target.read_bytes() == b"PREEXISTING COMPLETE FILE"
    # No temp/part file was left behind next to the target.
    assert list(tmp_path.iterdir()) == [target]


@contextlib.contextmanager
def _serve(handler_cls: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/file.bin"
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_slow_but_steady_download_is_not_capped_by_the_per_request_timeout(
    tmp_path: Path,
) -> None:
    # httpx applies a PER-SOCKET read timeout, not a whole-transfer deadline. A body that
    # dribbles in steadily (each gap under the timeout) but takes longer than the timeout in
    # total must still complete — the streamed transfer is governed by the caller's per-read
    # budget, never a cap on the whole download. Fails if the read timeout were a total deadline.
    chunks = [f"chunk-{i:02d};".encode() for i in range(8)]
    expected = b"".join(chunks)
    gap = 0.2  # < the 1s per-request timeout, but 8 gaps total ~1.6s > 1s

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # BaseHTTPRequestHandler dispatches by method name
            self.send_response(200)
            self.send_header("Content-Length", str(len(expected)))
            self.send_header("Connection", "close")
            self.end_headers()
            for chunk in chunks:
                self.wfile.write(chunk)
                self.wfile.flush()
                time.sleep(gap)

        def log_message(self, *args: object) -> None:  # silence the default stderr logging
            pass

    started = time.monotonic()
    with _serve(Handler) as uri, Api2Convert("k", timeout=1) as client:
        written = client.download(OutputFile(id="o", uri=uri)).save(tmp_path / "out.bin")

    assert written.read_bytes() == expected
    # Sanity: the transfer genuinely outlasted the (1s) per-request timeout.
    assert time.monotonic() - started > 1.0
