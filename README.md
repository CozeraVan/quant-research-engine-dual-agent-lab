# Quant Research Engine

`quant-research-engine` is a local, read-only research and backtesting framework for A-share quantitative work.

It is built around two separate engines:

- `evaluation`: fast, full-market factor and strategy screening.
- `portfolio`: account-level backtesting with realistic market rules, execution costs, and report artifacts.

The design is intentionally layered so you can screen broadly first, then spend compute only on the candidates worth simulating in more detail.

## Project Mechanism

The core workflow is:

1. Load daily bars and factor columns from PostgreSQL.
2. Assemble a research frame from price data plus declared factor fields.
3. Run evaluation for signal screening, forward returns, IC / Rank IC, quantiles, and grouped summaries.
4. Run portfolio backtests for single-symbol, batch, or shared-cash execution.
5. Emit CSV / JSON / Markdown artifacts plus `report_manifest.json`.
6. Discover and audit those artifacts through `qre report-files` and `qre report-audit`.

The data layer is read-only. It does not write to the upstream database during evaluation, preflight, or backtests.

## What Is Implemented

### Data Layer

- Read daily bars from `tushare_data.public.stock_daily`
- Read factor columns from `factors.*`
- Read-only preflight checks for market, factor, metadata, universe, liquidity, and benchmark availability
- Security metadata fallback with board inference
- Reusable Tushare security probe scaffold for source-shape validation

### Evaluation Engine

- Safe expression-based signals
- Forward returns
- Event summaries
- IC and Rank IC
- Quantile return summaries
- Rough friction-adjusted screening
- Metadata group summaries
- Deterministic random-baseline comparison
- Factor decay summaries

### Portfolio Engine

- Single-symbol long-only backtests
- Independent batch backtests
- Shared-cash multi-symbol backtests
- A-share lot sizing and T+1 sellability
- Commission, stamp tax, transfer fee, and slippage handling
- Price-limit validation
- Risk exits and rebalance logic
- FIFO lot accounting
- Failed-order diagnostics

### Reporting And Reproducibility

- CSV / JSON / Markdown outputs
- `report_manifest.json` for every durable run
- `qre report-files` for artifact discovery
- `qre report-audit` for artifact validation
- Strict `--require-match` behavior for report selectors
- `--json` output for automation
- Optional `--run-id` to correlate preflight, evaluation, and portfolio outputs

## Efficiency Notes

The engine is designed for practical batch use rather than interactive toy runs:

- Evaluation happens before portfolio simulation, so expensive backtests are reserved for shortlisted candidates.
- PostgreSQL reads are performed through `pandas` and SQLAlchemy with explicit field selection, which keeps the data pulls narrow.
- Report discovery is manifest-driven, so downstream automation can inspect structured metadata instead of parsing Markdown.
- JSON output is available for script integration without extra file scans.
- The security metadata smoke path is read-only and only downloads small samples for source verification.
- The architecture keeps market rules in the market/profile layer, which avoids duplicating execution logic inside strategies.

I have not published benchmark throughput numbers in this repository yet. The current focus is correctness, reproducibility, and keeping the pipeline fast enough for full-market daily research runs.

## Repository Layout

- `src/quant_research_engine/` - package source
- `tests/` - unit and regression tests
- `docs/agent/` - dual-agent workflow state and handoff docs
- `docs/modules/` - module-level documentation
- `outputs/` - local run artifacts, when present

## Quick Start

Set your PostgreSQL connection first:

```bash
export QRE_MARKET_DB_URL='postgresql+psycopg://user:pass@host:5432/tushare_data'
```

Run a smoke check:

```bash
uv run qre db-smoke
uv run qre factor-smoke --start 2020-01-01 --end 2020-01-31 --logical-name rsi2 --target factors.some_table.rsi2
uv run qre metadata-smoke
```

Run evaluation:

```bash
uv run qre eval-config strategy.yaml --start 2020-01-01 --end 2020-03-31 --output-dir outputs/eval
```

Run portfolio backtests:

```bash
uv run qre backtest-single strategy.yaml --symbol 000001.SZ --start 2020-01-01 --end 2020-03-31
uv run qre backtest-batch strategy.yaml --start 2020-01-01 --end 2020-03-31
uv run qre backtest-shared strategy.yaml --start 2020-01-01 --end 2020-03-31
```

Inspect durable artifacts:

```bash
uv run qre report-files outputs/shared/report_manifest.json --role orders
uv run qre report-audit outputs/shared/report_manifest.json --role orders --require-match
```

## Report Manifest Usage

Batch and shared-cash runs write `report_manifest.json` in the output directory. Use it as the stable entry point for downstream scripts instead of parsing Markdown reports.

Examples:

```bash
uv run qre report-files outputs/smoke_shared_manifest/report_manifest.json \
  --role window_metrics \
  --window M

uv run qre report-audit outputs/smoke_batch_rsi2_rolling_audit/report_manifest.json \
  --role rolling_ranked_symbols \
  --group-by board \
  --window-size 20 \
  --require-match
```

`report-files --json` and `report-audit --json` are available for automation and CI workflows.

## Current Data Status

The implementation currently works with the following local PostgreSQL sources:

- `public.stock_daily` for daily bars
- `factors.*` for technical factor inputs
- `stock_holder_number` and other non-core reference tables where available

Open items that still depend on upstream data confirmation:

- Real security-status metadata table for suspension / ST / risk warning
- Real benchmark index wiring

## Validation

The current repository is validated with focused pytest coverage plus progress-doc checks.

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
```

The targeted validation for the latest security-source scaffold also passes:

```bash
uv run pytest tests/test_tushare_security.py tests/test_postgres_store.py -q
```

## Design Documents

- [AGENTS.md](AGENTS.md)
- [docs/design/overview.md](docs/design/overview.md)
- [docs/design/architecture_mindmap.md](docs/design/architecture_mindmap.md)
- [docs/modules/module_boundaries.md](docs/modules/module_boundaries.md)
- [docs/modules/ashare_first_market_profile.md](docs/modules/ashare_first_market_profile.md)
- [docs/modules/data_layer.md](docs/modules/data_layer.md)
- [docs/modules/evaluation_layer.md](docs/modules/evaluation_layer.md)
- [docs/modules/portfolio_layer.md](docs/modules/portfolio_layer.md)
- [docs/mvp_plan.md](docs/mvp_plan.md)
- [进度.md](进度.md)
