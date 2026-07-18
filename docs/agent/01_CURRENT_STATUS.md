# Current Status

## Current Stage

Feature-complete engine in maintenance mode, under single-agent development since 2026-07-18.

The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, audit CLI, local browser console, strategy entry compiler, smoke runner, smoke discovery CLI, full-market backtest report, strategy IO contract, and research-run CLI orchestrator are implemented. Benchmark/reference read-side wiring, cross-sectional market-cap/liquidity metadata standardization, the portfolio baseline-comparison slice, benchmark report-artifact propagation, full-market workbook parity, deterministic regime classification, benchmark-aware regime source preference, and benchmark series wiring into evaluation frames are complete and accepted. As-of metadata snapshot wiring, benchmark membership/industry adapters, benchmark/reference read-side wiring, and strategy-entry pipeline hardening are complete.

On top of the frozen engine, a user-directed strategy catalog batch backtest (`QRE-STRATEGY-CATALOG-BATCH-BACKTEST-001`) was completed on 2026-05-30: 111 catalog strategies generated, 106 ran OK, 5 blocked on missing factor columns. That work is **not yet committed to git** (see `11_AGENT_STATE.md` Git State).

On 2026-07-18 the project switched from the dual-agent workflow (Codex + Claude Code) to single-agent development by Kimi Code (`QRE-SINGLE-AGENT-MIGRATION-001`); the earlier "fully frozen, no further work" closeout wording was stale and has been corrected. Tushare download/ingestion work is owned by sibling `quant_ts`, not QRE.

## Completed

