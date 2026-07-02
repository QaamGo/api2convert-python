"""End-to-end conformance against the real API.

Skipped unless ``API2CONVERT_API_KEY`` is set. Optionally point at another host
with ``API2CONVERT_BASE_URL``. Mirrors PHP tests/Live/ConversionConformanceTest.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from api2convert import Api2Convert, ValidationError

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("API2CONVERT_API_KEY"),
        reason="live tests require API2CONVERT_API_KEY",
    ),
]

REMOTE_JPG = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"


def _client() -> Api2Convert:
    base_url = os.environ.get("API2CONVERT_BASE_URL")
    return Api2Convert(base_url=base_url) if base_url else Api2Convert()


def test_converts_remote_image_to_png(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(REMOTE_JPG, "png")
        assert result.job.is_completed()
        written = result.save(tmp_path)
        assert written.stat().st_size > 0


def test_invalid_target_raises_validation_error() -> None:
    with _client() as client, pytest.raises(ValidationError):
        client.convert(REMOTE_JPG, "this-is-not-a-real-target")
