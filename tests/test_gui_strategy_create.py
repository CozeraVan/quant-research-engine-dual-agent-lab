from __future__ import annotations

import json
from pathlib import Path

import pytest

from quant_research_engine.gui import strategy_create
from quant_research_engine.gui.strategy_create import (
    CATALOG_CATEGORIES,
    check_strategy_duplicate,
    discard,
    list_sandbox,
    promote,
    record_smoke,
    save_to_sandbox,
)

_VALID_YAML = (
    "experiment:\n  name: sc_demo\n  market_profile: ashare_daily_default\n  frequency: daily\n"
    "data:\n  market_fields: [open, high, low, close, pre_close, vol, amount]\n"
    "  factor_fields:\n    rsi_14: factors.stock_daily_momentum_close.rsi_14\n"
    "signal:\n  entry: rsi_14 > 30\n  exit: rsi_14 > 60\n"
    "holding:\n  max_holding_days: 5\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
)


def _write_catalog_strategy(catalog_dir: Path, category: str, name: str) -> Path:
    target_dir = catalog_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{name}.yaml"
    path.write_text(_VALID_YAML.replace("sc_demo", name), encoding="utf-8")
    return path


# --- 查重 ---


def test_duplicate_hit_in_catalog(tmp_path):
    catalog = tmp_path / "catalog"
    _write_catalog_strategy(catalog, "mean_reversion", "sc_demo")
    conflict = check_strategy_duplicate(
        "sc_demo", catalog_dir=catalog, sandbox_dir=tmp_path / "sandbox"
    )
    assert conflict is not None
    assert "catalog" in conflict
    assert "mean_reversion" in conflict


def test_duplicate_hit_in_sandbox(tmp_path):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "sc_demo.yaml").write_text(_VALID_YAML, encoding="utf-8")
    conflict = check_strategy_duplicate(
        "sc_demo", catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox
    )
    assert conflict is not None
    assert "沙箱" in conflict


def test_duplicate_miss(tmp_path):
    assert check_strategy_duplicate(
        "brand_new", catalog_dir=tmp_path / "catalog", sandbox_dir=tmp_path / "sandbox"
    ) is None


# --- 沙箱落盘与列出 ---


def test_save_to_sandbox_roundtrip(tmp_path):
    sandbox = tmp_path / "sandbox"
    result = save_to_sandbox(
        _VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox
    )
    assert result["ok"] is True
    assert result["name"] == "sc_demo"
    assert Path(result["path"]).read_text(encoding="utf-8") == _VALID_YAML

    entries = list_sandbox(sandbox)
    assert len(entries) == 1
    assert entries[0]["name"] == "sc_demo"
    assert entries[0]["smoke"] is None


def test_save_to_sandbox_invalid_yaml(tmp_path):
    result = save_to_sandbox(
        "name: nope\n", catalog_dir=tmp_path / "catalog", sandbox_dir=tmp_path / "sandbox"
    )
    assert result["ok"] is False
    assert result["code"] == "invalid_yaml"


def test_save_to_sandbox_duplicate_rejected(tmp_path):
    sandbox = tmp_path / "sandbox"
    kwargs = {"catalog_dir": tmp_path / "catalog", "sandbox_dir": sandbox}
    assert save_to_sandbox(_VALID_YAML, **kwargs)["ok"] is True
    again = save_to_sandbox(_VALID_YAML, **kwargs)
    assert again["ok"] is False
    assert again["code"] == "duplicate_name"


def test_record_smoke_and_list(tmp_path):
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    record_smoke("sc_demo", "20260801T000000000000", sandbox_dir=sandbox)
    entry = list_sandbox(sandbox)[0]
    assert entry["smoke"]["run_id"] == "20260801T000000000000"
    assert entry["smoke"]["status"] == "running"


# --- 晋升 / 删除 ---


def test_promote_invalid_category(tmp_path):
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    result = promote("sc_demo", "not_a_category", catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    assert result["ok"] is False
    assert result["code"] == "invalid_category"
    for category in CATALOG_CATEGORIES:
        assert category in result["error"]


def test_promote_not_found(tmp_path):
    result = promote("ghost", "breakout", catalog_dir=tmp_path / "catalog", sandbox_dir=tmp_path / "sandbox")
    assert result["ok"] is False
    assert result["code"] == "not_found"


def test_promote_moves_file(tmp_path):
    catalog = tmp_path / "catalog"
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=catalog, sandbox_dir=sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)

    result = promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)
    assert result["ok"] is True
    dest = catalog / "mean_reversion" / "sc_demo.yaml"
    assert Path(result["path"]) == dest
    assert dest.exists()
    assert not (sandbox / "sc_demo.yaml").exists()
    # 冒烟 sidecar 保留作历史记录
    assert (sandbox / "sc_demo.smoke.json").exists()


def test_promote_blocked_by_catalog_duplicate(tmp_path):
    catalog = tmp_path / "catalog"
    sandbox = tmp_path / "sandbox"
    _write_catalog_strategy(catalog, "breakout", "sc_demo")
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "empty_catalog", sandbox_dir=sandbox)
    result = promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)
    assert result["ok"] is False
    assert result["code"] == "duplicate_name"


