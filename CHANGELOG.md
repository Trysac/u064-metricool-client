# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `metricool_client`: a typed, stdlib-only Metricool API client core with `MetricoolClient` (schedule posts, paginated comments, bounded retries), an injectable `Transport` with a redirect-refusing `UrllibTransport`, `PostDraft`/`Comment` models, `export_comments_csv` with OWASP CSV injection protection, and the typed `MetricoolError`.
- Initial project structure from the factory utility template.
