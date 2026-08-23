from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml

from quant_research_engine.gui.factor_wizard import (
    build_condition,
    build_factor_groups,
    build_strategy_yaml,
    combine_conditions,
    parse_factor_table_name,
)
from quant_research_engine.gui import factor_admin
from quant_research_engine.gui.factor_admin import (
    append_factor_entry,
    confirm_execute,
    get_job,
    parse_periods,
    read_indicators,
    rollback_config,
    start_factor_job,
)


# --- parse_factor_table_name ---


def test_parse_factor_table_name_valid():
    assert parse_factor_table_name("stock_daily_momentum_close") == ("momentum", "close")
    assert parse_factor_table_name("stock_daily_overlap_typical_price") == ("overlap", "typical_price")
    assert parse_factor_table_name("stock_daily_momentum_average_price") == ("momentum", "average_price")


def test_parse_factor_table_name_invalid():
    assert parse_factor_table_name("stock_daily") is None
    assert parse_factor_table_name("other_table") is None
    assert parse_factor_table_name("stock_daily_momentum_volume") is None  # 非价格列后缀


# --- build_factor_groups ---


def _tables_columns() -> dict[str, list[str]]:
    return {
        "stock_daily_momentum_close": ["ts_code", "trade_date", "rsi_14", "rsi_6"],
        "stock_daily_overlap_close": ["ts_code", "trade_date", "sma_20"],
        "stock_daily_overlap_typical_price": ["ts_code", "trade_date", "ema_21"],
        "not_a_factor_table": ["x"],
    }


def test_build_factor_groups_grouping_and_labels():
    groups = build_factor_groups(_tables_columns())
    assert groups[0]["group"] == "market"
    assert [i["column"] for i in groups[0]["items"]] == ["open", "high", "low", "close", "pre_close", "vol", "amount"]

    by_group = {g["group"]: g for g in groups}
    momentum = by_group["momentum"]
    assert momentum["label"] == "动量"
    cols = [i["column"] for i in momentum["items"]]
    assert cols == ["rsi_14", "rsi_6"]  # ts_code/trade_date 被剔除
    assert momentum["items"][0]["table"] == "factors.stock_daily_momentum_close"

    overlap = by_group["overlap"]
    assert overlap["label"] == "均线/重叠"
    tables = {i["table"] for i in overlap["items"]}
    assert "factors.stock_daily_overlap_typical_price" in tables
    assert any("典型价" in i["label"] for i in overlap["items"])

    assert "not_a_factor_table" not in {i["table"] for g in groups for i in g["items"]}


# --- build_condition / combine_conditions ---


def test_build_condition_all_operators():
    for op in [">", ">=", "<", "<=", "==", "!="]:
        assert build_condition("rsi_14", op, 30) == f"(rsi_14 {op} 30)"


def test_build_condition_right_factor_vs_number():
    assert build_condition("close", ">", "sma_20") == "(close > sma_20)"
    assert build_condition("close", ">", "20.5") == "(close > 20.5)"
    assert build_condition("close", ">", 0.08) == "(close > 0.08)"


def test_build_condition_validation():
    with pytest.raises(ValueError, match="运算符"):
        build_condition("a", "~~", 1)
    with pytest.raises(ValueError, match="左操作数"):
        build_condition("", ">", 1)
    with pytest.raises(ValueError, match="右操作数"):
        build_condition("a", ">", "")


def test_combine_conditions_and_or():
    conds = ["(a > 1)", "(b < 2)"]
    assert combine_conditions(conds, "and") == "(a > 1) and (b < 2)"
    assert combine_conditions(conds, "or") == "(a > 1) or (b < 2)"
    assert combine_conditions([], "and") is None
    with pytest.raises(ValueError, match="组合逻辑"):
        combine_conditions(conds, "xor")


# --- build_strategy_yaml ---


