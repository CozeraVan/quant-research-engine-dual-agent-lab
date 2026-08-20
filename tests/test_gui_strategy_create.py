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
    record_smoke("sc_demo", "rid-1", status="completed", sandbox_dir=sandbox)

    result = promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)
    assert result["ok"] is True
    dest = catalog / "mean_reversion" / "sc_demo.yaml"
    assert Path(result["path"]) == dest
    assert dest.exists()
    assert not (sandbox / "sc_demo.yaml").exists()
    # 冒烟 sidecar 保留作历史记录
    assert (sandbox / "sc_demo.smoke.json").exists()


# --- 晋升冒烟状态闸（缺口 2） ---


def test_promote_blocked_without_smoke(tmp_path):
    catalog = tmp_path / "catalog"
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=catalog, sandbox_dir=sandbox)
    result = promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)
    assert result["ok"] is False
    assert result["code"] == "smoke_not_passed"
    assert "冒烟" in result["error"]
    assert (sandbox / "sc_demo.yaml").exists()  # 未移动


def test_promote_blocked_when_smoke_running_or_failed(tmp_path):
    catalog = tmp_path / "catalog"
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=catalog, sandbox_dir=sandbox)
    record_smoke("sc_demo", "rid-1", status="running", sandbox_dir=sandbox)
    assert promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)["code"] == "smoke_not_passed"
    record_smoke("sc_demo", "rid-1", status="failed", sandbox_dir=sandbox)
    assert promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox)["code"] == "smoke_not_passed"


def test_promote_force_bypasses_gate(tmp_path):
    catalog = tmp_path / "catalog"
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=catalog, sandbox_dir=sandbox)
    result = promote("sc_demo", "mean_reversion", catalog_dir=catalog, sandbox_dir=sandbox, force=True)
    assert result["ok"] is True
    assert result["forced"] is True
    assert (catalog / "mean_reversion" / "sc_demo.yaml").exists()


# --- 冒烟 sidecar 闭环（缺口 1） ---


def test_finalize_smoke_completed_writes_metrics(tmp_path):
    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)
    record = {
        "sandbox_strategy": "sc_demo",
        "run_id": "rid-1",
        "status": "completed",
        "finished_at": "2026-08-20T00:00:00+00:00",
    }
    summary = {"metrics": {
        "total_trade_count": 7,
        "strategy_total_return": 0.05,
        "excess_return_vs_buy_hold": 0.01,
        "max_drawdown": -0.02,
        "unrelated": 1,
    }}
    strategy_create.finalize_smoke(record, sandbox_dir=sandbox, summary=summary)
    smoke = json.loads((sandbox / "sc_demo.smoke.json").read_text(encoding="utf-8"))
    assert smoke["status"] == "completed"
    assert smoke["finished_at"] == "2026-08-20T00:00:00+00:00"
    assert smoke["metrics"] == {
        "total_trade_count": 7,
        "strategy_total_return": 0.05,
        "excess_return_vs_buy_hold": 0.01,
        "max_drawdown": -0.02,
    }
    # 再次冒烟（running）不应残留上次的 error/metrics 之外的脏数据
    record_smoke("sc_demo", "rid-2", sandbox_dir=sandbox)
    failed = {"sandbox_strategy": "sc_demo", "run_id": "rid-2", "status": "failed", "error": "boom"}
    strategy_create.finalize_smoke(failed, sandbox_dir=sandbox)
    smoke = json.loads((sandbox / "sc_demo.smoke.json").read_text(encoding="utf-8"))
    assert smoke["status"] == "failed" and smoke["error"] == "boom"


def test_finalize_smoke_ignores_unmarked_run(tmp_path):
    assert strategy_create.finalize_smoke({"run_id": "x", "status": "completed"}, sandbox_dir=tmp_path) is None


