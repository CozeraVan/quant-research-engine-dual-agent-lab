# Implementation Brief

## Task ID

QRE-STRATEGY-STANDARDIZATION-001-FIXES

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Goal

Fix the Codex review blockers found after Claude Code standardized strategy entry/exit structure, added `strategies/high_level/` and `strategies/low_level/`, added the Bollinger mean reversion template, and rewrote the project README.

Do not expand scope beyond the required fixes below. Preserve the strategy-directory direction and the completed full-market Bollinger result.

## Required Fixes

1. Default `qre strategy-smoke` path regression
   - File: `src/quant_research_engine/apps/cli.py`
   - Problem: default strategy paths still resolve under deleted `examples/`.
   - Expected: default smoke run uses `strategies/high_level/rsi2_oversold_reversal_entry.yaml`, `strategies/high_level/ema200_bollinger_reversal_entry.yaml`, and `strategies/high_level/macd_zero_cross_momentum_entry.yaml`.
   - Add regression coverage for the no-`--strategies` default path.

2. GUI default strategy template path regression
   - File: `src/quant_research_engine/gui/app.py`
   - Problem: `DEFAULT_STRATEGY_TEMPLATE` still points to deleted `examples/ema200_bollinger_reversal.yaml`.
   - Expected: default YAML editor template comes from `strategies/low_level/ema200_bollinger_reversal.yaml` or another current low-level template.
   - Add/adjust GUI test coverage so the default template source cannot silently fall back to stale inline YAML after the strategy move.

3. Current docs still reference deleted `examples/` paths
   - Files found by Codex review:
     - `docs/modules/evaluation_layer.md`
     - `docs/modules/portfolio_workflow.md`
     - `docs/strategy_entry/three_strategy_smoke_report.md`
   - Expected: current non-legacy docs use `strategies/high_level/` for high-level compile/smoke examples and `strategies/low_level/` for executable StrategySpec examples.
   - Legacy docs under `docs/legacy/` may keep historical `examples/` references.

4. Agent workflow docs were stale
   - Files: `docs/agent/08_IMPLEMENTATION_BRIEF.md`, `docs/agent/10_REVIEW_REPORT.md`, `docs/agent/12_AGENT_BOARD.md`
   - Problem: these still described older chart/GUI tasks.
   - Expected: keep them aligned to this fix cycle until Codex re-review passes.

5. High-level EMA200 factor source mismatch
   - Files: `strategies/high_level/ema200_bollinger_reversal_entry.yaml`, compiler/catalog tests/docs as needed.
   - Evidence: compiling the high-level EMA entry emits `factors.stock_daily_overlap_typical.ema_200`, while the preserved low-level spec and existing missing-factor tests use `factors.stock_daily_overlap_typical_price.ema_200`.
   - Expected: choose the canonical upstream table/source contract and make high-level entry, compiler expectations, docs, and tests consistent. If the real upstream table is `typical_price`, use that consistently; if `typical` is canonical, update the low-level spec and docs accordingly.

6. HTML report scope lacks direct test coverage
   - Files: `src/quant_research_engine/portfolio/full_market_report.py`, `src/quant_research_engine/portfolio/io.py`, `src/quant_research_engine/portfolio/report_manifest.py`, tests.
   - Problem: `backtest_report.html` and `html_report` manifest role are now runtime behavior, but Codex found no tests that assert HTML report generation, manifest inclusion, or report-files/report-audit discoverability.
   - Expected: add focused tests for batch and shared-cash report output or justify removal/deferment if HTML report was not meant to be part of this task.

7. Full-market runner deliverable mismatch
   - File: `strategies/run_bollinger_full.py`
   - Problem: handoff says aggregate summary and standard HTML/Excel report outputs were generated, but the runner only appends `summary.csv` and progress state. The aggregate JSON exists in `outputs/`, but the script does not generate it.
   - Expected: either update the runner to produce the documented aggregate summary/report artifacts, or update docs/handoff to accurately describe the manual artifact-generation step and script output contract.

8. README command and artifact wording cleanup
   - File: `README.md`
   - Problems:
     - `qre preflight strategies/high_level/...` is documented, but `preflight` consumes low-level `StrategySpec`; `StrategySpec.from_yaml("strategies/high_level/bollinger_mean_reversion_entry.yaml")` raises `ValueError: data section is required`.
     - Excel sheet count wording says 10 sheets while chart sheets are also listed.
   - Expected: README examples match actual CLI behavior and avoid stale hardcoded counts.

## Non-Goals

- Do not rewrite portfolio architecture.
- Do not recompute indicators inside QRE.
- Do not delete or reinterpret the completed Bollinger full-market result.
- Do not move legacy archive docs just to remove historical `examples/` references.

## Validation Commands

Run at least:

```bash
uv run qre strategy-smoke --no-preflight --no-backtest --output-dir /tmp/qre-default-smoke-fix
uv run qre strategy-smoke --strategies strategies/high_level/rsi2_oversold_reversal_entry.yaml strategies/high_level/ema200_bollinger_reversal_entry.yaml strategies/high_level/macd_zero_cross_momentum_entry.yaml --no-preflight --no-backtest --output-dir /tmp/qre-explicit-smoke-fix
uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml
uv run qre compile strategies/high_level/ema200_bollinger_reversal_entry.yaml
uv run python - <<'PY'
from quant_research_engine.strategies.spec import StrategySpec
for path in [
    "strategies/low_level/bollinger_mean_reversion.yaml",
    "strategies/low_level/ema200_bollinger_reversal.yaml",
    "strategies/low_level/rsi2_reversal_research.yaml",
]:
    StrategySpec.from_yaml(path)
print("low-level specs ok")
PY
uv run pytest tests/test_cli.py tests/test_gui_app.py tests/test_gui_engine.py tests/test_compiler.py tests/test_strategy_spec.py tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

If a database is available, also run a small preflight/backtest smoke with `QRE_MARKET_DB_URL` against the moved low-level specs.
