# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Report manifests are now a stable discovery and audit entry point. The loader validates manifest kind and schema version, but malformed file entries can still fail with raw mapping access errors. A small next step is to make missing required file-entry fields fail with a clear `ValueError`.

## Goal

Add clear validation for required manifest file entry fields in `ReportFile.from_mapping(...)` or nearby loader code.

Required file entry fields:

- `key`
- `path`
- `filename`
- `role`

## Non-Goals

- Do not change generated manifest contents.
- Do not change manifest file entry shape for valid manifests.
- Do not change `qre report-files` or `qre report-audit` CLI flags.
- Do not change text or JSON output for valid manifests.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py` only if useful for CLI error behavior

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve report artifact and manifest discovery contracts for valid manifests.
- Preserve old manifest readability.
- Keep error behavior deterministic and clear.
- No database writes or credential handling.

## Implementation Steps

1. Inspect `ReportFile.from_mapping(...)` and `ReportManifest.from_path(...)`.
2. Add explicit validation for required file entry fields: `key`, `path`, `filename`, `role`.
3. Raise `ValueError` with a clear message identifying the missing field and manifest entry context.
4. Preserve optional metadata handling for `symbol`, `window`, and `group_by`.
5. Preserve existing kind and schema-version validation behavior.
6. Do not modify report writing code.
7. Add focused tests:
   - a valid manifest still loads;
   - a file entry missing `path` raises clear `ValueError`;
   - a file entry missing `role` raises clear `ValueError`.
8. Add a CLI test only if existing CLI invalid-manifest coverage does not sufficiently exercise exception propagation.
9. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task validates existing required file entry fields.

## API / Interface Changes

For invalid manifests only:

- `ReportManifest.from_path(...)` raises `ValueError` instead of an uncaught `KeyError` when a file entry lacks a required field.
- Existing CLI exception handling should continue returning exit code `2` and printing the error to stderr.

No behavior change for valid manifests.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
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

- [ ] Valid manifest file entries still load unchanged.
- [ ] Missing required file entry field raises clear `ValueError`.
- [ ] Error message identifies the missing field.
- [ ] Optional metadata fields remain optional.
- [ ] Existing report filtering, path resolution, validation, and CLI output behavior is preserved for valid manifests.
- [ ] No report writer or portfolio simulation behavior is modified.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid changing valid manifest behavior.
- Avoid making optional metadata required.
- Keep malformed-manifest errors clear for script operators.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Avoid unrelated refactors.
3. Avoid modifying forbidden files.
4. Stop and ask if the brief conflicts with existing code.
5. Run validation commands where possible.
6. Update:
   - `docs/agent/09_CODING_HANDOFF.md`
   - `docs/agent/04_TASK_HANDOFF.md`
   - `docs/agent/05_PROGRESS.md`
   - `docs/agent/11_AGENT_STATE.md`
   - `docs/agent/12_AGENT_BOARD.md`

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
