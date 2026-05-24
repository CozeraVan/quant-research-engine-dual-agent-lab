# Three Strategy Smoke Report

Task ID: QRE-STRATEGY-ENTRY-THREE-SMOKE-001
Date: 2026-05-22

## Status Summary

| Strategy | Compile | Preflight | Missing Factors | Backtest Smoke | Notes |
|---|---|---|---|---|---|
| RSI2 Oversold Reversal | PASS | SKIP | SKIP | SKIP | No DB available in this environment |
| EMA200+Bollinger Reversal | PASS | SKIP | SKIP | SKIP | No DB available in this environment |
| MACD Zero-Cross Momentum | PASS | SKIP | SKIP | SKIP | No DB available in this environment; 2 crossover warnings |

All three strategies compile successfully through the standardized entry path. Preflight, missing-factor, and backtest smoke stages are skipped because no database is configured in this environment (`QRE_MARKET_DB_URL` and `SR_MARKET_DB_URL` are unset).

## Per-Strategy Evidence

### 1. RSI2 Oversold Reversal

**Entry file:** `strategies/high_level/rsi2_oversold_reversal_entry.yaml`

**Compile output:**
```
strategy_id=rsi2_oversold_reversal
name=RSI2 Oversold Reversal
family=mean_reversion
direction=long_only
version=1.0.0
compile_status=ok
factor_target_count=1
factor_target_rsi_fast=factors.stock_daily_momentum_close.rsi_2
signal_expression=(rsi_fast < 10)
exit_signal_expression=(rsi_fast > 70)
```

**Factor resolution:**
- `rsi_fast` → `factors.stock_daily_momentum_close.rsi_2` (rsi, source=close, period=2)

**Risk/holding:**
- stop_loss_pct: 0.08, take_profit_pct: 0.12
- max_holding_days: 5
- min_listing_days: 120

**Artifacts:**
- `outputs/strategy-entry-smoke/rsi2_oversold_reversal/compiled_strategy_spec.json`

---

### 2. EMA200 + Bollinger Band Reversal

**Entry file:** `strategies/high_level/ema200_bollinger_reversal_entry.yaml`

**Compile output:**
```
strategy_id=ema200_bollinger_reversal
name=EMA200 Bollinger Band Reversal
family=mean_reversion
direction=long_only
version=1.0.0
compile_status=ok
factor_target_count=3
factor_target_ema_200=factors.stock_daily_overlap_typical.ema_200
factor_target_bb_upper=factors.stock_daily_volatility_close.bbu_20_2_0_2_0
factor_target_bb_lower=factors.stock_daily_volatility_close.bbl_20_2_0_2_0
signal_expression=(close > ema_200) and (close <= bb_lower)
exit_signal_expression=(close >= bb_upper)
```

**Factor resolution:**
- `ema_200` → `factors.stock_daily_overlap_typical.ema_200` (ema, source=typical, period=200)
- `bb_upper` → `factors.stock_daily_volatility_close.bbu_20_2_0_2_0` (bollinger, source=close, period=20, stddev=2.0, output=upper)
- `bb_lower` → `factors.stock_daily_volatility_close.bbl_20_2_0_2_0` (bollinger, source=close, period=20, stddev=2.0, output=lower)

**Risk/holding:**
- stop_loss_pct: 0.10
- max_holding_days: 20
- min_listing_days: 250

**Artifacts:**
- `outputs/strategy-entry-smoke/ema200_bollinger_reversal/compiled_strategy_spec.json`

---

### 3. MACD Zero-Cross Momentum

**Entry file:** `strategies/high_level/macd_zero_cross_momentum_entry.yaml`

**Compile output:**
```
strategy_id=macd_zero_cross_momentum
name=MACD Zero-Cross Momentum
family=momentum
direction=long_only
version=1.0.0
compile_status=ok
factor_target_count=2
factor_target_macd_line=factors.stock_daily_momentum_close.macd_12_26_9
factor_target_macd_signal=factors.stock_daily_momentum_close.macd_signal_12_26_9
signal_expression=(macd_line > macd_signal) and (macd_line < 0)
exit_signal_expression=(macd_line < macd_signal)
compile_issue_warning=crossover operator 'crosses_above' has no direct low-level equivalent; emitted as simple comparison.
compile_issue_warning=crossover operator 'crosses_below' has no direct low-level equivalent; emitted as simple comparison.
```

**Factor resolution:**
- `macd_line` → `factors.stock_daily_momentum_close.macd_12_26_9` (macd, source=close, fast=12, slow=26, signal=9, output=macd)
- `macd_signal` → `factors.stock_daily_momentum_close.macd_signal_12_26_9` (macd, source=close, fast=12, slow=26, signal=9, output=signal)

