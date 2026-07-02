"""Defensive DTO hydration + status classification (mirrors PHP JobModelTest)."""

from __future__ import annotations

from api2convert import InputFile, Job
from api2convert._data import nullable_int


def test_hydrates_from_api_payload() -> None:
    job = Job.from_dict(
        {
            "id": "job-7",
            "token": "tok",
            "status": {"code": "completed"},
            "conversion": [{"target": "png", "options": {"quality": 85}}],
            "input": [{"id": "in", "type": "remote"}],
            "output": [{"id": "o", "uri": "https://dl/x", "filename": "result.png", "size": 2048}],
            "warnings": [{"code": 1, "message": "heads up"}],
        }
    )

    assert job.id == "job-7"
    assert job.token == "tok"
    assert job.is_completed()
    assert not job.is_failed()
    assert job.is_terminal()
    assert job.conversion[0].target == "png"
    assert job.conversion[0].options["quality"] == 85
    assert job.input[0].type == "remote"
    assert job.output[0].size == 2048
    assert job.output[0].filename == "result.png"
    assert len(job.warnings) == 1
    assert len(job.errors) == 0
    assert job.raw["id"] == "job-7"  # full payload retained


def test_unknown_status_is_non_terminal() -> None:
    job = Job.from_dict({"id": "j", "status": {"code": "something_new"}})
    assert not job.is_terminal()
    assert not job.is_completed()


def test_tolerates_missing_fields() -> None:
    job = Job.from_dict({})
    assert job.output == []
    assert job.token is None
    assert job.status.code == ""


def test_content_type_snake_case_key_is_mapped() -> None:
    input_file = InputFile.from_dict({"type": "upload", "content_type": "image/png"})
    assert input_file.content_type == "image/png"


def test_nullable_int_coercion() -> None:
    assert nullable_int(42) == 42
    assert nullable_int("42") == 42
    assert nullable_int(3.9) == 3
    assert nullable_int("3.9") == 3
    assert nullable_int(True) is None  # bool is not numeric (matches PHP is_numeric)
    assert nullable_int("abc") is None
    assert nullable_int(None) is None