def test_engine_finalize_hook_writes_sidecar(monkeypatch, tmp_path):
    """engine._execute_and_finalize 对带 sandbox_strategy 标记的 run 回写 sidecar。"""
    from quant_research_engine.gui import engine

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "rid-1"
    run_dir.mkdir(parents=True)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(engine, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(strategy_create, "DEFAULT_SANDBOX_DIR", sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)

    def fake_cli(cmd, stdout_path, stderr_path):
        stdout_path.write_text(
            "trades=3\ntotal_return=0.05\nexcess_return_vs_buy_hold=0.01\nmax_drawdown=-0.02\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(engine, "_run_via_cli", fake_cli)
    record = {"run_id": "rid-1", "executor": "cli", "sandbox_strategy": "sc_demo", "status": "running"}
    engine._execute_and_finalize(record, run_dir, ["true"], {})
    smoke = json.loads((sandbox / "sc_demo.smoke.json").read_text(encoding="utf-8"))
    assert smoke["status"] == "completed"
    assert smoke["metrics"]["total_trade_count"] == 3.0
    assert smoke["metrics"]["strategy_total_return"] == 0.05
    assert smoke["metrics"]["excess_return_vs_buy_hold"] == 0.01
    assert smoke["metrics"]["max_drawdown"] == -0.02
    assert smoke["finished_at"]


def test_engine_finalize_hook_failure(monkeypatch, tmp_path):
    from quant_research_engine.gui import engine

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "rid-1"
    run_dir.mkdir(parents=True)
    sandbox = tmp_path / "sandbox"
    monkeypatch.setattr(engine, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(strategy_create, "DEFAULT_SANDBOX_DIR", sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)

    def boom(cmd, stdout_path, stderr_path):
        raise RuntimeError("引擎炸了")

    monkeypatch.setattr(engine, "_run_via_cli", boom)
    record = {"run_id": "rid-1", "executor": "cli", "sandbox_strategy": "sc_demo", "status": "running"}
    engine._execute_and_finalize(record, run_dir, ["true"], {})
    smoke = json.loads((sandbox / "sc_demo.smoke.json").read_text(encoding="utf-8"))
    assert smoke["status"] == "failed"
    assert "引擎炸了" in smoke["error"]


def test_list_sandbox_self_heals_stale_running(monkeypatch, tmp_path):
    """GUI 重启丢线程后 sidecar 滞留 running：list_sandbox 查 run 终态补写。"""
    from quant_research_engine.gui import engine

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "rid-1"
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps({
        "run_id": "rid-1", "sandbox_strategy": "sc_demo", "status": "completed",
        "finished_at": "2026-08-20T01:00:00+00:00",
    }), encoding="utf-8")
    (run_dir / "stdout.log").write_text("trades=2\ntotal_return=0.01\n", encoding="utf-8")
    monkeypatch.setattr(engine, "RUNS_DIR", runs_dir)

    sandbox = tmp_path / "sandbox"
    save_to_sandbox(_VALID_YAML, catalog_dir=tmp_path / "catalog", sandbox_dir=sandbox)
    record_smoke("sc_demo", "rid-1", sandbox_dir=sandbox)  # running
    entry = list_sandbox(sandbox)[0]
    assert entry["smoke"]["status"] == "completed"
    assert entry["smoke"]["metrics"]["total_trade_count"] == 2.0


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
    # 假 run_backtest：不真跑，建 run 目录并落盘 status.json（含 mark 合并，
    # 与真实 run_backtest 行为对齐）
    def fake_run_backtest(**kwargs):
        rid = "test-run-1"
        (runs_dir / rid).mkdir(parents=True, exist_ok=True)
        record = {"run_id": rid, "status": "running", "kwargs": kwargs}
        record.update(kwargs.get("mark") or {})
        (runs_dir / rid / "status.json").write_text(
            json.dumps(record, ensure_ascii=False), encoding="utf-8"
        )
        return record

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
    strategy_create.record_smoke("sc_demo", "rid-smoke", status="completed", sandbox_dir=sandbox)
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


def test_api_promote_blocked_without_smoke_409(app_client):
    client, sandbox, _, _ = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/promote", json={"name": "sc_demo", "category": "breakout"})
    assert resp.status_code == 409
    data = resp.get_json()
    assert data["code"] == "smoke_not_passed"
    assert "冒烟" in data["error"]
    assert (sandbox / "sc_demo.yaml").exists()  # 未移动


def test_api_promote_force_bypass(app_client):
    client, sandbox, catalog, _ = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    resp = client.post("/api/strategies/promote", json={"name": "sc_demo", "category": "breakout", "force": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["forced"] is True
    assert "force" in data["warning"]
    assert (catalog / "breakout" / "sc_demo.yaml").exists()


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
    # 沙箱列表冒烟状态渲染（通过/失败/冒烟中）与因子冒烟轮询
    assert "冒烟通过" in html and "冒烟失败" in html and "冒烟中" in html
    assert "/api/factor-create/smoke/" in html


# --- 晋升全量回测闸（promotion gate，QRE-GUI-PROMO-GATE-001） ---


def _gate_record(**over):
    record = {
        "promotion_gate": True,
        "promoted_strategy": "sc_demo",
        "run_id": "rid-gate",
        "status": "completed",
    }
    record.update(over)
    return record


def _gate_summary(trades=50, excess=0.02):
    return {"metrics": {
        "total_trade_count": trades,
        "strategy_total_return": 0.10,
        "excess_return_vs_buy_hold": excess,
        "max_drawdown": -0.05,
        "unrelated": 1,
    }}


def test_finalize_promotion_gate_passed(tmp_path):
    path = strategy_create.finalize_promotion_gate(
        _gate_record(), gates_dir=tmp_path, summary=_gate_summary()
    )
    gate = json.loads(path.read_text(encoding="utf-8"))
    assert gate["strategy"] == "sc_demo"
    assert gate["run_id"] == "rid-gate"
    assert gate["gate"] == "passed"
    assert gate["forced"] is False
    assert gate["criteria"]["min_trades"] == 30
    assert gate["metrics"] == {
        "total_trade_count": 50,
        "strategy_total_return": 0.10,
        "excess_return_vs_buy_hold": 0.02,
        "max_drawdown": -0.05,
    }
    assert "error" not in gate and gate["evaluated_at"]


def test_finalize_promotion_gate_failed_too_few_trades(tmp_path):
    path = strategy_create.finalize_promotion_gate(
        _gate_record(), gates_dir=tmp_path, summary=_gate_summary(trades=29, excess=0.5)
    )
    assert json.loads(path.read_text(encoding="utf-8"))["gate"] == "failed"


def test_finalize_promotion_gate_failed_negative_excess(tmp_path):
    path = strategy_create.finalize_promotion_gate(
        _gate_record(), gates_dir=tmp_path, summary=_gate_summary(trades=100, excess=0.0)
    )
    assert json.loads(path.read_text(encoding="utf-8"))["gate"] == "failed"


def test_finalize_promotion_gate_failed_missing_metrics(tmp_path):
    path = strategy_create.finalize_promotion_gate(
        _gate_record(), gates_dir=tmp_path, summary={"metrics": {}}
    )
    assert json.loads(path.read_text(encoding="utf-8"))["gate"] == "failed"


def test_finalize_promotion_gate_run_failed(tmp_path):
    path = strategy_create.finalize_promotion_gate(
        _gate_record(status="failed", error="引擎炸了"), gates_dir=tmp_path
    )
    gate = json.loads(path.read_text(encoding="utf-8"))
    assert gate["gate"] == "failed"
    assert "引擎炸了" in gate["error"]
    assert "metrics" not in gate


def test_finalize_promotion_gate_forced_passthrough(tmp_path):
    """force 晋升：评估照跑，forced 标记透传（failed 不阻止日更）。"""
    from quant_research_engine.gui.refresh_registry import gate_blocks_daily, load_gate

    strategy_create.finalize_promotion_gate(
        _gate_record(promotion_forced=True), gates_dir=tmp_path,
        summary=_gate_summary(trades=1, excess=-0.5),
    )
    gate = load_gate("sc_demo", tmp_path)
    assert gate["gate"] == "failed" and gate["forced"] is True
    assert gate_blocks_daily(gate) is False  # 强制在库：不阻止日更


def test_finalize_promotion_gate_ignores_unmarked_run(tmp_path):
    assert strategy_create.finalize_promotion_gate(
        {"run_id": "x", "status": "completed"}, gates_dir=tmp_path
    ) is None
    assert strategy_create.finalize_promotion_gate(
        {"promotion_gate": True, "status": "completed"}, gates_dir=tmp_path
    ) is None  # 无策略名


def test_engine_finalize_hook_writes_gate(monkeypatch, tmp_path):
    """engine._execute_and_finalize 对带 promotion_gate 标记的 run 回写 gate 文件。"""
    from quant_research_engine.gui import engine
    from quant_research_engine.gui import refresh_registry

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "rid-g1"
    run_dir.mkdir(parents=True)
    gates_dir = tmp_path / "gates"
    monkeypatch.setattr(engine, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(refresh_registry, "DEFAULT_GATES_DIR", gates_dir)

    def fake_cli(cmd, stdout_path, stderr_path):
        stdout_path.write_text(
            "trades=50\ntotal_return=0.10\nexcess_return_vs_buy_hold=0.02\nmax_drawdown=-0.05\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(engine, "_run_via_cli", fake_cli)
    record = {
        "run_id": "rid-g1",
        "executor": "cli",
        "promotion_gate": True,
        "promoted_strategy": "sc_demo",
        "status": "running",
    }
    engine._execute_and_finalize(record, run_dir, ["true"], {})
    gate = json.loads((gates_dir / "sc_demo.json").read_text(encoding="utf-8"))
    assert gate["gate"] == "passed"
    assert gate["metrics"]["total_trade_count"] == 50.0


def test_engine_finalize_hook_gate_failure(monkeypatch, tmp_path):
    from quant_research_engine.gui import engine
    from quant_research_engine.gui import refresh_registry

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "rid-g2"
    run_dir.mkdir(parents=True)
    gates_dir = tmp_path / "gates"
    monkeypatch.setattr(engine, "RUNS_DIR", runs_dir)
    monkeypatch.setattr(refresh_registry, "DEFAULT_GATES_DIR", gates_dir)

    def boom(cmd, stdout_path, stderr_path):
        raise RuntimeError("引擎炸了")

    monkeypatch.setattr(engine, "_run_via_cli", boom)
    record = {
        "run_id": "rid-g2",
        "executor": "cli",
        "promotion_gate": True,
        "promoted_strategy": "sc_demo",
        "status": "running",
    }
    engine._execute_and_finalize(record, run_dir, ["true"], {})
    gate = json.loads((gates_dir / "sc_demo.json").read_text(encoding="utf-8"))
    assert gate["gate"] == "failed"
    assert "引擎炸了" in gate["error"]


def test_api_promote_marks_run_and_force_gate_note(app_client):
    """晋升触发的全量回测带 promotion_gate 标记；force 响应注明闸语义。"""
    client, sandbox, catalog, runs_dir = app_client
    client.post("/api/strategies/create", json={"mode": "manual", "yaml_text": _VALID_YAML})
    # force=true 跳过冒烟闸
    resp = client.post("/api/strategies/promote",
                       json={"name": "sc_demo", "category": "mean_reversion", "force": True})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True and data["forced"] is True
    assert "强制在库" in data["gate_note"]
    status = json.loads((runs_dir / "test-run-1" / "status.json").read_text(encoding="utf-8"))
    assert status["promotion_gate"] is True
    assert status["promoted_strategy"] == "sc_demo"
    assert status["promotion_forced"] is True


def test_api_deep_validate_501(app_client):
    client, _, _, _ = app_client
    resp = client.post("/api/strategies/sc_demo/deep-validate", json={})
    assert resp.status_code == 501
    data = resp.get_json()
    assert data["ok"] is False and data["code"] == "not_implemented"
    assert "策略→信号池转换器" in data["error"]
    assert "validate_factor.py" in data["design"]["target_cli"]
