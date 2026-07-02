"""Webhook callback verification and parsing.

Pass the **raw** request body (bytes or the exact string received) so signature
verification is byte-exact. Verification uses HMAC-SHA256 and matches the
server's signed-webhooks scheme; until signed webhooks are enabled on your
account no signature is sent — use :meth:`WebhookVerifier.parse` then, or call
:meth:`construct_event` with an empty secret to skip verification.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .errors import SignatureVerificationError
from .models import Job


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """A verified webhook callback. The API posts the job whose status changed."""

    #: The job whose status changed.
    job: Job
    #: The full decoded callback body.
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> WebhookEvent:
        return cls(job=Job.from_dict(payload), payload=dict(payload))


class WebhookVerifier:
    """Verifies and parses webhook callbacks."""

    def construct_event(
        self, payload: str | bytes, signature: str | None, secret: str
    ) -> WebhookEvent:
        """Verify the signature (when a secret is given) and return the typed event.

        ``payload`` must be the raw request body. ``signature`` is the value of
        the signature header (``X-Oc-Signature``). Pass an empty ``secret`` to
        skip verification. Raises :class:`SignatureVerificationError` when the
        signature is missing or does not match.
        """
        if secret != "":
            if signature is None or signature == "":
                raise SignatureVerificationError("Missing webhook signature header.")
            expected = hmac.new(
                secret.encode("utf-8"), _to_bytes(payload), hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(expected.encode("ascii"), signature.encode("utf-8")):
                raise SignatureVerificationError("Webhook signature verification failed.")

        return self.parse(payload)

    def parse(self, payload: str | bytes) -> WebhookEvent:
        """Parse a callback body into a typed event WITHOUT verifying a signature.

        Only use this when signed webhooks are not yet enabled for your account.
        """
        try:
            decoded = json.loads(payload)
        except ValueError as exc:
            raise SignatureVerificationError(f"Webhook payload is not valid JSON: {exc}") from exc
        if not isinstance(decoded, dict):
            raise SignatureVerificationError("Webhook payload is not a JSON object.")
        return WebhookEvent.from_dict(decoded)


def _to_bytes(payload: str | bytes) -> bytes:
    return payload if isinstance(payload, bytes) else payload.encode("utf-8")
