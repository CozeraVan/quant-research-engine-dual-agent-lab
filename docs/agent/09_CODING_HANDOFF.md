# Coding Handoff

## Task ID

QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001

## Written By

CODEX (brief), CLAUDE_CODE (implementation + three fix passes)

## Status

USER_ACCEPTANCE

## Current Owner

CODEX

## Implementation Summary

An optional as-of date is now threaded through the read-side metadata loading path so evaluation, preflight, research-run, and all direct backtest consumers can request metadata snapshots aligned with a specific date rather than always using the latest available snapshot. The latest-snapshot fallback is preserved when no as-of date is supplied.

The SQL pattern caps `MAX(trade_date)` inside the subquery at the as-of date (`AND trade_date <= :as_of_date`), selecting the latest available snapshot not after the requested date. This applies to `reference.daily_basic`, `reference.index_weight`, and the reference security metadata status queries.

All Codex review findings are fixed across three fix passes:

1. `stock_risk_warning` now uses as-of date instead of `CURRENT_DATE` in `_query_status_ts_codes(mode="active_range")`.
2. `_run_backtest()` passes `metadata_as_of=request.metadata_as_of` to `ResearchFrameAssembler.build()`.
3. `_write_research_manifest()` records `metadata_as_of` in `research_run_manifest.json`.
4. Direct `backtest-batch` / `backtest-shared` CLI paths accept `--metadata-as-of`, thread it into `assembler.build()`, and record it in output `run_request` payloads.
5. Direct `backtest-single` CLI path accepts `--metadata-as-of`, threads it into `assembler.build()`, and records it in output `run_request` payloads.

## Files Changed

- `src/quant_research_engine/data/interfaces.py`:
  - Added `as_of: date | None = None` parameter to `ReferenceDataStore.load_security_metadata()`.

- `src/quant_research_engine/data/postgres.py`:
  - `load_security_metadata()` accepts and threads `as_of` to all internal loaders.
  - `_load_reference_daily_basic_snapshot()` accepts `as_of`, adds `AND trade_date <= :as_of_date` inside the `MAX(trade_date)` subquery.
  - `_load_reference_index_weight_snapshot()` accepts `as_of`, same SQL pattern.
  - `_load_reference_security_metadata()` accepts `as_of`, threads to status queries.
  - `_query_status_ts_codes()` accepts `as_of`, applies as-of date in both `latest_trade_date` and `active_range` modes (fixes `stock_risk_warning` CURRENT_DATE bug).

- `src/quant_research_engine/data/assembler.py`:
  - `ResearchFrameAssembler.build()` added `metadata_as_of: date | None = None` param, threaded to `store.load_security_metadata(ts_codes=ts_codes, as_of=metadata_as_of)`.

- `src/quant_research_engine/preflight.py`:
  - `PreflightRequest` added `metadata_as_of: date | None = None` field.
  - `PreflightRunner.run()` threads `as_of=request.metadata_as_of` to `load_security_metadata()`.

- `src/quant_research_engine/orchestration/research_run.py`:
  - `ResearchRunRequest` added `metadata_as_of: date | None = None` field.
  - `_run_preflight()` threads `metadata_as_of` to `PreflightRequest()`.
  - `_run_eval()` threads `metadata_as_of` to `assembler.build()`.
  - `_run_backtest()` threads `metadata_as_of` to `assembler.build()`.
  - `_write_research_manifest()` records `metadata_as_of` in the manifest payload.

- `src/quant_research_engine/apps/cli.py`:
  - Added `--metadata-as-of` arg (type `date.fromisoformat`) to eval-config, preflight, research-run, backtest-single, backtest-batch, and backtest-shared parsers.
  - All handlers pass `metadata_as_of` to `assembler.build()` and record it in `run_request` payloads.
  - eval-smoke intentionally skipped (does not load metadata).

- `tests/test_data_assembler.py`:
  - Updated all fake store `load_security_metadata` signatures to accept `as_of=None`.
  - Added `test_metadata_as_of_passed_to_store` and `test_metadata_as_of_none_when_omitted`.

- `tests/test_preflight.py`:
  - Updated all fake store `load_security_metadata` signatures to accept `as_of=None`.
  - Added `test_preflight_threads_metadata_as_of_to_load_security_metadata` and `test_preflight_metadata_as_of_none_when_omitted`.

- `tests/test_cli.py`:
  - Added `from datetime import date` import.
  - Updated all fake store `load_security_metadata` signatures to accept `as_of=None`.
  - Added 6 tests: eval-config as-of threading/null, preflight as-of threading/null, backtest-batch as-of threading/null, backtest-shared as-of threading/null, backtest-single as-of threading/null.

- `tests/test_research_run.py`:
  - Added `test_run_eval_passes_metadata_as_of_to_assembler` using `monkeypatch.setattr` on `ResearchFrameAssembler.build`.

## Behavior Summary

- When `--metadata-as-of` is supplied, metadata loaders select the latest available snapshot not after the requested date.
- When omitted, current latest-snapshot behavior is preserved.
- The SQL pattern uses `MAX(trade_date) <= as_of_date` inside the subquery to cap the selection window.
- All metadata sources (`daily_basic`, `index_weight`, security status tables including `stock_risk_warning`) respect the as-of date.
- All CLI entry points (eval-config, preflight, research-run, backtest-single, backtest-batch, backtest-shared) accept and propagate `--metadata-as-of`.
- The change is consumer-side and read-only; no producer-side code or schema changes.

## Validation Output

```bash
uv run pytest -q → 947 passed, 2 warnings
scripts/check-progress-docs.sh → passed
git diff --check → passed
```

## Handoff Back To Codex

All required fixes are complete across all backtest entry points. Await user approval for git finalization.
