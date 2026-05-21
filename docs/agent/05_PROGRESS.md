# Progress Tracker

## Current Phase

DONE

## Current Active Work

`QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` has passed Codex re-review and is finalized locally.

## Progress Table

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| DOC-1 | Initialize dual-agent workflow docs | DONE | USER/SCRIPT | commit `77fec02` | Preserve |
| DOC-2 | Migrate legacy docs into `docs/agent` | DONE | CODEX | commit `2565e13` | Preserve |
| DOC-3 | Add archive notes to legacy planning docs | DONE | CODEX | commit `2565e13` | Preserve; do not delete |
| QRE-GUI-LOCAL-BACKTEST-CONSOLE-001 | Local browser backtest console shell and YAML editor | DONE | CLAUDE_CODE | 179 GUI/CLI tests passed; rerun, artifact viewer, and summary.json coverage verified | Preserve |
| QRE-STRATEGY-IO-CONTRACT-DESIGN-001 | Strategy IO contract design | DESIGN_RECORDED | CODEX | `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`; user clarified QRE should write the strategy-entry standard, not rewrite external strategy projects | Preserve as the entry-contract source for later implementation |
| QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001 | Strategy entry authoring standard docs | DONE | CODEX/CLAUDE_CODE | `docs/strategy_entry/` includes 6 docs; `10_REVIEW_REPORT.md` PASS; local finalization complete | Start next task |
| QRE-FACTOR-MISSING-HANDOFF-STANDARD-001 | Operational missing-factor handoff standard | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `missing_factor_requests.json` emission + CLI status + lifecycle docs + 28 targeted tests; 168 tests passed | Start next task |
| QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001 | High-level entry compiler/preflight linkage | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS after fix cycle; expression emission now alias-based; 2 end-to-end runtime tests added; 302 tests pass | Start next task |
| QRE-REPORT-MT5-TV-FULL-MARKET-001 | MT5 + TradingView full-market report bundle | DONE | CODEX/CLAUDE_CODE | commit `27828b8`; `10_REVIEW_REPORT.md` PASS; `realized_pnl` semantic fix landed with regression test; 254 tests pass | Start next task |
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
| QRE-NEXT-52 | CLI regression coverage for invalid `window_size` manifest metadata | DONE | CODEX/CLAUDE_CODE | commit `06d2b4b`; `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock string and boolean `window_size` at `report-files` / `report-audit` command boundaries; 201 passed in 1.90s | Preserve |
| QRE-NEXT-53 | CLI strict/JSON parity for `window_size` filters | DONE | CLAUDE_CODE | commit `ec7a1d0`; `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock `--window-size` with `--json --require-match` for matched/zero-match cases across `report-files` and `report-audit`; 205 passed in 1.94s | Preserve |
| QRE-NEXT-54 | CLI strict/JSON parity for `window_size` + `group_by` filters | DONE | CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock `--window-size` + `--group-by` combined selector parity with `--json --require-match`; 209 passed in 2.02s | Preserve |
| QRE-NEXT-55 | Real suspension/ST/risk-warning metadata | BLOCKED | CODEX | Data layer adapter ready; no upstream security-status table in `tushare_data`; `stock_daily` has no suspension/ST/risk-warning columns; set `QRE_SECURITY_METADATA_TABLE` to unblock | Await user-provided source table or upstream data producer plan |
| QRE-NEXT-56 | Tushare security-status smoke harness | DONE | CODEX | `scripts/tushare_security_smoke.py`; `stock_basic` and `suspend_d` smoke validation succeed, `stock_st` / `stk_alert` remain permission-blocked | Preserve; use as a read-only source-shape probe before bulk ingestion |
| QRE-NEXT-57 | Tushare security source adapter scaffold | DONE | CODEX | `src/quant_research_engine/data/tushare_security.py`; smoke script now delegates to a reusable wrapper; targeted unit tests passed | Preserve; use as the reusable source boundary for later bulk ingestion |
| QRE-NEXT-58 | Tushare security snapshot contract | DONE | CLAUDE_CODE | `SNAPSHOT_FIXED_COLUMNS`, `SecuritySnapshot`, `derive_board()`, `normalize_snapshot_frame()`; 17 targeted tests pass; smoke harness preserved | Preserve; reuse as the source boundary for later bulk ingestion |

