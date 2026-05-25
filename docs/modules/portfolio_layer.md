# Portfolio Layer

## Purpose

The portfolio layer is the detailed validation engine.

It should eventually simulate:

- orders
- fills
- transaction costs
- slippage
- failed order reasons
- cash
- positions
- sellable inventory
- daily equity curve
- trades
- portfolio risk metrics

The first implementation is deliberately narrow: single-symbol daily long-only backtest.

## Current Scope

Implemented:

- Single-symbol long-only backtest.
- Independent multi-symbol batch backtest.
- Shared-cash multi-symbol portfolio backtest MVP.
- Expression entry signal.
- Signal on `t`, buy on `t+1` open.
- Fixed holding period exit.
- Full-cash buy sizing with A-share lot rounding.
- A-share commission, stamp tax, and transfer fee through market profile.
- Orders table.
- Trades table.
- Daily equity curve.
- Summary metrics.
- Output persistence for orders, trades, equity curve, and summary.
- Batch output persistence for per-symbol files and a batch `summary.csv`.
- Batch cross-sectional aggregate metrics in `summary_metrics.json`.
- Grouped batch analytics, initially for static columns such as `board`.
- Shared-cash output persistence for orders, trades, failed orders, equity curve, and summary.
- Shared-cash target weight models:
  - equal_weight
  - score_weight
  - inverse_volatility
- Shared-cash risk-control exits:
  - stop_loss
  - take_profit
  - trailing_stop
- Shared-cash fixed-interval rebalance for existing positions.
- Strategy YAML / CLI rebalance interval configuration.
- Shared-cash rebalance summary metrics:
  - `rebalance_order_count`
  - `rebalance_notional`
  - `rebalance_cost`
  - `rebalance_turnover`
- Shared-cash failed rebalance diagnostics:
  - `failed_rebalance_order_count`
  - `failed_rebalance_notional`
- Shared-cash rebalance sell realized-PnL trade rows:
  - `exit_reason=rebalance`
- Shared-cash lot-level accounting:
  - FIFO cost basis for overlapping entry/rebalance lots
  - T+1 sellable inventory checks for rebalance and exit sells
- Shared-cash portfolio risk metrics:
  - annualized_return
  - annualized_volatility
  - sharpe
  - max_drawdown
  - max_drawdown_peak_date
  - max_drawdown_trough_date
  - max_drawdown_recovery_date
  - max_drawdown_duration_days
  - return_drawdown_ratio
  - rolling fixed-size equity-curve metrics
- Report manifests for batch and shared-cash outputs.
- Report manifest discovery and audit CLI:
  - `qre report-files`
  - `qre report-audit`
  - `qre report-audit --require-match`
  - `qre report-files --window-size <int>`
  - `qre report-audit --window-size <int>`
- Shared-cash rolling risk output:
  - `rolling_metrics_20.csv`
- Batch rolling cross-sectional risk output:
  - `rolling_summary_20.csv`
  - `rolling_summary_20_by_<group>.csv`
  - `rolling_summary_20_by_<group>_ranked_symbols.csv`
- Failed order output.
- Percent slippage from market profile.
- Basic order blocking when optional input columns indicate:
  - `is_suspended`
  - `limit_up`
  - `limit_down`
- Automatic `limit_up` / `limit_down` inference from `pre_close`, execution price, and A-share board profile when those columns are absent.
- Sell retry after a blocked sell order.
- Optional `--run-id` on durable output commands:
  - `qre preflight --output-json`, `qre eval-config --output-dir`, `qre backtest-single --output-dir`, `qre backtest-batch --output-dir`, `qre backtest-shared --output-dir`
  - Persisted as `"run_id"` in preflight JSON, evaluation `run_manifest.json`, and portfolio `run_manifest.json`
  - Stored as `null` when omitted; linkage metadata only (not transactional)
- Run-manifest content validation through `qre report-audit --role run_manifest`:
  - Validated fields: `schema_version` (integer 1), `kind` (string), `run_id` (string or null), `command` (string), `strategy_path` (string), `artifacts` (list of strings)
  - Supported kinds: `evaluation_run_manifest`, `portfolio_backtest_run_manifest`
  - Structured issues for missing/invalid fields with codes `missing_run_manifest_field` and `invalid_run_manifest_field`
  - Only `run_id` accepts `null`; all other validated fields reject present-null
- Batch metadata group-by passthrough:
  - `qre backtest-batch --group-by <cols>` passes metadata columns through to batch summaries
  - Grouped outputs such as `group_by_board.csv` are written when `--group-by` is used
  - Report-manifest role `group_summary` with metadata `group_by=<col>`
