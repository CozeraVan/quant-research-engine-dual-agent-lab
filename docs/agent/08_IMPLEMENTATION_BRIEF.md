# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-SCHEMA-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Report manifests now include a deterministic top-level `schema_version: 1`, and JSON report tooling exposes the field. The loader currently preserves old manifests without the field. A small next step is to make unsupported future versions fail clearly instead of being silently accepted.

## Goal

Add explicit manifest schema-version validation in `ReportManifest.from_path(...)`: accept missing `schema_version` and version `1`, reject unsupported present values with a clear error.

## Non-Goals

- Do not change generated manifest contents.
- Do not change manifest file entry shape.
- Do not change `qre report-files` or `qre report-audit` CLI flags.
- Do not change text or JSON output for valid manifests.
- Do not change portfolio simulation behavior.
- Do not add timestamps, command lines, git SHAs, hostnames, usernames, or other environment-dependent metadata.
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

- Preserve report artifact and manifest discovery contracts for supported manifests.
- Preserve old manifest readability.
- Keep error behavior deterministic and clear.
- No database writes or credential handling.

## Implementation Steps

1. Inspect `ReportManifest.from_path(...)`.
2. Add a small helper or inline check that validates top-level `schema_version`.
3. Accept:
   - missing `schema_version`;
   - `schema_version == 1`.
4. Reject unsupported present values, including values other than integer `1`, with a clear `ValueError`.
5. Preserve existing manifest kind validation and file-entry loading behavior.
6. Do not modify report writing code; generated manifests already use `schema_version: 1`.
7. Add focused tests:
   - missing `schema_version` still loads;
   - `schema_version: 1` still loads;
   - unsupported numeric version, for example `2`, raises a clear error;
   - non-integer version, for example `"1"`, raises a clear error.
8. Add a CLI test only if existing CLI error coverage does not already exercise `ReportManifest.from_path(...)` exceptions clearly enough.
9. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task validates the existing optional manifest schema marker.

## API / Interface Changes

For invalid manifests only:

- `ReportManifest.from_path(...)` raises `ValueError` for unsupported present `schema_version`.
- Existing CLI exception handling should continue returning exit code `2` and printing the error to stderr.

No behavior change for old manifests without `schema_version` or current manifests with `schema_version: 1`.

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

- [ ] Missing `schema_version` remains readable.
- [ ] `schema_version: 1` remains readable.
- [ ] Unsupported present schema version raises a clear `ValueError`.
- [ ] Existing report filtering, path resolution, validation, and CLI output behavior is preserved for valid manifests.
- [ ] No report writer or portfolio simulation behavior is modified.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid rejecting legacy manifests that lack the field.
- Avoid weakening current manifest discovery or audit behavior.
- Keep unsupported-version errors clear for script operators.

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