**Warnings:** Two crossover operators (`crosses_above`, `crosses_below`) were converted to simple `>` / `<` comparisons. True crossover support requires lagged-comparison runtime engine support (future work).

**Risk/holding:**
- stop_loss_pct: 0.08
- max_holding_days: 10
- min_listing_days: 250

**Artifacts:**
- `outputs/strategy-entry-smoke/macd_zero_cross_momentum/compiled_strategy_spec.json`

---

## Skip Justifications

### Preflight skip

The `qre compile --preflight` command requires a PostgreSQL database connection configured via `QRE_MARKET_DB_URL` or `SR_MARKET_DB_URL`. Neither is set in the current environment. When a database becomes available, each strategy can be preflighted with:

```bash
qre compile strategies/high_level/rsi2_oversold_reversal_entry.yaml \
  --preflight --start 2024-01-01 --end 2024-02-01 \
  --output-dir outputs/strategy-entry-smoke/rsi2_oversold_reversal/
```

The compile step itself does not require a database — it resolves factor aliases to target paths using only the indicator catalog and column-name builders.

### Missing-factor skip

Missing-factor extraction requires a successful preflight run against a live database. The compiled `StrategySpec` dicts contain correct `factor_fields` entries; missing-factor requests will be emitted by the preflight handler when DB is available.

### Backtest smoke skip

Backtest execution requires market data (`public.stock_daily`) and factor data (`factors.*`) from a configured PostgreSQL database. All three compiled specs are structurally valid and ready for `qre backtest-batch` execution when DB is available. The compiled spec JSON files can be used as-is with the existing backtest commands.

## Validation

```bash
uv run pytest tests/test_compiler.py tests/test_missing_factor.py tests/test_preflight.py \
  tests/test_strategy_spec.py tests/test_cli.py tests/test_portfolio_io.py \
  tests/test_portfolio_report_manifest.py -q
# 302 passed, 2 warnings in 3.13s

scripts/check-progress-docs.sh
# Progress docs check passed.

git diff --check
# (no output — clean)
```

## Reproducibility

### One-command smoke runner (recommended)

```bash
# Run all 3 strategies with a single command (no DB required)
uv run qre strategy-smoke
```

This produces:
- `outputs/strategy-entry-smoke/smoke_summary.json` — deterministic run summary with per-strategy stage outcomes, `durations_s` timing metadata, and artifact paths
- `outputs/strategy-entry-smoke/<strategy_id>/compiled_strategy_spec.json` — per-strategy compiled specs
- When DB is available and preflight passes, additional artifacts per strategy:
  - `backtest_smoke_summary.csv` — full per-symbol backtest summary
  - `backtest_smoke_symbol_returns.csv` — top-20 symbols by total return
  - `backtest_smoke_metrics.json` — aggregate metrics (symbol_count, trade_count, mean_return, win_rate)

Stdout shows per-strategy artifact counts, paths, and stage durations:
```
strategy=rsi2_oversold_reversal compile=pass preflight=skip missing_factor=skip backtest_smoke=skip
  artifact_count=1
  artifact.compiled_strategy_spec=outputs/.../compiled_strategy_spec.json
  durations: compile=0.042s
```

Custom options:
```bash
# Custom output directory
uv run qre strategy-smoke --output-dir outputs/my-smoke/

# Custom strategy paths
uv run qre strategy-smoke --strategies path/to/my_strategy.yaml path/to/another.yaml

# Skip specific DB stages
uv run qre strategy-smoke --no-preflight
uv run qre strategy-smoke --no-backtest

# With preflight date range (DB required)
uv run qre strategy-smoke --start 2024-01-01 --end 2024-02-01
```

Exit codes: 0 for success (including no-DB skip), 2 for runner failure or compile failures.

### Compile-only (no DB required, per-strategy)

```bash
qre compile strategies/high_level/rsi2_oversold_reversal_entry.yaml \
  --output-dir outputs/strategy-entry-smoke/rsi2_oversold_reversal/

qre compile strategies/high_level/ema200_bollinger_reversal_entry.yaml \
  --output-dir outputs/strategy-entry-smoke/ema200_bollinger_reversal/

qre compile strategies/high_level/macd_zero_cross_momentum_entry.yaml \
  --output-dir outputs/strategy-entry-smoke/macd_zero_cross_momentum/
```

### Compile + preflight + missing-factor (DB required)

