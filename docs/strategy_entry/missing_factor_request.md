# Missing-Factor Request

When QRE validates a strategy entry against the factor catalog and finds unavailable factors, it emits a missing-factor request. This request is the machine-readable contract between QRE and `indicators_tushare`.

## Purpose

The missing-factor request tells `indicators_tushare` exactly what to compute and why, so the upstream project can backfill the required data without ambiguity.

QRE never computes missing indicators internally.

## Request Schema

A missing-factor request is a JSON array of requirement objects. Each object describes one unavailable factor:

```json
{
  "strategy_id": "rsi2_oversold_reversal",
  "alias": "rsi_fast",
  "indicator": "rsi",
  "category": "momentum",
  "source": "close",
  "period": 2,
  "params": {},
  "output": null,
  "expected_table": "stock_daily_momentum_close",
  "expected_column": "rsi_2",
  "date_range": {
    "start": "2024-01-01",
    "end": "2024-12-31"
  },
  "reason": "entry and exit threshold signal",
  "required": true
}
```

### Fields

| Field | Type | Description |
|---|---|---|
| `strategy_id` | string | Strategy that needs this factor. |
| `alias` | string | Alias from `factor_requirements`. |
| `indicator` | string | Indicator name. |
| `category` | string or null | Semantic category: `momentum`, `trend`, `volatility`, `volume`, `overlap`, `statistic`. QRE infers this from the factor catalog if available. |
| `source` | string | Price field: `close`, `open`, `high`, `low`, `typical`, `hlc3`, `ohlc4`. |
| `period` | integer | Lookback window in bars. |
| `params` | object | Extra parameters (e.g. `{"fast": 12, "slow": 26, "signal": 9}` for MACD). Empty object for parameterless indicators. |
| `output` | string or null | Output column for multi-output indicators. Null for single-output indicators. |
| `expected_table` | string | QRE's best guess at the canonical table name under `factors.*`. |
| `expected_column` | string | QRE's best guess at the canonical column name. |
| `date_range` | object | `start` and `end` dates the strategy needs this factor for. |
| `reason` | string | Why the strategy needs this factor. |
| `required` | boolean | Whether the strategy can run without it. |

## Request Output

QRE emits missing-factor requests as:

- A JSON file: `missing_factor_requests.json` in the strategy's output directory
- A human-readable summary on stdout during `qre preflight` or strategy validation

Example command:

```bash
qre strategy validate strategy.yaml --output-dir outputs/check/
```

Example output file:

```json
[
  {
    "strategy_id": "rsi2_oversold_reversal",
    "alias": "rsi_fast",
    "indicator": "rsi",
    "category": "momentum",
    "source": "close",
    "period": 2,
    "params": {},
    "output": null,
    "expected_table": "stock_daily_momentum_close",
    "expected_column": "rsi_2",
    "date_range": {
      "start": "2024-01-01",
      "end": "2024-12-31"
    },
    "reason": "entry and exit threshold signal",
    "required": true
  }
]
```

## Upstream Expectations

`indicators_tushare` should:

1. Read `missing_factor_requests.json`.
2. For each request, determine whether the indicator can be computed from available source data.
3. Compute the indicator for the requested date range (or a superset).
4. Write the result to the expected table and column, or to an equivalent location documented in the factor catalog.
5. Signal completion so QRE can re-validate.

## Optional vs Required

- `required: true` — the strategy cannot run without this factor. QRE stops validation with an error.
- `required: false` — the strategy can run with reduced logic. QRE emits a warning but proceeds.

## Lifecycle States

Each missing-factor request transitions through three states:

### `pending`

A request has been emitted in `missing_factor_requests.json` but the upstream has not yet fulfilled it.

Indicators:

- `missing_factor_requests.json` exists with one or more entries.
- `qre preflight` stdout shows `missing_factor_status=pending`.
- Factor schema checks in the preflight report have `status=error`.

### `fulfilled`

The upstream `indicators_tushare` has computed and written the requested factor data. QRE re-validation confirms the factor is now available.

Indicators:

- `missing_factor_requests.json` is `[]` (empty array).
- `qre preflight` stdout shows `missing_factor_status=ok`.
- Factor schema checks all pass (`status=ok`).

To reach this state:

1. Run `indicators_tushare` to consume `missing_factor_requests.json` and backfill the data.
2. Re-run `qre preflight --output-dir <dir>` to re-validate.
3. If all factors are now available, the file will be `[]` and backtest execution can proceed.

### `blocked`

The upstream cannot fulfill the request due to:

- Missing source data (e.g., the price source or date range is not available).
- Permission or access restrictions on the upstream data provider.
- Data contract mismatch (e.g., the expected table/column naming convention is incompatible).

Indicators:

- `missing_factor_requests.json` still has entries after an upstream attempt.
- The upstream should document the reason in its own output or log.
- QRE does not automatically detect `blocked` — a human or upstream process must flag it.

## Batch Requests

Multiple strategies can share factor requirements. QRE may emit a merged request file for a strategy family or research batch. The `strategy_id` field preserves traceability back to each strategy.
