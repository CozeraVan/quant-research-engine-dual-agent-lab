# Implementation Brief

## Task ID

QRE-ANALYTICS-CONCAT-001 (M9.1b ≤30s acceptance target completion)

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Close the last open acceptance line from M9.1b (backtest stage ≤ 30s, currently 40.2s): replace the per-symbol pandas loops in the window/rolling analytics collectors with cross-symbol concatenated computation, keeping outputs byte-identical (risk.py remains the untouched oracle).

## Background Evidence

- Benchmark decomposition (measured 2026-07-19): backtest stage 40.2s = frame ~17s (shared per run, near-irreducible) + vectorized engine ~9s + window/rolling analytics + write ~14-28s. The analytics collectors still loop per symbol with pandas ops (`_collect_window_return_rows`, `_collect_rolling_return_rows` in `analytics.py`).
- Equality machinery exists: `tests/test_analytics_vectorized.py` compares collectors against the old risk.py path exactly; baseline artifacts (`outputs/backtests/profile_baseline/a2db386713da/`) are byte-identical references.

## Scope

1. **Concat window collector**: build ONE big frame (symbol, trade_date, total_equity) across symbols (single sort by symbol+date, or trust engine date ordering with a safety sort), one `groupby(["window","symbol"])["total_equity"].agg(["first","last"])` pass, vectorized `total_return = last/first - 1` with the `first > 0` gate — replacing ~5,292 per-symbol pandas groupby calls.
2. **Concat rolling collector**: one concatenated sort, per-symbol segments via group boundaries (`np.split` / cumcount) with cheap numpy sliding windows per segment — eliminating per-symbol pandas frame construction.
3. **Equality verification (the gate)**: `tests/test_analytics_vectorized.py` must pass unchanged (oracle), plus real-DB artifact diff: re-run the tf01a full-market benchmark and diff `window_summary_M/Q/Y.csv` + `rolling_summary_20.csv` + `summary.csv` against the baseline (must stay byte-identical), and record the new stage duration.
4. Docs: update `09_CODING_HANDOFF.md` with the final decomposition; note whether ≤30s is met.

## Non-Goals

- No changes to `risk.py`, engine internals, or output contracts.
- No frame-level cross-strategy caching (runner-level; separate consideration).
- No new dependencies.

## Expected Tests

```bash
uv run pytest tests/test_analytics_vectorized.py -q   # oracle, must pass unchanged
uv run pytest -q
```

## Acceptance Criteria

- Oracle equality suite passes; real-DB artifacts byte-identical to baseline.
- tf01a quick-mode backtest stage duration recorded; target ≤ 30s (or the residual decomposition documented if not).
- Full pytest suite green.
