# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-SCHEMA-VERSION-NULL-REGRESSION-001

## Written By

CODEX

## Intended Implementer

CLAUDE_CODE

## Status

Ready for Claude Code implementation.

## Scope Summary

Add CLI regression coverage so `report-files --json` and `report-audit --json` both accept explicit top-level `schema_version: null` and report `schema_version` as JSON `null`.

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

- Use the existing `report-files --json` and `report-audit --json` schema-version tests as local patterns.
- For `report-audit --json`, create the referenced file so the audit can return `status: ok`.
- Preserve current schema-version validation semantics.
- Keep the task test-only if existing loader/CLI behavior already passes.

## Git State

- Branch: `master`
- Last accepted implementation commit: `cce750d Lock optional null manifest metadata at the CLI boundary`
- Current task is ready for Claude Code.
- Do not push.