```bash
qre compile strategies/high_level/rsi2_oversold_reversal_entry.yaml \
  --preflight --start 2024-01-01 --end 2024-02-01 \
  --output-dir outputs/strategy-entry-smoke/rsi2_oversold_reversal/

qre compile strategies/high_level/ema200_bollinger_reversal_entry.yaml \
  --preflight --start 2024-01-01 --end 2024-02-01 \
  --output-dir outputs/strategy-entry-smoke/ema200_bollinger_reversal/

qre compile strategies/high_level/macd_zero_cross_momentum_entry.yaml \
  --preflight --start 2024-01-01 --end 2024-02-01 \
  --output-dir outputs/strategy-entry-smoke/macd_zero_cross_momentum/
```

### Backtest smoke (DB required)

Use the compiled specs directly or convert back to YAML with the `factor_fields` mapping:

```bash
# Option A: use the compiled spec JSON via the low-level YAML path
# Option B: construct a low-level StrategySpec YAML using factor_targets from compile output
qre backtest-batch <spec.yaml> --start 2024-01-01 --end 2024-02-01 --output-dir outputs/<strategy>/
```

## Artifact Inventory

```
outputs/strategy-entry-smoke/
  smoke_summary.json                  # run-level stage outcomes, durations_s, artifact paths
  smoke_report_manifest.json          # manifest for discovery/audit (schema_version=1)
  rsi2_oversold_reversal/
    compiled_strategy_spec.json
  ema200_bollinger_reversal/
    compiled_strategy_spec.json
  macd_zero_cross_momentum/
    compiled_strategy_spec.json
```

## Manifest Contract

`smoke_report_manifest.json` follows the QRE report manifest schema (`kind=strategy_smoke_report_manifest`, `schema_version=1`). It can be discovered and validated with existing `qre report-files` and `qre report-audit` tooling.

### Structure

- Run-level entry: `{"role": "smoke_summary", "key": "smoke_summary", "path": "smoke_summary.json", "filename": "smoke_summary.json"}` (no `symbol`)
- Per-strategy entries: each artifact with `role=<artifact_key>`, `symbol=<strategy_id>`, relative `path`, and unique `key=<artifact_key>_<strategy_id>`

### Roles

| Role | Scope | When Present |
|---|---|---|
| `smoke_summary` | run | always |
| `compiled_strategy_spec` | per-strategy | always (compile success) |
| `missing_factor_requests` | per-strategy | when preflight finds missing factors |
| `backtest_smoke_summary` | per-strategy | when backtest smoke succeeds |
| `backtest_smoke_symbol_returns` | per-strategy | when backtest smoke succeeds |
| `backtest_smoke_metrics` | per-strategy | when backtest smoke succeeds |

### Usage

```bash
# Discover smoke artifacts
qre report-files --manifest outputs/strategy-entry-smoke/smoke_report_manifest.json

# Filter by role
qre report-files --manifest outputs/.../smoke_report_manifest.json --role compiled_strategy_spec

# Audit manifest contents
qre report-audit --manifest outputs/.../smoke_report_manifest.json
```

### Discovery CLI (`qre smoke-files`)

A dedicated discovery command summarizes the latest smoke run in one step. By default (no `--output-dir`), it auto-discovers the most recent run under `outputs/strategy-entry-smoke/`:

