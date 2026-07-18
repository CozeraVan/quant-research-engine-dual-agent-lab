# QRE Strategy Entry Standard

## Purpose

The QRE strategy entry standard defines how to author a strategy so it can be validated, compiled, backtested, and reported by the quant-research-engine (QRE).

This standard is for humans, the project's single development agent (Kimi Code), and external strategy projects. It separates *what the strategy means* from *where the data lives*. The author describes trading logic in terms of indicator aliases and rules — the QRE compiler resolves those aliases to database columns.

## Scope

Version 1 covers daily A-share technical-indicator strategies running against `public.stock_daily` and `factors.*`.

Out of scope for v1: minute bars, tick data, live trading, fundamental strategies, ML model training, clustering-driven discovery, QRE-side indicator calculation.

## End-to-End Flow

```
1. Write strategy entry file (strategy_card + factor_requirements + experiment_plan)
2. QRE validates the entry against the factor catalog
3. If factors are missing, QRE emits a missing-factor request for indicators_tushare
4. When factors are available, QRE compiles the entry into executable backtest tasks
5. QRE runs the backtest and emits standard full-market reports
```

## Project Boundaries

| Layer | Owns |
|---|---|
| QRE | Strategy input standard, factor availability checks, missing-factor requests, compilation, backtest execution, report output |
| indicators_tushare | Technical indicator calculation, period expansion, backfill, persistence into `factors.*` |
| research-notes / strategy-research | Strategy knowledge, natural-language descriptions, strategy libraries |

QRE does not rewrite external strategy repositories or compute indicators internally.

## Quick Start

Minimal long-only mean-reversion strategy:

```yaml
strategy:
  id: rsi2_oversold_reversal
  name: RSI2 Oversold Reversal
  family: mean_reversion
  description: Buy when 2-period RSI drops below 10, exit when it rises above 70.

rules:
  entry:
    all:
      - indicator: rsi
        alias: rsi_fast
        operator: "<"
        value: 10
  exit:
    any:
      - indicator: rsi
        alias: rsi_fast
        operator: ">"
        value: 70

factor_requirements:
  - alias: rsi_fast
    indicator: rsi
    source: close
    period: 2
    required: true
    reason: entry and exit threshold signal

experiment:
  id: rsi2_smoke
  frequency: daily
  market: ashare
  start: 2024-01-01
  end: 2024-12-31
  universe:
    include: all_a
    exclude_st: true
    exclude_suspended: true
    exclude_risk_warning: true
    min_listing_days: 120
  execution:
    signal_date: t
    entry_execution: t_plus_1_open
    exit_execution: t_plus_1_open
    market_profile: ashare_daily_default
  risk:
    max_holding_days: 5
    stop_loss_pct: 0.08
  capital:
    initial_cash: 1000000
    max_positions: 20
    position_weight: equal
```

## Your First Strategy: Step-by-Step

This walks you from creating a strategy file to seeing backtest results.

### 1. Create the strategy file

Save the Quick Start example above as `strategies/high_level/my_first_strategy_entry.yaml`.

### 2. Compile it

```bash
uv run qre compile strategies/high_level/my_first_strategy_entry.yaml
```

The compiler resolves indicator aliases to database columns and emits a low-level spec. If factors are missing, the compiler tells you exactly which ones.

### 3. Run a preflight check

```bash
uv run qre preflight strategies/high_level/my_first_strategy_entry.yaml \
  --start 2024-01-01 --end 2024-03-31
```

Preflight confirms data availability and factor coverage before you invest time in a full backtest.

### 4. Run a single-symbol backtest

```bash
uv run qre backtest-single strategies/high_level/my_first_strategy_entry.yaml \
  --symbol 000001.SZ --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/my-first/
```

### 5. Examine the results

```bash
ls outputs/my-first/
uv run qre report-files outputs/my-first/report_manifest.json
uv run qre report-audit outputs/my-first/report_manifest.json --require-match
```

### 6. Scale up to full-market

Once the single-symbol test looks good, run the same strategy across all A-shares:

```bash
uv run qre backtest-batch strategies/high_level/my_first_strategy_entry.yaml \
  --start 2024-01-01 --end 2024-12-31 \
  --initial-cash 1000000 --output-dir outputs/my-first-full/
```

For large full-market runs, use the `qre research-run` orchestrator which chains preflight → evaluation → backtest under one `--run-id`.

## File Organisation

A complete strategy entry is one YAML file with three sections:

| Section | Purpose | Reference |
|---|---|---|
| `strategy` / `rules` | Identity and trading logic | [strategy_card.md](strategy_card.md) |
| `factor_requirements` | Data dependencies | [factor_requirements.md](factor_requirements.md) |
| `experiment` | Run configuration | [experiment_plan.md](experiment_plan.md) |

The missing-factor request format that QRE emits to `indicators_tushare` is defined in [missing_factor_request.md](missing_factor_request.md).

Concrete examples across three strategy families are in [examples.md](examples.md).

## Directory Structure

Strategy files are organised in two directories:

```
strategies/
├── high_level/          # High-level strategy entry files (standard format)
│   ├── rsi2_oversold_reversal_entry.yaml
│   ├── ema200_bollinger_reversal_entry.yaml
│   ├── macd_zero_cross_momentum_entry.yaml
│   └── bollinger_mean_reversion_entry.yaml
├── low_level/           # Low-level StrategySpec files (compiled or hand-written)
│   ├── rsi2_reversal_research.yaml
│   ├── rsi2_reversal_with_risk.yaml
│   ├── rsi2_reversal_with_risk_and_weight.yaml
│   ├── rsi2_reversal_with_rebalance.yaml
│   ├── ema200_bollinger_reversal.yaml
│   └── bollinger_mean_reversion.yaml
└── run_bollinger_full.py  # Chunked full-market backtest runner
```

- **High-level entries** are authored by humans and compiled with `qre compile`.
- **Low-level specs** are compiled or hand-written for direct use with `qre backtest-*` commands.
- The **GUI** lives at `src/quant_research_engine/gui/` and supports both formats.
- **Output files** (reports, CSVs, JSONs) are written to `outputs/`.