- Python src-layout package under `src/quant_research_engine`.
- CLI entry point `qre`.
- Market profile loading, including A-share daily default YAML.
- Read-only PostgreSQL data access for daily bars, factors, metadata fallback, calendar, and benchmark-bar skeleton.
- Research-frame assembly from market bars plus declared factor fields.
- Read-only preflight checks for market/factor/join/metadata/universe/liquidity/benchmark availability.
- Safe expression evaluation, forward returns, event summaries, IC, Rank IC, quantile returns, rough friction-adjusted screening, metadata group summaries, deterministic random-baseline comparison, and factor decay summaries.
- Single-symbol, independent batch, and shared-cash portfolio backtests.
- A-share costs, lot sizing, price-limit validation, percent slippage, risk exits, rebalance, FIFO lot accounting, and T+1 sellable inventory in shared-cash simulation.
- Portfolio analytics, benchmark-relative analytics interface, Markdown/CSV/JSON outputs, report manifests, report discovery, and report audit.
- Shared-cash failed-order diagnostics and summary analysis.
- Portfolio backtest run manifests for reproducible output directories.
- Deterministic random-baseline comparison for evaluation output quality.
- Full-market workbook `Performance` sheet parity with `strategy_perf`.
- Real security metadata passthrough adapters for optional upstream status, industry, and membership-style columns.
- Batch backtest metadata group-by passthrough for optional upstream columns.
- Shared-cash metadata output passthrough for requested static metadata columns.
- Shared-cash row-level metadata group summaries for orders, trades, and failed orders.
- Evaluation factor decay summaries from existing IC and Rank IC outputs, including eval-config stdout, CSV artifact, and report-manifest validation.
- Real regime classification and regime summary outputs.
- Benchmark-aware regime source preference (`benchmark_close` / `benchmark_return` precedence when present in-frame).
- Optional run-level identifiers across preflight JSON, evaluation run manifests, and portfolio run manifests.
- Run manifest content validation in report audit, including required-field, kind, type, artifacts, and present-null checks.
- Local browser backtest console (`qre gui`) with YAML strategy editor, run history, rerun support, and artifact viewer.
- Strategy entry authoring standard (`docs/strategy_entry/`): strategy card, factor requirements, missing-factor request, experiment plan, and examples.
- Operational missing-factor handoff: `missing_factor_requests.json` emission, CLI preflight wiring, lifecycle docs.
- High-level strategy entry compiler: `qre compile` with alias-based expression resolution, indicator catalog, and preflight integration.
- Three-strategy entry validation: RSI2, EMA200+Bollinger, MACD entries compile and smoke-tested.
- Smoke runner automation: `qre strategy-smoke` one-command orchestration with deterministic `smoke_summary.json`.
- Smoke manifest/audit integration: `smoke_report_manifest.json` with report discovery/audit parity.
- Smoke discovery CLI: `qre smoke-files` with text/JSON modes, selectors, and 22 status enrichment flags.
- Full-market MT5/TradingView-aligned report bundle: `backtest_report.xlsx` (10 sheets), trades ledger, round trips, symbol/strategy performance, equity/drawdown curves, trade analysis, capital usage.
- Research-run CLI orchestrator: `qre research-run` chains preflight → eval → backtest under one `--run-id` with `research_run_manifest.json`.
- Research-run manifest integration: `research_run_manifest` registered in `_RUN_MANIFEST_KINDS`, with a top-level `report_manifest.json` (kind `research_run_report_manifest`) for whole-run discovery and audit through `qre report-files` / `qre report-audit`.
- Shared-cash full-market report: `engine_mode` parameter on all 6 builders and entry point in `full_market_report.py`; wired into `write_shared_cash_result()` with updated manifest helpers; 19 new tests (6 test classes + 2 integration tests).
- Full-market report charts: equity curve and drawdown chart PNGs generated via matplotlib Agg backend; embedded as new Excel sheets via openpyxl; both batch and shared_cash modes produce charts; 10 new tests.
- Portfolio baseline comparison outputs: single-symbol, batch, CLI, and full-market summary wiring expose buy-and-hold comparison metrics and optional benchmark-relative summary fields.
- Benchmark report-artifact propagation: `strategy_performance.json` now carries the batch benchmark section through to the durable report payload.
- GUI Strategy Builder (M8.6): form-based high-level strategy entry builder with compile-to-spec endpoint, indicator catalog, and run flow integration; 16 new tests.
- HTML backtest report: self-contained HTML report with embedded base64 charts, metric cards, PnL distribution, trade analysis, symbol performance, trades ledger, and round trips; integrated into batch and shared_cash report pipeline with direct tests.
- Research-run stage manifest recursive audit: `validate_contents()` on `research_run_report_manifest` now recursively validates nested eval/backtest stage report manifests via `_validate_nested_report_manifest()`; 7 unit + 4 CLI tests added; full suite at 814 passed.
- Research-run preflight report content audit: `validate_contents()` on `research_run_report_manifest` now validates `preflight_report` JSON content via `_validate_preflight_report()`; checks `status` (non-empty string), `checks` and `missing_factor_requests` (lists if present); 9 unit + 3 CLI tests added; full suite at 826 passed.
- Research-run audit role selector parity: 10 CLI regression tests lock `report-files` / `report-audit` role behavior for root research-run manifests across JSON/text output and `--require-match`; full suite at 836 passed.
- Strategy entry/exit standardization: `strategies/high_level/` and `strategies/low_level/` directories; Bollinger Band mean reversion template strategy; default strategy-smoke and GUI template paths migrated from deleted `examples/`; EMA200 typical source maps to the upstream `typical_price` table; chunked full-market backtest runner now writes `aggregate_summary.json`; README and active docs synced.
- Research-run preflight report shape audit: `_validate_preflight_report()` hardened to validate `status` values (`ok`, `warning`, `error`) and `checks[]` item object shape (`name`, `status`, `message`); new issue codes `invalid_preflight_report_check` and `missing_preflight_report_check_field`; 13 new tests; review PASS.
- Research-run preflight missing-factor shape audit: `_validate_preflight_report()` hardened to validate `missing_factor_requests[]` item object shape (`strategy_id`, `alias`, `indicator`, `expected_table`, `expected_column`, `date_range`, `reason`, `required`); new issue codes `invalid_preflight_report_missing_factor_request` and `missing_preflight_report_missing_factor_field`; 14 new tests; review PASS; full suite at 863 passed.
- Reference-data ingestion ownership migrated to sibling `quant_ts`; QRE reads populated reference tables only.
- Backtest-smoke truthiness reconciliation: `_try_backtest_smoke()` executes real `BatchBacktestEngine` runs; tracker entry moved from IMPLEMENTED to DONE; all agent docs aligned.
- `QRE-NEXT-55` tracker reconciliation: roadmap M4.9 was already DONE; progress row reconciled from IMPLEMENTED to DONE; all agent docs aligned.
- Strategy catalog batch backtest (`QRE-STRATEGY-CATALOG-BATCH-BACKTEST-001`, user-directed): 111 low-level strategy YAMLs across 7 categories under `strategies/catalog/`; `scripts/batch_preflight_check.py` and `scripts/batch_backtest_runner.py` built; expression parser in `signals.py` extended (`&`/`|`, method chaining, arithmetic); `research_run.py` bugs fixed; smoke-mode batch of 106 strategies completed 2026-05-30 (~11.5h, batch `61e67b53b644`): 106 OK / 5 error (missing factor columns `atr_10`, `sma_50`, `sma_9/26/52`, `sma_7/20/65`). Results: mean return -0.79% (2-month smoke window, not a research conclusion). **Uncommitted.**

