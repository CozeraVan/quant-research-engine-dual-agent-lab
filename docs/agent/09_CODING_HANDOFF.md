# Coding Handoff

## Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Fixed. Codex review found metadata collision issue; now resolved.

## Implementation Summary

- Added `metadata_columns: list[str] | None = None` to `SharedCashBacktestRequest`.
- Added `_build_metadata_lookup()` method to `SharedCashBacktestEngine` — builds a symbol-keyed dict from the prepared working frame using only requested metadata columns, taking the first non-null value per symbol per column, silently skipping absent columns.
- Threaded `symbol_metadata` through all execution methods (`_execute_due_sells`, `_execute_pending_buys`, `_execute_rebalance`, `_rebalance_sell`, `_rebalance_buy`) and row builder methods (`_order_row`, `_trade_row`, `_failed_order_row`). Metadata columns are appended after existing row fields using per-key `key not in row` check to prevent collision with canonical fields.
- Added `--metadata-columns` CLI argument to `backtest-shared` (zero or more column names via `nargs="*"`).
- Passed `metadata_columns=args.metadata_columns` to `SharedCashBacktestRequest` in CLI handler.
- Recorded `metadata_columns` in `run_manifest.json` request payload when `--output-dir` is used.

## Codex Review Fix

Codex identified that `row.update(...)` could overwrite canonical output fields when a requested metadata column shared a name with an existing row field (e.g., `metadata_columns=["trade_date"]` overwrote sell order dates with the symbol's first research-frame date).

Fix: replaced `row.update(symbol_metadata[symbol])` with per-key `key not in row` guards in all three row builders (`_order_row`, `_trade_row`, `_failed_order_row`).

Regression coverage added for `trade_date` collision in orders, `exit_reason` collision in trades, and `failure_reason` collision in failed_orders.

## Files Changed

- `src/quant_research_engine/portfolio/shared.py` — `SharedCashBacktestRequest.metadata_columns`, `_build_metadata_lookup()`, threaded `symbol_metadata` with collision-safe merge
- `src/quant_research_engine/apps/cli.py` — `--metadata-columns` flag, passed to request, recorded in `run_manifest.json`
- `tests/test_portfolio_shared.py` — 9 new tests: metadata in orders/trades/failed_orders; missing columns skipped; default unchanged; empty list noop; collision protection for trade_date/exit_reason/failure_reason
- `tests/test_cli.py` — 1 new test: metadata persisted to output CSVs and run_manifest

## Validation Results

```bash
uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q  # 142 passed
uv run pytest -q                                                                              # 293 passed in 2.73s
scripts/check-progress-docs.sh                                                                # passed (after doc update)
git diff --check                                                                              # passed
```

## Constraints

- Preserve default shared-cash output behavior when no metadata columns are requested. ✅
- Keep metadata propagation request-driven and additive. ✅
- Do not alter shared-cash simulation math, order selection, cash accounting, risk exits, rebalancing, or market validation. ✅
- Missing requested columns are skipped without schema guessing. ✅
- Requested metadata must not overwrite canonical output row fields. ✅ collision-safe merge.
- Do not add shared-cash group-by reports. ✅
- Do not push. ✅

## Git State

- Branch: `master`
- All code and doc changes uncommitted.
- Ready for Codex re-review.