def test_build_strategy_yaml_entry_exit_and_stops():
    yaml_text = build_strategy_yaml(
        name="wizard_demo",
        factor_fields={"rsi_14": "factors.stock_daily_momentum_close.rsi_14"},
        entry_expression="(rsi_14 < 30)",
        exit_expression="(rsi_14 > 60)",
        holding_days=5,
        stop_loss_pct=0.08,
        take_profit_pct=None,
        trailing_stop_pct=0.05,
    )
    spec = yaml.safe_load(yaml_text)
    assert spec["experiment"]["name"] == "wizard_demo"
    assert spec["data"]["factor_fields"]["rsi_14"] == "factors.stock_daily_momentum_close.rsi_14"
    assert spec["signal"]["entry"] == "(rsi_14 < 30)"
    assert spec["signal"]["exit"] == "(rsi_14 > 60)"
    assert spec["holding"]["max_holding_days"] == 5
    assert spec["risk"]["stop_loss_pct"] == 0.08
    assert "take_profit_pct" not in spec["risk"]
    assert spec["risk"]["trailing_stop_pct"] == 0.05


def test_build_strategy_yaml_no_exit_no_risk():
    yaml_text = build_strategy_yaml(
        name="x",
        factor_fields={},
        entry_expression="(close > sma_20) and (vol > 1000)",
        holding_days=20,
    )
    spec = yaml.safe_load(yaml_text)
    assert "exit" not in spec["signal"]
    assert "risk" not in spec


def test_build_strategy_yaml_requires_entry():
    with pytest.raises(ValueError, match="入场条件"):
        build_strategy_yaml(name="x", factor_fields={}, entry_expression=None)


# --- parse_periods ---


def test_parse_periods_valid():
    assert parse_periods("5,10,20") == [5, 10, 20]
    assert parse_periods(" 20 , 5 ,5 ") == [5, 20]


def test_parse_periods_invalid():
    with pytest.raises(ValueError, match="不能为空"):
        parse_periods("")
    with pytest.raises(ValueError, match="格式错误"):
        parse_periods("5,abc")
    with pytest.raises(ValueError, match="格式错误"):
        parse_periods("5.5")


# --- factors.yaml 追加 / 备份 / 回滚（临时副本，绝不碰真实 repo） ---


_SAMPLE_CONFIG = """factors:
  - name: sma
    category: overlap
    column: close
    periods: [5, 10, 20]

  - name: rsi
    category: momentum
    column: close
    periods: [6, 14]
"""


@pytest.fixture
def config_copy(tmp_path):
    repo = tmp_path / "indicators_tushare"
    (repo / "config").mkdir(parents=True)
    config_path = repo / "config" / "factors.yaml"
    config_path.write_text(_SAMPLE_CONFIG, encoding="utf-8")
    return repo, config_path


def test_read_indicators(config_copy):
    _, config_path = config_copy
    data = read_indicators(config_path)
    assert data["names"] == ["rsi", "sma"]
    assert data["columns"] == ["close"]


def test_append_factor_entry_backup_and_style(config_copy):
    _, config_path = config_copy
    backup = append_factor_entry(config_path, name="rsi", column="close", periods=[21, 28])
    assert backup.exists()
    assert backup.name.startswith("factors.yaml.bak-")
    # 备份内容 == 原内容
    assert backup.read_text(encoding="utf-8") == _SAMPLE_CONFIG

    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    entries = data["factors"]
    assert len(entries) == 3
    new = entries[-1]
    assert new == {"name": "rsi", "category": "momentum", "column": "close", "periods": [21, 28]}


def test_append_factor_entry_unknown_name(config_copy):
    _, config_path = config_copy
    with pytest.raises(ValueError, match="不在 indicators_tushare 已配置列表"):
        append_factor_entry(config_path, name="macd_never", column="close", periods=[10])


def test_rollback_config(config_copy):
    _, config_path = config_copy
    backup = append_factor_entry(config_path, name="sma", column="close", periods=[60])
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["factors"][-1]["periods"] == [60]
    rollback_config(config_path, backup)
    assert config_path.read_text(encoding="utf-8") == _SAMPLE_CONFIG


# --- 任务状态机（mock step_runner） ---


