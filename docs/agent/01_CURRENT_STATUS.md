# Current Status

## Current Stage

Advanced experimental MVP. The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, audit CLI, local browser console, strategy entry compiler, smoke runner, smoke discovery CLI, full-market backtest report, strategy IO contract, and research-run CLI orchestrator are implemented. The smoke discovery status enrichment series (22 flags) is complete.

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
- Real security metadata passthrough adapters for optional upstream status, industry, and membership-style columns.
- Batch backtest metadata group-by passthrough for optional upstream columns.
- Shared-cash metadata output passthrough for requested static metadata columns.
- Shared-cash row-level metadata group summaries for orders, trades, and failed orders.
- Evaluation factor decay summaries from existing IC and Rank IC outputs, including eval-config stdout, CSV artifact, and report-manifest validation.
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
- Research-run manifest integration: `research_run_manifest` registered in `_RUN_MANIFEST_KINDS`, discoverable through `qre report-files` and `qre report-audit`.
- Shared-cash full-market report: `engine_mode` parameter on all 6 builders and entry point in `full_market_report.py`; wired into `write_shared_cash_result()` with updated manifest helpers; 19 new tests (6 test classes + 2 integration tests).

## In Progress

No active implementation work. `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` remains blocked on upstream data availability. The reusable Tushare security source scaffold and canonical snapshot contract are complete and ready for future bulk ingestion work.

## Known Gaps

- Real index benchmark data-source wiring is not complete. Benchmark-relative code and data-loading skeleton exist, and temporary stock benchmark wiring exists.
- Time-varying suspension/ST/risk-warning metadata still depends on confirmed upstream source tables. Tushare `suspend_d` is available for smoke validation, but `stock_st` and `stk_alert` remain permission-gated.
- The reusable Tushare security source adapter exists, but the authoritative upstream security-status table is still missing.
- Benchmark membership, market-cap, liquidity bucket, and real regime grouping are not fully standardized across all research outputs.
- Evaluation layer does not yet implement real index benchmark comparison or real regime classification.

## Current Technical Stack

- Language: Python 3.10+
- Packaging: `pyproject.toml`, uv
- Database: PostgreSQL through SQLAlchemy and pandas
- CLI: argparse-based `qre`
- Config: YAML
- Test tools: pytest
- Frontend: local Flask browser console
- Deployment: local CLI/research workflows

## Current Repository Condition

- Git initialized: yes
- Current branch: `master`
- Remote configured: no remote shown by `git remote -v`
- Recent commits: `92f216d` (research-run orchestrator), `1c4b57e` (smoke discovery series complete)
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last verified full test: `519 passed, 2 warnings in 5.91s`

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

All known actionable gaps are either blocked on external data or marked future. No critical next step — user decides next direction.
