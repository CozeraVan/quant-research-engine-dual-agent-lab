# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

Awaiting Claude Code implementation.

## Scope Summary

- Normalize invalid manifest JSON parse failures into manifest-specific `ValueError`.
- Add focused malformed-JSON tests.
- Preserve valid-manifest behavior and recent shape validation.

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
- Do not modify forbidden files from the brief.
- Do not push.

## Starting Baseline

- Accepted implementation checkpoint: `950c814 feat: validate manifest root payload shape`
- Current branch: `master`
- Push is not approved.
