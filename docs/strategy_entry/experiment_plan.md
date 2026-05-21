# Experiment Plan

The experiment plan describes how to run the strategy: when, over what universe, with what capital, costs, and execution rules.

## Required Fields

### `experiment`

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Unique run identifier. Example: `rsi2_oversold_reversal_smoke` |
| `frequency` | string | Yes | Bar frequency. Currently only `daily` is supported. |
| `market` | string | Yes | Market identifier. `ashare` for A-share stocks. |
| `start` | date | Yes | Backtest start date (YYYY-MM-DD). |
| `end` | date | Yes | Backtest end date (YYYY-MM-DD). |

### `universe`

| Field | Type | Required | Description |
|---|---|---|---|
| `include` | string | Yes | Universe scope. `all_a` for all A-share stocks. |
| `exclude_st` | boolean | No | Exclude ST (special treatment) stocks. Default `true`. |
| `exclude_suspended` | boolean | No | Exclude suspended stocks when data is available. Default `true`. |
| `exclude_risk_warning` | boolean | No | Exclude risk-warning stocks when data is available. Default `true`. |
| `min_listing_days` | integer | No | Minimum listing days before a stock enters the universe. Default `120`. |
| `min_amount` | number or null | No | Minimum daily turnover amount filter. Null disables. Default `null`. |
| `codes` | list of strings | No | Specific stock codes to restrict the universe. When set, `include` is ignored. |

### `execution`

| Field | Type | Required | Description |
|---|---|---|---|
| `signal_date` | string | Yes | When rules are evaluated. `t` for same-day-close signals. |
| `entry_execution` | string | Yes | When entry orders fill. `t_plus_1_open` for next-bar-open (A-share default). |
| `exit_execution` | string | Yes | When exit orders fill. `t_plus_1_open` for next-bar-open (A-share default). |
| `market_profile` | string | Yes | Cost and rule profile. `ashare_daily_default` for standard A-share daily. |

### `capital`

| Field | Type | Required | Description |
|---|---|---|---|
| `initial_cash` | number | Yes | Starting cash. |
| `max_positions` | integer | No | Maximum concurrent positions. Null = unlimited. |
| `position_weight` | string | No | `equal` (default) or `score_weight`. |

### `risk` (experiment-level overrides)

These override the strategy-level `risk` block when present:

| Field | Type | Description |
|---|---|---|
| `max_holding_days` | integer or null | Force-exit after N trading days. |
| `stop_loss_pct` | number or null | Exit if loss from entry exceeds this fraction. |
| `take_profit_pct` | number or null | Exit if gain from entry exceeds this fraction. |
| `trailing_stop_pct` | number or null | Trailing stop distance from peak. |

### `cost_model`

| Field | Type | Required | Description |
|---|---|---|---|
| `commission_rate` | number | No | Commission rate as fraction. Default from `market_profile`. |
| `stamp_tax_rate` | number | No | Stamp tax rate. Default from `market_profile`. |
| `slippage_pct` | number | No | Slippage as fraction of price. Default from `market_profile`. |

When omitted, costs are taken from the market profile.

### `output`

| Field | Type | Description |
|---|---|---|
| `dir` | string | Output directory. Default: `outputs/{experiment.id}/` |
| `run_id` | string or null | External run identifier for cross-command traceability. |

## Backtest Modes

| Mode | CLI Command | Description |
|---|---|---|
| `single` | `qre backtest-single` | One symbol, detailed output. For debugging. |
| `batch` | `qre backtest-batch` | All symbols independently. Full-market reports. |
| `shared` | `qre backtest-shared` | All symbols sharing one cash account. Realistic portfolio simulation. |

The experiment plan declares the intended mode, and the CLI or runner selects the matching backtest command.

## Grouping

For grouped analysis, declare metadata columns:

```yaml
group_by:
  - board
  - industry
```

Available grouping columns depend on the metadata adapters configured in QRE.

## Acceptance Checklist

Before running a full backtest, verify:

- [ ] `strategy.id` is unique and versioned
- [ ] All rule aliases are declared in `factor_requirements`
- [ ] `start` and `end` dates are within available market data range
- [ ] `market_profile` matches the target market
- [ ] Execution assumptions (`t_plus_1_open`) are correct for the market
- [ ] Risk controls have reasonable values (not negative, not >100%)
- [ ] `initial_cash` is large enough for `max_positions` with sensible position sizes
- [ ] Missing factors have been requested or resolved

## Minimal Example

```yaml
experiment:
  id: rsi2_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
    exclude_st: true
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  capital:
    initial_cash: 1000000
  output:
    dir: outputs/rsi2_smoke/
```

This is enough to run a small-scope smoke test on a subset of the market.
