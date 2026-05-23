# Task Handoff

## Current Task

Add shared-cash support for the full-market report bundle — add `engine_mode` parameter to all builders in `full_market_report.py`, wire into `write_shared_cash_result()`, and add 19 new tests.

## Task ID

QRE-SHARED-CASH-FULL-MARKET-REPORT-001

## Current Status

IMPLEMENTED. Claude Code has completed the shared-cash full-market report support: all 6 builders + entry point accept `engine_mode`, `write_shared_cash_result()` now calls `write_full_market_report()` with `engine_mode="shared_cash"`, 19 new tests pass (519 total).

## Current Owner

CLAUDE_CODE

## Completed

- Shared-cash full-market report support implemented:
  - `src/quant_research_engine/portfolio/full_market_report.py` — `engine_mode` parameter added to `build_trades_ledger`, `build_round_trips`, `build_symbol_performance`, `build_full_market_equity_curve`, `build_strategy_performance`, and `write_full_market_report`. Shared-cash branches read flat DataFrames (orders, trades, equity_curve) instead of `dict[str, SingleSymbolBacktestResult]`. `failed_orders` parameter for correct failed order counting.
  - `src/quant_research_engine/portfolio/io.py` — `write_full_market_report()` called from `write_shared_cash_result()` with `engine_mode="shared_cash"`. `_shared_manifest_role()` updated for 9 full-market artifact roles. `_shared_report_paths()` includes full-market labels.
  - `tests/test_full_market_report.py` — 6 new test classes (17 tests): `TestBuildTradesLedgerSharedCash`, `TestBuildRoundTripsSharedCash`, `TestBuildSymbolPerformanceSharedCash`, `TestBuildFullMarketEquityCurveSharedCash`, `TestBuildStrategyPerformanceSharedCash`, `TestWriteFullMarketReportSharedCash`.
  - `tests/test_portfolio_io.py` — 2 new tests: `test_write_shared_cash_result_includes_full_market_files`, `test_shared_cash_manifest_validates_full_market_roles`.
  - 519 tests pass, no regressions.

- Three high-level strategy entry YAML files created from `docs/strategy_entry/examples.md`:
  - `examples/rsi2_oversold_reversal_entry.yaml` — RSI2 mean-reversion (1 factor: rsi_fast)
  - `examples/ema200_bollinger_reversal_entry.yaml` — EMA200 + Bollinger mean-reversion (3 factors: ema_200, bb_upper, bb_lower)
  - `examples/macd_zero_cross_momentum_entry.yaml` — MACD momentum (2 factors: macd_line, macd_signal)
- All three compile successfully via `qre compile` with `compile_status=ok`:
  - RSI2: 1 factor target, entry `(rsi_fast < 10)`, exit `(rsi_fast > 70)`
  - EMA200+Bollinger: 3 factor targets, entry `(close > ema_200) and (close <= bb_lower)`, exit `(close >= bb_upper)`
  - MACD: 2 factor targets, entry `(macd_line > macd_signal) and (macd_line < 0)`, exit `(macd_line < macd_signal)`, 2 crossover warnings
- Compiled artifacts written to `outputs/strategy-entry-smoke/<strategy_id>/compiled_strategy_spec.json`
- Preflight skipped: no database configured (`QRE_MARKET_DB_URL` and `SR_MARKET_DB_URL` unset)
- Missing-factor skipped: depends on preflight
- Backtest smoke skipped: no database available
- Consolidated smoke report: `docs/strategy_entry/three_strategy_smoke_report.md`
- All skip justifications documented per acceptance criteria
- 302 tests pass, no regressions

## Scope Notes

- QRE owns strategy input standards, factor availability validation, backtest execution, and report output contracts.
- QRE does not own rewriting `research-notes` / `strategy-research` or computing indicators internally.
- `indicators_tushare` remains the upstream technical-indicator calculator and `factors.*` producer.
- Strategy-entry direction clarified:
  - Entry strategy work is documentation-first.
  - QRE should write the MD contract that tells humans, Codex, Claude Code, and external strategy projects how a strategy entry file should be authored.
  - External strategy projects can convert natural-language strategy descriptions into QRE-standard strategy files.
