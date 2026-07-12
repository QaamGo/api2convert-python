"""The API resource classes.

One class per API tag: :class:`JobsResource`, :class:`ConversionsResource`,
:class:`PresetsResource`, :class:`StatsResource`, :class:`ContractsResource`.
Reach them through the client accessors (``client.jobs`` and friends). Methods
are thin: build the request, call the transport, hydrate a model.
"""

from __future__ import annotations

import builtins
import os
import time
from collections.abc import Mapping
from typing import IO, TYPE_CHECKING, Any
from urllib.parse import quote

from ._config import MAX_POLL_TIMEOUT, MIN_POLL_INTERVAL
from .cloud import CloudInput
from .errors import ConversionFailedError, ConversionTimeoutError
from .models import InputFile, Job, OutputFile, Preset

if TYPE_CHECKING:
    from ._transport import Transport
    from ._upload import FileUploader


def _seg(value: str) -> str:
    """Percent-encode a value for safe use as a single URL path segment.

    ``safe=""`` encodes ``/`` too, so a caller-supplied id (job/preset id, stats
    date/filter) can never inject extra path segments or a traversal into the URL.
    """
    return quote(value, safe="")


class JobsResource:
    """Full control over the job lifecycle.

    Most users only need ``client.convert()``, which is built on top of these
    methods. Reach for this resource for compound jobs, merges, presets, custom
    polling or job chaining.
    """

    def __init__(self, transport: Transport, uploader: FileUploader) -> None:
        self._transport = transport
        self._uploader = uploader

    def create(self, payload: Mapping[str, Any], idempotency_key: str | None = None) -> Job:
        """Create a job.

        Pass ``{"process": False}`` to stage it for uploads, then call
        :meth:`start` once inputs are attached. ``idempotency_key`` makes the
        create retry-safe (sent as the ``Idempotency-Key`` header).
        """
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key is not None else None
        return Job.from_dict(self._transport.request("POST", "/jobs", payload, headers=headers))

    def get(self, job_id: str) -> Job:
        return Job.from_dict(self._transport.request("GET", f"/jobs/{_seg(job_id)}"))

    def list(self, status: str | None = None, page: int = 1) -> builtins.list[Job]:
        """List the current key's jobs (paginated, 50 per page)."""
        query = {"page": str(page)}
        if status is not None:
            query["status"] = status
        rows = self._transport.request("GET", "/jobs", None, query)
        return [Job.from_dict(row) for row in rows if isinstance(row, dict)]

    def update(self, job_id: str, payload: Mapping[str, Any]) -> Job:
        return Job.from_dict(self._transport.request("PATCH", f"/jobs/{_seg(job_id)}", payload))

    def start(self, job_id: str) -> Job:
        """Start processing a staged job (``process => true``)."""
        return self.update(job_id, {"process": True})

    def cancel(self, job_id: str) -> None:
        """Cancel a job (whether staged or processing)."""
        self._transport.request("DELETE", f"/jobs/{_seg(job_id)}")

    def add_input(self, job_id: str, descriptor: CloudInput | Mapping[str, Any]) -> InputFile:
        """Attach an input — a :class:`~api2convert.cloud.CloudInput` builder, or a raw descriptor.

        ``add_input(job_id, {"type": "remote", "source": "https://..."})``, a
        Google Drive picker (``{"type": "gdrive_picker", "source": <file-id>,
        "credentials": {"token": ...}}``), or ``add_input(job_id,
        CloudInput.ftp(...))``.
        """
        body = descriptor.to_dict() if isinstance(descriptor, CloudInput) else descriptor
        return InputFile.from_dict(
            self._transport.request("POST", f"/jobs/{_seg(job_id)}/input", body)
        )

    def upload(
        self,
        job: Job,
        file: str | os.PathLike[str] | IO[bytes],
        filename: str | None = None,
    ) -> InputFile:
        """Upload a local file (path or stream) to the job's upload server."""
        return self._uploader.upload(job, file, filename)

    def wait(
        self, job_id: str, timeout_seconds: int | None = None, throw_on_failure: bool = True
    ) -> Job:
        """Block until the job reaches a terminal status, polling with backoff.

        Raises :class:`ConversionFailedError` on a failed/canceled job (unless
        ``throw_on_failure`` is ``False``) and :class:`ConversionTimeoutError`
        past the deadline. The interval is floored and the total wait capped, so
        no configuration can busy-loop or poll unbounded.
        """
        config = self._transport.config
        # Clamp again here (Config.create already clamps) so a directly-built
        # Config or a per-call override can never busy-loop or poll unbounded.
        timeout = min(
            MAX_POLL_TIMEOUT,
            max(0, timeout_seconds if timeout_seconds is not None else config.poll_timeout),
        )
        max_interval = max(MIN_POLL_INTERVAL, config.poll_max_interval)
        interval = max(MIN_POLL_INTERVAL, config.poll_interval)
        deadline = time.monotonic() + timeout

        while True:
            job = self.get(job_id)

            if (job.is_failed() or job.is_canceled()) and throw_on_failure:
                raise ConversionFailedError(job)

            if job.is_terminal():
                return job

            if time.monotonic() >= deadline:
                raise ConversionTimeoutError(job, timeout)

            self._transport.pause(interval)
            interval = min(max_interval, interval * 1.5)

    def outputs(self, job_id: str) -> builtins.list[OutputFile]:
        """Outputs produced by the job (use :meth:`get` or :meth:`wait` first)."""
        rows = self._transport.request("GET", f"/jobs/{_seg(job_id)}/output")
        return [OutputFile.from_dict(row) for row in rows if isinstance(row, dict)]


