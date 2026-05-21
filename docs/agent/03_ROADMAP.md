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
| M7.1 | Local browser console shell and YAML strategy editor | READY | CLAUDE_CODE | user-approved brainstorm; `docs/superpowers/specs/2026-05-21-local-backtest-console-design.md` | Implement `qre gui` shell, YAML editor, and run controls |
| M7.2 | Local filesystem run history and rerun support | READY | CLAUDE_CODE | approved local-history-first design; `docs/agent/change_requests/CR-0001-local-backtest-console.md` | Persist run records under `outputs/gui-console/` |
| M7.3 | Result viewer for summary, orders, trades, equity, and manifests | READY | CLAUDE_CODE | approved full-artifact viewer scope | Render report artifacts from completed runs |

## Milestone 8: Strategy IO Contract And Research Reports

| ID | Task | Status | Owner | Evidence | Next Step |
|---|---|---|---|---|---|
| M8.1 | Strategy IO contract design | DESIGN_RECORDED | CODEX | `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md` | User review and approval |
| M8.2 | Strategy entry writing standard | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001` completed; `docs/strategy_entry/` added with strategy card, factor requirements, missing-factor request, experiment plan, and examples; `10_REVIEW_REPORT.md` PASS | Preserve; use as contract baseline for compiler/preflight tasks |
| M8.3 | Factor availability and missing-factor handoff standard | READY_FOR_BRIEF | CODEX | design spec defines QRE -> `indicators_tushare` missing-factor request fields | Scope compiler/preflight support after spec approval |
| M8.7 | Operational missing-factor handoff workflow | DONE | CODEX/CLAUDE_CODE | `QRE-FACTOR-MISSING-HANDOFF-STANDARD-001` implemented; `missing_factor_requests.json` emission, CLI preflight wiring, lifecycle docs, and tests landed; `10_REVIEW_REPORT.md` PASS | Preserve; extend to compiler linkage in next slice |
| M8.8 | High-level strategy entry compiler/preflight linkage | DONE | CODEX/CLAUDE_CODE | `QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001` implemented; `qre compile` added; alias-based expression fix landed with end-to-end runtime compatibility tests; `10_REVIEW_REPORT.md` PASS | Preserve; extend crossover/runtime richness in future slices |
| M8.4 | Three-strategy entry validation sample | READY_FOR_BRIEF | CODEX/CLAUDE_CODE | user requested 3 existing strategy families converted to standard entry and smoke-tested | Include in implementation acceptance criteria |
| M8.5 | MT5 + TradingView full-market report contract | DONE | CODEX/CLAUDE_CODE | commits `27828b8`, `febb73d`; `10_REVIEW_REPORT.md` PASS; full-market bundle and review/finalization complete | Preserve; expand shared-cash/charts in future slices |
| M8.6 | GUI parameter surface for standard strategy IO | FUTURE | CLAUDE_CODE | GUI is visualization only; standard contract must come first | Add form controls after entry/report contracts are stable |

## Status Meaning

- TODO: Not started
- READY: scoped and suitable for the next implementer
- DESIGN_RECORDED: design artifact exists and awaits review/approval
- READY_FOR_BRIEF: agreed direction exists but no implementation brief has been written
- IN_PROGRESS: Started but not complete
- DONE: Completed and verified or preserved from legacy records
- BLOCKED: Blocked by missing decision, data, or approval
- WAITING_USER_APPROVAL: Codex prepared a brief; user must approve before Claude Code implements
