from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import refresh_batch  # noqa: E402


# --- should_full_rebuild（阈值回退全窗） ---


def _write_checkpoint(state_dir: Path, last: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "state.json").write_text(
        json.dumps({"last_processed_date": last}), encoding="utf-8"
    )


def test_should_full_rebuild_threshold(tmp_path):
    state_dir = tmp_path / "s1"
    _write_checkpoint(state_dir, "2026-07-20")
    # 差 8 天 ≤ 45 → 增量
    assert refresh_batch.should_full_rebuild(state_dir, date(2026, 7, 28), 45) is False
    # 差 46 天 > 45 → 全窗
    _write_checkpoint(state_dir, "2026-06-12")
    assert refresh_batch.should_full_rebuild(state_dir, date(2026, 7, 28), 45) is True


def test_should_full_rebuild_no_checkpoint(tmp_path):
    # 无 checkpoint（新策略首次）→ False（自然 bootstrap，不需要删目录）
    assert refresh_batch.should_full_rebuild(tmp_path / "ghost", date(2026, 7, 28), 45) is False


def test_should_full_rebuild_corrupt_checkpoint(tmp_path):
    state_dir = tmp_path / "s1"
    state_dir.mkdir()
    (state_dir / "state.json").write_text("not json", encoding="utf-8")
    assert refresh_batch.should_full_rebuild(state_dir, date(2026, 7, 28), 45) is True


# --- write_incremental_summary_metrics（聚合重算产物） ---


def test_write_incremental_summary_metrics(tmp_path):
    pd.DataFrame(
        [
            {"symbol": "a", "total_return": 0.10, "trade_count": 3},
            {"symbol": "b", "total_return": -0.05, "trade_count": 0},
            {"symbol": "c", "total_return": 0.20, "trade_count": 2},
        ]
    ).to_csv(tmp_path / "summary.csv", index=False)
    metrics = refresh_batch.write_incremental_summary_metrics(tmp_path)
    assert metrics["symbol_count"] == 3
    assert metrics["traded_symbol_count"] == 2
    assert metrics["total_trades"] == 5
    assert metrics["mean_total_return"] == pytest.approx((0.10 - 0.05 + 0.20) / 3)
    assert metrics["positive_return_symbol_rate"] == pytest.approx(2 / 3)
    written = json.loads((tmp_path / "backtest" / "summary_metrics.json").read_text(encoding="utf-8"))
    assert written == metrics


def test_write_incremental_summary_metrics_missing(tmp_path):
    assert refresh_batch.write_incremental_summary_metrics(tmp_path) is None


# --- run_incremental_refresh 编排（mock 引擎） ---


