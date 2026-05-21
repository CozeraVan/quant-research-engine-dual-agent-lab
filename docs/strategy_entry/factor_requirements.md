# Factor Requirements

Factor requirements declare what data the strategy needs and form the handoff contract between QRE and the upstream data layer.

## Purpose

The `factor_requirements` section tells QRE:

- Which indicators the strategy rules reference
- What source price field and period each indicator needs
- Which output to use for multi-output indicators (e.g. MACD)
- Whether the requirement is mandatory or optional

The author does not write low-level table paths. The QRE compiler resolves aliases to `factors.{table}.{column}` at validation time.

## Requirement Format

Each entry in `factor_requirements` is a mapping:

| Field | Type | Required | Description |
|---|---|---|---|
| `alias` | string | Yes | Short name used in `rules` conditions. Must be unique within the strategy. |
| `indicator` | string | Yes | Indicator name understood by `indicators_tushare` and QRE factor catalog. |
| `source` | string | Yes | Price field used as input: `close`, `open`, `high`, `low`, `typical`, `hlc3`, `ohlc4` |
| `period` | integer | Yes | Lookback window in bars. |
| `params` | mapping | No | Extra parameters for multi-parameter indicators. |
| `output` | string | No | Which output column to use for multi-output indicators. Omit for single-output indicators. |
| `required` | boolean | No | Default `true`. Set `false` for optional factors (strategy runs with reduced logic when missing). |
| `reason` | string | Yes | Why the strategy needs this factor. Used in missing-factor requests and documentation. |

## Single-Output Indicators

For indicators like RSI, EMA, or Bollinger Bands that produce one primary output per parameter set:

```yaml
factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: entry threshold signal — detect short-term oversold

  - alias: ema_200
    indicator: ema
    source: typical
    period: 200
    required: true
    reason: trend filter — only trade in direction of long-term trend
```

The QRE compiler resolves these to the factor catalog convention. For example, `rsi` with `source=close` and `period=2` maps to the canonical `factors` column.

## Multi-Output Indicators

For indicators like MACD or Bollinger Bands that produce multiple output columns, each output needs its own requirement entry with the same params:

```yaml
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
    reason: MACD line for zero-axis cross detection

  - alias: macd_signal
    indicator: macd
    source: close
    params:
      fast: 12
      slow: 26
      signal: 9
    output: signal
    required: true
    reason: MACD signal line for crossover confirmation

  - alias: bb_upper
    indicator: bollinger
    source: close
    period: 20
    params:
      stddev: 2.0
    output: upper
    required: true
    reason: upper band for exit signal

  - alias: bb_lower
    indicator: bollinger
    source: close
    period: 20
    params:
      stddev: 2.0
    output: lower
    required: true
    reason: lower band for entry signal
```

## Optional Factors

When a factor is marked `required: false`, the strategy should document what happens when it is missing:

```yaml
factor_requirements:
  - alias: atr_14
    indicator: atr
    source: typical
    period: 14
    required: false
    reason: volatility filter — skip trades in low-volatility regimes; when missing, all entries pass the volatility gate
```

## Period Handling

The `period` field is an integer number of daily bars. QRE and `indicators_tushare` interpret it as:

- For `rsi`: lookback window for the RSI calculation
- For `ema`: smoothing period
- For `bollinger`: lookback window for the moving average and standard deviation
- For `macd`: this is the signal line period; fast/slow are in `params`

Period values must be positive integers. Fractional periods and calendar-window periods are not supported in v1.

## Factor Catalog Resolution

QRE resolves factor requirements against its factor catalog at validation time. The catalog maps `(indicator, source, period, params, output)` tuples to concrete `factors.{table}.{column}` paths.

The author should never write table paths in the strategy entry. The compiler manages mapping, and the mapping convention is documented separately for QRE maintainers.

## Dependency Declaration

A complete strategy entry must declare every indicator alias used in `rules`. The compiler rejects entries with undeclared aliases.

Best practice: keep the factor requirements list in the same order as they appear in the rules, so a reader can scan from requirements to conditions.
