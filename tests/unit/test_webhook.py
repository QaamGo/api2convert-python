"""Webhook signature verification + parsing (mirrors PHP WebhookVerifierTest)."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from api2convert import SignatureVerificationError, WebhookVerifier

SECRET = "whsec_test"
PAYLOAD = '{"id":"job-1","status":{"code":"completed"}}'


def _sign(payload: str, secret: str = SECRET) -> str:
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def test_construct_event_verifies_valid_signature() -> None:
    event = WebhookVerifier().construct_event(PAYLOAD, _sign(PAYLOAD), SECRET)
    assert event.job.id == "job-1"
    assert event.job.is_completed()
    assert event.payload["status"]["code"] == "completed"


def test_rejects_tampered_payload() -> None:
    signature = _sign(PAYLOAD)
    with pytest.raises(SignatureVerificationError):
        WebhookVerifier().construct_event(PAYLOAD + " ", signature, SECRET)


def test_rejects_missing_signature_when_secret_given() -> None:
    with pytest.raises(SignatureVerificationError, match="Missing webhook signature"):
        WebhookVerifier().construct_event("{}", None, SECRET)


def test_parse_skips_verification_with_empty_secret() -> None:
    event = WebhookVerifier().construct_event('{"id":"job-2","status":{"code":"queued"}}', None, "")
    assert event.job.id == "job-2"


def test_rejects_invalid_json() -> None:
    with pytest.raises(SignatureVerificationError, match="not valid JSON"):
        WebhookVerifier().parse("not-json")


def test_rejects_valid_json_that_is_not_an_object() -> None:
    with pytest.raises(SignatureVerificationError, match="not a JSON object"):
        WebhookVerifier().parse("123")
