# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-CLI-MALFORMED-ROOT-REGRESSION-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

Awaiting Claude Code implementation.

## Scope Summary

- Add CLI regression coverage so `report-files` and `report-audit` both surface invalid JSON and non-object manifest roots with exit code 2 and clear stderr.
- Preserve existing CLI exit-code and stderr behavior for valid and previously-tested invalid manifests.

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

- Accepted implementation checkpoint: `75b42bc Lock manifest type failures at the CLI boundary`
- Current branch: `master`
- Push is not approved.