@pytest.fixture
def job_env(monkeypatch, tmp_path, config_copy):
    repo, config_path = config_copy
    monkeypatch.setattr("quant_research_engine.gui.factor_admin.FACTOR_ADMIN_DIR", tmp_path / "factor-admin")
    monkeypatch.setattr("quant_research_engine.gui.factor_admin._active_job_id", None)
    return repo, config_path


def _wait_status(job_id, targets, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = get_job(job_id)
        if record and record["status"] in targets:
            return record
        time.sleep(0.05)
    return get_job(job_id)


def test_job_sample_chain_then_confirm_execute(job_env):
    repo, config_path = job_env
    calls = []

    def runner(cmd, cwd, job_dir):
        calls.append(cmd)
        assert cwd == repo
        return 0

    record = start_factor_job(name="rsi", column="close", periods=[21], repo=repo, step_runner=runner)
    final = _wait_status(record["job_id"], {"awaiting_execute_confirmation"})
    assert final["status"] == "awaiting_execute_confirmation"
    # validate → plan → sample backfill
    assert len(calls) == 3
    assert calls[0][:4] == ["uv", "run", "python", "run_factor_admin.py"]
    assert "validate" in calls[0]
    assert "plan" in calls[1]
    assert "--sample-codes" in calls[2] and "--execute" in calls[2]
    # yaml 新 entry 保留
    assert yaml.safe_load(config_path.read_text(encoding="utf-8"))["factors"][-1]["periods"] == [21]

    # 人工确认全量回填
    confirm_execute(record["job_id"], step_runner=runner)
    done = _wait_status(record["job_id"], {"completed", "failed"})
    assert done["status"] == "completed"
    assert len(calls) == 4
    assert "--execute" in calls[3] and "--sample-codes" not in calls[3]


def test_job_failure_rolls_back(job_env):
    repo, config_path = job_env
    original = config_path.read_text(encoding="utf-8")

    def runner(cmd, cwd, job_dir):
        return 1 if "validate" in cmd else 0

    record = start_factor_job(name="rsi", column="close", periods=[99], repo=repo, step_runner=runner)
    final = _wait_status(record["job_id"], {"failed"})
    assert final["status"] == "failed"
    assert "validate" in final["error"]
    assert "已回滚" in final["error"]
    assert config_path.read_text(encoding="utf-8") == original
    # 锁已释放
    assert factor_admin.active_job_id() is None


def test_job_lock_conflict(job_env):
    repo, _ = job_env

    def slow_runner(cmd, cwd, job_dir):
        time.sleep(0.6)
        return 0

    start_factor_job(name="rsi", column="close", periods=[21], repo=repo, step_runner=slow_runner)
    with pytest.raises(RuntimeError, match="已有一个因子任务"):
        start_factor_job(name="sma", column="close", periods=[60], repo=repo, step_runner=slow_runner)
    # 等第一个跑完释放锁（slow_runner 有 3 步 × 0.6s，全量套件高负载下调度
    # 延迟可能超过 5s，余量放宽到 30s，仅影响该测试的等待上限）
    deadline = time.time() + 30
    while factor_admin.active_job_id() is not None and time.time() < deadline:
        time.sleep(0.05)
    assert factor_admin.active_job_id() is None


def test_confirm_execute_wrong_state(job_env):
    repo, _ = job_env

    def runner(cmd, cwd, job_dir):
        return 0

    record = start_factor_job(name="rsi", column="close", periods=[21], repo=repo, step_runner=runner)
    final = _wait_status(record["job_id"], {"awaiting_execute_confirmation"})
    confirm_execute(final["job_id"], step_runner=runner)
    done = _wait_status(record["job_id"], {"completed"})
    assert done["status"] == "completed"
    with pytest.raises(RuntimeError, match="不能执行全量回填"):
        confirm_execute(record["job_id"], step_runner=runner)
    with pytest.raises(KeyError):
        confirm_execute("nonexistent-job", step_runner=runner)


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
    monkeypatch.setattr("quant_research_engine.gui.factor_admin.FACTOR_ADMIN_DIR", tmp_path / "factor-admin")
    monkeypatch.setattr("quant_research_engine.gui.factor_admin._active_job_id", None)

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_factors_ok(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.factor_wizard.load_factor_tables_columns",
        lambda db_url=None: _tables_columns(),
    )
    resp = app_client.get("/api/factors")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    groups = {g["group"] for g in data["groups"]}
    assert {"market", "momentum", "overlap"} <= groups


def test_api_factors_db_down_503(app_client, monkeypatch):
    def boom(db_url=None):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(
        "quant_research_engine.gui.factor_wizard.load_factor_tables_columns", boom
    )
    resp = app_client.get("/api/factors")
    assert resp.status_code == 503
    assert "因子库不可用" in resp.get_json()["error"]


def test_api_factor_admin_indicators(app_client, monkeypatch, tmp_path):
    repo = tmp_path / "ind"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "factors.yaml").write_text(_SAMPLE_CONFIG, encoding="utf-8")
    monkeypatch.setattr("quant_research_engine.gui.factor_admin.indicators_repo", lambda env=None: repo)
    # app 内 import 的是同一函数对象引用；patch app 侧使用的入口
    import quant_research_engine.gui.factor_admin as fa

    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: repo)
    resp = app_client.get("/api/factor-admin/indicators")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["names"] == ["rsi", "sma"]


