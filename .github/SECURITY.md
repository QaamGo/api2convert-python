# Security Policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for a security problem in this SDK.

Report it privately through GitHub's **"Report a vulnerability"** button under the
repository's *Security* tab (private vulnerability reporting). If that is
unavailable, use the support channels at <https://www.api2convert.com>. Please
avoid disclosing details publicly until a fix has been released.

## Secrets this SDK handles

The library handles two secrets on the caller's behalf — keep both out of source
control and configure them via environment variables or a secret manager:

- the **account API key** (`X-Oc-Api-Key`) — read from configuration/environment
  (`API2CONVERT_API_KEY`) and sent only over TLS to the API host, never in a URL
  query string;
- the **webhook signing secret** — used locally to verify callback signatures
  (HMAC-SHA256 over the raw request body, constant-time comparison via
  `hmac.compare_digest`). The signature is delivered in the `X-Oc-Signature` header.

The SDK never logs a key/token and never places one in an exception message. If a
key is ever exposed, revoke and rotate it in the API2Convert dashboard immediately.
