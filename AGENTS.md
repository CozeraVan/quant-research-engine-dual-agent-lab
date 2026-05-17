# Quant Research Engine Agent Notes

## Project Objective

Build a reusable, modular, realistic research and backtesting framework.

The framework should support multiple markets and time granularities over time. The first concrete implementation is A-share daily technical-factor research and backtesting.

## Core Product Idea

The system has two engines:

1. **Large evaluation engine**
   - Full-market batch evaluation.
   - Fast screening of factors, factor combinations, and strategy families.
   - Roughly accounts for trading friction.
   - Produces cross-sectional, time-window, regime, industry, board, and benchmark comparisons.

2. **Detailed portfolio engine**
   - Account-level realistic backtesting.
   - Simulates orders, fills, holdings, sellable inventory, cash, fees, slippage, and equity curve.
   - Applies market-specific rules such as A-share T+1, price limits, suspensions, and lot size.
   - Used after the large engine identifies promising candidates.

## Important Design Constraints

- Do not make the core engine A-share-only.
- Do not make the core engine daily-only.
- Do not hardcode transaction costs or market rules into strategy logic.
- Keep market rules in market profiles or plugins.
- Keep data producers separate from research and backtesting.
- Keep signal generation, execution simulation, portfolio accounting, and analytics separate.
- Every broad run should start with a small smoke test.
- Avoid future leakage by default:
  - signals form on `t`
  - first default execution is no earlier than `t+1`
  - factor joins must be checked before interpreting results

## First Implementation Scope

The first milestone should remain focused:

- Market: A-share.
- Frequency: daily bars.
- Direction: long-only first.
- Data source: local PostgreSQL database `tushare_data`.
- Market table: `public.stock_daily`.
- Factor schema: `factors`.
- First output family:
  - factor event study
  - IC / Rank IC
  - quantile return
  - rough friction-adjusted factor/strategy evaluation
  - account-level simple portfolio backtest
  - CSV and Markdown reports

## Future Expansion Targets

Design interfaces so these can be added later:

- funds
- forex
- crypto
- futures
- options
- minute bars
- tick data
- millisecond-level event simulation
- stop loss, take profit, trailing stop
- margin and leverage
- contract multiplier and expiry
- funding fee and overnight interest
- order book matching and latency models

## Current Reference Material

Read these before implementation:

- `/home/van/quant-workspace/research-notes/current_status.md`
- `/home/van/quant-workspace/research-notes/handoff.md`
- `/home/van/quant-workspace/research-notes/roadmap.md`
- `/home/van/quant-workspace/research-notes/strategy_research_architecture.md`
- `/home/van/quant-workspace/research-notes/daily_strategy_catalog.md`
- `/home/van/quant-workspace/research-notes/strategy_indicator_requirement_matrix.md`
- `/home/van/quant-workspace/strategy-research/current_status.md`
- `/home/van/quant-workspace/strategy-research/handoff.md`
- `/home/van/quant-workspace/strategy-research/docs/architecture.md`
- `/home/van/quant-workspace/strategy-research/docs/database_requirements.md`

## Development Rule

Before coding each milestone, write or update the relevant design/plan document. Keep `进度.md` current at the end of each work session.

## Current Breakpoint: 2026-05-12 Early Morning

The engine currently has:

- PostgreSQL data access for daily bars, database-stored factors, and fallback security metadata.
- A-share daily market profile with costs, lot sizing, price-limit checks, and percent slippage.
- Expression-based evaluation and forward-return event study.
- Single-symbol portfolio backtest.
- Independent batch single-symbol backtest with grouped summary analytics.
- Shared-cash multi-symbol portfolio backtest.
- Shared-cash target weighting: `equal_weight`, `score_weight`, `inverse_volatility`.
- Portfolio risk metrics from equity curves.
- Shared-cash stop-loss / take-profit / trailing-stop exits with `exit_reason` recorded in trades.
- Strategy YAML risk controls under `risk`.
- Strategy YAML shared-cash weighting controls under `portfolio`.

Latest verified command:

```bash
uv run pytest -q
```

Latest verified result:

- `145 passed`

Latest real database smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-shared \
  examples/rsi2_reversal_with_rebalance.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ 688001.SH \
  --initial-cash 100000 \
  --max-positions 3 \
  --market-profile configs/market_profiles/ashare_daily_default.yaml \
  --output-dir outputs/smoke_shared_rsi2_yaml_rebalance
