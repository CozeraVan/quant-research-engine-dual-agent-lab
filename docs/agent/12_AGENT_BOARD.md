# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-AUDIT-ROLE-SELECTOR-PARITY-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_BRIEF_READY

## Sender

CODEX

## Short Message

Codex prepared the next implementation brief. Claude Code should lock CLI role selector parity for top-level `research_run_report_manifest` audits across `report-files`, `report-audit`, JSON/text output, and `--require-match`.

## Required Outcome

| Area | Required |
|---|---|
| Role selectors | `run_manifest`, `preflight_report`, `eval_report_manifest`, `backtest_report_manifest` select exact roles |
| CLI parity | `report-files` and `report-audit` behave consistently for selected roles |
| Validation triggers | Selected role validates only its own content path |
| Require-match | matching selectors exit 0; no-match selectors exit 2 |
| No side effects | no-match or sibling-role selectors do not validate unrelated malformed files |

## Review Status

PENDING_IMPLEMENTATION

## Evidence

- Previous finalized baseline: `eb3d8cd` research-run preflight report content audit; full suite `826 passed, 2 warnings`.
- Codex review risk: selector behavior is not fully locked for every root research-run role across CLI surfaces and output modes.

## Next Step

Claude Code implements `08_IMPLEMENTATION_BRIEF.md`, then updates `09_CODING_HANDOFF.md` for Codex review.
