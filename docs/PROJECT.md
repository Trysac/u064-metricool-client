# Project record

## Objective

Typed Python client core for the Metricool API: schedule posts, page through comments, export them to CSV with formula-injection protection

## Scope

- In scope: the public API documented in [README.md](../README.md), typed and tested.
- Out of scope: anything that needs runtime dependencies or I/O without an accepted ADR.

## Timeline

| Date | Event |
|---|---|
| 2026 | Repository created from the factory utility template. |

## Effort metrics

Measured values only; a value that has not been measured stays "pending measurement".

| Metric | Value |
|---|---|
| Tokens (input / output) | 444199 / 98393 |
| Hours (human) | pending measurement |
| Cost (USD) | 0.7943 |

## Factory run u064 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | claude-sonnet-5-5 | yes | 2225 | 81314 | 0 | 4246 | 0.4092 |
| fix-1 | claude-sonnet-5-5 | no | 4 | 337 | 5491 | 24396 | 0.0195 |
| fix-2 | claude-sonnet-5-5 | no | 6 | 936 | 7717 | 40944 | 0.0328 |
| fix-3 | claude-sonnet-5-5 | no | 8 | 1060 | 7734 | 55867 | 0.0355 |
| audit | claude-sonnet-5-5 | no | 12 | 3529 | 43020 | 140780 | 0.1569 |
| fix-4 | claude-sonnet-5-5 | no | 8 | 2978 | 10383 | 59891 | 0.0617 |
| docs | claude-haiku-5-5 | no | 115812 | 8239 | 0 | 0 | 0.0785 |

Total: $0.7943. Prices: Anthropic list prices.
