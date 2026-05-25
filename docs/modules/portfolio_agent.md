# Portfolio Agent Notes

## Purpose

This file is the portfolio-module handoff note for interrupted development sessions.

The portfolio layer is responsible for detailed account-level validation after the larger evaluation engine identifies candidate factors or strategies.

## Current Implemented Scope

- Single-symbol long-only backtest.
- Independent multi-symbol batch backtest.
- Shared-cash multi-symbol portfolio backtest.
- A-share cost, slippage, lot sizing, and price-limit checks through market profiles.
- Orders, trades, failed orders, equity curve, and summary output.
- Batch aggregate and grouped analytics.
- Batch Markdown summary report.
- Shared-cash target weights:
  - `equal_weight`
  - `score_weight`
  - `inverse_volatility`
- Shared-cash fixed risk-control exits:
  - `stop_loss`
  - `take_profit`
  - `trailing_stop`
- Shared-cash fixed-interval rebalance for existing positions.
- Order reason tagging:
  - `rebalance`
- Rebalance summary metrics:
  - `rebalance_order_count`
  - `rebalance_notional`
  - `rebalance_cost`
  - `rebalance_turnover`
- Failed rebalance diagnostics:
  - `failed_rebalance_order_count`
  - `failed_rebalance_notional`
- Rebalance sell realized-PnL rows:
  - `exit_reason=rebalance`
- Equity-curve risk metrics:
  - annualized return
  - annualized volatility
  - Sharpe
  - max drawdown
  - max drawdown peak/trough/recovery dates
  - max drawdown duration days
  - return/drawdown ratio
  - rolling fixed-size equity-curve metrics
- Benchmark-relative analytics interface:
  - excess total return
  - tracking error
  - information ratio
  - beta
  - alpha
  - up/down capture

## Current Verified State

Latest full verification:

```bash
uv run pytest -q
```

Result:

- `145 passed`

Latest smoke families:

- `backtest-single`
- `backtest-batch`
- `backtest-batch --group-by board`
- `backtest-shared`
- `backtest-shared --weight-model score_weight --score-column rsi_2`
- `backtest-shared --weight-model score_weight --score-column rsi_2 --stop-loss-pct 0.08 --take-profit-pct 0.12`
- `backtest-shared --weight-model score_weight --score-column rsi_2 --stop-loss-pct 0.08 --take-profit-pct 0.12 --trailing-stop-pct 0.10`
- `backtest-shared strategies/low_level/rsi2_reversal_with_risk.yaml --weight-model score_weight --score-column rsi_2`
- `backtest-shared strategies/low_level/rsi2_reversal_with_risk_and_weight.yaml`
- `backtest-shared strategies/low_level/rsi2_reversal_with_rebalance.yaml`
- `backtest-batch strategies/low_level/rsi2_reversal_research.yaml --group-by board`
- `backtest-batch strategies/low_level/rsi2_reversal_research.yaml --group-by board --print-summary-md`

## Next Milestone

Continue portfolio engine development:

- market-cap and liquidity metadata standardization
- benchmark membership and index grouping adapters

Completed target:

- Add a small reusable risk-control module.
- Add optional fields to `SharedCashBacktestRequest`.
- Apply risk exits before fixed holding-period exits.
- Record `exit_reason` on trades.
- Add trailing stop with no future leakage.
- Track each position's highest favorable price since entry.
- Add `trailing_stop` as a possible `exit_reason`.
- Add YAML fields for `stop_loss_pct`, `take_profit_pct`, and `trailing_stop_pct`.
- Keep CLI flags as overrides or explicit runtime inputs.
- Add YAML fields for `weight_model`, `score_column`, and `volatility_column`.
- Keep CLI weight flags as explicit runtime overrides.
- Add `rebalance_interval_days` to shared-cash request.
- Add strategy YAML field `portfolio.rebalance_interval_days`.
- Add CLI flag `--rebalance-interval-days`.
- Rebalance existing positions toward target weights on fixed trading-day intervals.
- Keep rebalance disabled by default.
- Tag rebalance orders with `reason=rebalance`.
- Add rebalance summary metrics.
- Add realized-PnL trade rows for rebalance sells.
- Preserve remaining cost basis after partial rebalance sells.
- Add failed rebalance diagnostics to summary.
- Add benchmark-relative analytics interface in `portfolio/benchmark.py`.
- Add data-source agnostic benchmark summary tests.
- Add `PostgresDataStore.load_benchmark_bars(...)` skeleton.
- Add data-layer tests for safe configurable benchmark table queries.
- Add `qre benchmark-smoke` CLI skeleton.
- Add CLI tests for benchmark data availability output.
- Add benchmark-relative summary output to `backtest-shared`.
- Verify temporary stock benchmark comparison using `public.stock_daily` and `000002.SZ`.
- Add shared-cash Markdown summary report with Portfolio, Rebalance, and Benchmark sections.
- Add readable display labels to Markdown summary while preserving `summary.json` keys.
- Add `backtest-shared --print-summary-md`.
- Add batch Markdown summary report.
- Keep batch Markdown concise by listing aggregate/group files, not every per-symbol artifact.
- Add `backtest-batch --print-summary-md`.
- Preserve existing batch key/value and CSV stdout for script compatibility.
- Add top/bottom symbol sections to batch Markdown reports.
- Sort top/bottom symbol sections by `total_return`.
- Add per-group top/bottom symbol CSV outputs for batch `group_by` reports.
- List group ranked-symbol outputs in batch Markdown.
- Add `group_rank_top_n` / `--group-rank-top-n` for batch group ranked-symbol reports.
- Add reusable windowed equity-curve performance analytics.
- Write shared-cash monthly window metrics to `window_metrics_M.csv`.
- Write shared-cash quarterly and yearly window metrics to `window_metrics_Q.csv` and `window_metrics_Y.csv`.
- Add shared-cash output file references to `summary.md`.
- Add batch monthly cross-sectional window summary output.
- Extend batch cross-sectional window summary output to M/Q/Y files.
- Add grouped batch cross-sectional window summary output for M/Q/Y files.
- Add grouped batch window ranked-symbol reports for M/Q/Y files.
- Add batch `report_manifest.json`.
- Add report discovery helper for `report_manifest.json`.
- Add `qre report-files` CLI for manifest filtering.
- Add `qre report-files --check-exists`.
- Add shared-cash `report_manifest.json` output.
- Add helper-level manifest content validation.
- Add `qre report-files --validate-contents`.
- Add `qre report-audit`.
- Add max-drawdown period diagnostics to portfolio risk analytics.
- Add rolling equity-curve risk metrics and shared-cash `rolling_metrics_20.csv`.
- Add batch rolling cross-sectional summary `rolling_summary_20.csv`.
- Add grouped batch rolling cross-sectional summaries such as `rolling_summary_20_by_board.csv`.
- Add grouped rolling ranked-symbol outputs such as `rolling_summary_20_by_board_ranked_symbols.csv`.
- Add strict zero-match failure option for report audit smoke checks.

