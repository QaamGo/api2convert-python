"""Retry, backoff and Retry-After guardrails (mirrors PHP RetryTest + polling guards).

High-level cases drive ``client.jobs``; the low-level replay/idempotency gates are
exercised directly on :class:`Transport` (as the PHP suite builds it directly).
"""

from __future__ import annotations

import email.utils
from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from api2convert import Api2Convert, NetworkError, ServerError
from api2convert._transport import Transport

from ..conftest import MockAPI

COMPLETED_JOB = {"id": "j", "status": {"code": "completed"}}


def test_retries_transient_status_then_succeeds(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(503, {"message": "x"})
    api.add_json(429, {"message": "x"})
    api.add_json(200, COMPLETED_JOB)
    client = make_client(max_retries=2)

    job = client.jobs.get("j")
    assert job.is_completed()
    assert len(api.requests) == 3


def test_retries_network_error_then_succeeds(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_error(httpx.ConnectError("boom"))
    api.add_json(200, COMPLETED_JOB)
    client = make_client(max_retries=1)

    assert client.jobs.get("j").is_completed()
    assert len(api.requests) == 2


def test_network_error_exhausted_raises_with_cause(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_error(httpx.ConnectError("boom"))
    api.add_error(httpx.ConnectError("boom"))
    client = make_client(max_retries=1)

    with pytest.raises(NetworkError) as excinfo:
        client.jobs.get("j")

    assert isinstance(excinfo.value.__cause__, httpx.ConnectError)
    assert len(api.requests) == 2


def test_create_job_is_not_retried_on_server_error(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"})
    client = make_client(max_retries=2)

    with pytest.raises(ServerError):
        client.jobs.create({"conversion": [{"target": "pdf"}]})

    assert len(api.requests) == 1  # bare POST must not be replayed (no duplicate job)


def test_create_with_idempotency_key_is_retried_on_server_error(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"})
    api.add_json(200, {"id": "job-1", "status": {"code": "incomplete"}})
    client = make_client(max_retries=2)

    job = client.jobs.create({"conversion": [{"target": "pdf"}]}, idempotency_key="idem-1")

    assert job.id == "job-1"
    assert len(api.requests) == 2
    assert api.request_at(0).headers["Idempotency-Key"] == "idem-1"


# --- low-level Transport gating ------------------------------------------------


def _post(transport: Transport, headers: dict[str, str] | None = None) -> httpx.Request:
    return transport.build_request("POST", "https://api.test/x", headers=headers, content=b"{}")


def _get(transport: Transport) -> httpx.Request:
    return transport.build_request("GET", "https://api.test/x")


def test_non_seekable_body_is_not_retried(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    for _ in range(3):
        api.add_json(429, {"message": "slow"})
    transport = make_transport(max_retries=3)

    response = transport.send(lambda: _post(transport), replayable=False)

    assert response.status_code == 429
    assert len(api.requests) == 1


def test_seekable_non_idempotent_post_is_not_retried_on_server_error(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"})
    api.add_json(503, {"message": "down"})
    transport = make_transport(max_retries=2)

    response = transport.send(lambda: _post(transport), replayable=True)

    assert response.status_code == 503
    assert len(api.requests) == 1


def test_post_with_idempotency_key_is_retried_on_server_error(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"})
    api.add_json(503, {"message": "down"})
    api.add_json(200, {"ok": True})
    transport = make_transport(max_retries=2)

    response = transport.send(lambda: _post(transport, {"Idempotency-Key": "key-123"}))

    assert response.status_code == 200
    assert len(api.requests) == 3


def test_rate_limited_post_is_retried_even_without_idempotency_key(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    api.add_json(429, {"message": "slow"})
    api.add_json(200, {"ok": True})
    transport = make_transport(max_retries=1)

    response = transport.send(lambda: _post(transport))

    assert response.status_code == 200
    assert len(api.requests) == 2


def test_honored_retry_after_is_clamped_to_ceiling(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    api.add_json(429, {"message": "slow"}, headers={"Retry-After": "99999"})
    api.add_json(200, {"ok": True})
    transport = make_transport(max_retries=1)

    transport.send(lambda: _get(transport))

    assert api.slept == [120.0]  # clamped to MAX_RETRY_AFTER_SECONDS, not jittered


def test_retry_after_http_date_is_parsed_and_clamped(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    future = email.utils.format_datetime(datetime.now(timezone.utc) + timedelta(hours=1))
    api.add_json(503, {"message": "down"}, headers={"Retry-After": future})
    api.add_json(200, {"ok": True})
    transport = make_transport(max_retries=1)

    transport.send(lambda: _get(transport))

    assert api.slept == [120.0]


def test_retry_after_zero_falls_back_to_backoff(
    make_transport: Callable[..., Transport], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"}, headers={"Retry-After": "0"})
    api.add_json(200, {"ok": True})
    transport = make_transport(max_retries=1)

    transport.send(lambda: _get(transport))

    assert len(api.slept) == 1
    assert api.slept[0] >= 0.5  # jittered exponential backoff, never a 0-delay retry storm
