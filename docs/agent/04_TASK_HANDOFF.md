# Task Handoff

## Current Task

Strengthen `run_manifest` content validation for report audit.

## Task ID

QRE-RUN-MANIFEST-CONTENT-VALIDATION-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and finalized `QRE-RUN-ID-MANIFEST-LINKAGE-001`.
- Local commit created: `1618657`, `Link durable outputs by run id`.
- Codex selected the next unblocked reporting validation task: stricter content validation for run manifests.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation validation:

- `uv run pytest tests/test_cli.py tests/test_portfolio_io.py -q` -> `127 passed, 2 warnings in 2.25s`
- `uv run pytest -q` -> `330 passed, 2 warnings in 3.18s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this task:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Keep `run_id` optional and allow explicit null.
- Do not alter report manifest file-entry schema.
- Preserve existing report-files/report-audit semantics except for stricter malformed run-manifest content issues.
- Do not validate nested strategy semantics or add orchestration behavior.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`.
