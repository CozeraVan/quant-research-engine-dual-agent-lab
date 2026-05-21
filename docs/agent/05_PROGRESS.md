# Progress Tracker

## Current Phase

CODEX_GIT_FINALIZING

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
| QRE-NEXT-24 | CLI regression coverage for optional file-entry metadata type errors | DONE | CODEX/CLAUDE_CODE | commit `a4693ab`; 4 CLI regression tests lock non-string optional `symbol` and `window` at the command boundary; 225 tests passed | Preserve |
| QRE-NEXT-25 | CLI regression coverage for optional `group_by` file-entry metadata type errors | DONE | CODEX/CLAUDE_CODE | commit `0083c82`; 2 CLI regression tests lock non-string optional `group_by` at the command boundary; 227 tests passed | Preserve |
| QRE-NEXT-26 | CLI regression coverage for valid explicit `null` optional file-entry metadata | DONE | CODEX/CLAUDE_CODE | commit `cce750d`; 2 CLI regression tests lock explicit `null` optional metadata via `--json`; 229 tests passed | Preserve |
| QRE-NEXT-27 | CLI regression coverage for explicit `null` top-level `schema_version` | DONE | CODEX/CLAUDE_CODE | commit `eac50d3`; 2 CLI regression tests lock explicit `schema_version: null` via `--json`; 231 tests passed | Preserve |
| QRE-NEXT-28 | CLI regression coverage for `report-files --json --check-exists` | DONE | CODEX/CLAUDE_CODE | commit `ff3732e`; 2 CLI regression tests lock JSON `--check-exists` existing + missing-file paths; 233 tests passed | Preserve |
| QRE-NEXT-29 | CLI regression coverage for `report-files --json --validate-contents` | DONE | CODEX/CLAUDE_CODE | commit `43a17b7`; 2 CLI regression tests lock JSON `--validate-contents` valid + structural-issue paths; 235 tests passed | Preserve |
| QRE-NEXT-30 | CLI regression coverage for exact `report-audit --json` issue payload details | DONE | CODEX/CLAUDE_CODE | local commit `dff2889`; per-issue `key`/`code`/`path`/`message` assertions for `missing_file` and `missing_columns`; 235 tests passed | Preserve |
| QRE-NEXT-31 | Shared-cash failed-order side diagnostics and summary analysis | DONE | CODEX/CLAUDE_CODE | local finalization; 238 tests passed; side-level diagnostics in `shared.py` and `io.py` | Preserve |
| QRE-NEXT-32 | Portfolio backtest run manifest reproducibility | DONE | CODEX/CLAUDE_CODE | commit `dea224a`; 246 tests passed; run_manifest.json for single, batch, shared; explicit role mapping; emitted manifests validate run manifests | Preserve |
| QRE-NEXT-33 | Evaluation metadata group summaries | DONE | CODEX/CLAUDE_CODE | commit `b25cbd7`; 255 passed in 2.45s; 6 engine tests + 2 CLI tests; group_summary in EvaluationResult; `eval-config --group-by` CLI support; Codex review passed | Preserve |
| QRE-NEXT-34 | Eval-config output artifacts and manifests | DONE | CODEX/CLAUDE_CODE | 265 passed in 2.83s; 2 CLI tests + 8 manifest tests; `--output-dir` writes events/summary/ic/quantile/group CSVs + run_manifest.json + report_manifest.json; evaluation_report_manifest kind; ReportManifest validates evaluation artifact roles; run_manifest records `market_profile` provenance when used | Codex review and local finalize |
| QRE-NEXT-35 | Evaluation random-baseline comparison | DONE | CODEX/CLAUDE_CODE | commit `495185b`; 274 passed in 3.19s; random baseline summary with deterministic RNG; CLI flag, stdout, CSV, manifest | Preserve |
| QRE-NEXT-36 | Real metadata adapters for optional upstream columns | DONE | CODEX/CLAUDE_CODE | local commit; 278 passed in 2.59s; passthrough columns preserved in `_load_security_metadata_table`; `_normalize_security_metadata` keeps all columns | Preserve |
| QRE-NEXT-37 | Batch metadata group-by passthrough | DONE | CODEX/CLAUDE_CODE | 283 passed in 2.67s; `summary_metadata_columns` in `BatchBacktestRequest`; CLI `backtest-batch --group-by` passes columns to engine; 5 new tests; Codex review passed | Preserve |
| QRE-NEXT-38 | Shared-cash metadata output passthrough | DONE | CODEX/CLAUDE_CODE | 293 passed in 2.80s; shared-cash `metadata_columns`; output rows carry requested metadata; collision guards prevent overwriting canonical fields; 10 new tests including CLI and collision coverage | Preserve |
| QRE-NEXT-39 | Shared-cash metadata group summaries | DONE | CODEX/CLAUDE_CODE | 315 passed in 3.00s; row-based grouped order/trade/failed-order summaries; `backtest-shared --group-by`; grouped CSV artifacts; manifest roles; empty no-column outputs handled | Preserve |
| QRE-NEXT-40 | Evaluation factor decay summary | DONE | CODEX/CLAUDE_CODE | commit `8b0e924`; `10_REVIEW_REPORT.md` PASS; `factor_decay_summary` in `EvaluationResult`; derived from `ic_summary` per factor/horizon; stdout + CSV artifact + manifest validation; 324 passed | Preserve |
| QRE-NEXT-41 | Run ID manifest linkage | DONE | CODEX/CLAUDE_CODE | commit `1618657`; `10_REVIEW_REPORT.md` PASS; 330 tests passed; optional `--run-id` on 5 commands; persisted in eval run_manifest, preflight JSON, and portfolio run_manifest | Preserve |
| QRE-NEXT-42 | Run manifest content validation | DONE | CODEX/CLAUDE_CODE | commit `983ca1b`; `10_REVIEW_REPORT.md` PASS; present-null fix accepted; 346 tests passed; Codex reproduction case now returns 4 issues (was 0) | Preserve |
| QRE-NEXT-43 | Run-ID and run-manifest audit usage docs | DONE | CODEX/CLAUDE_CODE | commit `ccb80e8`; `10_REVIEW_REPORT.md` PASS; README, portfolio_workflow.md, and portfolio_layer.md updated with `--run-id` and run-manifest audit documentation | Preserve |
| QRE-NEXT-44 | Evaluation artifacts usage docs | DONE | CODEX/CLAUDE_CODE | commit `974543e`; `10_REVIEW_REPORT.md` PASS; README plus module docs cover eval-config artifacts, report roles, random baseline, factor decay, and audit usage; finalize checks passed | Preserve |
| QRE-NEXT-45 | Metadata grouping and passthrough usage docs | DONE | CODEX/CLAUDE_CODE | commit `a59c1a4`; `10_REVIEW_REPORT.md` PASS; README plus 3 module docs cover eval/batch/shared metadata grouping, shared-cash passthrough, grouped roles, and structural-inspection disclaimer | Preserve |
| QRE-NEXT-46 | Evaluation group-by manifest parity | DONE | CODEX/CLAUDE_CODE | commit `745103e`; `10_REVIEW_REPORT.md` PASS; per-column `group_summary_by_<col>.csv` files with manifest metadata `group_by=<col>`; `report-files`/`report-audit --group-by` parity; 6 new tests; 164 tests pass | Preserve |
| QRE-NEXT-47 | Evaluation group-by parity docs | DONE | CODEX/CLAUDE_CODE | commit `5fc7605`; `10_REVIEW_REPORT.md` PASS; README, data_layer.md, and portfolio_workflow.md cover combined/per-column evaluation grouped artifacts and `--group-by` discovery/audit parity | Preserve |
| QRE-NEXT-48 | Grouped artifact `group_by` audit consistency | DONE | CODEX/CLAUDE_CODE | commit `a3768fb`; `10_REVIEW_REPORT.md` PASS; grouped eval/shared `group_by` mismatch checks now run only after required-column validation passes; malformed grouped-file regression added; 175 tests passed | Preserve |
| QRE-NEXT-49 | Batch grouped-artifact `group_by` header consistency | DONE | CODEX/CLAUDE_CODE | commit `de37afd`; `10_REVIEW_REPORT.md` PASS; batch grouped manifest `group_by` metadata now requires matching CSV header columns; 8 new tests; 183 tests passed | Preserve |
| QRE-NEXT-50 | Rolling-artifact `window_size` filter parity | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `window_size` parsed from manifest entries and surfaced through `files()`/`paths()`/`validate_contents()`, `--window-size` CLI flag, and `report-files --json`; 9 manifest + 5 CLI tests; 197 tests passed | Preserve |
| QRE-NEXT-51 | Rolling-artifact `window_size` usage docs | DONE | CODEX/CLAUDE_CODE | commit `22fd3d1`; `10_REVIEW_REPORT.md` PASS; README plus portfolio module docs updated with `--window-size` examples, `--window` vs `--window-size` distinction, and additive JSON metadata wording; doc checks passed | Preserve |
| QRE-NEXT-52 | CLI regression coverage for invalid `window_size` manifest metadata | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock string and boolean `window_size` at `report-files` / `report-audit` command boundaries; 201 passed in 1.96s | Preserve |

