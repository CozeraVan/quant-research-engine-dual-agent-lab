# Task Handoff

## Task ID

QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001

## Current Status

USER_ACCEPTANCE

## Current Owner

CODEX

## Problem Summary

Cross-sectional metadata was loaded as the latest available snapshot in all read-side paths. An optional as-of date now threads through the shared metadata loading path so eval/preflight/research-run and all direct backtest consumers can consume metadata aligned with a specific date while preserving the existing latest-snapshot fallback.

## Implementation Summary

- Added `as_of: date | None = None` to `ReferenceDataStore.load_security_metadata()` and all internal PostgreSQL loaders.
- SQL `MAX(trade_date)` subqueries now accept an optional `AND trade_date <= :as_of_date` clause that caps the selection window.
- `_query_status_ts_codes()` applies as-of date in both `latest_trade_date` and `active_range` modes (fixes `stock_risk_warning` CURRENT_DATE bug).
- `ResearchFrameAssembler.build()`, `PreflightRequest`, and `ResearchRunRequest` carry `metadata_as_of`.
- `_run_backtest()` passes `metadata_as_of` to `assembler.build()` and `_write_research_manifest()` records `metadata_as_of` in `research_run_manifest.json`.
- All direct CLI entry points (backtest-single, backtest-batch, backtest-shared) now accept `--metadata-as-of`, thread it into `assembler.build()`, and record it in output `run_request` payloads.
- `--metadata-as-of` CLI arg exposed on eval-config, preflight, research-run, backtest-single, backtest-batch, and backtest-shared.
- 13 new tests across assembler, preflight, CLI, and research-run test files.
- Latest-snapshot fallback preserved when as-of is omitted.

## Hard Constraints

- No Tushare download, credential, sync, or ingestion code added to QRE.
- `../quant_ts` not modified.
- Portfolio execution semantics unchanged.
- No new producer-side code.
- QRE remains read-only against upstream databases.

## Validation Evidence

```bash
uv run pytest -q → 947 passed, 2 warnings
scripts/check-progress-docs.sh → passed
git diff --check → passed
```

## Handoff To Codex

All required fixes are complete. Await user approval for git finalization.
