# Data Layer

## Purpose

The data layer is the first bridge between the reusable engine and existing local data producers.

Initial scope:

- Read daily A-share bars from PostgreSQL.
- Read technical factor history from PostgreSQL.
- Assemble research frames from declared market fields and declared database factor fields.
- Keep connection configuration outside source code.
- Provide small smoke commands before broad research runs.

Important rule:

- Backtests and evaluation runs must not recompute technical indicators in engine code.
- Strategies declare the factor columns they need.
- The data layer reads those columns from `factors.*` tables, just like it reads market bars from `public.stock_daily`.

## Configuration

Preferred environment variables:

- `QRE_MARKET_DB_URL`
- `QRE_FACTOR_DB_URL`
- `QRE_REFERENCE_DB_URL`
- `QRE_BENCHMARK_DB_URL`
- `QRE_RESEARCH_DB_URL`

Fallback environment variables for compatibility with `strategy-research`:

- `SR_MARKET_DB_URL`
- `SR_FACTOR_DB_URL`
- `SR_REFERENCE_DB_URL`
- `SR_BENCHMARK_DB_URL`
- `SR_RESEARCH_DB_URL`

Default market daily table:

- `public.stock_daily`

The project must not hardcode database passwords in source files or docs.

## Current Files

- `src/quant_research_engine/data/settings.py`
  - database URLs and table configuration.
- `src/quant_research_engine/data/catalog.py`
  - factor field request parsing.
- `src/quant_research_engine/data/interfaces.py`
  - market, factor, and reference data protocols.
- `src/quant_research_engine/data/postgres.py`
  - read-only PostgreSQL adapter.
- `src/quant_research_engine/data/assembler.py`
  - combines market bars and database factor fields into a research frame.
- `src/quant_research_engine/strategies/spec.py`
  - loads YAML strategy specs and converts factor declarations into database field requests.
- `src/quant_research_engine/apps/cli.py`
  - `db-smoke`, `factor-smoke`, `metadata-smoke`, `preflight`, and `eval-config` commands.
- `src/quant_research_engine/preflight.py`
  - read-only broad-run checks before larger evaluation or backtest runs.

## Smoke Commands

Market data smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre db-smoke \
  --start 2026-01-05 \
  --end 2026-01-12 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --limit 20
```

Factor data smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre factor-smoke \
  --start 2026-01-05 \
  --end 2026-01-12 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --logical-name rsi_2 \
  --target factors.stock_daily_momentum_close.rsi_2
```

Security metadata smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre metadata-smoke \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --limit 20
```

Config-driven evaluation smoke:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre eval-config \
  examples/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-01-30 \
  --codes 000001.SZ 000002.SZ 600000.SH
```

Broad-run preflight:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre preflight \
  examples/rsi2_reversal_research.yaml \
  --start 2026-05-11 \
  --end 2026-05-15 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --benchmark-table public.stock_daily \
  --benchmark-code 000002.SZ \
  --benchmark-value-column close
```

The preflight command is read-only. It checks market row availability, latest market date, requested symbol coverage, factor schema, factor non-null coverage, factor join coverage, metadata availability, universe filters, liquidity, and optional benchmark availability.

## Verified On 2026-05-11

Market smoke:

- `loaded_rows=18`
- columns: `ts_code,trade_date,open,high,low,close,pre_close,vol,amount`
- date range: `2026-01-05` to `2026-01-12`

Factor smoke:

- `loaded_rows=18`
- columns: `ts_code,trade_date,rsi_2`
- date range: `2026-01-05` to `2026-01-12`
- `non_null_rsi_2=18`

Config-driven evaluation smoke:

- `strategy=rsi2_reversal_research_mvp`
- `research_rows=60`
- `event_rows=18`

Security metadata smoke:

- Reads configured `QRE_SECURITY_METADATA_TABLE` / `SR_SECURITY_METADATA_TABLE` when present.
- Falls back to deriving metadata from `public.stock_daily` when no metadata table is configured.
- Derived fallback fields:
  - `list_date`: first available daily bar date.
  - `board`: inferred from `ts_code`.
  - `is_st`: `False`.
  - `is_risk_warning`: `False`.
  - `is_suspended`: `False`.

Board inference currently maps:

- `300*` / `301*`: `chinext`
- `688*`: `star_market`
- `*.BJ`: `beijing`
- all other A-share codes: `main_board`
- Real fallback smoke:
  - `000001.SZ`, `000002.SZ`, `600000.SH`: `main_board`
  - `300001.SZ`: `chinext`
  - `688001.SH`: `star_market`

## Next Step

Next data-layer tasks:

1. Replace static fallback `is_st` / `is_suspended` with real time-varying status data when a reliable local table is available.
2. Add benchmark membership and industry classification adapters for cross-sectional grouping.
3. Integrate preflight JSON reports into larger evaluation/backtest run scripts when those scripts are introduced.
