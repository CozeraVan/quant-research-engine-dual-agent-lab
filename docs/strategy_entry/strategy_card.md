# Strategy Card

The strategy card describes the strategy identity and trading logic. It is the first section of a QRE strategy entry file.

## Required Fields

### `strategy`

| Field | Type | Required | Description |
|---|---|---|---|
| `id` | string | Yes | Unique strategy identifier, lowercase snake_case. Example: `rsi2_oversold_reversal` |
| `name` | string | Yes | Human-readable name. Example: `RSI2 Oversold Reversal` |
| `family` | string | Yes | Strategy family. Recommended values: `trend_following`, `mean_reversion`, `breakout`, `momentum`, `carry`, `arbitrage`, `custom` |
| `description` | string | Yes | One-paragraph summary of what the strategy does and why. |
| `direction` | string | Yes | `long_only`, `short_only`, or `long_short` |
| `version` | string | No | Semantic version. Example: `1.0.0` |

### `rules`

The `rules` section defines entry, exit, risk, holding, and position-sizing logic.

| Block | Required | Description |
|---|---|---|
| `entry` | Yes | Conditions that trigger a new position. |
| `exit` | No | Conditions that trigger a position exit (in addition to risk exits). |
| `risk` | No | Stop-loss, take-profit, trailing-stop, and max-holding-day controls. |
| `holding` | No | Direction, max holding days. |
| `position_sizing` | No | Weight model, equal/score/risk-parity selection. |

## Rule Expression Format

Each rule block contains one or more condition groups. Conditions reference indicator aliases declared in `factor_requirements`.

### Logical Combinators

- `all` — every condition must be true (AND).
- `any` — at least one condition must be true (OR).

### Condition Fields

| Field | Type | Description |
|---|---|---|
| `indicator` | string | Indicator name (e.g. `rsi`, `ema`, `macd`). For reference only — the compiler resolves via `alias`. |
| `alias` | string | **Must match an alias in `factor_requirements`**. This is the data binding. |
| `operator` | string | Comparison: `<`, `>`, `<=`, `>=`, `==`, `!=`, `crosses_above`, `crosses_below` |
| `value` | number | Threshold value. |
| `alias_b` | string | For two-indicator comparisons: the second alias. |

### Examples

Simple threshold entry:

```yaml
entry:
  all:
    - alias: rsi_fast
      operator: "<"
      value: 10
```

Multi-condition entry (price above EMA AND RSI oversold):

```yaml
entry:
  all:
    - alias: ema_200
      operator: "<"
      alias_b: close
    - alias: rsi_fast
      operator: "<"
      value: 30
```

Crossover entry:

```yaml
entry:
  any:
    - alias: macd_line
      operator: crosses_above
      alias_b: macd_signal
```

Exit with OR logic:

```yaml
exit:
  any:
    - alias: rsi_fast
      operator: ">"
      value: 70
    - alias: close
      operator: ">="
      alias_b: bb_upper
```

### Built-in Aliases

These aliases are always available without declaring factor requirements:

| Alias | Meaning |
|---|---|
| `close` | Daily close price |
| `open` | Daily open price |
| `high` | Daily high price |
| `low` | Daily low price |
| `pre_close` | Previous day close |
| `vol` | Daily volume |
| `amount` | Daily turnover amount |

## Risk Controls

Risk controls are stop conditions that override holding rules. They are evaluated on each bar after entry.

```yaml
risk:
  stop_loss_pct: 0.08       # Exit if loss exceeds 8% from entry price
  take_profit_pct: 0.12     # Exit if gain exceeds 12% from entry price
  trailing_stop_pct: null   # Trailing stop distance (null = disabled)
  max_holding_days: 5       # Force-exit after N trading days
```

All risk fields are optional. Omitted or null fields are disabled.

## Holding Rules

```yaml
holding:
  direction: long_only       # long_only, short_only, or long_short
  max_holding_days: 9999     # Override for strategies without time-based exits
```

`max_holding_days` in `holding` is a default; `risk.max_holding_days` takes precedence when both are set.

## Position Sizing

```yaml
position_sizing:
  weight_model: equal        # equal, score_weight, or risk_parity
  score_column: null         # Alias of factor used for scoring (required for score_weight)
  volatility_column: null    # Alias of factor used for risk_parity
```

When `position_sizing` is omitted, `equal` weight is assumed.

## Execution Assumptions

These are declared in the `experiment` section, not `rules`, but they affect rule semantics:

| Field | Default | Meaning |
|---|---|---|
| `signal_date` | `t` | Rules are evaluated on bar `t` |
| `entry_execution` | `t_plus_1_open` | Entry fills at open of `t+1` |
| `exit_execution` | `t_plus_1_open` | Exit fills at open of `t+1` |

These defaults reflect A-share T+1 mechanics and prevent lookahead bias.

## Naming Conventions

- Strategy ID: `{indicator_family}_{logic_type}`, lowercase, underscores. Examples: `rsi2_oversold_reversal`, `ema200_bollinger_mean_reversion`, `macd_zero_cross_momentum`
- Version: semantic versioning. Increment MAJOR when backtest results would not be comparable to prior versions.
- Factor aliases: `{indicator_abbrev}_{period}` or `{indicator_abbrev}_{role}`. Examples: `rsi_fast`, `ema_slow`, `macd_line`, `bb_upper`