- Strategy entry standard docs completed: `docs/strategy_entry/` with 6 documentation files.
- Full-market report design and implementation completed:
  - MT5 workbook baseline + TradingView strategy tester metrics unified into QRE batch backtest outputs.
  - `src/quant_research_engine/portfolio/full_market_report.py`, wired into `io.py`, 9 manifest roles, 23 tests.
  - `realized_pnl` semantic fix applied and regression-tested.
- Missing-factor handoff implementation completed:
  - `src/quant_research_engine/strategies/missing_factor.py` — `MissingFactorRequest` model, extraction from `PreflightReport`, JSON emission.
  - `src/quant_research_engine/apps/cli.py` — `qre preflight --output-dir` writes `missing_factor_requests.json`.
  - `tests/test_missing_factor.py` — 25 tests (model, parsing, extraction, emission).
  - `tests/test_cli.py` — 3 CLI tests (output-dir empty, output-dir with missing, no-output-dir stdout).
  - `docs/strategy_entry/missing_factor_request.md` — lifecycle states added.
- High-level strategy entry compiler/linkage module: `src/quant_research_engine/strategies/compiler.py` (~410 lines)
  - `_INDICATOR_CATALOG` with 13 indicators (rsi, ema, sma, wma, macd, bollinger, atr, adx, cci, mfi, obv, stochastic, williams_r)
  - Column name builders: `_col_simple`, `_col_macd`, `_col_bollinger`
  - `parse_high_level_entry`, `compile_entry`, `compile_to_strategy_spec_dict`
  - Expression compiler with `all`/`any` combinators, comparison and crossover operators
  - Built-in alias shadow detection (close, open, high, low, pre_close, vol, amount)
  - Factor alias → `factors.table.column` resolution via catalog
- CLI `qre compile` command with `--output-dir`, `--preflight`, and preflight date flags
  - Stdout compilation summary (strategy_id, name, family, factor_targets, expressions, issues)
  - `compiled_strategy_spec.json` output for debugging
  - Optional preflight integration with missing-factor extraction
- Tests: 31 compiler tests + 4 CLI compile tests
- 302 tests pass, no regressions
- Smoke runner orchestration implemented:
  - `src/quant_research_engine/strategies/smoke_runner.py` — `StrategySmokeResult`, `SmokeSummary`, `run_strategy_smoke()`, `_check_db_available()`, `_try_compile()`, `_try_preflight()`, `_write_smoke_summary()`
  - `qre strategy-smoke` CLI command with `--strategies`, `--output-dir`, `--no-preflight`, `--no-backtest`, `--start`, `--end`
  - Deterministic `smoke_summary.json` with `run_id`, `generated_at`, `environment`, `strategies[]`, `overall_status`
  - No-DB mode is first-class: exit code 0, explicit skip reasons per stage
  - Exit code 2 for true runner failure or compile failures
  - 12 runner tests + 6 CLI strategy-smoke tests
  - 320 tests pass, no regressions
- Backtest-smoke truthiness fix implemented:
  - `src/quant_research_engine/strategies/smoke_runner.py` — `_try_backtest_smoke()` executes a real `BatchBacktestEngine` run; `backtest_smoke=pass` only after execution success; `backtest_smoke=fail` with reason on error
  - `tests/test_smoke_runner.py` — 5 truthiness tests (compile fail, no DB, empty frame, fail→overall_fail, pass→overall_pass)
  - 325 tests pass, no regressions
- Smoke artifact parity implemented:
  - `src/quant_research_engine/strategies/smoke_runner.py` — expanded `_try_backtest_smoke()` with 3 artifact types (summary CSV, top-20 returns CSV, metrics JSON); `durations_s` field on `StrategySmokeResult`; stage timing instrumentation
  - `src/quant_research_engine/apps/cli.py` — enhanced `strategy-smoke` stdout with artifact_count, per-artifact paths, and stage durations
  - `tests/test_smoke_runner.py` — 22 tests (12 original + 5 truthiness + 5 artifact parity)
  - `tests/test_cli.py` — 7 strategy-smoke tests (6 original + 1 artifact visibility)
