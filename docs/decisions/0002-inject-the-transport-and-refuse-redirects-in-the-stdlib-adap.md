# Inject the transport and refuse redirects in the stdlib adapter

Status: accepted (generated, pending human review)

## Context

The Metricool client must be testable without the network, must never leak the X-Mc-Auth token, and the verified API facts are limited to the base URL, the auth header and the userId/blogId query parameters. Endpoint paths could not be verified. urllib copies custom headers to redirect targets by default.

## Decision

All HTTP goes through a small Transport protocol returning an HttpResponse NamedTuple; tests use a fake transport. UrllibTransport is the only stdlib adapter: it accepts only https URLs, never follows redirects through a custom HTTPRedirectHandler, and caps the bytes it reads. Endpoint paths are required constructor arguments with no bundled default, and the JSON field mapping lives in one module (_endpoints.py) documented as to be verified before each release. Retries cover 429 for every method and 503 for GET only, with Retry-After honoured only as integer seconds capped at 60.

## Consequences

The core is deterministic and fully testable offline, and the token can only reach the configured https host. Callers must supply endpoint paths and may bring their own transport (for example with proxies or custom TLS). The field mapping may need adjusting once verified against the live API, which is confined to one module. Redirects surface as api_error instead of being followed.
