# Implementation Brief

## Task ID

QRE-PARAM-OVERRIDE-001 (M10.2a, CR-0003 F1a part 1)

## Created By

KIMI_CODE (single agent; roadmap order user-approved, "按计划推进" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Give research runs a unified runtime parameter surface: cost-rate overrides without editing market-profile YAMLs, and backtest-time universe filtering (the spec's `universe:` fields are currently honored only as preflight diagnostics). Scope note: stop-loss/take-profit for the batch path is split to **M10.2b** — it is new engine exit logic requiring dual-engine (simulator + vectorized) equality work, and deserves its own verification cycle. This slice changes NO engine behavior.

## Background Evidence

- Catalog strategies already declare `universe: {exclude_st: true, exclude_suspended: true, exclude_risk_warning: true, min_listing_days: 120}` — the author intent exists; the engine ignores it today.
- `StrategySpec` already parses `exclude_st/exclude_suspended/exclude_risk_warning/min_listing_days/min_amount`.
- `AShareMarketProfile` is a frozen dataclass — overrides via `dataclasses.replace` are trivial and safe.
- Metadata reality: `reference.stock_basic` is EMPTY; `stock_suspend` (468k rows), `daily_basic` (14M rows), `index_weight` populated; `stock_st` present. Status flags must be sourced with graceful degradation and explicit "rule unavailable" reporting — never silently skip an intended filter.

## Scope

1. **Market-profile cost overrides**: `ResearchRunRequest.profile_overrides: dict[str, float] | None` — allowed keys: `commission_rate`, `min_commission`, `stamp_tax_sell`, `transfer_fee_rate`, `slippage_buy_rate`, `slippage_sell_rate`. Applied in `_run_backtest` via `dataclasses.replace(profile, **overrides)` with validation (unknown keys and negative values rejected). Runner flags: `--commission-rate`, `--min-commission`, `--stamp-tax`, `--transfer-fee`, `--slippage-buy`, `--slippage-sell`.
2. **Universe metadata loader** (`portfolio/universe.py`, `load_universe_metadata`): per-symbol availability table built from populated sources — `is_suspended` (from `reference.stock_suspend` ranges, as of run start), `list_date` (derived from first bar in `public.stock_daily`), plus `is_st`/`is_risk_warning` when their tables are populated (else rule reports `unavailable`). Read-only, identifier-validated like postgres.py.
3. **Backtest-time universe filter** (`portfolio/universe.py`, `apply_universe_filter`): symbol-level filtering of the assembled frame before the engine — `exclude_st`, `exclude_suspended` (suspended on start date), `exclude_risk_warning`, `min_listing_days` (vs run start), `min_amount` (symbol mean daily amount over the window from the frame's `amount` column; unavailable if the column is absent). Produces a structured report: input/output rows+symbols, dropped per rule, unavailable rules.
4. **Wiring**: `ResearchRunRequest.universe_filter: bool = False` (explicit opt-in; no silent change to existing runs). When True, `_run_backtest` applies the spec's universe fields and records `universe_report` + `profile_overrides` in `research_run_manifest.json` (additive fields). Runner flag `--universe-filter`.
5. **Tests**: override validation (unknown key, negative value); each universe rule independently + combined + unavailable reporting (fake metadata, no DB); loader with fake store; research_run wiring with fakes; manifest records new fields; runner flag parsing; full suite green.

## Non-Goals

- No engine behavior changes (exit logic untouched — stops are M10.2b).
- No silent default-on filtering (explicit flag required).
- No row-level daily suspension removal (engine's per-order suspension rejection already covers execution; this slice filters at symbol level).
- No new dependencies.

## Expected Tests

```bash
uv run pytest tests/test_universe.py -q   # new suite
uv run pytest -q                           # full suite green
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
uv run python scripts/batch_backtest_runner.py --strategies tf01a_ma_cross_20_120 --mode smoke --skip-preflight --skip-eval --compact \
  --codes 000001.SZ 000002.SZ 600000.SH --universe-filter --slippage-buy 0.0005 --slippage-sell 0.0005 \
  --output-dir outputs/param_override_check   # small-sample sanity (R-QRE-009)
```

## Acceptance Criteria

- Cost overrides change results measurably and are recorded in the run manifest; invalid overrides rejected with clear errors.
- With `--universe-filter`, ST/suspended/new-listing/low-amount symbols are excluded per spec fields, with a per-rule drop/unavailable report in the manifest; identical results without the flag.
- Full pytest suite green; no behavior change in default runs.
