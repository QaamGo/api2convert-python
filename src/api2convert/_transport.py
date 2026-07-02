"""The HTTP layer: authenticated requests, transient-failure retries with
exponential backoff, error-response mapping to typed exceptions, and JSON
decoding.

Built on ``httpx``. Resources talk to the API through :meth:`Transport.request`;
the uploader and the downloader use :meth:`Transport.send` / :meth:`interpret`
directly because they need non-JSON bodies and per-job auth. Internal.
"""

from __future__ import annotations

import contextlib
import email.utils
import json
import platform
import random
import time
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import httpx

from ._config import Config
from .errors import (
    ApiError,
    AuthenticationError,
    NetworkError,
    NotFoundError,
    PaymentRequiredError,
    RateLimitError,
    ServerError,
    ValidationError,
)

_USER_AGENT: str | None = None


def _user_agent() -> str:
    global _USER_AGENT
    if _USER_AGENT is None:
        from . import __version__

        _USER_AGENT = f"api2convert-python/{__version__} python/{platform.python_version()}"
    return _USER_AGENT


class Transport:
    """Sends authenticated requests, retries transient failures, maps errors."""

    RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
    IDEMPOTENT_METHODS: frozenset[str] = frozenset(
        {"GET", "HEAD", "PUT", "DELETE", "OPTIONS", "TRACE"}
    )
    MAX_BACKOFF_SECONDS = 8.0
    #: Upper bound for an honored ``Retry-After`` — a hostile/misconfigured value
    #: asking for an absurd delay can never stall a worker for hours.
    MAX_RETRY_AFTER_SECONDS = 120.0

    def __init__(
        self,
        client: httpx.Client,
        config: Config,
        *,
        sleeper: Callable[[float], None] | None = None,
        rng: Callable[[], float] | None = None,
    ) -> None:
        self._client = client
        self._config = config
        self._sleep = sleeper if sleeper is not None else time.sleep
        self._rand = rng if rng is not None else random.random

    @property
    def config(self) -> Config:
        return self._config

    def close(self) -> None:
        self._client.close()

    def pause(self, seconds: float) -> None:
        """Sleep for (at least) ``seconds`` with a small upward jitter.

        Used by job polling; the jitter keeps a fleet from polling in lockstep.
        """
        self._sleep(self._jitter(seconds))

    def build_request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        files: Any = None,
    ) -> httpx.Request:
        return self._client.build_request(
            method, url, headers=headers, content=content, files=files
        )

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        query: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        """Perform an authenticated JSON request and return the decoded body."""
        request_headers: dict[str, str] = {"X-Oc-Api-Key": self._config.api_key}
        if headers:
            request_headers.update(headers)
        content: bytes | None = None
        if body is not None:
            content = json.dumps(body).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        url = self._url(path, query)

        def build() -> httpx.Request:
            return self.build_request(method, url, headers=request_headers, content=content)

        return self.interpret(self.send(build))

    def send(
        self,
        build: Callable[[], httpx.Request],
        *,
        stream: bool = False,
        replayable: bool = True,
        follow_redirects: bool = False,
    ) -> httpx.Response:
        """Send a request (rebuilt fresh each attempt) with retry/backoff.

        ``build`` returns a fresh :class:`httpx.Request` — a retry re-invokes it
        so a seekable body is replayed from the start. Adds the common ``Accept``
        and ``User-Agent`` headers but no auth (callers add the header they need).
        ``replayable`` must be ``False`` for a non-seekable body so it is sent once.

        ``follow_redirects`` defaults to ``False``: authenticated requests carry the
        account key / per-job token in a custom header, and httpx forwards custom
        headers across a cross-host redirect (it only strips ``Authorization``), so
        following a redirect on an authenticated request could leak the secret to
        another host. Only the self-contained download path — which sends no account
        key — opts in to redirects (storage URLs legitimately redirect).
        """
        attempt = 0
        while True:
            request = build()
            request.headers["Accept"] = "application/json"
            request.headers["User-Agent"] = _user_agent()
            idempotent = self._is_idempotent(request)

            try:
                response = self._client.send(
                    request, stream=stream, follow_redirects=follow_redirects
                )
            except httpx.TransportError as exc:
                # A non-idempotent request must not be replayed on a network error:
                # the backend may have already acted, so a blind retry could create a
                # duplicate job (and a duplicate charge).
                if replayable and idempotent and attempt < self._config.max_retries:
                    self._backoff(attempt)
                    attempt += 1
                    continue
                raise NetworkError(f"Request to API2Convert failed: {exc}") from exc

            status = response.status_code
            may_retry = (
                status in self.RETRYABLE_STATUSES
                and replayable
                and attempt < self._config.max_retries
                and (status == 429 or idempotent)
            )
            if may_retry:
                retry_after = response.headers.get("Retry-After", "")
                if stream:
                    response.close()
                self._backoff(attempt, retry_after)
                attempt += 1
                continue

            return response

    def interpret(self, response: httpx.Response) -> Any:
        """Raise a typed exception for error responses; otherwise decode JSON."""
        self.ensure_successful(response)

        raw = response.content
        if not raw:
            return {}
        try:
            decoded = json.loads(raw)
        except ValueError as exc:
            # A 2xx carrying a non-JSON body (e.g. an intermediary HTML page) must
            # surface as an SDK exception, not a bare JSON error escaping the hierarchy.
            raise NetworkError(f"API2Convert returned a non-JSON success response: {exc}") from exc
        return decoded if isinstance(decoded, dict | list) else {}

    def ensure_successful(self, response: httpx.Response) -> None:
        """Raise the appropriate typed exception when ``response`` is an HTTP error."""
        status = response.status_code
        if status < 400:
            return

        body = self._decode_safe(response)
        api_message = body.get("message")
        message = (
            api_message
            if isinstance(api_message, str)
            else (response.reason_phrase or "Request failed")
        )
        request_id = response.headers.get("X-Request-Id") or None

        if status in (401, 403):
            raise AuthenticationError(message, status_code=status, request_id=request_id, body=body)
        if status == 402:
            raise PaymentRequiredError(
                message, status_code=status, request_id=request_id, body=body
            )
        if status == 404:
            raise NotFoundError(message, status_code=status, request_id=request_id, body=body)
        if status == 429:
            raise RateLimitError(
                message,
                status_code=status,
                request_id=request_id,
                body=body,
                retry_after=self._parse_retry_after(response.headers.get("Retry-After", "")),
            )
        if status in (400, 422):
            raise ValidationError(message, status_code=status, request_id=request_id, body=body)
        if status >= 500:
            raise ServerError(message, status_code=status, request_id=request_id, body=body)
        raise ApiError(message, status_code=status, request_id=request_id, body=body)

    @contextlib.contextmanager
    def stream(
        self, uri: str, headers: Mapping[str, str] | None = None
    ) -> Iterator[httpx.Response]:
        """Open a (self-contained) download URL and yield the response stream.

        Used for output downloads — these URLs need no API key. Retry wraps only
        opening the stream + status line, never mid-stream consumption.
        """
        request_headers = dict(headers) if headers else {}

        def build() -> httpx.Request:
            return self.build_request("GET", uri, headers=request_headers)

        # Downloads carry no account key, and self-contained storage URLs legitimately
        # redirect, so this is the one path that opts in to following redirects.
        response = self.send(build, stream=True, replayable=True, follow_redirects=True)
        try:
            self.ensure_successful(response)
            yield response
        finally:
            response.close()

    def _url(self, path: str, query: Mapping[str, str] | None = None) -> str:
        url = self._config.base_url + "/" + path.lstrip("/")
        if query:
            url += "?" + urlencode(query)
        return url

    def _decode_safe(self, response: httpx.Response) -> dict[str, Any]:
        try:
            raw = response.read()
            if not raw:
                return {}
            decoded = json.loads(raw)
        except (ValueError, httpx.StreamError):
            return {}
        return decoded if isinstance(decoded, dict) else {}

    def _backoff(self, attempt: int, retry_after: str = "") -> None:
        retry = self._parse_retry_after(retry_after)
        if retry is not None and retry > 0:
            # Honor a positive Retry-After (capped so a hostile value can't stall
            # us for hours). Not jittered: the server asked for this exact delay.
            seconds = min(self.MAX_RETRY_AFTER_SECONDS, float(retry))
        else:
            # A zero/past Retry-After falls through to jittered exponential backoff
            # so we never retry-storm with no delay.
            seconds = self._jitter(min(self.MAX_BACKOFF_SECONDS, 0.5 * (2**attempt)))
        self._sleep(seconds)

    def _parse_retry_after(self, value: str) -> int | None:
        """Parse ``Retry-After`` (delay-seconds or HTTP-date) into whole seconds.

        Returns ``None`` when absent/unparseable; never negative.
        """
        if not value:
            return None
        try:
            return max(0, int(float(value)))
        except (ValueError, OverflowError):
            pass
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        delta = parsed - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))

    def _jitter(self, seconds: float) -> float:
        """Add a small upward jitter (0-25%) so correlated clients don't lockstep."""
        return seconds + seconds * 0.25 * self._rand()

    def _is_idempotent(self, request: httpx.Request) -> bool:
        if request.method.upper() in self.IDEMPOTENT_METHODS:
            return True
        return bool(request.headers.get("Idempotency-Key", ""))
