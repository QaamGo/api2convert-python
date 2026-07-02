"""Example webhook receiver (stdlib ``http.server``).

Point a job's ``callback`` at this endpoint and verify the payload before trusting
it. Run with:

    API2CONVERT_WEBHOOK_SECRET=whsec_... python examples/webhook.py
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

from api2convert import Api2Convert, SignatureVerificationError

# Fail closed: an empty secret makes construct_event() skip signature verification
# entirely, so refuse to run rather than trust an unverified body. If your account
# has not enabled signed webhooks yet, confirm that and switch deliberately to
# Api2Convert.webhooks().parse(payload) instead of leaving the secret unset.
SECRET = os.environ.get("API2CONVERT_WEBHOOK_SECRET", "")
if not SECRET:
    print(
        "API2CONVERT_WEBHOOK_SECRET is not set; refusing to accept unverified webhooks.",
        file=sys.stderr,
    )
    raise SystemExit(1)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # http.server dispatch method name
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)  # the RAW body
        signature = self.headers.get("X-Oc-Signature")

        try:
            event = Api2Convert.webhooks().construct_event(payload, signature, SECRET)
        except SignatureVerificationError:
            self._respond(400, "invalid signature")
            return

        job = event.job
        if job.is_completed():
            for output in job.output:
                print(f"Job {job.id} done: {output.uri}")
        elif job.is_failed():
            first = job.errors[0].message if job.errors else "unknown"
            print(f"Job {job.id} failed: {first}")

        self._respond(200, "ok")

    def _respond(self, status: int, body: str) -> None:
        self.send_response(status)
        self.end_headers()
        self.wfile.write(body.encode())


if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8000), WebhookHandler).serve_forever()
