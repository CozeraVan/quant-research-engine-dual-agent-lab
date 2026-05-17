# A-Share First Market Profile

## Purpose

This is the first market implementation for the universal engine.

It should model A-share daily trading realistically enough for factor research and daily strategy validation.

## Default Rules

```yaml
market_profile:
  name: ashare_daily_default
  timezone: Asia/Shanghai
  frequency: daily
  signal_lag:
    signal_date: t
    earliest_execution: t_plus_1
  settlement:
    stock_t_plus_one: true
  lot_size:
    buy_lot: 100
    allow_odd_lot_sell: true
  price_limit:
    main_board: 0.10
    chinext: 0.20
    star_market: 0.20
    beijing: 0.30
    st: 0.05
  costs:
    commission_rate: 0.0003
    min_commission: 5.0
    stamp_tax_sell: 0.0005
    transfer_fee_rate: 0.00001
  slippage:
    model: percent
    buy_rate: 0.0005
    sell_rate: 0.0005
```

The current implementation supports the `percent` slippage model:

- buy execution price = raw execution price * `(1 + buy_rate)`
- sell execution price = raw execution price * `(1 - sell_rate)`

By default, the in-code `AShareMarketProfile()` uses zero slippage. To use the YAML profile values, pass the profile file explicitly in CLI workflows.

## Execution Assumptions for First Milestone

- Signals form on trade date `t`.
- Default execution is next trading day open.
- If a stock is suspended on execution date, the order fails.
- If a buy order is blocked by limit-up conditions, the order fails.
- If a sell order is blocked by limit-down conditions, the order fails.
- Shares bought on `t` are not sellable until `t+1`.
- Buy quantity is rounded down to board lot size.
- Sell odd lots may be allowed if position contains odd-lot inventory.

## Data Requirements

Minimum market fields:

- `ts_code`
- `trade_date`
- `open`
- `high`
- `low`
- `close`
- `pre_close`
- `vol`
- `amount`

Recommended fields:

- `adj_factor`
- `turnover_rate`
- security metadata
- industry classification
- ST/risk-warning history
- suspension flags
- benchmark index history

## First Research Use Cases

- RSI reversal
- moving-average trend
- Bollinger mean reversion
- MACD momentum
- Donchian breakout
- factor rank top-N selection
- quantile factor spread