class ConversionsResource:
    """The conversions catalog (``GET /conversions``).

    The source of truth for which targets exist and which options each accepts.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self, category: str | None = None, target: str | None = None, page: int = 1
    ) -> builtins.list[dict[str, Any]]:
        """List supported conversions, optionally filtered by category/target.

        Each entry: ``{ id, category, target, options }``.
        """
        query = {"page": str(page)}
        if category is not None:
            query["category"] = category
        if target is not None:
            query["target"] = target
        rows = self._transport.request("GET", "/conversions", None, query)
        return [row for row in rows if isinstance(row, dict)]

    def options(self, target: str, category: str | None = None) -> dict[str, Any]:
        """The option schema (type / enum / default / range) for a single target.

        ``category`` is optional — pass it only to disambiguate an ambiguous target.
        """
        rows = self.list(category, target)
        first = rows[0] if rows else {}
        options = first.get("options", {})
        return options if isinstance(options, dict) else {}


class PresetsResource:
    """Saved conversion presets (reusable named target + options)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def list(
        self,
        category: str | None = None,
        target: str | None = None,
        filter: str | None = None,
    ) -> builtins.list[Preset]:
        query = {
            key: value
            for key, value in (("category", category), ("target", target), ("filter", filter))
            if value is not None
        }
        rows = self._transport.request("GET", "/presets", None, query)
        return [Preset.from_dict(row) for row in rows if isinstance(row, dict)]

    def create(self, payload: Mapping[str, Any]) -> Preset:
        """Create a preset from ``{ name, target, options, scope?, category? }``."""
        return Preset.from_dict(self._transport.request("POST", "/presets", payload))

    def get(self, preset_id: str) -> Preset:
        return Preset.from_dict(self._transport.request("GET", f"/presets/{_seg(preset_id)}"))

    def update(self, preset_id: str, payload: Mapping[str, Any]) -> Preset:
        return Preset.from_dict(
            self._transport.request("PATCH", f"/presets/{_seg(preset_id)}", payload)
        )

    def delete(self, preset_id: str) -> None:
        self._transport.request("DELETE", f"/presets/{_seg(preset_id)}")


class StatsResource:
    """API usage statistics. The response shape is free-form (returned as-is).

    ``filter`` is ``single`` (only the calling API key) or ``all`` (every key on
    the account, the default). The request is scoped by the ``X-Api2convert-Api-Key``
    header, so never pass a key as ``filter``.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def day(self, day: str, filter: str = "all") -> Any:
        """``day`` format ``yyyy-mm-dd``."""
        return self._transport.request("GET", f"/stats/day/{_seg(day)}/{_seg(filter)}")

    def month(self, month: str, filter: str = "all") -> Any:
        """``month`` format ``yyyy-mm``."""
        return self._transport.request("GET", f"/stats/month/{_seg(month)}/{_seg(filter)}")

    def year(self, year: str, filter: str = "all") -> Any:
        """``year`` format ``yyyy``."""
        return self._transport.request("GET", f"/stats/year/{_seg(year)}/{_seg(filter)}")


class ContractsResource:
    """Information about the account's active contracts (free-form response)."""

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    def get(self) -> Any:
        return self._transport.request("GET", "/contracts")
