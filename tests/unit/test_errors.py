"""HTTP status -> typed exception mapping (mirrors PHP ErrorMappingTest)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from api2convert import (
    Api2Convert,
    ApiError,
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PaymentRequiredError,
    RateLimitError,
    ServerError,
    ValidationError,
)

from ..conftest import MockAPI


@pytest.mark.parametrize(
    ("status", "exc_type"),
    [
        (400, ValidationError),
        (401, AuthenticationError),
        (402, PaymentRequiredError),
        (403, AuthenticationError),
        (404, NotFoundError),
        (422, ValidationError),
        (418, ApiError),
    ],
)
def test_status_maps_to_typed_exception(
    make_client: Callable[..., Api2Convert], api: MockAPI, status: int, exc_type: type[ApiError]
) -> None:
    api.add_json(status, {"message": "boom"}, headers={"X-Request-Id": "req-42"})
    client = make_client(max_retries=0)

    with pytest.raises(exc_type) as excinfo:
        client.jobs.get("job-x")

    err = excinfo.value
    assert type(err) is exc_type
    assert err.status_code == status
    assert str(err) == "boom"
    assert err.request_id == "req-42"
    assert err.body == {"message": "boom"}


def test_rate_limit_exposes_retry_after(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(429, {"message": "slow down"}, headers={"Retry-After": "7"})
    client = make_client(max_retries=0)

    with pytest.raises(RateLimitError) as excinfo:
        client.jobs.get("job-x")

    assert excinfo.value.status_code == 429
    assert excinfo.value.retry_after == 7


def test_server_error_maps_to_server_exception(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(503, {"message": "down"})
    client = make_client(max_retries=0)

    with pytest.raises(ServerError):
        client.jobs.get("job-x")


def test_falls_back_to_reason_phrase_when_no_message(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(404, None)
    client = make_client(max_retries=0)

    with pytest.raises(NotFoundError) as excinfo:
        client.jobs.get("job-x")

    assert str(excinfo.value) != ""


def test_non_json_success_body_raises_network_error(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_text(200, "<html>maintenance</html>")
    client = make_client(max_retries=0)

    with pytest.raises(NetworkError):
        client.jobs.get("job-x")
