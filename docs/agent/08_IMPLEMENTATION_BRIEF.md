# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-FILES-SHAPE-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest validation now covers supported `schema_version` values and required file entry fields. One malformed-manifest gap remains nearby: top-level payloads such as `"files": {}` or `files: [1]` still fail with raw `AttributeError` or `TypeError` instead of clear manifest-specific `ValueError` messages.

This is a small, low-risk follow-up in the same report-manifest robustness area from Milestone 5. It should stay tightly scoped to manifest loader shape validation.

## Goal

Add explicit validation for the top-level manifest `files` collection shape so malformed payloads fail with clear `ValueError` messages.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into general manifest-schema redesign.
- Do not newly require the top-level `files` key if current absent-field behavior can be preserved safely.

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

1. Inspect `ReportManifest.from_path(...)` and identify where raw exceptions still escape for malformed top-level `files` payloads.
2. Add explicit validation that the top-level `files` payload is a list when present.
3. Add explicit validation that each item in `files` is a mapping/object before calling `ReportFile.from_mapping(...)`.
4. Raise clear `ValueError` messages that identify the malformed shape without relying on Python internal exception text.
5. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - non-list `files`;
   - non-object entry inside `files`.
6. Only add CLI-level regression coverage if a tiny extra assertion is needed; keep the task as helper-focused if existing CLI behavior naturally benefits from the clearer loader errors.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with incorrect top-level `files` shape should now raise clear `ValueError` messages instead of raw `AttributeError` or `TypeError`.

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

- [ ] Non-list top-level `files` payload is rejected with clear `ValueError`.
- [ ] Non-object `files` entry is rejected with clear `ValueError`.
- [ ] Valid manifests still load unchanged.
- [ ] Existing schema-version and required-field validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid turning absent or legacy-compatible fields into new hard requirements unless the brief explicitly needs that behavior change.
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
