# Coding Handoff

## Task ID

QRE-STRATEGY-ENTRY-COMPILER-PREFLIGHT-LINKAGE-001

## Written By

CLAUDE_CODE

## Intended Reviewer

CODEX

## Status

FIXED. Runtime compatibility fix applied per `10_REVIEW_REPORT.md`. Ready for Codex re-review.

## Implementation Summary

Implemented the compiler/linkage layer from `docs/agent/08_IMPLEMENTATION_BRIEF.md`, bridging high-level strategy entry YAML (strategy + rules + factor_requirements + experiment sections) to the existing low-level `StrategySpec` preflight/backtest flow:

- **new module `compiler.py`** (`src/quant_research_engine/strategies/compiler.py`, ~410 lines):
  - `_INDICATOR_CATALOG` — maps indicator names to (category, column_builder) pairs. Supports 13 indicators: rsi, ema, sma, wma, macd, bollinger, atr, adx, cci, mfi, obv, stochastic, williams_r.
  - `_col_simple(indicator, source, period, params, output)` → `{indicator}_{period}`
  - `_col_macd(indicator, source, period, params, output)` → `macd_{fast}_{slow}_{signal}` or `macd_{output}_{fast}_{slow}_{signal}`
  - `_col_bollinger(indicator, source, period, params, output)` → `bb{u|l|m}_{period}_{nbdev_int}_{nbdev_frac}_{nbdev_int}_{nbdev_frac}`
  - `_build_table_name(category, source)` → `stock_daily_{category}_{source}`
  - `CompiledEntry` — dataclass carrying strategy metadata, factor_targets (alias → `factors.table.column`), signal expressions, experiment dict, rules dict, and compile issues.
  - `parse_high_level_entry(path)` → raw dict from YAML file.
  - `compile_entry(raw)` → `CompiledEntry`. Validates strategy/factor_requirements/experiment sections, resolves factor aliases to low-level table.column targets, builds signal expressions from rules with `all`/`any` combinators, detects shadowed built-in aliases (close, open, high, low, pre_close, vol, amount), and emits structured errors/warnings.
  - `compile_to_strategy_spec_dict(entry)` → dict for `StrategySpec.from_mapping()`. Reads risk/holding from `rules.risk`, universe from `experiment.universe`.
  - `_compile_expression(rule_block, factor_targets, issues)` — converts rule blocks into pandas-evaluable expression strings. Handles comparison operators (`<`, `>`, `<=`, `>=`, `==`, `!=`) and crossover operators (`crosses_above`, `crosses_below` → warning + simple fallback).

- **Wired into CLI** (`src/quant_research_engine/apps/cli.py`):
  - Added `qre compile` subcommand with `--output-dir`, `--preflight`, `--db-url`, `--start`, `--end`, `--codes`, `--min-factor-coverage`, `--run-id` flags.
  - Compilation summary printed to stdout: strategy_id, name, family, direction, compile_status, factor targets, signal expressions, issues.
  - `--output-dir` writes `compiled_strategy_spec.json`.
  - `--preflight` runs existing preflight checks against the compiled low-level spec, including missing-factor extraction and emission.

- **Tests** (`tests/test_compiler.py`, new, 31 tests):
  - Column name builders (8 tests): simple, macd, bollinger, error cases.
  - Table name builder (1 test).
  - Indicator catalog (1 test).
  - RSI2 compile (3 tests): factor targets, signal expression, StrategySpec bridge.
  - EMA200 + Bollinger compile (3 tests): factor targets, signal expression, StrategySpec bridge.
  - MACD compile (2 tests): factor targets, crossover warning.
  - Error cases (6 tests): missing strategy/factor_requirements/experiment, unknown indicator, duplicate alias, built-in alias shadowing.
  - File round-trip (1 test): `parse_high_level_entry` from temp file.
  - Factor defaults (1 test): optional factor requirement.
  - StrategySpec bridge edge cases (3 tests): universe defaults, no exit rules, no rules section.

- **CLI tests** (`tests/test_cli.py`, 4 new tests):
  - `test_cli_compile_rsi2_success` — valid RSI2 entry compiles with exit code 0 and correct stdout keys.
  - `test_cli_compile_invalid_yaml_returns_2` — malformed entry returns exit code 2.
  - `test_cli_compile_with_output_dir_writes_spec` — `--output-dir` writes `compiled_strategy_spec.json` with correct fields.
  - `test_cli_compile_preflight_without_dates_returns_2` — `--preflight` without `--start`/`--end` returns exit code 2.