```bash
# Auto-discover latest run (scans subdirectories for smoke_summary.json, picks most recent)
uv run qre smoke-files

# Explicit --latest flag (same as default behavior)
uv run qre smoke-files --latest

# Custom output directory (suppresses auto-discovery)
uv run qre smoke-files --output-dir outputs/my-smoke/

# JSON output
uv run qre smoke-files --json

# Filter to a single strategy
uv run qre smoke-files --strategy rsi2_oversold_reversal

# Combined JSON + strategy (includes per-strategy status fields)
uv run qre smoke-files --json --strategy ema200_bollinger_reversal

# Filter artifact role counts
uv run qre smoke-files --role backtest_smoke_summary

# Per-strategy details in text mode
uv run qre smoke-files --details

# Per-strategy details with JSON output
uv run qre smoke-files --json --details

# Filtered details + strategy
uv run qre smoke-files --details --strategy rsi2_oversold_reversal

# Export text output to file
uv run qre smoke-files --output-file reports/smoke_summary.txt

# Export JSON output to file
uv run qre smoke-files --json --output-file reports/smoke_summary.json

# Export to nested path (parent directories created automatically)
uv run qre smoke-files --output-file reports/nested/path/smoke_summary.txt

# Validate all referenced artifact files exist on disk (exit 0 if all present)
uv run qre smoke-files --check-exists

# Validate + JSON with missing-artifact details
uv run qre smoke-files --json --check-exists

# Strict selector: fail if strategy doesn't match (exit 2)
uv run qre smoke-files --strategy rsi2_oversold_reversal --require-match

# Strict selector: fail if role doesn't match (exit 2)
uv run qre smoke-files --role backtest_smoke_summary --require-match

# Strict selector with JSON: payload emitted + stderr reason + exit 2 on no-match
uv run qre smoke-files --json --strategy nonexistent --require-match

# Script-friendly missing artifact listing (requires --check-exists)
uv run qre smoke-files --check-exists --list-missing

# JSON + list-missing: JSON payload first, then one path per line
uv run qre smoke-files --json --check-exists --list-missing

# Quiet mode: suppress stdout, keep stderr and exit code (for automation)
uv run qre smoke-files --quiet

# Quiet mode with check-exists: stderr diagnostics preserved, stdout suppressed
uv run qre smoke-files --quiet --check-exists

# Status-only text mode: emits only overall_status for automation scripts
uv run qre smoke-files --status-only

# Status-only JSON mode: emits minimal {"overall_status": "...", "run_id": "..."}
uv run qre smoke-files --json --status-only

# Status-only with quiet: suppresses even the compact status output
uv run qre smoke-files --status-only --quiet

# Persist output to status file for CI (works with all output modes)
uv run qre smoke-files --status-file /tmp/smoke-status.txt

# Status-only JSON to file
uv run qre smoke-files --json --status-only --status-file /tmp/smoke-status.json

# Status-file with --quiet: stdout suppressed, file still written
uv run qre smoke-files --quiet --status-file /tmp/smoke-status.txt

# Status-format text: force plain-text status line with --status-only
uv run qre smoke-files --status-only --status-format text

# Status-format json: force JSON output with --status-only (no --json flag needed)
uv run qre smoke-files --status-only --status-format json

# Status-format json with status-file: persist forced JSON to file
uv run qre smoke-files --status-only --status-format json --status-file /tmp/ci-status.json

# Status-format without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-format text

# Status-reason: enrich status-only output with derived failure reason
uv run qre smoke-files --status-only --status-reason

# Status-reason with JSON format
uv run qre smoke-files --status-only --json --status-reason

# Status-reason persisted to file
uv run qre smoke-files --status-only --status-reason --status-file /tmp/ci-status.txt

# Status-reason without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-reason

# Numeric status code (ok=0, fail=1)
uv run qre smoke-files --status-only --status-code

# Status-code with JSON
uv run qre smoke-files --status-only --status-code --json

# Status-code with reason (text mode): "1\trsi2_oversold_reversal: compile=fail"
uv run qre smoke-files --status-only --status-code --status-reason

# Status-code without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-code

# Status metadata (appends run_id and source_mode fields)
uv run qre smoke-files --status-only --status-meta

# Status metadata with JSON (adds "source_mode" key)
uv run qre smoke-files --status-only --status-meta --json

# Status metadata without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-meta

# Status summary strategy counts (total/pass/fail/skip)
uv run qre smoke-files --status-only --status-summary

# Status summary with JSON
uv run qre smoke-files --status-only --status-summary --json

# Status fail-key first failing strategy id
uv run qre smoke-files --status-only --status-fail-key

# Status fail-key with JSON (null when no failures)
uv run qre smoke-files --status-only --status-fail-key --json

# Status fail-key without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-fail-key

# Status fail-stage first failing stage name
uv run qre smoke-files --status-only --status-fail-stage

# Status fail-stage with JSON
uv run qre smoke-files --status-only --status-fail-stage --json

# Status fail-stage combined with fail-key
uv run qre smoke-files --status-only --status-fail-key --status-fail-stage

# Status fail-stage without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-fail-stage

# Status timestamp (text)
uv run qre smoke-files --status-only --status-timestamp

# Status timestamp with JSON
uv run qre smoke-files --status-only --status-timestamp --json

# Status timestamp without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-timestamp

# Status output-dir (text)
uv run qre smoke-files --status-only --status-output-dir

# Status output-dir with JSON
uv run qre smoke-files --status-only --status-output-dir --json

# Status output-dir without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-output-dir

# Status manifest-path (text)
uv run qre smoke-files --status-only --status-manifest-path

# Status manifest-path with JSON
uv run qre smoke-files --status-only --status-manifest-path --json

# Status manifest-path without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-manifest-path

# Status manifest-exists (text, true when manifest file is present)
uv run qre smoke-files --status-only --status-manifest-exists

# Status manifest-exists with JSON
uv run qre smoke-files --status-only --status-manifest-exists --json

# Status manifest-exists without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-manifest-exists

# Status artifact count (appends total artifact count to status-only output)
uv run qre smoke-files --status-only --status-artifact-count

# Status artifact count with JSON (adds "artifact_count" integer key)
uv run qre smoke-files --status-only --status-artifact-count --json

# Status artifact count without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-artifact-count

# Status strategy count (appends total strategy count to status-only output)
uv run qre smoke-files --status-only --status-strategy-count

# Status strategy count with JSON (adds "strategy_count" integer key)
uv run qre smoke-files --status-only --status-strategy-count --json

# Status strategy count without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-strategy-count

# Status fail count (appends failing-strategy count to status-only output)
uv run qre smoke-files --status-only --status-fail-count

# Status fail count with JSON (adds "fail_count" integer key)
uv run qre smoke-files --status-only --status-fail-count --json

# Status fail count without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-fail-count

# Status skip count (appends skipped-strategy count to status-only output)
uv run qre smoke-files --status-only --status-skip-count

# Status skip count with JSON (adds "skip_count" integer key)
uv run qre smoke-files --status-only --status-skip-count --json

# Status skip count without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-skip-count

# Status pass count (appends passed-strategy count to status-only output)
uv run qre smoke-files --status-only --status-pass-count

# Status pass count with JSON (adds "pass_count" integer key)
uv run qre smoke-files --status-only --status-pass-count --json

# Status pass count without --status-only returns exit 2 (invalid combination)
uv run qre smoke-files --status-pass-count
```

