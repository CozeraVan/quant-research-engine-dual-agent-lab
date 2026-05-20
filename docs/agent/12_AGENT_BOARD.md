# Agent Board

## Current Task ID

QRE-EVAL-FACTOR-DECAY-SUMMARY-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

Implement evaluation factor decay summaries from existing IC and Rank IC outputs.

## Implementation Request

Claude Code should implement `08_IMPLEMENTATION_BRIEF.md` exactly:

1. Add `factor_decay_summary` to `EvaluationResult`.
2. Derive factor decay rows from existing `ic_summary`.
3. Compare each factor/horizon against that factor's smallest horizon.
4. Print `factor_decay_summary` from `qre eval-config` when available.
5. Persist `factor_decay_summary.csv` under `eval-config --output-dir`.
6. Add report manifest validation for the new artifact role.
7. Preserve existing evaluation behavior and artifacts.
8. Write `09_CODING_HANDOFF.md` with changed files, validation, risks, and git state.

## Constraints Check

- Do not add benchmark wiring, regime classification, or new data sources.
- Do not compute technical indicators internally.
- Do not change existing IC, Rank IC, quantile, group, or random-baseline semantics.
- Keep output manifests compatible with `report-files` and `report-audit`.
- Do not push.

## Required Validation

- `uv run pytest tests/test_evaluation_forward_returns.py tests/test_cli.py tests/test_portfolio_report_manifest.py -q`
- `uv run pytest -q`
- `scripts/check-progress-docs.sh`
- `git diff --check`

## Expected Changed Files

- `src/quant_research_engine/evaluation/models.py`
- `src/quant_research_engine/evaluation/engine.py`
- `src/quant_research_engine/apps/cli.py`
- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_evaluation_forward_returns.py`
- `tests/test_cli.py`
- `tests/test_portfolio_report_manifest.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Next Step

Claude Code should implement the current task from `08_IMPLEMENTATION_BRIEF.md`.
