# Implementation Brief

## Task ID

QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`PostgresDataStore.load_security_metadata()` currently supports two modes:

1. A configured security metadata table via `QRE_SECURITY_METADATA_TABLE` / `SR_SECURITY_METADATA_TABLE`.
2. A fallback derived from `public.stock_daily`, which synthesizes `list_date`, infers `board`, and sets `is_st`, `is_risk_warning`, and `is_suspended` to `False`.

That fallback is good enough for smoke coverage, but it leaves the portfolio/preflight path without real suspension and ST/risk-warning behavior. The repository also does not yet confirm which upstream table should be used as the authoritative source for time-varying security-status metadata. The reusable Tushare source scaffold now exists for future source-shape probing.

## Goal

Confirm the upstream security-status metadata source table/schema and wire real suspension/ST/risk-warning metadata through the read-only data layer if the table exists.

## Non-Goals

- Do not write to upstream databases.
- Do not change `PostgresDataStore.load_security_metadata()` unless the confirmed source table can safely replace the fallback.
- Do not hardcode credentials or invent status semantics.
- Do not change market-profile rules, evaluation logic, or unrelated portfolio behavior.
- Do not edit legacy archived docs under `docs/legacy`.
- Do not expand into benchmark wiring, regime classification, or broad metadata refactors unless they are required to support the confirmed source table.

## Affected Modules

Expected runtime/tests:

- `src/quant_research_engine/data/postgres.py`
- `tests/test_postgres_store.py`
- `tests/test_preflight.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `docs/legacy/**`
- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- `README.md`
- `docs/modules/**`
- `src/quant_research_engine/**` unless the data-layer metadata adapter is the confirmed implementation surface

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve read-only data access.
- Keep the existing fallback behavior unless the confirmed source table can safely replace it.
- Do not invent status semantics or table schemas.
- If no confirmed upstream table/schema can be identified, stop and write a blocker with the exact missing information.

## Implementation Steps

1. Inspect `PostgresDataStore.load_security_metadata()`, `_load_security_metadata_table()`, `_derive_security_metadata_from_daily()`, and `_normalize_security_metadata()` in `src/quant_research_engine/data/postgres.py`.
2. Confirm the authoritative upstream security metadata table/schema from local repo config, docs, or database metadata access.
3. If the source table exists, implement the read-only adapter so real suspension/ST/risk-warning values flow through `load_security_metadata()` and remain consumable by `preflight.py` and downstream portfolio code.
4. Add or adjust targeted tests in `tests/test_postgres_store.py` and `tests/test_preflight.py` to lock the chosen behavior.
5. If no confirmed table/schema exists, stop with a blocker that names the missing table and columns.
6. Update handoff/progress docs.

## Data / Schema Changes

- No schema migration.
- Read-only metadata loading only.
- Any new source-table assumptions must be documented explicitly in the blocker or final handoff.

## API / Interface Changes

- No public API changes are expected outside the Tushare security source helper and tests.
- No public API changes are expected unless the confirmed source table requires a small loader extension.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_postgres_store.py tests/test_preflight.py -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] The confirmed upstream security metadata source table/schema is identified, or a blocker records the missing information exactly.
- [ ] If a confirmed table exists, `load_security_metadata()` loads real suspension/ST/risk-warning metadata without breaking the existing fallback path.
- [ ] `preflight.py` continues to consume metadata correctly for exclusion checks.
- [ ] Targeted tests in `tests/test_postgres_store.py` and/or `tests/test_preflight.py` lock the implemented behavior.
- [ ] Legacy archived docs are untouched.
- [ ] `uv run pytest tests/test_postgres_store.py tests/test_preflight.py -q`, `scripts/check-progress-docs.sh`, and `git diff --check` pass, or the blocker explains why they cannot.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state if code changes were made.

## Risks

- The source table may not exist or may have a date-granular schema that needs explicit confirmation before implementation.
- Avoid replacing the current fallback with an incorrect partial schema.
- Preserve read-only access and do not invent hidden writes or refresh jobs.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Start by confirming the security metadata source table/schema.
3. Avoid editing `docs/legacy/**`.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation or blocker discovery.
5. Stop and write a blocker if the source table/schema cannot be confirmed.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
