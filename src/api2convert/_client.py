"""The API2Convert client — convert, compress and transform files with one call.

``convert()`` hides the multi-step job lifecycle (create -> upload -> start ->
poll -> download). For full control, use ``client.jobs`` and the other resources.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable, Mapping
from types import TracebackType
from typing import IO, Any

import httpx

from ._config import Config
from ._transport import Transport
from ._upload import FileUploader
from .models import Job, OutputFile
from .resources import (
    ContractsResource,
    ConversionsResource,
    JobsResource,
    PresetsResource,
    StatsResource,
)
from .result import ConversionResult, FileDownload
from .webhook import WebhookVerifier

_URL_RE = re.compile(r"^https?://", re.IGNORECASE)


class Api2Convert:
    """API2Convert client.

    Quick start::

        client = Api2Convert("YOUR_API_KEY")
        client.convert("invoice.docx", "pdf").save("invoice.pdf")
    """

    def __init__(
        self,
        api_key: str = "",
        *,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
        poll_interval: float | None = None,
        poll_max_interval: float | None = None,
        poll_timeout: int | None = None,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        """Build the client.

        ``api_key`` falls back to the ``API2CONVERT_API_KEY`` environment
        variable when empty. Pass ``http_client`` to bring your own configured
        :class:`httpx.Client`.
        """
        api_key = api_key or os.environ.get("API2CONVERT_API_KEY", "")
        if not api_key:
            raise ValueError(
                "No API key provided. Pass it to the constructor or set the "
                "API2CONVERT_API_KEY environment variable."
            )

        config = Config.create(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            poll_interval=poll_interval,
            poll_max_interval=poll_max_interval,
            poll_timeout=poll_timeout,
        )

        self._owns_client = http_client is None
        if http_client is None:
            # follow_redirects stays False here (the default): the transport opts into
            # redirects only on the no-auth download path, so a cross-host redirect can
            # never carry the account key. Redirect-following is set per-request anyway.
            http_client = httpx.Client(timeout=httpx.Timeout(float(config.timeout)))
        elif not isinstance(http_client, httpx.Client):
            raise TypeError("http_client must be an httpx.Client instance.")

        self._transport = Transport(http_client, config, sleeper=sleeper)
        uploader = FileUploader(self._transport)
        self._jobs = JobsResource(self._transport, uploader)
        self._conversions = ConversionsResource(self._transport)
        self._presets = PresetsResource(self._transport)
        self._stats = StatsResource(self._transport)
        self._contracts = ContractsResource(self._transport)

    def convert(
        self,
        source: str | os.PathLike[str] | IO[bytes],
        to: str,
        options: Mapping[str, Any] | None = None,
        *,
        category: str | None = None,
        timeout: int | None = None,
        output_index: int | None = None,
        filename: str | None = None,
        download_password: str | None = None,
    ) -> ConversionResult:
        """Convert a file and wait for the result.

        Hand it a local path, a public URL, or an open stream, name the target
        format, and get back a result you can ``save()``. ``options`` are the
        target-specific conversion options (discover them via :meth:`options`).
        A ``download_password`` is remembered and applied automatically on download.
        """
        job = self._start_conversion(
            source, to, options, category, None, filename, download_password
        )
        done = self._jobs.wait(job.id, timeout)
        return ConversionResult(
            done,
            self._transport,
            output_index if output_index is not None else 0,
            download_password,
        )

    def convert_async(
        self,
        source: str | os.PathLike[str] | IO[bytes],
        to: str,
        options: Mapping[str, Any] | None = None,
        *,
        callback: str | None = None,
        category: str | None = None,
        filename: str | None = None,
        download_password: str | None = None,
    ) -> Job:
        """Start a conversion without waiting.

        Pass a ``callback`` URL to be notified (sets ``notify_status``), or poll
        later with ``client.jobs.get(job.id)`` / ``client.jobs.wait(job.id)``.
        """
        return self._start_conversion(
            source, to, options, category, callback, filename, download_password
        )

    def download(self, output: OutputFile, download_password: str | None = None) -> FileDownload:
        """A :class:`FileDownload` for an output file.

        A ``download_password`` is remembered and sent automatically on download
        (overridable per call).
        """
        return FileDownload(self._transport, output, download_password)

    def options(self, target: str, category: str | None = None) -> dict[str, Any]:
        """Discover the valid options (type / enum / default / range) for a target."""
        return self._conversions.options(target, category)

    @property
    def jobs(self) -> JobsResource:
        return self._jobs

    @property
    def conversions(self) -> ConversionsResource:
        return self._conversions

    @property
    def presets(self) -> PresetsResource:
        return self._presets

    @property
    def stats(self) -> StatsResource:
        return self._stats

    @property
    def contracts(self) -> ContractsResource:
        return self._contracts

    @staticmethod
    def webhooks() -> WebhookVerifier:
        """Webhook verifier — usable without a configured client."""
        return WebhookVerifier()

    def close(self) -> None:
        """Close the underlying HTTP client (only if this client created it)."""
        if self._owns_client:
            self._transport.close()

    def __enter__(self) -> Api2Convert:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _start_conversion(
        self,
        source: str | os.PathLike[str] | IO[bytes],
        to: str,
        options: Mapping[str, Any] | None,
        category: str | None,
        callback: str | None,
        filename: str | None,
        download_password: str | None,
    ) -> Job:
        conversion: dict[str, Any] = {"target": to}
        if category is not None:
            conversion["category"] = category
        if options:
            conversion["options"] = dict(options)

        payload: dict[str, Any] = {"conversion": [conversion]}
        if callback is not None:
            payload["callback"] = callback
            payload["notify_status"] = True
        if download_password is not None:
            payload["download_passwords"] = [download_password]

        if isinstance(source, str) and _URL_RE.match(source):
            payload["process"] = True
            payload["input"] = [{"type": "remote", "source": source}]
            return self._jobs.create(payload)

        payload["process"] = False
        created = self._jobs.create(payload)
        self._jobs.upload(created, source, filename)
        return self._jobs.start(created.id)
