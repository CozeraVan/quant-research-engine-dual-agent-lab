# Progress

> Archived Note:
> This document was created before the dual-agent workflow migration.
> Current authoritative planning, progress, handoff, and review documents live in docs/agent/.
> Keep this file for historical reference only.

## 2026-05-17

- Reoriented the active work from `indicators_tushare` repair to `quant-research-engine` planning.
- Inspected QRE docs, source layout, CLI, tests, configs, and examples.
- Confirmed QRE full tests pass: `145 passed in 1.27s`.
- Ran fresh read-only QRE database smokes against latest available data window:
  - market bars loaded through `qre db-smoke`
  - factor values loaded through `qre factor-smoke`
  - strategy evaluation plumbing checked through `qre eval-config`
- Checked `quant_ts` structure and systemd timer status.
- Confirmed previous indicators data write was limited to three smoke-test stocks and recorded it for review.
- Created file-based planning records:
  - `task_plan.md`
  - `findings.md`
  - `progress.md`
- Updated QRE and research-level planning/status files:
  - `docs/mvp_plan.md`
  - `进度.md`
  - `/home/van/quant-workspace/research-notes/current_status.md`
  - `/home/van/quant-workspace/research-notes/handoff.md`
- Reverted the QRE-adjacent indicators documentation/code additions from the earlier smoke-write pass; no further indicators repair work is part of the current QRE plan.
- Re-ran QRE full tests during the current audit:
  - `uv run pytest -q`
  - result: `145 passed in 1.14s`
- Synchronized stale QRE md status:
  - `docs/modules/portfolio_workflow.md`
  - `docs/modules/portfolio_layer.md`
  - `docs/modules/evaluation_layer.md`

## Current Blocker

Phase 4 first implementation is complete. Shared-cash now has lot-level FIFO accounting and T+1 sellable inventory checks.

## 2026-05-17 Phase 2 Preflight

- Added read-only preflight implementation:
  - `src/quant_research_engine/preflight.py`
- Added CLI:
  - `qre preflight`
- Added tests:
  - `tests/test_preflight.py`
  - `tests/test_cli.py::test_cli_preflight_prints_read_only_report`
- Red test observed first:
  - missing module: `No module named 'quant_research_engine.preflight'`
- Green verification:
  - `uv run pytest tests/test_preflight.py tests/test_cli.py::test_cli_preflight_prints_read_only_report -q`
  - result: `2 passed`
- Related verification:
  - `uv run pytest tests/test_preflight.py tests/test_cli.py tests/test_data_assembler.py tests/test_postgres_store.py -q`
  - result: `54 passed`
- Real read-only DB smoke:
  - `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre preflight examples/rsi2_reversal_research.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH --benchmark-table public.stock_daily --benchmark-code 000002.SZ --benchmark-value-column close`
  - result: `status=ok`, `market_rows=15`, `factor_rsi_2_coverage_ratio=1.0`, `join_coverage_ratio=1.0`
- Full verification:
  - `uv run pytest -q`
  - result: `147 passed in 1.22s`

## 2026-05-17 Phase 2 Preflight Optimization

- Added strategy universe parsing in `StrategySpec`:
  - `exclude_st`
  - `exclude_suspended`
  - `exclude_risk_warning`
  - `min_listing_days`
  - `min_amount`
- Added preflight universe/liquidity diagnostics:
  - `universe_total_symbols`
  - `universe_eligible_symbols`
  - `universe_excluded_new_listing`
  - `universe_excluded_st`
  - `universe_excluded_risk_warning`
  - `universe_excluded_suspended`
  - `universe_excluded_low_amount`
- TDD red tests:
  - missing `StrategySpec.exclude_st`
  - missing `PreflightRequest.min_listing_days`
- Target tests:
  - `uv run pytest tests/test_strategy_spec.py::test_strategy_spec_loads_factor_fields_from_yaml tests/test_preflight.py::test_preflight_runner_reports_universe_filter_diagnostics -q`
  - result: `2 passed`
- Related verification:
  - `uv run pytest tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_data_assembler.py tests/test_postgres_store.py -q`
  - result: `59 passed`
- Real read-only DB smoke:
  - result: `status=ok`, `universe_total_symbols=3`, `universe_eligible_symbols=3`
