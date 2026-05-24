# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_REQUEST

## Sender

CODEX

## Short Message

User approved implementation. Claude Code should implement `QRE-RESEARCH-RUN-STAGE-ARTIFACT-PARITY-001` from `08_IMPLEMENTATION_BRIEF.md`.

## Review Status

NOT_STARTED

## Evidence

- README documents `outputs/research/<run>/eval/report_manifest.json` and `outputs/research/<run>/backtest/report_manifest.json`.
- `src/quant_research_engine/orchestration/research_run.py::_run_eval()` runs evaluation but does not persist evaluation artifacts.
- `_run_backtest()` writes artifacts directly into the research-run root instead of `<output_dir>/backtest/`.
- `tests/test_cli.py` only covers `research-run` help/missing-DB paths and ends with an unused `ResearchRunStrategySpec` helper.

## Next Step

Claude Code implements the brief, updates `09_CODING_HANDOFF.md`, `04_TASK_HANDOFF.md`, `05_PROGRESS.md`, `11_AGENT_STATE.md`, and `12_AGENT_BOARD.md`, then returns to Codex for review.
