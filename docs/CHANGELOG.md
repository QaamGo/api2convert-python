# Changelog

All notable changes to this package are documented here. This project adheres to
[Semantic Versioning](https://semver.org/).

## [10.2.1] - 2026-07-08

Security hardening for downloads, config and URL handling (parity with the PHP SDK 10.2.1).

- Secret-bearing requests no longer follow redirects automatically, so the `X-Api2convert-Api-Key`,
  `X-Api2convert-Token` and `X-Api2convert-Download-Password` headers can never leak across a cross-host redirect.
  Password-less downloads are followed manually with the `X-Api2convert-*` headers dropped on cross-origin hops.
- Un-followed redirects and malformed URLs surface as a typed network error; partial download files
  are cleaned up on error.
- Dynamic URL path segments are percent-encoded, and an empty API key raises a typed configuration
  error.

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
