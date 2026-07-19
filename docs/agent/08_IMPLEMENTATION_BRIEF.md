# Implementation Brief

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Created By

KIMI_CODE (single agent; roadmap order user-approved: M9.1b → M10.1 → M10.2 → M10.3)

## Intended Implementer

KIMI_CODE

## Goal

One command that turns a completed compact batch into a per-strategy **fit report**: which stock classes each strategy actually fits. For every strategy, report market-wide excess return AND best-class excess return side by side, with winner-class feature description, enrichment significance, noise filtering, and multiple-testing adjustment — so a strategy with modest market-wide but strong class-specific edge is not buried. **No new backtest runs** (user instruction 2026-07-19: no full-scale backtests until core engine work is complete; this slice is pure analysis of existing artifacts).

## Background Evidence

- Input data ready: `outputs/backtests/quick_batch_106/f365c8a07b33/` — 106 strategies × 5,292 symbols × 2024, `backtest/summary.csv` per strategy (symbol, total_return, trade_count, win_rate, total_cost, buy_hold_return, excess_return_vs_buy_hold, order_count, failed_order_count).
- Verified gap: summary.csv carries **no class columns** (metadata was not threaded in the catalog batch). Class dimensions come from the DB metadata snapshot (read-only `load_security_metadata`: board, industry_group, market_cap_bucket, liquidity_bucket) — a single cheap query, not a backtest.
- User's motivating example: strategy A 5% market-wide / 8% best-class vs strategy B 3% market-wide / 12% best-class — B must surface.

## Scope

1. **New module** `src/quant_research_engine/analysis/strategy_fit.py`:
   - Batch loading: `batch_summary.json` + per-strategy `backtest/summary.csv` (skip error strategies, record skips).
   - Metadata join: read-only metadata snapshot for all symbols with explicit `--metadata-as-of` (default: batch end date); symbols missing metadata get `unknown` bucket (counted, never silently dropped).
   - Noise filters (configurable): `--min-trades` (default 5), drop NaN returns, `--min-class-size` (default 30 universe symbols per reportable class).
   - **Significance tiers instead of top-N%**: per symbol per strategy, exact one-sided binomial test on `win_rate` (fraction of net-profitable trades) vs H0: p=0.5, via `math.lgamma` (no deps). Tiers: **90% / 99% / 99.9%** (p ≤ 0.10 / 0.01 / 0.001). Magnitude gate: `total_return > 0` AND `excess_return_vs_buy_hold > 0` — the strategy must beat the stock's own natural (buy-and-hold) return, not merely the market. **Free-rider accounting**: stocks that are profitable but carry no true excess (e.g. natural +30% vs strategy +25%) are excluded from the pool but counted and reported separately as natural-growth riders. The winner pool = significant stocks only (no broad top-pct).
   - **Strategy-level meta-test**: per tier, binomial test of the strategy's significant-stock count against the false-positive expectation (eligible_symbols × tier alpha). A no-edge (≈50% win rate) strategy yields ~expected counts and is correctly judged ineffective; the 90/99/99.9% meta tier is the strategy effectiveness grade.
   - **Return decomposition everywhere**: per stock and per strategy, report `total_return` / `buy_hold_return` / `excess_return_vs_buy_hold` side by side; rankings sort by excess, never by raw strategy return; free-rider (profitable-but-no-excess) counts are explicit per strategy.
   - Enrichment per dimension (`board`, `industry_group`, `market_cap_bucket`, `liquidity_bucket`) on the significant pool (default 99% tier): winner share in class vs class share in universe + hypergeometric p-value (pure Python `math.comb`).
   - Multiple-testing adjustment: Benjamini-Hochberg FDR (q=0.05) across (strategy × dimension × class) enrichment tests.
   - Strategy-fit summary per strategy: eligible symbols, n_90/n_99/n_999, expected false positives per tier, meta p per tier, market mean excess, significant-pool mean excess, best-class (dimension=value) with enrichment p and BH-adjusted p, `class_edge` flag (significant meta tier + pool excess − market excess ≥ 2 pp).
2. **Command** `scripts/strategy_fit_report.py --batch-dir <dir> [--tiers 0.10,0.01,0.001] [--pool-tier 0.01] [--min-trades 5] [--metadata-as-of DATE] [--output-dir outputs/strategy_fit/<id>]`: writes `strategy_fit_stocks.csv` (per-strategy significant stock pool: tier, binomial p, `total_return` / `buy_hold_return` / `excess_return_vs_buy_hold` side by side), `strategy_fit_summary.csv` (including free-rider counts and mean strategy/natural/excess decomposition), `strategy_fit_classes.csv`, `strategy_fit_report.md` (strategy ranking by meta tier and pool excess + class descriptions + filter accounting), `report_manifest.json` (new kind `strategy_fit_report_manifest`, registered so `qre report-files` / `qre report-audit` work).
3. **Runner passthrough (small)**: `--metadata-columns` flag on `batch_backtest_runner.py` threaded to `ResearchRunRequest.metadata_columns`, so future batches embed class columns in summary.csv directly (v1 analysis does not depend on it).
4. **Tests**: synthetic batch fixtures with hand-computed expectations; exact binomial vs known values (e.g. 3/4 wins → p=0.15625); meta-test false-positive behavior under random (no-edge) data; BH-FDR ordering; filter accounting; unknown-bucket handling; manifest audit parity; determinism.

## Non-Goals

- No backtest runs of any scale (user instruction); analysis reads existing artifacts only.
- No time-window stability metric in v1 — per-symbol monthly returns are not persisted in compact artifacts. Follow-up v1.1: add `symbol_month_returns.csv` to compact mode (cheap, vectorized from equity curves) + stability metric; recorded in CR-0003.
- No ML clustering (M10.4, separate dependency decision).
- No GUI work.

## Expected Tests

```bash
uv run pytest tests/test_strategy_fit.py -q   # new suite
uv run pytest -q                              # full suite green
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
uv run python scripts/strategy_fit_report.py --batch-dir outputs/backtests/quick_batch_106/f365c8a07b33
uv run qre report-audit outputs/strategy_fit/<id>/report_manifest.json --require-match
```

## Acceptance Criteria

- Command completes on `quick_batch_106/f365c8a07b33` without any backtest execution; all 106 strategies analyzed (5 skipped with reason if errored).
- Report ranks strategies by meta-test tier (90/99/99.9%) and significant-pool excess; no-edge strategies (≈50% win rate) correctly land below the 90% meta tier (false positives ≈ expectation); `class_edge` strategies highlighted; per-strategy significant stock pool exported in `strategy_fit_stocks.csv`.
- Manifest registered and `qre report-audit` passes; full pytest suite green; outputs deterministic.
