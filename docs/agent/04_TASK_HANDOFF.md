# Task Handoff

## Current Task

Document evaluation artifacts and diagnostics usage.

## Task ID

QRE-DOCS-EVAL-ARTIFACTS-USAGE-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and finalized `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`.
- Local commit created: `ccb80e8`, `Document run manifest audit usage`.
- Codex selected the next unblocked documentation task: evaluation artifacts and diagnostics usage.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`.

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

Last finalized documentation validation:

- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed
- Pytest not required because no runtime code or executable examples changed.

Required validation for this documentation task:

- `scripts/check-progress-docs.sh`
- `git diff --check`
- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` only if code or executable examples are changed

## Known Risks

- Keep examples credential-free.
- Do not edit `docs/legacy/**`.
- Do not imply evaluation diagnostics prove factor or strategy effectiveness.
- Do not document real benchmark or regime features as implemented.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`.
