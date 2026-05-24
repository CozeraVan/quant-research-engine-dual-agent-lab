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
- Research-run manifest integration: `research_run_manifest` registered in `_RUN_MANIFEST_KINDS`, with a top-level `report_manifest.json` (kind `research_run_report_manifest`) for whole-run discovery and audit through `qre report-files` / `qre report-audit`.
- Shared-cash full-market report: `engine_mode` parameter on all 6 builders and entry point in `full_market_report.py`; wired into `write_shared_cash_result()` with updated manifest helpers; 19 new tests (6 test classes + 2 integration tests).
- Full-market report charts: equity curve and drawdown chart PNGs generated via matplotlib Agg backend; embedded as new Excel sheets via openpyxl; both batch and shared_cash modes produce charts; 10 new tests.
- GUI Strategy Builder (M8.6): form-based high-level strategy entry builder with compile-to-spec endpoint, indicator catalog, and run flow integration; 16 new tests.
- HTML backtest report: self-contained HTML report with embedded base64 charts, metric cards, PnL distribution, trade analysis, symbol performance, trades ledger, and round trips; integrated into batch and shared_cash report pipeline with direct tests.
- Strategy entry/exit standardization: `strategies/high_level/` and `strategies/low_level/` directories; Bollinger Band mean reversion template strategy; default strategy-smoke and GUI template paths migrated from deleted `examples/`; EMA200 typical source maps to the upstream `typical_price` table; chunked full-market backtest runner now writes `aggregate_summary.json`; README and active docs synced.

## In Progress

`QRE-RESEARCH-RUN-STAGE-MANIFEST-AUDIT-001` is briefed for Claude Code. It should recursively validate nested eval/backtest stage report manifests when auditing a top-level research-run `report_manifest.json`. `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` remains blocked on upstream data availability.

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
- Recent commits: `7d1e28d` (research-run root manifest finalization state), `0fb70f1` (research-run root manifest finalized)
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last verified full test: `803 passed, 2 warnings in 12.52s`

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

Implement `QRE-RESEARCH-RUN-ROOT-REPORT-MANIFEST-001` from `docs/agent/08_IMPLEMENTATION_BRIEF.md`, then hand back to Codex for review.
