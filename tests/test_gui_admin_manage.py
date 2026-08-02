from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from quant_research_engine.gui import daily_jobs
from quant_research_engine.gui.daily_jobs import get_daily_job, start_script_job
from quant_research_engine.gui.maintenance import (
    PROTECTED_BATCHES,
    delete_batches,
    list_batches,
)
from quant_research_engine.gui.strategy_admin import delete_strategy, find_strategy_file


# --- 策略删除 + 注册表联动 ---


@pytest.fixture
def strategy_env(tmp_path):
    catalog = tmp_path / "catalog"
    (catalog / "mean_reversion").mkdir(parents=True)
    (catalog / "mean_reversion" / "mr01a_x.yaml").write_text("experiment:\n  name: mr01a_x\n", encoding="utf-8")
    (catalog / "bo01a_y.yaml").write_text("experiment:\n  name: bo01a_y\n", encoding="utf-8")
    registry = tmp_path / "registry.json"
    backtests = tmp_path / "backtests"
    (backtests / "batch1" / "mr01a_x").mkdir(parents=True)
    return catalog, registry, backtests


def test_delete_strategy_ok_and_registry_sync(strategy_env):
    catalog, registry, backtests = strategy_env
    from quant_research_engine.gui.refresh_registry import save_registry

    save_registry({"include": ["mr01a_x", "bo01a_y"], "stopped": ["mr01a_x"]}, registry)
    result = delete_strategy(
        "mr01a_x", catalog_dir=catalog, registry_path=registry, outputs_backtests=backtests
    )
    assert not (catalog / "mean_reversion" / "mr01a_x.yaml").exists()
    assert result["registry"]["include"] == ["bo01a_y"]  # 自动移出注册表
    assert result["registry"]["stopped"] == []  # stopped 也清理
    # STRAT-TAB：产物目录一并删除并列出清单
    assert len(result["deleted_dirs"]) == 1
    assert not (backtests / "batch1" / "mr01a_x").exists()
    assert result["errors"] == []


def test_delete_strategy_not_found(strategy_env):
    catalog, registry, backtests = strategy_env
    with pytest.raises(ValueError, match="不在 catalog"):
        delete_strategy("ghost", catalog_dir=catalog, registry_path=registry,
                        outputs_backtests=backtests)
    with pytest.raises(ValueError, match="不能为空"):
        delete_strategy("  ", catalog_dir=catalog)


def test_find_strategy_file(strategy_env):
    catalog, _, _ = strategy_env
    assert find_strategy_file("bo01a_y", catalog) is not None
    assert find_strategy_file("nope", catalog) is None


# --- 通用脚本任务（补全/删列共用） ---


