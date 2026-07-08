"""Live conformance suite — the canonical, cross-SDK set of scenarios that
exercises the real API2Convert API end to end.

Every scenario mirrors one of the documented example guides (and its runnable
counterpart in ``examples/``), so this file doubles as an executable tour of the
SDK: convert, discover, drive the job lifecycle by hand, run operations, and
handle the typed errors.

Because these hit the real API and consume quota, the whole module is gated: it
is skipped unless ``API2CONVERT_API_KEY`` is set. Point at another host (e.g. a
beta environment) with ``API2CONVERT_BASE_URL``. Run them with::

    API2CONVERT_API_KEY=<key> pytest -m live

Never commit a real key — it is read only from the environment.

The positive scenarios map 1:1 to the 20 documented example guides (see
``examples/``); two negative scenarios cover the typed error paths:

    quickstart, convert-files, uploading-files, job-lifecycle, add-watermark,
    create-thumbnails, compress-files, create-archives, create-hashes,
    extract-assets, file-analysis, compare-files, capture-website,
    audio-operations, image-operations, webhooks, presets, statistics,
    rate-limits, authentication
    + invalid-target (ValidationError) and bad-key (AuthenticationError).
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

# Public example fixtures (stable, hosted by online-convert.com). ---------------
PDF = "https://example-files.online-convert.com/document/pdf/example.pdf"
PNG = "https://example-files.online-convert.com/raster%20image/png/example.png"
JPG = "https://example-files.online-convert.com/raster%20image/jpg/example.jpg"
JPG_SMALL = "https://example-files.online-convert.com/raster%20image/jpg/example_small.jpg"
WAV = "https://example-files.online-convert.com/audio/wav/example.wav"
DOCX = "https://example-files.online-convert.com/document/docx/example.docx"
ZIP = "https://example-files.online-convert.com/archive/zip/example.zip"

#: A minimal valid 1x1 PNG, written to disk to exercise the real multipart
#: upload handshake (remote-URL inputs skip upload entirely).
ONE_PX_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc00000000301010018dd8db00000000049454e44ae426082"
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


# 1. quickstart — convert a remote URL, get the job, download the output --------
def test_quickstart(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(JPG, "png")
        assert result.job.is_completed()

        job = client.jobs.get(result.job.id)
        assert job.is_completed()

        written = result.save(tmp_path)
        assert written.stat().st_size > 0


# 2. convert-files — browse the catalog, then convert --------------------------
def test_convert_files(tmp_path: Path) -> None:
    with _client() as client:
        catalog = client.conversions.list()
        assert len(catalog) > 0

        to_png = client.conversions.list(target="png")
        assert len(to_png) > 0

        result = client.convert(JPG, "png")
        assert result.job.is_completed()
        assert result.save(tmp_path).stat().st_size > 0


# 3. uploading-files — one-call upload + convert of a local file ---------------
def test_uploading_files(tmp_path: Path) -> None:
    src = tmp_path / "pixel.png"
    src.write_bytes(ONE_PX_PNG)

    with _client() as client:
        result = client.convert(src, "png")
        assert result.job.is_completed()
        assert len(result.contents()) > 0


# 4. job-lifecycle — create -> add input -> start -> wait -> outputs -----------
def test_job_lifecycle() -> None:
    with _client() as client:
        jobs = client.jobs
        job = jobs.create(
            {"process": False, "conversion": [{"category": "image", "target": "png"}]}
        )
        assert job.id

        jobs.add_input(job.id, {"type": "remote", "source": JPG})
        jobs.start(job.id)

        finished = jobs.wait(job.id)
        assert finished.is_completed()

        outputs = jobs.outputs(job.id)
        assert len(outputs) > 0
        assert len(outputs) == len(finished.output)
        assert outputs[0].uri


# 5. add-watermark — stamp a PNG onto a PDF (two remote inputs) ----------------
def test_add_watermark() -> None:
    with _client() as client:
        jobs = client.jobs
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {"type": "remote", "source": PDF},
                    {"type": "remote", "source": PNG},
                ],
                "conversion": [
                    {
                        "category": "document",
                        "target": "pdf",
                        "options": {"stamp": True, "alignment": "center"},
                    }
                ],
            }
        )
        finished = jobs.wait(job.id)
        assert finished.is_completed()
        assert len(jobs.outputs(job.id)) > 0


# 6. create-thumbnails — render a document page preview ------------------------
def test_create_thumbnails(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(
            PDF,
            "thumbnail",
            {"thumbnail_target": "png", "width": 300, "pages": "first", "dpi": 150},
            category="operation",
        )
        assert result.job.is_completed()
        assert result.save(tmp_path).stat().st_size > 0


# 7. compress-files — shrink a file with the compress operation ----------------
def test_compress_files(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(
            JPG, "compress", {"compression_level": "high"}, category="operation"
        )
        assert result.job.is_completed()
        assert result.save(tmp_path).stat().st_size > 0


# 8. create-archives — bundle two files into a ZIP ----------------------------
def test_create_archives() -> None:
    with _client() as client:
        jobs = client.jobs
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {"type": "remote", "source": PDF},
                    {"type": "remote", "source": PNG},
                ],
                "conversion": [{"category": "archive", "target": "zip"}],
            }
        )
        finished = jobs.wait(job.id)
        assert finished.is_completed()
        assert len(jobs.outputs(job.id)) > 0


# 9. create-hashes — compute a SHA-256 checksum -------------------------------
def test_create_hashes() -> None:
    with _client() as client:
        result = client.convert(ZIP, "sha256", category="hash")
        assert result.job.is_completed()
        assert len(result.contents()) > 0


# 10. extract-assets — pull embedded assets out of a document -----------------
def test_extract_assets() -> None:
    with _client() as client:
        result = client.convert(DOCX, "extract-assets", category="operation")
        assert result.job.is_completed()
        assert len(result.outputs()) > 0


# 11. file-analysis — extract file metadata as JSON ---------------------------
def test_file_analysis() -> None:
    with _client() as client:
        result = client.convert(JPG, "json", category="metadata")
        assert result.job.is_completed()
        assert len(result.contents()) > 0


# 12. compare-files — diff two images -----------------------------------------
def test_compare_files() -> None:
    with _client() as client:
        jobs = client.jobs
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {"type": "remote", "source": JPG_SMALL},
                    {"type": "remote", "source": JPG},
                ],
                "conversion": [
                    {
                        "category": "operation",
                        "target": "compare-image",
                        "options": {"method": "ssim", "threshold": 5, "diff_color": "red"},
                    }
                ],
            }
        )
        finished = jobs.wait(job.id)
        assert finished.is_completed()


# 13. capture-website — screenshot a URL to PNG -------------------------------
def test_capture_website() -> None:
    with _client() as client:
        jobs = client.jobs
        job = jobs.create(
            {
                "process": True,
                "input": [
                    {
                        "type": "remote",
                        "source": "https://www.online-convert.com",
                        "engine": "screenshot",
                        "options": {
                            "screen_width": 1280,
                            "screen_height": 1024,
                            "device_scale_factor": 1,
                        },
                    }
                ],
                "conversion": [{"category": "image", "target": "png"}],
            }
        )
        finished = jobs.wait(job.id)
        assert finished.is_completed()
        assert len(jobs.outputs(job.id)) > 0


# 14. audio-operations — re-encode WAV -> AAC ---------------------------------
def test_audio_operations(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(
            WAV,
            "aac",
            {
                "audio_codec": "aac",
                "audio_bitrate": 192,
                "channels": "stereo",
                "frequency": 44100,
            },
            category="audio",
        )
        assert result.job.is_completed()
        assert result.save(tmp_path).stat().st_size > 0


# 15. image-operations — resize an image --------------------------------------
def test_image_operations(tmp_path: Path) -> None:
    with _client() as client:
        result = client.convert(
            JPG,
            "resize-image",
            {
                "width": 800,
                "height": 600,
                "resize_by": "px",
                "resize_handling": "keep_aspect_ratio_crop",
            },
            category="operation",
        )
        assert result.job.is_completed()
        assert result.save(tmp_path).stat().st_size > 0


# 16. webhooks — start async with a callback (do NOT wait for the webhook) -----
def test_webhooks() -> None:
    with _client() as client:
        job = client.convert_async(
            DOCX,
            "pdf",
            callback="https://your-app.example.com/api2convert/webhook",
            category="document",
        )
        assert job.id
        # A started job has been created server-side but is not yet terminal.
        assert not job.is_failed()


# 17. presets — list saved presets (may be empty) -----------------------------
def test_presets() -> None:
    with _client() as client:
        presets = client.presets.list(category="video", target="mp4")
        assert isinstance(presets, list)


# 18. statistics — read usage for a recent month ------------------------------
def test_statistics() -> None:
    with _client() as client:
        stats = client.stats.month("2026-06")
        assert stats is not None


# 19. rate-limits — inspect the account's contracts ---------------------------
def test_rate_limits() -> None:
    with _client() as client:
        contracts = client.contracts.get()
        assert contracts is not None


# 20. authentication — an authenticated call succeeds -------------------------
def test_authentication() -> None:
    with _client() as client:
        jobs = client.jobs.list()
        assert isinstance(jobs, list)


# Negative: validation error on an unknown target -----------------------------
#
# The API rejects an unknown target — either synchronously at create time
# (a ``ValidationError``) or as a failed job (a ``ConversionFailedError``).
def test_invalid_target_is_a_typed_error() -> None:
    with _client() as client, pytest.raises((ValidationError, ConversionFailedError)):
        client.convert(JPG, "this-is-not-a-real-target")


# Negative: authentication error, with no secret leak -------------------------
#
# A bad key produces a typed ``AuthenticationError`` carrying the HTTP status.
# Crucially, the SDK never puts a credential into an error message.
def test_authentication_error_leaks_no_secret() -> None:
    bogus_key = "a2c-invalid-key-for-testing"
    with _client(bogus_key) as client, pytest.raises(AuthenticationError) as excinfo:
        client.jobs.list()

    error = excinfo.value
    assert error.status_code in (401, 403)
    assert bogus_key not in str(error)
