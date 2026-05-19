# Current Status

## Current Stage

Advanced experimental MVP. The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, and audit CLI are implemented. Current development focus is portfolio realism and run reproducibility.

## Completed

- Python src-layout package under `src/quant_research_engine`.
- CLI entry point `qre`.
- Market profile loading, including A-share daily default YAML.
- Read-only PostgreSQL data access for daily bars, factors, metadata fallback, calendar, and benchmark-bar skeleton.
- Research-frame assembly from market bars plus declared factor fields.
- Read-only preflight checks for market/factor/join/metadata/universe/liquidity/benchmark availability.
- Safe expression evaluation, forward returns, event summaries, IC, Rank IC, quantile returns, and rough friction-adjusted screening.
- Single-symbol, independent batch, and shared-cash portfolio backtests.
- A-share costs, lot sizing, price-limit validation, percent slippage, risk exits, rebalance, FIFO lot accounting, and T+1 sellable inventory in shared-cash simulation.
- Portfolio analytics, benchmark-relative analytics interface, Markdown/CSV/JSON outputs, report manifests, report discovery, and report audit.
- Shared-cash failed-order diagnostics and summary analysis.
- Portfolio backtest run manifests for reproducible output directories.

## In Progress

- Phase 4 portfolio realism and validation workflow improvements.
- Shared-cash failed-order diagnostics and summary analysis completed.
- Portfolio backtest run-manifest reproducibility completed.
- Migration from legacy project docs into `docs/agent` as the authoritative dual-agent entry point.

## Known Gaps

- Real index benchmark data-source wiring is not complete. Benchmark-relative code and data-loading skeleton exist, and temporary stock benchmark wiring exists.
- Real suspension, ST, and risk-warning state still need reliable time-varying metadata sources.
- Industry, benchmark membership, market-cap, liquidity bucket, and regime grouping are not fully wired.
- Evaluation layer does not yet implement regime split, industry/board/market-cap grouping, benchmark comparison, random baseline, or factor decay.
- Larger research-run bundles across preflight, evaluation, and backtest outputs are not yet standardized.

## Current Technical Stack

- Language: Python 3.10+
- Packaging: `pyproject.toml`, uv
- Database: PostgreSQL through SQLAlchemy and pandas
- CLI: argparse-based `qre`
- Config: YAML
- Test tools: pytest
- Frontend: none
- Deployment: local CLI/research workflows

## Current Repository Condition

- Git initialized: yes
- Current branch: `master`
- Remote configured: no remote shown by `git remote -v`
- Recent commits: `77fec02`, `7657cd1`
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

Select the next implementation brief for Claude Code when a new portfolio subtask is ready.

Real index benchmark wiring should remain a follow-up after the available index table, schema, code column, and value column are confirmed.
