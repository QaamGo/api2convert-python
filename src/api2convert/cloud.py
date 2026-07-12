"""Cloud storage connectors — provider vocabulary, input builder, output target.

The API imports inputs from and delivers outputs to customer-owned cloud
storage. This module models the wire descriptors: a :class:`CloudProvider`
vocabulary, a :class:`CloudInput` builder (input side), and an
:class:`OutputTarget` model (output side).

These types live in their own module (rather than ``models``) so the input
builder can carry redaction logic without an import cycle:
:class:`~api2convert.models.Conversion` hydrates :class:`OutputTarget`, so this
module must not import ``models``. The one wire literal it needs — the input
``type`` value ``"cloud"`` — is spelled inline (matching
``InputType.CLOUD.value``) to keep it dependency-free.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from . import _data, _redact

#: The input descriptor ``type`` for a cloud import (== ``InputType.CLOUD.value``).
_CLOUD_TYPE = "cloud"


class CloudProvider(str, Enum):
    """The cloud storage providers the API can import inputs from / deliver outputs to.

    The values of a cloud descriptor's ``source`` (input) / ``type`` (output)
    field. This is **build-side vocabulary only**: it types the input builder
    and the output-target ``of`` factory. Read models keep ``source`` / ``type``
    / ``status`` as **raw strings**, so an unknown provider string returned by
    the server round-trips untyped and never throws — never pass a raw provider
    string through ``CloudProvider(...)`` on the read path.

    Import support (a :class:`CloudInput` factory) exists for :attr:`AMAZON_S3`,
    :attr:`AZURE`, :attr:`FTP` and :attr:`GOOGLE_CLOUD`. :attr:`GDRIVE` and
    :attr:`YOUTUBE` are **output-only** (they validate as an output ``type`` but
    have no downloader); Google Drive *input* uses the separate ``gdrive_picker``
    input type via the generic ``add_input`` raw path.
    """

    AMAZON_S3 = "amazons3"
    AZURE = "azure"
    FTP = "ftp"
    GDRIVE = "gdrive"
    GOOGLE_CLOUD = "googlecloud"
    YOUTUBE = "youtube"


@dataclass(frozen=True, slots=True, repr=False)
class CloudInput:
    """A cloud-storage input descriptor: ``{type:"cloud", source, parameters, credentials}``.

    Hand it to ``client.convert()`` / ``convert_async()`` as the input, or to
    ``client.jobs.add_input(job_id, cloud_input)``; either way it emits the wire
    descriptor via :meth:`to_dict`. Like a remote URL, a cloud input is a
    **started** job (``process=True``), not a staged upload.

    The per-provider named constructors carry each provider's required keys
    **verbatim** — flat and lowercase, exactly as the API expects
    (``accesskeyid``, not ``access_key_id``). The required keys are constructor
    arguments (structural correctness), **not** a runtime gate: the builder never
    rejects a descriptor the permissive, asynchronously-validating server would
    accept. Optional and forward-compat keys go through the trailing
    ``parameters`` / ``credentials`` maps, or the generic :meth:`of` escape hatch.

    ``credentials`` ride in the plaintext body, so :meth:`__repr__` masks the
    **whole** credentials object to ``[REDACTED]`` and any sensitive
    ``parameters`` leaf.
    """

    source: str
    parameters: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def of(
        cls,
        source: CloudProvider | str,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> CloudInput:
        """Generic escape hatch: any provider (typed or forward-compat string) + free-form maps."""
        value = source.value if isinstance(source, CloudProvider) else source
        return cls(value, dict(parameters or {}), dict(credentials or {}))

    @classmethod
    def amazon_s3(
        cls,
        bucket: str,
        file: str,
        accesskeyid: str,
        secretaccesskey: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> CloudInput:
        """Import from Amazon S3. Extra/forward-compat keys merge in via the maps."""
        return cls(
            CloudProvider.AMAZON_S3.value,
            {"bucket": bucket, "file": file, **(parameters or {})},
            {"accesskeyid": accesskeyid, "secretaccesskey": secretaccesskey, **(credentials or {})},
        )

    @classmethod
    def azure(
        cls,
        container: str,
        file: str,
        accountname: str,
        accountkey: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> CloudInput:
        """Import from Azure Blob Storage. Extra/forward-compat keys merge in via the maps."""
        return cls(
            CloudProvider.AZURE.value,
            {"container": container, "file": file, **(parameters or {})},
            {"accountname": accountname, "accountkey": accountkey, **(credentials or {})},
        )

    @classmethod
    def ftp(
        cls,
        host: str,
        file: str,
        username: str,
        password: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> CloudInput:
        """Import from an FTP server. Extra/forward-compat keys merge in via the maps."""
        return cls(
            CloudProvider.FTP.value,
            {"host": host, "file": file, **(parameters or {})},
            {"username": username, "password": password, **(credentials or {})},
        )

    @classmethod
    def google_cloud(
        cls,
        projectid: str,
        bucket: str,
        file: str,
        keyfile: str,
        *,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> CloudInput:
        """Import from Google Cloud Storage. Extra/forward-compat keys merge in via the maps."""
        return cls(
            CloudProvider.GOOGLE_CLOUD.value,
            {"projectid": projectid, "bucket": bucket, "file": file, **(parameters or {})},
            {"keyfile": keyfile, **(credentials or {})},
        )

    def to_dict(self) -> dict[str, Any]:
        """The wire descriptor for ``POST /jobs`` (inline ``input``) / ``POST /jobs/{id}/input``."""
        return {
            "type": _CLOUD_TYPE,
            "source": self.source,
            "parameters": dict(self.parameters),
            "credentials": dict(self.credentials),
        }

    def __repr__(self) -> str:
        """Human-readable form with credentials masked — safe to log/inspect.

        The whole ``credentials`` object renders as ``[REDACTED]``; sensitive
        ``parameters`` leaves are masked too.
        """
        params = json.dumps(_redact.parameters(self.parameters), separators=(",", ":"))
        return (
            f"CloudInput(type=cloud, source={self.source}, "
            f"parameters={params}, credentials={_redact.MARKER})"
        )


@dataclass(frozen=True, slots=True, repr=False)
class OutputTarget:
    """A cloud-storage delivery target for a conversion's output.

    The wire shape is ``{type, parameters, credentials}``. Attach one (or more) to a conversion via
    ``client.convert(..., output_targets=[...])`` / ``convert_async(...)``, or inline in a raw
    ``client.jobs.create()`` conversion map. When any output target is set the conversion delivers
    straight to your storage and produces **no** local output — so ``convert()`` returns the
    completed job without downloading.

    This wave ships the **generic** shape only (``type`` + free-form ``parameters`` /
    ``credentials``); per-provider output keys live in a separate service and diverge per provider,
    so there are no per-provider output factories yet.

    Serialization (:meth:`to_dict`) emits ``{type, parameters, credentials}`` and **omits
    ``status``** (server-set, read-only). On read (:meth:`from_dict`) ``type``, ``parameters`` and
    ``status`` round-trip as raw values; ``credentials`` are **never** surfaced (the API returns
    them empty). ``credentials`` ride in the plaintext body, so :meth:`__repr__` masks the object.
    """

    type: str
    parameters: dict[str, Any] = field(default_factory=dict)
    credentials: dict[str, Any] = field(default_factory=dict)
    status: str | None = None

    @classmethod
    def of(
        cls,
        type: CloudProvider | str,
        parameters: Mapping[str, Any] | None = None,
        credentials: Mapping[str, Any] | None = None,
    ) -> OutputTarget:
        """Generic constructor accepting a typed provider or a forward-compat string."""
        value = type.value if isinstance(type, CloudProvider) else type
        return cls(value, dict(parameters or {}), dict(credentials or {}))

    def to_dict(self) -> dict[str, Any]:
        """The create-side descriptor ``{type, parameters, credentials}`` — ``status`` omitted."""
        return {
            "type": self.type,
            "parameters": dict(self.parameters),
            "credentials": dict(self.credentials),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OutputTarget:
        """Hydrate from a ``GET /jobs/{id}`` ``output_target[]`` element.

        ``type`` / ``status`` stay raw strings (an unknown provider round-trips
        untyped); ``credentials`` are deliberately not surfaced.
        """
        return cls(
            type=_data.as_str(data.get("type")),
            parameters=_data.as_object(data.get("parameters")),
            credentials={},
            status=_data.nullable_str(data.get("status")),
        )

    def __repr__(self) -> str:
        """Human-readable form with credentials masked — safe to log/inspect."""
        params = json.dumps(_redact.parameters(self.parameters), separators=(",", ":"))
        return (
            f"OutputTarget(type={self.type}, parameters={params}, "
            f"credentials={_redact.MARKER}, status={self.status})"
        )