- Shared-cash metadata output passthrough:
  - `qre backtest-shared --metadata-columns <cols>` appends requested static metadata to order, trade, and failed-order output rows
  - Collision guards prevent metadata columns from overwriting canonical fields
- Shared-cash metadata group summaries:
  - `qre backtest-shared --group-by <cols>` writes per-group row summaries
  - Artifacts: `orders_by_<col>.csv`, `trades_by_<col>.csv`, `failed_orders_by_<col>.csv`
  - Report roles: `shared_orders_group_summary`, `shared_trades_group_summary`, `shared_failed_orders_group_summary`
  - Empty no-column outputs are handled without error
- Evaluation metadata group summaries:
  - `qre eval-config --group-by <cols>` writes `group_summary.csv`
  - Report role: `evaluation_group_summary`
  - Grouping works on available research-frame metadata columns

Grouped outputs support segmentation and structural inspection only. They do not provide exposure attribution, per-group portfolio return attribution, or proof of strategy quality.

Not implemented yet:

- Benchmark membership grouping metadata.
- Industry classification normalization for cross-sectional grouping.
- Real regime grouping metadata.

## Current Files

- `src/quant_research_engine/portfolio/single_symbol.py`
- `src/quant_research_engine/portfolio/batch.py`
- `src/quant_research_engine/portfolio/shared.py`
- `src/quant_research_engine/portfolio/analytics.py`
- `src/quant_research_engine/portfolio/benchmark.py`
- `src/quant_research_engine/portfolio/risk.py`
- `src/quant_research_engine/portfolio/risk_controls.py`
- `src/quant_research_engine/portfolio/weights.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_portfolio_single_symbol.py`
- `tests/test_portfolio_batch.py`
- `tests/test_portfolio_shared.py`
- `tests/test_portfolio_analytics.py`
- `tests/test_portfolio_benchmark.py`
- `tests/test_portfolio_risk.py`
- `tests/test_portfolio_risk_controls.py`
- `tests/test_portfolio_weights.py`
- `tests/test_portfolio_io.py`
- `src/quant_research_engine/apps/cli.py`

## CLI Smoke

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-single \
  strategies/low_level/rsi2_reversal_research.yaml \
  --symbol 000001.SZ \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --initial-cash 100000 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --output-dir outputs/smoke_000001_rsi2_with_slippage
```

Batch smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-batch \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --initial-cash 100000 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --group-by board \
  --output-dir outputs/smoke_batch_rsi2_with_slippage
```

Shared-cash smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-shared \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ 688001.SH \
  --initial-cash 100000 \
  --max-positions 3 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --output-dir outputs/smoke_shared_rsi2
```

Report audit smoke:

```bash
uv run qre report-audit \
  outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M
```

Shared-cash score-weight smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-shared \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ 688001.SH \
  --initial-cash 100000 \
  --max-positions 3 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --weight-model score_weight \
  --score-column rsi_2 \
  --stop-loss-pct 0.08 \
  --take-profit-pct 0.12 \
  --trailing-stop-pct 0.10 \
  --output-dir outputs/smoke_shared_rsi2_score_weight
```

Shared-cash YAML risk smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-shared \
  strategies/low_level/rsi2_reversal_with_risk.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ 688001.SH \
  --initial-cash 100000 \
  --max-positions 3 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --weight-model score_weight \
  --score-column rsi_2 \
  --output-dir outputs/smoke_shared_rsi2_yaml_risk
```

Shared-cash YAML risk and weight smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-shared \
  strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ 688001.SH \
  --initial-cash 100000 \
  --max-positions 3 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --output-dir outputs/smoke_shared_rsi2_yaml_risk_weight
```

## Verified On 2026-05-11

No-slippage result using the in-code default profile:

- strategy: `rsi2_reversal_research_mvp`
- symbol: `000001.SZ`
- orders: `10`
- trades: `5`
- initial_cash: `100000.0`
- final_equity: `99088.60131999999`
- total_return: `-0.009113986800000085`
- trade_count: `5`
- win_rate: `0.4`
- total_cost: `539.39868`

With YAML profile slippage (`buy_rate=0.0005`, `sell_rate=0.0005`), the same smoke produced:

- orders: `10`
- trades: `5`
- final_equity: `98579.33581894005`
- total_return: `-0.014206641810599496`
- trade_count: `5`
- win_rate: `0.4`
- total_cost: `538.0581810599999`

Output files:

