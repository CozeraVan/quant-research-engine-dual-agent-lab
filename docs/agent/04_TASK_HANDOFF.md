# Task Handoff

## Current Task

Document run-ID linkage and run-manifest audit usage.

## Task ID

QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and finalized `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`.
- Local commit created: `983ca1b`, `Validate run manifests in report audit`.
- Codex selected the next unblocked documentation task: update README/module docs for `--run-id` and run-manifest audit usage.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`.

## Expected Files

- `README.md`
- `docs/modules/portfolio_workflow.md`
- `docs/modules/portfolio_layer.md`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation validation:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `158 passed, 2 warnings in 1.78s`
- `uv run pytest -q` -> `346 passed, 2 warnings in 3.30s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this documentation task:

- `scripts/check-progress-docs.sh`
- `git diff --check`
- `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` only if code or executable examples are changed

## Known Risks

- Keep examples credential-free.
- Do not edit `docs/legacy/**`.
- Do not imply run-ID linkage is a full orchestrator or transactional workflow.
- Do not describe audit as proving factor or strategy effectiveness.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-DOCS-RUN-MANIFEST-AUDIT-USAGE-001`.
