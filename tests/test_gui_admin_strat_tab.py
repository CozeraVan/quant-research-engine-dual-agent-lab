from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui import admin as _admin
from quant_research_engine.gui.refresh_registry import (
    latest_strategy_result,
    list_result_artifacts,
    load_registry,
    refresh_overview,
    save_registry,
    set_strategy_stopped,
)
from quant_research_engine.gui.strategy_admin import delete_strategy, strategy_catalog_info


@pytest.fixture(autouse=True)
def _clear_cache():
    _admin._cache.clear()
    yield
    _admin._cache.clear()


# --- per-strategy 最新结果提取 ---


def _write_result(root: Path, batch: str, sid: str, metrics: dict, mtime_offset: int = 0) -> Path:
    path = root / batch / sid / "backtest" / "strategy_performance.json"
    path.parent.mkdir(parents=True)
    payload = {
        "strategy_name": sid,
        "date_start": "2024-07-01",
        "date_end": "2026-07-27",
        "symbol_count": 5547,
        "traded_symbol_count": 3200,
        "excess_return_vs_buy_hold": -0.0234,
        "max_drawdown": -0.35,
        "strategy_total_return": 0.05,
        "buy_hold_return": 0.08,
        "win_rate": 0.45,
        "profit_factor": 1.2,
        "total_trade_count": 500,
        **metrics,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_latest_strategy_result_picks_newest(tmp_path):
    old = _write_result(tmp_path, "batch_old", "s1", {"max_drawdown": -0.5})
    new = _write_result(tmp_path / "refresh", "b2", "s1", {"max_drawdown": -0.35})
    # 手动控制 mtime：new 更新
    import os
    import time

    past = time.time() - 1000
    os.utime(old, (past, past))
    result = latest_strategy_result("s1", tmp_path)
    assert result is not None
    assert result["source_file"] == str(new)
    m = result["metrics"]
    assert m["date_start"] == "2024-07-01"
    assert m["traded_symbol_count"] == 3200
    assert m["symbol_count"] == 5547
    assert m["excess_return_vs_buy_hold"] == pytest.approx(-0.0234)
    assert m["max_drawdown"] == pytest.approx(-0.35)
    # 缓存命中
    assert latest_strategy_result("s1", tmp_path)["source_file"] == str(new)


def test_latest_strategy_result_benchmark_fallback(tmp_path):
    _write_result(tmp_path, "b1", "s2", {
        "excess_return_vs_buy_hold": None,
        "benchmark_excess_return": 0.012,
    })
    # 删掉 excess 键使其走 benchmark 兜底
    path = tmp_path / "b1" / "s2" / "backtest" / "strategy_performance.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload.pop("excess_return_vs_buy_hold", None)
    payload["benchmark_excess_return"] = 0.012
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = latest_strategy_result("s2", tmp_path)
    assert result["metrics"].get("benchmark_excess") == pytest.approx(0.012)


def test_latest_strategy_result_none(tmp_path):
    assert latest_strategy_result("ghost", tmp_path) is None


def test_list_result_artifacts(tmp_path):
    _write_result(tmp_path, "b1", "s1", {})
    (tmp_path / "b1" / "s1" / "backtest" / "trades.csv").write_text("a,b\n", encoding="utf-8")
    files = list_result_artifacts(tmp_path / "b1" / "s1")
    rels = {f["rel"] for f in files}
    assert "backtest/strategy_performance.json" in rels
    assert "backtest/trades.csv" in rels


# --- overview 四列数据 ---


def test_overview_four_columns(tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    for sid in ("s1", "s2"):
        (catalog / f"{sid}.yaml").write_text("x: 1", encoding="utf-8")
    backtests = tmp_path / "backtests"
    _write_result(backtests, "b1", "s1", {})

    overview = refresh_overview(
        state_path=tmp_path / "state.json",
        registry_path=tmp_path / "registry.json",
        delta_root=tmp_path / "delta",
        catalog_dir=catalog,
        backtests_dir=backtests,
    )
    by_id = {s["strategy_id"]: s for s in overview["strategies"]}
    s1 = by_id["s1"]
    assert s1["date_start"] == "2024-07-01"
    assert s1["date_end"] == "2026-07-27"
    assert s1["traded_symbol_count"] == 3200
    assert s1["symbol_count"] == 5547
    assert s1["excess_return"] == pytest.approx(-0.0234)
    assert s1["max_drawdown"] == pytest.approx(-0.35)
    # 无结果策略显示 None（前端渲染 —）
    assert by_id["s2"]["excess_return"] is None
    assert by_id["s2"]["date_start"] is None
    # 全量模式默认开启
    assert by_id["s1"]["enabled"] is True
    assert by_id["s2"]["enabled"] is True


# --- registry v2 stopped 语义（含旧格式兼容） ---


def test_registry_legacy_formats(tmp_path):
    reg = tmp_path / "registry.json"
    reg.write_text(json.dumps(["a", "b"]), encoding="utf-8")  # 纯数组
    assert load_registry(reg) == {"include": ["a", "b"], "stopped": []}
    reg.write_text(json.dumps({"strategies": ["a"]}), encoding="utf-8")  # 线上旧格式
    assert load_registry(reg) == {"include": ["a"], "stopped": []}


def test_set_strategy_stopped_toggle(tmp_path):
    reg = tmp_path / "registry.json"
    data = set_strategy_stopped("s1", True, reg)
    assert data["stopped"] == ["s1"]
    data = set_strategy_stopped("s2", True, reg)
    assert data["stopped"] == ["s1", "s2"]
    data = set_strategy_stopped("s1", False, reg)
    assert data["stopped"] == ["s2"]
    with pytest.raises(ValueError, match="不能为空"):
        set_strategy_stopped(" ", True, reg)


def test_stopped_applies_in_both_modes(tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    for sid in ("a", "b"):
        (catalog / f"{sid}.yaml").write_text("x: 1", encoding="utf-8")
    reg = tmp_path / "registry.json"

    # 全量模式（include 空）+ stopped
    save_registry({"include": [], "stopped": ["a"]}, reg)
    overview = refresh_overview(
        state_path=tmp_path / "state.json", registry_path=reg,
        delta_root=tmp_path / "delta", catalog_dir=catalog,
        backtests_dir=tmp_path / "bt",
    )
    assert overview["mode"] == "full_catalog"
    by_id = {s["strategy_id"]: s for s in overview["strategies"]}
    assert by_id["a"]["enabled"] is False
    assert by_id["b"]["enabled"] is True


# --- catalog 简介提取 ---


def test_strategy_catalog_info(tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text(
        "# 策略 ID: s1\n# 说明: RSI 超卖回归，RSI>60 出场\n# =====\n"
        "experiment:\n  name: s1_exp\n"
        "signal:\n  entry: rsi_14 > 30\n  exit: rsi_14 > 60\n"
        "holding:\n  max_holding_days: 5\n",
        encoding="utf-8",
    )
    info = strategy_catalog_info("s1", catalog)
    assert info["name"] == "s1_exp"
    assert info["entry"] == "rsi_14 > 30"
    assert info["exit"] == "rsi_14 > 60"
    assert info["max_holding_days"] == 5
    assert any("RSI 超卖回归" in c for c in info["comments"])
    assert strategy_catalog_info("ghost", catalog) == {}


# --- 删除连动产物（白名单） ---


def test_delete_strategy_removes_artifacts(tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("x: 1", encoding="utf-8")
    backtests = tmp_path / "backtests"
    (backtests / "b1" / "s1" / "backtest").mkdir(parents=True)
    (backtests / "refresh" / "rb" / "s1").mkdir(parents=True)  # 嵌套批次目录
    (backtests / "b1" / "s2").mkdir(parents=True)
    result = delete_strategy(
        "s1", catalog_dir=catalog, registry_path=tmp_path / "reg.json",
        outputs_backtests=backtests,
    )
    assert len(result["deleted_dirs"]) == 1  # 只有 <backtests>/<batch>/<sid> 一级
    assert not (backtests / "b1" / "s1").exists()
    assert (backtests / "refresh" / "rb" / "s1").is_dir()  # 更深嵌套不动（白名单边界）
    assert (backtests / "b1" / "s2").is_dir()  # 其它策略不动


# --- 路由层 ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_route_toggle(app_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("x: 1", encoding="utf-8")
    registry = tmp_path / "registry.json"
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", registry)
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)

    resp = app_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "s1", "stopped": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["stopped"] == ["s1"]
    assert "下个定时任务生效" in data["message"]

    resp = app_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "ghost", "stopped": True})
    assert resp.status_code == 400
    resp = app_client.post("/api/admin/strategies/toggle", json={"strategy_id": ""})
    assert resp.status_code == 400


def _setup_detail_env(monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr
    import quant_research_engine.gui.strategy_admin as sa

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text(
        "# 说明: 测试策略\nexperiment:\n  name: s1_exp\nsignal:\n  entry: rsi_14 > 30\n",
        encoding="utf-8",
    )
    backtests = tmp_path / "backtests"
    _write_result(backtests, "b1", "s1", {})
    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", backtests)
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(sa, "CATALOG_DIR", catalog)
    # app 路由内 import 的是 rr.DEFAULT_BACKTESTS_DIR（函数默认参数在定义时绑定！）
    return catalog, backtests


def test_route_strategy_detail(app_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    # latest_strategy_result 默认参数在定义时绑定，需要同时打函数默认值的补丁
    import quant_research_engine.gui.refresh_registry as rr

    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", tmp_path / "backtests")

    resp = app_client.get("/admin/strategy/s1")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "s1" in html
    assert "测试策略" in html
    assert "2024-07-01" in html and "2026-07-27" in html
    assert "最大回撤" in html
    assert "产物文件下载" in html

    resp = app_client.get("/admin/strategy/ghost")
    assert resp.status_code == 404


def test_route_strategy_artifact(app_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    resp = app_client.get("/api/admin/strategy/s1/artifact/backtest/strategy_performance.json")
    assert resp.status_code == 200
    # 越界拒绝
    resp = app_client.get("/api/admin/strategy/s1/artifact/..%2F..%2Fsecret.txt")
    assert resp.status_code in (400, 404)
    resp = app_client.get("/api/admin/strategy/ghost/artifact/x.json")
    assert resp.status_code == 404
