# Roadmap

## Milestone 1: Project Skeleton And Core Interfaces

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M1.1 | Python package skeleton | DONE | HISTORICAL | `src/quant_research_engine`, `pyproject.toml`, tests | Preserve |
| M1.2 | Core models and A-share market profile | DONE | HISTORICAL | `core/models.py`, `markets/ashare.py`, profile config | Preserve |
| M1.3 | CLI smoke foundation | DONE | HISTORICAL | `qre` CLI | Preserve |

## Milestone 2: Data Layer And Preflight

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M2.1 | Read daily market bars | DONE | HISTORICAL | `PostgresDataStore.load_daily_bars` | Preserve |
| M2.2 | Read factor columns from `factors.*` | DONE | HISTORICAL | factor catalog and assembler | Preserve |
| M2.3 | Metadata fallback and board inference | DONE | HISTORICAL | `load_security_metadata`, `derive_board` | Replace fallback with real metadata when available |
| M2.4 | Read-only broad-run preflight | DONE | HISTORICAL | `qre preflight` | Integrate into larger run acceptance workflow |
| M2.5 | Real status/industry/membership adapters | DONE | CODEX/CLAUDE_CODE | local finalization commit; 278 tests passed; metadata source-table passthrough columns preserved with fixed-column fallback normalization | Preserve; time-varying status tables remain future work |
| M2.6 | Tushare security-status smoke harness | DONE | CODEX | `scripts/tushare_security_smoke.py`; `stock_basic` and `suspend_d` smoke validation succeed, `stock_st` / `stk_alert` remain permission-blocked | Preserve; use as a read-only source-shape probe before bulk ingestion |
| M2.7 | Tushare security source adapter scaffold | DONE | CODEX | `src/quant_research_engine/data/tushare_security.py`; smoke script now reuses a shared source wrapper; targeted unit tests passed | Preserve; reuse for future bulk ingestion and endpoint-specific probes |
| M2.8 | Tushare security snapshot contract | DONE | CLAUDE_CODE | `src/quant_research_engine/data/tushare_security.py`; canonical snapshot contract, normalized frame helper, and targeted tests landed; 34 tests passed | Preserve; reuse as the source boundary for later bulk ingestion |

## Milestone 3: Evaluation Engine

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M3.1 | Safe expression signals | DONE | HISTORICAL | `evaluation/signals.py` tests | Preserve |
| M3.2 | Event study and forward returns | DONE | HISTORICAL | `evaluation/engine.py` tests | Preserve |
| M3.3 | IC, Rank IC, quantile return | DONE | HISTORICAL | legacy progress records, tests | Preserve |
| M3.4 | Rough friction-adjusted screening | DONE | HISTORICAL | `round_trip_cost_rate`, market-profile estimate | Preserve |
| M3.5 | Regime and metadata group summaries | DONE | CODEX/CLAUDE_CODE | commit `b25cbd7`; 255 tests passed; evaluation metadata group summaries implemented | Preserve; real regime classification can follow later |
| M3.6 | Benchmark/random-baseline comparison for evaluation | DONE | CODEX/CLAUDE_CODE | commit `495185b`; 274 tests passed; deterministic random-baseline comparison implemented with seed-controlled CLI output and report-manifest validation | Preserve; benchmark wiring remains blocked until table/schema confirmation |
| M3.7 | Factor decay summary | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 324 tests passed; `factor_decay_summary` generated from IC/Rank IC horizons and emitted through eval-config artifacts/manifests | Preserve |

