# Coding Handoff

## Task ID

QRE-REPORT-FILES-JSON-VALIDATE-CONTENTS-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage for `report-files --json --validate-contents` when matched files are valid and when matched files have structural validation issues.

## Files To Change

Expected:

- `tests/test_cli.py`

Update after implementation:

- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Do not change production code unless the new tests expose a real command-boundary bug.

## Validation Required

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Handoff Notes

- Use existing non-JSON `--validate-contents` tests and JSON report-files tests as local patterns.
- For the validation-failure case, assert stdout still contains JSON with `matched_files == 1` and one file entry.
- Assert stderr contains the report key, `missing_columns`, the resolved path, and the missing column name.
- Keep the task test-only if existing CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `ff3732e Lock report-files JSON check-exists behavior`
- Current task is ready for Claude Code.
- Do not push.
