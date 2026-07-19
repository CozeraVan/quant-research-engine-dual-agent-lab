# CR-0003: Strategy Operations & Fit Analysis (Milestone 10)

## 1. Background

Direction and granularity aligned with the user on 2026-07-19 (brainstorm recorded in `06_DECISION_LOG.md` entry of the same date). Three user ideas were adopted:

- **F1**: modular backtest parameters with normalized reports — CLI runtime overrides first, GUI later.
- **F2**: continuous strategy testing — idempotent full re-run after data updates (no stateful incremental).
- **F3**: per-strategy winner-stock clustering with noise filtering — two phases: enrichment analysis first (zero new dependencies), ML clustering evaluated later.

Execution order agreed: M9.1b (vectorized engine, from CR-0002) → F3 → F1 → F2. M9.2 (statistical validation) and M9.3 (aggregate report) from CR-0002 are folded into M10.1 (F3), which subsumes them.

## 2. Goal

Turn the QRE from a batch-capable engine into an operations-ready research tool: fast enough for full-history runs (M9.1b, CR-0002), able to say *which stocks each strategy actually fits* (F3), configurable without editing YAMLs (F1), and self-refreshing when upstream data lands (F2).

## 3. User Scenario

1. Research lead picks or authors a strategy YAML, overrides stamp tax / slippage / stops / window / universe at run time, and gets a normalized report comparable across runs (F1).
2. After `quant_ts` refreshes daily bars and `indicators_tushare` refreshes factors, the catalog's rolling-window results update automatically and deltas are reported (F2).
3. For each strategy, the report shows not just market-wide excess return but *best stock-class* excess return, the shared features of its winner stocks (board / industry / cap / liquidity), and whether that edge survives noise filtering — so a strategy with 3% market-wide but 12% best-class excess is not buried (F3).

## 4. Scope

### In Scope

- **M10.1 Strategy-fit analysis & noise filtering (F3 phase 1)** (`QRE-STRATEGY-FIT-ANALYSIS-001`):
  - Read per-symbol strategy results (`summary.csv`, compact batches) → select **significant winners** per strategy, not a broad top-N%: exact one-sided binomial test on per-symbol win rate (net-profitable trade fraction) vs p=0.5, confidence tiers 90%/99%/99.9% (user refinement 2026-07-19), plus magnitude gates (positive net return, positive excess vs buy-hold) and noise filters (minimum trade count, liquidity floor, return sanity bounds). **Free-rider accounting**: stocks profitable only via the stock's own natural rise (excess ≤ 0, e.g. natural +30% vs strategy +25%) are excluded but explicitly counted/reported; returns always decomposed as strategy vs natural vs excess (user refinement 2026-07-19).
  - Strategy-level meta-test per tier: significant-stock count vs false-positive expectation (eligible × alpha) — no-edge strategies are correctly judged ineffective.
  - Enrichment analysis of significant winners vs universe baseline across `board`, `industry_group`, `market_cap_bucket`, `liquidity_bucket`; hypergeometric significance (pure-Python, no new deps).
  - Stability check: does the enrichment repeat across M/Q window slices?
  - Strategy-fit report: per-strategy significant stock pool, market-wide vs significant-pool excess, meta-tier rankings, class descriptions; multiple-testing adjustment across strategies and clusters (absorbs M9.2); manifest-registered and `qre report-audit`-discoverable (absorbs M9.3).
- **M10.2 Unified runtime parameter overrides (F1a)** (`QRE-PARAM-OVERRIDE-001`):
  - Run-level overrides without editing YAMLs: cost rates (commission/stamp/transfer/slippage), stop-loss/take-profit for the batch path, date window, symbol universe.
  - Backtest-time universe filtering: apply `exclude_st` / `exclude_suspended` / `min_listing_days` / `min_amount` to the frame before the engine (currently preflight-only diagnostics).
  - Normalized run report schema: identical shape across runs and strategies for cross-run comparison.
