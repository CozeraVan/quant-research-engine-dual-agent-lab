# Coding Handoff

## Task ID

QRE-REFERENCE-MARKET-CAP-LIQUIDITY-METADATA-001

## Written By

CLAUDE_CODE

## Status

IMPLEMENTED

## Summary

Extended QRE's read-side metadata path with latest-available market-cap and liquidity metadata from `reference.daily_basic`. The composed `reference.*` metadata path and daily-derived fallback path now both receive daily_basic enrichment when the table is available.

## Files Changed

- `src/quant_research_engine/data/postgres.py` — Added `_load_reference_daily_basic_snapshot()` to query latest `reference.daily_basic` per `ts_code`; added `_compute_market_cap_bucket()` and `_compute_liquidity_bucket()` static bucket helpers; modified `load_security_metadata()` to enrich both composed-reference and daily-derived paths with daily_basic columns before normalization.
- `tests/test_postgres_store.py` — Added 7 new tests: 2 bucket mapping tests, 5 daily_basic enrichment tests.

## Behavior Summary

### Daily Basic Enrichment

- `_load_reference_daily_basic_snapshot()` queries `reference.daily_basic` for the latest snapshot per `ts_code` using `MAX(trade_date)` subquery.
- Exposes raw columns: `total_mv`, `circ_mv`, `turnover_rate`, `turnover_rate_f`, `volume_ratio` (where available).
- `_compute_market_cap_bucket()` maps `total_mv` (万元) to `small`/`mid`/`large`:
  - `small`: < 5,000,000 (50亿 RMB)
  - `mid`: 5,000,000 - 50,000,000 (50-500亿 RMB)
  - `large`: >= 50,000,000 (500亿+ RMB)
- `_compute_liquidity_bucket()` maps `turnover_rate_f` (%) to `low`/`mid`/`high`:
  - `low`: < 1.0%
  - `mid`: 1.0% - 5.0%
  - `high`: >= 5.0%

### Enrichment Rules

- Explicit `QRE_SECURITY_METADATA_TABLE` path: NO daily_basic enrichment (preserves existing behavior).
- Composed `reference.*` path: enriched with daily_basic when table exists.
- Daily-derived fallback path: enriched with daily_basic when table exists.
- Missing columns default gracefully — e.g., if `total_mv` is present but `turnover_rate_f` is missing, only `market_cap_bucket` is added.
- Missing `reference.daily_basic` table: enrichment is skipped, all existing behavior preserved.

## Validation Output

```
uv run pytest -q tests/test_postgres_store.py
35 passed in 0.68s

uv run pytest -q tests/test_preflight.py tests/test_data_assembler.py
6 passed in 0.36s

uv run pytest -q
881 passed, 2 warnings in 19.13s

scripts/check-progress-docs.sh
Progress docs check passed.

git diff --check
(clean)
```

## Handoff To Codex

Implementation is complete. Codex should review `git diff HEAD` against `08_IMPLEMENTATION_BRIEF.md`, write `10_REVIEW_REPORT.md`, and finalize or request fixes.