## Latest Verified State

Recorded on 2026-05-21 after Claude Code implemented the full-market backtest report bundle for `QRE-REPORT-MT5-TV-FULL-MARKET-001`:

- Current task: `QRE-REPORT-MT5-TV-FULL-MARKET-001` — IMPLEMENTED
- Last finalized: `QRE-GUI-LOCAL-BACKTEST-CONSOLE-001` (commit `766dc98`)
- Implementation:
  - `src/quant_research_engine/portfolio/full_market_report.py` — ~350 lines with 11 report-building functions plus main entry point
  - `src/quant_research_engine/portfolio/io.py` — wired `write_full_market_report()` into `write_batch_result()`; updated role mapping and path listing
  - `src/quant_research_engine/portfolio/report_manifest.py` — 9 new required-column rules for new roles
  - `pyproject.toml` — added `openpyxl>=3.1.0`
  - `tests/test_full_market_report.py` — 23 tests across 12 test classes
  - `backtest_report.xlsx` — 10 sheets with bold headers
- Validation:
  - `uv run pytest tests/test_full_market_report.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q` → 254 passed, 2 warnings in 3.20s
  - `scripts/check-progress-docs.sh` → passed
  - `git diff --check` → passed
- Residual limitations:
  - Commission splits (commission, stamp_tax, transfer_fee, slippage) are null — current engine has single cost field
  - Margin fields null — cash-only simulation
  - Intratrade path fields null — A-share daily engine does not track intra-trade bar-level paths
  - Batch-only for first release; shared-cash reuse is future work
- Next step: Codex reviews the implementation, runs validation, and writes `docs/agent/10_REVIEW_REPORT.md`

Current GUI direction approved on 2026-05-21:

- Local browser console is the first GUI form.
- Strategy input is YAML text first, not drag-and-drop composition.
- Run history stays on the local filesystem in v1.
- The console should show summary, orders, trades, equity, and manifest artifacts.
- Direct module execution is the default; CLI fallback remains available.

Current strategy IO direction approved for design on 2026-05-21:

- QRE is the strategy IO contract, validation, backtest, and reporting engine.
- QRE should not rewrite `research-notes` or `strategy-research`.
- Strategy entry standardization is documentation-first: write MD guidance for how others should author QRE strategy entry files.
- External strategy projects can convert natural-language strategy descriptions into the QRE-standard entry format.
- `indicators_tushare` remains responsible for computing missing technical indicators or periods and writing them into `factors.*`.
- QRE should emit missing-factor requests rather than computing indicators internally.
- Report output should follow the MT5 report baseline while producing a single full-market report set with `symbol` columns, not per-stock report files.
- A future validation step must convert three existing strategy families into the standard entry format and run small-scope smoke tests with exit code `0`.

Current report-output direction approved on 2026-05-21:

- QRE should combine the MT5 report workbook baseline and TradingView strategy tester screenshots into one full-market report contract.
- Reports are full-market A-share artifacts with `symbol` columns, not one workbook per stock.
- Required additive files: `backtest_report.xlsx` (10 sheets), `trades_ledger.csv`, `round_trips.csv`, `symbol_performance.csv`, `strategy_performance.json`, `equity_curve.csv`, `drawdown_curve.csv`, `trade_analysis.json`, `capital_usage.json`, and `report_manifest.json`.
- First implementation omits rendered charts, but emits workbook sheets, CSV/JSON files, manifest roles, and audit/discovery behavior.
- Existing engineering artifacts and report-manifest behavior remain compatible.

User-requested strategy work in 2026-05-21:

- Added optional `signal.exit` support to the strategy spec and threaded it through single-symbol, batch, and shared-cash backtest requests so a strategy can schedule next-bar exits without lookahead.
- Verified with `uv run pytest tests/test_strategy_spec.py tests/test_portfolio_single_symbol.py tests/test_portfolio_shared.py -q` → 46 passed in 1.01s.
- Ran a full-market chunked backtest for the EMA200 + Bollinger strategy against `tushare_data` using `public.stock_daily` and `factors.*`.
  - Full-history chunked run: `2010-01-04` to `2026-05-20`
  - Universe: 5,522 symbols
  - Traded symbols: 4,957
  - Total trades: 17,233
  - Mean total return: 13.8446%
  - Median total return: 6.0678%
  - Positive-return symbol rate: 61.93%
  - Best symbol: `002706.SZ` at `+464.08%`
  - Worst symbol: `000576.SZ` at `-74.90%`
  - Total cost: `2,174,348.80`
  - Failed orders: `23`

