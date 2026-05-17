# Evaluation Layer

## Purpose

The evaluation layer is the first version of the large screening engine.

It is designed to quickly answer:

- How many signal events does a factor expression produce?
- What are the forward returns after the signal?
- Does a candidate signal look promising before detailed account-level simulation?

This layer is intentionally lighter than the future portfolio engine.

Evaluation assumes all factor columns already exist in the input research frame. It must not compute technical indicators internally.

## Current Scope

Implemented:

- Safe expression signal evaluation for simple comparisons and boolean `and`/`or`.
- Forward return calculation by `ts_code`.
- Event table generation.
- Summary table generation.
- IC and Rank IC summary by factor and horizon.
- Quantile return summary by factor, horizon, and quantile when enough cross-sectional observations exist.
- Rough friction-adjusted event summary:
  - explicit `round_trip_cost_rate`
  - or estimated from a market profile's commission, tax, transfer fee, and percent slippage
- CLI smoke command that connects:
  - daily market bars
  - factor history
  - expression signal
  - forward returns
  - IC / Rank IC
  - quantile return
- Config-driven smoke command from YAML strategy specs.

Not implemented yet:

- Regime split.
- Industry/board/market-cap grouping.
- Benchmark comparison.
- Portfolio/account-level simulation.

## Current Files

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/signals.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/strategies/spec.py`
- `src/quant_research_engine/data/assembler.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_evaluation_signals.py`
- `tests/test_evaluation_forward_returns.py`

## Supported Signal Expressions

Examples:

- `rsi_2 < 10`
- `close > sma_20`
- `rsi_2 < 10 and close > sma_20`

The expression evaluator intentionally rejects:

- function calls
- attribute access
- imports
- unknown columns

This keeps early signal evaluation simple and avoids unsafe Python evaluation.

## Smoke Command

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre eval-smoke \
  --start 2026-01-05 \
  --end 2026-01-30 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --logical-name rsi_2 \
  --target factors.stock_daily_momentum_close.rsi_2 \
  --signal 'rsi_2 < 10' \
  --horizons 1 3 5
```

## Verified On 2026-05-11

Result:

- `research_rows=60`
- `event_rows=12`

Summary:

| horizon | event_count | mean_forward_return | median_forward_return | win_rate |
|---:|---:|---:|---:|---:|
| 1 | 12 | -0.002805233615359124 | -0.0066865115332385705 | 0.25 |
| 3 | 12 | -0.018730055594545564 | -0.013455685540025575 | 0.08333333333333333 |
| 5 | 12 | -0.02662007904368931 | -0.035006077389604484 | 0.08333333333333333 |

These numbers are only a small-window smoke result and should not be interpreted as a strategy conclusion.

Config-driven smoke from `examples/rsi2_reversal_research.yaml`:

- `research_rows=60`
- `event_rows=18`
- horizon 1: event_count `18`, mean `-0.0029337036247699183`, win_rate `0.2777777777777778`
- horizon 3: event_count `16`, mean `-0.01686409110930514`, win_rate `0.0625`
- horizon 5: event_count `12`, mean `-0.02662007904368931`, win_rate `0.08333333333333333`
- horizon 10: event_count `7`, mean `-0.051371192673058105`, win_rate `0.14285714285714285`
- horizon 20: event_count `0`

## Verified On 2026-05-17

Config-driven smoke against `2026-05-11` to `2026-05-15`:

- `research_rows=15`
- `event_rows=5`
- IC summary generated for `rsi_2`.
- `horizon=1`: `mean_ic=-0.30337898885384407`, `mean_rank_ic=-0.25`
- `horizon=3`: `mean_ic=-0.9094508298560615`, `mean_rank_ic=-0.5`
- Quantile summary emitted but had zero rows per quantile in the 3-symbol smoke because the configured quantile count is 5 and the cross-section is too small.
- Rough friction-adjusted smoke with `configs/market_profiles/ashare_daily_default.yaml` estimated `round_trip_cost_rate=0.00212`.
- Horizon 1 mean adjusted forward return: `-0.010319842669621836`.
- Full verification: `154 passed in 1.33s`.

## Next Step

Large evaluation MVP is complete for the current project stage. The next engine work should move to portfolio realism unless evaluation grouping/regime analysis is explicitly prioritized.

Portfolio simulation already has an advanced MVP in the portfolio layer, so this is no longer a gate before any portfolio work. It is the main remaining gap in the large screening engine.
