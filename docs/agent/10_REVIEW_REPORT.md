# Review Report

## Task ID

QRE-STRATEGY-STANDARDIZATION-001-FIXES

## Written By

CODEX

## Review Outcome

PASS

## Reviewed Implementation

Claude Code implemented all Required Fixes for `QRE-STRATEGY-STANDARDIZATION-001`: default strategy-smoke paths, GUI default template path, active docs path migration, EMA200 source/table alignment, HTML report coverage, Bollinger full-market runner aggregate output, README behavior cleanup, and agent workflow doc alignment. Codex added two final regression tests during re-review to lock the default smoke path and GUI template source.

## Findings

No blocking findings.

## Fix Verification

- Default `qre strategy-smoke` now resolves the three canonical entries under `strategies/high_level/` and passes in no-DB mode with preflight/backtest skipped.
- GUI default YAML template now resolves to `strategies/low_level/ema200_bollinger_reversal.yaml`.
- Active non-legacy docs no longer contain stale `examples/` path references except historical review/brief text in agent docs.
- High-level EMA200 compile target now emits `factors.stock_daily_overlap_typical_price.ema_200`, matching the preserved low-level spec and missing-factor expectations.
- HTML report output now has direct unit/integration coverage and is included in generated manifest roles.
- `strategies/run_bollinger_full.py` documents and writes `aggregate_summary.json` after chunk completion.
- README preflight examples use low-level specs, and Excel sheet-count wording no longer hardcodes stale counts.

## Validation Run By Codex

```bash
uv run pytest tests/test_cli.py::test_cli_strategy_smoke_default_strategies_use_current_paths tests/test_gui_app.py::test_default_strategy_template_uses_current_low_level_path -q
# 2 passed

uv run qre strategy-smoke --no-preflight --no-backtest --output-dir /tmp/qre-default-smoke-final
# overall_status=pass; three canonical strategies compile=pass

uv run qre strategy-smoke --strategies strategies/high_level/rsi2_oversold_reversal_entry.yaml strategies/high_level/ema200_bollinger_reversal_entry.yaml strategies/high_level/macd_zero_cross_momentum_entry.yaml --no-preflight --no-backtest --output-dir /tmp/qre-explicit-smoke-final
# overall_status=pass

uv run qre compile strategies/high_level/bollinger_mean_reversion_entry.yaml
# compile_status=ok

uv run qre compile strategies/high_level/ema200_bollinger_reversal_entry.yaml
# compile_status=ok; factor_target_ema_200=factors.stock_daily_overlap_typical_price.ema_200

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
# low-level specs ok

uv run pytest tests/test_cli.py tests/test_gui_app.py tests/test_gui_engine.py tests/test_compiler.py tests/test_strategy_spec.py tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q
# 537 passed, 2 warnings
```

## Remaining Risks

- Database-backed preflight/backtest smoke was not run because no `QRE_MARKET_DB_URL` / `SR_MARKET_DB_URL` is configured in this environment.
- `docs/legacy/` intentionally retains historical `examples/` references.

## Final Recommendation

Accept. Local git finalization completed without remote push because no remote push was requested.

## Next Agent State

- Phase: `DONE`
- Owner: `USER`
