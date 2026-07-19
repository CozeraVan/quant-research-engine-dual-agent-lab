# Implementation Brief

## Task ID

QRE-PREFLIGHT-MISSING-FACTOR-ROBUSTNESS-001

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Fix a contract violation found during the M9.4 handoff: `qre preflight` **crashes** with a raw SQL `UndefinedColumn` error when a strategy's factor column is absent from the database, instead of completing with an error report and emitting `missing_factor_requests.json` — the documented operational handoff for upstream factor production (M8.3/M8.7).

## Root Cause (verified)

`preflight.py::PreflightRunner.run()` first runs `_factor_schema_checks(factor)` (which correctly reports `factor_schema:<name>` error checks for missing tables/columns via schema introspection) but then unconditionally calls `store.load_factor_history(field_requests=request.factor_fields)` with ALL requested factors — including the missing column — and the database raises `UndefinedColumn` before the report (and the missing-factor extraction) can complete.

## Scope

1. In `PreflightRunner.run()`: after the schema checks, call `load_factor_history` only with **loadable** factor fields (table exists AND column exists). Missing factors keep their `factor_schema:<name>` error check and get zero-coverage factor coverage rows (status error) — no crash, report completes with overall error status, and `extract_missing_factors` works end-to-end again.
2. Tests (`tests/test_preflight.py` additions): missing-column strategy completes with error report + extractable missing-factor request; mixed loadable+missing factors; all-missing factors; loadable path unchanged.
3. Docs: record the fix in `09_CODING_HANDOFF.md` and mark the M9.4 noted follow-up resolved.

## Non-Goals

- No changes to `load_factor_history` itself (callers must pass existing columns; the assembler path intentionally errors on truly missing factors during backtests, which the batch runner already captures as strategy errors).
- No new missing-factor semantics, no upstream changes, no new dependencies.

## Expected Tests

```bash
uv run pytest tests/test_preflight.py -q
uv run pytest -q
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# Real-DB: qre preflight on bo02_keltner_breakout (missing atr_10) completes
# with error report and emits missing_factor_requests.json
```

## Acceptance Criteria

- Preflight on a strategy with missing factor columns completes (does not raise), reports `factor_schema:*` error checks, and `qre preflight --output-dir` emits `missing_factor_requests.json`.
- All 5 blocked strategies produce their requests through the standard `qre preflight` path (verified against the M9.4 consolidated file).
- Full pytest suite green; existing preflight behavior for available factors unchanged.
