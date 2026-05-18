# Task Handoff

## Current Task

Validate top-level manifest `files` presence explicitly.

## Task ID

QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-ENTRY-TYPE-VALIDATION-001`.
- Local checkpoint created: `d3eb1d0 Keep malformed manifest entry values from becoming bogus strings`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.
- Next task selected: explicit top-level manifest `files` presence validation.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-FILES-PRESENCE-VALIDATION-001`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py` only if needed for command-boundary regression coverage

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `23 passed in 0.05s`
- Last accepted full validation: `uv run pytest -q` -> `200 passed in 2.21s`
- `scripts/check-progress-docs.sh` -> passed
- `scripts/git-finalize-check.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to top-level `files` presence only.
- Preserve valid-manifest behavior when `files` is present and a list.
- Preserve the existing `files` list-shape validation path.

## Next Suggested Step

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the validation, run the required checks, and hand back for Codex review.
