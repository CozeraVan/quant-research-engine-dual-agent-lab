# Current Status

## Current Stage

Advanced experimental MVP. The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, audit CLI, and local browser console are implemented. Current active implementation focus is the full-market backtest report contract: combine the MT5 report baseline and TradingView strategy tester metrics into QRE report artifacts.

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

## In Progress

`QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` remains blocked on upstream data availability. The reusable Tushare security source scaffold and canonical snapshot contract are complete and ready for future bulk ingestion work.

`QRE-REPORT-MT5-TV-FULL-MARKET-001` is ready for Claude Code implementation. The report contract is documented in `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`.

## Known Gaps

- Real index benchmark data-source wiring is not complete. Benchmark-relative code and data-loading skeleton exist, and temporary stock benchmark wiring exists.
- Time-varying suspension/ST/risk-warning metadata still depends on confirmed upstream source tables. Tushare `suspend_d` is available for smoke validation, but `stock_st` and `stk_alert` remain permission-gated.
- The reusable Tushare security source adapter exists, but the authoritative upstream security-status table is still missing.
- The canonical security-snapshot contract is complete on top of the reusable source scaffold.
- Benchmark membership, market-cap, liquidity bucket, and real regime grouping are not fully standardized across all research outputs.
- Evaluation layer does not yet implement real index benchmark comparison or real regime classification.
- Larger research-run bundles beyond run-level identifier linkage are not yet standardized.
- Strategy entry is not yet standardized beyond the current low-level YAML `StrategySpec`.
- Full-market MT5/TradingView-style report bundles are not yet implemented; current report files are useful engineering artifacts but not the final research-facing report contract.

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
- Recent commits: `2da15bb`, `ec7a1d0`
- Test command: `uv run pytest -q`
- Progress-doc check: `scripts/check-progress-docs.sh`
- Git finalization check: `scripts/git-finalize-check.sh`
- Last legacy-recorded full test: `156 passed in 1.30s`

## Current CLI Surface

- `qre profile`
- `qre db-smoke`
- `qre factor-smoke`
- `qre metadata-smoke`
- `qre benchmark-smoke`
- `qre preflight`
- `qre eval-smoke`
- `qre eval-config`
- `qre backtest-single`
- `qre backtest-batch`
- `qre backtest-shared`
- `qre report-files`
- `qre report-audit`

## Next Recommended Step

Claude Code implements `QRE-REPORT-MT5-TV-FULL-MARKET-001` from `08_IMPLEMENTATION_BRIEF.md`. Keep `QRE-DATA-REAL-SUSPENSION-ST-RISK-WARNING-METADATA-001` blocked until the upstream security metadata source table/schema is confirmed.