- Smoke manifest/audit integration implemented:
  - `src/quant_research_engine/portfolio/report_manifest.py` — added `"strategy_smoke_report_manifest"` to `_SUPPORTED_MANIFEST_KINDS`
  - `src/quant_research_engine/strategies/smoke_runner.py` — `_write_smoke_report_manifest()` (~50 lines); wired into `run_strategy_smoke()`
  - `src/quant_research_engine/apps/cli.py` — manifest path in `strategy-smoke` stdout
  - `tests/test_smoke_runner.py` — 27 tests (12 original + 5 truthiness + 5 artifact parity + 5 manifest)
  - `tests/test_cli.py` — 8 strategy-smoke tests (6 original + 1 artifact visibility + 1 manifest path)
  - 337 tests pass, no regressions
- Smoke manifest filter parity implemented:
  - `tests/test_cli.py` — 15 new CLI regression tests for smoke manifest filtering across `report-files` (9) and `report-audit` (6) with role/symbol/strict/json selector combinations
  - No runtime changes needed — existing command surfaces already handle smoke manifest filtering correctly
  - 352 tests pass, no regressions
- Smoke discovery CLI implemented:
  - `src/quant_research_engine/apps/cli.py` — `qre smoke-files` command with text/JSON output modes and `--strategy`/`--role` selectors; reads `smoke_summary.json` + `smoke_report_manifest.json`
  - `tests/test_cli.py` — 8 new CLI regression tests
  - `docs/strategy_entry/three_strategy_smoke_report.md` — discovery CLI usage section added
  - 360 tests pass, no regressions
- Smoke discovery latest-run auto-discovery implemented:
  - `src/quant_research_engine/apps/cli.py` — `--latest` flag; auto-scan subdirectories of `outputs/strategy-entry-smoke` for `smoke_summary.json`, pick most recent by mtime; `resolved_output_dir` in text/JSON output
  - `tests/test_cli.py` — 3 new CLI tests (latest discovery success, no runs, output-dir precedence); 2 existing test assertions updated
  - 363 tests pass, no regressions
- Smoke discovery stability hardening implemented:
  - Deterministic strategy ordering (sorted by `strategy_id`) and artifact key ordering
  - `source_mode` indicator (`manifest` vs `artifacts_fallback`) in text and JSON output
  - Manifest/fallback count parity with aligned fixtures and tests
  - 4 new CLI regression tests; 367 tests pass
- Smoke discovery `--details` mode implemented:
  - `--details` flag for per-strategy stage/artifact details in text (indented blocks) and JSON (`strategies` array)
  - Selector interplay with `--strategy`/`--role` preserved
  - 4 new CLI regression tests; 371 tests pass
- Smoke discovery `--output-file` export implemented:
  - `--output-file <path>` parser + export handling for text and JSON output
  - Parent directory auto-creation (`parent.mkdir(parents=True, exist_ok=True)`)
  - Write-failure stderr error message + exit code 2
  - 4 new CLI regression tests; 375 tests pass
- Smoke discovery `--check-exists` artifact audit implemented:
  - `--check-exists` parser flag + artifact presence validation logic (~35 lines)
  - Collects paths from manifest (preferred) or summary artifacts; checks `is_file()` per path
  - Text mode: missing paths printed one-per-line to stderr
  - JSON mode: additive `missing_artifact_count` + `missing_artifacts` (sorted) fields
  - Exit code 2 when any referenced artifact is missing
  - 4 new CLI regression tests; 379 tests pass
- Smoke discovery `--require-match` strict selector implemented:
  - `--require-match` parser flag + strict no-match logic (~10 lines)
  - `--strategy` no-match with `--require-match`: stderr "No matching strategy: ..." + exit 2
  - `--role` no-match with `--require-match`: stderr "No matching role: ..." + exit 2
  - JSON mode preserves payload emission and returns 2 with stderr reason
  - Default behavior unchanged when flag absent
  - 4 new CLI regression tests; 383 tests pass
- Smoke discovery `--quiet` no-stdout automation mode implemented:
  - `--quiet` parser flag; wrapped 4 stdout `print()` calls in `if not args.quiet:` guards
  - Text output, JSON payload, and `--list-missing` path lines all suppressed when `--quiet` is set
  - Stderr diagnostics and exit codes preserved unchanged
  - `--output-file` writing unaffected by `--quiet`
  - 4 new CLI regression tests; 391 tests pass
