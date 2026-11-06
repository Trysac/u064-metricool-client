# Security

This document describes the threat model of `trysac-metricool-client` (module `metricool_client`).
Report vulnerabilities as described in the repository `SECURITY.md`.

## Threat model

The library holds a Metricool user token and talks to the Metricool API through an injectable
transport. It also turns public comments, which are attacker-controlled text, into CSV files.

### Defended

| Threat | Defence |
|---|---|
| Token leakage through URLs | The token is sent only in the `X-Mc-Auth` header. `userId` and `blogId` are the only query parameters. |
| Token leakage through logs | The library logs method, path, status and attempt only, through `logging.getLogger(__name__)` with a `NullHandler`. It never configures logging and never logs headers, queries or bodies. |
| Token leakage through `repr`, `str` and errors | `repr(client)` shows only the base URL. `MetricoolError` messages are static, capped at 200 characters, and never contain request URLs, headers or response bodies. Transport failures are reduced to the exception class name. |
| Token leakage through redirects | `UrllibTransport` accepts only `https` URLs and refuses every redirect (a custom `HTTPRedirectHandler`), because urllib would copy custom headers such as `X-Mc-Auth` to the redirect target. A 3xx answer becomes `api_error`. `base_url` must be `https` and may not contain credentials, a query or a fragment. |
| Header injection | The token, `userId` and `blogId` must be printable ASCII; control characters are rejected. Endpoint paths are restricted to a safe character set and cannot contain `..`, `?`, `#` or a leading `//`. |
| Event callbacks leaking data | `on_event` payloads contain only `method`, `path`, `status` and `attempt`. A failing callback cannot break a request. |
| CSV (formula) injection | `export_comments_csv` prefixes every cell that starts with `=`, `+`, `-`, `@`, a tab or a carriage return with a single quote (OWASP CSV Injection guidance). The guard applies to every column. |
| Oversized or hostile responses | A body larger than `max_response_bytes` (default 10 MiB) raises `too_large` before parsing. `UrllibTransport` reads at most `max_read_bytes`. JSON is parsed only after the size check; a `RecursionError` or `ValueError` becomes `invalid_response`. Pages are limited by `max_pages` and items per page are capped. |
| Retry storms | Retries are bounded by `max_retries`. Only 429 (any method) and 503 (GET only, since a POST is not idempotent) are retried. `Retry-After` is honoured only as a non-negative integer of seconds and capped at 60. |

### Not defended

- A compromised token: anyone holding it can act as the user.
- A compromised host or interpreter: the token lives in process memory.
- A malicious `Transport` supplied by the caller.
- Spreadsheet applications that treat other leading characters, or content after a quote, as formulas.
  The guard follows the OWASP list only.

## Unverified API details

The base URL, the `X-Mc-Auth` header and the `userId` / `blogId` query parameters were verified on
2026-11-05 at app.metricool.com/resources/apidocs. The endpoint paths could not be verified, so they
are required constructor arguments. The JSON field names in `_endpoints.py` are this library's own
mapping and must be checked against the Metricool API guide before each release.
