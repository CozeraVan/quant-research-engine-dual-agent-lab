# Implementation Brief

## Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

Report manifests can discover and audit emitted artifacts. CSV roles already have required-column validation, and JSON summary/run-manifest entries are currently checked only for being JSON objects. After adding optional `run_id` linkage to durable outputs, run manifests should have a small content-level validation contract so `report-audit --validate-contents --role run_manifest` can catch malformed or incomplete run metadata.

## Goal

Strengthen `run_manifest` content validation in `ReportManifest.validate_contents()` while preserving existing report discovery and audit behavior.

## Non-Goals

- Do not change run-manifest filenames or report-manifest file-entry schema.
- Do not change preflight, evaluation, or portfolio math.
- Do not require a non-null `run_id`; explicit null remains valid.
- Do not add a new orchestrator command or database writes.
- Do not wire real benchmark tables or real regime classification.

## Affected Modules

Expected:

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Update only additional files if the current code shape clearly requires it.

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- `.env*`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve `report-files` and `report-audit` command semantics.
- Keep `run_id` optional and allow explicit null.
- Keep validation errors structured through existing `ReportValidationIssue`.
- Do not expose secrets or environment values.

## Implementation Steps

1. Inspect `ReportManifest.validate_contents()`, `_validate_json_object()`, and existing run-manifest tests.
2. Add role-specific validation for JSON entries with `role == "run_manifest"`.
3. Preserve generic JSON-object validation for `role == "summary"`.
4. For run manifests, validate at least these top-level fields:
   - `schema_version`
   - `kind`
   - `run_id`
   - `command`
   - `strategy_path`
   - `artifacts`
5. Required field type expectations:
   - `schema_version`: integer `1`
   - `kind`: string
   - `run_id`: string or null
   - `command`: string
   - `strategy_path`: string
   - `artifacts`: list of strings
6. Permit portfolio and evaluation run-manifest kinds:
   - `portfolio_backtest_run_manifest`
   - `evaluation_run_manifest`
7. Report missing fields and type errors as `ReportValidationIssue` entries with stable codes. Suggested codes:
   - `missing_run_manifest_field`
   - `invalid_run_manifest_field`
8. Add focused tests in `tests/test_portfolio_report_manifest.py` covering valid run manifest, missing field, invalid `run_id`, invalid artifacts shape, and unsupported run-manifest kind.
9. Add or update a CLI regression test proving `report-audit --validate-contents --role run_manifest` returns failure and includes the structured issue when a run manifest is malformed.
10. Update handoff and progress docs.

## Data / Schema Changes

- No database schema changes.
- Report manifest file-entry schema remains unchanged.
- Run-manifest validation contract becomes stricter for audit operations.

## API / Interface Changes

- `ReportManifest.validate_contents(role="run_manifest")` returns structured issues for malformed run manifests instead of only checking JSON object shape.
- `qre report-audit --validate-contents --role run_manifest` can now fail on missing/invalid run-manifest fields.

## Validation Plan

Run focused tests:

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
```

Run full checks:

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Acceptance Criteria

- [ ] Valid evaluation and portfolio run manifests pass `validate_contents(role="run_manifest")`.
- [ ] Missing required run-manifest fields produce structured issues.
- [ ] Invalid `run_id` type produces a structured issue while null remains valid.
- [ ] Invalid `artifacts` payloads produce structured issues.
- [ ] Unsupported run-manifest `kind` produces a structured issue.
- [ ] Summary JSON validation remains unchanged.
- [ ] `report-audit --validate-contents --role run_manifest` reports malformed run manifests through existing CLI issue output.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git state.

## Risks

- Avoid rejecting existing valid manifests with `run_id: null`.
- Keep the validation contract minimal and run-level; do not validate nested strategy semantics.
- Preserve existing issue payload shape used by JSON audit output.

## Instructions for Claude Code

Claude Code must:

1. Follow this brief strictly.
2. Keep the implementation focused on validation.
3. Preserve existing report discovery/audit behavior except for the new malformed-run-manifest issues.
4. Update `04`, `05`, `09`, `11`, and `12` after implementation.
5. Stop and write a blocker only if this brief conflicts with current code.

## Next Agent State

- Phase: `CLAUDE_IMPLEMENTING`
- Owner: `CLAUDE_CODE`