```

Latest smoke result:

- final_equity: `91948.09570266725`
- total_return: `-0.08051904297332746`
- max_drawdown: `-0.10598694839752243`
- trades: `23`
- trade_count: `23`
- win_rate: `0.30434782608695654`
- total_cost: `692.2641297028`
- rebalance_order_count: `11`
- rebalance_notional: `176089.058025`
- rebalance_cost: `116.64872180729999`
- rebalance_turnover: `1.802646944210471`
- failed_rebalance_order_count: `0`
- failed_rebalance_notional: `0.0`
- order reason counts:
  - `none=32`
  - `rebalance=11`
- exit_reason counts:
  - `holding_period=13`
  - `rebalance=7`
  - `stop_loss=2`
  - `trailing_stop=1`

## Current Breakpoint: Benchmark-Relative Analytics Interface Implemented

Before changing runtime code for this milestone, keep these docs synchronized:

- `AGENTS.md`
- `docs/modules/portfolio_agent.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_layer.md`
- `进度.md`

Implemented target:

- Optional shared-cash rebalance mechanism.
- Default behavior remains unchanged unless rebalance is explicitly enabled.
- First scope is long-only daily A-share shared cash.
- Rebalance uses current-day known prices only and does not look ahead.
- Order validation, lot sizing, cost, slippage, and price-limit blocking stay inside market profile logic.
- Rebalance orders are recorded with `reason=rebalance`.
- Summary includes `rebalance_order_count`, `rebalance_notional`, `rebalance_cost`, and `rebalance_turnover`.
- Summary includes `failed_rebalance_order_count` and `failed_rebalance_notional`.
- Rebalance sells now generate realized-PnL trade rows with `exit_reason=rebalance`.
- Partial rebalance sells allocate entry cost by sold quantity and preserve remaining position cost basis.
- Portfolio benchmark-relative analytics interface exists in `portfolio/benchmark.py`.
- Benchmark analytics is currently data-source agnostic:
  - input portfolio equity curve
  - input benchmark value frame
  - align by `trade_date`
  - compute total excess return, tracking error, information ratio, beta, alpha, and capture ratios
- Data layer benchmark/index loading skeleton exists:
  - `PostgresDataStore.load_benchmark_bars(...)`
  - configurable table name
  - configurable value fields
- CLI benchmark data smoke exists:
  - `qre benchmark-smoke`
  - reports loaded rows, date range, non-null benchmark value count, and return observation count
- `backtest-shared` benchmark-relative summary is wired:
  - can use `public.stock_daily` and another stock as temporary benchmark
  - supports `--benchmark-table`, `--benchmark-code`, and `--benchmark-value-column`
- Shared-cash output writes `summary.md` with Portfolio, Rebalance, and Benchmark sections.
- Markdown summary uses display labels while `summary.json` keeps stable machine-readable keys.
- `backtest-shared --print-summary-md` prints the same human-readable Markdown summary to stdout.
- Batch backtest output writes `summary.md` with aggregate metrics and top-level output file references.
- `backtest-batch --print-summary-md` prints the same human-readable Markdown summary to stdout.
- Batch Markdown keeps `summary.csv` and `summary_metrics.json` as machine-readable sources of truth.
- Batch group-by reports are listed in Markdown when `group_by` is used.
- Batch Markdown includes Top Symbols and Bottom Symbols sections sorted by `total_return`.
- Batch group-by output includes `group_by_<column>_ranked_symbols.csv` with each group's top and bottom symbol.
- Batch group ranked-symbol depth is configurable through `--group-rank-top-n`.
- Risk layer includes reusable windowed equity-curve analytics for month, quarter, and year windows.
- Shared-cash output writes window metrics to `window_metrics_M.csv`, `window_metrics_Q.csv`, and `window_metrics_Y.csv`.
- Shared-cash `summary.md` includes an Output Files section listing core CSV/JSON/Markdown outputs.
- Batch output writes cross-sectional window summaries to `window_summary_M.csv`, `window_summary_Q.csv`, and `window_summary_Y.csv`.
- Batch output writes grouped cross-sectional window summaries such as `window_summary_M_by_board.csv`, `window_summary_Q_by_board.csv`, and `window_summary_Y_by_board.csv` when `group_by` is provided.
- Batch output writes grouped window ranked-symbol reports such as `window_summary_M_by_board_ranked_symbols.csv`, `window_summary_Q_by_board_ranked_symbols.csv`, and `window_summary_Y_by_board_ranked_symbols.csv`.
- Batch output writes `report_manifest.json` so downstream scripts can discover generated artifacts without parsing Markdown.
- Report discovery helper can load `report_manifest.json` and filter files by role, symbol, window, or group.
- `qre report-files` can inspect/filter `report_manifest.json` from shell scripts.
- `qre report-files --check-exists` can validate that matched manifest file paths still exist.
- Shared-cash output writes `report_manifest.json` and can be inspected by `qre report-files`.
- `ReportManifest.validate_contents()` can perform lightweight CSV/JSON structure validation.
- `qre report-files --validate-contents` can run lightweight content validation for matched manifest entries.
- `qre report-audit` can summarize report manifest file counts, missing files, validation issues, and audit status.
- Portfolio risk analytics includes max-drawdown peak, trough, recovery, and duration diagnostics.
- Portfolio risk analytics includes reusable rolling equity-curve metrics.
- Shared-cash output writes `rolling_metrics_20.csv` and lists it in Markdown and `report_manifest.json`.
- Batch output writes rolling cross-sectional summary `rolling_summary_20.csv`.
- Batch grouped output writes rolling cross-sectional summaries such as `rolling_summary_20_by_board.csv`.
- Batch grouped output writes rolling ranked-symbol files such as `rolling_summary_20_by_board_ranked_symbols.csv`.
- `qre report-audit --require-match` can fail zero-match smoke checks.

Next target:

- Continue portfolio analytics/reporting improvements.
- Keep real index benchmark table wiring for after index data is available.

## Current Milestone: Strict Report Audit Matching Implemented

Implemented in this coding pass:

- Add `qre report-audit --require-match`.
- Return exit code `2` when filters match zero manifest entries.
- Print `status=failed` and a clear stderr message for zero-match audits.
- Keep default `report-audit` behavior unchanged when `--require-match` is absent.
- Use this for future rolling-report smoke checks.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `145 passed`

Latest strict audit smoke:

```bash
uv run qre report-audit outputs/smoke_batch_rsi2_rolling_audit/report_manifest.json \
  --role rolling_ranked_symbols \
  --group-by board \
  --require-match
