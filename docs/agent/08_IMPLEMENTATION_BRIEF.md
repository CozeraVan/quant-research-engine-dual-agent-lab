# Implementation Brief

## Task ID

QRE-REPORT-FILES-JSON-001

## Created By

CODEX

## Intended Implementer

CLAUDE_CODE

## Background

`qre report-audit --json` now provides machine-readable audit output. `qre report-files` still prints paths or keys as plain text only. Adding JSON output to `report-files` completes the small reporting CLI machine-readability pair without changing default behavior.

## Goal

Add an opt-in JSON output mode to `qre report-files` that emits matched manifest entries and resolved paths in a machine-readable object.

## Non-Goals

- Do not change default `report-files` text output.
- Do not change `report-audit` behavior.
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

- Preserve default `report-files` behavior when JSON mode is not requested.
- Preserve `report-files --require-match` semantics and exit codes.
- Preserve manifest discovery and filtering semantics.
- No database writes or credential handling.

## Implementation Steps

1. Inspect current `report-files` CLI handling and tests.
2. Add an opt-in JSON flag to `report-files`. Prefer:
   - `--json`
3. When `--json` is set, print one JSON object to stdout with at least:
   - `manifest_kind`
   - `matched_files`
   - `files`
4. Each item in `files` should include at least:
   - `key`
   - `path`
   - `filename`
   - `role`
   - optional manifest metadata when present, such as `symbol`, `window`, and `group_by`
5. Preserve `--keys` behavior in non-JSON mode. In JSON mode, prefer the full `files` object output even if `--keys` is passed, or reject the combination clearly; document the chosen behavior in tests and handoff.
6. Preserve existing `--check-exists`, `--validate-contents`, and `--require-match` semantics and exit codes.
7. Add CLI tests:
   - JSON output for matched entries includes expected fields and resolved path;
   - JSON output for zero matches without `--require-match` exits `0` with `matched_files = 0`;
   - `--json --require-match` zero-match exits `2` and emits a JSON object suitable for scripts, or preserves existing stderr behavior if that is simpler and documented.
8. Update handoff/progress/state/board docs after implementation.

## Data / Schema Changes

None.

## API / Interface Changes

Allowed:

- Add optional CLI flag:
  - `qre report-files MANIFEST --json`

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

- [ ] `qre report-files --json` emits valid JSON on stdout.
- [ ] JSON output includes matched count and file entries.
- [ ] Default text output remains compatible with existing tests.
- [ ] Existing `--require-match`, `--check-exists`, and `--validate-contents` semantics are preserved.
- [ ] Focused and full tests pass, or unavailable checks are documented.
- [ ] `09_CODING_HANDOFF.md` records changed files, validation, risks, and git status.

## Risks

- Avoid mixing human text into stdout in JSON mode.
- Be explicit about `--keys` interaction with `--json`.

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
