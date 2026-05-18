# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-CLI-FILE-ENTRY-SHAPE-REGRESSION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation rejects malformed `files` entries such as non-object entries and non-string required entry fields, but the CLI regression suite does not yet lock representative entry-shape/type errors at the command boundary. `report-files` and `report-audit` should keep surfacing these malformed-manifest failures with exit code `2` and clear stderr output.

## Goal

Add CLI regression coverage for malformed manifest file entries while preserving existing valid-manifest CLI behavior.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into general manifest schema redesign.
- Do not modify CLI code unless a tiny adjustment is strictly necessary.

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

- Preserve valid-manifest loading and filtering behavior.
- Keep malformed-manifest errors deterministic and clear.
- No database writes or credential handling.
- No unrelated CLI or reporting refactors.

## Implementation Steps

1. Inspect existing malformed-manifest CLI tests in `tests/test_cli.py`.
2. Add coverage for `report-files` when a `files` entry is not an object.
3. Add coverage for `report-files` when a required file-entry field has the wrong type.
4. Add coverage for `report-audit` when a `files` entry is not an object.
5. Add coverage for `report-audit` when a required file-entry field has the wrong type.
6. Assert current command-boundary behavior: exit code `2` and clear stderr containing the loader error.
7. Do not modify CLI or loader code unless the tests expose a real bug that must be fixed.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task adds regression coverage only unless a tiny bugfix is required.

## API / Interface Changes

Valid CLI behavior should remain unchanged.

Malformed manifests with non-object file entries or non-string required entry fields should continue surfacing a clear loader error through CLI stderr with exit code `2`.

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

- [ ] `report-files` surfaces a non-object file entry with exit code `2`.
- [ ] `report-files` surfaces a non-string required file-entry field with exit code `2`.
- [ ] `report-audit` surfaces a non-object file entry with exit code `2`.
- [ ] `report-audit` surfaces a non-string required file-entry field with exit code `2`.
- [ ] Existing valid-manifest CLI behavior remains unchanged.
- [ ] Existing malformed-manifest CLI behavior for malformed roots, unsupported `kind`, unsupported `schema_version`, missing top-level fields, top-level type errors, and missing file-entry fields remains unchanged.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new work scoped to CLI regression coverage.
- Avoid weakening existing malformed-manifest stderr expectations.
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
