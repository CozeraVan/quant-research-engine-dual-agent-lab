# Agent Board

## Current Task ID

QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001

## Current Recipient

USER

## Message Type

CODEX_TO_USER

## Sender

CODEX

## Short Message

Implementation passed review for `QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001`. Side-level failed-order diagnostics and summary analysis are now present in shared-cash summaries. All 238 tests pass. Local finalization is complete.

## Implementation Summary

1. Added `failed_order_count_by_side` and `failed_order_notional_by_side` to `_failed_order_diagnostics()` in `shared.py`. Uses `value_counts()` and `groupby().sum()` on the `side` column. Empty-failed-orders and empty-result paths return empty dicts.
2. Added side-level breakdown rendering between reason breakdown and failure_reason breakdown in `_failed_order_summary_items()` in `io.py`.
3. Added 3 tests in `test_portfolio_shared.py`: side diagnostics with triggered failed orders, empty-dict fallback when no failed orders, and empty-result side diagnostics.
4. Updated 2 existing tests in `test_portfolio_io.py` to include side-level keys in the summary dict and assert the new Markdown row.
5. Updated `01`, `03`, `04`, `05`, `08`, `09`, `10`, `11`, and `12` for finalization.

## Constraints Check

- ✅ Scope limited to side-level failed-order diagnostics and summary analysis.
- ✅ No unrelated benchmark/data-source changes.
- ✅ No forbidden files modified.
- ✅ All existing behavior preserved (additive only).
- ✅ Not pushed.

## Changed Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_portfolio_shared.py`
- `tests/test_portfolio_io.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest -q                  # 237 passed in 2.23s
scripts/check-progress-docs.sh    # passed
git diff --check                  # passed
```
