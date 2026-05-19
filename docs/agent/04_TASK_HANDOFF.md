# Task Handoff

## Current Task

Add output artifacts and manifests for `qre eval-config`.

## Task ID

QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001

## Current Status

Ready for Claude Code implementation.

## Current Owner

CLAUDE_CODE

## Completed

- Codex reviewed and accepted `QRE-EVAL-METADATA-GROUP-SUMMARY-REGRESSION-001`.
- Codex created local checkpoint `b25cbd7` for the completed metadata group-summary task.
- Codex selected the next self-contained follow-up: durable `eval-config` output artifacts.
- Codex wrote the new implementation brief in `08_IMPLEMENTATION_BRIEF.md`.

## In Progress

- Claude Code should implement `QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001` from `08_IMPLEMENTATION_BRIEF.md`.

## Expected Files

- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- optional evaluation IO helper module
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py` or a new focused manifest test file
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Validation Baseline

- Previous accepted focused: `uv run pytest tests/test_evaluation_forward_returns.py -q` -> `14 passed in 0.39s`
- Previous accepted CLI: `uv run pytest tests/test_cli.py -q` -> `93 passed in 1.30s`
- Previous accepted full: `uv run pytest -q` -> `255 passed in 2.45s`
- Previous checks: `scripts/check-progress-docs.sh`, `git diff --check`, and `scripts/git-finalize-check.sh` passed before local checkpoint `b25cbd7`.

## Known Risks

- Output-dir behavior must be additive and optional.
- Existing portfolio report-manifest parsing must remain compatible.
- Run manifests must omit sensitive connection values.
- No evaluation math should change.

## Next Suggested Step

Claude Code should read `08`, `11`, and `12`, then implement the current Claude Code task.
