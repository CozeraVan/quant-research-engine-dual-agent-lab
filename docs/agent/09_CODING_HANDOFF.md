# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-GROUP-BY-TYPE-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage so `report-files` and `report-audit` both surface non-string optional file-entry `group_by` metadata with exit code `2` and clear stderr.

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

- Use the existing optional `symbol` and `window` malformed-manifest CLI tests as the local pattern.
- Expected stderr substring: `manifest file entry field 'group_by' must be a string or null`.
- Preserve exit code `2` for malformed manifests.
- Keep the task test-only if existing loader/CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `a4693ab Lock optional manifest entry type failures at the CLI boundary`
- Current task is ready for Claude Code.
- Do not push.
