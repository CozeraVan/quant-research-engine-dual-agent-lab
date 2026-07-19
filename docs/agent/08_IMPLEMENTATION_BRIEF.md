# Implementation Brief

## Task ID

QRE-STOPS-BATCH-ENGINE-001 (M10.2b, CR-0003 F1a part 2)

## Created By

KIMI_CODE (single agent; roadmap order user-approved, "请继续按计划推进" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Honor `stop_loss_pct` / `take_profit_pct` in the single-symbol and batch backtest path — declared in strategy YAMLs' `risk:` section since the catalog exists (e.g. tf01a `stop_loss_pct: 0.08`) but ignored by the batch path today. Both engine implementations (simulator AND vectorized) must honor them with **metric-identical results**, verified by the full equality ladder. Trailing stop is explicitly out of scope (anchor-tracking variant; shared engine already has it).

## Semantics (locked for both engines)

- Parameters on `SingleSymbolBacktestRequest` / `BatchBacktestRequest`: `stop_loss_pct`, `take_profit_pct` (default None = disabled).
- Evaluation: at every bar while holding (including the entry bar's close), compare the bar's `mark_price_column` (close) against the actual fill `entry_price`:
  - `close <= entry_price × (1 - stop_loss_pct)` → schedule sell at next bar's open, reason `stop_loss`.
  - `close >= entry_price × (1 + take_profit_pct)` → schedule sell at next bar's open, reason `take_profit`.
- Execution reuses the existing pending-sell machinery: T+1 next-open execution, slippage, order validation, failed-order records, rejection retry with the ORIGINAL reason preserved.
- Per-bar precedence (locked): pending retry > holding expiry (immediate at that bar's open) > `stop_loss` > `take_profit` > `exit_signal` (all three schedule next bar; first setter wins the reason).
- Last-bar guard: no scheduling when `index + 1 >= len(working)` (same as exit_signal).
- Validation: `stop_loss_pct` must be in (0, 1); `take_profit_pct` must be > 0.
- Vectorized engine: with stops enabled it iterates every bar (dense candidate set, numpy) — sparse event-loop only when stops are disabled.

## Scope

1. `SingleSymbolBacktestRequest` += `stop_loss_pct`, `take_profit_pct`; simulator sell-block gains the two branches at the locked precedence.
2. `single_symbol_vectorized.py`: identical branches + dense candidate set when stops enabled.
3. `BatchBacktestRequest` += both fields + validation; both batch paths (simulator/vectorized) thread them into per-symbol requests.
4. `ResearchRunRequest` += `apply_stops: bool = False`, `stop_loss_pct`, `take_profit_pct` (None = use spec). Opt-in only: when `apply_stops=False`, stops are NOT applied (no silent change to existing runs). When True: batch request gets request overrides or spec values. Shared mode: pass spec/override stops through to `SharedCashBacktestRequest` (fields already exist there).
5. Runner: `--apply-stops`, `--stop-loss-pct`, `--take-profit-pct` threaded `BatchRunConfig` → `ResearchRunRequest`; echoed into batch_summary config.
6. Tests (dual-engine equality is the acceptance gate):
   - Deterministic: stop_loss trigger, take_profit trigger, stop evaluated on entry-bar close, precedence over exit_signal, stop + limit-down rejection retry preserving reason, both params unset (existing suite unchanged).
   - Randomized property frames EXTENDED with random stop params (dual-engine equality across all seeds).
   - Validation errors; research_run/runner threading; spec-vs-override precedence.
7. Real-DB small-sample (R-QRE-009): stop-declaring strategies × 3-50 symbols — dual-engine `summary.csv` diff + apply-vs-not differ.

## Non-Goals

- No trailing stop (follow-up; needs anchor tracking).
- No shared-cash engine changes (already supports stops; this slice only passes values through).
- No default-on activation (explicit `--apply-stops` or request flag required).
- No intraday stop evaluation (close-based only; no lookahead).

## Expected Tests

```bash
uv run pytest tests/test_single_symbol_vectorized.py tests/test_universe.py -q
uv run pytest -q
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# R-QRE-009: small-sample dual-engine check with stops enabled (3-50 symbols)
```

## Acceptance Criteria

- Dual-engine equality holds with stops enabled: extended randomized suite + real-DB small-sample `summary.csv` identical.
- `--apply-stops` measurably changes results for stop-declaring strategies; without it, results are bit-identical to before.
- Precedence/reason contracts locked by tests (`stop_loss`/`take_profit` recorded in trades ledger exit_reason).
- Full pytest suite green.