## Completed Module Summary

- Data layer: read-only PostgreSQL adapter, factor catalog, research assembler, metadata fallback, benchmark-bar skeleton, preflight, real metadata passthrough adapters.
- Evaluation layer: safe expression signals, forward returns, event summaries, IC, Rank IC, quantile summaries, rough friction adjustment, metadata group summaries, durable output artifacts with manifests, random-baseline comparison, factor decay summaries.
- Portfolio layer: single-symbol, batch, shared-cash, costs, slippage, lot sizing, price-limit checks, risk exits, rebalance, FIFO lot accounting, T+1 sellability, failed-order diagnostics, analytics, batch metadata group-by passthrough, shared-cash metadata output passthrough, shared-cash row-level metadata group summaries, full-market backtest report bundle (trades ledger, round trips, symbol/strategy performance, equity/drawdown curves, trade analysis, capital usage, Excel workbook).
- Reporting: CSV/JSON/Markdown outputs, report manifests, manifest filtering, existence/content validation, strict audit/report-files matching, failed-order artifact schema validation, JSON audit/file-selection output, README and workflow documentation, manifest schema versioning with validation, schema version exposed in JSON tooling and ReportManifest helper, manifest file entry validation, CLI malformed-manifest regression coverage, manifest `files` shape validation, manifest root shape validation, missing top-level manifest field CLI regression coverage, top-level manifest field type CLI regression coverage, malformed manifest root CLI regression coverage, malformed manifest file entry CLI regression coverage, schema-version type CLI regression coverage, optional file-entry metadata type CLI regression coverage, optional `group_by` file-entry metadata CLI regression coverage, null optional metadata CLI regression coverage, null schema-version CLI regression coverage, `report-files --json --check-exists` CLI regression coverage, `report-files --json --validate-contents` CLI regression coverage, `report-audit --json` issue payload field CLI regression coverage, shared-cash failed-order diagnostics and summary analysis, portfolio backtest run-manifest reproducibility, evaluation metadata group summaries, eval-config output artifacts and manifests, evaluation random-baseline comparison, evaluation artifact usage docs, metadata grouping and passthrough usage docs, evaluation group-by manifest parity, grouped artifact `group_by` content consistency validation, batch grouped-artifact `group_by` header consistency validation, rolling-artifact `window_size` manifest filter parity, full-market report Excel workbook.

## Pending Work Summary

- Real index benchmark wiring after table/schema confirmation.
- Real suspension/ST/risk-warning time-varying metadata, pending a confirmed upstream table or higher Tushare permissions for `stock_st` / `stk_alert`.
- Canonical security-snapshot contract is complete; later bulk ingestion can reuse the Tushare source scaffold.
- Bulk ingestion / durable loading for the Tushare security source scaffold once the upstream source contract is settled.
- Industry, market-cap, liquidity, membership, and regime grouping across evaluation and shared-cash outputs.
- Larger research-run reproducibility workflow beyond run-ID linkage.
- Strategy IO contract implementation after design approval.
- Full-market report shared-cash support (currently batch-only).
- Full-market report charts.
- GUI parameter controls over the future standard strategy entry contract.

## Status Meaning

- TODO: Not started
- READY: Scoped and ready for the implementer
- WAITING_USER_APPROVAL: User approval required before the next agent proceeds
- IN_PROGRESS: Started but not complete
- IMPLEMENTED: Implemented by Claude Code, awaiting Codex review
- DESIGN_RECORDED: Design artifact exists and awaits review/approval
- READY_FOR_BRIEF: Direction is agreed but implementation brief is not yet written
- DONE: Completed and verified or preserved from legacy evidence
- BLOCKED: Blocked
- FUTURE: Future milestone

## Update Rules

- Mark DONE only with evidence.
- If code changed, update `04_TASK_HANDOFF.md` and this file.
- If a dual-agent phase changed, update `11_AGENT_STATE.md`.
- If architecture or major decisions changed, update `06_DECISION_LOG.md`.