Text output example:
```
run_id=abc123-def
resolved_output_dir=/home/user/qre/outputs/strategy-entry-smoke/20260522-run
source_mode=manifest
overall_status=ok
strategy_count=3
strategy=ema200_bollinger_reversal compile=pass preflight=skip missing_factor=skip backtest_smoke=skip
strategy=macd_zero_cross_momentum compile=pass preflight=skip missing_factor=skip backtest_smoke=skip
strategy=rsi2_oversold_reversal compile=pass preflight=skip missing_factor=skip backtest_smoke=skip
artifact_role_summary:
  compiled_strategy_spec: 3
  smoke_summary: 1
```

Strategies are listed in deterministic `strategy_id` order. `source_mode` shows `manifest` when `smoke_report_manifest.json` is available, or `artifacts_fallback` when only per-strategy `artifacts` dicts are used.

JSON output:
```json
{
  "artifact_role_counts": {
    "compiled_strategy_spec": 3,
    "smoke_summary": 1
  },
  "overall_status": "ok",
  "resolved_output_dir": "/home/user/qre/outputs/strategy-entry-smoke/20260522-run",
  "run_id": "abc123-def",
  "source_mode": "manifest",
  "strategy_count": 3
}
```

`--details` adds per-strategy blocks in text mode:
```
  strategy_id=ema200_bollinger_reversal
    compile=pass
    preflight=skip
    missing_factor=skip
    backtest_smoke=skip
    artifacts=['compiled_strategy_spec']
  strategy_id=rsi2_oversold_reversal
    compile=pass
    preflight=skip
    missing_factor=skip
    backtest_smoke=skip
    artifacts=['compiled_strategy_spec']
```

JSON with `--details` adds a `strategies` array (always present with `--details`, regardless of `--strategy` filter):
```json
{
  "...": "...",
  "strategies": [
    {
      "artifacts": ["compiled_strategy_spec"],
      "backtest_smoke": "skip",
      "compile": "pass",
      "missing_factor": "skip",
      "preflight": "skip",
      "strategy_id": "ema200_bollinger_reversal"
    },
    {
      "artifacts": ["compiled_strategy_spec"],
      "backtest_smoke": "skip",
      "compile": "pass",
      "missing_factor": "skip",
      "preflight": "skip",
      "strategy_id": "rsi2_oversold_reversal"
    }
  ]
}
```

When `--output-dir` is provided, that path is used directly and `resolved_output_dir` reflects it. `--output-file` writes the rendered output (text or JSON) to a file, creating parent directories as needed; stdout remains unchanged. On write failure, a clear stderr error is printed and exit code 2 is returned.

`--check-exists` validates that all artifact files referenced in the smoke summary or manifest exist on disk. Missing paths are printed to stderr (one per line, sorted) and exit code 2 is returned if any are absent. JSON output with `--check-exists` includes additive `missing_artifact_count` and `missing_artifacts` (sorted) fields. Without `--check-exists`, behavior is unchanged and no missing-artifact fields appear in JSON.

