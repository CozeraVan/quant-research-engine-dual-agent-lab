# Agent Board

## Current Task ID

QRE-REPORT-FILES-JSON-CHECK-EXISTS-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for `report-files --json --check-exists` when matched files exist and when matched files are missing. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous explicit `schema_version: null` CLI regression task and created local checkpoint `eac50d3`.
2. Next gap: non-JSON `report-files --check-exists` is covered, but JSON mode with `--check-exists` lacks direct regression coverage.
3. Add a passing `report-files --json --check-exists` test when matched files exist.
4. Add a missing-file `report-files --json --check-exists` test that asserts exit code `2`, normal JSON stdout, and missing-path stderr.
5. Preserve stdout/stderr behavior and output ordering.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for `report-files --json --check-exists`.
- Preserve missing-path stderr and JSON stdout behavior.
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
