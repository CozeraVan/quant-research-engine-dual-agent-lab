# Agent Board

## Current Task ID

QRE-EVAL-CONFIG-OUTPUT-ARTIFACTS-REGRESSION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE_CODE

## Sender

CODEX

## Short Message

New implementation task is ready. Please implement durable `eval-config` output artifacts from `docs/agent/08_IMPLEMENTATION_BRIEF.md`.

## Implementation Summary

Codex has prepared the next self-contained task:

1. Add `qre eval-config --output-dir`.
2. Write evaluation artifacts such as `events.csv`, `summary.csv`, `ic_summary.csv`, `quantile_summary.csv`, and `group_summary.csv` when applicable.
3. Write `run_manifest.json` with safe run metadata.
4. Write `report_manifest.json` with kind `evaluation_report_manifest`.
5. Extend `ReportManifest` loading/content validation for evaluation artifacts.
6. Add focused CLI and manifest regression tests.

## Constraints Check

- Scope should stay in eval-config output handling, report-manifest support, and focused tests.
- Existing evaluation calculations must not change.
- Existing stdout behavior should remain compatible.
- Existing portfolio report manifests must remain compatible.
- Do not store sensitive connection values.
- Do not push.

## Expected Changed Files

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

## Required Validation

```bash
uv run pytest tests/test_cli.py -q
uv run pytest tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
