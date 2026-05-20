# Implementation Brief

## Task ID

QRE-DATA-REAL-METADATA-ADAPTERS-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`PostgresDataStore.load_security_metadata()` already exposes a read-only metadata path with fallback `list_date` and `board` derivation. The loader still normalizes a fixed subset of columns, which means real upstream status, industry, or membership-style metadata may be dropped if the source table already provides it.

The next useful step is to turn that loader into a real adapter: preserve optional upstream metadata columns when they exist, keep the current fallback behavior when they do not, and keep the assembler/preflight merge path unchanged.

## Goal

Add real status/industry/membership metadata adapters to the data layer, with fallback-preserving behavior and regression tests.

## Non-Goals

- Do not add new upstream writes.
- Do not guess new table names or invent schema that is not already available in the configured metadata source.
- Do not change existing evaluation math, portfolio math, or benchmark wiring.
- Do not compute technical indicators inside QRE.
- Do not record sensitive connection values.

## Affected Modules

Expected:

- `src/quant_research_engine/data/postgres.py`
- `src/quant_research_engine/data/assembler.py`
- `tests/test_postgres_store.py`
- `tests/test_data_assembler.py`
- `tests/test_preflight.py`

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

- Preserve existing metadata fallback behavior when optional source columns are missing.
- Keep the adapter additive and optional.
- Keep data access read-only.
- Avoid benchmark table guesses while the real source remains unconfirmed.
- Keep the implementation deterministic in behavior where the source data is deterministic.

## Implementation Steps

1. Inspect the current metadata loader normalization path and confirm which optional columns the configured source table already exposes.
2. Extend `load_security_metadata()` so optional upstream columns are preserved instead of being discarded, while the existing fallback fields remain stable.
3. Keep `ResearchFrameAssembler` and `PreflightRunner` consuming the returned frame without special-case logic.
4. Add regression tests for source-table passthrough, fallback-only operation, and downstream merge behavior.
5. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- No new upstream tables.
- Optional passthrough columns only; no guessed schema additions.

## API / Interface Changes

- `load_security_metadata()` may return additional metadata columns when the configured source table provides them.
- Downstream consumers should continue to merge the returned frame by `ts_code` without new branches.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_postgres_store.py tests/test_data_assembler.py tests/test_preflight.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `load_security_metadata()` preserves optional upstream metadata columns when the configured source table provides them.
- [ ] The existing fallback `list_date` / `board` / status behavior remains unchanged when optional columns are absent.
- [ ] `ResearchFrameAssembler` and `PreflightRunner` continue to merge metadata without special-case code.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Source tables may vary by environment, so the adapter must tolerate missing optional columns.
- Keep the implementation additive; do not disturb existing metadata fallback behavior.
- Do not overreach into real benchmark wiring before the index schema is confirmed.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the adapter small and additive.
3. Reuse the existing metadata merge path rather than introducing a new framework.
4. Update `01`, `03`, `04`, `05`, `06`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code or source columns.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
