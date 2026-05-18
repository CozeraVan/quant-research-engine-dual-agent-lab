# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-FILES-SHAPE-VALIDATION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

Implement explicit top-level manifest `files` shape validation. Reject non-list `files` payloads and non-object file entries with clear `ValueError`, while keeping valid-manifest behavior unchanged.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do

1. Tighten `ReportManifest.from_path(...)` so malformed top-level `files` payloads fail clearly.
2. Add focused tests in `tests/test_portfolio_report_manifest.py` for:
   - non-list `files`;
   - non-object file entry.
3. Keep the task narrowly scoped to manifest loader validation.
4. Update `04`, `05`, `09`, `11`, and `12` before handing back.
5. Run the required validation commands.

## Must Not Do

1. Do not modify unrelated CLI/reporting behavior.
2. Do not broaden this into a manifest-schema redesign.
3. Do not modify forbidden files from the brief.
4. Do not push.

## Expected Files

- `src/quant_research_engine/portfolio/report_manifest.py`
- `tests/test_portfolio_report_manifest.py`
- `docs/agent/04_TASK_HANDOFF.md`
- `docs/agent/05_PROGRESS.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

## Required Validation

```bash
uv run pytest tests/test_portfolio_report_manifest.py -q
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```
