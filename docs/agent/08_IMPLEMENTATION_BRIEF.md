# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-ENTRY-TYPE-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation now covers invalid JSON text, root payload shape, top-level `files` shape, required file entry presence, supported `schema_version`, and top-level `kind`. One nearby hardening gap remains inside `ReportFile.from_mapping(...)`: malformed entry field values are still silently coerced with `str(...)`, so numeric, boolean, or container values can pass through as bogus strings instead of failing with a clear manifest-specific validation error.

## Goal

Make manifest file-entry field type validation explicit for required and optional string fields while preserving current behavior for valid manifests.

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

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`

Optional only if strictly needed:

- `tests/test_cli.py`

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

1. Inspect `ReportFile.from_mapping(...)`, `_optional_string(...)`, and nearby manifest-loader tests.
2. Add explicit validation that required file-entry fields `key`, `path`, `filename`, and `role` are strings.
3. Add explicit validation that optional file-entry fields `symbol`, `window`, and `group_by` are either strings or `null`/absent.
4. Preserve the existing missing-required-field `ValueError` behavior.
5. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - non-string required field values;
   - non-string optional metadata values;
   - a valid manifest with string metadata still loading unchanged.
6. Add CLI regression coverage in `tests/test_cli.py` only if it is needed to lock down command-boundary propagation of the loader error.
7. Keep the task helper-focused; do not modify report writer code.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with non-string file-entry field values should now raise clear `ValueError` messages instead of being silently coerced into strings.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q
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

- [ ] Non-string required file-entry field values are rejected with clear `ValueError`.
- [ ] Non-string optional metadata values are rejected with clear `ValueError`.
- [ ] Existing missing-required-field validation remains intact.
- [ ] Valid manifests still load unchanged.
- [ ] Existing invalid-JSON, root, `files`, `kind`, schema-version, and file-entry presence validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new validation narrowly scoped to file-entry field types.
- Do not weaken the existing missing-field validation or valid-manifest behavior.
- Do not let the new checks disturb the recently added invalid-JSON, root, `files`, `kind`, or schema-version validation.

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
