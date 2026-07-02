"""Config clamps that prevent busy-loop / unbounded-poll (mirrors PHP PollingGuardsTest)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from api2convert import Api2Convert, Config
from api2convert._config import MAX_POLL_TIMEOUT, MIN_POLL_INTERVAL

from ..conftest import MockAPI


@pytest.mark.parametrize("value", [0.0, -5.0])
def test_poll_interval_is_floored_to_a_minimum(value: float) -> None:
    assert Config.create("k", poll_interval=value).poll_interval >= MIN_POLL_INTERVAL


def test_poll_max_interval_is_never_below_the_start_interval() -> None:
    config = Config.create("k", poll_interval=3.0, poll_max_interval=1.0)
    assert config.poll_max_interval >= config.poll_interval


def test_poll_timeout_is_capped_to_a_maximum() -> None:
    assert Config.create("k", poll_timeout=10**12).poll_timeout == MAX_POLL_TIMEOUT


def test_timeout_is_never_disabled() -> None:
    assert Config.create("k", timeout=0).timeout >= 1


def test_zero_interval_is_floored_not_busy_looped(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    api.add_json(200, {"id": "j", "status": {"code": "incomplete"}})
    api.add_json(200, {"id": "j", "status": {"code": "completed"}})
    client = make_client(poll_interval=0.0)

    client.jobs.wait("j")

    assert len(api.slept) >= 1
    assert all(slept >= MIN_POLL_INTERVAL for slept in api.slept)
