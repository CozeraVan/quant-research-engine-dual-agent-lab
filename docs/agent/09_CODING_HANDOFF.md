# Coding Handoff

## Task ID

QRE-STOPS-BATCH-ENGINE-001 (M10.2b, CR-0003 F1a part 2)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Request fields**: `SingleSymbolBacktestRequest` and `BatchBacktestRequest` gained `stop_loss_pct` / `take_profit_pct` (default None = disabled); batch validation (`stop_loss_pct` ∈ (0,1), `take_profit_pct` > 0).
2. **Simulator** (`single_symbol.py`): two new sell-block branches at the locked precedence — pending retry > holding expiry (immediate) > `stop_loss` > `take_profit` > `exit_signal` (last three schedule next bar). Close-based evaluation vs actual fill price, no lookahead, last-bar guard, retry preserves original reason.
3. **Vectorized engine**: identical branches; dense candidate set (`np.arange(n)`) when stops enabled (any bar's close can cross), sparse event loop unchanged when disabled.
4. **Wiring**: `ResearchRunRequest.apply_stops` (opt-in, default False) + `stop_loss_pct`/`take_profit_pct` overrides (None = use spec `risk:` values); effective levels hoisted before the mode branch; batch path threads into `BatchBacktestRequest`; shared path passes stops + `trailing_stop_pct` through to the existing shared-engine fields. Runner: `--apply-stops`, `--stop-loss-pct`, `--take-profit-pct`; echoed into batch_summary config.
5. **Tests** (50 new): 7 deterministic stop cases (trigger, entry-bar-close trigger, precedence over exit_signal, limit-down rejection retry preserving reason, expiry-beats-stop, batch validation), 40 new randomized seeds WITH random stop params (dual-engine equality), 3 research_run threading tests (off → None, on → spec values, override wins).

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py` (fields + stop branches)
- `src/quant_research_engine/portfolio/single_symbol_vectorized.py` (branches + dense candidates)
- `src/quant_research_engine/portfolio/batch.py` (fields + validation + threading)
- `src/quant_research_engine/orchestration/research_run.py` (apply_stops wiring, batch + shared)
- `src/quant_research_engine/orchestration/batch_runner.py`, `scripts/batch_backtest_runner.py` (flags)
- `tests/test_single_symbol_vectorized.py` (+47), `tests/test_universe.py` (+3)

## Validation Output

```bash
uv run pytest -q → 1109 passed, 4 warnings (1059 baseline + 50 new)

# R-QRE-009 real-DB small-sample ladder:
#   tf01a  × 3 codes × smoke, --apply-stops: simulator vs vectorized → summary.csv IDENTICAL
#   mr04a  × 3 codes × smoke, --apply-stops --stop-loss-pct 0.05: dual IDENTICAL
#   mr04a  A/B (1% stop vs off): summaries differ — stops measurably honored
#   real trade with exit_reason=stop_loss observed (000001.SZ)
```

## Semantics Note (locked)

Close-based stop evaluation vs actual fill `entry_price`; next-open execution through the existing pending-sell machinery (slippage, validation, failed orders, retry with original reason); precedence pending retry > holding expiry > stop_loss > take_profit > exit_signal; trailing stop remains out of scope (shared engine already has it); opt-in only — default runs bit-identical.
