# Strategy Entry Examples

Three complete strategy entries covering different strategy families: mean-reversion, trend-following, and momentum/breakout.

Each example follows the three-section format: `strategy` + `rules`, `factor_requirements`, `experiment`.

These examples are plumbing demonstrations. They validate the entry format and factor-resolution path, not strategy alpha.

---

## Example 1: RSI2 Oversold Reversal (Mean Reversion)

Family: `mean_reversion`. Buys short-term RSI oversold signals, exits on RSI recovery.

```yaml
strategy:
  id: rsi2_oversold_reversal
  name: RSI2 Oversold Reversal
  family: mean_reversion
  description: >
    Buy when 2-period RSI drops below 10 (short-term oversold extreme).
    Exit when RSI recovers above 70 or a risk stop triggers.
    Designed for A-share daily T+1 execution.
  direction: long_only
  version: "1.0.0"

rules:
  entry:
    all:
      - alias: rsi_fast
        operator: "<"
        value: 10
  exit:
    any:
      - alias: rsi_fast
        operator: ">"
        value: 70
  risk:
    stop_loss_pct: 0.08
    take_profit_pct: 0.12
    trailing_stop_pct: null
    max_holding_days: 5
  position_sizing:
    weight_model: equal

factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: entry and exit threshold signal — detects short-term oversold and recovery

experiment:
  id: rsi2_oversold_reversal_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
    exclude_st: true
    exclude_suspended: true
    exclude_risk_warning: true
    min_listing_days: 120
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  capital:
    initial_cash: 1000000
    max_positions: 10
    position_weight: equal
  output:
    dir: outputs/rsi2_oversold_reversal_smoke/
```

### What This Validates

- Single-indicator strategy with entry and exit thresholds
- Risk stop-loss and take-profit active alongside signal exit
- Equal-weight position sizing
- Minimal factor requirements (one entry)

---

## Example 2: EMA200 + Bollinger Band Mean Reversion (Trend-Filtered Mean Reversion)

Family: `mean_reversion`. Uses a long-term EMA as trend filter and Bollinger Bands for entry/exit.

```yaml
strategy:
  id: ema200_bollinger_reversal
  name: EMA200 Bollinger Band Reversal
  family: mean_reversion
  description: >
    Buy when price is above EMA200 (uptrend filter) and closes at or below
    the lower Bollinger Band (2 stddev). Exit when price closes at or above
    the upper Bollinger Band. Long-only, daily A-share.
  direction: long_only
  version: "1.0.0"

rules:
  entry:
    all:
      - alias: close
        operator: ">"
        alias_b: ema_200
      - alias: close
        operator: "<="
        alias_b: bb_lower
  exit:
    any:
      - alias: close
        operator: ">="
        alias_b: bb_upper
  risk:
    stop_loss_pct: 0.10
    max_holding_days: 20

factor_requirements:
  - alias: ema_200
    indicator: ema
    source: typical
    period: 200
    required: true
    reason: long-term trend direction filter

  - alias: bb_upper
    indicator: bollinger
    source: close
    period: 20
    params:
      stddev: 2.0
    output: upper
    required: true
    reason: exit threshold — price crossing above upper band

  - alias: bb_lower
    indicator: bollinger
    source: close
    period: 20
    params:
      stddev: 2.0
    output: lower
    required: true
    reason: entry threshold — price at or below lower band

experiment:
  id: ema200_bollinger_reversal_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
    exclude_st: true
    exclude_suspended: true
    exclude_risk_warning: true
    min_listing_days: 250
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  capital:
    initial_cash: 1000000
    max_positions: 10
    position_weight: equal
  output:
    dir: outputs/ema200_bollinger_reversal_smoke/
```

### What This Validates

- Multi-indicator strategy with trend filter
- Built-in alias comparisons (`close > ema_200`, `close <= bb_lower`)
- Multi-output indicator (Bollinger Bands upper/lower)
- Three factor requirements with matching params

---

## Example 3: MACD Zero-Cross Momentum (Momentum)

Family: `momentum`. Buys when MACD line crosses above the signal line from below zero, exits when MACD crosses below signal.

```yaml
strategy:
  id: macd_zero_cross_momentum
  name: MACD Zero-Cross Momentum
  family: momentum
  description: >
    Buy when MACD line crosses above signal line while both are below zero
    (early momentum turn). Exit when MACD line crosses back below signal line.
    Long-only, daily A-share.
  direction: long_only
  version: "1.0.0"

rules:
  entry:
    all:
      - alias: macd_line
        operator: crosses_above
        alias_b: macd_signal
      - alias: macd_line
        operator: "<"
        value: 0
  exit:
    any:
      - alias: macd_line
        operator: crosses_below
        alias_b: macd_signal
  risk:
    stop_loss_pct: 0.08
    max_holding_days: 10

factor_requirements:
  - alias: macd_line
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: macd
    required: true
    reason: MACD line for zero-axis position and crossover detection

  - alias: macd_signal
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: signal
    required: true
    reason: MACD signal line for crossover entry and exit

experiment:
  id: macd_zero_cross_momentum_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-02-01
  universe:
    include: all_a
    exclude_st: true
    exclude_suspended: true
    exclude_risk_warning: true
    min_listing_days: 250
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  capital:
    initial_cash: 1000000
    max_positions: 10
    position_weight: equal
  output:
    dir: outputs/macd_zero_cross_momentum_smoke/
```

### What This Validates

- Multi-output indicator with parameter object (MACD fast/slow/signal)
- Crossover operator (`crosses_above`, `crosses_below`)
- Multi-condition entry (crossover AND negative MACD)
- Two factor requirements for one logical indicator

---

## Mapping to Current QRE Internals

These standard entry files are designed for the future compiler. Until the compiler is implemented, here is how each example maps to the current low-level `StrategySpec` YAML understood by `qre backtest-batch`:

### RSI2 → Current Format

```yaml
data:
  factor_fields:
    rsi_fast: factors.stock_daily_momentum_close.rsi_2
signal:
  type: expression
  entry: rsi_fast < 10
  exit: rsi_fast > 70
```

### EMA200 + Bollinger → Current Format

```yaml
data:
  factor_fields:
    ema_200: factors.stock_daily_overlap_typical_price.ema_200
    bb_upper: factors.stock_daily_volatility_close.bbu_20_2_0_2_0
    bb_lower: factors.stock_daily_volatility_close.bbl_20_2_0_2_0
signal:
  type: expression
  entry: close > ema_200 and close <= bb_lower
  exit: close >= bb_upper
```

### MACD → Current Format

```yaml
data:
  factor_fields:
    macd_line: factors.stock_daily_momentum_close.macd_12_26_9
    macd_signal: factors.stock_daily_momentum_close.macd_signal_12_26_9
signal:
  type: expression
  entry: macd_line > macd_signal and macd_line < 0
  exit: macd_line < macd_signal
```

Note: the crossover operator (`crosses_above`/`crosses_below`) does not have a direct current-format equivalent. The current `StrategySpec` uses pandas-evaluable expressions. The compiler will expand crossovers into lagged comparisons against the previous bar.

## Smoke Test Expectations

Each example should pass a small-scope smoke test:

```bash
qre backtest-batch examples/rsi2_oversold_reversal.yaml \
  --start 2024-01-01 --end 2024-02-01 \
  --output-dir outputs/rsi2_smoke/
```

Acceptance: command exits `0`, output directory contains `report_manifest.json`, and `report-audit --validate-contents` returns zero issues.

These smoke tests are plumbing validation only — they do not represent strategy alpha evidence.
