# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-TOPLEVEL-FIELDS-REGRESSION-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

Awaiting Claude Code implementation.

## Scope Summary

- Add CLI regression coverage for missing top-level manifest `kind` and `files`.
- Preserve existing CLI exit-code and stderr behavior for invalid manifests.
- Preserve valid-manifest CLI behavior.

## Expected Files

- `tests/test_cli.py`
- `src/**` only if a tiny bugfix is strictly necessary
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation To Run

```bash
uv run pytest tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Constraints

- Do not change valid-manifest behavior.
- Do not modify CLI code unless strictly necessary.
- Do not modify forbidden files from the brief.
- Do not push.

## Starting Baseline

- Accepted implementation checkpoint: `53f9aba Keep missing manifest files distinct from empty manifests`
- Current branch: `master`
- Push is not approved.
