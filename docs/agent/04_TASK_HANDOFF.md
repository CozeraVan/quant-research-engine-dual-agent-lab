# Task Handoff

## Current Task

Normalize invalid manifest JSON parse failures.

## Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Current Status

Brief prepared by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-ROOT-SHAPE-VALIDATION-001`.
- Local checkpoint created: `950c814 feat: validate manifest root payload shape`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001` from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `16 passed in 0.04s`
- Last accepted full validation: `uv run pytest -q` -> `193 passed in 1.78s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to JSON parse failure normalization only.
- Preserve root-shape, `files`-shape, and valid-manifest behavior.

## Next Suggested Step

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the validation, run the required checks, and hand back for Codex review.