## Milestone 4: Portfolio Engine

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M4.1 | Single-symbol long-only backtest | DONE | HISTORICAL | `portfolio/single_symbol.py` | Preserve |
| M4.2 | Independent batch backtest | DONE | HISTORICAL | `portfolio/batch.py` | Preserve |
| M4.3 | Shared-cash multi-symbol backtest | DONE | HISTORICAL | `portfolio/shared.py` | Preserve |
| M4.4 | Costs, slippage, lot sizing, price-limit checks | DONE | HISTORICAL | A-share market profile and tests | Preserve |
| M4.5 | Risk exits, weights, rebalance | DONE | HISTORICAL | risk/weights/rebalance docs and tests | Preserve |
| M4.6 | FIFO lot accounting and T+1 sellable inventory | DONE | HISTORICAL | legacy progress: `156 passed` | Preserve |
| M4.7 | Stronger failed-order diagnostics | DONE | CODEX/CLAUDE_CODE | local review passed; 238 tests passed; side-level failed-order summary diagnostics added | Preserve |
| M4.8 | Real index benchmark wiring | BLOCKED | USER/CODEX | table/schema not confirmed | Confirm available index table and columns |
| M4.9 | Real suspension/ST/risk-warning metadata | BLOCKED | CLAUDE_CODE | fallback currently static unless data provided; source table confirmation pending | Confirm source table/schema and wire real metadata adapter if available |
| M4.10 | Batch metadata passthrough group-by | DONE | CODEX/CLAUDE_CODE | 283 tests passed; `summary_metadata_columns` added to batch requests; CLI `--group-by` columns flow into batch summaries | Preserve |
| M4.11 | Shared-cash metadata output passthrough | DONE | CODEX/CLAUDE_CODE | 293 tests passed; `metadata_columns` added to shared-cash requests; output rows carry requested metadata without overwriting canonical fields | Preserve |
| M4.12 | Shared-cash metadata group summaries | DONE | CODEX/CLAUDE_CODE | 315 tests passed; `backtest-shared --group-by` writes row-based grouped order/trade/failed-order CSVs with manifest validation | Preserve |

## Milestone 5: Reporting And Reproducibility

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M5.1 | CSV/JSON/Markdown report outputs | DONE | HISTORICAL | portfolio IO docs | Preserve |
| M5.2 | Report manifests | DONE | HISTORICAL | `report_manifest.json` | Preserve |
| M5.3 | Report discovery and audit CLI | DONE | HISTORICAL | `qre report-files`, `qre report-audit` | Use in acceptance checks |
| M5.4 | Strict zero-match report audit | DONE | HISTORICAL | `--require-match` | Preserve |
| M5.5 | Larger research-run reproducibility workflow | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 330 tests passed; optional `--run-id` links preflight/eval/backtest durable JSON outputs | Preserve; larger orchestration can follow later |
| M5.6 | Run manifest content validation | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 346 tests passed; `run_manifest` content validation catches missing/invalid fields and present-null non-nullable fields | Preserve |
| M5.7 | Run manifest usage documentation | DONE | CODEX/CLAUDE_CODE | commit `ccb80e8`; README/module docs cover `--run-id` and run-manifest audit usage | Preserve |
| M5.8 | Evaluation artifact usage documentation | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; README, data-layer docs, and workflow docs cover eval-config artifacts, report roles, audit usage, deterministic random baseline, and factor decay wording | Preserve |
| M5.9 | Metadata grouping usage documentation | DONE | CODEX/CLAUDE_CODE | commit `a59c1a4`; `10_REVIEW_REPORT.md` PASS; README plus module docs cover eval/batch/shared metadata grouping, shared-cash passthrough, grouped roles, and discovery/audit patterns | Preserve |
| M5.10 | Evaluation group-by manifest parity | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; per-column `group_summary_by_<col>.csv` files plus evaluation manifest `group_by` metadata; 164 targeted tests passed | Preserve |
| M5.11 | Evaluation group-by parity documentation | DONE | CODEX/CLAUDE_CODE | commit `5fc7605`; `10_REVIEW_REPORT.md` PASS; README plus module docs cover combined/per-column evaluation grouped artifacts and `--group-by` discovery/audit usage | Preserve |
| M5.12 | Grouped artifact `group_by` audit consistency | DONE | CODEX/CLAUDE_CODE | commit `a3768fb`; `10_REVIEW_REPORT.md` PASS; grouped eval/shared `group_by` mismatch checks now run only after required-column validation passes; 175 targeted tests passed | Preserve |
| M5.13 | Batch grouped-artifact `group_by` header consistency | DONE | CODEX/CLAUDE_CODE | commit `de37afd`; `10_REVIEW_REPORT.md` PASS; batch grouped manifest `group_by` metadata now requires matching CSV header columns; 183 targeted tests passed | Preserve |
| M5.14 | Rolling-artifact `window_size` filter parity | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; batch/shared rolling manifest metadata `window_size` now filters through report discovery/audit and surfaces in `report-files --json`; 197 targeted tests passed | Preserve |
| M5.15 | Rolling-artifact `window_size` usage documentation | DONE | CODEX/CLAUDE_CODE | commit `22fd3d1`; `10_REVIEW_REPORT.md` PASS; README and portfolio module docs now cover `--window-size` discovery/audit usage, `--window` vs `--window-size`, and additive JSON metadata wording | Preserve |
| M5.16 | CLI regression coverage for invalid `window_size` manifest metadata | DONE | CODEX/CLAUDE_CODE | commit `06d2b4b`; `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock string and boolean `window_size` at `report-files` / `report-audit` command boundaries; 201 targeted tests passed | Preserve |
| M5.17 | CLI strict/JSON parity for `window_size` filters | DONE | CLAUDE_CODE | commit `ec7a1d0`; `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock `--window-size` with `--json --require-match` for matched/zero-match cases across `report-files` and `report-audit`; 205 tests passed | Preserve |
| M5.18 | CLI strict/JSON parity for `window_size` + `group_by` filters | DONE | CLAUDE_CODE | commit `ec7a1d0`; `10_REVIEW_REPORT.md` PASS; 4 CLI regression tests lock `--window-size` + `--group-by` combined selector parity with `--json --require-match`; 209 tests passed | Preserve |

