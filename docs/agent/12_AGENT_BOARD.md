# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

Harden `ReportManifest.from_path()` so a missing top-level `files` field fails clearly instead of silently becoming an empty manifest. Present empty-list `files` should keep their current behavior, and present non-list `files` should keep the existing rejection path.

## Implementation Summary

1. Inspect `ReportManifest.from_path(...)` around `raw_files = payload.get("files", [])`.
2. Add explicit validation for a missing top-level `files` field.
3. Preserve the current validation path for present-but-non-list `files`.
4. Preserve current behavior when `files` is present as an empty list.
5. Add focused tests in `tests/test_portfolio_report_manifest.py`; add CLI regression only if needed.
6. Update `04`, `05`, `09`, `11`, and `12`.

## Constraints Check

- No CLI/reporting behavior changes for valid manifests.
- Scoped only to top-level `files` presence validation.
- Preserve present empty-list behavior and existing non-list rejection.
- No forbidden files modified.
- Not pushed.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py` only if needed for CLI-boundary regression coverage
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
