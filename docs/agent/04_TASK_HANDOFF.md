# Task Handoff

## Current Task

Add metadata group summaries to evaluation results.

## Task ID

QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-PORTFOLIO-BACKTEST-RUN-MANIFEST-REGRESSION-001`.
- Codex created local checkpoint `dea224a` for the completed run-manifest task.
- Codex selected the next self-contained roadmap item from M3.5: evaluation metadata group summaries.
- Codex wrote the new implementation brief in `08_IMPLEMENTATION_BRIEF.md`.

## In Progress

- Claude Code should implement `QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001` from `08_IMPLEMENTATION_BRIEF.md`.

## Expected Files

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- Previous accepted full suite: `uv run pytest -q` -> `246 passed in 2.37s`
- Previous accepted docs/checks: `scripts/check-progress-docs.sh`, `git diff --check`, and `scripts/git-finalize-check.sh` passed before local checkpoint `dea224a`.
- New task focused validation should include:
  - `uv run pytest tests/test_evaluation_forward_returns.py -q`
  - `uv run pytest tests/test_cli.py -q`
  - `uv run pytest -q`
  - `scripts/check-progress-docs.sh`
  - `git diff --check`

## Known Risks

- Grouping must be additive; default evaluation behavior should not change.
- Group labels must come from the current event row only.
- Missing group columns should produce a clear error instead of silent empty output.
- No new data-source wiring is expected in this task.

## Next Suggested Step

Claude Code should read `08`, `11`, and `12`, then implement the current Claude Code task.
