# AGENTS — maintaining the API2Convert Python SDK

This SDK is **hand-written** (not generated from OpenAPI) and kept in sync with the API by a human
**or an AI agent**. This file is the playbook for that. The model: a committed spec snapshot is the
diff baseline, a fixed behavior contract protects the ergonomics, and the test suite is the guardrail.
It is the Python port of the PHP SDK and stays behaviorally equivalent to it.

## Why hand-written

The conversion flow is multi-step (create → upload → poll → download) and the **upload step is not
in the OpenAPI spec at all**, so a generator cannot produce a usable client. We optimise for a
junior-friendly surface — one-call `convert()` — and use AI to keep it current.

## Repo layout

| Path | What it is |
|------|------------|
| `src/api2convert/_client.py` | The client + the `convert()` / `convert_async()` façade. **Hand-authored.** |
| `src/api2convert/result.py` | `ConversionResult` + `FileDownload` helpers (incl. path-traversal defense). **Hand-authored.** |
| `src/api2convert/_upload.py` | Multipart upload to the per-job server. **Hand-authored** (not in the spec). |
| `src/api2convert/resources.py` | One class per API tag (Jobs, Conversions, Presets, Stats, Contracts). **Derived** from the spec. |
| `src/api2convert/models.py` | Typed DTOs + enums (`JobStatus`, `InputType`). **Derived** from the spec. |
| `src/api2convert/_transport.py` | Transport: auth, retries/backoff, error mapping. Mostly stable infrastructure. |
| `src/api2convert/errors.py` | The typed exception hierarchy. |
| `src/api2convert/webhook.py` | Webhook verification (HMAC-SHA256, constant-time). **Hand-authored.** |
| `src/api2convert/_data.py` | Null-safe coercion helpers for defensive hydration. |
| `openapi/api2convert.openapi.json` | **Committed spec snapshot** the SDK targets — the diff baseline. |
| `docs/SDK_CONTRACT.md` | The fixed, language-agnostic public surface + semantics (shared across SDKs). |
| `tests/unit/*` | Offline golden tests (`httpx.MockTransport`). **The guardrail.** |
| `tests/live/*` | End-to-end conformance against the real API (skipped without a key). |

## How to update the SDK to a new API version

1. **Refresh the snapshot.** Fetch the latest spec and overwrite `openapi/api2convert.openapi.json`:
   ```bash
   curl -s https://api.api2convert.com/v2/openapi.json -o openapi/api2convert.openapi.json   # or /v2/schema
   git diff --stat openapi/
   ```
2. **Diff it.** Inspect the change: new/removed/renamed operations, new fields, new enum values.
3. **Update the DERIVED layer to match the diff, and nothing else:**
   - New/changed fields → update the relevant DTO in `models.py` (`from_dict` + a typed field).
   - New operation → add a method on the matching resource class (mirror the existing style).
   - New input/output target types → extend the matching enum.
4. **Do NOT change the hand-authored public API** (`convert`, `convert_async`, `download`, upload,
   polling, webhook verification, exception classes) unless `docs/SDK_CONTRACT.md` changes first.
   If a real product change requires it, update `docs/SDK_CONTRACT.md` in the same change and bump
   the **major** version.
5. **Lint + type-check + test (the guardrail):**
   ```bash
   ruff check src tests && ruff format --check src tests   # style
   mypy                                                     # PHPStan-level-8 analog (strict)
   pytest -m "not live"                                     # golden tests
   ```
   Add or update a golden test in `tests/unit/` for any new behavior. Keep `tests/live/` runnable.
6. **Record + version.** Add an entry to `docs/CHANGELOG.md`. The version is derived from the git
   tag via `hatch-vcs` — release by pushing a `vX.Y.Z` tag (per SemVer: additive spec change → minor;
   breaking public-surface change → major). There is no version constant to bump.

## Guarantees to uphold (don't break these)

- **Never commit a real API key, token or secret** — not in source, tests, fixtures, examples,
  CI files or commit messages, and never publish one anywhere. Keys come only from environment
  variables (`API2CONVERT_API_KEY`) or masked/protected CI variables; tests use obvious fakes
  (`test-key`, `whsec_test`, …). The SDK must never log or expose a key/token in errors.
- **The contract is law.** Public method names, signatures and semantics match `docs/SDK_CONTRACT.md`
  across every SDK language. Adapt only to Python idiom (snake_case, keyword-only controls, `bytes`).
- **Upload uses the per-job `X-Oc-Token`, never the account key.** There is a test for this.
- **`convert()` stays one call** for the common case (path/URL/stream → `to` → `save()`).
- **Transient failures retry; failures surface as typed exceptions.** Never leak a raw httpx/transport
  error to the caller. A bare non-idempotent `POST` is never blindly replayed (no duplicate jobs).
- **Python 3.10+, `from __future__ import annotations`, frozen dataclasses, Ruff, mypy `--strict`.**
- **Minimal dependencies.** `httpx` only at runtime. Don't add heavy deps (no pydantic).

## Conventions

- Models parse defensively via `_data` helpers (tolerate missing/extra fields — never throw on a
  surprising payload during hydration).
- Resource methods are thin: build the request, call `Transport`, hydrate a model.
- Keep the README quickstart copy-pasteable; if you change the happy path, update the README example.

## Multi-tool note

This repo ships `AGENTS.md` (this file, auto-discovered by many AI CLIs) and `docs/SDK_CONTRACT.md`
(the shared cross-language contract). Point Claude Code / Copilot / Codex at these two files.
