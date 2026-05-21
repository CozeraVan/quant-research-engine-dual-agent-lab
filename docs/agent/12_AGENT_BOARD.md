# Agent Board

## Current Task ID

QRE-FACTOR-MISSING-HANDOFF-STANDARD-001

## Current Recipient

USER

## Message Type

FINALIZED

## Sender

CLAUDE_CODE

## Short Message

Operational missing-factor handoff standard finalized locally: review passed, request artifact flow is ready for use.

## Accepted Direction

- QRE should standardize strategy entry, factor availability checks, backtest execution, and report output.
- QRE should not rewrite `research-notes` / `strategy-research`.
- QRE should not compute technical indicators internally.
- External strategy projects should author QRE-standard strategy entry files from their strategy libraries.
- `indicators_tushare` should receive missing-factor requests and calculate/backfill required indicators or periods.
- Full-market report output should use the MT5 report as a baseline and keep all stock trades in unified tables with `symbol`.
- The future acceptance plan must include three existing strategy families converted into the standard entry format and smoke-tested with exit code `0`.
- TradingView screenshots add benchmark comparison, Sharpe/Sortino, trade analysis, P&L distribution, capital usage, margin placeholders, run-up, and drawdown fields.
- The first implementation may omit charts, but must emit stable workbook sheets, CSV/JSON tables, manifest roles, and audit/discovery behavior.

## Design Artifact

- `docs/superpowers/specs/2026-05-21-strategy-io-contract-design.md`
- `docs/superpowers/specs/2026-05-21-full-market-backtest-report-design.md`
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`
- `docs/strategy_entry/missing_factor_request.md`

## Implementation Artifacts

- `src/quant_research_engine/strategies/missing_factor.py` — new (~260 lines)
- `src/quant_research_engine/apps/cli.py` — `--output-dir` flag and extraction/emission in preflight handler
- `tests/test_missing_factor.py` — 25 new tests
- `tests/test_cli.py` — 3 new tests

## Validation

```bash
uv run pytest tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py -q
scripts/check-progress-docs.sh
git diff --check
```

Results: 168 passed, 2 warnings (pre-existing numpy) in 2.01s; all quality checks pass.

## Next Step

Move to the next task slice: high-level strategy entry compiler/preflight linkage.
