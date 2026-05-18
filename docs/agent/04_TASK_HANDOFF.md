# Task Handoff

## Current Task

Harden top-level report manifest `files` shape validation.

## Task ID

QRE-REPORT-MANIFEST-FILES-SHAPE-VALIDATION-001

## Current Status

Brief prepared by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-CLI-INVALID-MANIFEST-001`.
- Local checkpoint created: `56253a5 test: add malformed manifest cli regression coverage`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-FILES-SHAPE-VALIDATION-001` from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`

## Validation Baseline

- Last accepted focused CLI validation: `uv run pytest tests/test_cli.py -q` -> `57 passed in 0.91s`
- Last accepted full validation: `uv run pytest -q` -> `189 passed in 1.88s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Preserve current absent-field compatibility if it is not necessary to tighten it for this task.
- Keep the implementation scoped to loader validation rather than broader manifest or CLI refactors.

## Next Suggested Step

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the validation, run the required checks, and hand back for Codex review.
