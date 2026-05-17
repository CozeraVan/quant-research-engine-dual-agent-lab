# Coding Handoff

## Task ID

QRE-PORTFOLIO-FAILED-ORDER-DIAGNOSTICS-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Implemented

- Added `_failed_order_diagnostics()` method in `shared.py` that computes:
  - `failed_order_count` (total)
  - `failed_order_count_by_reason` (dict, keys: `entry_exit`, `rebalance`)
  - `failed_order_count_by_failure_reason` (dict, keys from market validation)
  - `failed_order_notional_by_reason` (dict)
  - `failed_order_notional_by_failure_reason` (dict)
- Integrated diagnostics into `_build_summary()` and `_empty_result()`.
- Added `_SUMMARY_LABELS` entry for `failed_order_count`.
- Added `_failed_order_summary_items()` helper for Markdown output.
- Added "Failed Orders" section to `shared_summary_markdown()`.
- Added 4 new tests in `test_portfolio_shared.py`.
- Added 2 new tests in `test_portfolio_io.py`.

## Required Fixes Applied (2026-05-17)

- Fixed `_portfolio_summary_items()` in `io.py` to exclude `failed_order_*` keys from the generic Portfolio section.
- Enhanced Markdown test to assert readable diagnostics in Failed Orders section.
- Added test that no Failed Orders section or `failed_order_*` raw dicts appear in Portfolio section when zero failures.
- Added test that zero-failed-orders summaries produce no noisy failed-order output.

## Modified Files

- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_portfolio_shared.py`
- `tests/test_portfolio_io.py`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`

## Not Implemented

- None. All brief items and Required Fixes are implemented.

## Deviations from Brief

- None. Implementation follows the brief strictly.

## Validation Commands Run

```bash
uv run pytest -q
# 162 passed in 1.59s

scripts/check-progress-docs.sh
# passed

git diff --check
# no whitespace errors
```

## Validation Results

All 162 tests pass. No regression. Both Required Fixes applied and verified.

## Known Risks

- `reason` field in failed orders is `None` for entry/exit paths; mapped to key `"entry_exit"` in dicts. If future code adds explicit reason strings for entry/exit, the mapping logic may need updating.
- Notional values in failed-order dicts may be zero when `notional` is NaN or when the order was rejected before price calculation. This is recorded as `0.0` consistently.
- The Markdown section only appears when `failed_order_count > 0`, so reports with no failed orders remain unchanged.

## Questions for Reviewer

- None.

## Git Status at Handoff

```
M docs/agent/04_TASK_HANDOFF.md
M docs/agent/05_PROGRESS.md
M docs/agent/09_CODING_HANDOFF.md
M docs/agent/11_AGENT_STATE.md
M src/quant_research_engine/portfolio/io.py
M src/quant_research_engine/portfolio/shared.py
M tests/test_portfolio_io.py
M tests/test_portfolio_shared.py
```

No new files. No forbidden files modified.

## Next Suggested Step

Codex should re-review the implementation, confirm Required Fixes are resolved, and write `docs/agent/10_REVIEW_REPORT.md`.

## Next Agent State After Implementation

- Phase: `CODEX_REVIEWING`
- Owner: `CODEX`
