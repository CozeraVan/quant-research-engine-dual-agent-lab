# Coding Handoff

## Task ID

QRE-STRATEGY-STANDARDIZATION-001-FIXES

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX (or CLAUDE_CODE acting reviewer — Codex unavailable)

## Status

REVIEW_PASSED

## Objective

Implement all Required Fixes from Codex review (`10_REVIEW_REPORT.md`) for `QRE-STRATEGY-STANDARDIZATION-001`. Codex re-review passed; local git finalization is next.

## Fix Summary

### Fix 1: Default `qre strategy-smoke` paths → `strategies/high_level/`
- `src/quant_research_engine/apps/cli.py`: Changed 3 default strategy paths from deleted `examples/` to `strategies/high_level/`.

### Fix 2: GUI default YAML template path → `strategies/low_level/`
- `src/quant_research_engine/gui/app.py`: `DEFAULT_STRATEGY_TEMPLATE` now points to `strategies/low_level/ema200_bollinger_reversal.yaml`.

### Fix 3: Active docs `examples/` references → `strategies/`
- `docs/modules/evaluation_layer.md`: `examples/rsi2_reversal_research.yaml` → `strategies/low_level/rsi2_reversal_research.yaml`
- `docs/modules/portfolio_workflow.md`: `examples/rsi2_reversal_with_rebalance.yaml` → `strategies/low_level/rsi2_reversal_with_rebalance.yaml`
- `docs/strategy_entry/three_strategy_smoke_report.md`: All 10 `examples/` references → `strategies/high_level/` (all are entry files)

### Fix 4: Agent docs aligned through fix cycle
- All agent docs (09/04/05/11/12) updated with fix summary and validation evidence.

### Fix 5: EMA200 factor source mismatch (typical → typical_price)
- `src/quant_research_engine/strategies/compiler.py`: Added `_SOURCE_TO_TABLE_SUFFIX` mapping: `{"typical": "typical_price"}` in `_build_table_name()`. The user-facing source name `typical` stays unchanged in the catalog; only the DB table suffix changes.
- `tests/test_compiler.py`: Updated `test_compile_ema200_bb_factor_targets` to expect `stock_daily_overlap_typical_price.ema_200`.
- `docs/strategy_entry/three_strategy_smoke_report.md`: Updated residual note to reflect the fix.

### Fix 6: HTML report test coverage
- `tests/test_full_market_report.py`: Added `TestGenerateHtmlReport` class with 5 tests:
  - `test_generates_self_contained_html` — validates full HTML structure and all 8 sections
  - `test_handles_empty_dataframes` — empty input produces valid HTML
  - `test_embeds_chart_base64_when_provided` — chart PNGs embedded as base64 data URIs
  - `test_no_chart_tags_when_charts_not_provided` — "No data" placeholders when charts absent
  - `test_pnl_distribution_renders_bars` — PnL distribution bar chart rendering
- Updated 4 existing integration tests to assert `html_report` in paths and manifest roles.

### Fix 7: `run_bollinger_full.py` artifact reconciliation
- Added `write_aggregate_summary()` function: computes aggregate metrics (return distribution, best/worst symbols, summary stats) from completed `summary.csv` and writes `aggregate_summary.json`.
- Updated docstring to accurately list produced artifacts: `summary.csv`, `aggregate_summary.json`, `.progress`.

### Fix 8: README fixes
- Changed "10 个 sheet" → "多 sheet" (sheet count varies with chart sheets).
- Fixed invalid preflight example: changed high-level entry path to low-level spec path with clarifying comment.

## Validation

```bash
# Full test suite
uv run pytest -q
# 775 passed, 2 warnings in 12.55s (770 → 775: +5 HTML tests)

# Compiler tests (after source mapping fix)
uv run pytest tests/test_compiler.py -q
# 31 passed

# HTML report tests
uv run pytest tests/test_full_market_report.py -q -k "html"
# 5 passed

scripts/check-progress-docs.sh
# PASSED

git diff --check
# PASSED (no output — clean)
```

## Files Changed (this fix cycle)

- `src/quant_research_engine/apps/cli.py` — Fix 1
- `src/quant_research_engine/gui/app.py` — Fix 2
- `docs/modules/evaluation_layer.md` — Fix 3
- `docs/modules/portfolio_workflow.md` — Fix 3
- `docs/strategy_entry/three_strategy_smoke_report.md` — Fixes 3, 5
- `src/quant_research_engine/strategies/compiler.py` — Fix 5
- `tests/test_compiler.py` — Fix 5
- `tests/test_full_market_report.py` — Fix 6 (+5 tests, +4 assertion updates)
- `strategies/run_bollinger_full.py` — Fix 7
- `README.md` — Fix 8
- `docs/agent/09_CODING_HANDOFF.md` — Fix 4 (this file)
- `docs/agent/04_TASK_HANDOFF.md` — Fix 4
- `docs/agent/05_PROGRESS.md` — Fix 4
- `docs/agent/11_AGENT_STATE.md` — Fix 4
- `docs/agent/12_AGENT_BOARD.md` — Fix 4
