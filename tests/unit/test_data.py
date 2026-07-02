"""Coercion-helper semantics (mirrors PHP Support\\Data)."""

from __future__ import annotations

from api2convert import _data


def test_as_str_only_accepts_real_strings() -> None:
    assert _data.as_str("x") == "x"
    assert _data.as_str(5) == ""  # ints are not stringified
    assert _data.as_str(None, "d") == "d"


def test_nullable_str() -> None:
    assert _data.nullable_str("x") == "x"
    assert _data.nullable_str(5) is None


def test_nullable_int_edge_cases() -> None:
    assert _data.nullable_int(-3.9) == -3  # truncates toward zero
    assert _data.nullable_int(float("inf")) is None
    assert _data.nullable_int("inf") is None
    assert _data.nullable_int("") is None


def test_as_bool() -> None:
    assert _data.as_bool(True) is True
    assert _data.as_bool("true") is False  # only real booleans pass
    assert _data.as_bool("x", True) is True


def test_as_object() -> None:
    assert _data.as_object({"a": 1}) == {"a": 1}
    assert _data.as_object([1, 2]) == {}
    assert _data.as_object(None) == {}


def test_as_list() -> None:
    assert _data.as_list([1, 2]) == [1, 2]
    assert _data.as_list({"a": 1, "b": 2}) == [1, 2]  # object -> its values
    assert _data.as_list("x") == []


def test_str_list() -> None:
    assert _data.str_list(["a", 1, "b", None]) == ["a", "b"]


def test_map_objects_skips_non_dicts() -> None:
    seen = _data.map_objects([{"k": 1}, "skip", 3, {"k": 2}], lambda d: d["k"])
    assert seen == [1, 2]