def test_run_incremental_refresh_orchestration(monkeypatch, tmp_path):
    calls = []

    class _Result:
        updated = True
        new_rows = {"orders": 2, "trades": 1, "failed_orders": 0, "equity_curve": 5}
        watermark = date(2026, 7, 28)
        duration_s = 0.1

    def fake_run(store, spec, request):
        calls.append(request)
        # 模拟引擎写 summary.csv（供 metrics 写出）；引擎会自建 state_dir
        sid = request.strategy_path.stem
        state_dir = request.output_root / sid
        state_dir.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"symbol": "a", "total_return": 0.01, "trade_count": 1}]).to_csv(
            (state_dir / "summary.csv"), index=False
        )
        return _Result()

    monkeypatch.setattr(
        "quant_research_engine.orchestration.incremental.run_incremental", fake_run
    )

    # 一个正常策略（小差）+ 一个大差策略（回退全窗，目录被删重建）+ 一个失败策略
    inc_root = tmp_path / "inc"
    _write_checkpoint(inc_root / "ok_s", "2026-07-25")
    stale = inc_root / "stale_s"
    _write_checkpoint(stale, "2026-01-01")
    (stale / "orders.csv").write_text("old", encoding="utf-8")

    yaml_paths = []
    for sid in ("ok_s", "stale_s", "boom_s"):
        p = tmp_path / f"{sid}.yaml"
        p.write_text(
            "experiment:\n  name: x\ndata:\n  factor_fields:\n    f: factors.t.c\n"
            "signal:\n  entry: x < 0\nevaluation:\n  forward_return_horizons: [1]\n"
            "holding:\n  max_holding_days: 1\n",
            encoding="utf-8",
        )
        yaml_paths.append(p)

    real_run = fake_run

    def run_or_boom(store, spec, request):
        if request.strategy_path.stem == "boom_s":
            raise RuntimeError("引擎炸了")
        return real_run(store, spec, request)

    monkeypatch.setattr(
        "quant_research_engine.orchestration.incremental.run_incremental", run_or_boom
    )

    results, per_strategy = refresh_batch.run_incremental_refresh(
        yaml_paths,
        store=None,
        start=date(2024, 7, 28),
        end=date(2026, 7, 28),
        data_date=date(2026, 7, 28),
        incremental_root=inc_root,
        threshold_days=45,
        codes=["000001.SZ"],
    )
    assert [r["status"] for r in results] == ["ok", "ok", "error"]
    by_id = {e["strategy_id"]: e for e in per_strategy}
    assert "rebuilt" not in by_id["ok_s"]  # 小差不重建
    assert by_id["stale_s"]["rebuilt"] is True  # 大差回退全窗
    assert not (stale / "orders.csv").exists()  # 旧目录已删
    assert "引擎炸了" in by_id["boom_s"]["error"]
    # 每个 ok 策略都写了 summary_metrics.json
    for sid in ("ok_s", "stale_s"):
        assert (inc_root / sid / "backtest" / "summary_metrics.json").exists()
    # IncrementalRequest 参数透传
    req = calls[0]
    assert req.start == date(2024, 7, 28)
    assert req.codes == ["000001.SZ"]


# --- 合并语义复用断言（7 月引擎的既有能力，此处验证我们的调用契约） ---


def test_merge_dedup_and_recompute_contract(tmp_path):
    """台账 concat + 键去重 + 汇总重算：验证我们依赖的 7 月引擎语义仍成立。"""
    from quant_research_engine.orchestration.incremental import (
        _append_equity_ledger,
        _recompute_summary,
        _update_row_ledger,
    )

    state_dir = tmp_path / "s"
    state_dir.mkdir()
    # 两批 equity：同一 (symbol, trade_date) 重复 → 汇总去重
    eq1 = pd.DataFrame(
        {"symbol": ["a"], "trade_date": pd.to_datetime(["2026-07-25"]), "total_equity": [100.0]}
    )
    eq2 = pd.DataFrame(
        {"symbol": ["a", "a"], "trade_date": pd.to_datetime(["2026-07-25", "2026-07-26"]),
         "total_equity": [101.0, 102.0]}
    )
    _append_equity_ledger(state_dir / "equity_curve.csv", eq1)
    _append_equity_ledger(state_dir / "equity_curve.csv", eq2)
    # trades 合并去重
    t1 = pd.DataFrame({
        "symbol": ["a"], "entry_date": pd.to_datetime(["2026-07-20"]),
        "exit_date": pd.to_datetime(["2026-07-22"]), "net_pnl": [1.0], "cost": [0.1],
    })
    t2 = pd.DataFrame({
        "symbol": ["a"], "entry_date": pd.to_datetime(["2026-07-20"]),
        "exit_date": pd.to_datetime(["2026-07-22"]), "net_pnl": [1.0], "cost": [0.1],
    })
    _update_row_ledger(
        state_dir / "trades.csv", t1,
        subset=["symbol", "entry_date", "exit_date"], sort_cols=["symbol", "entry_date"],
        parse_dates=["entry_date", "exit_date"],
    )
    _update_row_ledger(
        state_dir / "trades.csv", t2,
        subset=["symbol", "entry_date", "exit_date"], sort_cols=["symbol", "entry_date"],
        parse_dates=["entry_date", "exit_date"],
    )
    summary = _recompute_summary(state_dir, initial_cash=100.0, symbols=["a"])
    row = summary.iloc[0]
    assert row["final_equity"] == pytest.approx(102.0)  # 去重后取最后
    assert row["trade_count"] == 1  # 重复成交合并
    assert row["win_rate"] == pytest.approx(1.0)