def test_discard_removes_yaml_and_sidecar(tmp_path):
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)
    result = discard("sc_demo", sandbox_dir=sandbox)
    assert result["ok"] is True
    assert list_sandbox(sandbox) == []
    assert discard("sc_demo", sandbox_dir=sandbox)["code"] == "not_found"


# --- API 层 ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    catalog = tmp_path / "catalog"
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    monkeypatch.setattr(strategy_create, "DEFAULT_SANDBOX_DIR", sandbox)
    monkeypatch.setattr(strategy_create, "CATALOG_DIR", catalog)
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    monkeypatch.setattr("quant_research_engine.gui.app.try_acquire_run_slot", lambda: True)
    monkeypatch.setattr("quant_research_engine.gui.app.release_run_slot", lambda: None)
    # 因子存在性检查注入假 lookup：rsi_14 存在
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._default_column_lookup",
        lambda db_url=None: (lambda table: {"rsi_14"}),
    )
    # 假 run_backtest：不真跑，只建 run 目录供 _mark_run 落盘
    def fake_run_backtest(**kwargs):
        rid = "test-run-1"
        (runs_dir / rid).mkdir(parents=True, exist_ok=True)
        return {"run_id": rid, "status": "running", "kwargs": kwargs}

    monkeypatch.setattr("quant_research_engine.gui.app.run_backtest", fake_run_backtest)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, sandbox, catalog, runs_dir


def test_api_create_manual_ok(app_client):
    client, sandbox, _, _ = app_client
    resp = client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["name"] == "sc_demo"
    assert (sandbox / "sc_demo.yaml").exists()


def test_api_create_invalid_yaml_400(app_client):
    client, _, _, _ = app_client
    resp = client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": "name: nope\n"})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "invalid_yaml"


def test_api_create_duplicate_409(app_client):
    client, _, _, _ = app_client
    assert client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML}).status_code == 200
    resp = client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "duplicate_name"


def test_api_create_missing_factors(app_client, monkeypatch, tmp_path):
    client, sandbox, _, _ = app_client
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._default_column_lookup",
        lambda db_url=None: (lambda table: set()),  # 什么都不存在
    )
    enqueued = []
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._enqueue_missing_factors",
        lambda spec, missing, *, queue_path: enqueued.append(missing),
    )
    resp = client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is False
    assert data["code"] == "missing_factors"
    assert data["missing_factors"] == ["rsi_14"]
    assert enqueued  # 已入补因子队列
    assert not (sandbox / "sc_demo.yaml").exists()  # 缺因子不入沙箱


def test_api_sandbox_list(app_client):
    client, _, _, _ = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.get("/api/strategies/sandbox")
    data = resp.get_json()
    assert data["ok"] is True
    assert [s["name"] for s in data["strategies"]] == ["sc_demo"]
    assert "mean_reversion" in data["categories"]


def test_api_smoke(app_client):
    client, sandbox, _, runs_dir = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/smoke", json={"name": "sc_demo"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["run_id"] == "test-run-1"
    assert data["code"] == strategy_create.SMOKE_DEFAULT_CODE
    # sidecar 已记录，run 记录带 sandbox 标记
    smoke = json.loads((sandbox / "sc_demo.smoke.json").read_text(encoding="utf-8"))
    assert smoke["run_id"] == "test-run-1"
    status = json.loads((runs_dir / "test-run-1" / "status.json").read_text(encoding="utf-8"))
    assert status["sandbox_strategy"] == "sc_demo"
    assert status["purpose"] == "smoke"


def test_api_smoke_not_found(app_client):
    client, _, _, _ = app_client
    assert client.post("/api/strategies/smoke", json={"name": "ghost"}).status_code == 404


def test_api_promote(app_client):
    client, sandbox, catalog, runs_dir = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/promote", json={"name": "sc_demo", "category": "breakout"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["run_id"] == "test-run-1"
    assert (catalog / "breakout" / "sc_demo.yaml").exists()
    assert not (sandbox / "sc_demo.yaml").exists()
    status = json.loads((runs_dir / "test-run-1" / "status.json").read_text(encoding="utf-8"))
    assert status["promoted_strategy"] == "sc_demo"
    # 全量回测参数：shared + 空 codes（全市场）
    assert status["kwargs"]["mode"] == "shared"
    assert status["kwargs"]["codes"] == ""


def test_api_promote_invalid_category(app_client):
    client, sandbox, _, _ = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/promote", json={"name": "sc_demo", "category": "nope"})
    assert resp.status_code == 400
    assert (sandbox / "sc_demo.yaml").exists()  # 未移动


def test_api_sandbox_delete(app_client):
    client, sandbox, _, _ = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/sandbox/delete", json={"name": "sc_demo"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert not (sandbox / "sc_demo.yaml").exists()
    assert client.post("/api/strategies/sandbox/delete", json={"name": "sc_demo"}).status_code == 404


def test_index_page_contains_sandbox_panel(app_client):
    client, _, _, _ = app_client
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "沙箱策略" in html
    assert "btn-save-sandbox" in html
