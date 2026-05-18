# Agent Board

## Current Task ID

QRE-REPORT-DOCS-JSON-CLI-001

## Current Recipient

CODEX

## Message Type

CLAUDE_TO_CODEX

## Sender

CLAUDE_CODE

## Short Message

Docs-only implementation complete. README now documents `report-files --require-match`, `report-files --json`, and `report-audit --json` with concise examples. No src/ or tests/ changes. All 175 tests pass. Ready for Codex review.

## Must Read

- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/02_LOCKED_REQUIREMENTS.md`

## Must Do (Codex)

1. Review the README changes against `docs/agent/08_IMPLEMENTATION_BRIEF.md`.
2. Write `docs/agent/10_REVIEW_REPORT.md`.
3. If review passes and user has requested One-Shot Review-Finalize-Next:
   - Create local git checkpoint for accepted implementation.
   - Prepare next `08_IMPLEMENTATION_BRIEF.md`.
   - Update `12_AGENT_BOARD.md` for Claude Code.
   - Create local checkpoint for planning docs.
   - Set Phase = `CLAUDE_IMPLEMENTING`, Owner = `CLAUDE_CODE`.
4. If review fails, write Required Fixes and hand back to Claude Code.

## Must Not Do

1. Do not push (no standing approval).
2. Do not modify code (review only).
3. Do not modify forbidden files.

## Changed Files (for review)

- `README.md` — added JSON and strict-matching documentation

## Required Validation

```bash
scripts/check-progress-docs.sh
git diff --check
uv run pytest -q
```
