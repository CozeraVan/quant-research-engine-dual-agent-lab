# Coding Handoff

## Task ID

QRE-MISSING-FACTOR-QUEUE-001

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + real-DB verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

Per user instructions 2026-07-19 (queue missing-factor requests for upstream linkage; shelve-and-continue for blocked strategies):

1. **Queue store** (`strategies/factor_request_queue.py`): consolidated JSON queue at `outputs/handoff/missing_factor_requests.json` with dedup by (strategy_id, alias), `first_seen`/`last_seen` timestamps, `pending|fulfilled` statuses, and `recheck_fulfillment` (read-only schema check) so upstream progress is visible and shelved strategies can be re-enabled. `make_schema_column_lookup` caches per-table schema reads. `find_missing_factor_columns` / `build_requests_for_strategy` formalize the M9.4 inline logic.
2. **Shelve semantics** (`orchestration/batch_runner.py`): pre-execution read-only schema check per strategy (lazy per-process store, fork-safe); strategies with missing factor columns get status `missing_factors` (shelved, icon "M") WITHOUT executing — the batch continues. `missing_requests` attached to results and batch_summary entries; counts include `missing_factors`; exit code treats shelved as non-failure.
3. **Auto-queue** (`scripts/batch_backtest_runner.py`): after every batch, shelved strategies' requests are upserted into the queue (dedup-safe) with a printed summary.
4. **CLI** (`scripts/factor_request_queue.py`): `list [--pending|--fulfilled]`, `show --strategy`, `recheck` (updates statuses from DB schema).
5. **Upstream contract** (`docs/handoff.md`): queue file format, pending→fulfilled lifecycle, consumption contract for `indicators_tushare` (compute → ingest → recheck → re-run shelved), DB-mirror and direct-invocation as later options.
6. **Tests** (8 new): dedup/timestamps, save/load ordering, recheck + idempotence, schema lookup caching, spec-driven detection + request building, runner shelves without executing, runner executes when factors present, counts; one existing counts test updated for the new key.

## Files Changed

- `src/quant_research_engine/strategies/factor_request_queue.py` (new)
- `src/quant_research_engine/orchestration/batch_runner.py` (shelve semantics)
- `scripts/batch_backtest_runner.py` (auto-queue + exit code), `scripts/refresh_batch.py` (exit code)
- `scripts/factor_request_queue.py` (new), `docs/handoff.md` (new)
- `tests/test_factor_request_queue.py` (new, 8), `tests/test_batch_runner.py` (counts expectation)

## Validation Output

```bash
uv run pytest -q → 1129 passed, 4 warnings (1121 baseline + 8 new)

# Real-DB small batch (mr04a + tf07e × 3 codes):
#   [1/2] + mr04a ok; [2/2] M tf07e missing_factors (shelved, not executed)
#   auto-queue: +1 request → outputs/handoff/missing_factor_requests.json
#   queue list: 1 pending; recheck: 0 newly fulfilled (sma_7 still absent)
#   queue file then merged back to all 7 pending requests (atr_10×2, sma_50, sma_9/26/52, sma_7)
```
