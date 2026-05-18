# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-FILES-SHAPE-VALIDATION-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

Awaiting Claude Code implementation.

## Scope Summary

- Add explicit loader validation for malformed top-level manifest `files` payloads.
- Reject non-list `files` values with clear `ValueError`.
- Reject non-object items inside `files` with clear `ValueError`.
- Preserve valid-manifest behavior.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation To Run

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

## Constraints

- Do not change valid-manifest behavior.
- Do not modify CLI code unless strictly necessary.
- Do not require new manifest fields beyond the current contract.
- Do not modify forbidden files from the brief.

## Starting Baseline

- Accepted implementation checkpoint: `56253a5 test: add malformed manifest cli regression coverage`
- Current branch: `master`
- Push is not approved.
