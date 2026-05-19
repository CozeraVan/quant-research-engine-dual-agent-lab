# Agent Board

## Current Task ID

QRE-REPORT-AUDIT-JSON-ISSUE-PAYLOAD-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for exact `report-audit --json` issue payload details for missing-file and missing-columns failures. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous `report-files --json --validate-contents` CLI regression task and created local checkpoint `43a17b7`.
2. Next gap: `report-audit --json` has aggregate issue coverage but does not lock exact issue object payload fields for script consumers.
3. Add or strengthen coverage for a missing-file issue object with stable `key`, `code`, `path`, and `message`.
4. Add or strengthen coverage for a missing-columns issue object with stable `key`, `code`, `path`, and `message`.
5. Preserve `report-audit --json` output behavior.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for `report-audit --json` issue payload details.
- Preserve issue object fields and issue counts.
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
