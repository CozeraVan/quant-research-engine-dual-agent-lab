# Current Status

## Current Stage

Advanced experimental MVP. The skeleton, data layer, evaluation MVP, portfolio MVP, reporting, manifests, and audit CLI are implemented. Current development focus is portfolio realism, metadata-aware outputs, and broader research-run reproducibility.

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

## In Progress

Claude Code is assigned to strengthen `run_manifest` content validation for report audit.

## Known Gaps

- Real index benchmark data-source wiring is not complete. Benchmark-relative code and data-loading skeleton exist, and temporary stock benchmark wiring exists.
- Time-varying suspension/ST/risk-warning metadata still depends on confirmed upstream source tables.
- Benchmark membership, market-cap, liquidity bucket, and real regime grouping are not fully standardized across all research outputs.
- Evaluation layer does not yet implement real index benchmark comparison or real regime classification.
- Larger research-run bundles beyond run-level identifier linkage are not yet standardized.
- Run manifest content validation is currently scoped for stricter audit coverage.

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

Claude Code should implement `QRE-RUN-MANIFEST-CONTENT-VALIDATION-001`. Real index benchmark wiring should remain a follow-up after the available index table, schema, code column, and value column are confirmed.
