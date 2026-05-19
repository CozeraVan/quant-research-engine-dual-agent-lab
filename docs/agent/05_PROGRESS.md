# Progress Tracker

## Current Phase

USER_ACCEPTANCE

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
| QRE-NEXT-12 | CLI malformed-manifest regression coverage | DONE | CODEX/CLAUDE_CODE | commit `56253a5`; 189 tests passed | Preserve |
| QRE-NEXT-13 | Manifest `files` payload shape validation | DONE | CODEX/CLAUDE_CODE | commit `6d7d596`; 191 tests passed | Preserve |
| QRE-NEXT-14 | Manifest root payload shape validation | DONE | CODEX/CLAUDE_CODE | commit `950c814`; 193 tests passed | Preserve |
| QRE-NEXT-15 | Manifest invalid JSON normalization | DONE | CODEX/CLAUDE_CODE | commit `333f46d`; malformed JSON now raises manifest-specific `ValueError`; 195 tests passed | Preserve |
| QRE-NEXT-16 | Manifest top-level `kind` validation | DONE | CODEX/CLAUDE_CODE | commit `3d8a01e`; missing/non-string `kind` now raises manifest-specific `ValueError`; 198 tests passed | Preserve |
| QRE-NEXT-17 | Manifest file-entry field type validation | DONE | CODEX/CLAUDE_CODE | commit `d3eb1d0`; non-string entry fields now raise manifest-specific `ValueError`; 200 tests passed | Preserve |
| QRE-NEXT-18 | Manifest top-level `files` presence validation | DONE | CODEX/CLAUDE_CODE | commit `53f9aba`; missing `files` now raises manifest-specific `ValueError`; 201 tests passed | Preserve |
| QRE-NEXT-19 | CLI regression coverage for missing top-level manifest fields | DONE | CODEX/CLAUDE_CODE | commit `5aa584b`; 4 CLI regression tests lock missing `kind`/`files` at the command boundary; 205 tests passed | Preserve |
| QRE-NEXT-20 | CLI regression coverage for top-level manifest type errors | DONE | CODEX/CLAUDE_CODE | commit `75b42bc`; 4 CLI regression tests lock non-string `kind` and non-list `files` at the command boundary; 209 tests passed | Preserve |
| QRE-NEXT-21 | CLI regression coverage for malformed manifest roots | DONE | CODEX/CLAUDE_CODE | commit `be62461`; 4 CLI regression tests lock invalid JSON/non-object roots at the command boundary; 213 tests passed | Preserve |
| QRE-NEXT-22 | CLI regression coverage for malformed manifest file entries | DONE | CODEX/CLAUDE_CODE | commit `ac234d8`; 4 CLI regression tests lock non-object file entries and non-string required file-entry fields at the command boundary; 217 tests passed | Preserve |
| QRE-NEXT-23 | CLI regression coverage for schema-version type errors | DONE | CODEX/CLAUDE_CODE | commit `bdce0fa`; 4 CLI regression tests lock string and boolean `schema_version` at the command boundary; 221 tests passed | Preserve |
| QRE-NEXT-24 | CLI regression coverage for optional file-entry metadata type errors | DONE | CODEX/CLAUDE_CODE | Codex review passed; 4 CLI regression tests lock non-string optional `symbol` and `window` at the command boundary; 225 tests passed | Local checkpoint |

## Latest Verified State

Recorded on 2026-05-19 after Codex review of `QRE-REPORT-MANIFEST-CLI-OPTIONAL-ENTRY-TYPE-REGRESSION-001`:

- `uv run pytest tests/test_cli.py -q` -> `81 passed in 1.09s`
- `uv run pytest -q` -> `225 passed in 2.19s`
- `scripts/check-progress-docs.sh` -> passed
- `git diff --check` -> passed
- `scripts/git-finalize-check.sh` -> passed
- Accepted task: `QRE-REPORT-MANIFEST-CLI-OPTIONAL-ENTRY-TYPE-REGRESSION-001`
- Next step: local checkpoint, then next brief

## Completed Module Summary

- Data layer: read-only PostgreSQL adapter, factor catalog, research assembler, metadata fallback, benchmark-bar skeleton, preflight.
- Evaluation layer: safe expression signals, forward returns, event summaries, IC, Rank IC, quantile summaries, rough friction adjustment.
- Portfolio layer: single-symbol, batch, shared-cash, costs, slippage, lot sizing, price-limit checks, risk exits, rebalance, FIFO lot accounting, T+1 sellability, failed-order diagnostics, analytics.
- Reporting: CSV/JSON/Markdown outputs, report manifests, manifest filtering, existence/content validation, strict audit/report-files matching, failed-order artifact schema validation, JSON audit/file-selection output, README and workflow documentation, manifest schema versioning with validation, schema version exposed in JSON tooling and ReportManifest helper, manifest file entry validation, CLI malformed-manifest regression coverage, manifest `files` shape validation, manifest root shape validation, missing top-level manifest field CLI regression coverage, top-level manifest field type CLI regression coverage, malformed manifest root CLI regression coverage, malformed manifest file entry CLI regression coverage, schema-version type CLI regression coverage, optional file-entry metadata type CLI regression coverage.

## Pending Work Summary

- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning time-varying metadata.
- Industry, board, market-cap, liquidity, membership, and regime grouping.
- Evaluation benchmark/random-baseline comparison.
- Larger research-run reproducibility workflow.
- CLI regression coverage for optional `group_by` file-entry metadata type errors.

## Status Meaning

- TODO: Not started
- READY: Scoped and ready for the implementer
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
