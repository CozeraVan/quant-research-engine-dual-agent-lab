# Task Handoff

## Current Task

QRE-STRATEGY-STANDARDIZATION-001-FIXES: Implement Codex-requested Required Fixes for strategy entry/exit standardization.

## Task ID

QRE-STRATEGY-STANDARDIZATION-001-FIXES

## Current Status

DONE. All 8 Required Fixes from Codex review are complete, Codex re-review passed, and local git finalization is complete. No remote push was requested.

## Current Owner

CODEX (re-review after fix cycle)

## Fix Summary

1. Default `qre strategy-smoke` paths → `strategies/high_level/` (`cli.py`)
2. GUI default YAML template path → `strategies/low_level/` (`gui/app.py`)
3. Active docs `examples/` references → `strategies/` (3 docs updated)
4. Agent workflow docs aligned through fix cycle (5 docs updated)
5. EMA200 factor source mismatch resolved: `_SOURCE_TO_TABLE_SUFFIX` mapping typical→typical_price in compiler (`compiler.py`, `test_compiler.py`)
6. HTML report test coverage added: `TestGenerateHtmlReport` with 5 tests; 4 existing integration tests updated (`test_full_market_report.py`)
7. `run_bollinger_full.py` now generates `aggregate_summary.json` after all chunks complete
8. README: fixed invalid high-level preflight example, changed stale "10 sheets" to "多 sheet"

## Validation

```bash
uv run pytest -q
# 775 passed, 2 warnings in 12.55s

uv run pytest tests/test_compiler.py -q
# 31 passed

scripts/check-progress-docs.sh
# PASSED

git diff --check
# PASSED
```

## Handoff To Codex

User decides the next project direction.
