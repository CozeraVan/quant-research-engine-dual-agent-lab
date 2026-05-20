# Task Handoff

## Current Task

Add request-driven metadata passthrough columns to shared-cash order, trade, and failed-order outputs.

## Task ID

QRE-SHARED-CASH-METADATA-OUTPUTS-001

## Current Status

Accepted locally.

## Current Owner

USER

## Completed

- Added `metadata_columns: list[str] | None = None` to `SharedCashBacktestRequest`.
- Added `_build_metadata_lookup()` method — builds symbol-keyed dict from working frame using only requested columns, first non-null value per symbol, silently skips absent columns.
- Threaded `symbol_metadata` through all execution methods and row builders with collision-safe merge (per-key `key not in row` guard).
- Added `--metadata-columns` CLI argument to `backtest-shared` with `nargs="*"`.
- Passed `metadata_columns` to `SharedCashBacktestRequest` and recorded in `run_manifest.json`.
- Added 9 engine tests (orders/trades/failed_orders metadata, missing columns skipped, default unchanged, empty list noop, collision protection for trade_date/exit_reason/failure_reason).
- Added 1 CLI test (metadata persisted to output CSVs and run_manifest).
- Fixed Codex-identified collision: `row.update(...)` replaced with per-key guards preventing metadata from overwriting canonical row fields.
- Updated `09_CODING_HANDOFF.md`.
- Codex re-reviewed and accepted the implementation.

## In Progress

None.

## Expected Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_shared.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/10_REVIEW_REPORT.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Recorded on 2026-05-20 after Codex final review:

- `uv run pytest tests/test_portfolio_shared.py tests/test_cli.py tests/test_portfolio_io.py -q` -> `142 passed in 2.18s`
- `uv run pytest -q` -> `293 passed in 2.80s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Do not add shared-cash group-by reports in this task.
- Do not change shared-cash portfolio math, order selection, cash accounting, risk exits, rebalancing, or market validation.
- Metadata propagation must be request-driven. Do not copy all factor or market columns into output rows.
- Missing requested columns should be skipped rather than guessed.
- Treat requested metadata columns as static symbol metadata for this task; time-varying metadata semantics remain future work.
- Requested metadata must not overwrite canonical output row fields such as `trade_date`, `entry_date`, `exit_date`, `cost`, or `net_pnl`. ✅ collision-safe merge.

## Next Suggested Step

None. Await next task selection.
