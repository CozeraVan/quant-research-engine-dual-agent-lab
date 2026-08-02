from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

from quant_research_engine.gui import daily_jobs
from quant_research_engine.gui.daily_jobs import (
    PIPELINES,
    get_daily_job,
    journalctl_tail,
    start_daily_job,
)
from quant_research_engine.gui.refresh_registry import (
    list_catalog_strategies,
    load_registry,
    refresh_overview,
    register_strategy,
    save_registry,
    unregister_strategy,
)


# --- refresh_batch registry loader ---


def test_refresh_batch_load_registry_ids(tmp_path):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    try:
        import refresh_batch

        reg = tmp_path / "registry.json"
        # 文件不存在 → ids=None（全量），无 stopped
        assert refresh_batch.load_registry_ids(reg) == {"ids": None, "stopped": set()}
        # 旧格式 {"strategies": [...]} 兼容
        reg.write_text(json.dumps({"strategies": ["b", "a", "a"]}), encoding="utf-8")
        assert refresh_batch.load_registry_ids(reg) == {"ids": ["a", "b"], "stopped": set()}
        reg.write_text(json.dumps({"strategies": []}), encoding="utf-8")
        assert refresh_batch.load_registry_ids(reg)["ids"] is None
        reg.write_text("not json", encoding="utf-8")
        assert refresh_batch.load_registry_ids(reg)["ids"] is None
        # v2：include + stopped
        reg.write_text(json.dumps({"include": ["a", "b"], "stopped": ["b"]}), encoding="utf-8")
        result = refresh_batch.load_registry_ids(reg)
        assert result["ids"] == ["a", "b"]
        assert result["stopped"] == {"b"}
        # v2：include 空 + stopped（全量 − stopped）
        reg.write_text(json.dumps({"include": [], "stopped": ["c"]}), encoding="utf-8")
        result = refresh_batch.load_registry_ids(reg)
        assert result["ids"] is None and result["stopped"] == {"c"}
    finally:
        sys.path.pop(0)


# --- registry 读写 ---


def test_registry_register_unregister(tmp_path):
    reg = tmp_path / "registry.json"
    assert load_registry(reg) == {"include": [], "stopped": []}
    data = register_strategy("mr01a_rsi14_oversold_reversal", reg)
    assert data["include"] == ["mr01a_rsi14_oversold_reversal"]
    data = register_strategy("bo01a_donchian_20_breakout", reg)
    assert data["include"] == ["bo01a_donchian_20_breakout", "mr01a_rsi14_oversold_reversal"]
    # 重复注册去重
    register_strategy("mr01a_rsi14_oversold_reversal", reg)
    assert len(load_registry(reg)["include"]) == 2
    data = unregister_strategy("mr01a_rsi14_oversold_reversal", reg)
    assert data["include"] == ["bo01a_donchian_20_breakout"]
    with pytest.raises(ValueError, match="不能为空"):
        register_strategy("  ", reg)


def test_list_catalog_strategies(tmp_path):
    (tmp_path / "mean_reversion").mkdir()
    (tmp_path / "mean_reversion" / "a.yaml").write_text("x: 1", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("x: 1", encoding="utf-8")
    assert list_catalog_strategies(tmp_path) == ["a", "b"]
    assert list_catalog_strategies(tmp_path / "nope") == []


def test_refresh_overview(tmp_path):
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({
        "last_data_date": "2026-07-17", "last_run_at": "2026-07-19T11:34:18+00:00",
        "last_batch_dir": "/tmp/b", "window_years": 2, "strategy_count": 3, "ok_count": 2,
    }), encoding="utf-8")
    registry = tmp_path / "registry.json"
    save_registry({"include": ["a"], "stopped": ["b"]}, registry)
    catalog = tmp_path / "catalog"
    (catalog / "cat").mkdir(parents=True)
    for sid in ("a", "b", "c"):
        (catalog / "cat" / f"{sid}.yaml").write_text("x: 1", encoding="utf-8")
    delta_root = tmp_path / "delta"
    delta_dir = delta_root / "20260719_cf5f"
    delta_dir.mkdir(parents=True)
    (delta_dir / "delta_report.json").write_text(json.dumps({
        "data_date": "2026-07-17", "strategy_count": 3, "changed": 1,
        "rows": [
            {"strategy_id": "a", "status": "ok", "transition": "unchanged"},
            {"strategy_id": "b", "status": "error", "transition": "ok->error"},
        ],
    }), encoding="utf-8")

    overview = refresh_overview(
        state_path=state_path, registry_path=registry,
        delta_root=delta_root, catalog_dir=catalog,
        backtests_dir=tmp_path / "no-backtests",
    )
    assert overview["state"]["last_data_date"] == "2026-07-17"
    assert overview["registered"] == ["a"]
    assert overview["stopped"] == ["b"]
    assert overview["registry_effective"] is True
    assert overview["mode"] == "registry"
    assert overview["catalog_total"] == 3
    assert overview["unregistered"] == ["b", "c"]
    assert overview["latest_delta"]["changed"] == 1
    by_id = {s["strategy_id"]: s for s in overview["strategies"]}
    assert by_id["a"]["enabled"] is True and by_id["a"]["stopped"] is False
    assert by_id["b"]["enabled"] is False and by_id["b"]["stopped"] is True
    assert by_id["c"]["enabled"] is False  # 注册模式：不在 include 即关闭
    assert by_id["c"]["status"] is None
    assert by_id["a"]["status"] == "ok"
    assert by_id["a"]["excess_return"] is None  # 无结果文件 → —


