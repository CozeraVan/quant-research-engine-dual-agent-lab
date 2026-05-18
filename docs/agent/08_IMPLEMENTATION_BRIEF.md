# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-KIND-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation now covers invalid JSON text, root payload shape, top-level `files` shape, required file entry fields, and supported `schema_version`. One nearby hardening gap remains at the top-level `kind` field: missing or non-string `kind` values currently fall through the generic supported-kind check instead of failing with a clearer manifest-specific validation error.

## Goal

Make top-level manifest `kind` validation explicit for missing or non-string values while preserving current behavior for valid manifests and unsupported string kinds.

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

1. Inspect `ReportManifest.from_path(...)` around `kind = payload.get("kind")` and the supported-kind membership check.
2. Add explicit validation for a missing top-level `kind`.
3. Add explicit validation for non-string `kind` values such as numbers, lists, or `null`.
4. Preserve the current rejection path for unsupported string `kind` values.
5. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - missing `kind`;
   - non-string `kind`;
   - an unsupported string `kind`, to confirm current behavior is preserved.
6. Keep the task helper-focused; do not modify CLI code unless a tiny extra assertion is strictly necessary.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with missing or non-string top-level `kind` should now raise clear `ValueError` messages instead of falling through the generic supported-kind check.

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

- [ ] Missing top-level `kind` is rejected with clear `ValueError`.
- [ ] Non-string top-level `kind` is rejected with clear `ValueError`.
- [ ] Unsupported string `kind` values are still rejected.
- [ ] Valid manifests still load unchanged.
- [ ] Existing invalid-JSON, root, `files`, schema-version, and file-entry validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new validation narrowly scoped to the top-level `kind` field.
- Do not weaken the existing supported-kind list or its error path for unsupported strings.
- Do not let the new check disturb the recently added invalid-JSON and shape validation.

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
