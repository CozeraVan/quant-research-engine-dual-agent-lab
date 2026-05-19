# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-CLI-SCHEMA-VERSION-NULL-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation accepts a missing `schema_version`, supported integer `schema_version: 1`, and explicit JSON `null` because `schema_version` is optional. Existing CLI regression coverage locks schema-version type errors and JSON output for absent or integer schema versions, but explicit `schema_version: null` is not directly locked at the command boundary.

`report-files --json` and `report-audit --json` should continue accepting explicit `schema_version: null` and reporting JSON `schema_version` as `null`.

## Goal

Add CLI regression coverage for explicit `null` top-level `schema_version` while preserving existing CLI output behavior.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into general manifest schema redesign.
- Do not modify CLI or loader code unless a tiny adjustment is strictly necessary.

## Affected Modules

Expected:

- `tests/test_cli.py`

Optional only if strictly needed:

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `src/**` outside `portfolio/report_manifest.py`
- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve valid-manifest loading, filtering, and JSON output behavior.
- Keep malformed-manifest errors deterministic and clear.
- No database writes or credential handling.
- No unrelated CLI or reporting refactors.

## Implementation Steps

1. Inspect existing schema-version CLI JSON tests and schema-version type-error tests in `tests/test_cli.py`.
2. Add coverage for `report-files --json` when the manifest explicitly sets top-level `schema_version` to `null`.
3. Add coverage for `report-audit --json` when the manifest explicitly sets top-level `schema_version` to `null`; create the referenced file so the audit can pass.
4. Assert current valid command-boundary behavior: exit code `0`, no stderr, matched file count is correct, and JSON payload reports `schema_version` as `null`.
5. Do not modify CLI or loader code unless the tests expose a real bug that must be fixed.
6. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task adds regression coverage only unless a tiny bugfix is required.

## API / Interface Changes

Valid CLI behavior should remain unchanged.

Manifests with explicit `schema_version: null` should continue loading successfully through `report-files` and `report-audit`.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_cli.py -q
```

Run full tests:

```bash
uv run pytest -q
```

Run workflow checks:

```bash
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] `report-files --json` accepts explicit `schema_version: null` with exit code `0`.
- [ ] `report-audit --json` accepts explicit `schema_version: null` with exit code `0` when referenced files exist.
- [ ] Both JSON payloads report `schema_version` as `null`.
- [ ] Existing valid-manifest CLI behavior remains unchanged.
- [ ] Existing malformed-manifest CLI behavior for schema-version type errors remains unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new work scoped to CLI regression coverage.
- Avoid changing schema-version validation semantics.
- Do not introduce CLI behavior changes for valid manifests.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
