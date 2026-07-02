"""Immutable client configuration.

Build via :meth:`Config.create`, which clamps every knob so a caller value can
neither busy-loop the poll (interval floor) nor poll unbounded (timeout ceiling).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Default API base URL — includes the ``/v2`` path segment, no trailing slash.
DEFAULT_BASE_URL = "https://api.api2convert.com/v2"

#: Hard floor for the job-poll interval (seconds); prevents a busy-spin self-DDOS.
MIN_POLL_INTERVAL = 0.5

#: Hard ceiling for the total job-poll timeout (4 hours); bounds an unbounded poll.
MAX_POLL_TIMEOUT = 14400


@dataclass(frozen=True, slots=True)
class Config:
    """Immutable client configuration value object.

    The constructor does not clamp — use :meth:`create` (the single entry point
    the client uses) so a caller value can never busy-loop or poll unbounded.
    """

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    #: Per-request network timeout (connect and read), in seconds.
    timeout: int = 30
    #: Automatic retries for transient failures (429 / 5xx / network).
    max_retries: int = 2
    #: First poll interval when waiting for a job, in seconds.
    poll_interval: float = 1.0
    #: Upper bound the poll interval backs off to, in seconds.
    poll_max_interval: float = 5.0
    #: How long to wait for a job to finish before giving up, in seconds.
    poll_timeout: int = 300

    @classmethod
    def create(
        cls,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        poll_interval: float | None = None,
        poll_max_interval: float | None = None,
        poll_timeout: int | None = None,
    ) -> Config:
        poll_interval_value = max(
            MIN_POLL_INTERVAL, float(poll_interval if poll_interval is not None else 1.0)
        )
        poll_max_interval_value = max(
            poll_interval_value,
            float(poll_max_interval if poll_max_interval is not None else 5.0),
        )
        poll_timeout_value = min(
            MAX_POLL_TIMEOUT,
            max(0, int(poll_timeout if poll_timeout is not None else 300)),
        )
        return cls(
            api_key=api_key,
            base_url=(base_url if base_url is not None else DEFAULT_BASE_URL).rstrip("/"),
            timeout=max(1, int(timeout if timeout is not None else 30)),
            max_retries=max(0, int(max_retries if max_retries is not None else 2)),
            poll_interval=poll_interval_value,
            poll_max_interval=poll_max_interval_value,
            poll_timeout=poll_timeout_value,
        )
