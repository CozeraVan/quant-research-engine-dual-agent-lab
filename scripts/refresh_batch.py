#!/usr/bin/env python3
"""Continuous strategy refresh: detect new data and re-run the catalog.

Usage:
  uv run python scripts/refresh_batch.py --check-only          # watermark vs state, no run
  uv run python scripts/refresh_batch.py                       # incremental merge (default)
  uv run python scripts/refresh_batch.py --full-window         # full rolling-window re-run (legacy)
  uv run python scripts/refresh_batch.py --force               # refresh regardless
  uv run python scripts/refresh_batch.py --codes 000001.SZ 600000.SH   # small-sample

Modes (QRE-REFRESH-INCREMENTAL-001):
  incremental (default): only new trading days are computed and merged into the
    per-strategy store at outputs/refresh/incremental/<strategy_id>/ (7月增量引擎:
    checkpoint 持仓延续 + 台账去重 + 聚合重算); large watermark gaps (>45 自然日)
    or config changes automatically fall back to a full bootstrap.
  full: legacy rolling-window full re-run into outputs/backtests/refresh/<batch>/.

State lives at outputs/refresh/state.json; batches at outputs/backtests/refresh/<id>/;
incremental store at outputs/refresh/incremental/; delta reports at outputs/refresh/delta/<timestamp>/.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from quant_research_engine.orchestration.batch_runner import (
    BatchRunConfig,
    BatchSummary,
    discover_strategies,
    execute_batch,
    new_batch_id,
    summarize_results,
    utc_now_iso,
    write_batch_summary,
)
from quant_research_engine.orchestration.refresh import (
    compute_delta,
    compute_window,
    data_watermark,
    load_state,
    needs_refresh,
    save_state,
    write_delta_report,
    RefreshState,
)

CATALOG_DIR = ROOT / "strategies" / "catalog"
DEFAULT_BATCH_ROOT = ROOT / "outputs" / "backtests" / "refresh"
DEFAULT_STATE_FILE = ROOT / "outputs" / "refresh" / "state.json"
DEFAULT_DELTA_ROOT = ROOT / "outputs" / "refresh" / "delta"
DEFAULT_REGISTRY_FILE = ROOT / "outputs" / "refresh" / "registry.json"


def load_registry_ids(registry_path: Path) -> dict[str, Any]:
    """Load the refresh strategy registry.

    v2 格式 {"include": [...], "stopped": [...]}；兼容旧格式纯数组或
    {"strategies": [...]}（视为 include，stopped=[]）。
    返回 {"ids": [...] | None, "stopped": set}：
    ids=None 表示 include 为空（调用方全量扫描，再排除 stopped）。
    """
    import json

    result: dict[str, Any] = {"ids": None, "stopped": set()}
    if not registry_path.exists():
        return result
    try:
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return result
    include: list[str] = []
    stopped: list[str] = []
    if isinstance(payload, list):
        include = payload
    elif isinstance(payload, dict):
        if isinstance(payload.get("include"), list):
            include = payload["include"]
        elif isinstance(payload.get("strategies"), list):
            include = payload["strategies"]
        if isinstance(payload.get("stopped"), list):
            stopped = payload["stopped"]
    ids = sorted({str(sid) for sid in include})
    result["stopped"] = {str(s) for s in stopped}
    result["ids"] = ids or None
    return result


# ---------------------------------------------------------------------------
# incremental mode（QRE-REFRESH-INCREMENTAL-001）
# ---------------------------------------------------------------------------

DEFAULT_INCREMENTAL_ROOT = ROOT / "outputs" / "refresh" / "incremental"


def should_full_rebuild(state_dir: Path, data_date: date, threshold_days: int) -> bool:
    """水印差超过阈值（自然日）→ 回退全窗 bootstrap；无 checkpoint → False（自然 bootstrap）。"""
    checkpoint_path = state_dir / "state.json"
    if not checkpoint_path.exists():
        return False
    import json as _json

    try:
        payload = _json.loads(checkpoint_path.read_text(encoding="utf-8"))
        last = date.fromisoformat(str(payload["last_processed_date"]))
    except (KeyError, ValueError, OSError, _json.JSONDecodeError):
        return True  # 损坏的 checkpoint：重建
    return (data_date - last).days > threshold_days


def write_incremental_summary_metrics(state_dir: Path) -> dict[str, Any] | None:
    """由合并后 summary.csv 写 backtest/summary_metrics.json（供 delta 报告复用）。"""
    import json as _json

    import pandas as pd

    summary_path = state_dir / "summary.csv"
    if not summary_path.exists():
        return None
    summary = pd.read_csv(summary_path)
    returns = summary["total_return"].dropna() if "total_return" in summary else pd.Series(dtype=float)
    metrics = {
        "symbol_count": int(len(summary)),
        "traded_symbol_count": int((summary.get("trade_count", pd.Series(dtype=float)).fillna(0) > 0).sum()),
        "mean_total_return": None if returns.empty else float(returns.mean()),
        "total_trades": int(summary.get("trade_count", pd.Series(dtype=float)).fillna(0).sum()),
        "positive_return_symbol_rate": None if returns.empty else float((returns > 0).mean()),
    }
    out_dir = state_dir / "backtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary_metrics.json").write_text(
        _json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return metrics


def run_incremental_refresh(
    yaml_paths: list[Path],
    *,
    store,
    start: date,
    end: date,
    data_date: date,
    incremental_root: Path,
    threshold_days: int = 45,
    apply_stops: bool = False,
    universe_filter: bool = False,
    codes: list[str] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """逐策略增量补跑并合并（复用 7 月增量引擎）。

    返回 (results, per_strategy)：results 形如 batch runner 的结果行（供汇总），
    per_strategy 供 last_run.json。
    """
    import shutil
    import traceback

    from quant_research_engine.orchestration.incremental import (
        IncrementalRequest,
        run_incremental,
    )
    from quant_research_engine.strategies.spec import StrategySpec

    incremental_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    per_strategy: list[dict[str, Any]] = []

    for yaml_path in yaml_paths:
        sid = yaml_path.stem
        state_dir = incremental_root / sid
        entry: dict[str, Any] = {"strategy_id": sid, "category": yaml_path.parent.name}
        try:
            if should_full_rebuild(state_dir, data_date, threshold_days):
                shutil.rmtree(state_dir)
                entry["rebuilt"] = True
            spec = StrategySpec.from_yaml(yaml_path)
            result = run_incremental(
                store,
                spec,
                IncrementalRequest(
                    strategy_path=yaml_path,
                    start=start,
                    end=end,
                    output_root=incremental_root,
                    apply_stops=apply_stops,
                    universe_filter=universe_filter,
                    codes=codes,
                ),
            )
            write_incremental_summary_metrics(state_dir)
            entry.update(
                {
                    "status": "ok",
                    "output_dir": str(state_dir),
                    "updated": result.updated,
                    "new_rows": result.new_rows,
                    "watermark": str(result.watermark) if result.watermark else None,
                    "duration_s": round(result.duration_s, 2),
                }
            )
        except Exception as exc:  # 单策略失败不阻塞整体（与 batch runner 一致）
            entry.update({"status": "error", "error": f"{exc}", "traceback": traceback.format_exc()[-2000:]})
        results.append({"strategy_id": sid, "category": entry["category"],
                        "status": entry["status"], "output_dir": entry.get("output_dir", "")})
        per_strategy.append(entry)
    return results, per_strategy


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuous strategy refresh (watermark detection + idempotent re-run + delta report)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--check-only", action="store_true", help="Report watermark vs state; do not run")
    parser.add_argument("--force", action="store_true", help="Refresh even when the watermark is unchanged")
    parser.add_argument("--window-years", type=int, default=2, help="Rolling window length in years (default: 2)")
    parser.add_argument("--jobs", type=int, default=4, help="Parallel workers (default: 4)")
    parser.add_argument("--codes", nargs="*", help="Limit symbols (small-sample/testing)")
    parser.add_argument("--with-eval", action="store_true", help="Also run the eval stage (slower)")
    parser.add_argument("--apply-stops", action="store_true", help="Honor spec stop_loss/take_profit")
    parser.add_argument("--universe-filter", action="store_true", help="Apply spec universe rules")
    parser.add_argument("--category", help="Limit to one catalog category")
    parser.add_argument("--strategies", nargs="*", help="Limit to specific strategy IDs")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_FILE,
                        help="Strategy registry file (default: outputs/refresh/registry.json); "
                             "when present and non-empty, limits the run to registered IDs "
                             "(--strategies takes precedence)")
    parser.add_argument("--state-file", type=Path, default=DEFAULT_STATE_FILE)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_BATCH_ROOT)
    parser.add_argument("--mode", choices=["incremental", "full"], default="incremental",
                        help="incremental（默认）只跑新增交易日并合并进既有结果；full 全窗重跑")
    parser.add_argument("--full-window", action="store_true",
                        help="等同于 --mode full（保留旧行为的便捷开关）")
    parser.add_argument("--incremental-threshold-days", type=int, default=45,
                        help="水印差超过该自然日数（≈30 交易日）时回退全窗 bootstrap（默认 45）")
    args = parser.parse_args()

    mode = "full" if args.full_window else args.mode

    from quant_research_engine.data.postgres import PostgresDataStore
    from quant_research_engine.data.settings import DatabaseSettings

    store = PostgresDataStore(DatabaseSettings.from_env())
    data_date = data_watermark(store)
    close = getattr(store, "close", None)
    if data_date is None:
        print("ERROR: no data watermark (empty market table?)", file=sys.stderr)
        return 1

    state = load_state(args.state_file)
    print(f"data watermark: {data_date}")
    print(f"state: {state.last_data_date if state else '(none — first run)'}")

    if args.check_only:
        refresh_needed = needs_refresh(data_date, state)
        print(f"refresh needed: {refresh_needed}")
        return 0

    if not args.force and not needs_refresh(data_date, state):
        print("No new data since last refresh — nothing to do.")
        return 0

    start, end = compute_window(data_date, args.window_years)
    registry = load_registry_ids(args.registry)
    registry_ids = registry["ids"]
    registry_stopped = registry["stopped"]
    strategy_filter = args.strategies if args.strategies else registry_ids
    if strategy_filter and not args.strategies:
        print(f"registry: {len(strategy_filter)} registered strategies ({args.registry})")
    yaml_paths = discover_strategies(CATALOG_DIR, args.category, strategy_filter)
    if registry_stopped and not args.strategies:
        before = len(yaml_paths)
        yaml_paths = [p for p in yaml_paths if p.stem not in registry_stopped]
        if before != len(yaml_paths):
            print(f"registry: skipped {before - len(yaml_paths)} stopped strategies")
    batch_id = new_batch_id()

    if mode == "incremental":
        print(f"mode: incremental（合并进 outputs/refresh/incremental/；--full-window 回退全窗）")
        results, per_strategy = run_incremental_refresh(
            yaml_paths,
            store=store,
            start=start,
            end=end,
            data_date=data_date,
            incremental_root=DEFAULT_INCREMENTAL_ROOT,
            threshold_days=args.incremental_threshold_days,
            apply_stops=args.apply_stops,
            universe_filter=args.universe_filter,
            codes=args.codes,
        )
        ok = sum(1 for r in results if r["status"] == "ok")
        last_run_path = DEFAULT_INCREMENTAL_ROOT / "last_run.json"
        last_run_path.write_text(
            json.dumps(
                {
                    "batch_id": batch_id,
                    "generated_at": utc_now_iso(),
                    "data_date": str(data_date),
                    "window": {"start": str(start), "end": str(end)},
                    "strategies": per_strategy,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        save_state(
            args.state_file,
            RefreshState(
                last_data_date=str(data_date),
                last_run_at=utc_now_iso(),
                last_batch_dir=str(DEFAULT_INCREMENTAL_ROOT),
                window_years=args.window_years,
                codes=args.codes,
                strategy_count=len(results),
                ok_count=ok,
                config={
                    "mode": "incremental",
                    "incremental_root": str(DEFAULT_INCREMENTAL_ROOT),
                    "threshold_days": args.incremental_threshold_days,
                    "apply_stops": args.apply_stops,
                    "universe_filter": args.universe_filter,
                    "registry": str(args.registry) if registry_ids else None,
                },
            ),
        )
        print(f"\nIncremental refresh complete: {ok} ok / {len(results)} total")
        print(f"  last_run: {last_run_path}")
        print(f"  state: {args.state_file}")
        if callable(close):
            close()
        return 0 if ok == len(results) else 1

    output_base = args.output_root / batch_id

    print(f"window: {start} → {end} ({args.window_years}y)")
    print(f"strategies: {len(yaml_paths)}; jobs: {args.jobs}; output: {output_base}")

    config = BatchRunConfig(
        output_base=output_base,
        start=start,
        end=end,
        skip_preflight=True,
        skip_eval=not args.with_eval,
        compact=True,
        catalog_dir=CATALOG_DIR,
        engine_impl="vectorized",
        codes=args.codes,
        apply_stops=args.apply_stops,
        universe_filter=args.universe_filter,
    )

    results = execute_batch(yaml_paths, config, jobs=max(1, args.jobs))
    counts = summarize_results(results)
    summary = BatchSummary(
        batch_id=batch_id,
        generated_at=utc_now_iso(),
        mode="refresh",
        date_range={"start": str(start), "end": str(end)},
        config={
            "engine_impl": "vectorized",
            "compact": True,
            "jobs": max(1, args.jobs),
            "with_eval": args.with_eval,
            "apply_stops": args.apply_stops,
            "universe_filter": args.universe_filter,
            "window_years": args.window_years,
            "registry": str(args.registry) if registry_ids else None,
        },
        results=results,
        summary=counts,
    )
    summary_path = write_batch_summary(summary, output_base)

    previous_batch_dir = Path(state.last_batch_dir) if state and state.last_batch_dir else None
    delta_rows = compute_delta(previous_batch_dir, output_base)
    delta_dir = DEFAULT_DELTA_ROOT / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{batch_id}"
    delta_paths = write_delta_report(
        delta_dir,
        data_date=data_date,
        window=(start, end),
        previous_batch_dir=previous_batch_dir,
        new_batch_dir=output_base,
        delta_rows=delta_rows,
    )

    save_state(
        args.state_file,
        RefreshState(
            last_data_date=str(data_date),
            last_run_at=utc_now_iso(),
            last_batch_dir=str(output_base),
            window_years=args.window_years,
            codes=args.codes,
            strategy_count=len(results),
            ok_count=counts["ok"],
            config=summary.config,
        ),
    )

    print(f"\nRefresh complete: {counts['ok']} ok / {counts['total']} total")
    print(f"  batch: {summary_path}")
    print(f"  delta: {delta_paths['delta_report_md']}")
    print(f"  state: {args.state_file}")
    if callable(close):
        close()
    return 0 if counts["total"] - counts["ok"] - counts["skipped"] - counts.get("missing_factors", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
