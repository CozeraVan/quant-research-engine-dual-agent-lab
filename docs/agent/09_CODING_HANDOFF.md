# Coding Handoff

## Task ID

QRE-REPORT-FILES-JSON-CHECK-EXISTS-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage for `report-files --json --check-exists` when matched files exist and when matched files are missing.

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

- Use existing non-JSON `--check-exists` tests and JSON report-files tests as local patterns.
- For the missing-file case, assert stdout still contains JSON with `matched_files == 1` and one file entry.
- Assert stderr contains the resolved missing path and exit code is `2`.
- Keep the task test-only if existing CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `eac50d3 Lock null schema version at the CLI boundary`
- Current task is ready for Claude Code.
- Do not push.
