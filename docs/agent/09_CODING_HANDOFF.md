# Coding Handoff

## Task ID

QRE-SHARED-FAILED-ORDER-SIDE-SUMMARY-REGRESSION-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

Reviewed and accepted locally.

## Scope Summary

- Added side-level failed-order diagnostics (`failed_order_count_by_side`, `failed_order_notional_by_side`) to `SharedCashBacktestEngine._failed_order_diagnostics` in `shared.py`.
- Added side breakdown rendering to `_failed_order_summary_items` in `io.py`.
- Added 3 tests in `test_portfolio_shared.py`: side diagnostics with triggered failed orders, empty-dict fallback when no failed orders, and empty-result side diagnostics.
- Updated 2 existing tests in `test_portfolio_io.py` to assert new side-level Markdown rows and empty-dict keys.

## Files Changed

- `src/quant_research_engine/portfolio/shared.py` — 6 lines added
- `src/quant_research_engine/portfolio/io.py` — 4 lines added
- `tests/test_portfolio_shared.py` — 59 lines added (3 new tests)
- `tests/test_portfolio_io.py` — 5 lines added (2 updated tests)

## Validation Results

```bash
uv run pytest tests/test_portfolio_shared.py -q  # 20 passed
uv run pytest tests/test_portfolio_io.py -q      # 8 passed
uv run pytest -q                                 # 238 passed in 2.22s
scripts/check-progress-docs.sh      # passed
git diff --check                    # passed
```

## Constraints

- Do not change valid-manifest behavior. ✅ preserved
- Do not modify forbidden files. ✅ compliant
- Preserve shared-cash execution behavior. ✅ additive diagnostics only
- Do not push. ✅ not pushed

## Git State

- Branch: `master`
- Local checkpoint pending commit.
