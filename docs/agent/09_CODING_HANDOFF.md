# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage so `report-files --json` and `report-audit --json` both accept explicit `null` optional file-entry metadata for `symbol`, `window`, and `group_by`.

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

- Use the existing `report-files --json` optional metadata test and malformed optional metadata tests as local patterns.
- For `report-audit --json`, create the referenced file so the audit can return `status: ok`.
- Preserve current JSON serialization behavior for optional metadata whose value resolves to `None`.
- Keep the task test-only if existing loader/CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `0083c82 Lock optional group-by manifest type failures at the CLI boundary`
- Current task is ready for Claude Code.
- Do not push.