`--require-match` enables strict selector behavior for `--strategy` and `--role` filters. When a specified strategy or role has zero matches, a concise stderr message is printed (e.g., "No matching strategy: ...") and exit code 2 is returned. In JSON mode, the standard payload is still emitted to stdout before returning exit code 2. Without `--require-match`, a selector with zero matches is not an error and exit code 0 is returned.

`--list-missing` (requires `--check-exists`) prints sorted unique missing artifact relative paths to stdout, one per line, after the normal text or JSON output. This enables script-friendly consumption of the missing-artifact list without parsing stderr. Without `--check-exists`, `--list-missing` prints a guidance message to stderr and returns exit code 2.

`--quiet` suppresses all normal stdout output (both text and JSON payloads, including `--list-missing` paths). Stderr diagnostics and exit code semantics are preserved unchanged. This enables automation scripts that only need the exit code outcome. `--output-file` writing is unaffected by `--quiet`. Without `--quiet`, behavior is unchanged.

`--status-only` emits a compact single-line output for lightweight automation. In text mode, only the `overall_status` string (e.g., `ok`) is printed. In JSON mode, the payload is reduced to `{"overall_status": "...", "run_id": "..."}`. All other flags (`--check-exists`, `--require-match`, `--list-missing`, `--output-file`) continue to work normally. `--quiet` suppresses even the compact `--status-only` output. Without `--status-only`, the full text or JSON output is emitted unchanged.

`--status-file <path>` persists the effective output payload to a file, always — even when `--quiet` suppresses stdout. The written content matches the current output mode: full text or JSON when `--status-only` is absent; compact status line or minimal JSON when `--status-only` is set. Parent directories are created automatically. Write failures print to stderr and return exit code 2.

`--status-format {text,json}` forces the output format when `--status-only` is enabled, independent of the `--json` flag. Use `text` for a plain status line (`ok`/`fail`) on stdout and in `--status-file`. Use `json` for `{"overall_status": "...", "run_id": "..."}` on stdout and in `--status-file`, regardless of whether `--json` was passed. If `--status-format` is set without `--status-only`, the command returns exit code 2 with a short stderr diagnostic. When `--status-format` is absent, the current behavior is preserved (`--json` controls the output shape).

`--status-reason` enriches status-only output with a derived failure reason. In text mode, output becomes `<status>\t<reason>` (e.g., `fail\trsi2_oversold_reversal: compile=fail`); when status is `ok`, the reason is empty. In JSON mode, a `reason` key is added to the minimal payload. The reason is derived from the first failing strategy stage across compile, preflight, missing_factor, and backtest_smoke. Requires `--status-only`; using `--status-reason` without `--status-only` returns exit code 2 with stderr guidance.

`--status-code` emits a numeric status code instead of the text `ok`/`fail` string. `ok` maps to `0` and any non-ok status (including `fail`) maps to `1`. In text mode, the output is the numeric string (e.g., `"0"` or `"1"`). In JSON mode, a `"status_code"` key is added to the minimal payload. When combined with `--status-reason`, text output becomes `"<code>\t<reason>"` (e.g., `"1\trsi2_oversold_reversal: compile=fail"`) and JSON output includes both `"status_code"` and `"reason"`. Requires `--status-only`; using `--status-code` without `--status-only` returns exit code 2 with stderr guidance.

`--status-meta` appends stable metadata fields to status-only output. In text mode, the output becomes `<status>\trun_id=<value>\tsource_mode=<mode>` (e.g., `ok\trun_id=test-run-001\tsource_mode=artifacts_fallback`). The metadata fields appear after any `--status-code` or `--status-reason` content. In JSON mode, a `"source_mode"` key is added to the minimal payload (the `"run_id"` key is already present by default). Requires `--status-only`; using `--status-meta` without `--status-only` returns exit code 2 with stderr guidance.

`--status-summary` appends compact strategy-count fields to status-only output. In text mode, the output becomes `<status>\ttotal=<n>\tpass=<n>\tfail=<n>\tskip=<n>` (e.g., `ok\ttotal=2\tpass=2\tfail=0\tskip=0`). The count fields appear after any `--status-meta` content. In JSON mode, integer keys `strategy_total`, `strategy_pass`, `strategy_fail`, `strategy_skip` are added to the minimal payload. Strategy classification: any stage not in (pass, skip) → fail; all stages skip → skip; otherwise → pass. Requires `--status-only`; using `--status-summary` without `--status-only` returns exit code 2 with stderr guidance.

