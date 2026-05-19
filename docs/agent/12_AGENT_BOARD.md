# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-CLI-OPTIONAL-NULL-METADATA-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for explicit `null` optional metadata across `report-files --json` and `report-audit --json`. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous optional `group_by` CLI regression task and created local checkpoint `0083c82`.
2. Next gap: the loader accepts optional `symbol`, `window`, and `group_by` when explicitly set to JSON `null`, but that valid command-boundary path lacks direct CLI regression coverage.
3. Add a `report-files --json` test for explicit `null` optional `symbol`, `window`, and `group_by`.
4. Add a `report-audit --json` test for explicit `null` optional `symbol`, `window`, and `group_by`; create the referenced file so audit status is `ok`.
5. Preserve current JSON serialization behavior for optional metadata whose value resolves to `None`.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for explicit `null` optional metadata.
- Preserve current JSON serialization behavior for optional metadata whose value is `None`.
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
