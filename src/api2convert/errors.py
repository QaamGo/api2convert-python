"""The typed exception hierarchy.

Every failure raised by the SDK descends from :class:`Api2ConvertError`. HTTP
error responses (status >= 400) map to :class:`ApiError` and its subclasses;
transport failures, conversion failures, poll timeouts and webhook verification
failures descend directly from the base.

The class names use Python's ``...Error`` convention; they map 1:1 to the PHP
SDK's ``...Exception`` classes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import Job, JobMessage


class Api2ConvertError(Exception):
    """Base class for every exception raised by the SDK.

    Catch this to handle any SDK failure in one place; catch a more specific
    subclass to react to a particular failure mode.
    """


class ApiError(Api2ConvertError):
    """An HTTP error response (status >= 400).

    Used directly for a 4xx with no more specific subclass; specific statuses
    map to the dedicated subclasses below.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 0,
        request_id: str | None = None,
        body: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        #: Value of the ``X-Request-Id`` response header, if any. Quote it in support requests.
        self.request_id = request_id
        #: The decoded JSON error body, or ``{}`` when absent/unparseable.
        self.body: dict[str, Any] = body if body is not None else {}


class AuthenticationError(ApiError):
    """The API key is missing, invalid or not permitted (HTTP 401 / 403)."""


class PaymentRequiredError(ApiError):
    """The account has no remaining quota/credit (HTTP 402)."""


class NotFoundError(ApiError):
    """The requested resource does not exist (HTTP 404)."""


class ValidationError(ApiError):
    """The request was rejected as invalid, e.g. an unknown target (HTTP 400 / 422)."""


class RateLimitError(ApiError):
    """Too many requests (HTTP 429), raised only once auto-retries are exhausted."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = 429,
        request_id: str | None = None,
        body: dict[str, Any] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, request_id=request_id, body=body)
        #: Seconds to wait before retrying, parsed from the ``Retry-After`` header (raw, uncapped).
        self.retry_after = retry_after


class ServerError(ApiError):
    """A server-side error (HTTP >= 500), raised once auto-retries are exhausted."""


class NetworkError(Api2ConvertError):
    """A request did not yield a usable response.

    Raised for a transport-level failure (DNS/connection/TLS/read) once
    idempotent retries are exhausted, or for a 2xx response whose body is not
    valid JSON.
    """


class ConversionFailedError(Api2ConvertError):
    """A job reached the ``failed`` (or ``canceled``) status.

    The originating :class:`~api2convert.models.Job` is attached so you can
    inspect its errors and warnings.
    """

    def __init__(self, job: Job, message: str | None = None) -> None:
        self.job = job
        super().__init__(message if message is not None else self._build_message(job))

    def errors(self) -> list[JobMessage]:
        """The failed job's errors (may be empty if the API gave no detail)."""
        return self.job.errors

    @staticmethod
    def _build_message(job: Job) -> str:
        first = job.errors[0] if job.errors else None
        if first is not None:
            code = f" (code {first.code})" if first.code is not None else ""
            return f"Conversion failed: {first.message}{code}"
        info = job.status.info
        return f"Conversion failed: {info}" if info is not None else "Conversion failed."


class ConversionTimeoutError(Api2ConvertError):
    """A job did not reach a terminal status within the configured poll timeout.

    The job is still running server-side — re-fetch it later with
    ``client.jobs.get(job.id)`` or raise the timeout. (Maps to the PHP SDK's
    ``TimeoutException``; named to avoid shadowing the builtin ``TimeoutError``.)
    """

    def __init__(self, job: Job, timeout_seconds: int) -> None:
        self.job = job
        super().__init__(
            f"Timed out after {timeout_seconds}s waiting for job {job.id} to finish "
            f"(last status: {job.status.code})."
        )


class SignatureVerificationError(Api2ConvertError):
    """A webhook payload could not be verified against the provided signature/secret.

    Treat this as a security event: do not trust or process the payload.
    """