@pytest.fixture
def jobs_env(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", tmp_path / "daily-jobs")
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs._active_jobs", {})


def test_script_job_shares_pipeline_lock(jobs_env):
    calls = []

    def runner(cmd, cwd, job_dir):
        calls.append(cmd)
        time.sleep(0.2)
        return 0

    start_script_job(lock_key="indicators", label="因子补全", cmd=["echo", "1"], cwd=Path("/tmp"), runner=runner)
    # 同锁键（indicators 管线）重入 → 409 语义
    with pytest.raises(RuntimeError, match="已有任务在运行"):
        daily_jobs.start_daily_job("indicators", runner=runner)
    deadline = time.time() + 5
    while daily_jobs._active_jobs and time.time() < deadline:
        time.sleep(0.05)
    assert not daily_jobs._active_jobs
    assert calls == [["echo", "1"]]


# --- drop_factor_columns.py 安全检查（不触 DB 的路径） ---


def _run_drop_script(args):
    import subprocess
    import sys as _sys

    script = (Path(__file__).resolve().parents[2] / "indicators_tushare" / "scripts" / "drop_factor_columns.py")
    if not script.exists():
        pytest.skip("indicators_tushare repo 不可用")
    return subprocess.run(
        [_sys.executable, str(script), *args],
        capture_output=True, text=True, timeout=60,
        cwd=str(script.parent.parent),
    )


def test_drop_script_rejects_protected_columns():
    proc = _run_drop_script(["--table", "stock_daily_momentum_close", "--columns", "ts_code"])
    assert proc.returncode == 2
    assert "关键列不可删除" in proc.stderr


def test_drop_script_rejects_bad_table():
    proc = _run_drop_script(["--table", "public.stock_daily", "--columns", "x"])
    assert proc.returncode == 2
    assert "非法因子表名" in proc.stderr


# --- 批次删除路径白名单 ---


@pytest.fixture
def batches_env(tmp_path, monkeypatch):
    from quant_research_engine.gui import admin

    admin._cache.clear()
    backtests = tmp_path / "backtests"
    for name in ("batch_a", "batch_b", "refresh"):
        (backtests / name / "strat1").mkdir(parents=True)
    yield backtests
    admin._cache.clear()


def test_list_batches_protected(batches_env):
    result = list_batches(batches_env)
    by_name = {b["name"]: b for b in result["batches"]}
    assert by_name["refresh"]["protected"] is True
    assert by_name["batch_a"]["protected"] is False
    assert by_name["batch_a"]["strategy_count"] == 1
    # 受保护批次不计入可删合计
    assert result["total_size_bytes"] == sum(
        b["size_bytes"] or 0 for b in result["batches"] if b["name"] != "refresh"
    )


def test_delete_batches_whitelist(batches_env):
    result = delete_batches(["batch_a", "refresh", "../etc", "ghost", "a/b"], batches_env)
    assert result["deleted"] == ["batch_a"]
    assert not (batches_env / "batch_a").exists()
    assert (batches_env / "refresh").is_dir()  # 受保护未动
    errors = " ".join(result["errors"])
    assert "受保护" in errors and "非法批次名" in errors and "不存在" in errors


def test_delete_batches_symlink_escape_rejected(tmp_path, monkeypatch):
    from quant_research_engine.gui import admin

    admin._cache.clear()
    real = tmp_path / "real"
    real.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "backtests"
    link.symlink_to(real)
    # 在 root 外制造同名目录，root 内不放 → 白名单拒绝
    result = delete_batches(["outside"], link)
    assert result["deleted"] == []
    assert outside.is_dir()
    admin._cache.clear()


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
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", tmp_path / "daily-jobs")
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs._active_jobs", {})

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_route_strategy_delete(app_client, monkeypatch, tmp_path):
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "s1.yaml").write_text("x: 1", encoding="utf-8")
    registry = tmp_path / "registry.json"
    import quant_research_engine.gui.strategy_admin as sa
    import quant_research_engine.gui.refresh_registry as rr

    monkeypatch.setattr(sa, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", registry)
    monkeypatch.setattr(sa, "OUTPUTS_BACKTESTS", tmp_path / "bt")

    resp = app_client.post("/api/admin/strategies/delete", json={"strategy_id": "s1"})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert not (catalog / "s1.yaml").exists()

    resp = app_client.post("/api/admin/strategies/delete", json={"strategy_id": "ghost"})
    assert resp.status_code == 400
    resp = app_client.post("/api/admin/strategies/delete", json={"strategy_id": ""})
    assert resp.status_code == 400


def test_route_factor_backfill_command(app_client, monkeypatch):
    captured = {}

    def fake_start(**kw):
        captured.update(kw)
        return {"job_id": "j1", "status": "running", "pipeline": kw["lock_key"], "label": kw["label"]}

    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.start_script_job", fake_start)
    resp = app_client.post("/api/admin/factor-backfill",
                           json={"table": "factors.stock_daily_momentum_close"})
    assert resp.status_code == 200
    cmd = captured["cmd"]
    assert "run_factor_admin.py" in cmd and "backfill" in cmd
    assert "--categories" in cmd and "momentum" in cmd
    assert "--execute" in cmd and "--baseline-ref" in cmd
    assert captured["lock_key"] == "indicators"

    resp = app_client.post("/api/admin/factor-backfill", json={"table": "bad"})
    assert resp.status_code == 400


def test_route_factor_backfill_lock_409(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.daily_jobs._active_jobs", {"indicators": "running"}
    )
    resp = app_client.post("/api/admin/factor-backfill",
                           json={"table": "factors.stock_daily_momentum_close"})
    assert resp.status_code == 409
    assert "已有任务在运行" in resp.get_json()["error"]


def test_route_factor_columns_drop(app_client, monkeypatch):
    captured = {}

    def fake_start(**kw):
        captured.update(kw)
        return {"job_id": "j2", "status": "running", "pipeline": kw["lock_key"], "label": kw["label"]}

    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.start_script_job", fake_start)
    resp = app_client.post("/api/admin/factor-columns/drop",
                           json={"table": "factors.stock_daily_momentum_close", "columns": ["rsi_99"]})
    assert resp.status_code == 200
    cmd = captured["cmd"]
    assert any("drop_factor_columns.py" in c for c in cmd) and "--execute" in cmd
    assert "rsi_99" in cmd and "stock_daily_momentum_close" in cmd

    # 保护列 / 非法表 / 空列
    resp = app_client.post("/api/admin/factor-columns/drop",
                           json={"table": "factors.stock_daily_momentum_close", "columns": ["ts_code"]})
    assert resp.status_code == 400
    resp = app_client.post("/api/admin/factor-columns/drop",
                           json={"table": "bad", "columns": ["x"]})
    assert resp.status_code == 400
    resp = app_client.post("/api/admin/factor-columns/drop",
                           json={"table": "factors.stock_daily_momentum_close", "columns": []})
    assert resp.status_code == 400


def test_route_maintenance_batches_and_delete(app_client, monkeypatch, tmp_path):
    backtests = tmp_path / "backtests"
    (backtests / "b1" / "s1").mkdir(parents=True)
    (backtests / "refresh" / "s2").mkdir(parents=True)
    import quant_research_engine.gui.maintenance as mt
    from quant_research_engine.gui import admin

    admin._cache.clear()
    monkeypatch.setattr(mt, "DEFAULT_BACKTESTS_DIR", backtests)

    resp = app_client.get("/api/admin/maintenance/batches")
    assert resp.status_code == 200
    data = resp.get_json()
    names = {b["name"] for b in data["batches"]}
    assert names == {"b1", "refresh"}

    resp = app_client.post("/api/admin/maintenance/delete", json={"names": ["b1"]})
    assert resp.status_code == 200
    assert resp.get_json()["deleted"] == ["b1"]
    assert not (backtests / "b1").exists()
    assert (backtests / "refresh").is_dir()

    resp = app_client.post("/api/admin/maintenance/delete", json={"names": ["refresh"]})
    assert resp.status_code == 400
    assert "受保护" in resp.get_json()["errors"][0]

    resp = app_client.post("/api/admin/maintenance/delete", json={"names": []})
    assert resp.status_code == 400
    admin._cache.clear()


def test_admin_page_manage_ui(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "维护区" in html
    assert "补全此表" in html
    assert "mt-delete" in html
    # 注册/新建入口已恢复，无暂缓隐藏标记
    assert "TODO-P3c-restore" not in html