```

Result:

- `manifest_kind=batch_backtest_report_manifest`
- `matched_files=1`
- `missing_files=0`
- `validation_issues=0`
- `status=ok`

## Current Milestone: Grouped Rolling Ranked Symbols Implemented

Implemented in this coding pass:

- Add reusable grouped rolling ranked-symbol analytics.
- First supported rolling window: 20 trading observations.
- Write grouped rolling ranked-symbol files such as `rolling_summary_20_by_board_ranked_symbols.csv`.
- Include grouped rolling ranked-symbol files in batch Markdown Output Files and `report_manifest.json`.
- Keep this as analytics/reporting only: no order, fill, cost, signal, or data-source changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `143 passed`

## Current Milestone: Batch Grouped Rolling Risk Summary Implemented

Implemented in this coding pass:

- Add reusable grouped batch rolling summary analytics.
- First supported grouped rolling window: 20 trading observations.
- Write grouped batch files such as `rolling_summary_20_by_board.csv` when `group_by` is provided.
- Include grouped rolling summary files in batch Markdown Output Files and `report_manifest.json`.
- Keep this as analytics/reporting only: no order, fill, cost, signal, or data-source changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `142 passed`

## Current Milestone: Batch Rolling Risk Cross-Sectional Summary Implemented

Implemented in this coding pass:

- Add reusable batch rolling summary analytics.
- First supported rolling window: 20 trading observations.
- Write batch `rolling_summary_20.csv`.
- Include the rolling summary file in batch Markdown Output Files and `report_manifest.json`.
- Keep this as analytics/reporting only: no order, fill, cost, signal, or data-source changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `141 passed`

## Current Milestone: Rolling Equity-Curve Risk Metrics Implemented

Implemented in this coding pass:

- Add reusable trailing fixed-size rolling equity-curve metrics.
- First supported report window: 20 trading observations.
- Write shared-cash `rolling_metrics_20.csv`.
- Include the rolling metrics file in shared-cash Markdown Output Files and `report_manifest.json`.
- Keep this as analytics/reporting only: no order, fill, cost, signal, or data-source changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `140 passed`

## Current Milestone: Max Drawdown Period Diagnostics Implemented

Implemented in this coding pass:

- Extend `summarize_equity_curve(...)` with max-drawdown period metadata:
  - peak date
  - trough date
  - recovery date
  - drawdown duration in calendar days
- Extend windowed equity metrics with the same fields.
- Add readable Markdown labels for the new summary fields.
- Keep this as analytics/reporting only: no order, fill, cost, signal, or data-source changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `138 passed`

## Current Milestone: Report Manifest Audit CLI Implemented

Implemented in this coding pass:

- Add `qre report-audit <manifest>`.
- Reuse existing report manifest loading, filtering, path existence, and content validation logic.
- Output compact key/value summary suitable for shell scripts:
  - `manifest_kind`
  - `matched_files`
  - `missing_files`
  - `validation_issues`
  - `status`
- Respect `--role`, `--symbol`, `--window`, and `--group-by` filters.
- Return `0` when matched files exist and content validation passes.
- Return `2` when files are missing or content validation has issues.
- Keep this milestone offline: no database access and no portfolio simulation behavior changes.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `137 passed`

Latest report audit smoke:

```bash
uv run qre report-audit outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M
```

Result:

- `manifest_kind=shared_cash_backtest_report_manifest`
- `matched_files=1`
- `missing_files=0`
- `validation_issues=0`
- `status=ok`

## Current Milestone: Report Manifest CLI Content Validation Implemented

Implemented in this coding pass:

- Add `qre report-files --validate-contents`.
- Reuse `ReportManifest.validate_contents()` instead of duplicating CSV/JSON parsing in CLI.
- Respect existing `--role`, `--symbol`, `--window`, and `--group-by` filters during validation.
- Print validation issues to stderr and return exit code `2`.
- Preserve existing path/key stdout behavior when validation passes.
- Keep this milestone offline: no database access and no benchmark/index dependency.

Latest verification:

```bash
uv run pytest -q
```

Result:

- `135 passed`

Latest report manifest smoke:

```bash
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M \
  --validate-contents \
  --check-exists
```

Result:

- `outputs/smoke_shared_manifest/window_metrics_M.csv`
