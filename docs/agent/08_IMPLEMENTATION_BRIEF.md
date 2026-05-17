# Implementation Brief

## Task ID

QRE-REPORT-AUDIT-JSON-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-audit` currently prints a concise text summary and issue lines. This is useful for humans, but scripts need stable machine-readable output to gate larger research workflows.

The next low-risk reporting task is to add an opt-in JSON output mode for `report-audit` without changing the existing default text behavior.

## Goal

Add a JSON output option to `qre report-audit` that emits the audit summary and validation details in a machine-readable object.

## Non-Goals

- Do not change default `report-audit` text output.
- Do not change `report-files` behavior.
- Do not change manifest JSON shape.
- Do not change report artifact generation.
- Do not change portfolio simulation behavior.
- Do not add database access.
- Do not modify old root progress docs.

## Affected Modules

Expected:

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`

Docs/handoff:

- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Files Likely to Change

- `src/quant_research_engine/apps/cli.py`
- `tests/test_cli.py`
- agent handoff docs listed above

## Forbidden Files

- `uv.lock`
- `pyproject.toml`
- database credentials or `.env*`
- upstream data producer projects
- old root progress docs unless separately requested

## Locked Requirements

Read:

- `docs/agent/02_LOCKED_REQUIREMENTS.md`

Task-specific locked requirements:

- Preserve default `report-audit` behavior when JSON mode is not requested.
- Preserve `report-audit --require-match` semantics and exit codes.
- Preserve manifest discovery and filtering semantics.
- No database writes or credential handling.

## Implementation Steps

1. Inspect current `report-audit` CLI handling and tests.
2. Add an opt-in JSON flag to `report-audit`. Prefer:
   - `--json`
3. When `--json` is set, print one JSON object to stdout with at least:
   - `manifest_kind`
   - `matched_files`
   - `missing_files`
   - `validation_issues`
   - `status`
   - `issues`
4. `issues` should be a list of objects with at least:
   - `key`
   - `code`
   - `path`
   - `message`
5. In JSON mode, keep stderr behavior for fatal parse/load errors. For normal audit failures, prefer JSON on stdout and no stderr unless `--require-match` has zero matches; if preserving the existing stderr message for zero-match is simpler, document it in handoff and tests.
6. Preserve existing text output exactly enough that current tests still pass.
7. Add CLI tests:
   - valid manifest JSON output exits `0` and includes expected fields;
   - malformed/missing report artifact JSON output exits `2` and includes issue objects;
   - `--json --require-match` zero-match behavior is covered.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None.

## API / Interface Changes

Allowed:

- Add optional CLI flag:
  - `qre report-audit MANIFEST --json`

Avoid:

- Changing default text output.
- Changing existing flags or positional arguments.
- Changing manifest JSON shape.

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

- [ ] `qre report-audit --json` emits valid JSON on stdout.
- [ ] JSON output includes summary counts, status, and issue details.
- [ ] Default text output remains compatible with existing tests.
- [ ] Existing `--require-match` semantics and exit codes are preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- JSON output should be stable enough for scripts, so avoid informal string-only payloads.
- Do not mix human text into stdout in JSON mode.

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