- Smoke discovery `--status-only` compact automation mode implemented:
  - `--status-only` parser flag; text mode emits only `overall_status` string
  - JSON mode emits minimal `{"overall_status": "...", "run_id": "..."}` payload
  - Full output payload and text output preserved when flag absent
  - `--quiet` suppresses even `--status-only` stdout
  - 4 new CLI regression tests; 395 tests pass
- Smoke discovery `--status-file` persisted CI output implemented:
  - `--status-file <path>` parser flag; writes effective payload in all 3 output branches
  - Content matches current mode: full text/JSON or compact `--status-only` output
  - Parent directories auto-created; write failure returns exit 2 with stderr
  - `--quiet` does not suppress status-file writing
  - 5 new CLI regression tests; 400 tests pass
- Smoke discovery `--status-format` format selector implemented:
  - `--status-format {text,json}` parser flag; requires `--status-only`
  - `text` forces plain status line; `json` forces minimal JSON regardless of `--json` flag
  - Invalid combination (`--status-format` without `--status-only`) returns exit 2 with stderr
  - `--quiet` suppresses stdout but not `--status-file` writes
  - 4 new CLI regression tests; 404 tests pass
- Smoke discovery `--status-reason` failure enrichment implemented:
  - `--status-reason` parser flag; requires `--status-only`
  - Derives first failing stage reason from strategy compile/preflight/missing_factor/backtest_smoke
  - Text mode: emits `<status>\t<reason>`; JSON mode: adds `"reason"` key
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 408 tests pass
- Smoke discovery `--status-code` numeric code output implemented:
  - `--status-code` parser flag; requires `--status-only`
  - Maps `overall_status` to numeric code: `ok`→`0`, `fail`→`1`
  - Text mode: emits numeric string (e.g. `"0"` or `"1"`)
  - JSON mode: adds `"status_code"` key to minimal payload
  - `--status-reason` interaction preserved (code + reason concatenated in text, additive in JSON)
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 412 tests pass
- Smoke discovery `--status-code` finalized (Codex review PASS).
- Smoke discovery `--status-meta` metadata enrichment implemented:
  - `--status-meta` parser flag; requires `--status-only`
  - Text mode: appends `\trun_id=<value>\tsource_mode=<mode>` after status payload
  - JSON mode: adds `"source_mode"` key to minimal payload
  - Compatible with `--status-code`, `--status-reason`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 416 tests pass
- Smoke discovery `--status-meta` finalized (Codex review PASS).
- Smoke discovery `--status-summary` strategy count enrichment implemented:
  - `--status-summary` parser flag; requires `--status-only`
  - Text mode: appends `\ttotal=<n>\tpass=<n>\tfail=<n>\tskip=<n>` after status payload
  - JSON mode: adds `strategy_total`, `strategy_pass`, `strategy_fail`, `strategy_skip` integer keys
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 420 tests pass
- Smoke discovery `--status-summary` finalized (Codex review PASS).
- Smoke discovery `--status-fail-key` first failing strategy id implemented:
  - `--status-fail-key` parser flag; requires `--status-only`
  - Derives first failing strategy_id from ordered strategy stage statuses
  - Text mode: appends `\tfail_key=<strategy_id-or-empty>` after status payload
  - JSON mode: adds `"fail_key"` string or `null` key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 5 new CLI regression tests; 425 tests pass
- Smoke discovery `--status-fail-key` finalized (Codex review PASS).
- Smoke discovery `--status-fail-stage` first failing stage name implemented:
  - `--status-fail-stage` parser flag; requires `--status-only`
  - Derives first failing stage from ordered strategies with precedence (compile/preflight/missing_factor/backtest_smoke)
  - Text mode: appends `\tfail_stage=<stage-or-empty>` after status payload
  - JSON mode: adds `"fail_stage"` string or `null` key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 5 new CLI regression tests; 430 tests pass
- Smoke discovery `--status-fail-stage` finalized (Codex review PASS).
- Smoke discovery `--status-timestamp` run generation timestamp implemented:
  - `--status-timestamp` parser flag; requires `--status-only`
  - Derives timestamp from `smoke_summary.generated_at`
  - Text mode: appends `\ttimestamp=<generated_at-or-empty>` after status payload
  - JSON mode: adds `"timestamp"` string or `null` key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 434 tests pass