- Full verification:
  - `uv run pytest -q`
  - result: `148 passed in 1.18s`

## 2026-05-17 Phase 3 Evaluation Metrics

- Added IC / Rank IC / quantile return support:
  - `src/quant_research_engine/evaluation/models.py`
  - `src/quant_research_engine/evaluation/engine.py`
  - `src/quant_research_engine/strategies/spec.py`
  - `src/quant_research_engine/apps/cli.py`
- Added tests:
  - `tests/test_evaluation_forward_returns.py`
  - `tests/test_strategy_spec.py`
  - `tests/test_cli.py`
- TDD red tests:
  - `EvaluationRequest` missing `factor_columns`
  - `StrategySpec` missing `quantiles`
  - CLI missing `ic_summary` and `quantile_summary` output
- Target and related verification:
  - IC/quantile target tests: `2 passed`
  - YAML/CLI target tests: `2 passed`
  - evaluation/CLI/strategy related suite: `51 passed`
- Real read-only DB smoke:
  - `research_rows=15`
  - `event_rows=5`
  - IC summary generated for `rsi_2`
  - quantile summary emitted zero-count rows because 3-symbol smoke is smaller than configured 5 quantiles
- Full verification:
  - `uv run pytest -q`
  - result: `151 passed in 1.28s`

## 2026-05-17 Phase 3 Friction-Adjusted Screening

- Added rough friction-adjusted event screening:
  - `round_trip_cost_rate`
  - `adjusted_forward_return_<horizon>`
  - adjusted mean/median/win-rate summary columns
- Added CLI inputs:
  - `--round-trip-cost-rate`
  - `--market-profile`
- TDD red tests:
  - `EvaluationRequest` missing `round_trip_cost_rate`
  - CLI missing `--round-trip-cost-rate`
  - CLI missing `--market-profile` for cost-rate estimation
- Target tests:
  - `uv run pytest tests/test_evaluation_forward_returns.py::test_evaluation_engine_computes_friction_adjusted_event_summary tests/test_cli.py::test_cli_eval_config_accepts_round_trip_cost_rate -q`
  - result: `2 passed`
  - `uv run pytest tests/test_cli.py::test_cli_eval_config_can_estimate_round_trip_cost_from_market_profile tests/test_cli.py::test_cli_eval_config_accepts_round_trip_cost_rate -q`
  - result: `2 passed`
- Related tests:
  - `uv run pytest tests/test_evaluation_forward_returns.py tests/test_evaluation_signals.py tests/test_strategy_spec.py tests/test_cli.py tests/test_config_loader.py -q`
  - result: `55 passed`
- Real read-only DB smoke:
  - `round_trip_cost_rate=0.00212`
  - horizon 1 `mean_adjusted_forward_return=-0.010319842669621836`
- Full verification:
  - `uv run pytest -q`
  - result: `154 passed in 1.33s`

## 2026-05-17 Phase 4 Shared-Cash Lot Accounting

- Added lot-level accounting to shared-cash positions:
  - FIFO realized PnL for partial rebalance sells
  - T+1 sellable inventory check using `entry_bar_index`
- Added tests:
  - `test_shared_cash_rebalance_partial_sell_uses_fifo_lot_cost_basis`
  - `test_shared_cash_rebalance_does_not_sell_same_day_bought_lot`
- TDD red observations:
  - weighted-average entry price was used for partial rebalance sells
  - same-day rebalance could sell a lot bought earlier that same day
- Verification:
  - `uv run pytest tests/test_portfolio_shared.py -q`
  - result: `12 passed`
  - `uv run pytest tests/test_portfolio_shared.py tests/test_portfolio_single_symbol.py tests/test_portfolio_batch.py tests/test_portfolio_io.py tests/test_portfolio_analytics.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
  - result: `83 passed`
- Real read-only DB smoke:
  - `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre backtest-shared examples/rsi2_reversal_with_rebalance.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH --initial-cash 100000 --max-positions 2 --market-profile configs/market_profiles/ashare_daily_default.yaml --output-dir outputs/smoke_shared_phase4_lots`
  - result: output artifacts written under `outputs/smoke_shared_phase4_lots`
- Full verification:
  - `uv run pytest -q`
  - result: `156 passed in 1.30s`