- **M10.3 Continuous strategy refresh (F2)** (`QRE-CONTINUOUS-REFRESH-001`):
  - Watermark detection: DB `max(trade_date)` vs last batch watermark (read-only).
  - Idempotent re-run script on rolling window (default 2 years), reusing the catalog runner with `--resume`.
  - Scheduler wiring (systemd timer or cron, mirroring `quant_ts` practice) + delta report vs previous batch.
- **M10.4 ML clustering (F3 phase 2)** — FUTURE: evaluate scikit-learn k-means only after M10.1 proves value; requires explicit dependency approval.

### Out of Scope

- GUI console work (deferred per F1 CLI-first decision; the existing GUI skeleton stays as-is).
- Stateful incremental backtesting (rejected in favor of idempotent re-run).
- Intraday / minute-level data, short selling, portfolio-level shared-cash vectorization.
- New indicator computation inside QRE (R-QRE-002).

## 5. Affected Requirements

- R-QRE-007: all new report artifacts must register in `report_manifest.json` and pass `qre report-audit`.
- R-QRE-008: M10.1 outputs are screening evidence, still not research conclusions until M9.4 full-history validation.
- R-CORE-003: every slice ships with tests; metric equality against existing simulators where applicable.

## 6. Protected Requirements

- Read `docs/agent/02_LOCKED_REQUIREMENTS.md` — especially R-QRE-001 (scope), R-QRE-002 (no internal indicators), R-QRE-003 (no lookahead), R-QRE-005 (read-only DB), R-CORE-002 (no unrelated rewrites).

## 7. Suggested Tasks

| Task ID | Task | Priority | Status |
|---|---|---|---|
| QRE-STRATEGY-FIT-ANALYSIS-001 | M10.1 winner-stock enrichment, noise filtering, strategy-fit report (F3 phase 1) | High | PLANNING (brief written 2026-07-19) |
| QRE-PARAM-OVERRIDE-001 | M10.2 runtime parameter overrides + backtest-time universe filter (F1a) | Medium | TODO |
| QRE-CONTINUOUS-REFRESH-001 | M10.3 watermark detection + idempotent re-run + scheduler + delta report (F2) | Medium | TODO |
| QRE-ML-CLUSTERING-001 | M10.4 optional ML clustering phase 2 (F3 phase 2) | Low | FUTURE (dependency approval needed) |

## 8. Acceptance Criteria

- [ ] M10.1: for any completed compact batch, one command produces a per-strategy fit report (winner classes, enrichment significance, stability, adjusted rankings) that passes `qre report-audit`.
- [ ] M10.2: stamp tax / slippage / stops / window / universe are overridable per run via CLI flags or run-config; filtered universes measurably change backtest membership; report schema identical across runs.
- [ ] M10.3: after a simulated data refresh, the refresh script detects the watermark gap, re-runs affected strategies on the rolling window, and emits a delta report; scheduler entry documented.
- [ ] No new dependencies in M10.1-M10.3; M10.4 requires separate approval.

## 9. Risks

- Enrichment on ~5,292 symbols × 106 strategies has multiple-comparison risk inside clusters too — adjusted in M10.1 design (absorbed M9.2).
- Winner-class fit may be regime-specific; stability check mitigates but does not prove persistence (R-QRE-008 wording stays in reports).
- Backtest-time universe filtering changes results vs unfiltered runs — must be an explicit, recorded run parameter, never a silent default change.
- Idempotent re-run assumes M9.1b speed; without it, daily refresh of 106 strategies is not practical (11h).

## 10. Implementation Notes

- Input data for M10.1 already exists: `outputs/backtests/quick_batch_106/f365c8a07b33/*/backtest/summary.csv` + metadata columns from the frame (`board`, `industry_group`, `market_cap_bucket`, `liquidity_bucket`).
- Keep M10.1 pandas-only; hypergeometric test via `math.comb` or equivalent.
- M10.2 overrides should flow run-config → market profile copy, never mutate the shared profile object.
- F2 scheduler must not overlap with manual batch runs on the same output tree.

## 11. Proposed Agent State Transition

- Next Phase: `PLANNING`
- Next Owner: `KIMI_CODE`