- Smoke discovery `--status-timestamp` finalized (Codex review PASS).
- Smoke discovery `--status-output-dir` resolved run directory implemented:
  - `--status-output-dir` parser flag; requires `--status-only`
  - Derives path from already-resolved smoke run directory
  - Text mode: appends `\toutput_dir=<absolute-path>` after status payload
  - JSON mode: adds `"output_dir"` string key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 438 tests pass
- Smoke discovery `--status-manifest-path` resolved manifest file path implemented:
  - `--status-manifest-path` parser flag; requires `--status-only`
  - Derives path from already-resolved `manifest_path` variable (`output_dir / "smoke_report_manifest.json"`)
  - Text mode: appends `\tmanifest_path=<absolute-path>` after status payload
  - JSON mode: adds `"manifest_path"` string key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 442 tests pass
- Smoke discovery `--status-manifest-exists` manifest existence boolean implemented:
  - `--status-manifest-exists` parser flag; requires `--status-only`
  - Derives bool from `manifest_path.is_file()`
  - Text mode: appends `\tmanifest_exists=true|false` after status payload
  - JSON mode: adds `"manifest_exists"` boolean key
  - Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-format`, `--quiet`, `--status-file`
  - Invalid combination returns exit 2 with stderr
  - 4 new CLI regression tests; 446 tests pass

## Scope Notes (Strategy Entry MD Contract)

The strategy-entry MD contract is complete under `docs/strategy_entry/`:

- Strategy Card fields (`strategy_card.md`).
- Factor Requirements fields (`factor_requirements.md`).
- Experiment Plan fields (`experiment_plan.md`).
- Missing-factor request fields for `indicators_tushare` (`missing_factor_request.md`).
- Three complete examples: RSI2, EMA200+Bollinger, MACD (`examples.md`).
- README with end-to-end flow and project boundaries (`README.md`).
- Three-strategy smoke report (`three_strategy_smoke_report.md`).

The current report-output implementation produces:

- `backtest_report.xlsx` (10 sheets: Overview, Performance, TradesLedger, RoundTrips, SymbolPerformance, EquityCurve, DrawdownCurve, TradeAnalysis, CapitalUsage, Artifacts)
- `trades_ledger.csv`, `round_trips.csv`, `symbol_performance.csv`, `strategy_performance.json`, `equity_curve.csv`, `drawdown_curve.csv`, `trade_analysis.json`, `capital_usage.json`
- `report_manifest.json` (updated with new stable roles)

The current missing-factor implementation produces:

- `missing_factor_requests.json` — stable JSON array matching `docs/strategy_entry/missing_factor_request.md` schema.
- Stdout summary: `missing_factor_count`, `missing_factor_status` (ok/pending), per-missing-factor lines.
- Empty `[]` when no factors are missing.

## Residual Limitations

- Commission splits (`commission`, `stamp_tax`, `transfer_fee`, `slippage`) are null in the trades ledger because the current engine does not track per-order cost components separately.
- Margin fields (`average_margin_used`, `max_margin_used`, `min_margin_used`) are null because the current simulation is cash-only.
- Intratrade path fields (`max_favorable_return`, `max_adverse_return`, bars-in-trade stats) are null because the A-share daily engine does not track intra-trade bar-level paths.
- Batch-only for the first release; shared-cash reuse is future work.
- Column name parsing is heuristic; `expected_table` and `expected_column` are the authoritative fields.
- All factors treated as `required: true` — current `StrategySpec` has no optional-factor concept.
- Crossover operators (`crosses_above`, `crosses_below`) emit warnings and fall back to simple comparisons. True crossover support requires runtime engine changes.
- Preflight, missing-factor, and backtest smoke stages require a configured PostgreSQL database.

## Prior Completed Context

The local browser backtest console is complete and finalized locally in commit `766dc98`. A later local GUI update made the verified EMA200 + Bollinger reversal strategy preload into the editor from `examples/ema200_bollinger_reversal.yaml`; those GUI files are still uncommitted and should not be reverted by this planning task.

- Smoke discovery `--status-artifact-count` artifact total count implemented:
  - `src/quant_research_engine/apps/cli.py` — `--status-artifact-count` parser flag; requires `--status-only`; derives `artifact_total = sum(artifact_roles.values())` from already-computed `artifact_roles` dict; text mode appends `\tartifact_count=<int>`; JSON mode adds `"artifact_count"` integer key
  - `tests/test_cli.py` — 4 new tests (text artifact_count, JSON artifact_count integer assertion, requires-status-only validation, quiet+status-file)
  - `docs/strategy_entry/three_strategy_smoke_report.md` — usage examples, description paragraph, exit codes and compatibility notes
  - 98 smoke-files tests pass; 450 full suite pass
- Smoke discovery `--status-strategy-count` strategy total count implemented:
  - `src/quant_research_engine/apps/cli.py` — `--status-strategy-count` parser flag; requires `--status-only`; derives count from `len(strategies)`; text mode appends `\tstrategy_count=<int>`; JSON mode adds `"strategy_count"` integer key
  - `tests/test_cli.py` — 4 new tests (text strategy_count, JSON strategy_count integer assertion, requires-status-only validation, quiet+status-file)
  - `docs/strategy_entry/three_strategy_smoke_report.md` — usage examples, description paragraph, exit codes and compatibility notes
  - 102 smoke-files tests pass; 454 full suite pass
- Smoke discovery `--status-fail-count` failing-strategy count implemented:
  - `src/quant_research_engine/apps/cli.py` — `--status-fail-count` parser flag; requires `--status-only`; derives count from already-computed `summary_fail` (strategies where any stage is not pass/skip); text mode appends `\tfail_count=<int>`; JSON mode adds `"fail_count"` integer key
  - `tests/test_cli.py` — 4 new tests (text fail_count, JSON fail_count integer assertion, requires-status-only validation, quiet+status-file)
  - `docs/strategy_entry/three_strategy_smoke_report.md` — usage examples, description paragraph, exit codes and compatibility notes
  - 106 smoke-files tests pass; 458 full suite pass
- Smoke discovery `--status-skip-count` skipped-strategy count implemented:
  - `src/quant_research_engine/apps/cli.py` — `--status-skip-count` parser flag; requires `--status-only`; derives count from already-computed `summary_skip` (strategies where all stages are `skip`); text mode appends `	skip_count=<int>`; JSON mode adds `"skip_count"` integer key
  - `tests/test_cli.py` — 4 new tests (text skip_count, JSON skip_count integer assertion, requires-status-only validation, quiet+status-file)
  - `docs/strategy_entry/three_strategy_smoke_report.md` — usage examples, description paragraph, exit codes and compatibility notes
  - 110 smoke-files tests pass; 462 full suite pass
- Smoke discovery `--status-pass-count` passed-strategy count implemented:
  - `src/quant_research_engine/apps/cli.py` — `--status-pass-count` parser flag; requires `--status-only`; derives count from already-computed `summary_pass` (strategies where all stages are `pass`); text mode appends `\tpass_count=<int>`; JSON mode adds `"pass_count"` integer key
  - `tests/test_cli.py` — 4 new tests (text pass_count=2, JSON pass_count integer assertion, requires-status-only validation, quiet+status-file)
  - `docs/strategy_entry/three_strategy_smoke_report.md` — usage examples, description paragraph, exit codes and compatibility notes
  - 114 smoke-files tests pass; 466 full suite pass

## Validation Baseline

```bash
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py tests/test_portfolio_report_manifest.py tests/test_smoke_runner.py -q
scripts/check-progress-docs.sh
git diff --check
```

Current results: 466 passed, 2 warnings (pre-existing numpy) in 4.86s; all checks pass.

## Known Risks

- Existing report outputs and manifest roles remain compatible.
- First implementation does not have true charts, but workbook sheets and data tables are emitted.
- Current engine does not split every cost component (`commission`, `stamp_tax`, `transfer_fee`, `slippage_amount`); MT5 columns exist with null/zero conventions where source data is unavailable.
- Independent batch mode has no single shared cash account; full-market equity is synthesized by summing per-symbol equity curves.
- QRE must not compute missing indicators internally; it should emit missing-factor requests for `indicators_tushare`.
- Column name parsing from `factor_fields` targets is heuristic and documented as best-effort.
- Existing uncommitted GUI changes are outside this planning task and must be preserved.
- Table name for EMA with source=typical is `stock_daily_overlap_typical` (compiler-generated). If upstream `factors` uses `typical_price`, the entry YAML should use `source: typical_price`.

## Next Suggested Step

Claude Code (acting finalizer) performs git commit. Smoke discovery status enrichment series is now complete.
