# Implementation Brief

## Task ID

QRE-PORTFOLIO-BATCH-METADATA-GROUPBY-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

The data layer now preserves optional upstream metadata columns from the configured security metadata table. `backtest-batch` already assembles research frames with metadata and supports `--group-by`, but `BatchBacktestEngine` only copies a fixed metadata whitelist into `BatchBacktestResult.summary`.

That means newly preserved metadata columns can exist in the research frame but still be unavailable to existing batch grouped reports.

## Goal

Let batch backtests carry requested metadata `group_by` columns into the batch summary, so existing stdout and output-dir grouped report paths work for optional upstream metadata columns.

## Non-Goals

- Do not add new upstream tables or database writes.
- Do not guess specific metadata schemas, table names, or column meanings.
- Do not change portfolio execution, order, risk, cost, or return math.
- Do not change shared-cash or single-symbol behavior unless required by imports or tests.
- Do not compute technical indicators inside QRE.
- Do not record sensitive connection values.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/batch.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_portfolio_batch.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/01_CURRENT_STATUS.md`
- `docs/agent/03_ROADMAP.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/06_DECISION_LOG.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve existing batch summary metadata columns by default.
- Keep the change additive and scoped to metadata propagation/report grouping.
- Keep data access read-only.
- Avoid benchmark and time-varying-status table guesses.
- Do not change portfolio simulation math.

## Implementation Steps

1. Inspect `BatchBacktestRequest`, `BatchBacktestEngine._metadata_row()`, CLI `backtest-batch`, and existing group-by report writers.
2. Add a small mechanism for batch requests to ask the engine to include extra metadata columns in `summary`. A conservative shape is `summary_metadata_columns: list[str] | None = None`, with the current fixed `SUMMARY_METADATA_COLUMNS` preserved as defaults.
3. In CLI `backtest-batch`, pass the requested `--group-by` columns as extra summary metadata columns so existing `summarize_batch_by()` and `write_batch_result(..., group_by=...)` can use them.
4. Preserve existing behavior when `--group-by` is omitted.
5. Keep missing-column behavior explicit. If a requested group-by column is absent from the assembled frame, returning the current `summary must include <column>` error from grouped summary code is acceptable.
6. Add regression tests for engine-level metadata propagation and CLI batch grouping by a passthrough column.
7. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.
- No hardcoded new metadata schema. Columns are request-driven.

## API / Interface Changes

- `BatchBacktestRequest` may gain an optional `summary_metadata_columns` list.
- CLI `backtest-batch --group-by <column>` should make that column available in `BatchBacktestResult.summary` when it exists in the research frame.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_batch.py tests/test_cli.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Existing batch summary metadata columns still appear as before.
- [ ] A requested passthrough metadata group-by column can appear in `BatchBacktestResult.summary`.
- [ ] `qre backtest-batch --group-by <passthrough_column>` can print and persist grouped reports when that column exists in the assembled frame.
- [ ] Missing requested group-by columns still fail clearly.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Copying too many frame columns into summary could leak factor columns into report metadata. Keep propagation request-driven.
- Keep the implementation small; do not create a new metadata registry for this task.
- Do not overreach into real benchmark wiring or time-varying status metadata before source schemas are confirmed.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the metadata propagation explicit and request-driven.
3. Reuse existing group-by report paths rather than adding new report types.
4. Update `01`, `03`, `04`, `05`, `06`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
