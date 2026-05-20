# Task Handoff

## Current Task

Document evaluation group-by manifest parity usage.

## Task ID

QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001

## Current Status

Claude Code implementation complete. Ready for Codex review.

## Current Owner

CODEX

## Completed

- Codex finalized `QRE-EVAL-GROUP-BY-MANIFEST-PARITY-001` locally.
- Local commit created: `745103e`, `Align evaluation grouped artifact filtering`.
- Codex selected the next unblocked documentation task: evaluation group-by manifest parity usage.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001`.
- Claude Code updated README, data_layer.md, and portfolio_workflow.md with per-column evaluation grouped artifact docs, manifest `group_by` metadata behavior, and `--group-by` discovery/audit examples.

## Expected Files

- `README.md`
- `docs/modules/data_layer.md`
- `docs/modules/portfolio_workflow.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation validation:

- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` -> 164 passed
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed
- Local commit: `745103e`
- Pytest not required for the next task unless executable examples or runtime code are changed.

## Known Risks

- Keep examples credential-free.
- Do not edit `docs/legacy/**`.
- Do not imply grouped diagnostics prove factor or strategy effectiveness.
- Do not describe per-column grouped files as replacing the combined `group_summary.csv`.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001`.
