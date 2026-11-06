# metricool-client

[![PyPI version](https://img.shields.io/pypi/v/trysac-metricool-client)](https://pypi.org/project/trysac-metricool-client/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-metricool-client)](LICENSE)
[![CI](https://github.com/Trysac/u064-metricool-client/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u064-metricool-client/actions/workflows/ci.yml)

Typed Python client core for the Metricool API: schedule posts, page through comments, export them to CSV with formula-injection protection

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-metricool-client
# or
uv add trysac-metricool-client
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import metricool_client

# normalize() trims surrounding whitespace and lower-cases the text.
print(metricool_client.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    metricool_client.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
