# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-AUDIT-USAGE-DOCS-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_BRIEF_READY

## Sender

CODEX

## Short Message

Codex prepared the next implementation brief. Claude Code should sync README/module docs with the finalized top-level research-run report-manifest audit contract.

## Required Outcome

| Area | Required |
|---|---|
| README | research-run section documents top-level `report_manifest.json` audit entry point |
| Role examples | commands for `run_manifest`, `preflight_report`, `eval_report_manifest`, `backtest_report_manifest` |
| Selector semantics | docs explain role isolation and shared `report-files` / `report-audit` selectors |
| Module docs | `docs/modules/portfolio_workflow.md` updated; `portfolio_layer.md` pointer if useful |
| Safety | no runtime/schema changes, no legacy-doc edits, no strategy-quality claims |

## Review Status

PENDING_IMPLEMENTATION

## Evidence

- Previous finalized baseline: `a027d69` research-run audit role selector parity; full suite `836 passed, 2 warnings`.
- Codex documentation gap: README examples show only basic top-level audit and `run_manifest`; final role-level audit contract is not fully documented.

## Next Step

Claude Code implements `08_IMPLEMENTATION_BRIEF.md`, then updates `09_CODING_HANDOFF.md` for Codex review.
