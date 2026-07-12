# API2Convert Python SDK

[![CI](https://github.com/QaamGo/api2convert-python/actions/workflows/ci.yml/badge.svg)](https://github.com/QaamGo/api2convert-python/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/api2convert?cacheSeconds=3600)](https://pypi.org/project/api2convert/)
![Python](https://img.shields.io/pypi/pyversions/api2convert?cacheSeconds=3600)
![License](https://img.shields.io/badge/license-MIT-green)

The official Python client for the [API2Convert](https://www.api2convert.com) file-conversion API.
Convert, compress and transform **images, documents, audio, video, ebooks, archives and CAD** — and
run operations like OCR, merge, thumbnail and website capture — in one line of code.

```python
from api2convert import Api2Convert

client = Api2Convert("YOUR_API_KEY")

client.convert("invoice.docx", "pdf").save("invoice.pdf")
```

That single call creates a job, uploads your file, starts it, waits for it to finish and gives you
back a result you can save. No polling loops, no manual upload handling.

## Requirements

- Python 3.10+
- [`httpx`](https://www.python-httpx.org/) (installed automatically)

## Install

```bash
pip install api2convert
```

Get an API key from the [API2Convert dashboard / documentation](https://www.api2convert.com/documentation).

## Quick start

```python
from api2convert import Api2Convert

# Reads the API2CONVERT_API_KEY environment variable when no key is passed.
client = Api2Convert("YOUR_API_KEY")

# 1) From a local file
client.convert("photo.png", "jpg").save("photo.jpg")

# 2) From a URL
client.convert("https://example.com/photo.png", "jpg").save("photo.jpg")

# 3) With conversion options (discover them via client.options("jpg"))
client.convert("photo.png", "jpg", {"quality": 85, "width": 1280, "height": 720}).save("out/")
```

`convert(source, to, options=None, ...)` — `source` is a **local path, a public URL, or an open
binary stream**; `to` is the **target format**; `options` is the **conversion options** map for that
target. Less-common controls are keyword-only arguments: `category`, `timeout`, `output_index`,
`filename`, `download_password`. The returned `ConversionResult` lets you:

```python
result = client.convert("report.docx", "pdf")

result.save("report.pdf")       # stream to a file
result.save("downloads/")       # ...or a directory (keeps the server filename)
data = result.contents()        # ...or get the raw bytes
url = result.url()              # ...or just the download URL
```

## Password-protect the result

Pass `download_password` and the output is locked behind it. The SDK remembers the password and
sends it automatically when you download — you don't pass it again:

```python
result = client.convert("statement.docx", "pdf", download_password="hunter2")

result.save("statement.pdf")    # the password is applied for you
```

The download URL still needs the password from anywhere else (a browser, curl, another process),
via the `X-Api2convert-Download-Password` header. When you already hold an `OutputFile` — e.g. from the Jobs
API — hand the password to `download()`:

```python
client.download(output, "hunter2").save("out/")
```

## Asynchronous conversions & webhooks

For long-running jobs, start the conversion and get notified via a webhook instead of waiting:

```python
job = client.convert_async("movie.mov", "mp4", callback="https://your-app.example.com/webhooks/api2convert")
```

In your webhook handler, verify and parse the callback:

```python
from api2convert import Api2Convert
from api2convert import SignatureVerificationError

payload = request.body                       # the RAW body (bytes or str)
signature = request.headers.get("X-Oc-Signature")

try:
    event = Api2Convert.webhooks().construct_event(payload, signature, "YOUR_WEBHOOK_SECRET")
    job = event.job
    # ... react to job.status.code ...
except SignatureVerificationError:
    ...  # respond 400
```

> Signed webhooks are being rolled out. Until they are enabled for your account no signature is
> sent — call `Api2Convert.webhooks().parse(payload)` (or pass an empty secret) to deserialize the
> callback without verifying.

## Cloud storage

Read an input straight from your own cloud storage, and/or deliver the converted output into a
bucket — no local upload or download in between. Supports Amazon S3, Azure, FTP and Google Cloud.

Import an input with the per-provider `CloudInput` factory (keys are flat and lowercase, exactly as
the API expects) and convert it like any other source:

```python
from api2convert import Api2Convert, CloudInput

client = Api2Convert("YOUR_API_KEY")

s3_input = CloudInput.amazon_s3(
    bucket="my-bucket",
    file="invoices/report.docx",
    accesskeyid="AKIA...",
    secretaccesskey="...",
)

client.convert(s3_input, "pdf").save("report.pdf")
```

To deliver the result into a bucket instead, attach an `OutputTarget` via `output_targets`. When any
output target is set the conversion delivers straight to your storage and produces **no** local file
— so there is nothing to `save()`:

```python
from api2convert import Api2Convert, CloudProvider, OutputTarget

client = Api2Convert("YOUR_API_KEY")

target = OutputTarget.of(
    CloudProvider.AMAZON_S3,
    parameters={"bucket": "my-bucket", "file": "out/report.pdf"},
    credentials={"accesskeyid": "AKIA...", "secretaccesskey": "..."},
)

# Delivered to the bucket — the job completes without a downloadable output.
client.convert("report.docx", "pdf", output_targets=[target])
```

`azure(...)`, `ftp(...)` and `google_cloud(...)` build inputs the same way; output uses the generic
`OutputTarget` for every provider. Credentials ride in the request body but are **redacted** in
exception messages and object inspection (`repr`) as `[REDACTED]` — they are never logged or printed.

## Error handling

Every failure is a typed exception extending `api2convert.Api2ConvertError`:

```python
from api2convert import (
    Api2Convert,
    AuthenticationError,
    ConversionFailedError,
    RateLimitError,
    ValidationError,
)

try:
    Api2Convert("KEY").convert("photo.png", "jpg").save("photo.jpg")
except ValidationError as e:
    ...  # bad target / option — str(e) explains
except AuthenticationError:
    ...  # bad or missing API key
except RateLimitError as e:
    ...  # too many requests — retry after e.retry_after seconds
except ConversionFailedError as e:
    ...  # the job failed — inspect e.errors()
```

| Exception | When |
|---|---|
| `AuthenticationError` | 401 / 403 — bad or missing key |
| `PaymentRequiredError` | 402 — no remaining quota |
| `ValidationError` | 400 / 422 — invalid request (e.g. unknown target) |
| `NotFoundError` | 404 — resource doesn't exist |
| `RateLimitError` | 429 — exposes `.retry_after` |
| `ServerError` | 5xx |
| `NetworkError` | transport failure / non-JSON success body |
| `ConversionFailedError` | the job reached `failed`; exposes `.job` and `.errors()` |
| `ConversionTimeoutError` | the job didn't finish within the poll timeout |
| `SignatureVerificationError` | a webhook payload failed verification |

Transient failures (429, 5xx, network errors) are **retried automatically** with exponential backoff.

## Power user: the full job API

`convert()` is sugar over the Jobs API. Drop down to it for compound jobs, merges, presets, custom
polling or job chaining:

```python
job = client.jobs.create({
    "process": False,
    "conversion": [{"target": "pdf", "options": {"pdf_a": True}}],
})

client.jobs.upload(job, "contract.docx")                          # local file
client.jobs.add_input(job.id, {"type": "remote", "source": "https://example.com/appendix.docx"})

client.jobs.start(job.id)
done = client.jobs.wait(job.id, timeout_seconds=120)

for output in done.output:
    client.download(output).save("out/")
```

Available resources: `client.jobs`, `client.conversions` (the catalog + option discovery),
`client.presets`, `client.stats`, `client.contracts`.

Discover the valid options for any target:

```python
options = client.options("jpg")            # -> {"quality": {...}, "width": {...}, ...}
```

## Configuration

```python
client = Api2Convert(
    "YOUR_API_KEY",
    timeout=30,             # per-request network timeout (seconds)
    max_retries=2,          # automatic retries for transient failures
    poll_interval=1.0,      # first poll interval when waiting (seconds)
    poll_max_interval=5.0,  # backoff cap (seconds)
    poll_timeout=300,       # give up waiting after this many seconds
)
```

Bring your own configured `httpx.Client` by passing `http_client=...`.

## Security — never publish your API key

- **Never hard-code or commit your API key.** Load it from the environment (`API2CONVERT_API_KEY`)
  or a secrets manager.
- In CI, store it as a **masked & protected** variable and never print it to logs.
- Treat the per-job upload **token** and your **webhook signing secret** with the same care.
- The SDK never logs your key/token and never puts them in exception messages.
- If a key is ever exposed, **revoke and rotate it** in the API2Convert dashboard immediately.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'

ruff check src tests examples && ruff format --check src tests examples   # lint + format
mypy src examples                                                         # static typing (strict)
pytest -m "not live"                                     # offline unit tests
```

Live conformance tests run against the real API when `API2CONVERT_API_KEY` is set:

```bash
API2CONVERT_API_KEY=... pytest -m live
```

## Examples

Runnable, self-contained programs live in [`examples/`](examples/) — one per documented guide.
Each reads the key from `API2CONVERT_API_KEY` (and honours `API2CONVERT_BASE_URL`). Run any of
them with, e.g., `API2CONVERT_API_KEY=your-key python examples/quickstart.py`.

| Example | Guide |
|---|---|
| [`quickstart.py`](examples/quickstart.py) | Convert a remote file, look the job up, download the output |
| [`convert_files.py`](examples/convert_files.py) | Browse the conversions catalog, then convert |
| [`uploading_files.py`](examples/uploading_files.py) | One-call upload + convert of a local file |
| [`job_lifecycle.py`](examples/job_lifecycle.py) | Drive create → add input → start → wait → outputs by hand |
| [`add_watermark.py`](examples/add_watermark.py) | Stamp a PNG onto a PDF (multi-input job) |
| [`create_thumbnails.py`](examples/create_thumbnails.py) | Render a document page preview |
| [`compress_files.py`](examples/compress_files.py) | Shrink a file with the compress operation |
| [`create_archives.py`](examples/create_archives.py) | Bundle several files into a ZIP |
| [`create_hashes.py`](examples/create_hashes.py) | Compute a SHA-256 checksum |
| [`extract_assets.py`](examples/extract_assets.py) | Extract embedded assets from a document |
| [`file_analysis.py`](examples/file_analysis.py) | Extract file metadata as JSON |
| [`compare_files.py`](examples/compare_files.py) | Diff two images |
| [`capture_website.py`](examples/capture_website.py) | Screenshot a URL to PNG |
| [`audio_operations.py`](examples/audio_operations.py) | Re-encode audio (WAV → AAC) |
| [`image_operations.py`](examples/image_operations.py) | Resize an image |
| [`webhooks.py`](examples/webhooks.py) | Start a conversion asynchronously with a callback |
| [`presets.py`](examples/presets.py) | List saved conversion presets |
| [`statistics.py`](examples/statistics.py) | Read API usage for a month |
| [`rate_limits.py`](examples/rate_limits.py) | Inspect the account's contracts |
| [`authentication.py`](examples/authentication.py) | Verify the API key with an authenticated call |

The [live conformance suite](tests/live/test_conformance.py) mirrors these examples 1:1 — each test
performs the same operation and asserts success — plus two negative tests (an unknown target is a
typed `ValidationError`; a bad key is a typed `AuthenticationError` that never leaks the key).

It runs automatically against the real API on every release tag (see
`.github/workflows/live-conformance.yml`), so a published version is always verified end to end.

This SDK is hand-written and kept in sync with the API by an AI agent — see [`AGENTS.md`](AGENTS.md)
and [`docs/SDK_CONTRACT.md`](docs/SDK_CONTRACT.md). Notable changes are recorded in
[`docs/CHANGELOG.md`](docs/CHANGELOG.md).

## License

MIT — see [`LICENSE`](LICENSE).
