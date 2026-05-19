# Agent Board

## Current Task ID

QRE-REPORT-FILES-JSON-VALIDATE-CONTENTS-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for `report-files --json --validate-contents` when matched files are valid and when matched files have structural validation issues. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous `report-files --json --check-exists` CLI regression task and created local checkpoint `ff3732e`.
2. Next gap: non-JSON `report-files --validate-contents` is covered, but JSON mode with `--validate-contents` lacks direct regression coverage.
3. Add a passing `report-files --json --validate-contents` test when matched files are structurally valid.
4. Add a validation-failure `report-files --json --validate-contents` test that asserts exit code `2`, normal JSON stdout, and validation issue stderr.
5. Preserve stdout/stderr behavior and output ordering.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for `report-files --json --validate-contents`.
- Preserve validation-issue stderr and JSON stdout behavior.
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