- `outputs/smoke_000001_rsi2_no_slippage/orders.csv`
- `outputs/smoke_000001_rsi2_no_slippage/trades.csv`
- `outputs/smoke_000001_rsi2_no_slippage/failed_orders.csv`
- `outputs/smoke_000001_rsi2_no_slippage/equity_curve.csv`
- `outputs/smoke_000001_rsi2_no_slippage/summary.json`
- `outputs/smoke_000001_rsi2_with_slippage/orders.csv`
- `outputs/smoke_000001_rsi2_with_slippage/trades.csv`
- `outputs/smoke_000001_rsi2_with_slippage/failed_orders.csv`
- `outputs/smoke_000001_rsi2_with_slippage/equity_curve.csv`
- `outputs/smoke_000001_rsi2_with_slippage/summary.json`

Batch output files:

- `outputs/smoke_batch_rsi2_with_slippage/summary.csv`
- `outputs/smoke_batch_rsi2_with_slippage/summary_metrics.json`
- `outputs/smoke_batch_rsi2_with_slippage/group_by_board.csv`
- `outputs/smoke_batch_rsi2_with_slippage/<symbol>/orders.csv`
- `outputs/smoke_batch_rsi2_with_slippage/<symbol>/trades.csv`
- `outputs/smoke_batch_rsi2_with_slippage/<symbol>/failed_orders.csv`
- `outputs/smoke_batch_rsi2_with_slippage/<symbol>/equity_curve.csv`
- `outputs/smoke_batch_rsi2_with_slippage/<symbol>/summary.json`

Batch smoke result with YAML profile slippage:

- `000001.SZ`: final_equity `98579.33581894005`, total_return `-0.014206641810599496`, trades `5`, win_rate `0.4`
- `000002.SZ`: final_equity `94411.88596898004`, total_return `-0.05588114031019953`, trades `3`, win_rate `0.6666666666666666`
- `600000.SH`: final_equity `89842.25464364502`, total_return `-0.10157745356354975`, trades `5`, win_rate `0.4`

Batch aggregate metrics:

- symbol_count: `3`
- traded_symbol_count: `3`
- positive_return_symbol_rate: `0.0`
- mean_total_return: `-0.05722174522811626`
- median_total_return: `-0.05588114031019953`
- return_std: `0.043700830687205754`
- total_trades: `13`
- total_failed_orders: `0`

Grouped batch analytics:

- `qre backtest-batch --group-by board` prints and writes grouped metrics.
- `BatchBacktestEngine` copies available static metadata columns into per-symbol summary:
  - `board`
  - `industry`
  - `benchmark`
  - `is_st`
  - `is_risk_warning`
- Verified 5-symbol grouped smoke output:
  - output directory: `outputs/smoke_batch_rsi2_group_by_board`
  - group file: `group_by_board.csv`
  - boards covered: `chinext`, `main_board`, `star_market`

Shared-cash portfolio smoke:

- output directory: `outputs/smoke_shared_rsi2_equal_weight`
- symbols: `5`
- max_positions: `3`
- orders: `28`
- trades: `14`
- final_equity: `93166.01775322505`
- total_return: `-0.0683398224677495`
- win_rate: `0.35714285714285715`
- total_cost: `490.03574677500006`
- annualized_return: `-0.27699116568514104`
- annualized_volatility: `0.19366123197795493`
- sharpe: `-1.5794772387765874`
- max_drawdown: `-0.09735449004468788`
- return_drawdown_ratio: `-0.7019688813159003`

Shared-cash score-weight smoke:

- output directory: `outputs/smoke_shared_rsi2_score_weight`
- score_column: `rsi_2`
- final_equity: `97892.74973376007`
- total_return: `-0.02107250266239935`
- annualized_return: `-0.09297219712855143`
- annualized_volatility: `0.21920089902674925`
- sharpe: `-0.338471095755269`
- max_drawdown: `-0.09156033586432988`
- return_drawdown_ratio: `-0.2301488134952199`

Shared-cash score-weight smoke with stop loss / take profit:

- output directory: `outputs/smoke_shared_rsi2_score_weight_risk_controls`
- stop_loss_pct: `0.08`
- take_profit_pct: `0.12`
- final_equity: `98288.98745537398`
- total_return: `-0.017110125446260227`
- annualized_return: `-0.07602837061454637`
- sharpe: `-0.28473199214765416`
- max_drawdown: `-0.06623312165616868`
- exit_reason counts:
  - `holding_period`: `13`
  - `stop_loss`: `2`
  - `take_profit`: `1`

Shared-cash score-weight smoke with stop loss / take profit / trailing stop:

