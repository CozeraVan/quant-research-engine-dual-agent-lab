"""QRE-GUI-DEEP-VALIDATE-001：策略→信号池转换器 + deep-validate API 测试。

subprocess 全部 mock（不触 cluster-ashare 真实执行）；转换器与报告解析为
纯函数单测。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quant_research_engine.gui import deep_validate, strategy_create
from quant_research_engine.gui.deep_validate import (
    locate_strategy_yaml,
    parse_report_summary,
    parse_validate_stdout,
    spec_to_conditions,
    used_expression_fields,
)
from quant_research_engine.strategies.spec import StrategySpec

_VALID_YAML = (
    "experiment:\n  name: sc_demo\n  market_profile: ashare_daily_default\n  frequency: daily\n"
    "data:\n  market_fields: [open, high, low, close, pre_close, vol, amount]\n"
    "  factor_fields:\n    rsi_14: factors.stock_daily_momentum_close.rsi_14\n"
    "signal:\n  entry: rsi_14 > 30\n  exit: rsi_14 > 60\n"
    "holding:\n  max_holding_days: 5\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
)

_NO_ENTRY_YAML = (
    "experiment:\n  name: no_entry\ndata:\n  market_fields: [close]\n"
    "  factor_fields: {}\n"
    "signal:\n  entry: ''\n"
    "holding:\n  max_holding_days: 5\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
)

_SAMPLE_MD_GO = """# demo 四关验证报告

## 0. 结论

**GO**。gate1 原始超额 +0.800%（t=3.10）> 0 且 t≥2.0 且正 regime 数 3≥2；gate3 净超额 +0.500%（t=2.40）> 0 且 t≥2.0。

## 1. 方法与信号来源

- 信号 = 逐日池定义

## 3. 四关结果

| 关 | 天数 | 平均超额 | t | NW t | 保守t | 正值率 |
|---|---|---|---|---|---|---|
| gate1 原始超额（close/close） | 500 | +0.800% | 3.10 | 2.90 | 2.20 | 58% |
| gate2 可执行毛超额（T+1开盘） | 500 | +0.600% | 2.50 | 2.30 | 1.80 | 56% |
| **gate3 净超额（并行子组合，主口径）** | 500 | +0.500% | 2.40 | 2.10 | 1.70 | 55% |

