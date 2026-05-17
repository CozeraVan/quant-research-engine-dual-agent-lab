# Progress Tracker

## Current Phase

WAITING_USER_APPROVAL

## Progress Table

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| DOC-1 | Initialize dual-agent workflow docs | DONE | USER/SCRIPT | commit `77fec02` | Preserve |
| DOC-2 | Migrate legacy docs into `docs/agent` | DONE | CODEX | current migration | User review |
| DOC-3 | Add archive notes to legacy planning docs | DONE | CODEX | Archived Note added to five legacy md files | Preserve; do not delete |
| QRE-M1 | Project skeleton and core market profile | DONE | HISTORICAL | package layout, tests, skeleton plan | Preserve |
| QRE-M2 | Data layer and preflight | DONE | HISTORICAL | `qre db-smoke`, `factor-smoke`, `metadata-smoke`, `preflight` | Add real metadata adapters later |
| QRE-M3 | Evaluation MVP | DONE | HISTORICAL | forward returns, IC, Rank IC, quantile, friction summaries | Add grouping/regime later |
| QRE-M4 | Portfolio MVP | DONE | HISTORICAL | single, batch, shared-cash, risk, rebalance, FIFO lots, T+1 inventory | Improve diagnostics |
| QRE-M5 | Reporting and manifest audit | DONE | HISTORICAL | report manifests, `report-files`, `report-audit` | Standardize larger run workflow later |
| QRE-NEXT-1 | Failed-order diagnostics brief | WAITING_USER_APPROVAL | USER | `08_IMPLEMENTATION_BRIEF.md` | Approve for Claude Code |

## Latest Verified Legacy State

Recorded in legacy docs on 2026-05-17:

- Full tests after shared-cash lot accounting: `uv run pytest -q` -> `156 passed in 1.30s`
- Shared-cash smoke generated orders/trades/equity/report artifacts under `outputs/smoke_shared_phase4_lots`
- Read-only DB/factor/evaluation smokes worked for `2026-05-11` to `2026-05-15`

These results are migrated historical evidence. Rerun validation before any finalization or current success claim.

## Completed Module Summary

- Data layer: read-only PostgreSQL adapter, factor catalog, research assembler, metadata fallback, benchmark-bar skeleton, preflight.
- Evaluation layer: safe expression signals, forward returns, event summaries, IC, Rank IC, quantile summaries, rough friction adjustment.
- Portfolio layer: single-symbol, batch, shared-cash, costs, slippage, lot sizing, price-limit checks, risk exits, rebalance, FIFO lot accounting, T+1 sellability, analytics.
- Reporting: CSV/JSON/Markdown outputs, report manifests, manifest filtering, existence/content validation, strict audit option.

## Pending Work Summary

- Stronger failed-order diagnostics and summaries.
- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning time-varying metadata.
- Industry, board, market-cap, liquidity, membership, and regime grouping.
- Evaluation benchmark/random-baseline comparison.
- Larger research-run reproducibility workflow.

## Status Meaning

- TODO: Not started
- WAITING_USER_APPROVAL: User approval required before the next agent proceeds
- IN_PROGRESS: Started but not complete
- DONE: Completed and verified or preserved from legacy evidence
- BLOCKED: Blocked
- FUTURE: Future milestone

## Update Rules

- Mark DONE only with evidence.
- If code changed, update `04_TASK_HANDOFF.md` and this file.
- If a dual-agent phase changed, update `11_AGENT_STATE.md`.
- If architecture or major decisions changed, update `06_DECISION_LOG.md`.
