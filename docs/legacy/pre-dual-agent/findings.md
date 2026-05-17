# Findings

## 2026-05-17 Status Correction

- `quant-research-engine` is not a git repository, but it has a complete Python package layout under `src/quant_research_engine`, tests under `tests`, examples, configs, docs, and output smoke artifacts.
- QRE full test suite was freshly run:
  - command: `uv run pytest -q`
  - result: `145 passed in 1.27s`
- Fresh read-only DB smoke against `tushare_data` worked for `2026-05-11` to `2026-05-15`:
  - `qre db-smoke`: `loaded_rows=15`, date range `2026-05-11` to `2026-05-15`
  - `qre factor-smoke` for `factors.stock_daily_momentum_close.rsi_2`: `loaded_rows=15`, `non_null_rsi_2=15`
  - `qre eval-config examples/rsi2_reversal_research.yaml`: `research_rows=15`, `event_rows=5`
- `docs/mvp_plan.md` was stale relative to `AGENTS.md` and `进度.md`; it still described early milestones even though portfolio/reporting/report-audit capabilities are already implemented.
- The active project focus should be QRE, not further indicators repair.

## 2026-05-17 QRE Documentation/Code Audit

- Code confirms the two-engine objective in the docs:
  - evaluation engine: expression signal event study and forward returns are implemented, but IC, Rank IC, quantile return, and friction-adjusted screening are not implemented yet.
  - portfolio engine: single-symbol, independent batch, and shared-cash backtests are implemented with A-share costs, slippage, price-limit checks, risk controls, rebalance, reports, manifests, benchmark-relative summary hooks, and report audit.
- Stale doc items found and synchronized:
  - `docs/modules/portfolio_workflow.md` still said rebalance was next; it is implemented.
  - `docs/modules/portfolio_layer.md` still listed rebalance/risk-control improvement as a future next step; the remaining near-term realism work is sellable inventory/lot accounting, real index benchmark wiring, and real status metadata.
  - `docs/modules/evaluation_layer.md` still described IC/Rank IC as a gate before portfolio simulation; portfolio MVP already exists, so IC/Rank IC is now the main remaining large-evaluation gap rather than a portfolio prerequisite.
- Fresh full test verification after the audit:
  - command: `uv run pytest -q`
  - result: `145 passed in 1.14s`

## Upstream Data Systems

- `quant_ts` has no project-local `AGENTS.md`; top-level workspace rules apply.
- `quant_ts` is the market-data loader. Its daily mode uses `sync_manager.py --mode daily`, `DailyHandler`, and `DataAuditor.find_adj_mismatch`.
- System timers are active:
  - `quant-ts-daily.timer`: next trigger `2026-05-17 17:30:00 CST`
  - `indicators-tushare-daily.timer`: next trigger `2026-05-17 17:40:00 CST`
- `indicators_tushare` should be considered repaired and in daily-update mode unless the user explicitly reopens factor repair.

## Indicators Smoke Write

- A small smoke write was performed earlier through `indicators_tushare` repair interfaces for:
  - `002050.SZ`
  - `002051.SZ`
  - `002052.SZ`
- Verification for `2024-01-01` to `2024-06-30` now shows:
  - `002050.SZ`: `117` rows, `117` non-null `macd_6_13_5`, `117` non-null `rsi_12`
  - `002051.SZ`: `117` rows, `117` non-null `macd_6_13_5`, `117` non-null `rsi_12`
  - `002052.SZ`: `107` rows, `107` non-null `macd_6_13_5`, `107` non-null `rsi_12`
- No broad indicators repair was started in this planning pass.

## 2026-05-17 Phase 2 Preflight Implementation

- Added a read-only preflight layer:
  - `src/quant_research_engine/preflight.py`
  - `PreflightRunner`
  - `PreflightRequest`
  - `PreflightReport`
- Added CLI:
  - `qre preflight <strategy.yaml> --start <date> --end <date> --codes ...`
  - optional benchmark checks through `--benchmark-table`, `--benchmark-code`, and `--benchmark-value-column`
  - optional JSON report through `--output-json`
- Checks currently covered:
  - market row availability and latest market date
  - requested symbol coverage
  - factor table and column existence
  - factor non-null coverage ratio
  - market/factor inner join coverage
  - security metadata availability
  - optional benchmark row/non-null availability
- Real read-only smoke used socket authentication:
  - command: `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre preflight examples/rsi2_reversal_research.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH --benchmark-table public.stock_daily --benchmark-code 000002.SZ --benchmark-value-column close`
  - result: `status=ok`
  - `market_rows=15`
  - `latest_market_date=2026-05-15`
  - `factor_rsi_2_coverage_ratio=1.0`
  - `join_coverage_ratio=1.0`
  - `metadata_rows=3`
  - `benchmark_rows=5`
- Verification:
  - targeted: `54 passed in 0.50s`
  - full suite: `147 passed in 1.22s`

## 2026-05-17 Phase 2 Preflight Optimization

