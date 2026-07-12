"""Credential redaction for cloud connectors.

Cloud ``credentials`` ride in the plaintext request body, so they must never
surface where a value object or an SDK-emitted string could leak them. This
helper centralizes the masks the contract mandates (mirrors the PHP SDK's
``Support\\Redactor``):

- the **whole ``credentials`` object** collapses to :data:`MARKER` on every
  object-inspection path (``__repr__`` / ``__str__``);
- any ``parameters`` leaf whose key contains a sensitive token
  (:data:`SENSITIVE_SUBSTRINGS`, case-insensitive substring) collapses to
  :data:`MARKER` (see :func:`parameters`);
- the decoded error body is deep-walked (:func:`redact_body`) as
  belt-and-suspenders — the API only ever echoes field *names*, never a
  credential *value*, but a future server/proxy change must not leak one.

Internal helper, not part of the public API.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

#: The fixed, fleet-wide redaction marker (D9).
MARKER = "[REDACTED]"

#: Case-insensitive substrings that mark a key as carrying a secret. A key
#: containing any of these has its whole value masked.
SENSITIVE_SUBSTRINGS: tuple[str, ...] = (
    "token",
    "password",
    "passwd",
    "secret",
    "key",
    "keyfile",
    "credential",
    "passphrase",
    "sas",
    "sig",
    "signature",
)


def is_sensitive_key(key: str) -> bool:
    """Whether a key name marks its value as sensitive (case-insensitive substring)."""
    lower = key.lower()
    return any(needle in lower for needle in SENSITIVE_SUBSTRINGS)


def _walk(value: Any) -> Any:
    """Deep-walk any decoded JSON value, masking sensitive keys to :data:`MARKER`.

    A mapping key matching :func:`is_sensitive_key` has its whole value replaced;
    nested mappings and lists are walked recursively; scalars pass through.
    """
    if isinstance(value, Mapping):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and is_sensitive_key(key):
                out[key] = MARKER
            else:
                out[key] = _walk(item)
        return out
    if isinstance(value, list):
        return [_walk(item) for item in value]
    return value


def parameters(params: Mapping[str, Any]) -> dict[str, Any]:
    """Mask sensitive leaves of a ``parameters`` map.

    Any key matching :func:`is_sensitive_key` has its value replaced by
    :data:`MARKER`; nested maps/lists are walked recursively. Non-secret keys
    (``bucket``, ``host``, ``file``, ``container``, ``projectid``, …) are left
    untouched.
    """
    return cast("dict[str, Any]", _walk(dict(params)))


def redact_body(body: Mapping[str, Any]) -> dict[str, Any]:
    """Deep-walk a decoded error body and mask every sensitive key's value.

    Handles a flattened/dotted key like ``input.0.credentials.secretaccesskey``
    (it contains ``secret``/``key``) as well as nested structures.
    """
    return cast("dict[str, Any]", _walk(dict(body)))