def test_refresh_overview_full_catalog_mode(tmp_path):
    """注册表为空 → full_catalog 模式（横幅告警的数据源）。"""
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "a.yaml").write_text("x: 1", encoding="utf-8")
    overview = refresh_overview(
        state_path=tmp_path / "state.json",
        registry_path=tmp_path / "registry.json",
        delta_root=tmp_path / "delta",
        catalog_dir=catalog,
    )
    assert overview["mode"] == "full_catalog"
    assert overview["registered"] == []
    assert overview["registry_effective"] is False


def test_admin_page_has_mode_banner(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "mode-banner" in html
    assert "全量模式" in html
    assert "仅注册策略模式" in html


# --- daily jobs ---


@pytest.fixture
def jobs_env(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", tmp_path / "daily-jobs")
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs._active_jobs", {})
    return tmp_path


def _wait(job_id, targets, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = get_daily_job(job_id)
        if record and record["status"] in targets:
            return record
        time.sleep(0.05)
    return get_daily_job(job_id)


def test_daily_job_success_command_construction(jobs_env):
    calls = []

    def runner(cmd, cwd, job_dir):
        calls.append((cmd, cwd))
        return 0

    record = start_daily_job("quant-ts", runner=runner)
    final = _wait(record["job_id"], {"completed", "failed"})
    assert final["status"] == "completed"
    cmd, cwd = calls[0]
    assert cmd == PIPELINES["quant-ts"]["cmd"]
    assert cmd[:3] == ["/home/van/.local/bin/uv", "run", "python"]
    assert "sync_manager.py" in cmd and "--mode" in cmd and "daily" in cmd
    assert cwd == PIPELINES["quant-ts"]["cwd"]


def test_daily_job_failure_marks_failed(jobs_env):
    record = start_daily_job("indicators", runner=lambda cmd, cwd, job_dir: 3)
    final = _wait(record["job_id"], {"failed"})
    assert final["status"] == "failed"
    assert "退出码 3" in final["error"]


def test_daily_job_lock_per_pipeline(jobs_env):
    def slow(cmd, cwd, job_dir):
        time.sleep(0.3)
        return 0

    start_daily_job("quant-ts", runner=slow)
    # 同管线重入 → 409 语义
    with pytest.raises(RuntimeError, match="已有任务在运行"):
        start_daily_job("quant-ts", runner=slow)
    # 不同管线不阻塞
    other = start_daily_job("qre-refresh", runner=slow)
    assert other["status"] == "running"
    deadline = time.time() + 5
    while daily_jobs._active_jobs and time.time() < deadline:
        time.sleep(0.05)
    assert not daily_jobs._active_jobs


def test_daily_job_unknown_pipeline(jobs_env):
    with pytest.raises(KeyError):
        start_daily_job("nope")


# --- journalctl 解析/回退 ---


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def test_journalctl_tail_ok():
    result = journalctl_tail("quant-ts-daily.service", runner=lambda cmd, **kw: _Proc("line1\nline2\n"))
    assert result["source"] == "journalctl"
    assert "line1" in result["text"]


def test_journalctl_tail_fallback_logfile(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "sync.log").write_text("a\nb\nc\n", encoding="utf-8")
    spec = dict(PIPELINES["quant-ts"])
    spec["log_dirs"] = [log_dir]
    monkeypatch.setitem(PIPELINES, "quant-ts", spec)

    result = journalctl_tail("quant-ts-daily.service", runner=lambda cmd, **kw: _Proc("", 1))
    assert result["source"] == "logfile:sync.log"
    assert result["text"].splitlines() == ["a", "b", "c"]


def test_journalctl_tail_no_fallback(monkeypatch):
    spec = dict(PIPELINES["qre-refresh"])
    spec["log_dirs"] = []
    monkeypatch.setitem(PIPELINES, "qre-refresh", spec)
    result = journalctl_tail("qre-refresh.service", runner=lambda cmd, **kw: _Proc("", 1))
    assert result["source"] == "error"
    assert "未找到" in result["text"]


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


def test_route_daily_job_unknown_404(app_client):
    resp = app_client.post("/api/admin/daily-jobs/nope")
    assert resp.status_code == 404


def test_route_daily_job_start_and_409(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs._active_jobs", {"quant-ts": "running-job"})
    resp = app_client.post("/api/admin/daily-jobs/quant-ts")
    assert resp.status_code == 409
    assert "已有任务在运行" in resp.get_json()["error"]


def test_route_daily_job_start_ok(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.daily_jobs._default_runner",
        lambda cmd, cwd, job_dir: 0,
    )
    resp = app_client.post("/api/admin/daily-jobs/qre-refresh")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["pipeline"] == "qre-refresh"
    assert "refresh_batch.py" in data["cmd"]
    final = _wait(data["job_id"], {"completed", "failed"})
    assert final["status"] == "completed"

    status_resp = app_client.get(f"/api/admin/daily-jobs/{data['job_id']}")
    assert status_resp.status_code == 200
    assert status_resp.get_json()["status"] == "completed"


def test_route_daily_job_status_404(app_client):
    resp = app_client.get("/api/admin/daily-jobs/nonexistent")
    assert resp.status_code == 404


def test_route_daily_logs(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.daily_jobs.journalctl_tail",
        lambda unit, **kw: {"source": "journalctl", "text": "log-content"},
    )
    resp = app_client.get("/api/admin/daily-logs/quant-ts")
    assert resp.status_code == 200
    assert resp.get_json()["text"] == "log-content"
    resp = app_client.get("/api/admin/daily-logs/nope")
    assert resp.status_code == 404


def test_route_refresh_register_flow(app_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.refresh_registry as rr

    registry = tmp_path / "registry.json"
    catalog = tmp_path / "catalog"
    catalog.mkdir()
    (catalog / "strat_a.yaml").write_text("x: 1", encoding="utf-8")
    monkeypatch.setattr(rr, "DEFAULT_REGISTRY_PATH", registry)
    monkeypatch.setattr(rr, "CATALOG_DIR", catalog)
    monkeypatch.setattr(rr, "DEFAULT_STATE_PATH", tmp_path / "state.json")
    monkeypatch.setattr(rr, "DEFAULT_DELTA_ROOT", tmp_path / "delta")

    resp = app_client.post("/api/admin/refresh/register", json={"strategy_id": "strat_a"})
    assert resp.status_code == 200
    assert resp.get_json()["registered"] == ["strat_a"]
    assert json.loads(registry.read_text(encoding="utf-8"))["include"] == ["strat_a"]

    resp = app_client.post("/api/admin/refresh/register", json={"strategy_id": "ghost"})
    assert resp.status_code == 400
    assert "不在 catalog" in resp.get_json()["error"]

    resp = app_client.post("/api/admin/refresh/register", json={"strategy_id": ""})
    assert resp.status_code == 400

    resp = app_client.get("/api/admin/refresh")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["registered"] == ["strat_a"]
    assert data["catalog_total"] == 1

    resp = app_client.post("/api/admin/refresh/unregister", json={"strategy_id": "strat_a"})
    assert resp.status_code == 200
    assert resp.get_json()["registered"] == []


def test_admin_page_contains_p3b_ui(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "策略状态" in html
    assert "立即运行" in html
    assert "最近日志" in html
    assert "加入持续更新" in html or "持续更新" in html
