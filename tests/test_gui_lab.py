"""策略实验台（lab，8081）应用测试（QRE-GUI-LAB-PORT-017）。

覆盖：lab 首页两个 tab、策略详情页与产物下载、关键 API
（/api/admin/refresh、/api/strategies/sandbox、/api/strategies/create 校验路径、
/api/admin/strategies/toggle），并确认 lab 不挂 8080 专有路由而 create_app 保持不变。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def lab_client(monkeypatch, tmp_path):
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

    from quant_research_engine.gui.lab import create_lab_app

    app = create_lab_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


# --- 首页：两个 tab 原样移植 ---


def test_lab_home_200_two_tabs(lab_client):
    resp = lab_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # 两个 tab 标记
    assert 'data-tab="strategy"' in html
    assert "新增策略" in html
    assert 'data-tab="onboard"' in html
    assert "回测管理" in html
    # 新增策略 tab 关键交互（自 index.html strategy tab 移植）
    assert 'id="tab-strategy"' in html
    assert 'id="btn-nl-compile"' in html
    assert 'id="btn-save-sandbox"' in html
    assert 'id="sandbox-panel"' in html
    assert 'id="btn-deep-validate"' in html
    # 回测管理 tab 关键交互（自 admin.html onboard tab 移植，含 QRE-GUI-SORT-016 排序）
    assert 'id="tab-onboard"' in html
    assert 'id="btn-ob-refresh"' in html
    assert "ob-registry-table" in html
    assert "sortable" in html
    assert "/api/admin/refresh" in html
    assert "/api/admin/strategies/toggle" in html
    assert "/api/admin/strategies/delete" in html


def test_lab_does_not_mount_full_console_routes(lab_client):
    # lab 只含两个页面相关路由：8080 的管理台/因子/构建器路由不在 lab 上
    assert lab_client.get("/admin").status_code == 404
    assert lab_client.get("/api/admin/overview").status_code == 404
    assert lab_client.get("/api/factor-create/sandbox").status_code == 404
    assert lab_client.get("/api/builder/indicator-catalog").status_code == 404


# --- 策略详情页 + 产物下载 ---


def _write_result(root: Path, batch: str, sid: str) -> Path:
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
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


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
    _write_result(backtests, "b1", "s1")
    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", backtests)
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(sa, "CATALOG_DIR", catalog)
    return catalog, backtests


def test_lab_strategy_detail(lab_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    resp = lab_client.get("/admin/strategy/s1")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "s1" in html
    assert "测试策略" in html
    assert "产物文件下载" in html

    assert lab_client.get("/admin/strategy/ghost").status_code == 404


def test_lab_strategy_artifact(lab_client, monkeypatch, tmp_path):
    _setup_detail_env(monkeypatch, tmp_path)
    resp = lab_client.get("/api/admin/strategy/s1/artifact/backtest/strategy_performance.json")
    assert resp.status_code == 200
    # 越界拒绝
    resp = lab_client.get("/api/admin/strategy/s1/artifact/..%2F..%2Fsecret.txt")
    assert resp.status_code in (400, 404)
    assert lab_client.get("/api/admin/strategy/ghost/artifact/x.json").status_code == 404


# --- 关键 API 在 lab 上可用 ---


def test_lab_api_admin_refresh(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("experiment:\n  name: s1\n", encoding="utf-8")
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(rr, "DEFAULT_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(rr, "DEFAULT_BACKTESTS_DIR", tmp_path / "backtests")
    monkeypatch.setattr(rr, "DEFAULT_INCREMENTAL_ROOT", tmp_path / "incremental")
    monkeypatch.setattr(rr, "DEFAULT_DELTA_ROOT", tmp_path / "delta")

    resp = lab_client.get("/api/admin/refresh")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["catalog_total"] == 1


def test_lab_api_refresh_register_validation(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")

    assert lab_client.post("/api/admin/refresh/register", json={"strategy_id": ""}).status_code == 400
    assert lab_client.post("/api/admin/refresh/register", json={"strategy_id": "ghost"}).status_code == 400
    assert lab_client.post("/api/admin/refresh/unregister", json={"strategy_id": ""}).status_code == 400


def test_lab_api_toggle(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("x: 1", encoding="utf-8")
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", tmp_path / "registry.json")
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)

    resp = lab_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "s1", "stopped": True})
    assert resp.status_code == 200
    assert resp.get_json()["stopped"] == ["s1"]
    assert lab_client.post("/api/admin/strategies/toggle",
                           json={"strategy_id": "ghost", "stopped": True}).status_code == 400


def test_lab_api_strategies_sandbox(lab_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.strategy_create as sc

    monkeypatch.setattr(sc, "DEFAULT_SANDBOX_DIR", tmp_path / "sandbox")
    resp = lab_client.get("/api/strategies/sandbox")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["strategies"] == []
    assert data["categories"]


def test_lab_api_strategies_create_invalid_yaml(lab_client):
    resp = lab_client.post("/api/strategies/create",
                           json={"mode": "manual", "yaml_text": ": 不是合法yaml"})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["ok"] is False
    assert data["code"] == "invalid_yaml"


def test_lab_api_validate(lab_client):
    resp = lab_client.post("/api/validate", json={"yaml": "experiment:\n  name: x\n"})
    assert resp.status_code == 200
    assert "valid" in resp.get_json()


def test_lab_api_templates(lab_client):
    assert lab_client.get("/api/templates").status_code == 200
    assert lab_client.post("/api/templates", json={"name": "", "yaml": "x"}).status_code == 400


# --- 8080 主控制台路由零变化（共享注册后仍全量可用） ---


def test_create_app_routes_unchanged():
    from quant_research_engine.gui.app import create_app
    from quant_research_engine.gui.lab import create_lab_app

    full_rules = {r.rule for r in create_app().url_map.iter_rules()}
    lab_rules = {r.rule for r in create_lab_app().url_map.iter_rules()}
    # lab 路由是主控制台的子集
    assert lab_rules <= full_rules
    # 主控制台专有规律犹在
    for rule in ("/admin", "/api/admin/overview", "/api/factor-create/sandbox",
                 "/api/builder/compile", "/api/admin/market-risk", "/compare"):
        assert rule in full_rules
        assert rule not in lab_rules