## 4. 诚实边界
"""

_SAMPLE_MD_NOGO = _SAMPLE_MD_GO.replace("**GO**", "**NO-GO**")


def _spec(yaml_text: str = _VALID_YAML) -> StrategySpec:
    import yaml as _yaml

    return StrategySpec.from_mapping(_yaml.safe_load(yaml_text))


# --- 转换器（纯函数） ---


def test_used_expression_fields():
    assert used_expression_fields("rsi_14 > 30") == {"rsi_14"}
    assert used_expression_fields("(close > sma_200) & (rsi_2 < 10)") == {
        "close", "sma_200", "rsi_2"}
    assert used_expression_fields("close > close.shift(1)") == {"close"}


def test_spec_to_conditions_basic():
    cond = spec_to_conditions(_spec(), d0="2015-01-01", d1="2026-08-19")
    assert cond["name"] == "sc_demo"
    assert cond["expression"] == "rsi_14 > 30"
    assert cond["factor_fields"] == {
        "rsi_14": "factors.stock_daily_momentum_close.rsi_14"}
    assert cond["used_fields"] == ["rsi_14"]
    assert cond["d0"] == "2015-01-01" and cond["d1"] == "2026-08-19"
    assert "入场条件" in cond["scope_note"]
    assert Path(cond["qre_src"]).name == "src"


def test_spec_to_conditions_no_entry_raises():
    with pytest.raises(ValueError, match="无入场表达式"):
        spec_to_conditions(_spec(_NO_ENTRY_YAML), d0="2015-01-01", d1="2026-01-01")


def test_locate_strategy_yaml_sandbox_first(tmp_path):
    sandbox = tmp_path / "sandbox"
    catalog = tmp_path / "catalog" / "mean_reversion"
    sandbox.mkdir(parents=True)
    catalog.mkdir(parents=True)
    (sandbox / "sc_demo.yaml").write_text(_VALID_YAML, encoding="utf-8")
    (catalog / "sc_demo.yaml").write_text(
        _VALID_YAML.replace("rsi_14 > 30", "rsi_14 > 50"), encoding="utf-8")
    text = locate_strategy_yaml("sc_demo", sandbox_dir=sandbox,
                                catalog_dir=catalog.parent)
    assert "rsi_14 > 30" in text  # 沙箱优先


def test_locate_strategy_yaml_catalog_by_stem_and_experiment(tmp_path):
    catalog = tmp_path / "catalog" / "trend_following"
    catalog.mkdir(parents=True)
    (catalog / "tf_x.yaml").write_text(_VALID_YAML, encoding="utf-8")
    # 文件 stem 匹配
    assert locate_strategy_yaml("tf_x", sandbox_dir=tmp_path / "sb",
                                catalog_dir=catalog.parent) is not None
    # experiment.name 匹配（文件名不同）
    assert locate_strategy_yaml("sc_demo", sandbox_dir=tmp_path / "sb",
                                catalog_dir=catalog.parent) is not None
    assert locate_strategy_yaml("nobody", sandbox_dir=tmp_path / "sb",
                                catalog_dir=catalog.parent) is None


# --- 报告解析（纯函数） ---


def test_parse_report_summary_go():
    summary = parse_report_summary(_SAMPLE_MD_GO)
    assert summary["verdict"] == "GO"
    assert "gate3 净超额" in summary["conclusion"]
    gates = {g["gate"]: g for g in summary["gates"]}
    assert len(gates) == 3
    g3 = next(g for g in summary["gates"] if g["gate"].startswith("gate3"))
    assert g3["mean_excess"] == "+0.500%" and g3["t"] == "2.40"


def test_parse_report_summary_nogo():
    assert parse_report_summary(_SAMPLE_MD_NOGO)["verdict"] == "NO-GO"


def test_parse_validate_stdout():
    out = parse_validate_stdout(
        "[fv] 信号 x：10 个信号日\n[fv] 最终结论: GO\n"
        "[fv] 报告: /tmp/x_四关验证报告.md\n")
    assert out["verdict"] == "GO"
    assert out["report_path"] == "/tmp/x_四关验证报告.md"


# --- job worker（mock subprocess） ---


def _fake_subproc_factory(tmp_path: Path, pool_rc=0, val_rc=0):
    report = tmp_path / "qre_sc_demo_四关验证报告.md"
    report.write_text(_SAMPLE_MD_GO, encoding="utf-8")
    calls = []

    def fake_run(cmd, cwd=None, capture_output=None, text=None, timeout=None):
        calls.append(list(cmd))
        if "pool_from_conditions.py" in cmd[1]:
            stdout = ("[pool] sc_demo：100 个信号日，5000 条记录，"
                      "平均 50 只/日 → /tmp/pool.parquet\n")
            return subprocess.CompletedProcess(cmd, pool_rc, stdout, "")
        stdout = (f"[fv] 最终结论: GO\n[fv] 报告: {report}\n")
        return subprocess.CompletedProcess(cmd, val_rc, stdout, "")

    return fake_run, calls


def _run_job_sync(monkeypatch, tmp_path, subproc):
    """用同步假 starter 跑 start_deep_validate_job，返回 (record, job_dir)。"""
    jobs_dir = tmp_path / "daily-jobs"
    monkeypatch.setattr(
        "quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", jobs_dir)
    captured = {}

    def fake_starter(*, lock_key, label, cmd, cwd, runner):
        job_dir = jobs_dir / "job-1"
        job_dir.mkdir(parents=True)
        code = runner(cmd, cwd, job_dir)
        captured.update(lock_key=lock_key, label=label, cmd=cmd)
        return {"job_id": "job-1", "status": "completed" if code == 0 else "failed"}

    record = deep_validate.start_deep_validate_job(
        "sc_demo", _spec(), d0="2020-01-01", d1="2021-01-01",
        work_dir=tmp_path / "dv", job_starter=fake_starter, subproc=subproc)
    return record, jobs_dir / "job-1", captured


def test_start_deep_validate_job_happy(monkeypatch, tmp_path):
    fake_run, calls = _fake_subproc_factory(tmp_path)
    record, job_dir, captured = _run_job_sync(monkeypatch, tmp_path, fake_run)
    assert record["ok"] and record["job_id"] == "job-1"
    assert captured["lock_key"] == "deep-validate:sc_demo"
    # 两段 subprocess：先 pool 后 validate；pool 脚本用 cluster venv 解释器
    assert len(calls) == 2
    assert "pool_from_conditions.py" in calls[0][1]
    assert "validate_factor.py" in calls[1][1]
    assert "--pool-parquet" in calls[1]
    # 条件 JSON 已落盘且口径注明
    cond = json.loads((tmp_path / "dv" / "conditions.json").read_text())
    assert cond["expression"] == "rsi_14 > 30"
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is True
    assert result["verdict"] == "GO"
    assert result["pool"]["signal_days"] == 100
    assert result["report_path"].endswith("四关验证报告.md")
    assert any(g["gate"].startswith("gate3") for g in result["gates"])


def test_start_deep_validate_job_pool_failure(monkeypatch, tmp_path):
    fake_run, _ = _fake_subproc_factory(tmp_path, pool_rc=1)
    record, job_dir, _ = _run_job_sync(monkeypatch, tmp_path, fake_run)
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert record["status"] == "failed"
    assert result["ok"] is False and "信号池生成失败" in result["error"]


def test_start_deep_validate_job_validate_failure(monkeypatch, tmp_path):
    fake_run, _ = _fake_subproc_factory(tmp_path, val_rc=1)
    record, job_dir, _ = _run_job_sync(monkeypatch, tmp_path, fake_run)
    result = json.loads((job_dir / "result.json").read_text(encoding="utf-8"))
    assert result["ok"] is False and "四关验证执行失败" in result["error"]


def test_start_deep_validate_job_bad_dates(tmp_path):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        deep_validate.start_deep_validate_job("sc_demo", _spec(), d0="2020/01/01")
    with pytest.raises(ValueError, match="晚于"):
        deep_validate.start_deep_validate_job(
            "sc_demo", _spec(), d0="2021-01-01", d1="2020-01-01")


# --- API ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    sandbox = tmp_path / "sandbox"
    catalog = tmp_path / "catalog"
    jobs_dir = tmp_path / "daily-jobs"
    monkeypatch.setattr(strategy_create, "DEFAULT_SANDBOX_DIR", sandbox)
    monkeypatch.setattr(deep_validate, "CATALOG_DIR", catalog)
    monkeypatch.setattr(
        "quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", jobs_dir)
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._default_column_lookup",
        lambda db_url=None: (lambda table: {"rsi_14"}),
    )
    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client, sandbox, catalog, jobs_dir


def _seed_sandbox(sandbox: Path) -> None:
    sandbox.mkdir(parents=True, exist_ok=True)
    (sandbox / "sc_demo.yaml").write_text(_VALID_YAML, encoding="utf-8")


def test_api_deep_validate_not_found(app_client):
    client, _, _, _ = app_client
    resp = client.post("/api/strategies/nobody/deep-validate", json={})
    assert resp.status_code == 404
    assert resp.get_json()["code"] == "not_found"


def test_api_deep_validate_no_entry(app_client):
    client, sandbox, _, _ = app_client
    sandbox.mkdir(parents=True)
    (sandbox / "no_entry.yaml").write_text(_NO_ENTRY_YAML, encoding="utf-8")
    resp = client.post("/api/strategies/no_entry/deep-validate", json={})
    assert resp.status_code == 400
    assert resp.get_json()["code"] == "no_entry_signal"


def test_api_deep_validate_cluster_unavailable(app_client, monkeypatch):
    client, sandbox, _, _ = app_client
    _seed_sandbox(sandbox)
    monkeypatch.setattr(deep_validate, "cluster_available",
                        lambda: "cluster-ashare 解释器不存在: /x")
    resp = client.post("/api/strategies/sc_demo/deep-validate", json={})
    assert resp.status_code == 500
    assert resp.get_json()["code"] == "cluster_unavailable"


def test_api_deep_validate_missing_factors(app_client, monkeypatch, tmp_path):
    client, sandbox, _, _ = app_client
    _seed_sandbox(sandbox)
    monkeypatch.setattr(deep_validate, "cluster_available", lambda: None)
    monkeypatch.setattr(
        "quant_research_engine.gui.nl_compiler._default_column_lookup",
        lambda db_url=None: (lambda table: set()),  # rsi_14 不存在
    )
    queue_path = tmp_path / "queue.json"
    # app.py 在路由内 from ... import DEFAULT_QUEUE_PATH，打源模块即可
    import quant_research_engine.strategies.factor_request_queue as frq
    monkeypatch.setattr(frq, "DEFAULT_QUEUE_PATH", queue_path)
    resp = client.post("/api/strategies/sc_demo/deep-validate", json={})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data["code"] == "missing_factors"
    assert data["missing_factors"] == ["rsi_14"]
    assert queue_path.exists()  # 已入补因子队列


def test_api_deep_validate_submit_and_poll(app_client, monkeypatch, tmp_path):
    client, sandbox, _, jobs_dir = app_client
    _seed_sandbox(sandbox)
    monkeypatch.setattr(deep_validate, "cluster_available", lambda: None)

    def fake_start(name, spec, *, d0=None, d1=None, **kwargs):
        job_dir = jobs_dir / "job-x"
        job_dir.mkdir(parents=True)
        (job_dir / "status.json").write_text(json.dumps({
            "job_id": "job-x", "status": "completed",
            "created_at": "2026-08-20T00:00:00+00:00"}), encoding="utf-8")
        (job_dir / "result.json").write_text(json.dumps({
            "ok": True, "verdict": "NO-GO",
            "report_path": "/cluster/outputs/qre_sc_demo_四关验证报告.md",
            "gates": [{"gate": "gate3 净超额", "mean_excess": "-0.300%",
                       "t": "-1.50", "pos_rate": "44%"}],
        }, ensure_ascii=False), encoding="utf-8")
        return {"ok": True, "job_id": "job-x", "status": "running",
                "strategy": name, "d0": d0 or "2015-01-01",
                "d1": d1 or "2026-08-20"}

    monkeypatch.setattr(deep_validate, "start_deep_validate_job", fake_start)
    resp = client.post("/api/strategies/sc_demo/deep-validate",
                       json={"d0": "2020-01-01"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] and data["job_id"] == "job-x"
    assert data["d0"] == "2020-01-01"  # 请求参数覆盖默认区间

    poll = client.get("/api/strategies/sc_demo/deep-validate/job-x")
    assert poll.status_code == 200
    pdata = poll.get_json()
    assert pdata["status"] == "completed"
    assert pdata["result"]["verdict"] == "NO-GO"
    assert pdata["result"]["report_path"].endswith("四关验证报告.md")

    missing = client.get("/api/strategies/sc_demo/deep-validate/job-none")
    assert missing.status_code == 404


def test_api_deep_validate_conflict(app_client, monkeypatch):
    client, sandbox, _, _ = app_client
    _seed_sandbox(sandbox)
    monkeypatch.setattr(deep_validate, "cluster_available", lambda: None)

    def busy(*args, **kwargs):
        raise RuntimeError("「深度验证 sc_demo」已有任务在运行")

    monkeypatch.setattr(deep_validate, "start_deep_validate_job", busy)
    resp = client.post("/api/strategies/sc_demo/deep-validate", json={})
    assert resp.status_code == 409
