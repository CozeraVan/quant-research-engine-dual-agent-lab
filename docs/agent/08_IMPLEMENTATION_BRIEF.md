# Implementation Brief

## Task ID

QRE-CONTINUOUS-REFRESH-001 (M10.3, CR-0003 F2)

## Created By

KIMI_CODE (single agent; roadmap order user-approved "请继续按计划推进" 2026-07-19)

## Intended Implementer

KIMI_CODE

## Goal

Keep strategy results current as upstream data lands: detect new data via a database watermark, idempotently re-run the catalog on a rolling window using the vectorized runner, and emit a delta report against the previous batch. The machinery is built and small-sample verified only — **no full-scale execution** (standing user instruction 2026-07-19); the scheduler ships as documented unit files, not installed.

## Background Evidence

- Vectorized engine + shared frame make full catalog re-runs cheap (~30 min for 106 strategies), so idempotent full re-run beats stateful incremental (decision log 2026-07-19).
- Runner already supports `--jobs`, `--compact`, `--resume`, `--engine-impl`.
- `quant_ts` uses systemd timers upstream; we mirror the pattern with user-level units.

## Scope

1. **`orchestration/refresh.py`**:
   - `data_watermark(store)`: read-only `SELECT MAX(trade_date)` on the market daily table.
   - `RefreshState` (JSON at `outputs/refresh/state.json`): `last_data_date`, `last_run_at`, `last_batch_dir`, `window_years`, `codes`, `strategy_count`, `ok_count`, `config` (jobs/compact/engine_impl/apply_stops).
   - `needs_refresh(data_date, state)`: true when no state or `data_date > state.last_data_date`.
   - `compute_window(data_date, window_years)`: end = data_date; start = data_date minus window_years (calendar).
   - `compute_delta(previous_batch_dir, new_batch_dir)`: per-strategy comparison from `batch_summary.json` results (status changes) and per-strategy `backtest/summary_metrics.json` (mean_total_return, total_trades, positive_return_symbol_rate) → delta rows incl. new/removed/error transitions.
   - `write_delta_report(...)`: `delta_report.json` + `delta_report.md` + `report_manifest.json` (kind `strategy_refresh_delta_manifest` registered for report-audit).
2. **`scripts/refresh_batch.py`**: `--check-only` (report watermark vs state, do nothing), `--force`, `--window-years` (default 2), `--jobs` (default 4), `--codes` (small-sample/testing), `--with-eval` (default skip eval for speed), `--apply-stops` passthrough. Flow: load state → watermark → skip when current (unless forced) → run catalog batch via `orchestration.batch_runner` core → delta report vs `state.last_batch_dir` → save state.
3. **Scheduler units** `deploy/qre-refresh.service` + `deploy/qre-refresh.timer` (systemd user units, daily 18:30): documented in README with install commands; NOT installed by the agent.
4. **Tests** `tests/test_refresh.py`: watermark/needs_refresh/window logic, state roundtrip, delta computation (metric changes, new/removed/error transitions), end-to-end with monkeypatched batch execution and fake store (state written, delta report emitted, second run no-ops), manifest audit parity.

## Non-Goals

- No full-scale execution during this slice (small-sample `--codes` verification only).
- No systemd installation/enabling by the agent (user enables when ready).
- No stateful incremental backtesting (idempotent re-run by design).
- No GUI work.

## Expected Tests

```bash
uv run pytest tests/test_refresh.py -q
uv run pytest -q
```

## Validation Commands

```bash
uv run pytest -q
scripts/check-progress-docs.sh
git diff --check
# Small-sample (R-QRE-009): refresh_batch.py --codes 000001.SZ 000002.SZ 600000.SH --force
# then --check-only (no-op path), then delta report inspection + report-audit
```

## Acceptance Criteria

- `--check-only` correctly reports current/stale watermark without running anything.
- Forced small-sample refresh runs the batch, writes state, and emits a delta report that passes `qre report-audit`.
- A second run with no new data no-ops; with a bumped watermark it refreshes and the delta report shows per-strategy changes.
- Full pytest suite green; systemd unit files documented but not installed.
