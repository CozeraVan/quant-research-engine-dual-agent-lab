# Task Handoff

## Current Task

Make top-level manifest `kind` validation explicit.

## Task ID

QRE-REPORT-MANIFEST-KIND-VALIDATION-001

## Current Status

Planned by Codex. Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001`.
- Local checkpoint created: `333f46d feat: normalize invalid report manifest json errors`.
- Next low-risk follow-up task selected from the ongoing report-manifest robustness track.
- Next task selected: explicit top-level manifest `kind` validation.

## In Progress

Claude Code should implement `QRE-REPORT-MANIFEST-KIND-VALIDATION-001`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`

## Validation Baseline

- Last accepted focused validation: `uv run pytest tests/test_portfolio_report_manifest.py -q` -> `18 passed in 0.04s`
- Last accepted full validation: `uv run pytest -q` -> `195 passed in 1.85s`
- `scripts/check-progress-docs.sh` -> passed
- `scripts/git-finalize-check.sh` -> passed
- `git diff --check` -> passed

## Known Risks

- Keep the implementation scoped to top-level `kind` validation only.
- Preserve supported-kind handling for unsupported strings.
- Preserve invalid-JSON, root-shape, `files`-shape, and valid-manifest behavior.

## Next Suggested Step

Claude Code should read `docs/agent/08_IMPLEMENTATION_BRIEF.md` and `docs/agent/12_AGENT_BOARD.md`, implement the validation, run the required checks, and hand back for Codex review.