## In Progress

- `QRE-SINGLE-AGENT-MIGRATION-001`: migration of the workflow documentation from dual-agent to single-agent (Kimi Code) mode.

## Known Gaps

- Benchmark membership and industry classification are standardized for the current MVP slice using latest-available snapshots. Time-varying history is out of scope for the current closeout.
- Full as-of time-varying history for cross-sectional metadata is out of scope for the current closeout.
- The reusable Tushare security source adapter remains as historical source-shape context only. All download/ingest work belongs in `quant_ts`, not QRE.
- Benchmark series wiring is complete and accepted; manifests record benchmark parameters and CLI enforces paired-arg validation.
- As-of metadata snapshot wiring is implemented and all three fix passes are complete; all backtest entry points (single, batch, shared) now accept and propagate `--metadata-as-of`; finalized in commit `7c32b65`.
- The strategy catalog batch backtest used a 2-month smoke window (2024-01-01 to 2024-03-01); results validate plumbing only and are not research conclusions (R-QRE-008). Quick (1-year) and full (2015-2025) batch modes have not been run.
- 5 catalog strategies are blocked on missing DB factor columns (`atr_10`, `sma_50`, `sma_9`, `sma_26`, `sma_52`, `sma_7`, `sma_20`, `sma_65`); factor computation belongs to upstream `indicators_tushare` / `quant_ts`.
- The GUI console (`qre gui`) is implemented but has no real runs recorded yet (`outputs/gui-console/runs/` is empty).

## Current Technical Stack

- Language: Python 3.10+
- Packaging: `pyproject.toml`, uv
- Database: PostgreSQL through SQLAlchemy and pandas
- CLI: argparse-based `qre`
- Config: YAML
- Test tools: pytest
- Frontend: local Flask browser console
- Deployment: local CLI/research workflows
- Development workflow: single-agent (Kimi Code) with `docs/agent/` as long-term memory

## Current Repository Condition

- Git initialized: yes
- Current branch: `master`
- Remote configured: no remote shown by `git remote -v`
- Recent commits: `33bb175` (resolve stale decision-log items), `9d41ce7` (finalize onboarding agent state), `0c4bbcf` (bilingual GUI templates), `abac8de` (fix GUI default template), `c7353aa` (Chinese annotations in low-level strategy YAMLs)
- Uncommitted: `Makefile`, `evaluation/signals.py`, `orchestration/research_run.py` modified; `scripts/batch_backtest_runner.py`, `scripts/batch_preflight_check.py`, `scripts/generate_strategy_yamls.py`, `strategies/catalog/` untracked (batch backtest work products)
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last verified full test run: `947 passed` (2026-05-30)

## Current CLI Surface

- `qre profile`
- `qre db-smoke`
- `qre factor-smoke`
- `qre metadata-smoke`
- `qre benchmark-smoke`
- `qre preflight`
- `qre eval-smoke`
- `qre eval-config`
- `qre compile`
- `qre strategy-smoke`
- `qre smoke-files`
- `qre backtest-single`
- `qre backtest-batch`
- `qre backtest-shared`
- `qre report-files`
- `qre report-audit`
- `qre gui`
- `qre research-run`

## Next Recommended Step

Pending user decision among:

1. Approve git finalization of the uncommitted strategy catalog batch backtest work products.
2. Commission upstream factor computation (`atr_10`, `sma_7/9/20/26/50/52/65`) in `indicators_tushare` / `quant_ts` to unblock the 5 remaining catalog strategies.
3. Run deeper validation batches (`--mode quick` 1-year / `--mode full` 2015-2025) once results are meant to inform research.
4. Any new change request through the single-agent workflow.