## Latest Verified State

Recorded on 2026-05-21 after Codex accepted `QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001` for local finalization:

- Current task: `QRE-CLI-WINDOW-SIZE-METADATA-TYPE-REGRESSION-001`
- Last finalized: `QRE-DOCS-ROLLING-WINDOW-SIZE-FILTER-USAGE-001` (commit `22fd3d1`)
- Current verification:
  - `uv run pytest tests/test_cli.py tests/test_portfolio_report_manifest.py -q` → 201 passed in 1.96s
  - `scripts/check-progress-docs.sh` → passed
  - `git diff --check` → passed
  - `scripts/git-finalize-check.sh` → passed (from `22fd3d1`)
- Review: `10_REVIEW_REPORT.md` is now PASS
- Last implementation: test-only — 4 CLI regression tests lock string and boolean `window_size` at `report-files` / `report-audit` command boundaries; runtime unchanged
- Next step: Codex local finalization commit

## Completed Module Summary

- Data layer: read-only PostgreSQL adapter, factor catalog, research assembler, metadata fallback, benchmark-bar skeleton, preflight, real metadata passthrough adapters.
- Evaluation layer: safe expression signals, forward returns, event summaries, IC, Rank IC, quantile summaries, rough friction adjustment, metadata group summaries, durable output artifacts with manifests, random-baseline comparison, factor decay summaries.
- Portfolio layer: single-symbol, batch, shared-cash, costs, slippage, lot sizing, price-limit checks, risk exits, rebalance, FIFO lot accounting, T+1 sellability, failed-order diagnostics, analytics, batch metadata group-by passthrough, shared-cash metadata output passthrough, shared-cash row-level metadata group summaries.
- Reporting: CSV/JSON/Markdown outputs, report manifests, manifest filtering, existence/content validation, strict audit/report-files matching, failed-order artifact schema validation, JSON audit/file-selection output, README and workflow documentation, manifest schema versioning with validation, schema version exposed in JSON tooling and ReportManifest helper, manifest file entry validation, CLI malformed-manifest regression coverage, manifest `files` shape validation, manifest root shape validation, missing top-level manifest field CLI regression coverage, top-level manifest field type CLI regression coverage, malformed manifest root CLI regression coverage, malformed manifest file entry CLI regression coverage, schema-version type CLI regression coverage, optional file-entry metadata type CLI regression coverage, optional `group_by` file-entry metadata CLI regression coverage, null optional metadata CLI regression coverage, null schema-version CLI regression coverage, `report-files --json --check-exists` CLI regression coverage, `report-files --json --validate-contents` CLI regression coverage, `report-audit --json` issue payload field CLI regression coverage, shared-cash failed-order diagnostics and summary analysis, portfolio backtest run-manifest reproducibility, evaluation metadata group summaries, eval-config output artifacts and manifests, evaluation random-baseline comparison, evaluation artifact usage docs, metadata grouping and passthrough usage docs, evaluation group-by manifest parity, grouped artifact `group_by` content consistency validation, batch grouped-artifact `group_by` header consistency validation, rolling-artifact `window_size` manifest filter parity.

## Pending Work Summary

- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning time-varying metadata.
- Industry, market-cap, liquidity, membership, and regime grouping across evaluation and shared-cash outputs.
- Larger research-run reproducibility workflow beyond run-ID linkage.

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
