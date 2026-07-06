"""Conversion result and download helpers.

:class:`ConversionResult` wraps a completed job; :class:`FileDownload` streams a
single output file to disk or memory. Both remember a download password supplied
at conversion time and send it automatically on download.
"""

from __future__ import annotations

import contextlib
import os
import posixpath
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import Api2ConvertError
from .models import Job, OutputFile

if TYPE_CHECKING:
    from ._transport import Transport


class FileDownload:
    """A downloadable output file.

    Returned by ``client.download(output)`` and used internally by
    :class:`ConversionResult`.
    """

    _CHUNK_SIZE = 1 << 16  # 64 KiB

    def __init__(
        self,
        transport: Transport,
        output: OutputFile,
        download_password: str | None = None,
    ) -> None:
        self._transport = transport
        self._output = output
        self._download_password = download_password

    def url(self) -> str:
        """The self-contained download URL (no auth required)."""
        return self._output.uri

    def save(
        self, path_or_dir: str | os.PathLike[str], download_password: str | None = None
    ) -> Path:
        """Stream the file to disk.

        ``path_or_dir`` is a file path, or a directory (the API filename is used).
        A password set at conversion time is applied automatically; pass one here
        only to override it. Returns the path written to.
        """
        target = self._resolve_target(os.fspath(path_or_dir))
        parent = os.path.dirname(target) or "."
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as exc:
            raise Api2ConvertError(f"Could not create directory: {parent}") from exc

        try:
            handle = open(target, "wb")  # noqa: SIM115 — closed by the with-block below
        except OSError as exc:
            raise Api2ConvertError(f"Could not open file for writing: {target}") from exc

        try:
            with (
                handle,
                self._transport.stream(
                    self._output.uri, self._headers(download_password)
                ) as source,
            ):
                for chunk in source.iter_bytes(self._CHUNK_SIZE):
                    handle.write(chunk)
        except BaseException:
            # A mid-stream failure (network drop, disk full, interrupt) must not leave
            # a truncated file the caller could mistake for a complete download.
            with contextlib.suppress(OSError):
                os.unlink(target)
            raise

        return Path(target)

    def contents(self, download_password: str | None = None) -> bytes:
        """Download the file and return its contents (loads into memory)."""
        with self._transport.stream(self._output.uri, self._headers(download_password)) as source:
            return source.read()

    def _resolve_target(self, path_or_dir: str) -> str:
        looks_like_dir = (
            os.path.isdir(path_or_dir) or path_or_dir.endswith("/") or path_or_dir.endswith(os.sep)
        )
        if looks_like_dir:
            name = (
                self._safe_name(self._output.filename)
                or self._safe_name(self._output.id)
                or "output"
            )
            return os.path.join(path_or_dir.rstrip("/\\"), name)
        return path_or_dir

    @staticmethod
    def _safe_name(name: str | None) -> str | None:
        """Reduce an API-supplied name to a bare filename safe to append to a dir.

        ``output.filename`` / ``output.id`` come straight from the API JSON, so a
        value like ``../../etc/cron.d/evil`` (or one with separators or a NUL byte)
        must never escape the caller's chosen directory. Returns ``None`` when
        nothing usable remains, so the caller can fall back.
        """
        if name is None:
            return None
        cleaned = name.replace("\x00", "").replace("\\", "/")
        base = posixpath.basename(cleaned).strip()
        if base in ("", ".", ".."):
            return None
        return base

    def _headers(self, download_password: str | None) -> dict[str, str]:
        password = download_password if download_password is not None else self._download_password
        return {"X-Oc-Download-Password": password} if password is not None else {}


class ConversionResult:
    """The result of a completed conversion.

    The common case is one output: ``result.save("out.pdf")``. Jobs that produce
    several files expose them via :meth:`outputs` and :meth:`download`.
    """

    def __init__(
        self,
        job: Job,
        transport: Transport,
        index: int = 0,
        download_password: str | None = None,
    ) -> None:
        #: The completed job.
        self.job = job
        self._transport = transport
        self._index = index
        self._download_password = download_password

    def output(self) -> OutputFile:
        """The selected output file (the first one by default)."""
        # Mirror PHP's `$job->output[$index] ?? throw`: any index not present —
        # including a negative one — raises rather than wrapping around.
        if self._index < 0 or self._index >= len(self.job.output):
            raise Api2ConvertError("The job produced no output files.")
        return self.job.output[self._index]

    def outputs(self) -> list[OutputFile]:
        """All output files produced by the job."""
        return self.job.output

    def url(self) -> str:
        """The download URL of the selected output (self-contained, no auth)."""
        return self.output().uri

    def save(
        self, path_or_dir: str | os.PathLike[str], download_password: str | None = None
    ) -> Path:
        """Download the selected output to disk. Returns the path written to."""
        return self.download().save(path_or_dir, download_password)

    def contents(self, download_password: str | None = None) -> bytes:
        """Download the selected output and return its contents (loads into memory)."""
        return self.download().contents(download_password)

    def download(self, output: OutputFile | None = None) -> FileDownload:
        """A :class:`FileDownload` for a specific output (defaults to the selected one)."""
        return FileDownload(
            self._transport,
            output if output is not None else self.output(),
            self._download_password,
        )