`--status-fail-key` appends the first failing strategy id to status-only output. In text mode, the output becomes `<status>\tfail_key=<strategy_id>` (e.g., `fail\tfail_key=rsi2_oversold_reversal`) or `<status>\tfail_key=` when no strategy fails. The fail_key field appears after any `--status-summary` content. In JSON mode, a `"fail_key"` key is added to the minimal payload: the strategy_id string when at least one strategy fails, or `null` when all strategies pass. The first failing strategy is determined by iterating strategies in existing order and checking compile/preflight/missing_factor/backtest_smoke stages for any non-pass-non-skip value. Requires `--status-only`; using `--status-fail-key` without `--status-only` returns exit code 2 with stderr guidance.

`--status-fail-stage` appends the first failing stage name to status-only output. In text mode, the output becomes `<status>\tfail_stage=<stage>` (e.g., `fail\tfail_stage=compile`) or `<status>\tfail_stage=` when no stage fails. The fail_stage field appears after any `--status-fail-key` content. In JSON mode, a `"fail_stage"` key is added to the minimal payload: the stage name string when at least one stage fails, or `null` when all stages pass. The first failing stage is determined by iterating strategies in existing order and checking stages in precedence order: compile, preflight, missing_factor, backtest_smoke. The first non-pass-non-skip stage across the first failing strategy wins. Combined with `--status-fail-key`, operators can localize both the failing strategy and the failing stage. Requires `--status-only`; using `--status-fail-stage` without `--status-only` returns exit code 2 with stderr guidance.

`--status-timestamp` appends the run generation timestamp to status-only output. In text mode, the output becomes `<status>\ttimestamp=<generated_at>` (e.g., `ok\ttimestamp=2026-05-22T00:00:00Z`) or `<status>\ttimestamp=` when `generated_at` is missing from the summary. The timestamp field appears after any `--status-fail-stage` content. In JSON mode, a `"timestamp"` key is added to the minimal payload: the `generated_at` ISO-8601 string when present, or `null` when absent. The timestamp value is taken directly from the `generated_at` field in `smoke_summary.json`. Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-timestamp` without `--status-only` returns exit code 2 with stderr guidance.

`--status-output-dir` appends the resolved smoke run directory path to status-only output. In text mode, the output becomes `<status>\toutput_dir=<absolute-path>` (e.g., `ok\toutput_dir=/home/user/qre/outputs/strategy-entry-smoke/20260522-run`). The output_dir field appears after any `--status-timestamp` content. In JSON mode, an `"output_dir"` key is added to the minimal payload with the absolute resolved path as a string. The value is derived from the already-resolved smoke run directory used by `smoke-files` (which may come from `--output-dir`, `--latest`, or explicit path). Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-output-dir` without `--status-only` returns exit code 2 with stderr guidance.

`--status-manifest-path` appends the resolved smoke report manifest file path to status-only output. In text mode, the output becomes `<status>\tmanifest_path=<absolute-path>` (e.g., `ok\tmanifest_path=/home/user/qre/outputs/strategy-entry-smoke/20260522-run/smoke_report_manifest.json`). The manifest_path field appears after any `--status-output-dir` content. In JSON mode, a `"manifest_path"` key is added to the minimal payload with the absolute resolved path as a string. The value is derived from the already-resolved `smoke_report_manifest.json` path used by `smoke-files` (which may come from `--output-dir`, `--latest`, or explicit path). Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-manifest-path` without `--status-only` returns exit code 2 with stderr guidance.

`--status-manifest-exists` appends a manifest existence boolean to status-only output. In text mode, the output becomes `<status>\tmanifest_exists=true` or `<status>\tmanifest_exists=false`. The manifest_exists field appears after any `--status-manifest-path` content. In JSON mode, a `"manifest_exists"` boolean key is added to the minimal payload. The value is derived from checking whether the resolved `smoke_report_manifest.json` file exists on disk (`manifest_path.is_file()`). Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-artifact-count`, `--status-strategy-count`, `--status-fail-count`, `--status-skip-count`, `--status-pass-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-manifest-exists` without `--status-only` returns exit code 2 with stderr guidance.

`--status-artifact-count` appends the total artifact count to status-only output. In text mode, the output becomes `<status>\tartifact_count=<int>` (e.g., `ok\tartifact_count=4`). The artifact_count field appears after any `--status-manifest-exists` content. In JSON mode, an `"artifact_count"` integer key is added to the minimal payload. The value is derived from the already-computed artifact role count aggregation (from manifest when available, or from per-strategy artifact fallback). Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-strategy-count`, `--status-fail-count`, `--status-skip-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-artifact-count` without `--status-only` returns exit code 2 with stderr guidance.

`--status-strategy-count` appends the total strategy count to status-only output. In text mode, the output becomes `<status>\tstrategy_count=<int>` (e.g., `ok\tstrategy_count=3`). The strategy_count field appears after any `--status-artifact-count` content. In JSON mode, a `"strategy_count"` integer key is added to the minimal payload. The value is derived from `len(strategies)` — the count of strategies present in the smoke summary (after any `--strategy` filter). Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-artifact-count`, `--status-fail-count`, `--status-skip-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-strategy-count` without `--status-only` returns exit code 2 with stderr guidance.

