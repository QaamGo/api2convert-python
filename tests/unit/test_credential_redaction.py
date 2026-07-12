"""Cloud-connector fixture 3 — the credential redaction / isolation suite.

The single secret ``SUPERSECRET123`` must never appear on any rendering/error
path, and the fixed marker ``[REDACTED]`` must appear where a credentials object
is rendered. Mirrors the PHP ``CredentialRedactionTest``.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from api2convert import Api2Convert, CloudInput, CloudProvider, OutputTarget, ValidationError

from ..conftest import MockAPI

SECRET = "SUPERSECRET123"
MARKER = "[REDACTED]"


# ---- 3a: object rendering --------------------------------------------------------------


def test_cloud_input_repr_masks_credentials() -> None:
    rendered = repr(
        CloudInput.amazon_s3(bucket="b", file="f", accesskeyid="AKIA", secretaccesskey=SECRET)
    )

    assert SECRET not in rendered
    assert MARKER in rendered
    # str() falls through to __repr__, so the inspection path is masked too.
    assert SECRET not in str(
        CloudInput.amazon_s3(bucket="b", file="f", accesskeyid="AKIA", secretaccesskey=SECRET)
    )
    # Non-secret parameters still render.
    assert '"bucket":"b"' in rendered


def test_output_target_repr_masks_credentials() -> None:
    rendered = repr(
        OutputTarget.of(
            CloudProvider.FTP,
            {"host": "ftp.example.com"},
            {"username": "u", "password": SECRET},
        )
    )

    assert SECRET not in rendered
    assert MARKER in rendered


# ---- 3b + 3c: error text and error-body deep-walk --------------------------------------


def test_create_path_error_never_leaks_submitted_credential(
    make_client: Callable[..., Api2Convert], api: MockAPI
) -> None:
    # A 422 whose decoded body echoes the submitted secret in a nested/dotted key (belt-and-
    # suspenders: the real API echoes field *names* only). The convert() request body itself
    # carried the secret in credentials — it must not surface on the exception either.
    api.add_json(
        422,
        {
            "message": "Validation failed",
            "errors": {"input.0.credentials.secretaccesskey": SECRET},
        },
    )

    with pytest.raises(ValidationError) as excinfo:
        make_client(max_retries=0).convert(CloudInput.amazon_s3("b", "f", "AKIA", SECRET), "jpg")

    error = excinfo.value
    # 3b: no secret in the message or anywhere on the exception.
    assert SECRET not in str(error)
    # 3c: the deep-walk masks the echoed secret to the marker.
    body_json = json.dumps(error.body)
    assert SECRET not in body_json
    assert MARKER in body_json


# ---- 3d: sensitive parameters leaf -----------------------------------------------------


def test_sensitive_parameters_leaf_is_masked_in_rendering() -> None:
    rendered = repr(CloudInput.of(CloudProvider.AMAZON_S3, {"token": "PARAMSECRET", "bucket": "b"}))

    assert "PARAMSECRET" not in rendered
    assert MARKER in rendered
    # A non-secret key renders normally.
    assert '"bucket":"b"' in rendered
