# Implementation Brief

## Task ID

QRE-TRAILING-STOP-BATCH-001 (M10.2b follow-up)

## Created By

KIMI_CODE (single agent; user direction "请你继续推进下一步任务" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Add trailing stop to the single-symbol/batch backtest path, completing the stop family (stop_loss/take_profit landed in M10.2b, commit `24c284d`). `StrategySpec.risk.trailing_stop_pct` is already parsed and catalog strategies declare it; the batch path ignores it today. Both engines (simulator + vectorized) must honor it with metric-identical results.

## Semantics (locked for both engines; batch-path model)

- Parameter: `trailing_stop_pct` on `SingleSymbolBacktestRequest` / `BatchBacktestRequest` (default None = disabled); validation: must be > 0.
- Anchor: starts at the actual fill `entry_price`; updated at every bar while holding with the bar's `high` (fallback to `mark_price_column` when `high` is unavailable): `anchor = max(anchor, high)`.
- Trigger: after the anchor update, if `close <= anchor × (1 - trailing_stop_pct)` → schedule sell at next bar's open, reason `trailing_stop` (same pending-sell machinery: slippage, validation, retry preserving reason, last-bar guard).
- Precedence (locked): pending retry > holding expiry > stop_loss > take_profit > trailing_stop > exit_signal.
- Deliberate model difference from the shared engine (documented): the shared engine evaluates intraday `low/high` touches and fills same-day at the stop price; the batch path stays close-based with next-open execution (no intraday ambiguity, no lookahead).
- Activation: same `apply_stops` gate as fixed stops (spec `risk.trailing_stop_pct` used when enabled; request/runner `--trailing-stop-pct` overrides). Default runs unchanged.
- Vectorized engine: dense candidate set when ANY stop type is enabled (fixed or trailing).

## Scope

1. `SingleSymbolBacktestRequest` += `trailing_stop_pct`; simulator: anchor state + update + trigger branch at locked precedence.
2. `single_symbol_vectorized.py`: identical anchor/branch; dense candidates when any stop enabled.
3. `BatchBacktestRequest` += `trailing_stop_pct` + validation; both batch paths thread it.
4. `ResearchRunRequest` += `trailing_stop_pct` (override; None = spec value when `apply_stops`); runner flag `--trailing-stop-pct`. (Shared-mode passthrough of spec trailing was already wired in M10.2b.)
5. Tests: deterministic (anchor tracks high, close-breach trigger, anchor reset between trades, high-column fallback, precedence vs exit_signal/fixed stops, retry preserves reason), randomized seeds WITH trailing params (dual-engine equality), validation, threading.
6. Real-DB small-sample: dual-engine identity with trailing enabled + A/B effect.

## Non-Goals

- No shared-engine changes (already has trailing).
- No intraday (low/high touch) stop model in the batch path.
- No default-on activation.

## Expected Tests

```bash
uv run pytest tests/test_single_symbol_vectorized.py -q
uv run pytest -q
```

## Acceptance Criteria

- Dual-engine equality holds with trailing enabled (extended randomized suite + real-DB small-sample diff).
- `--trailing-stop-pct` with `--apply-stops` measurably changes results for stop-declaring strategies; without the gate, results bit-identical to before.
- Full pytest suite green.