Next target:

- Continue portfolio analytics/reporting improvements.
- Wire real index benchmark tables after index data is available.

Latest completed coding pass:

- Add `qre report-audit --require-match`.
- Zero matched manifest entries should fail only when this flag is present.
- Preserve current report-audit behavior when the flag is absent.
- Use this option for future rolling-report smoke checks.
- Verified with `uv run pytest -q`: `145 passed`.

Previous completed coding pass:

- Add grouped rolling ranked-symbol analytics.
- First grouped output pattern: `rolling_summary_20_by_<group>_ranked_symbols.csv`.
- Include grouped rolling ranked symbols in Markdown Output Files and `report_manifest.json`.
- Keep the change analytics/reporting-only; no simulation behavior changes.
- Verified with `uv run pytest -q`: `143 passed`.

Previous completed coding pass:

- Add reusable grouped batch rolling summary analytics.
- First grouped batch report output: `rolling_summary_20_by_<group>.csv`.
- Include grouped rolling summaries in Markdown Output Files and `report_manifest.json`.
- Keep the change analytics/reporting-only; no simulation behavior changes.
- Verified with `uv run pytest -q`: `142 passed`.

Previous completed coding pass:

- Add reusable batch rolling summary analytics.
- First batch report output: `rolling_summary_20.csv`.
- Include rolling summary in Markdown Output Files and `report_manifest.json`.
- Keep the change analytics/reporting-only; no simulation behavior changes.
- Verified with `uv run pytest -q`: `141 passed`.

Previous completed coding pass:

- Add reusable trailing fixed-size rolling equity-curve metrics.
- First shared-cash report output: `rolling_metrics_20.csv`.
- Include rolling metrics in Markdown Output Files and `report_manifest.json`.
- Keep the change analytics/reporting-only; no simulation behavior changes.
- Verified with `uv run pytest -q`: `140 passed`.

Previous completed coding pass:

- Extend portfolio risk metrics with max-drawdown peak/trough/recovery dates.
- Add max-drawdown duration in calendar days.
- Carry the fields into windowed equity metrics.
- Keep the change analytics/reporting-only; no simulation behavior changes.
- Verified with `uv run pytest -q`: `138 passed`.

Previous completed coding pass:

- Add `qre report-audit <manifest>`.
- Audit can be filtered by role, symbol, window, or group.
- Audit summarizes matched file count, missing file count, validation issue count, and status.
- Audit returns `0` only when the selected report files exist and pass lightweight content validation.
- Verified with `uv run pytest -q`: `137 passed`.

Previous completed coding pass:

- Add `qre report-files --validate-contents`.
- Validate only matched manifest entries when report filters are provided.
- Return `0` with normal path/key output when validation passes.
- Return `2` and write machine-readable-enough issue lines to stderr when validation fails.
- Verified with `uv run pytest -q`: `135 passed`.

## Guardrails

- No future leakage.
- Use current or past bar open/high/low/close only at the current simulation date.
- Do not calculate indicators inside the portfolio engine.
- Keep A-share market constraints in market profile, not strategy logic.
- Keep all new behavior covered by unit tests before implementation.
- Keep current shared-cash behavior unchanged when rebalance interval is absent.
