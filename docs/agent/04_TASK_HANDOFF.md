# Task Handoff

## Current Task

Normalize invalid manifest JSON parse failures.

## Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Current Status

Review passed. Ready for local checkpoint.

## Current Owner

CODEX

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-ROOT-SHAPE-VALIDATION-001`.
- Local checkpoint created: `950c814 feat: validate manifest root payload shape`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.
- Claude Code implemented invalid JSON normalization in `ReportManifest.from_path()`.
- Focused tests added for incomplete JSON object and non-JSON text.
- Codex review passed with no Required Fixes.

## In Progress

Codex should create the local checkpoint commit for `QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `18 passed in 0.05s`
- Last accepted full validation: `uv run pytest -q` -> `195 passed in 1.77s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to JSON parse failure normalization only.
- Preserve root-shape, `files`-shape, and valid-manifest behavior.

## Next Suggested Step

Codex should commit the accepted implementation locally, then prepare the next manifest-loader hardening brief for Claude Code.
