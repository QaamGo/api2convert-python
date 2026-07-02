"""Job polling / ``wait`` guardrails (mirrors PHP WaitTest)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from api2convert import Api2Convert, ConversionFailedError, ConversionTimeoutError

from ..conftest import MockAPI


def test_polls_until_completed(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(200, {"id": "j", "status": {"code": "processing"}})
    api.add_json(200, {"id": "j", "status": {"code": "completed"}})
    client = make_client()

    job = client.jobs.wait("j")
    assert job.is_completed()
    assert len(api.requests) == 3


def test_throws_conversion_failed_with_job_errors(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(
        200,
        {
            "id": "j",
            "status": {"code": "failed"},
            "errors": [{"code": 4000, "message": "The input file could not be processed."}],
        },
    )
    client = make_client()

    with pytest.raises(ConversionFailedError) as excinfo:
        client.jobs.wait("j")

    err = excinfo.value
    assert err.job.is_failed()
    assert len(err.errors()) == 1
    assert err.errors()[0].code == 4000
    assert "could not be processed" in err.errors()[0].message


def test_returns_failed_job_when_throw_on_failure_disabled(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "failed"}})
    client = make_client()

    job = client.jobs.wait("j", throw_on_failure=False)
    assert job.is_failed()


def test_times_out(make_client: Callable[..., Api2Convert], api: MockAPI) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "incomplete"}})
    client = make_client(poll_timeout=0)

    with pytest.raises(ConversionTimeoutError):
        client.jobs.wait("j")


def test_canceled_job_raises_conversion_failed(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "canceled"}})
    client = make_client()

    with pytest.raises(ConversionFailedError):
        client.jobs.wait("j")


def test_canceled_job_is_terminal_when_throw_on_failure_disabled(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "canceled"}})
    client = make_client()

    job = client.jobs.wait("j", throw_on_failure=False)
    assert job.is_canceled()
    assert job.is_terminal()
