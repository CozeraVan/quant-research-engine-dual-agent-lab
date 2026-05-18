# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-ROOT-SHAPE-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation now covers supported `schema_version`, required file entry fields, and top-level `files` shape. One nearby malformed-manifest gap remains: when the JSON root itself is not an object, `ReportManifest.from_path()` still fails with raw `AttributeError` because it assumes `payload.get(...)` exists.

Observed current malformed roots such as `[]`, `1`, `null`, and `"x"` still produce Python internal errors rather than manifest-specific `ValueError`.

## Goal

Add explicit validation that the top-level manifest JSON payload is an object so malformed roots fail with clear `ValueError` messages.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into general manifest-schema redesign.
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

1. Inspect `ReportManifest.from_path(...)` and identify where non-object root payloads still leak raw Python exceptions.
2. Add explicit validation that the decoded JSON root is an object/mapping before reading `kind`, `schema_version`, or `files`.
3. Raise a clear `ValueError` that identifies the malformed root shape without relying on Python internal exception text.
4. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - list root payload;
   - scalar or null root payload.
5. Preserve current valid-manifest behavior and the recently added `files` shape validation.
6. Only add CLI-level regression coverage if a tiny extra assertion is needed; keep the task helper-focused if existing CLI behavior naturally benefits.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with a non-object JSON root should now raise clear `ValueError` messages instead of raw `AttributeError`.

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

- [ ] Non-object manifest root payload is rejected with clear `ValueError`.
- [ ] Focused tests cover at least one list root and one scalar-or-null root case.
- [ ] Valid manifests still load unchanged.
- [ ] Existing schema-version, file-entry, and `files` shape validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new validation narrowly scoped to the manifest root shape.
- Avoid adding requirements beyond “JSON root must be an object”.
- Keep error messages specific enough for debugging but not coupled to Python internal exception wording.

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
