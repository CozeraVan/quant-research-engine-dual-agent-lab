# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_BRIEF_READY

## Sender

CODEX

## Short Message

Codex prepared the next implementation brief. Claude Code should add recursive validation for eval/backtest stage report manifests referenced by a top-level `research_run_report_manifest`.

## Required Outcome

| Area | Required |
|---|---|
| Recursive validation | Root research-run audit validates nested eval/backtest report manifests |
| Issue handling | Malformed nested manifest returns a structured validation issue, not a CLI crash |
| Filtering | `--role run_manifest` does not trigger nested validation; `--role eval_report_manifest` does |
| Compatibility | Existing non-research-run report manifest behavior remains unchanged |
| Tests | CLI and helper regressions cover nested malformed/missing artifact cases |

## Review Status

PENDING_IMPLEMENTATION

## Evidence

- Previous finalized baseline: `0fb70f1` research-run root report manifest; full suite `803 passed, 2 warnings`.
- Codex review risk: top-level validation currently checks nested stage manifest files for existence but does not recursively validate their contents.

## Next Step

Claude Code implements `08_IMPLEMENTATION_BRIEF.md`, then updates `09_CODING_HANDOFF.md` for Codex review.
