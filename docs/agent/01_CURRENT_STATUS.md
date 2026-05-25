# Current Status

## Current Stage

Advanced experimental MVP. The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, audit CLI, local browser console, strategy entry compiler, smoke runner, smoke discovery CLI, full-market backtest report, strategy IO contract, and research-run CLI orchestrator are implemented. Benchmark/reference read-side wiring and cross-sectional market-cap/liquidity metadata standardization are now complete. Tushare download/ingestion work is owned by sibling `quant_ts`, not QRE.

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
- Research-run stage manifest recursive audit: `validate_contents()` on `research_run_report_manifest` now recursively validates nested eval/backtest stage report manifests via `_validate_nested_report_manifest()`; 7 unit + 4 CLI tests added; full suite at 814 passed.
- Research-run preflight report content audit: `validate_contents()` on `research_run_report_manifest` now validates `preflight_report` JSON content via `_validate_preflight_report()`; checks `status` (non-empty string), `checks` and `missing_factor_requests` (lists if present); 9 unit + 3 CLI tests added; full suite at 826 passed.
- Research-run audit role selector parity: 10 CLI regression tests lock `report-files` / `report-audit` role behavior for root research-run manifests across JSON/text output and `--require-match`; full suite at 836 passed.
- Strategy entry/exit standardization: `strategies/high_level/` and `strategies/low_level/` directories; Bollinger Band mean reversion template strategy; default strategy-smoke and GUI template paths migrated from deleted `examples/`; EMA200 typical source maps to the upstream `typical_price` table; chunked full-market backtest runner now writes `aggregate_summary.json`; README and active docs synced.
- Research-run preflight report shape audit: `_validate_preflight_report()` hardened to validate `status` values (`ok`, `warning`, `error`) and `checks[]` item object shape (`name`, `status`, `message`); new issue codes `invalid_preflight_report_check` and `missing_preflight_report_check_field`; 13 new tests; review PASS.
- Research-run preflight missing-factor shape audit: `_validate_preflight_report()` hardened to validate `missing_factor_requests[]` item object shape (`strategy_id`, `alias`, `indicator`, `expected_table`, `expected_column`, `date_range`, `reason`, `required`); new issue codes `invalid_preflight_report_missing_factor_request` and `missing_preflight_report_missing_factor_field`; 14 new tests; review PASS; full suite at 863 passed.
- Reference-data ingestion ownership migrated to sibling `quant_ts`; QRE reads populated reference tables only.

## In Progress

- (none)

## Known Gaps

- Benchmark membership and real regime grouping are not fully standardized across all research outputs.
- Full as-of time-varying history for cross-sectional metadata remains a future enhancement.
- The reusable Tushare security source adapter remains as historical source-shape context only. Future download/ingest changes belong in `quant_ts`, not QRE.
- Evaluation layer does not yet implement real regime classification.

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
- Recent commits: `9e00f0a` (research-run audit usage docs), `a027d69` (research-run audit role selector parity)
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last verified targeted tests: `35 passed`, `6 passed`, and `427 passed` across the current finalize checks

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

No active implementation slice is queued. The current QRE slice is complete and reviewed. When the next task is defined, update `08/09/11/12` together before assigning it to Claude Code.
