# Coding Handoff

## Task ID

QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001

## Written By

CODEX

## Intended Reviewer

CODEX

## Status

Awaiting Claude Code implementation.

## Scope Summary

- Add explicit validation for a missing top-level `files` field in `ReportManifest.from_path()`.
- Preserve current behavior when `files` is present as an empty list.
- Preserve existing present-but-non-list `files` validation behavior.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py` only if needed for CLI-boundary regression coverage
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

- Accepted implementation checkpoint: `d3eb1d0 Keep malformed manifest entry values from becoming bogus strings`
- Current branch: `master`
- Push is not approved.
