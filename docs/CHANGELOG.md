# Changelog

All notable changes to this package are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [10.2.0] - 2026-07-02

First public release of the official, hand-written Python SDK (`api2convert`), targeting Python 3.10+.
Behaviorally equivalent to the PHP SDK — same public surface and semantics per
[`docs/SDK_CONTRACT.md`](SDK_CONTRACT.md), adapted to Python idiom.

### Core
- One-call `convert(source, to, options=None)` happy path that hides the create -> upload -> poll ->
  download lifecycle for local files, URLs and binary streams; returns a `ConversionResult` with
  `save()` / `contents()` / `url()`.
- `convert_async()` for webhook-driven workflows (sets `notify_status` when a `callback` is given).
- `options(target)` to discover the valid conversion options for a target format.
- Full Jobs API (`client.jobs`) plus `client.conversions`, `client.presets`, `client.stats` and
  `client.contracts` resources.
- Automatic retries with jittered exponential backoff honoring `Retry-After`; a bare non-idempotent
  `POST` is never blindly replayed (no duplicate jobs).
- Webhook signature verification (`Api2Convert.webhooks().construct_event(...)`, HMAC-SHA256,
  constant-time comparison).
- Typed exception hierarchy rooted at `Api2ConvertError`; ships `py.typed` for full type support.
