# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-CLI-SCHEMA-VERSION-NULL-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

New brief ready. Implement CLI regression coverage for explicit top-level `schema_version: null` across `report-files --json` and `report-audit --json`. Keep it test-only unless existing behavior is broken.

## Implementation Summary

1. Codex accepted the previous explicit `null` optional metadata CLI regression task and created local checkpoint `cce750d`.
2. Next gap: explicit top-level `schema_version: null` is accepted by current loader semantics but lacks direct CLI regression coverage.
3. Add a `report-files --json` test for explicit `schema_version: null`.
4. Add a `report-audit --json` test for explicit `schema_version: null`; create the referenced file so audit status is `ok`.
5. Assert both JSON payloads report `schema_version` as `null`.
6. Update `04`, `05`, `09`, `11`, and `12` after implementation.

## Constraints Check

- Preserve valid-manifest CLI behavior.
- Scope changes to CLI regression coverage for explicit `schema_version: null`.
- Preserve current schema-version validation semantics.
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
