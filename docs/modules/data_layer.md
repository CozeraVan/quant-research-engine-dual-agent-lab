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
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-01-30 \
  --codes 000001.SZ 000002.SZ 600000.SH
```

### Evaluation Output Artifacts

`qre eval-config --output-dir <dir>` writes durable CSV artifacts, a run manifest, and a report manifest. The report manifest is the stable entry point for `qre report-files` and `qre report-audit`.

Emitted files and their report-manifest roles:

| File | Role |
|---|---|
| `events.csv` | `events` |
| `summary.csv` | `evaluation_summary` |
| `ic_summary.csv` | `ic_summary` |
| `quantile_summary.csv` | `quantile_summary` |
| `group_summary.csv` | `evaluation_group_summary` (when `--group-by` is used) |
| `random_baseline_summary.csv` | `random_baseline_summary` (when `--random-baseline-seed` is used) |
| `factor_decay_summary.csv` | `factor_decay_summary` |
| `run_manifest.json` | `run_manifest` |

```bash
# Evaluation with durable output and diagnostics
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre eval-config \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH \
  --output-dir outputs/eval-rsi2 \
  --group-by board \
  --random-baseline-seed 42
```

Factor decay is derived from existing IC and Rank IC summaries per factor and horizon. It uses the smallest horizon per factor as the base and reports each horizon's IC / Rank IC difference from that base (signed difference, not a ratio). Random-baseline comparison uses a deterministic RNG when a seed is provided.

Discover and audit evaluation artifacts:

```bash
# List all evaluation artifact paths
uv run qre report-files outputs/eval-rsi2/report_manifest.json

# Audit the evaluation summary artifact
uv run qre report-audit outputs/eval-rsi2/report_manifest.json --role evaluation_summary

# Audit factor decay with strict matching
uv run qre report-audit outputs/eval-rsi2/report_manifest.json \
  --role factor_decay_summary --require-match
```

These diagnostics evaluate artifact structure only. They do not prove factor effectiveness or strategy quality.

Broad-run preflight:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre preflight \
  strategies/low_level/rsi2_reversal_research.yaml \
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

### Metadata-Aware Grouping

Evaluation and portfolio backtest commands accept `--group-by` on available research-frame metadata columns. Grouping works over any columns present after metadata assembly, including static fallback columns such as `board` and passthrough columns from real metadata tables.

Evaluation grouping writes a combined `group_summary.csv` (role `evaluation_group_summary`) and per-column files such as `group_summary_by_board.csv` (same role with manifest metadata `group_by=<col>`). The combined file contains all `group_by` values in one CSV; per-column files contain only rows for a single `group_by` column value so they can be filtered individually with `report-files` / `report-audit --group-by`.

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre eval-config \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ \
  --output-dir outputs/eval-grouped \
  --group-by board

# List all grouped artifacts (combined + per-column)
uv run qre report-files outputs/eval-grouped/report_manifest.json --role evaluation_group_summary

# Filter to the board-specific per-column file
uv run qre report-files outputs/eval-grouped/report_manifest.json \
  --role evaluation_group_summary --group-by board

# Audit the board-specific per-column file
uv run qre report-audit outputs/eval-grouped/report_manifest.json \
  --role evaluation_group_summary --group-by board --require-match
```

Batch grouping produces grouped cross-sectional summaries such as `group_by_board.csv`. The report-manifest role is `group_summary` with metadata `group_by=<col>`:

```bash
QRE_MARKET_DB_URL='<local-db-url>' \
uv run qre backtest-batch \
  strategies/low_level/rsi2_reversal_research.yaml \
  --start 2026-01-05 \
  --end 2026-03-31 \
  --codes 000001.SZ 000002.SZ 600000.SH 300001.SZ \
  --output-dir outputs/batch-grouped \
  --group-by board

# Audit grouped batch output
uv run qre report-audit outputs/batch-grouped/report_manifest.json \
  --role group_summary --group-by board --require-match
```

Shared-cash backtests support `--metadata-columns` to write selected static metadata into order, trade, and failed-order rows, and `--group-by` to produce per-group row summaries. Grouping works on the same metadata columns available in the assembled research frame.

Grouped outputs support segmentation and structural inspection only. They do not provide exposure attribution, causal explanation, or proof of strategy quality.

## Next Step

Next data-layer tasks:

1. Replace static fallback `is_st` / `is_suspended` with real time-varying status data when a reliable local table is available.
2. Add benchmark membership and industry classification adapters for cross-sectional grouping.
3. Integrate preflight JSON reports into larger evaluation/backtest run scripts when those scripts are introduced.