def test_api_factor_admin_indicators_missing(app_client, monkeypatch, tmp_path):
    import quant_research_engine.gui.factor_admin as fa

    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: tmp_path / "nope")
    resp = app_client.get("/api/factor-admin/indicators")
    assert resp.status_code == 503
    assert "QRE_INDICATORS_REPO" in resp.get_json()["error"]


def test_api_factor_admin_request_validation(app_client):
    resp = app_client.post("/api/factor-admin/request", json={"name": "", "column": "close", "periods": "5"})
    assert resp.status_code == 400
    resp = app_client.post("/api/factor-admin/request", json={"name": "rsi", "column": "close", "periods": "5,x"})
    assert resp.status_code == 400
    assert "格式错误" in resp.get_json()["error"]


def test_api_factor_admin_request_409(app_client, monkeypatch):
    import quant_research_engine.gui.factor_admin as fa

    monkeypatch.setattr(fa, "_active_job_id", "some-running-job")
    resp = app_client.post(
        "/api/factor-admin/request",
        json={"name": "rsi", "column": "close", "periods": "21"},
    )
    assert resp.status_code == 409
    assert "已有一个因子任务" in resp.get_json()["error"]


def test_api_factor_admin_job_not_found(app_client):
    resp = app_client.get("/api/factor-admin/jobs/nope")
    assert resp.status_code == 404


def test_index_page_contains_wizard(app_client):
    resp = app_client.get("/")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    # 两 tab 结构：新增策略（默认）+ 新增因子
    assert "新增策略" in html
    assert "新增因子" in html
    assert 'id="tab-strategy"' in html
    assert 'id="tab-factor"' in html
    # 可视化构建区与路径 A（补周期）元素保留
    assert "wz-factor-groups" in html
    assert "wz-admin-submit" in html
    assert "wzGotoFactorAdmin" in html
    # 路径 B（全新指标 fc-create）已迁入首页
    assert 'id="fc-code"' in html
    assert 'id="fc-promote"' in html
    # 旧 builder tab 已删除
    assert "tab-builder" not in html
    assert "builder-layout" not in html


def test_factor_admin_backfill_commands_pin_baseline_head():
    """回归：backfill 必须固定 --baseline-ref HEAD，否则默认基线会选 ~291 列
    （2026-08-03 实战发现的重大隐患：全量重算并覆盖 statistics 口径）。"""
    from quant_research_engine.gui import factor_admin

    for cmd in (factor_admin.SAMPLE_BACKFILL_CMD, factor_admin.FULL_BACKFILL_CMD, factor_admin.PLAN_CMD):
        assert "--baseline-ref" in cmd
        assert cmd[cmd.index("--baseline-ref") + 1] == "HEAD"
