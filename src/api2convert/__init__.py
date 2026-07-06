"""Official Python SDK for the API2Convert file-conversion API.

Convert, compress and transform images, documents, audio, video, ebooks,
archives and CAD — and run operations like OCR, merge, thumbnail and website
capture — in one line of code::

    from api2convert import Api2Convert

    client = Api2Convert("YOUR_API_KEY")
    client.convert("invoice.docx", "pdf").save("invoice.pdf")
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from ._client import Api2Convert
from ._config import Config
from .errors import (
    Api2ConvertError,
    ApiError,
    AuthenticationError,
    ConfigurationError,
    ConversionFailedError,
    ConversionTimeoutError,
    NetworkError,
    NotFoundError,
    PaymentRequiredError,
    RateLimitError,
    ServerError,
    SignatureVerificationError,
    ValidationError,
)
from .models import (
    Conversion,
    InputFile,
    InputType,
    Job,
    JobMessage,
    JobStatus,
    OutputFile,
    Preset,
    Status,
)
from .result import ConversionResult, FileDownload
from .webhook import WebhookEvent, WebhookVerifier

try:
    __version__ = version("api2convert")
except PackageNotFoundError:  # running from a source checkout without an install
    __version__ = "0.0.0+unknown"


def webhooks() -> WebhookVerifier:
    """Webhook verifier — usable without a configured client."""
    return WebhookVerifier()


__all__ = [
    "Api2Convert",
    "Api2ConvertError",
    "ApiError",
    "AuthenticationError",
    "Config",
    "ConfigurationError",
    "Conversion",
    "ConversionFailedError",
    "ConversionResult",
    "ConversionTimeoutError",
    "FileDownload",
    "InputFile",
    "InputType",
    "Job",
    "JobMessage",
    "JobStatus",
    "NetworkError",
    "NotFoundError",
    "OutputFile",
    "PaymentRequiredError",
    "Preset",
    "RateLimitError",
    "ServerError",
    "SignatureVerificationError",
    "Status",
    "ValidationError",
    "WebhookEvent",
    "WebhookVerifier",
    "__version__",
    "webhooks",
]
