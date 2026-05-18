# Implementation Brief

## Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Manifest loader validation now covers supported `schema_version`, required file entry fields, top-level `files` shape, and root payload shape. One nearby malformed-manifest gap remains: invalid JSON text still leaks raw `JSONDecodeError` from `json.loads()` instead of producing a manifest-specific `ValueError`.

Observed current malformed text such as `"{"`, `"{"kind":"`, or `"not-json"` still produces raw JSON parser errors.

## Goal

Normalize invalid manifest JSON parse failures into clear manifest-specific `ValueError` messages.

## Non-Goals

- Do not change valid-manifest behavior.
- Do not change CLI flags or normal CLI output for valid manifests.
- Do not change report writer output.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not broaden this into general exception-wrapping beyond manifest JSON parsing.
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

1. Inspect `ReportManifest.from_path(...)` and identify the current raw `JSONDecodeError` path from `json.loads()`.
2. Wrap only manifest JSON parse failures and raise a clear `ValueError` that indicates invalid manifest JSON.
3. Keep the message stable enough for tests while still including enough context to debug malformed text.
4. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least:
   - malformed JSON object text such as `"{"`;
   - malformed scalar text such as `"not-json"` or an incomplete object.
5. Preserve current valid-manifest behavior and all recently added shape validation.
6. Only add CLI-level regression coverage if a tiny extra assertion is needed; keep the task helper-focused if existing CLI behavior naturally benefits.
7. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None. This task tightens loader validation only.

## API / Interface Changes

Valid manifests should remain unchanged.

Malformed manifests with invalid JSON text should now raise clear `ValueError` messages instead of raw `JSONDecodeError`.

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

- [ ] Invalid manifest JSON text is rejected with clear `ValueError`.
- [ ] Focused tests cover at least two malformed JSON text cases.
- [ ] Valid manifests still load unchanged.
- [ ] Existing root, `files`, schema-version, and file-entry validation behavior is preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Keep the new wrapping narrowly scoped to JSON parsing only.
- Avoid obscuring too much parser context; the message should still help debug malformed text.
- Do not let the new code swallow unrelated loader errors.

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
