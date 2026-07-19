# Implementation Brief

## Task ID

QRE-MISSING-FACTOR-QUEUE-001

## Created By

KIMI_CODE (single agent; user instructions 2026-07-19: queue missing-factor requests for upstream linkage; shelve-and-continue for blocked strategies)

## Intended Implementer

KIMI_CODE

## Goal

Operationalize the missing-factor lifecycle: (1) a durable, consolidated **request queue** for indicators/periods absent from the factor DB — the standard handoff that the `indicators_tushare` project will consume later (compute + ingest, or invoke its scripts); (2) **shelve semantics** for blocked strategies in batch runs — marked `missing_factors` (not `error`), the batch continues with the next strategy, and their requests are automatically consolidated into the queue after the batch.

## User Instructions (2026-07-19)

1. Strategies needing indicators/periods absent from the factor DB: store the requests locally (DB mirror is a later option pending the user's target-DB confirmation — write access needs it per R-QRE-005).
2. During the current testing phase, shelve such strategies and continue with the next strategy's backtest.
3. Sync work state to the md docs (standard workflow).

## Scope

1. **Queue store** (`strategies/factor_request_queue.py`): consolidated JSON queue at `outputs/handoff/missing_factor_requests.json`.
   - `load_queue()` / `save_queue()` / `upsert_requests()` — dedup by (strategy_id, alias); keeps `first_seen`, updates `last_seen`, merges metadata.
   - Each entry carries `status: pending|fulfilled`; `recheck_fulfillment(store)` marks entries whose expected column now exists (read-only schema check) with `fulfilled_at` — so upstream progress is visible and shelved strategies can be re-enabled.
2. **Batch runner shelve semantics** (`orchestration/batch_runner.py`):
   - New result status `missing_factors` (shelved), distinct from generic `error`: detected when the strategy's exception is a DB missing-column/missing-table failure, or when a pre-batch schema check finds missing factor columns (reuses the read-only schema check from the M9.4 handoff).
   - After the batch, missing-factor strategies' requests are automatically upserted into the queue (strategy_id, alias, expected_table, expected_column, date_range from the batch window, reason).
   - `batch_summary.json` summary counts gain `missing_factors`; exit code treats shelved as non-failure (batch succeeds with shelved strategies; generic errors still fail).
3. **CLI** `scripts/factor_request_queue.py`: `list` (pending/fulfilled table), `recheck` (schema re-check against DB, update statuses), `show --strategy <id>`.
4. **Upstream contract doc** (`docs/handoff.md`): the queue file format, the pending→fulfilled lifecycle, how `indicators_tushare` should consume it (read queue → compute indicators → write `factors.*` → QRE `recheck` marks fulfilled → shelved strategies re-runnable via `--strategies`/`--resume`), and the future direct-invocation option.
5. **Tests**: queue dedup/upsert/recheck with fake stores; runner classification (UndefinedColumn → missing_factors vs generic exception → error); auto-queue after batch; CLI list/recheck; full suite green.

## Non-Goals

- No DB-table queue mirror in v1 (needs the user's target-DB decision; file is the durable store).
- No direct invocation of `indicators_tushare` scripts (future integration, interface TBD).
- No indicator computation inside QRE (R-QRE-002).
- No changes to upstream projects.

## Expected Tests

```bash
uv run pytest tests/test_factor_request_queue.py -q
uv run pytest -q
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# Real-DB small-sample: batch including one blocked strategy → status
# missing_factors, batch continues, queue updated; factor_request_queue.py list/recheck
```

## Acceptance Criteria

- A batch containing a blocked strategy finishes with that strategy marked `missing_factors` (shelved), the rest `ok`, and the queue file updated automatically with its requests (dedup-safe on re-runs).
- `factor_request_queue.py recheck` marks requests fulfilled when columns appear (verified with a fake and, if available, a real temporarily-present column — otherwise documented).
- `docs/handoff.md` documents the upstream consumption contract; full pytest suite green.