## Milestone 6: Dual-Agent Workflow

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M6.1 | Initialize dual-agent docs | DONE | USER/SCRIPT | commit `77fec02` | Preserve |
| M6.2 | Migrate legacy project knowledge into `docs/agent` | DONE | CODEX | current doc migration | User review |
| M6.3 | First post-migration implementation brief | WAITING_USER_APPROVAL | USER | `08_IMPLEMENTATION_BRIEF.md` | Approve or revise |

## Milestone 7: Local Backtest Console

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M7.1 | Local browser console shell and YAML strategy editor | DONE | CLAUDE_CODE | `QRE-GUI-LOCAL-BACKTEST-CONSOLE-001` finalized; 179 GUI/CLI tests; editor, rerun, artifact viewer, summary.json | Preserve |
| M7.2 | Local filesystem run history and rerun support | DONE | CLAUDE_CODE | Run records persisted under `outputs/gui-console/`; rerun YAML restoration verified | Preserve |
| M7.3 | Result viewer for summary, orders, trades, equity, and manifests | DONE | CLAUDE_CODE | Full-artifact viewer renders report artifacts from completed runs | Preserve |

## Milestone 8: Strategy IO Contract And Research Reports

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M8.1 | Strategy IO contract design | DONE | CODEX | `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`; all contract components implemented (docs, compiler, missing-factor, smoke runner, full-market report, GUI) | Preserve |
| M8.2 | Strategy entry writing standard | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001` completed; `docs/strategy_entry/` added with strategy card, factor requirements, missing-factor request, experiment plan, and examples; `10_REVIEW_REPORT.md` PASS | Preserve; use as contract baseline for compiler/preflight tasks |
| M8.3 | Factor availability and missing-factor handoff standard | DONE | CODEX/CLAUDE_CODE | `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` + `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` finalized; missing-factor emission, CLI preflight wiring, lifecycle docs, compiler linkage all complete | Preserve |
| M8.7 | Operational missing-factor handoff workflow | DONE | CODEX/CLAUDE_CODE | `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` implemented; `missing_factor_requests.json` emission, CLI preflight wiring, lifecycle docs, and tests landed; `10_REVIEW_REPORT.md` PASS | Preserve; extend to compiler linkage in next slice |
| M8.8 | High-level strategy entry compiler/preflight linkage | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` implemented; `qre compile` added; alias-based expression fix landed with end-to-end runtime compatibility tests; `10_REVIEW_REPORT.md` PASS | Preserve; extend crossover/runtime richness in future slices |
| M8.4 | Three-strategy entry validation sample | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-ENTRY-THREE-SMOKE-001` finalized; three strategy entries compile; smoke artifacts and consolidated report recorded; no-DB skip path documented | Preserve as baseline |
| M8.9 | Three-strategy smoke runner automation | DONE | CODEX/CLAUDE_CODE | Baseline automation slice accepted as precursor and expanded into full hardening lane | Preserve as precursor |
| M8.10 | Strategy-entry pipeline hardening package | DONE | CODEX/CLAUDE_CODE | `qre strategy-smoke` + deterministic `smoke_summary.json` + CLI/tests/docs; all sub-items (truthiness, artifact parity, manifest/audit, filter parity, discovery CLI, latest, stability, details, output export, check-exists, require-match, list-missing, quiet, status enrichment 22 flags) finalized and committed in `1c4b57e` | Preserve as baseline |
| M8.11 | Backtest-smoke truthiness fix | DONE | CODEX/CLAUDE_CODE | Real `_try_backtest_smoke()` execution path landed; false PASS removed; regression tests added | Preserve as baseline |
| M8.12 | Smoke-run artifact parity and summary clarity | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-ARTIFACT-PARITY-001` finalized with PASS review | Preserve as baseline |
| M8.13 | Smoke manifest and audit contract | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-MANIFEST-AUDIT-001` finalized with PASS review | Preserve as baseline |
| M8.14 | Smoke manifest filter parity regression coverage | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-MANIFEST-FILTER-PARITY-001` finalized with PASS review | Preserve as baseline |
| M8.15 | Smoke discovery CLI ergonomics | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-DISCOVERY-CLI-001` finalized with PASS review | Preserve as baseline |
| M8.16 | Smoke discovery latest-run ergonomics | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-DISCOVERY-LATEST-001` finalized with PASS review | Preserve as baseline |
| M8.17 | Smoke discovery output stability hardening | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-SMOKE-DISCOVERY-STABILITY-001` finalized with PASS review | Preserve as baseline |
| M8.18 | Smoke discovery details view ergonomics | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--details` detailed per-strategy output mode and tests finalized | Preserve as baseline |
| M8.19 | Smoke discovery output export | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--output-file` text/json export with parent-dir auto-create and write-failure exit handling | Preserve as baseline |
| M8.20 | Smoke discovery artifact existence audit | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--check-exists` plus missing-artifact diagnostics and regression tests finalized | Preserve as baseline |
| M8.21 | Smoke discovery strict selector require-match | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; strict selector no-match behavior finalized | Preserve as baseline |
| M8.22 | Smoke discovery list-missing output | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; script-friendly missing path listing finalized | Preserve as baseline |
| M8.23 | Smoke discovery quiet mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; quiet mode finalized | Preserve as baseline |
| M8.24 | Smoke discovery status-only mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; status-only compact output finalized | Preserve as baseline |
| M8.25 | Smoke discovery status-file mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; status-file persistence finalized | Preserve as baseline |
| M8.26 | Smoke discovery status-format mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; status-format mode finalized | Preserve as baseline |
| M8.27 | Smoke discovery status-reason mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; status-reason mode finalized | Preserve as baseline |
| M8.28 | Smoke discovery status-code mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; status-code mode finalized | Preserve as baseline |
| M8.29 | Smoke discovery status-meta mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-meta` landed with validation and docs | Preserve as baseline |
| M8.30 | Smoke discovery status-summary mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-summary` landed with validation and docs | Preserve as baseline |
| M8.31 | Smoke discovery status-fail-key mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-fail-key` landed with validation and docs | Preserve as baseline |
| M8.32 | Smoke discovery status-fail-stage mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-fail-stage` landed with validation and docs | Preserve as baseline |
| M8.33 | Smoke discovery status-timestamp mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-timestamp` landed with validation and docs | Preserve as baseline |
| M8.34 | Smoke discovery status-output-dir mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-output-dir` landed with validation and docs | Preserve as baseline |
| M8.35 | Smoke discovery status-manifest-path mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-manifest-path` landed with validation and docs | Preserve as baseline |
| M8.36 | Smoke discovery status-manifest-exists mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-manifest-exists` landed with validation and docs | Preserve as baseline |
| M8.37 | Smoke discovery status-artifact-count mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-artifact-count` landed with validation and docs | Preserve as baseline |
| M8.38 | Smoke discovery status-strategy-count mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-strategy-count` landed with validation and docs | Preserve as baseline |
| M8.39 | Smoke discovery status-fail-count mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-fail-count` landed with validation and docs | Preserve as baseline |
| M8.40 | Smoke discovery status-skip-count mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-skip-count` landed with validation and docs | Preserve as baseline |
| M8.41 | Smoke discovery status-pass-count mode | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `--status-pass-count` landed with validation and docs | Preserve as baseline |
| M8.42 | Research-run CLI orchestrator | DONE | CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `qre research-run` chains preflight→eval→backtest under one `--run-id` with `research_run_manifest.json`; 476 tests passed | Preserve; expand run-bundle scope in future slices |
| M8.43 | Research-run manifest integration | DONE | CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `research_run_manifest` registered in `_RUN_MANIFEST_KINDS`; manifest emits standard run_manifest fields (schema_version, kind, command, strategy_path, artifacts); 1 new validation test; 477 tests passed | Preserve |
| M8.44 | Shared-cash full-market report support | DONE | CLAUDE_CODE | `engine_mode` parameter on all 6 builders and entry point in `full_market_report.py`; wired into `write_shared_cash_result()`; updated `_shared_manifest_role()` and `_shared_report_paths()` for 9 full-market roles; 19 new tests (17 unit + 2 integration); 519 tests passed | Preserve |
| M8.45 | Full-market report charts | DONE | CLAUDE_CODE | `generate_equity_curve_chart()` + `generate_drawdown_chart()`; embedded in Excel via openpyxl; manifest roles registered; 10 new tests; 529 tests passed | Preserve |
| M8.46 | Research-run stage artifact parity | DONE | CODEX/CLAUDE_CODE | commit `310f966`; `10_REVIEW_REPORT.md` PASS; preflight/eval/backtest stage artifacts persist and top-level artifacts are stage-qualified | Preserve |
| M8.47 | Research-run root report manifest | DONE | CLAUDE_CODE | `report_manifest.json` with kind `research_run_report_manifest`; `qre report-files`/`qre report-audit` accept the new manifest; `run_manifest` role validates provenance; stage entry points only when present; CLI prints `report_manifest=`; README paths synced; 803 tests passed | Preserve |
| M8.48 | Research-run stage manifest recursive audit | DONE | CLAUDE_CODE | commit `dcb4925`; Codex post-commit review PASS; recursive validation for eval/backtest stage manifests live; 7 unit + 4 CLI tests; 814 passed | Preserve |
| M8.49 | Research-run preflight report content audit | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; `_validate_preflight_report()` validates `status`/`checks`/`missing_factor_requests`; 9 unit + 3 CLI tests; 826 passed (+12) | Preserve |
| M8.50 | Research-run audit role selector parity | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; 10 CLI regression tests lock `report-files`/`report-audit` role selector behavior for root research-run manifests; 836 passed (+10) | Preserve |
| M8.51 | Research-run audit usage documentation | DONE | CODEX/CLAUDE_CODE | `10_REVIEW_REPORT.md` PASS; README section 10 expanded with role-specific audit examples; portfolio_workflow.md audit contract subsection added; portfolio_layer.md pointer added; full suite unchanged at 836 passed | Preserve |
| M8.5 | MT5 + TradingView full-market report contract | DONE | CODEX/CLAUDE_CODE | commits `27828b8`, `febb73d`; `10_REVIEW_REPORT.md` PASS; full-market bundle and review/finalization complete | Preserve; expand shared-cash/charts in future slices |
| M8.6 | GUI parameter surface for standard strategy IO | DONE | CLAUDE_CODE | Builder tab with high-level entry forms; compile endpoint; indicator catalog endpoint; run integration; 16 new tests; 770 passed; review PASS | Preserve |

## Status Meaning

- TODO: Not started
- READY: scoped and suitable for the next implementer
- DESIGN_RECORDED: design artifact exists and awaits review/approval
- READY_FOR_BRIEF: agreed direction exists but no implementation brief has been written
- IN_PROGRESS: Started but not complete
- DONE: Completed and verified or preserved from legacy records
- BLOCKED: Blocked by missing decision, data, or approval
- WAITING_USER_APPROVAL: Codex prepared a brief; user must approve before Claude Code implements
