# Agent Board

## Current Task ID

QRE-RESEARCH-RUN-PREFLIGHT-REPORT-AUDIT-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_BRIEF_READY

## Sender

CODEX

## Short Message

Codex prepared the next implementation brief. Claude Code should add content validation for `preflight/preflight_report.json` entries referenced by a top-level `research_run_report_manifest`.

## Required Outcome

| Area | Required |
|---|---|
| Preflight validation | Root research-run audit validates `preflight_report` JSON content |
| Required field | `status` exists and is a non-empty string |
| Optional lists | `checks` and `missing_factor_requests`, when present, are lists |
| Filtering | `--role preflight_report` validates preflight; `--role run_manifest` does not |
| Compatibility | Non-research-run manifests with `preflight_report` role do not trigger this validation |

## Review Status

PENDING_IMPLEMENTATION

## Evidence

- Previous finalized baseline: `dcb4925` research-run stage manifest recursive audit; full suite `814 passed, 2 warnings`.
- Codex review risk: top-level validation currently checks `preflight/preflight_report.json` for existence but does not validate its JSON content.

## Next Step

Claude Code implements `08_IMPLEMENTATION_BRIEF.md`, then updates `09_CODING_HANDOFF.md` for Codex review.