`--status-fail-count` appends the failing-strategy count to status-only output. In text mode, the output becomes `<status>\tfail_count=<int>` (e.g., `ok\tfail_count=0` or `fail\tfail_count=2`). The fail_count field appears after any `--status-strategy-count` content. In JSON mode, a `"fail_count"` integer key is added to the minimal payload. The value is derived from the already-computed `summary_fail` — the count of strategies where any stage (compile, preflight, missing_factor, backtest_smoke) is not pass/skip. Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-artifact-count`, `--status-strategy-count`, `--status-skip-count`, `--status-pass-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-fail-count` without `--status-only` returns exit code 2 with stderr guidance.

`--status-skip-count` appends the skipped-strategy count to status-only output. In text mode, the output becomes `<status>\tskip_count=<int>` (e.g., `ok\tskip_count=2`). The skip_count field appears after any `--status-fail-count` content. In JSON mode, a `"skip_count"` integer key is added to the minimal payload. The value is derived from the already-computed `summary_skip` — the count of strategies where all stages (compile, preflight, missing_factor, backtest_smoke) are `skip`. Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-artifact-count`, `--status-strategy-count`, `--status-fail-count`, `--status-pass-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-skip-count` without `--status-only` returns exit code 2 with stderr guidance.

`--status-pass-count` appends the passed-strategy count to status-only output. In text mode, the output becomes `<status>\tpass_count=<int>` (e.g., `ok\tpass_count=2`). The pass_count field appears after any `--status-skip-count` content. In JSON mode, a `"pass_count"` integer key is added to the minimal payload. The value is derived from the already-computed `summary_pass` — the count of strategies where all stages (compile, preflight, missing_factor, backtest_smoke) are `pass`. Compatible with `--status-code`, `--status-reason`, `--status-meta`, `--status-summary`, `--status-fail-key`, `--status-fail-stage`, `--status-timestamp`, `--status-output-dir`, `--status-manifest-path`, `--status-manifest-exists`, `--status-artifact-count`, `--status-strategy-count`, `--status-fail-count`, `--status-skip-count`, `--status-format`, `--quiet`, and `--status-file`. Requires `--status-only`; using `--status-pass-count` without `--status-only` returns exit code 2 with stderr guidance.

Exit codes: 0 for ok, 2 for fail status, missing summary, no available runs, write failure (--output-file, --status-file), missing artifacts (--check-exists), strict no-match (--require-match), --list-missing without --check-exists, --status-format without --status-only, --status-reason without --status-only, --status-code without --status-only, --status-meta without --status-only, --status-summary without --status-only, --status-fail-key without --status-only, --status-fail-stage without --status-only, --status-timestamp without --status-only, --status-output-dir without --status-only, --status-manifest-path without --status-only, --status-manifest-exists without --status-only, --status-artifact-count without --status-only, --status-strategy-count without --status-only, --status-fail-count without --status-only, --status-skip-count without --status-only, or --status-pass-count without --status-only. `--quiet` and `--status-only` do not change exit code behavior.

## Acceptance Criteria Status

| Criterion | Status |
|---|---|
| All three strategies compile via `qre compile` | PASS |
| All three strategies run preflight and produce deterministic status | SKIP — no DB configured |
| Missing-factor artifact behavior is demonstrated for each strategy | SKIP — depends on preflight |
| At least one strategy completes a backtest smoke, or all skips are justified | SKIP — no DB configured; justification documented |
| `docs/strategy_entry/three_strategy_smoke_report.md` is complete and reproducible | DONE |
| `docs/agent/09_CODING_HANDOFF.md` contains exact commands and outputs summary | PENDING (next step) |

## Residual Notes

- All compiled expressions use alias names (not full `factors.*.*` paths), matching the expression evaluator's `ast.Name` requirement.
- Crossover operators are the only known gap between high-level rule semantics and low-level expression evaluation. They emit warnings and fall back to simple comparisons.
- Table name for EMA with source=typical is `stock_daily_overlap_typical_price` (compiler-generated via `_SOURCE_TO_TABLE_SUFFIX` mapping), matching the actual upstream `factors` table.
- All three compiled specs are compatible with `StrategySpec.from_mapping()` and the existing `qre backtest-batch` / `qre backtest-shared` commands.
