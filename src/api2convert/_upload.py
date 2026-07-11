"""Uploads a local file to a job's per-job upload server.

This step is intentionally hand-written — it is NOT described by the OpenAPI
spec. It posts a ``multipart/form-data`` body (field ``file``) to
``{job.server}/upload-file/{job.id}`` and authenticates with the per-job
``X-Oc-Token`` header — never the account API key. The body is streamed, so
large files are not read into memory. Internal.
"""

from __future__ import annotations

import os
from typing import IO, TYPE_CHECKING

import httpx

from .errors import Api2ConvertError
from .models import InputFile

if TYPE_CHECKING:
    from ._transport import Transport
    from .models import Job


class FileUploader:
    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def upload(
        self,
        job: Job,
        file: str | os.PathLike[str] | IO[bytes],
        filename: str | None = None,
    ) -> InputFile:
        if not job.server or job.token is None:
            raise Api2ConvertError(
                "Cannot upload: the job has no upload server/token. "
                "Create the job with process=false and upload before starting it."
            )

        stream, resolved_name, opened = self._resolve(file, filename)
        seekable = _is_seekable(stream)
        url = job.server.rstrip("/") + "/upload-file/" + job.id
        token = job.token

        def build() -> httpx.Request:
            if seekable:
                stream.seek(0)
            return self._transport.build_request(
                "POST", url, headers={"X-Oc-Token": token}, files={"file": (resolved_name, stream)}
            )

        try:
            response = self._transport.send(build, stream=True, replayable=seekable)
            return InputFile.from_dict(self._transport.interpret(response))
        finally:
            if opened is not None:
                opened.close()

    def _resolve(
        self, file: str | os.PathLike[str] | IO[bytes], filename: str | None
    ) -> tuple[IO[bytes], str, IO[bytes] | None]:
        if isinstance(file, str | os.PathLike):
            path = os.path.realpath(os.fspath(file))
            if not os.path.isfile(path):
                raise Api2ConvertError(f"Input file not found: {file}")
            handle = open(path, "rb")  # noqa: SIM115 — closed by upload()'s finally
            # Mirror PHP's `$filename ?? default` (null-coalesce): only None falls
            # back to the default, so an explicit "" is preserved as-is.
            name = os.path.basename(path) if filename is None else filename
            return handle, name, handle
        return file, ("file" if filename is None else filename), None


def _is_seekable(stream: IO[bytes]) -> bool:
    seekable = getattr(stream, "seekable", None)
    if callable(seekable):
        try:
            return bool(seekable())
        except (OSError, ValueError):
            return False
    return False
