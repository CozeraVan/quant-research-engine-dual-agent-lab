# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-GROUP-BY-TYPE-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for non-string optional `group_by` file-entry metadata across `report-files` and `report-audit`. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous optional `symbol`/`window` CLI regression task and created local checkpoint `a4693ab`.
2. Next gap: optional `group_by` uses the same loader validation path but lacks direct CLI command-boundary regression coverage.
3. Add a `report-files` test for non-string optional `group_by`.
4. Add a `report-audit` test for non-string optional `group_by`.
5. Assert exit code `2` and stderr containing `manifest file entry field 'group_by' must be a string or null`.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for optional `group_by` type errors.
- Preserve malformed-manifest exit code `2` and stderr behavior.
- Do not modify forbidden files.
- Do not push.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
