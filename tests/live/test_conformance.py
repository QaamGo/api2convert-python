"""Live conformance suite — the canonical, cross-SDK set of scenarios that
exercises the real API2Convert API end to end.

Every scenario is written to read like an idiomatic usage example, so this file
doubles as an executable tour of the SDK: build a client, convert, discover,
drive the job lifecycle by hand, and handle the typed errors.

Because these hit the real API and consume quota, the whole module is gated: it
is skipped unless ``API2CONVERT_API_KEY`` is set. Point at another host (e.g. a
beta environment) with ``API2CONVERT_BASE_URL``. Run them with::

    API2CONVERT_API_KEY=<key> pytest -m live

Never commit a real key — it is read only from the environment.

The seven scenarios mirror the shared spec implemented by every api2convert SDK
(php, python, java, go, nodejs, dotnet, ruby, rust):

1. ``test_convert_remote_url_to_png``            — one-call convert of a URL
2. ``test_upload_local_file_and_convert``        — multipart upload of a file
3. ``test_convert_with_options``                 — apply conversion options
4. ``test_discover_conversion_catalog``          — options/catalog discovery
5. ``test_manual_job_lifecycle_and_inspection``  — create → input → start → wait
6. ``test_invalid_target_is_a_typed_error``      — validation error handling
7. ``test_authentication_error_leaks_no_secret`` — auth error, no key leak
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api2convert import (
    Api2Convert,
    AuthenticationError,
    ConversionFailedError,
    ValidationError,
)

# The whole file auto-skips (passes) unless a key is present, so a keyless run
# still validates import/collection without ever touching the network.
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("API2CONVERT_API_KEY"),
        reason="live tests require API2CONVERT_API_KEY",
    ),
]

#: A small, stable public image used as a remote input across the suite.
REMOTE_JPG = "https://example-files.online-convert.com/raster%20image/jpg/example_small.jpg"

#: A minimal valid 1x1 PNG, written to disk to exercise the real multipart
#: upload handshake (remote-URL inputs skip upload entirely).
ONE_PX_PNG = bytes(
    (
        0x89,
        0x50,
        0x4E,
        0x47,
        0x0D,
        0x0A,
        0x1A,
        0x0A,
        0x00,
        0x00,
        0x00,
        0x0D,
        0x49,
        0x48,
        0x44,
        0x52,
        0x00,
        0x00,
        0x00,
        0x01,
        0x00,
        0x00,
        0x00,
        0x01,
        0x08,
        0x02,
        0x00,
        0x00,
        0x00,
        0x90,
        0x77,
        0x53,
        0xDE,
        0x00,
        0x00,
        0x00,
        0x0C,
        0x49,
        0x44,
        0x41,
        0x54,
        0x08,
        0xD7,
        0x63,
        0xF8,
        0xCF,
        0xC0,
        0x00,
        0x00,
        0x00,
        0x03,
        0x01,
        0x01,
        0x00,
        0x18,
        0xDD,
        0x8D,
        0xB0,
        0x00,
        0x00,
        0x00,
        0x00,
        0x49,
        0x45,
        0x4E,
        0x44,
        0xAE,
        0x42,
        0x60,
        0x82,
    )
)


def _client(api_key: str | None = None) -> Api2Convert:
    """Build a client the idiomatic way.

    With no ``api_key`` the constructor reads ``API2CONVERT_API_KEY`` from the
    environment; ``API2CONVERT_BASE_URL`` (when set) retargets the host so the
    same suite can run against prod or a beta environment.
    """
    base_url = os.environ.get("API2CONVERT_BASE_URL") or None
    if api_key is not None:
        return Api2Convert(api_key, base_url=base_url)
    return Api2Convert(base_url=base_url)


# 1. One-call convert of a remote URL ---------------------------------------
#
# The simplest usage: hand ``convert`` a URL and a target format. The SDK
# creates a server-side-fetch job, polls it to completion, and hands back a
# result you can save straight to disk.
def test_convert_remote_url_to_png(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(REMOTE_JPG, "png")
        assert result.job.is_completed()

        written = result.save(tmp_path)
        assert written.stat().st_size > 0


# 2. Upload and convert a local file ----------------------------------------
#
# For a local path (or bytes / a stream), the SDK stages the job, streams the
# file to the per-job upload server (authenticated with the job's token, never
# your account key), starts it, polls, and downloads.
def test_upload_local_file_and_convert(tmp_path: Path) -> None:
    src = tmp_path / "pixel.png"
    src.write_bytes(ONE_PX_PNG)

    with _client() as client:
        result = client.convert(src, "jpg")
        assert result.job.is_completed()

        data = result.contents()
        assert len(data) > 0
        # A JPEG starts with the SOI marker 0xFF 0xD8.
        assert data[:2] == b"\xff\xd8"


# 3. Apply conversion options -----------------------------------------------
#
# Pass target-specific options as the third argument. Discover the valid keys
# for a target with ``client.options`` (see the next scenario); here we
# re-encode at a lower JPEG quality.
def test_convert_with_options() -> None:
    with _client() as client:
        result = client.convert(
            REMOTE_JPG,
            "jpg",
            # Add e.g. "width": 64, "height": 64 to resize.
            {"quality": 50},
        )
        assert result.job.is_completed()

        data = result.contents()
        assert len(data) > 0


# 4. Discover the conversion catalog ----------------------------------------
#
# ``client.conversions.list`` and ``client.options`` describe what the API can
# do — which targets exist and which options each accepts. Neither consumes
# conversion quota, so they are cheap to call before building a request.
def test_discover_conversion_catalog() -> None:
    with _client() as client:
        # Which conversions target "jpg"?
        conversions = client.conversions.list(target="jpg")
        assert len(conversions) > 0

        # The option schema for a target (type / enum / default / range per option).
        options = client.options("png", "image")
        assert isinstance(options, dict)


# 5. Drive the full job lifecycle by hand -----------------------------------
#
# ``convert`` is built from these primitives. Driving them yourself unlocks
# compound/merge jobs, custom inputs, and step-by-step inspection: create a
# staged job, attach an input, start it, wait for completion, then inspect the
# job's status and output metadata.
def test_manual_job_lifecycle_and_inspection() -> None:
    with _client() as client:
        jobs = client.jobs

        # Stage a job (process=False) so we can attach inputs before starting.
        job = jobs.create({"process": False, "conversion": [{"target": "png"}]})
        assert job.id

        # Attach a remote input, then start processing.
        jobs.add_input(job.id, {"type": "remote", "source": REMOTE_JPG})
        jobs.start(job.id)

        # Poll to a terminal status.
        finished = jobs.wait(job.id)
        assert finished.is_completed()

        # Inspect the outputs — both from the finished job and via the outputs API.
        assert len(finished.output) > 0
        outputs = jobs.outputs(job.id)
        assert len(outputs) == len(finished.output)

        first = finished.output[0]
        assert first.uri
        # Output size, if reported, should be positive.
        assert first.size is None or first.size > 0


# 6. Validation error on an unknown target ----------------------------------
#
# The API rejects an unknown target — either synchronously at create time
# (a ``ValidationError``) or as a failed job (a ``ConversionFailedError``).
# Both are typed errors you can catch.
def test_invalid_target_is_a_typed_error() -> None:
    with _client() as client, pytest.raises((ValidationError, ConversionFailedError)):
        client.convert(REMOTE_JPG, "this-is-not-a-real-target")


# 7. Authentication error, with no secret leak ------------------------------
#
# A bad key produces a typed ``AuthenticationError`` carrying the HTTP status.
# Crucially, the SDK never puts a credential into an error message — we assert
# the bogus key does not appear in the rendered error.
def test_authentication_error_leaks_no_secret() -> None:
    bogus_key = "a2c-invalid-key-for-testing"

    # A second client built with a deliberately invalid key. Call an
    # authenticated endpoint (jobs list) and expect it to be rejected.
    with _client(bogus_key) as client, pytest.raises(AuthenticationError) as excinfo:
        client.jobs.list()

    error = excinfo.value
    assert error.status_code in (401, 403)
    assert bogus_key not in str(error)
