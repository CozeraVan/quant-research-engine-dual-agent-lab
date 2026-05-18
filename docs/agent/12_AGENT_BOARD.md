# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001

## Current Recipient

CODEX

## Message Type

CODEX_REVIEW_PASS

## Sender

CODEX

## Short Message

Review passed. Manifest file entry validation now raises clear `ValueError` for missing required fields while preserving valid-manifest behavior and optional metadata handling. Ready for local checkpoint and next planning.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do (Codex)

1. Create local git checkpoint for accepted implementation.
2. Prepare next `08_IMPLEMENTATION_BRIEF.md`.
3. Update `12_AGENT_BOARD.md` for Claude Code.
4. Create local checkpoint for planning docs.
5. Set Phase = `CLAUDE_IMPLEMENTING`, Owner = `CLAUDE_CODE`.

## Must Not Do

1. Do not push (no standing approval).
2. Do not modify code (review only).
3. Do not modify forbidden files.

## Changed Files (for review)

- `src/quant_research_engine/portfolio/report_manifest.py` — added `_REQUIRED_FIELDS` and explicit validation in `ReportFile.from_mapping()`
- `tests/test_portfolio_report_manifest.py` — added `test_report_manifest_rejects_file_entry_missing_path` and `test_report_manifest_rejects_file_entry_missing_role`

## Required Validation

```bash
uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
