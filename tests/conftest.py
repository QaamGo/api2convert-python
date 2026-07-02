"""Shared test harness.

``MockAPI`` is the Python analog of the PHP suite's ``php-http/mock-client``: a
FIFO queue of canned responses plus a recorded list of outgoing requests, served
through an :class:`httpx.MockTransport`. The client's ``sleeper`` is redirected
into ``MockAPI.slept`` so retry/poll timing is asserted without real waits.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from api2convert import Api2Convert
from api2convert._config import Config
from api2convert._transport import Transport


class MockAPI:
    """A queue of canned responses + a record of the requests that consumed them."""

    def __init__(self) -> None:
        self._queue: deque[tuple[str, Any, Any, dict[str, str]]] = deque()
        self.requests: list[httpx.Request] = []
        self.bodies: list[bytes] = []
        self.slept: list[float] = []

    def add_json(
        self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        content = b"" if body is None else json.dumps(body).encode("utf-8")
        hdrs = dict(headers or {})
        if body is not None:
            hdrs.setdefault("content-type", "application/json")
        self._queue.append(("resp", status, content, hdrs))

    def add_text(
        self, status: int = 200, text: str = "", headers: dict[str, str] | None = None
    ) -> None:
        self._queue.append(("resp", status, text.encode("utf-8"), dict(headers or {})))

    def add_error(self, exc: Exception) -> None:
        self._queue.append(("err", exc, None, {}))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.bodies.append(request.read())
        self.requests.append(request)
        kind, payload, content, headers = self._queue.popleft()
        if kind == "err":
            raise payload
        return httpx.Response(status_code=payload, content=content, headers=headers)

    def request_at(self, index: int) -> httpx.Request:
        return self.requests[index]

    def json_at(self, index: int) -> Any:
        return json.loads(self.bodies[index])

    def body_at(self, index: int) -> bytes:
        return self.bodies[index]


@pytest.fixture
def api() -> MockAPI:
    return MockAPI()


@pytest.fixture
def make_client(api: MockAPI) -> Callable[..., Api2Convert]:
    def _make(**opts: Any) -> Api2Convert:
        http_client = httpx.Client(
            transport=httpx.MockTransport(api.handler), follow_redirects=True
        )
        return Api2Convert("test-key", http_client=http_client, sleeper=api.slept.append, **opts)

    return _make


@pytest.fixture
def make_transport(api: MockAPI) -> Callable[..., Transport]:
    def _make(**opts: Any) -> Transport:
        http_client = httpx.Client(
            transport=httpx.MockTransport(api.handler), follow_redirects=True
        )
        config = Config.create("test-key", **opts)
        return Transport(http_client, config, sleeper=api.slept.append)

    return _make
