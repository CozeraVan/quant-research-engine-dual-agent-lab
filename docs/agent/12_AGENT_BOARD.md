# Agent Board

## Current Task ID

QRE-BENCHMARK-MEMBERSHIP-INDUSTRY-ADAPTERS-001

## Current Recipient

CLAUDE_CODE

## Message Type

IMPLEMENTATION_REQUEST

## Sender

CODEX

## Short Message

The next QRE slice is benchmark membership and industry classification standardization. Read `08/09/11/12`, then implement a read-only adapter that uses `reference.index_weight` for benchmark membership and normalizes industry into a stable grouping column. QRE must remain read-only and must not restore Tushare producer code.

## Required Outcome

| Area | Required | Status |
|---|---|---|
| Benchmark membership | Latest-available `reference.index_weight` rows are exposed through the read-side metadata path when benchmark context is available | READY_FOR_IMPLEMENTATION |
| Industry grouping | `industry_group` is normalized from raw industry metadata without mutating the passthrough | READY_FOR_IMPLEMENTATION |
| Explicit metadata table | `QRE_SECURITY_METADATA_TABLE` priority remains unchanged | REQUIRED |
| Fallback compatibility | Daily-derived fallback still works if `reference.stock_basic` is absent | REQUIRED |
| QRE scope | No Tushare download/ingest code in QRE | REQUIRED |
| Tests | Targeted unit tests cover benchmark membership, industry normalization, and fallback behavior | REQUIRED |

## Review Status

NOT_STARTED

## Evidence Available

- `../quant_ts/REFERENCE_DATA.md` lists `reference.index_weight` as the benchmark membership source.
- `../quant_ts/handlers/reference_data_handler.py` defines the `index_weight` reference dataset for read-only ingestion ownership in the sibling project.
- `reference.stock_basic`, `reference.stock_suspend`, `reference.stock_st`, and `reference.stock_risk_warning` are already available and wired into QRE read-side metadata composition.

## Claude Code Steps

1. Extend the read-side metadata adapter to load the latest `reference.index_weight` snapshot for the requested benchmark code when benchmark context is present.
2. Add benchmark membership columns for downstream grouping and diagnostics.
3. Normalize industry metadata into a stable `industry_group` column while preserving the raw `industry` passthrough.
4. Keep explicit metadata tables first-priority and skip enrichment when source tables are missing.
5. Add focused tests for latest-snapshot selection, fallback behavior, and normalization.
6. Update the agent/doc state files so the next handoff is unambiguous.

## Claude Code Instructions

Read:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Then implement only the scoped QRE code changes.

## Next Step

Claude Code implements and updates `09_CODING_HANDOFF.md`. Codex then reviews and writes `10_REVIEW_REPORT.md`.
