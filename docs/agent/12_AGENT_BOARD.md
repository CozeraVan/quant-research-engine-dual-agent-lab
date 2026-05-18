# Agent Board

## Current Task ID

QRE-REPORT-MANIFEST-INVALID-JSON-VALIDATION-001

## Current Recipient

CLAUDE_CODE

## Message Type

CODEX_TO_CLAUDE

## Sender

CODEX

## Short Message

Normalize invalid manifest JSON parse failures. Malformed text like `"{"`, `"{"kind":"`, or `"not-json"` should raise clear manifest-specific `ValueError` instead of raw `JSONDecodeError`, while valid-manifest behavior stays unchanged.

## Must Do

1. Wrap only manifest JSON parse failures in `ReportManifest.from_path()`.
2. Add focused tests in `tests/test_portfolio_report_manifest.py` for at least two malformed JSON text cases.
3. Preserve root-shape, `files`-shape, file-entry, schema-version, and valid-manifest behavior.
4. Update `04`, `05`, `09`, `11`, and `12` before handing back.
5. Run the required validation commands.

## Must Not Do

1. Do not modify unrelated CLI/reporting behavior.
2. Do not broaden this into general exception wrapping.
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
