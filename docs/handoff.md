# Missing-Factor Handoff Contract (QRE ↔ indicators_tushare)

Status: current operational contract (2026-07-19, QRE-MISSING-FACTOR-QUEUE-001)

## Purpose

When a QRE strategy requires an indicator/period that does not exist in the
factor database, QRE does NOT compute it (R-QRE-002). Instead the request is
queued for the upstream `indicators_tushare` project, which computes the
indicator and writes it into `factors.*`. Shelved strategies are re-enabled
once their requests are fulfilled.

## Queue file

Location: `outputs/handoff/missing_factor_requests.json` (consolidated,
deduplicated by `(strategy_id, alias)`).

Entry shape:

```json
{
  "strategy_id": "bo02_keltner_breakout",
  "alias": "atr_10",
  "indicator": "atr",
  "category": "volatility",
  "source": "close",
  "period": 10,
  "params": {},
  "output": null,
  "expected_table": "factors.stock_daily_volatility_close",
  "expected_column": "atr_10",
  "date_range": {"start": "2015-01-01", "end": "2025-12-31"},
  "reason": "factor required by strategy 'bo02_keltner_breakout'",
  "required": true,
  "first_seen": "2026-07-19T...",
  "last_seen": "2026-07-19T...",
  "status": "pending",
  "fulfilled_at": null
}
```

## Lifecycle

1. **Pending** — a batch run detects missing factor columns for a strategy
   (read-only schema check before execution). The strategy is marked
   `missing_factors` (shelved), the batch continues with the next strategy,
   and its requests are upserted into the queue automatically
   (`first_seen`/`last_seen` maintained, dedup-safe).
2. **Computation (upstream)** — `indicators_tushare` reads the queue,
   computes the requested indicator/period for the requested date range, and
   writes results into `factors.*` (ownership: upstream; QRE never writes to
   upstream databases, R-QRE-005).
3. **Fulfillment check** — `uv run python scripts/factor_request_queue.py recheck`
   re-checks the DB schema (read-only) and marks fulfilled entries with
   `fulfilled_at`.
4. **Re-enable** — re-run the shelved strategies with
   `uv run python scripts/batch_backtest_runner.py --strategies <ids> ...`;
   the pre-execution schema check now passes.

## CLI

```bash
uv run python scripts/factor_request_queue.py list            # all entries
uv run python scripts/factor_request_queue.py list --pending  # pending only
uv run python scripts/factor_request_queue.py show --strategy <id>
uv run python scripts/factor_request_queue.py recheck         # update statuses
```

## Notes

- A DB-table queue mirror is a later option pending the target-DB decision
  (QRE write access requires explicit approval, R-QRE-005).
- Direct invocation of `indicators_tushare` scripts from QRE is a future
  integration step (interface to be defined when the upstream is ready).
- Current pending requests as of 2026-07-19: atr_10 (×2 strategies),
  sma_50, sma_9, sma_26, sma_52, sma_7 — see the queue file.
