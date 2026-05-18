# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation now covers invalid JSON text, root payload shape, top-level `files` shape, required file entry presence, supported `schema_version`, top-level `kind`, and file-entry field types. One nearby hardening gap remains in `ReportManifest.from_path(...)`: missing top-level `files` currently falls through `payload.get("files", [])` and is treated like an empty manifest instead of failing with a clear manifest-specific validation error.

## Goal

Make top-level manifest `files` presence validation explicit while preserving current behavior for valid manifests that already provide `files`.

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

1. Inspect `ReportManifest.from_path(...)` around `raw_files = payload.get("files", [])` and nearby manifest-loader tests.
2. Add explicit validation for a missing top-level `files` field.
3. Preserve the existing validation path for present-but-non-list `files` values.
4. Preserve current behavior when `files` is present as an empty list.
5. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - missing top-level `files`;
   - present empty-list `files`;
   - present non-list `files`, to confirm existing behavior is preserved.
6. Add CLI regression coverage in `tests/test_cli.py` only if it is needed to lock down command-boundary propagation of the loader error.
7. Keep the task helper-focused; do not modify report writer code or file-entry validation logic unless strictly necessary.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with a missing top-level `files` field should now raise a clear `ValueError` instead of being silently treated as empty manifests.

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

- [ ] Missing top-level `files` is rejected with clear `ValueError`.
- [ ] Present empty-list `files` still loads unchanged.
- [ ] Existing present-but-non-list `files` validation remains intact.
- [ ] Valid manifests still load unchanged.
- [ ] Existing invalid-JSON, root, `kind`, schema-version, file-entry presence, and file-entry type validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new validation narrowly scoped to top-level `files` presence.
- Do not reject present empty-list `files` manifests if they are currently supported.
- Do not let the new check disturb the recently added invalid-JSON, root, `kind`, file-entry, or schema-version validation.

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
