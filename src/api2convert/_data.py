"""Typed, null-safe accessors over decoded JSON.

Mirrors the PHP SDK's ``Support\\Data`` helper: model hydration stays free of
scattered casts and, crucially, **never throws** on a surprising payload — a
missing or wrong-typed field falls back to a sensible default. Internal helper,
not part of the public API.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, TypeVar

T = TypeVar("T")


def as_str(value: Any, default: str = "") -> str:
    """Return ``value`` when it is a real ``str``, else ``default``.

    Does not stringify ints/floats/bools — only genuine strings pass through
    (matches PHP ``Data::string``).
    """
    return value if isinstance(value, str) else default


def nullable_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def nullable_int(value: Any) -> int | None:
    """Coerce numeric values to ``int`` (truncating toward zero), else ``None``.

    ``bool`` is rejected: it is a subclass of ``int`` in Python, but PHP's
    ``is_numeric(true)`` is ``false`` so booleans must not become ``1``/``0``.
    Numeric strings and floats are truncated (``"3.9"`` → ``3``), matching
    PHP's ``(int)`` cast semantics.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        try:
            return int(value)
        except (ValueError, OverflowError):
            return None
    if isinstance(value, str):
        try:
            return int(float(value))
        except (ValueError, OverflowError):
            return None
    return None


def as_bool(value: Any, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def as_object(value: Any) -> dict[str, Any]:
    """Return ``value`` when it is a dict (a JSON object), else an empty dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """Return a list of values.

    A JSON array passes through; a JSON object is reduced to its values (mirrors
    PHP ``array_values`` on an associative array); anything else yields ``[]``.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def map_objects(value: Any, factory: Callable[[Mapping[str, Any]], T]) -> list[T]:
    """Build a model from each dict element of ``value``; skip non-dict elements."""
    return [factory(item) for item in as_list(value) if isinstance(item, dict)]


def str_list(value: Any) -> list[str]:
    return [item for item in as_list(value) if isinstance(item, str)]
