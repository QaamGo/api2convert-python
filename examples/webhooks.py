"""Webhooks — start a conversion asynchronously and be notified via a callback.

``convert_async`` returns immediately with a STARTED job; the API POSTs to your
``callback`` URL when the job finishes. Verify and parse that callback in your
HTTP handler with ``Api2Convert.webhooks()`` (see ``on_webhook`` below).

Run with:
    API2CONVERT_API_KEY=your-key python examples/webhooks.py
"""

from __future__ import annotations

import os
import sys

from api2convert import Api2Convert, Api2ConvertError, SignatureVerificationError

DOCX = "https://example-files.online-convert.com/document/docx/example.docx"
CALLBACK_URL = "https://your-app.example.com/api2convert/webhook"


def main() -> int:
    client = Api2Convert(base_url=os.environ.get("API2CONVERT_BASE_URL") or None)
    try:
        # Kick off the conversion; do NOT wait — the callback notifies us later.
        job = client.convert_async(DOCX, "pdf", callback=CALLBACK_URL, category="document")
        print(f"Started job {job.id} (status: {job.status.code})")
        print(f"API2Convert will POST the result to: {CALLBACK_URL}")
    except Api2ConvertError as error:
        print(f"Failed: {error}", file=sys.stderr)
        return 1
    return 0


def on_webhook(raw_body: bytes, signature_header: str | None, secret: str) -> None:
    """Handle the callback POST in your web app.

    Pass the RAW request body and the ``X-Oc-Signature`` header. With signed
    webhooks enabled, verification is byte-exact; until then, pass an empty
    secret (or use ``Api2Convert.webhooks().parse(raw_body)``) to skip it.
    """
    try:
        event = Api2Convert.webhooks().construct_event(raw_body, signature_header, secret)
    except SignatureVerificationError:
        return  # respond 400 in a real handler
    job = event.job
    if job.is_completed():
        for output in job.output:
            print(f"Job {job.id} done: {output.uri}")
    elif job.is_failed():
        first = job.errors[0].message if job.errors else "unknown"
        print(f"Job {job.id} failed: {first}")


if __name__ == "__main__":
    raise SystemExit(main())
