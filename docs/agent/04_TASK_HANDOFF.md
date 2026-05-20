# Task Handoff

## Current Task

Document evaluation artifacts and diagnostics usage.

## Task ID

QRE-DOCS-EVAL-ARTIFACTS-USAGE-001

## Current Status

Accepted locally by Codex review. Ready for local git finalization.

## Current Owner

CODEX

## Completed

- Codex reviewed and finalized `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`.
- Local commit created: `ccb80e8`, `Document run manifest audit usage`.
- Codex selected the next unblocked documentation task: evaluation artifacts and diagnostics usage.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`.
- Claude Code updated README.md, docs/modules/data_layer.md, and docs/modules/portfolio_workflow.md with evaluation artifact roles, output-dir examples, factor decay derivation, and random baseline determinism.
- Codex review found a required documentation accuracy fix: two module docs describe factor decay as "decay ratios", but the implemented metric is a signed difference from the base horizon, not a ratio.
- Claude Code replaced inaccurate "decay ratios" wording with "signed difference from base" in both files.
- Codex re-reviewed the fix and marked `10_REVIEW_REPORT.md` as PASS.

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

Codex should run final git checks and create the local completion commit for `QRE-DOCS-EVAL-ARTIFACTS-USAGE-001`.
