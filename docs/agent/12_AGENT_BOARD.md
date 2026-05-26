# Agent Board

## Current Task ID

QRE-PORTFOLIO-BASELINE-COMPARISON-001

## Current Recipient

CLAUDE_CODE

## Message Type

STATUS_UPDATE

## Sender

CODEX

## Short Message

The next slice is portfolio baseline comparison. Populate buy-and-hold and benchmark-relative strategy comparison fields without changing execution semantics.

## Required Outcome

| Area | Required | Status |
|---|---|---|
| Buy-and-hold fields | `buy_hold_return` and related fields are populated in single-symbol and batch summaries using the same available symbol window | READY |
| Benchmark comparison | Optional benchmark inputs are wired through the batch/full-market reporting path and populate benchmark-relative summary fields | READY |
| Industry metadata | `industry` / `industry_group` passthrough remains available for same-industry comparison | READY |
| Shared-cash behavior | Existing shared-cash benchmark-relative comparison continues to work unchanged | READY |
| QRE scope | No Tushare download/ingest code in QRE | READY |
| Tests | Targeted unit tests cover buy-hold metrics, benchmark wiring, and metadata passthrough | READY |

## Review Status

PENDING

## Evidence Available

- `src/quant_research_engine/portfolio/full_market_report.py` already reserves buy-hold and benchmark fields in the reporting schema.
- `src/quant_research_engine/portfolio/benchmark.py` already implements benchmark-relative summary math for shared-cash output.
- `src/quant_research_engine/portfolio/batch.py` and `src/quant_research_engine/portfolio/single_symbol.py` are the most likely wiring points for buy-and-hold baseline metrics.
- `industry` / `industry_group` columns already flow through existing metadata and grouped report paths.

## Claude Code Steps

1. Populate the buy-and-hold baseline fields first so the report schema stops emitting null comparison values.
2. Thread benchmark-relative summary inputs through the batch/full-market path using the existing helper.
3. Preserve industry metadata passthrough and grouped outputs.
4. Return the changed files and validation output to Codex for review.

## Claude Code Instructions

Read:

- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/agent/09_CODING_HANDOFF.md`
- `docs/agent/11_AGENT_STATE.md`
- `docs/agent/12_AGENT_BOARD.md`

Then implement only the scoped QRE code changes.

## Next Step

Claude Code implementation, then Codex review.
