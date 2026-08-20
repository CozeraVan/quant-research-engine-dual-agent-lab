"""GUI 新因子创建闭环（P2）测试：NL 生成 / 静态安全 / 查重 / 沙箱 / 冒烟 / 晋升 / API。

不真连 DB、不真跑 backfill：LLM 走注入的 http_post，冒烟/晋升子进程与
job_starter 全部注入假实现，indicators 目录用 tmp 假树。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from quant_research_engine.gui import factor_create
from quant_research_engine.gui.factor_nl_compiler import (
    check_code_safety,
    generate_factor_code,
    normalize_meta,
    parse_llm_output,
)
from quant_research_engine.gui.nl_compiler import ENV_API_KEY, ENV_BASE_URL, ENV_MODEL

# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

VALID_CODE = (
    "import pandas as pd\n"
    "import pandas_ta as ta\n"
    "from core.factor_base import FactorBase\n"
    "\n\n"
    "class ROCFactor(FactorBase):\n"
    '    """Rate of Change (ROC)"""\n'
    "    def __init__(self, db_manager):\n"
    '        super().__init__(db_manager); self.indicator_name = "roc"; self.category = "momentum"\n'
    "    def calculate_logic(self, df, p=None):\n"
    "        series = self.get_price_series(df)\n"
    "        return ta.roc(series, length=p) if p else ta.roc(series)\n"
)

LLM_OK_OUTPUT = (
    "<<<CODE>>>\n```python\n" + VALID_CODE + "```\n<<<META>>>\n"
    "name: roc\ncategory: momentum\ncolumn: close\nperiods: [25]\n"
)


def _llm_env() -> dict[str, str]:
    return {ENV_BASE_URL: "http://llm.local/v1", ENV_API_KEY: "k", ENV_MODEL: "m"}


def _http_ok(content: str):
    def http_post(url, headers, payload, timeout):
        assert payload["messages"][0]["role"] == "system"
        assert "FactorBase" in payload["messages"][0]["content"]
        return {"choices": [{"message": {"content": content}}]}

    return http_post


def _make_repo(tmp_path: Path) -> Path:
    """构造假 indicators 目录树：factors/ + config/factors.yaml + sandbox/factors/。"""
    repo = tmp_path / "indicators"
    (repo / "factors").mkdir(parents=True)
    (repo / "sandbox" / "factors").mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "config" / "factors.yaml").write_text(
        "factors:\n"
        "  - name: sma\n"
        "    category: overlap\n"
        "    column: close\n"
        "    periods: [5, 20]\n",
        encoding="utf-8",
    )
    return repo


def _pgrep_idle():
    return subprocess.CompletedProcess(args=["pgrep"], returncode=1, stdout="", stderr="")


def _pgrep_busy():
    return subprocess.CompletedProcess(
        args=["pgrep"], returncode=0, stdout="1234 python run_factor_admin.py backfill\n", stderr=""
    )


# ---------------------------------------------------------------------------
# 静态安全检查
# ---------------------------------------------------------------------------


def test_safety_accepts_valid_factor():
    assert check_code_safety(VALID_CODE) == []


def test_safety_rejects_import_os():
    code = VALID_CODE.replace("import pandas as pd", "import os\nimport pandas as pd")
    violations = check_code_safety(code)
    assert any("import os" in v for v in violations)


def test_safety_rejects_from_import_os_path():
    assert any("from-import" in v for v in check_code_safety("from os import path\n"))
    # core.factor_base 是唯一允许的项目内 from-import
    assert check_code_safety("from core.factor_base import FactorBase\n") == []
    assert any("from-import" in v for v in check_code_safety("from core.db_manager import DBManager\n"))


def test_safety_rejects_dunder_import_and_open():
    assert any("__import__" in v for v in check_code_safety("__import__('os')\n"))
    assert any("open()" in v for v in check_code_safety("open('/etc/passwd')\n"))
    assert any("eval()" in v for v in check_code_safety("eval('1+1')\n"))


def test_safety_rejects_dunder_attribute():
    assert any("dunder" in v for v in check_code_safety("x.__class__.__globals__\n"))


def test_safety_rejects_syntax_error():
    assert any("语法错误" in v for v in check_code_safety("def broken(:\n"))


# ---------------------------------------------------------------------------
# LLM 输出解析 / 生成
# ---------------------------------------------------------------------------


def test_parse_llm_output_ok():
    parsed = parse_llm_output(LLM_OK_OUTPUT)
    assert "class ROCFactor" in parsed["code"]
    assert parsed["meta"]["name"] == "roc"
    assert parsed["meta"]["periods"] == [25]


def test_parse_llm_output_error_marker():
    with pytest.raises(ValueError, match="人工通道"):
        parse_llm_output("<<<ERROR>>>该需求超出模板因子范围，请走人工通道：需要财务数据")


def test_parse_llm_output_missing_meta():
    with pytest.raises(ValueError, match="META"):
        parse_llm_output("<<<CODE>>>\n" + VALID_CODE)


def test_generate_factor_code_ok():
    result = generate_factor_code("ROC 变动率，周期 25", http_post=_http_ok(LLM_OK_OUTPUT), env=_llm_env())
    assert result["ok"] is True
    assert "ROCFactor" in result["code"]
    assert result["meta"] == {"name": "roc", "category": "momentum", "column": "close", "periods": [25]}


def test_generate_factor_code_not_configured():
    result = generate_factor_code("ROC", env={})
    assert result["ok"] is False and result["code"] == "not_configured"


def test_generate_factor_code_out_of_scope():
    raw = "<<<ERROR>>>该需求超出模板因子范围，请走人工通道：需要横截面排名"
    result = generate_factor_code("全市场排名因子", http_post=_http_ok(raw), env=_llm_env())
    assert result["ok"] is False and result["code"] == "out_of_scope"
    assert "人工通道" in result["error"]


def test_generate_factor_code_unsafe_output():
    raw = "<<<CODE>>>\nimport os\n" + VALID_CODE + "<<<META>>>\nname: roc\ncategory: momentum\n"
    result = generate_factor_code("ROC", http_post=_http_ok(raw), env=_llm_env())
    assert result["ok"] is False and result["code"] == "unsafe"
    assert "import os" in result["error"]


def test_generate_factor_code_empty_description():
    assert generate_factor_code("  ", env=_llm_env())["code"] == "empty"


def test_normalize_meta_defaults():
    meta = normalize_meta({"name": " ROC ", "category": "Momentum"})
    assert meta["name"] == "roc" and meta["category"] == "momentum"
    assert meta["column"] == "close" and meta["periods"] == [None]


# ---------------------------------------------------------------------------
# 查重
# ---------------------------------------------------------------------------


def test_duplicate_hit_by_db_column():
    tables = {"stock_daily_momentum_close": ["ts_code", "trade_date", "roc_25", "rsi_14"]}
    conflict = factor_create.check_factor_duplicate("roc", "momentum", "close", [25], tables_columns=tables, config_path=Path("/nonexistent.yaml"))
    assert conflict and "roc_25" in conflict


def test_duplicate_no_false_positive_same_suffix():
    # 不同指标同周期不应误判（sma_20 存在不影响 ema 20）
    tables = {"stock_daily_overlap_close": ["ts_code", "trade_date", "sma_20"]}
    conflict = factor_create.check_factor_duplicate("ema", "overlap", "close", [20], tables_columns=tables, config_path=Path("/nonexistent.yaml"))
    assert conflict is None


def test_duplicate_hit_by_config(tmp_path):
    repo = _make_repo(tmp_path)
    conflict = factor_create.check_factor_duplicate(
        "sma", "overlap", "close", [60, 20], tables_columns=None, config_path=repo / "config" / "factors.yaml"
    )
    assert conflict and "sma" in conflict


def test_duplicate_miss(tmp_path):
    repo = _make_repo(tmp_path)
    tables = {"stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14"]}
    conflict = factor_create.check_factor_duplicate(
        "roc", "momentum", "close", [25], tables_columns=tables, config_path=repo / "config" / "factors.yaml"
    )
    assert conflict is None


# ---------------------------------------------------------------------------
# 沙箱读写
# ---------------------------------------------------------------------------


def test_sandbox_save_list_discard(tmp_path):
    repo = _make_repo(tmp_path)
    saved = factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    assert saved["ok"] is True
    assert (repo / "sandbox" / "factors" / "roc_factor.py").exists()

    listing = factor_create.list_sandbox(repo=repo)
    assert [e["name"] for e in listing] == ["roc"]

    discarded = factor_create.discard_factor("roc", repo=repo)
    assert discarded["ok"] is True
    assert factor_create.list_sandbox(repo=repo) == []


def test_sandbox_save_rejects_unsafe(tmp_path):
    repo = _make_repo(tmp_path)
    result = factor_create.save_factor_to_sandbox("import os\n", "evil", repo=repo)
    assert result["ok"] is False and result["code"] == "unsafe"


def test_sandbox_save_rejects_bad_name(tmp_path):
    repo = _make_repo(tmp_path)
    assert factor_create.save_factor_to_sandbox(VALID_CODE, "ROC!", repo=repo)["code"] == "invalid_name"


# ---------------------------------------------------------------------------
# 冒烟（子进程 mock）
# ---------------------------------------------------------------------------


def _smoke_runner(payload: dict, returncode: int = 0):
    def runner(cmd, cwd, timeout):
        assert "sandbox/smoke_factor.py" in cmd
        return subprocess.CompletedProcess(
            args=cmd, returncode=returncode, stdout="一些日志\n" + json.dumps(payload, ensure_ascii=False) + "\n", stderr=""
        )

    return runner


def test_run_smoke_ok(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    payload = {"ok": True, "indicator_name": "roc", "columns": ["roc_25"], "rows": 400, "errors": []}
    result = factor_create.run_smoke("roc", params=[25], repo=repo, runner=_smoke_runner(payload))
    assert result["ok"] is True and result["columns"] == ["roc_25"]


def test_run_smoke_parse_failure(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)

    def bad_runner(cmd, cwd, timeout):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="boom", stderr="traceback...")

    result = factor_create.run_smoke("roc", repo=repo, runner=bad_runner)
    assert result["ok"] is False and "无法解析" in result["error"]


def test_run_smoke_missing_sandbox(tmp_path):
    repo = _make_repo(tmp_path)
    result = factor_create.run_smoke("ghost", repo=repo, runner=_smoke_runner({}))
    assert result["ok"] is False and "不存在" in result["error"]


# ---------------------------------------------------------------------------
# 异步冒烟（缺口 3）：start_smoke_job 复用 start_script_job 调度协议
# ---------------------------------------------------------------------------


def _sync_job_starter(captured: dict):
    """假 job_starter：同步执行 worker（daily_jobs runner 协议），返回 job 记录。"""

    def starter(*, lock_key, label, cmd, cwd, runner):
        captured.update(lock_key=lock_key, label=label, cmd=cmd, cwd=cwd)
        job_dir = captured["job_root"] / "job-1"
        job_dir.mkdir(parents=True, exist_ok=True)
        exit_code = runner(cmd, cwd, job_dir)
        return {"job_id": "job-1", "status": "completed" if exit_code == 0 else "failed"}

    return starter


def test_start_smoke_job_ok_writes_sidecar_and_result(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    payload = {"ok": True, "indicator_name": "roc", "factor_class": "ROCFactor",
               "category": "momentum", "code": "600519.SH", "columns": ["roc_25"], "rows": 400, "errors": []}
    captured: dict = {"job_root": tmp_path / "jobs"}
    result = factor_create.start_smoke_job(
        "roc", params=[25], repo=repo,
        smoke_runner=_smoke_runner(payload), job_starter=_sync_job_starter(captured),
    )
    assert result["ok"] is True and result["job_id"] == "job-1" and result["status"] == "running"
    assert captured["lock_key"] == "factor-smoke:roc"
    # 终态：sidecar completed + job_dir/result.json
    sidecar = json.loads((repo / "sandbox" / "factors" / "roc.smoke.json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "completed"
    assert sidecar["result"]["columns"] == ["roc_25"]
    job_result = json.loads((captured["job_root"] / "job-1" / "result.json").read_text(encoding="utf-8"))
    assert job_result["ok"] is True and job_result["rows"] == 400


def test_start_smoke_job_failure_marks_sidecar_failed(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)

    def bad_runner(cmd, cwd, timeout):
        return subprocess.CompletedProcess(args=cmd, returncode=2, stdout="boom", stderr="traceback...")

    captured: dict = {"job_root": tmp_path / "jobs"}
    factor_create.start_smoke_job(
        "roc", repo=repo, smoke_runner=bad_runner, job_starter=_sync_job_starter(captured)
    )
    sidecar = json.loads((repo / "sandbox" / "factors" / "roc.smoke.json").read_text(encoding="utf-8"))
    assert sidecar["status"] == "failed"
    assert "无法解析" in sidecar["error"]
    job_result = json.loads((captured["job_root"] / "job-1" / "result.json").read_text(encoding="utf-8"))
    assert job_result["ok"] is False


def test_start_smoke_job_missing_sandbox(tmp_path):
    repo = _make_repo(tmp_path)
    result = factor_create.start_smoke_job("ghost", repo=repo, job_starter=_fake_job_starter)
    assert result["ok"] is False and result["code"] == "not_found"


def test_discard_factor_removes_smoke_sidecar(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    _write_smoke_ok(repo, "roc")
    discarded = factor_create.discard_factor("roc", repo=repo)
    assert discarded["ok"] is True
    assert not (repo / "sandbox" / "factors" / "roc.smoke.json").exists()


# ---------------------------------------------------------------------------
# config 追加 / 晋升
# ---------------------------------------------------------------------------


def test_append_config_entry_periods_and_backup(tmp_path):
    repo = _make_repo(tmp_path)
    config_path = repo / "config" / "factors.yaml"
    backup = factor_create.append_config_entry(
        config_path, name="roc", category="momentum", column="close", params=[25]
    )
    text = config_path.read_text(encoding="utf-8")
    assert "  - name: roc" in text and "periods: [25]" in text
    assert backup.exists()


def test_append_config_entry_params_list(tmp_path):
    repo = _make_repo(tmp_path)
    config_path = repo / "config" / "factors.yaml"
    factor_create.append_config_entry(
        config_path, name="kama", category="overlap", column="close", params=[[10, 2, 30]]
    )
    assert "      - [10, 2, 30]" in config_path.read_text(encoding="utf-8")


def test_append_config_entry_null_params(tmp_path):
    repo = _make_repo(tmp_path)
    config_path = repo / "config" / "factors.yaml"
    factor_create.append_config_entry(config_path, name="apo", category="momentum", column="close", params=[None])
    assert "    params: [null]" in config_path.read_text(encoding="utf-8")


def _write_smoke_ok(repo: Path, name: str) -> None:
    """写入一条「冒烟通过」sidecar（晋升状态闸的前置条件）。"""
    factor_create._write_smoke_sidecar(
        name,
        {"name": name, "status": "completed", "result": {"ok": True}, "finished_at": "2026-08-20T00:00:00+00:00"},
        repo=repo,
    )


def _fake_job_starter(**kwargs):
    return {"job_id": "job-test-1", "status": "running", **kwargs}


def test_promote_rejects_when_admin_busy(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    _write_smoke_ok(repo, "roc")
    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_busy, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "admin_busy"
    assert not (repo / "factors" / "roc_factor.py").exists()


def test_promote_blocked_without_smoke(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "smoke_not_passed"
    assert "冒烟" in result["error"]
    assert not (repo / "factors" / "roc_factor.py").exists()


def test_promote_blocked_when_smoke_failed(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    factor_create._write_smoke_sidecar(
        "roc", {"name": "roc", "status": "failed", "error": "语法错误"}, repo=repo
    )
    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "smoke_not_passed"


def test_promote_force_bypasses_smoke_gate(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo,
        pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter, force=True,
    )
    assert result["ok"] is True and result["forced"] is True
    assert (repo / "factors" / "roc_factor.py").exists()


def test_promote_ok_copies_appends_starts_job(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    _write_smoke_ok(repo, "roc")
    started: list[dict] = []

    def starter(**kwargs):
        started.append(kwargs)
        return {"job_id": "job-xyz", "status": "running"}

    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=starter
    )
    assert result["ok"] is True and result["job_id"] == "job-xyz", result
    assert (repo / "factors" / "roc_factor.py").read_text(encoding="utf-8") == VALID_CODE
    text = (repo / "config" / "factors.yaml").read_text(encoding="utf-8")
    assert "  - name: roc" in text and "periods: [25]" in text
    assert started and started[0]["lock_key"] == "indicators"
    assert "validate" in started[0]["cmd"][-1] and "backfill" in started[0]["cmd"][-1]


def test_promote_rejects_existing_module(tmp_path):
    repo = _make_repo(tmp_path)
    (repo / "factors" / "roc_factor.py").write_text("# existing\n", encoding="utf-8")
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    _write_smoke_ok(repo, "roc")
    result = factor_create.promote_factor(
        "roc", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "duplicate_name"


def test_promote_rejects_missing_sandbox(tmp_path):
    repo = _make_repo(tmp_path)
    result = factor_create.promote_factor(
        "ghost", "momentum", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "not_found"


def test_promote_rejects_bad_category(tmp_path):
    repo = _make_repo(tmp_path)
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)
    _write_smoke_ok(repo, "roc")
    result = factor_create.promote_factor(
        "roc", "weird", "close", [25], repo=repo, pgrep_runner=_pgrep_idle, job_starter=_fake_job_starter
    )
    assert result["ok"] is False and result["code"] == "invalid_category"


def test_check_no_admin_running_idle_and_busy():
    assert factor_create.check_no_admin_running(_pgrep_idle) is None
    assert "run_factor_admin" in factor_create.check_no_admin_running(_pgrep_busy)


# ---------------------------------------------------------------------------
# API 层（Flask test client）
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def test_api_nl_generate(client, monkeypatch):
    monkeypatch.setenv(ENV_BASE_URL, "http://llm.local/v1")
    monkeypatch.setenv(ENV_API_KEY, "k")
    monkeypatch.setenv(ENV_MODEL, "m")
    from quant_research_engine.gui import factor_nl_compiler

    def fake_call_llm(description, config, *, http_post=None, timeout=60, system_prompt=None):
        assert system_prompt and "FactorBase" in system_prompt
        return LLM_OK_OUTPUT

    monkeypatch.setattr(factor_nl_compiler, "call_llm", fake_call_llm)
    resp = client.post("/api/factor-create/nl-generate", json={"description": "ROC 变动率，周期 25"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True and data["meta"]["name"] == "roc"


def test_api_nl_generate_empty(client):
    resp = client.post("/api/factor-create/nl-generate", json={"description": ""})
    assert resp.status_code == 400


def test_api_check_unsafe(client):
    resp = client.post(
        "/api/factor-create/check",
        json={"code": "import os\n", "name": "evil", "category": "momentum", "column": "close", "periods": [5]},
    )
    data = resp.get_json()
    assert data["ok"] is False and any("import os" in v for v in data["violations"])


def test_api_check_duplicate_with_db_down(client, monkeypatch, tmp_path):
    from quant_research_engine.gui import factor_wizard

    monkeypatch.setattr(
        factor_wizard, "load_factor_tables_columns", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down"))
    )
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("QRE_INDICATORS_REPO", str(repo))
    resp = client.post(
        "/api/factor-create/check",
        json={"code": VALID_CODE, "name": "sma", "category": "overlap", "column": "close", "periods": [20]},
    )
    data = resp.get_json()
    assert data["ok"] is False
    assert "sma" in data["duplicate"]
    assert "因子库不可用" in data["warning"]


def test_api_smoke_submits_async_job(client, monkeypatch):
    """POST /api/factor-create/smoke 改为异步：提交即返回 job_id。"""
    monkeypatch.setattr(
        factor_create, "save_factor_to_sandbox", lambda code, name, **kw: {"ok": True, "name": name, "path": "/tmp/x.py"}
    )
    captured: dict = {}

    def fake_start(name, **kwargs):
        captured.update(name=name, params=kwargs.get("params"))
        return {"ok": True, "job_id": "job-1", "status": "running", "name": name}

    monkeypatch.setattr(factor_create, "start_smoke_job", fake_start)
    resp = client.post(
        "/api/factor-create/smoke",
        json={"code": VALID_CODE, "name": "roc", "category": "momentum", "column": "close", "periods": [25]},
    )
    data = resp.get_json()
    assert resp.status_code == 200
    assert data["ok"] is True and data["job_id"] == "job-1" and data["status"] == "running"
    assert captured["params"] == [25]


def test_api_smoke_lock_conflict_409(client, monkeypatch):
    monkeypatch.setattr(
        factor_create, "save_factor_to_sandbox", lambda code, name, **kw: {"ok": True, "name": name}
    )

    def busy(name, **kwargs):
        raise RuntimeError("「新因子冒烟 roc」已有任务在运行，请等待完成后再触发")

    monkeypatch.setattr(factor_create, "start_smoke_job", busy)
    resp = client.post(
        "/api/factor-create/smoke",
        json={"code": VALID_CODE, "name": "roc", "category": "momentum", "column": "close"},
    )
    assert resp.status_code == 409


def test_api_smoke_status_polling(client, monkeypatch, tmp_path):
    """GET /api/factor-create/smoke/<job_id>：running → 终态读 result.json。"""
    from quant_research_engine.gui import daily_jobs

    jobs_dir = tmp_path / "daily-jobs"
    monkeypatch.setattr(daily_jobs, "DAILY_JOBS_DIR", jobs_dir)

    job_dir = jobs_dir / "job-1"
    job_dir.mkdir(parents=True)
    (job_dir / "status.json").write_text(json.dumps({
        "job_id": "job-1", "status": "running", "label": "新因子冒烟 roc",
        "created_at": "2026-08-20T00:00:00+00:00",
    }), encoding="utf-8")
    resp = client.get("/api/factor-create/smoke/job-1")
    data = resp.get_json()
    assert resp.status_code == 200 and data["status"] == "running" and "result" not in data

    # 终态：status failed + result.json 带错误详情
    (job_dir / "status.json").write_text(json.dumps({
        "job_id": "job-1", "status": "failed", "error": "脚本退出码 1（详见日志）",
        "created_at": "2026-08-20T00:00:00+00:00",
    }), encoding="utf-8")
    (job_dir / "result.json").write_text(json.dumps({
        "ok": False, "error": "冒烟输出无法解析（exit=2）：boom",
    }), encoding="utf-8")
    resp = client.get("/api/factor-create/smoke/job-1")
    data = resp.get_json()
    assert data["status"] == "failed"
    assert data["result"]["ok"] is False and "无法解析" in data["result"]["error"]

    assert client.get("/api/factor-create/smoke/ghost").status_code == 404


def test_api_promote(client, monkeypatch):
    captured: dict = {}

    def fake_promote(name, category, column, params, **kwargs):
        captured.update(name=name, category=category, column=column, params=params)
        return {"ok": True, "name": name, "path": "/repo/factors/roc_factor.py", "job_id": "job-1"}

    monkeypatch.setattr(factor_create, "promote_factor", fake_promote)
    resp = client.post(
        "/api/factor-create/promote",
        json={"name": "roc", "category": "momentum", "column": "close", "periods": [25]},
    )
    data = resp.get_json()
    assert data["ok"] is True and data["job_id"] == "job-1"
    assert captured["params"] == [25]


def test_api_promote_busy_conflict(client, monkeypatch):
    monkeypatch.setattr(
        factor_create,
        "promote_factor",
        lambda *a, **k: {"ok": False, "code": "admin_busy", "error": "有任务在跑"},
    )
    resp = client.post(
        "/api/factor-create/promote",
        json={"name": "roc", "category": "momentum", "column": "close", "periods": [25]},
    )
    assert resp.status_code == 409


def test_api_promote_smoke_gate_409_and_force(client, monkeypatch):
    """晋升状态闸：smoke_not_passed → 409；force=true 透传并注明。"""
    seen: dict = {}

    def fake_promote(name, category, column, params, **kwargs):
        seen["force"] = kwargs.get("force")
        if not kwargs.get("force"):
            return {"ok": False, "code": "smoke_not_passed", "error": "未通过冒烟测试：请先运行冒烟测试"}
        return {"ok": True, "name": name, "path": "/repo/factors/roc_factor.py", "job_id": "j", "forced": True}

    monkeypatch.setattr(factor_create, "promote_factor", fake_promote)
    payload = {"name": "roc", "category": "momentum", "column": "close", "periods": [25]}
    resp = client.post("/api/factor-create/promote", json=payload)
    assert resp.status_code == 409
    assert resp.get_json()["code"] == "smoke_not_passed"

    resp = client.post("/api/factor-create/promote", json={**payload, "force": True})
    data = resp.get_json()
    assert resp.status_code == 200 and data["forced"] is True
    assert "force" in data["warning"]
    assert seen["force"] is True


def test_api_sandbox_list_and_delete(client, monkeypatch, tmp_path):
    repo = _make_repo(tmp_path)
    monkeypatch.setenv("QRE_INDICATORS_REPO", str(repo))
    factor_create.save_factor_to_sandbox(VALID_CODE, "roc", repo=repo)

    resp = client.get("/api/factor-create/sandbox")
    data = resp.get_json()
    assert data["ok"] is True and [f["name"] for f in data["factors"]] == ["roc"]
    assert "momentum" in data["categories"]

    resp = client.post("/api/factor-create/sandbox/delete", json={"name": "roc"})
    assert resp.get_json()["ok"] is True
    assert client.get("/api/factor-create/sandbox").get_json()["factors"] == []

    resp = client.post("/api/factor-create/sandbox/delete", json={"name": "roc"})
    assert resp.status_code == 404
