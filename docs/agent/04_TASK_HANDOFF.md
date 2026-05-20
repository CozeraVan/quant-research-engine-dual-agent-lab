# Task Handoff

## Current Task

Add optional run-level identifiers to preflight, evaluation, and portfolio durable outputs.

## Task ID

QRE-RUN-ID-MANIFEST-LINKAGE-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and finalized `QRE-EVAL-FACTOR-DECAY-SUMMARY-001`.
- Local commit created: `8b0e924`, `Summarize evaluation factor decay`.
- Codex selected the next unblocked reproducibility task: run-level manifest linkage through optional `--run-id`.
- Codex prepared `08_IMPLEMENTATION_BRIEF.md` for `QRE-RUN-ID-MANIFEST-LINKAGE-001`.

## Expected Files

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/io.py`
- `tests/test_cli.py`
- `tests/test_portfolio_io.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

Last finalized implementation validation:

- `uv run pytest tests/test_evaluation_forward_returns.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q` -> `164 passed, 2 warnings in 1.76s`
- `uv run pytest -q` -> `324 passed, 2 warnings in 3.05s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed

Required validation for this task:

- `uv run pytest tests/test_cli.py tests/test_portfolio_io.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Known Risks

- Keep `run_id` optional and metadata-only.
- Do not add a new orchestrator command or database writes.
- Do not alter report manifest file-entry schema.
- Preserve existing command behavior when `--run-id` is omitted.

## Next Suggested Step

Claude Code should read `11_AGENT_STATE.md`, `12_AGENT_BOARD.md`, and `08_IMPLEMENTATION_BRIEF.md`, then implement `QRE-RUN-ID-MANIFEST-LINKAGE-001`.
