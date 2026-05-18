# Progress Tracker

## Current Phase

CLAUDE_IMPLEMENTING

## Progress Table

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| DOC-1 | Initialize dual-agent workflow docs | DONE | USER/SCRIPT | commit `77fec02` | Preserve |
| DOC-2 | Migrate legacy docs into `docs/agent` | DONE | CODEX | commit `2565e13` | Preserve |
| DOC-3 | Add archive notes to legacy planning docs | DONE | CODEX | commit `2565e13` | Preserve; do not delete |
| QRE-M1 | Project skeleton and core market profile | DONE | HISTORICAL | package layout, tests, skeleton plan | Preserve |
| QRE-M2 | Data layer and preflight | DONE | HISTORICAL | `qre db-smoke`, `factor-smoke`, `metadata-smoke`, `preflight` | Add real metadata adapters later |
| QRE-M3 | Evaluation MVP | DONE | HISTORICAL | forward returns, IC, Rank IC, quantile, friction summaries | Add grouping/regime later |
| QRE-M4 | Portfolio MVP | DONE | HISTORICAL | single, batch, shared-cash, risk, rebalance, FIFO lots, T+1 inventory | Preserve |
| QRE-M4.7 | Failed-order diagnostics implementation | DONE | CODEX/CLAUDE_CODE | commit `28e6f25` | Preserve |
| QRE-M5.6 | Failed-order report schema and audit validation | DONE | CODEX/CLAUDE_CODE | commit `001177f` | Preserve |
| QRE-M5.7 | `report-files --require-match` | DONE | CODEX/CLAUDE_CODE | commit `e568823` | Preserve |
| QRE-M5.8 | `report-audit --json` | DONE | CODEX/CLAUDE_CODE | commit `3f7d623` | Preserve |
| QRE-M5.9 | `report-files --json` | DONE | CODEX/CLAUDE_CODE | commit `faa95e2` | Preserve |
| QRE-M5.10 | README report CLI JSON/strict docs | DONE | CODEX/CLAUDE_CODE | commit `e1eb4a5`; 175 tests passed before checkpoint | Preserve |
| QRE-NEXT-7 | Report manifest schema version | DONE | CODEX/CLAUDE_CODE | commit `72533bb`; 176 tests passed | Preserve |
| QRE-NEXT-8 | Manifest schema version in JSON tooling | DONE | CODEX/CLAUDE_CODE | commit `d34a694`; 179 tests passed | Preserve |
| QRE-NEXT-9 | Manifest schema version docs | DONE | CODEX/CLAUDE_CODE | commit `19d9ae4`; 179 tests passed | Preserve |
| QRE-NEXT-10 | Manifest schema version validation | DONE | CODEX/CLAUDE_CODE | commit `0fca02a`; 182 tests passed | Preserve |
| QRE-NEXT-11 | Manifest file entry validation | DONE | CODEX/CLAUDE_CODE | commit `feab301`; 184 tests passed | Preserve |
| QRE-NEXT-12 | CLI malformed-manifest regression coverage | READY | CLAUDE_CODE | brief `QRE-REPORT-CLI-INVALID-MANIFEST-001` prepared | Claude Code implements |

## Latest Verified State

Recorded on 2026-05-18 after local checkpoint for `QRE-REPORT-MANIFEST-ENTRY-VALIDATION-001` and next planning:

- `uv run pytest tests/test_portfolio_report_manifest.py tests/test_cli.py -q` -> `64 passed in 0.60s`
- `uv run pytest -q` -> `184 passed in 1.40s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- Required-field validation added to `ReportFile.from_mapping()` for `key`, `path`, `filename`, `role`.
- Accepted implementation committed locally as `feab301 feat: validate report manifest file entries`.
- Next implementation brief prepared: `QRE-REPORT-CLI-INVALID-MANIFEST-001`.

## Completed Module Summary

- Data layer: read-only PostgreSQL adapter, factor catalog, research assembler, metadata fallback, benchmark-bar skeleton, preflight.
- Evaluation layer: safe expression signals, forward returns, event summaries, IC, Rank IC, quantile summaries, rough friction adjustment.
- Portfolio layer: single-symbol, batch, shared-cash, costs, slippage, lot sizing, price-limit checks, risk exits, rebalance, FIFO lot accounting, T+1 sellability, failed-order diagnostics, analytics.
- Reporting: CSV/JSON/Markdown outputs, report manifests, manifest filtering, existence/content validation, strict audit/report-files matching, failed-order artifact schema validation, JSON audit/file-selection output, README and workflow documentation, manifest schema versioning with validation, schema version exposed in JSON tooling and ReportManifest helper.

## Pending Work Summary

- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning time-varying metadata.
- Industry, board, market-cap, liquidity, membership, and regime grouping.
- Evaluation benchmark/random-baseline comparison.
- Larger research-run reproducibility workflow.

## Status Meaning

- TODO: Not started
- WAITING_USER_APPROVAL: User approval required before the next agent proceeds
- IN_PROGRESS: Started but not complete
- IMPLEMENTED: Implemented by Claude Code, awaiting Codex review
- DONE: Completed and verified or preserved from legacy evidence
- BLOCKED: Blocked
- FUTURE: Future milestone

## Update Rules

- Mark DONE only with evidence.
- If code changed, update `04_TASK_HANDOFF.md` and this file.
- If a dual-agent phase changed, update `11_AGENT_STATE.md`.
- If architecture or major decisions changed, update `06_DECISION_LOG.md`.
