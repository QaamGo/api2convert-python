"""Typed DTOs and enums for the API2Convert data model.

DTOs are frozen (immutable) dataclasses hydrated by a defensive ``from_dict``
that tolerates missing/extra fields and never raises — mirroring the PHP SDK's
``readonly`` models and their ``fromArray`` factories. Attribute names use
snake_case matching the wire JSON keys (``content_type``, ``id_source``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import _data
from .cloud import CloudProvider, OutputTarget

__all__ = [
    "CloudProvider",
    "Conversion",
    "InputFile",
    "InputType",
    "Job",
    "JobMessage",
    "JobStatus",
    "OutputFile",
    "OutputTarget",
    "Preset",
    "Status",
]


class JobStatus(str, Enum):
    """Well-known job status codes (the ``status.code`` field).

    The API may introduce further codes; treat any code not listed here as
    non-terminal. Use :meth:`is_terminal_code` for a raw status string rather
    than comparing by hand.
    """

    CREATED = "created"
    INCOMPLETE = "incomplete"
    DOWNLOADING = "downloading"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

    def is_terminal(self) -> bool:
        """A terminal job is finished and will not change further."""
        return self in _TERMINAL_STATUSES

    @staticmethod
    def is_terminal_code(code: str) -> bool:
        """Is the given raw status code terminal? Unknown codes are non-terminal."""
        return code in _TERMINAL_CODES


_TERMINAL_STATUSES = frozenset({JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELED})
_TERMINAL_CODES = frozenset(status.value for status in _TERMINAL_STATUSES)


class InputType(str, Enum):
    """The kinds of source an input file can be created from (the input ``type`` field).

    A typed reference for building input descriptors by hand, e.g.
    ``add_input(job_id, {"type": InputType.REMOTE.value, "source": ...})``.
    """

    UPLOAD = "upload"
    REMOTE = "remote"
    OUTPUT = "output"
    INPUT_ID = "input_id"
    GDRIVE_PICKER = "gdrive_picker"
    BASE64 = "base64"
    CLOUD = "cloud"


@dataclass(frozen=True, slots=True, kw_only=True)
class Status:
    """A job's status: a machine-readable :attr:`code` plus optional human :attr:`info`."""

    code: str = ""
    info: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Status:
        return cls(
            code=_data.as_str(data.get("code")),
            info=_data.nullable_str(data.get("info")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Conversion:
    """A single conversion within a job: the target format plus its options."""

    target: str = ""
    id: str | None = None
    category: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    output_targets: list[OutputTarget] = field(default_factory=list)
    """Cloud delivery targets for this conversion's output, if any (read-side)."""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Conversion:
        return cls(
            target=_data.as_str(data.get("target")),
            id=_data.nullable_str(data.get("id")),
            category=_data.nullable_str(data.get("category")),
            options=_data.as_object(data.get("options")),
            metadata=_data.as_object(data.get("metadata")),
            output_targets=_data.map_objects(data.get("output_target"), OutputTarget.from_dict),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InputFile:
    """An input file attached to a job."""

    id: str | None = None
    type: str = ""
    source: str | None = None
    status: str | None = None
    filename: str | None = None
    size: int | None = None
    content_type: str | None = None
    options: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    """Cloud-input locator keys (``bucket``, ``file``, ``host``, …); empty for non-cloud inputs.

    Credentials are never surfaced on read (the API returns them empty).
    """

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InputFile:
        return cls(
            id=_data.nullable_str(data.get("id")),
            type=_data.as_str(data.get("type")),
            source=_data.nullable_str(data.get("source")),
            status=_data.nullable_str(data.get("status")),
            filename=_data.nullable_str(data.get("filename")),
            size=_data.nullable_int(data.get("size")),
            content_type=_data.nullable_str(data.get("content_type")),
            options=_data.as_object(data.get("options")),
            parameters=_data.as_object(data.get("parameters")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class OutputFile:
    """A produced output file.

    :attr:`uri` is a self-contained download URL (no auth), valid for a limited
    time (24h by default).
    """

    id: str | None = None
    uri: str = ""
    filename: str | None = None
    size: int | None = None
    status: str | None = None
    content_type: str | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutputFile:
        return cls(
            id=_data.nullable_str(data.get("id")),
            uri=_data.as_str(data.get("uri")),
            filename=_data.nullable_str(data.get("filename")),
            size=_data.nullable_int(data.get("size")),
            status=_data.nullable_str(data.get("status")),
            content_type=_data.nullable_str(data.get("content_type")),
            checksum=_data.nullable_str(data.get("checksum")),
            metadata=_data.as_object(data.get("metadata")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class JobMessage:
    """An error or warning attached to a job (the ``errors[]`` / ``warnings[]`` entries)."""

    code: int | None = None
    message: str = ""
    source: str | None = None
    id_source: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> JobMessage:
        return cls(
            code=_data.nullable_int(data.get("code")),
            message=_data.as_str(data.get("message")),
            source=_data.nullable_str(data.get("source")),
            id_source=_data.nullable_str(data.get("id_source")),
            details=_data.as_object(data.get("details")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Preset:
    """A saved conversion preset (a reusable named set of target + options)."""

    id: str | None = None
    name: str = ""
    target: str | None = None
    category: str | None = None
    scope: str | None = None
    options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Preset:
        return cls(
            id=_data.nullable_str(data.get("id")),
            name=_data.as_str(data.get("name")),
            target=_data.nullable_str(data.get("target")),
            category=_data.nullable_str(data.get("category")),
            scope=_data.nullable_str(data.get("scope")),
            options=_data.as_object(data.get("options")),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class Job:
    """A conversion job — the central API2Convert resource.

    :attr:`server` and :attr:`token` are needed to upload local files;
    :attr:`output` holds the produced files once :meth:`is_completed`.
    :attr:`raw` keeps the full decoded response for fields not surfaced as
    typed properties.
    """

    id: str = ""
    status: Status = field(default_factory=Status)
    token: str | None = None
    server: str | None = None
    callback: str | None = None
    conversion: list[Conversion] = field(default_factory=list)
    input: list[InputFile] = field(default_factory=list)
    output: list[OutputFile] = field(default_factory=list)
    errors: list[JobMessage] = field(default_factory=list)
    warnings: list[JobMessage] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Job:
        return cls(
            id=_data.as_str(data.get("id")),
            status=Status.from_dict(_data.as_object(data.get("status"))),
            token=_data.nullable_str(data.get("token")),
            server=_data.nullable_str(data.get("server")),
            callback=_data.nullable_str(data.get("callback")),
            conversion=_data.map_objects(data.get("conversion"), Conversion.from_dict),
            input=_data.map_objects(data.get("input"), InputFile.from_dict),
            output=_data.map_objects(data.get("output"), OutputFile.from_dict),
            errors=_data.map_objects(data.get("errors"), JobMessage.from_dict),
            warnings=_data.map_objects(data.get("warnings"), JobMessage.from_dict),
            raw=dict(data),
        )

    def is_completed(self) -> bool:
        return self.status.code == JobStatus.COMPLETED.value

    def is_failed(self) -> bool:
        return self.status.code == JobStatus.FAILED.value

    def is_canceled(self) -> bool:
        """The job was canceled server-side — terminal, and produced no output."""
        return self.status.code == JobStatus.CANCELED.value

    def is_terminal(self) -> bool:
        """Finished (completed, failed or canceled) and will not change further."""
        return JobStatus.is_terminal_code(self.status.code)
