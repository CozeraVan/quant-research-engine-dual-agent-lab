# Agent Board

## Current Task ID

QRE-DOCS-EVAL-GROUP-BY-MANIFEST-PARITY-USAGE-001

## Current Recipient

CODEX

## Message Type

CLAUDE_CODE_TO_CODEX

## Sender

CLAUDE_CODE

## Short Message

Docs updated for evaluation per-column grouped artifacts and --group-by parity. Ready for review.

## Changes Summary

- `README.md` — updated "Evaluation Grouping" with per-column files, manifest `group_by` metadata, and `--group-by` discovery/audit examples
- `docs/modules/data_layer.md` — updated "Metadata-Aware Grouping" evaluation section with per-column artifact explanation
- `docs/modules/portfolio_workflow.md` — updated eval group summary section with per-column file behavior
- Agent docs — 04/05/09/11/12 updated

## Validation

- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed

## Next Step

Codex should review and produce `10_REVIEW_REPORT.md`.
