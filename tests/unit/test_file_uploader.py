"""Upload precondition + local-file guards (mirrors PHP FileUploaderTest)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from api2convert import Api2Convert, Api2ConvertError, Job, Status

from ..conftest import MockAPI


def test_upload_fails_when_job_has_no_upload_server_or_token(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    client = make_client()
    job = Job(id="j", status=Status(code="incomplete"))

    with pytest.raises(Api2ConvertError, match="no upload server/token"):
        client.jobs.upload(job, "irrelevant.txt")

    assert len(api.requests) == 0  # fails before any network call


def test_upload_fails_when_local_file_does_not_exist(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    client = make_client()
    job = Job(id="j", status=Status(code="incomplete"), token="t", server="https://s")

    with pytest.raises(Api2ConvertError, match="Input file not found"):
        client.jobs.upload(job, "/nonexistent/does-not-exist.xyz")

    assert len(api.requests) == 0


def test_explicit_empty_filename_is_not_replaced_by_basename(
    make_client: Callable[..., Api2Convert], api: MockAPI, tmp_path: Path
) -> None:
    # PHP null-coalesces the filename, so an explicit "" must NOT fall back to the
    # basename (which would leak the local filename the caller deliberately blanked).
    # httpx normalizes an empty filename to no filename attribute, same as None.
    source = tmp_path / "secret-name.txt"
    source.write_text("x")
    api.add_json(200, {"id": "in", "type": "upload"})
    client = make_client()
    job = Job(id="j", status=Status(code="incomplete"), token="t", server="https://s/v2")

    client.jobs.upload(job, source, filename="")

    assert b'filename="secret-name.txt"' not in api.body_at(0)