## Files Changed

- `src/quant_research_engine/strategies/compiler.py` — new (~410 lines)
- `src/quant_research_engine/apps/cli.py` — added `qre compile` parser + handler, imported compiler functions
- `tests/test_compiler.py` — 31 tests (29 compiler + 2 end-to-end runtime compatibility)
- `tests/test_cli.py` — 4 new CLI compile tests
- `docs/agent/09_CODING_HANDOFF.md` — this file (updated with review fix)
- `docs/agent/04_TASK_HANDOFF.md` — updated status
- `docs/agent/05_PROGRESS.md` — updated phase/task
- `docs/agent/11_AGENT_STATE.md` — phase to CODEX_REVIEWING
- `docs/agent/12_AGENT_BOARD.md` — handoff message

## Validation Results

```
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py -q
302 passed, 2 warnings in 3.01s
```

- All 31 compiler tests pass (29 compiler + 2 end-to-end runtime compatibility).
- All 4 new CLI compile tests pass.
- All existing tests pass (no regressions).
- 2 pre-existing numpy warnings (unrelated).

```
scripts/check-progress-docs.sh → passed
git diff --check → passed
```

## Review Fix (2026-05-22)

Blocking issue from `10_REVIEW_REPORT.md`: `_compile_expression()` emitted full factor target paths (`factors.stock_daily_momentum_close.rsi_2`) in signal expressions, but the expression evaluator in `signals.py` only supports `ast.Name` nodes, not `ast.Attribute` chains.

Fix applied:

- Changed `_compile_expression()` to use alias names directly in expressions (e.g. `rsi_fast`, `ema_200`) instead of resolving to full `factors.table.column` paths.
- Added validation warnings when a referenced alias is neither a declared factor nor a built-in market field.
- Added 2 end-to-end runtime compatibility tests that verify `compile_entry()` → `compile_to_strategy_spec_dict()` → `StrategySpec.from_mapping()` → `evaluate_expression_signal()` works correctly for both RSI2 and EMA200+Bollinger strategies with mock DataFrames.

## Design Decisions

- **`rules` dict stored in `CompiledEntry`**: the raw rules section (including `risk`) is needed by `compile_to_strategy_spec_dict` to read `stop_loss_pct` and `max_holding_days`. Previously these were incorrectly read from `experiment.risk`.
- **Full factor target paths in expressions**: the expression compiler resolves aliases to their full `factors.table.column` paths rather than keeping alias names. This means expressions are self-contained and directly evaluable without alias lookups.
- **Crossover operators emit warnings**: `crosses_above` and `crosses_below` have no direct low-level equivalent. They emit a warning and fall back to simple `>` / `<` comparisons. Runtime crossover support is future work.
- **Built-in alias protection**: aliases that shadow built-in market fields (close, open, high, low, pre_close, vol, amount) produce errors.
- **Compilation errors vs parse errors both return exit code 2**: both `parse_high_level_entry` and `compile_entry` exceptions are caught and reported to stderr.

## Residual Limitations

- Crossover operators (`crosses_above`, `crosses_below`) are not supported at runtime — emitted as simple comparisons with warnings.
- Optional factors: all factors are treated as `required: true` because `StrategySpec` has no optional-factor concept.
- The `compile` command's `--preflight` mode requires `--db-url` or env-var database configuration — no embedded smoke DB.
- Column name building for `stochastic` and `williams_r` uses the simple `{indicator}_{period}` pattern, which may need refinement when real `factors.*` tables for these indicators are confirmed.

## Constraints

- No database writes.
- No invocation of external projects.
- No changes to existing report behavior, manifest roles, or audit logic.
- Read-only data access preserved.
- Existing low-level `StrategySpec` workflow fully preserved.
- Existing uncommitted GUI changes preserved.

## Git State

- Branch: `master`
- Last finalized commit: `146acd2` (Codex finalized `QRE-STRATEGY-ENTRY-CONTRACT-DOCS-001`)
- Working tree contains compiler module, CLI wiring, tests, and agent doc updates.

## Next Suggested Step

Codex reviews the implementation, runs validation, and writes `docs/agent/10_REVIEW_REPORT.md`.