- output directory: `outputs/smoke_shared_rsi2_score_weight_trailing_stop`
- stop_loss_pct: `0.08`
- take_profit_pct: `0.12`
- trailing_stop_pct: `0.10`
- final_equity: `95464.11996512687`
- total_return: `-0.0453588003487313`
- annualized_return: `-0.19159062779347302`
- sharpe: `-1.1217147540454728`
- max_drawdown: `-0.09151959754067462`
- exit_reason counts:
  - `holding_period`: `13`
  - `stop_loss`: `2`
  - `trailing_stop`: `1`

Shared-cash YAML risk smoke:

- strategy file: `strategies/low_level/rsi2_reversal_with_risk.yaml`
- YAML fields:
  - `risk.stop_loss_pct=0.08`
  - `risk.take_profit_pct=0.12`
  - `risk.trailing_stop_pct=0.10`
- CLI/YAML priority:
  - explicit CLI risk flags override YAML
  - absent CLI risk flags use YAML
  - absent YAML values remain `None`
- output directory: `outputs/smoke_shared_rsi2_yaml_risk`
- final_equity: `95464.11996512687`
- total_return: `-0.0453588003487313`
- max_drawdown: `-0.09151959754067462`
- exit_reason counts:
  - `holding_period`: `13`
  - `stop_loss`: `2`
  - `trailing_stop`: `1`

Shared-cash YAML risk and weight smoke:

- strategy file: `strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml`
- YAML fields:
  - `risk.stop_loss_pct=0.08`
  - `risk.take_profit_pct=0.12`
  - `risk.trailing_stop_pct=0.10`
  - `portfolio.weight_model=score_weight`
  - `portfolio.score_column=rsi_2`
- CLI/YAML priority:
  - explicit CLI weight flags override YAML
  - absent CLI weight flags use YAML
  - absent YAML weight model falls back to shared-cash default `equal_weight`
- output directory: `outputs/smoke_shared_rsi2_yaml_risk_weight`
- final_equity: `95464.11996512687`
- total_return: `-0.0453588003487313`
- max_drawdown: `-0.09151959754067462`
- exit_reason counts:
  - `holding_period`: `13`
  - `stop_loss`: `2`
  - `trailing_stop`: `1`

This is a smoke result only. It is not a conclusion about RSI(2) effectiveness.

Shared-cash YAML risk, weight, and rebalance smoke:

- strategy file: `strategies/low_level/rsi2_reversal_with_rebalance.yaml`
- YAML fields:
  - `risk.stop_loss_pct=0.08`
  - `risk.take_profit_pct=0.12`
  - `risk.trailing_stop_pct=0.10`
  - `portfolio.weight_model=score_weight`
  - `portfolio.score_column=rsi_2`
  - `portfolio.rebalance_interval_days=5`
- output directory: `outputs/smoke_shared_rsi2_yaml_rebalance`
- final_equity: `91948.09570266725`
- total_return: `-0.08051904297332746`
- trades: `23`
- trade_count: `23`
- win_rate: `0.30434782608695654`
- total_cost: `692.2641297028`
- annualized_return: `-0.3192941867288124`
- sharpe: `-2.4956978974558`
- max_drawdown: `-0.10598694839752243`
- rebalance_order_count: `11`
- rebalance_notional: `176089.058025`
- rebalance_cost: `116.64872180729999`
- rebalance_turnover: `1.802646944210471`
- failed_rebalance_order_count: `0`
- failed_rebalance_notional: `0.0`
- order reason counts:
  - `none`: `32`
  - `rebalance`: `11`
- exit_reason counts:
  - `holding_period`: `13`
  - `rebalance`: `7`
  - `stop_loss`: `2`
  - `trailing_stop`: `1`

This is a smoke result only. It is not a conclusion about RSI(2) effectiveness.

## Next Step

Next coding target options:

- wire real index benchmark tables once benchmark/index data is available
- run `qre benchmark-smoke` before interpreting index-relative metrics

Future execution realism:

- connect real suspension metadata when available
- derive ST/risk-warning state from metadata instead of requiring frame input
- add industry classification normalization, benchmark membership, and market regime metadata sources
- replace temporary stock benchmark with real index benchmark once benchmark data is available

## Report-Manifest Audit

Portfolio outputs include a `report_manifest.json` that is discoverable and auditable through `qre report-files` and `qre report-audit`. The report-manifest contract (kinds, roles, filtering, content validation, and exit codes) is documented in `docs/modules/portfolio_workflow.md`.

For `qre research-run`, the top-level `report_manifest.json` (kind=`research_run_report_manifest`) serves as a single audit entry point for the entire run. Role-specific commands (`run_manifest`, `preflight_report`, `eval_report_manifest`, `backtest_report_manifest`) are documented in `docs/modules/portfolio_workflow.md` and in the README research-run section.
