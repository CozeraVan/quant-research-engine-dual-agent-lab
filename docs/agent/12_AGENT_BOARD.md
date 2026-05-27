# Agent Board

## Current Task ID

QRE-REFERENCE-ASOF-METADATA-SNAPSHOT-001

## Current Recipient

CODEX

## Message Type

USER_ACCEPTANCE

## Sender

CLAUDE_CODE

## Summary

Claude Code completed three fix passes for the as-of metadata snapshot wiring:

- Fix pass 1: `stock_risk_warning` now uses as-of date instead of `CURRENT_DATE`; `_run_backtest()` passes `metadata_as_of` to assembler; `_write_research_manifest()` records `metadata_as_of`.
- Fix pass 2: Direct `backtest-batch` / `backtest-shared` CLI paths now accept `--metadata-as-of`, thread it into `assembler.build()`, and record it in output `run_request` payloads.
- Fix pass 3: Direct `backtest-single` CLI path now accepts `--metadata-as-of`, threads it into `assembler.build()`, and records it in output `run_request` payloads.
- 6 new CLI tests added across all three backtest entry points.

## Required Action

Await user approval for git finalization.
