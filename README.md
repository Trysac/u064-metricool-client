# metricool-client

[![PyPI version](https://img.shields.io/pypi/v/trysac-metricool-client)](https://pypi.org/project/trysac-metricool-client/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-metricool-client)](LICENSE)
[![CI](https://github.com/Trysac/u064-metricool-client/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u064-metricool-client/actions/workflows/ci.yml)

Typed Python client core for the Metricool API: schedule posts, page through comments, export them to CSV with formula-injection protection

## Problem

Social media teams that automate publishing through Metricool write one-off scripts with raw HTTP
calls, mishandle time zones and leak the API token in logs or redirects. Exported comment
spreadsheets can also carry formula-injection payloads from public commenters. This typed client
sits behind a transport interface, which makes automation testable, and ships a safe CSV exporter.

## Install

```sh
pip install trysac-metricool-client
# or
uv add trysac-metricool-client
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
from datetime import date, datetime, timezone

from metricool_client import (
    MetricoolClient,
    PostDraft,
    UrllibTransport,
    export_comments_csv,
)

client = MetricoolClient(
    "my-token",
    "my-user-id",
    "my-blog-id",
    transport=UrllibTransport(),
    # Paths are relative to base_url; check them against the Metricool API guide.
    endpoints={"schedule_post": "/path/to/schedule", "list_comments": "/path/to/comments"},
)

post_id = client.schedule_post(
    PostDraft(
        text="Hello",
        networks=("twitter",),
        publish_at=datetime(2026, 1, 2, 9, 30, tzinfo=timezone.utc),
    )
)

comments = client.list_comments("twitter", date(2026, 1, 1), date(2026, 1, 31))
with open("comments.csv", "w", newline="") as out:
    count = export_comments_csv(comments, out)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