- Added strategy universe parsing:
  - `exclude_st`
  - `exclude_suspended`
  - `exclude_risk_warning`
  - `min_listing_days`
  - `min_amount`
- Added preflight universe diagnostics:
  - total loaded universe symbols
  - eligible symbols
  - excluded symbols by reason: `new_listing`, `st`, `risk_warning`, `suspended`, `low_amount`
- `qre preflight` now prints universe diagnostics and still returns success for warnings unless a hard error is found.
- Real read-only smoke:
  - `status=ok`
  - `universe_total_symbols=3`
  - `universe_eligible_symbols=3`
  - all universe exclusion counts were `0`
- Verification:
  - related suite: `59 passed in 0.52s`
  - full suite: `148 passed in 1.18s`

## 2026-05-17 Phase 3 Evaluation Metrics

- Added `EvaluationRequest.factor_columns` and `EvaluationRequest.quantiles`.
- Added `EvaluationResult.ic_summary` and `EvaluationResult.quantile_summary`.
- IC / Rank IC semantics:
  - compute forward returns first by `ts_code`
  - for each `trade_date`, correlate current factor values with future returns cross-sectionally
  - Rank IC uses pandas ranks, avoiding an extra scipy dependency
  - dates with fewer than two valid pairs are skipped
- Quantile return semantics:
  - assign quantiles per `trade_date`
  - aggregate forward returns by factor, horizon, and quantile
  - if cross-section is smaller than configured quantiles or factor values are not sufficiently distinct, output zero-count quantile rows
- CLI:
  - `eval-smoke` passes the single logical factor into IC calculation
  - `eval-config` passes YAML factor fields and `evaluation.quantiles`
  - output now includes `ic_summary` and `quantile_summary` sections when available
- Real read-only smoke:
  - command: `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre eval-config examples/rsi2_reversal_research.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH`
  - `research_rows=15`
  - `event_rows=5`
  - `rsi_2` horizon 1 `mean_ic=-0.30337898885384407`, `mean_rank_ic=-0.25`
  - quantile rows were emitted with zero counts because the smoke used only 3 symbols with 5 configured quantiles
- Verification:
  - related suite: `51 passed in 0.50s`
  - full suite: `151 passed in 1.28s`

## 2026-05-17 Phase 3 Friction-Adjusted Screening

- Added rough friction adjustment to event summary:
  - `EvaluationRequest.round_trip_cost_rate`
  - per-event `adjusted_forward_return_<horizon>`
  - summary columns: `round_trip_cost_rate`, `mean_adjusted_forward_return`, `median_adjusted_forward_return`, `adjusted_win_rate`
- CLI support:
  - `--round-trip-cost-rate`
  - `--market-profile <yaml>` for rough automatic rate estimation
- Market profile estimate semantics:
  - buy side: commission rate + transfer fee rate + buy slippage rate
  - sell side: commission rate + transfer fee rate + stamp tax + sell slippage rate
  - minimum commission is intentionally ignored because large evaluation does not know per-trade notional
- Real read-only smoke:
  - command: `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre eval-config examples/rsi2_reversal_research.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH --market-profile configs/market_profiles/ashare_daily_default.yaml`
  - estimated `round_trip_cost_rate=0.00212`
  - horizon 1 `mean_forward_return=-0.008199842669621838`
  - horizon 1 `mean_adjusted_forward_return=-0.010319842669621836`
- Verification:
  - related suite: `55 passed in 0.55s`
  - full suite: `154 passed in 1.33s`

## 2026-05-17 Phase 4 Shared-Cash Lot Accounting

- Added lot-level accounting inside shared-cash positions:
  - each buy/rebalance buy appends a lot
  - lots track quantity, entry price, entry date, entry cost, and entry bar index
  - position aggregate fields remain for compatibility
- Rebalance and exit sells now consume lots FIFO for realized PnL.
- Sellable inventory now uses T+1 daily semantics:
  - only lots with `entry_bar_index < current_bar_index` can be sold
  - same-day rebalance cannot sell a just-bought lot
- TDD red tests:
  - partial rebalance sell used weighted-average cost basis instead of FIFO
  - same-day rebalance sold a lot bought earlier the same day
- Real read-only DB smoke:
  - command: `QRE_MARKET_DB_URL='postgresql+psycopg:///tushare_data' uv run qre backtest-shared examples/rsi2_reversal_with_rebalance.yaml --start 2026-05-11 --end 2026-05-15 --codes 000001.SZ 000002.SZ 600000.SH --initial-cash 100000 --max-positions 2 --market-profile configs/market_profiles/ashare_daily_default.yaml --output-dir outputs/smoke_shared_phase4_lots`
  - result wrote orders/trades/equity/report artifacts under `outputs/smoke_shared_phase4_lots`
- Verification:
  - shared-cash tests: `12 passed in 0.30s`
  - portfolio/CLI related suite: `83 passed in 1.11s`
  - full suite: `156 passed in 1.30s`
