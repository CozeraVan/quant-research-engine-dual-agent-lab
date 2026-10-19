from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from quant_research_engine.gui.engine import (
    _build_cli_command,
    _ensure_dirs,
    _run_id,
    compile_high_level_entry,
    get_run,
    get_run_artifacts,
    get_run_stderr,
    get_run_stdout,
    get_run_strategy_yaml,
    list_runs,
    list_templates,
    load_template,
    run_backtest,
    save_template,
    validate_yaml,
    GUI_BASE_DIR,
    RUNS_DIR,
    TEMPLATES_DIR,
)


# --- validate_yaml ---


def test_validate_yaml_valid_strategy():
    yaml_text = """
experiment:
  name: default
  engine:
    kind: single
data:
  factor_fields:
    my_factor: factors.test.close
signal:
  entry: "rsi_2 < 10"
evaluation:
  forward_return_horizons: [1, 3, 5]
holding:
  max_holding_days: 1
"""
    result = validate_yaml(yaml_text)
    assert result == {"valid": True}


def test_validate_yaml_parse_error():
    result = validate_yaml(": invalid : yaml : [")
    assert result["valid"] is False
    assert "YAML parse error" in result["error"]


def test_validate_yaml_not_a_mapping():
    result = validate_yaml("- item1\n- item2\n")
    assert result["valid"] is False
    assert "must be a mapping" in result["error"]


def test_validate_yaml_strategy_spec_error():
    result = validate_yaml("name: test\n# missing required signal_expression\n")
    assert result["valid"] is False
    assert "StrategySpec error" in result["error"]


# --- _run_id ---


def test_run_id_is_string():
    rid = _run_id()
    assert isinstance(rid, str)
    assert len(rid) == 21  # YYYYMMDDTHHMMSSffffff


# --- _ensure_dirs ---


def test_ensure_dirs_creates_base(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path / "gui-console")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "gui-console" / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "gui-console" / "runs")

    _ensure_dirs()

    assert (tmp_path / "gui-console" / "templates").exists()
    assert (tmp_path / "gui-console" / "runs").exists()


# --- templates ---


def test_save_and_list_templates(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path)

    save_template("my-template", "name: test\nsignal_expression: rsi < 10\n")

    assert "my-template" in list_templates()


def test_save_template_replaces_slashes(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path)

    save_template("a/b/c", "content")

    names = list_templates()
    assert "a_b_c" in names
    assert "a/b/c" not in names


def test_save_template_empty_name_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path)

    with pytest.raises(ValueError, match="must not be empty"):
        save_template("   ", "content")


def test_load_template(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path)

    save_template("test-tmpl", "name: t\nsignal_expression: x < 0\n")

    result = load_template("test-tmpl")
    assert result is not None
    assert "name: t" in result


def test_load_template_missing_returns_none():
    result = load_template("nonexistent-template-xyz")
    assert result is None


def test_list_templates_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "nonexistent")

    assert list_templates() == []


# --- run history ---


def _write_mock_run(run_dir: Path, run_id: str, status: str = "completed", **extra) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "run_id": run_id,
        "mode": "batch",
        "start": "2026-01-05",
        "end": "2026-03-31",
        "codes": ["000001.SZ"],
        "status": status,
    }
    record.update(extra)
    (run_dir / "status.json").write_text(json.dumps(record), encoding="utf-8")


def test_list_runs_returns_sorted(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)

    _write_mock_run(runs_dir / "run-001", "run-001")
    _write_mock_run(runs_dir / "run-002", "run-002")

    runs = list_runs()
    assert len(runs) == 2


def test_list_runs_skips_missing_status(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    (runs_dir / "empty").mkdir(parents=True, exist_ok=True)

    runs = list_runs()
    assert len(runs) == 0


def test_get_run_existing(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    _write_mock_run(runs_dir / "run-abc", "run-abc", status="completed")

    record = get_run("run-abc")
    assert record is not None
    assert record["run_id"] == "run-abc"
    assert record["status"] == "completed"


def test_get_run_missing():
    assert get_run("nonexistent") is None


def test_get_run_stdout_stderr(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    run_dir = runs_dir / "run-out"
    run_dir.mkdir(parents=True)
    (run_dir / "stdout.log").write_text("hello stdout", encoding="utf-8")
    (run_dir / "stderr.log").write_text("hello stderr", encoding="utf-8")

    assert get_run_stdout("run-out") == "hello stdout"
    assert get_run_stderr("run-out") == "hello stderr"


def test_get_run_stdout_missing_returns_none():
    assert get_run_stdout("nonexistent") is None


def test_get_run_strategy_yaml(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    run_dir = runs_dir / "run-yaml"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text("name: strat\nsignal_expression: x > 0\n", encoding="utf-8")

    yaml_text = get_run_strategy_yaml("run-yaml")
    assert yaml_text is not None
    assert "name: strat" in yaml_text


def test_get_run_strategy_yaml_missing_returns_none():
    assert get_run_strategy_yaml("nonexistent") is None


def test_get_run_artifacts(monkeypatch, tmp_path):
    runs_dir = tmp_path / "runs"
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", runs_dir)
    run_dir = runs_dir / "run-art"
    _write_mock_run(run_dir, "run-art", artifacts={"summary.csv": "/tmp/summary.csv"})

    artifacts = get_run_artifacts("run-art")
    assert artifacts == {"summary.csv": "/tmp/summary.csv"}


def test_get_run_artifacts_no_record():
    assert get_run_artifacts("nonexistent") == {}


# --- _build_cli_command ---


def test_build_cli_command_single_mode():
    cmd = _build_cli_command(
        mode="single",
        strategy_path=Path("/tmp/strat.yaml"),
        start="2026-01-01",
        end="2026-03-31",
        codes=["000001.SZ"],
        initial_cash="200000",
        max_positions=None,
        output_dir=None,
        db_url=None,
        market_profile=None,
    )
    assert "backtest-single" in cmd
    assert "--symbol" in cmd
    assert "000001.SZ" in cmd
    assert "--start" in cmd
    assert "--initial-cash" in cmd
    assert "200000" in cmd


def test_build_cli_command_shared_mode():
    cmd = _build_cli_command(
        mode="shared",
        strategy_path=Path("/tmp/strat.yaml"),
        start="2026-01-01",
        end="2026-03-31",
        codes=["000001.SZ", "000002.SZ"],
        initial_cash="500000",
        max_positions="15",
        output_dir="/tmp/out",
        db_url="postgresql:///test",
        market_profile="/tmp/profile.yaml",
    )
    assert "backtest-shared" in cmd
    assert "--codes" in cmd
    assert "000001.SZ" in cmd
    assert "--max-positions" in cmd
    assert "15" in cmd
    assert "--output-dir" in cmd
    assert "--db-url" in cmd


# --- run_backtest (module executor path only, no DB) ---


def test_run_backtest_cli_failure_captures_error(monkeypatch, tmp_path):
    """When CLI executor fails, the run should be marked failed."""
    from unittest.mock import Mock

    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    mock_run = Mock(side_effect=RuntimeError("command not found"))
    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_cli", mock_run)

    result = run_backtest(
        yaml_text="name: t\nsignal_expression: x < 0\n",
        mode="single",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
        executor="cli",
    )
    assert result["status"] == "failed"
    assert "command not found" in result["error"]


def test_run_backtest_module_executor_single(monkeypatch, tmp_path):
    """Module executor should write stdout/stderr and mark status completed."""
    from unittest.mock import Mock

    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    def fake_run_via_module(**kwargs):
        kwargs["stdout_path"].write_text("strategy=test\norders=0\n", encoding="utf-8")
        kwargs["stderr_path"].write_text("", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run_via_module)

    result = run_backtest(
        yaml_text="experiment:\n  name: default\n  engine:\n    kind: single\ndata:\n  factor_fields:\n    f: factors.t.c\nsignal:\n  entry: x < 0\nevaluation:\n  forward_return_horizons: [1]\nholding:\n  max_holding_days: 1\n",
        mode="single",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
        output_dir=str(tmp_path / "outputs"),
    )
    assert result["status"] == "completed"
    assert result["mode"] == "single"


# --- max_holding_days 参数透传（SaaS 高级参数 = 落库 = 引擎生效） ---


def test_override_holding_days():
    from quant_research_engine.gui.engine import _override_holding_days
    from quant_research_engine.strategies.spec import StrategySpec

    yaml_text = (
        "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
        "signal:\n  entry: close > 0\nevaluation:\n  forward_return_horizons: [1]\nholding:\n  max_holding_days: 60\n"
    )
    spec = StrategySpec.from_mapping(__import__("yaml").safe_load(yaml_text))
    assert spec.holding_days == 60
    # None = 不覆盖（YAML 为准）；显式值覆盖 YAML；0 = 不限持仓天数
    assert _override_holding_days(spec, None).holding_days == 60
    assert _override_holding_days(spec, 20).holding_days == 20
    assert _override_holding_days(spec, 0).holding_days == 0
    # 原 frozen 实例不被修改
    assert spec.holding_days == 60


def test_run_backtest_records_and_forwards_max_holding_days(monkeypatch, tmp_path):
    """run_backtest 把 max_holding_days 写进 run 记录并透传给执行器。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    captured = {}

    def fake_run_via_module(**kwargs):
        captured.update(kwargs)
        kwargs["stdout_path"].write_text("strategy=t\norders=0\n", encoding="utf-8")
        kwargs["stderr_path"].write_text("", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run_via_module)

    yaml_text = (
        "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
        "signal:\n  entry: close > 0\nholding:\n  max_holding_days: 60\n"
    )
    result = run_backtest(
        yaml_text=yaml_text,
        mode="shared",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
        max_holding_days=0,
        precheck=False,
    )
    assert result["status"] == "completed"
    assert captured["max_holding_days"] == 0  # 0 也要透传（不限），不能按 falsy 丢弃
    assert result["max_holding_days"] == 0

    # 缺省（None）不落记录、不覆盖
    result2 = run_backtest(
        yaml_text=yaml_text,
        mode="shared",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
    )
    assert captured["max_holding_days"] is None
    assert "max_holding_days" not in result2


# --- 成交价列参数透传（entry_price / exit_price，SaaS 高级参数） ---


def test_resolve_price_columns():
    from quant_research_engine.gui.engine import _resolve_price_columns

    assert _resolve_price_columns(None, None) == ("open", "open")
    assert _resolve_price_columns("close", None) == ("close", "close")  # 出场跟随入场
    assert _resolve_price_columns("vwap", "open") == ("vwap", "open")
    with pytest.raises(ValueError):
        _resolve_price_columns("bad", None)
    with pytest.raises(ValueError):
        _resolve_price_columns(None, "bad")


def test_extend_market_fields():
    from quant_research_engine.gui.engine import _extend_market_fields

    base = ["open", "high", "low", "close", "pre_close", "vol", "amount"]
    assert _extend_market_fields(base, "open") == base
    assert _extend_market_fields(base, "vwap", "close") == [*base, "vwap"]


def test_run_backtest_records_and_forwards_price_columns(monkeypatch, tmp_path):
    """run_backtest 把 entry_price/exit_price 写进 run 记录并透传给执行器。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    captured = {}

    def fake_run_via_module(**kwargs):
        captured.update(kwargs)
        kwargs["stdout_path"].write_text("strategy=t\norders=0\n", encoding="utf-8")
        kwargs["stderr_path"].write_text("", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run_via_module)

    yaml_text = (
        "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
        "signal:\n  entry: close > 0\nholding:\n  max_holding_days: 20\n"
    )
    result = run_backtest(
        yaml_text=yaml_text,
        mode="shared",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
        entry_price="close",
        exit_price="vwap",
    )
    assert result["status"] == "completed"
    assert captured["entry_price"] == "close"
    assert captured["exit_price"] == "vwap"
    assert result["entry_price"] == "close"
    assert result["exit_price"] == "vwap"

    # 缺省（None）不落记录键，引擎默认 open/跟随入场
    result2 = run_backtest(
        yaml_text=yaml_text,
        mode="shared",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
    )
    assert captured["entry_price"] is None
    assert captured["exit_price"] is None
    assert "entry_price" not in result2
    assert "exit_price" not in result2

    # 非法列在建 run 前直接拒绝
    with pytest.raises(ValueError):
        run_backtest(
            yaml_text=yaml_text,
            mode="shared",
            start="2026-01-05",
            end="2026-01-06",
            codes="000001.SZ",
            entry_price="bad",
        )


def test_run_backtest_precheck_full_params_carry_price_columns(monkeypatch, tmp_path):
    """precheck 的 full_params 携带 entry_price/exit_price（8081 全量重跑链透传）。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)

    def fake_run_via_module(**kwargs):
        kwargs["stdout_path"].write_text("strategy=t\norders=0\n", encoding="utf-8")
        kwargs["stderr_path"].write_text("", encoding="utf-8")

    monkeypatch.setattr("quant_research_engine.gui.engine._run_via_module", fake_run_via_module)

    yaml_text = (
        "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
        "signal:\n  entry: close > 0\nholding:\n  max_holding_days: 20\n"
    )
    result = run_backtest(
        yaml_text=yaml_text,
        mode="shared",
        start="2026-01-05",
        end="2026-01-06",
        codes="000001.SZ",
        entry_price="vwap",
        exit_price="close",
        precheck=True,
    )
    assert result["status"] == "completed"
    assert result["full_params"]["entry_price"] == "vwap"
    assert result["full_params"]["exit_price"] == "close"


# --- compile_high_level_entry ---


VALID_HIGH_LEVEL_ENTRY = {
    "strategy": {
        "id": "rsi2_oversold_reversal",
        "name": "RSI2 Oversold Reversal",
        "family": "mean_reversion",
        "direction": "long_only",
        "description": "Buy when 2-period RSI is oversold.",
    },
    "rules": {
        "entry": {
            "all": [
                {"alias": "rsi_fast", "operator": "<", "value": 10}
            ]
        }
    },
    "factor_requirements": [
        {
            "alias": "rsi_fast",
            "indicator": "rsi",
            "source": "close",
            "period": 2,
            "reason": "Oversold entry signal",
        }
    ],
    "experiment": {
        "id": "rsi2-test",
        "frequency": "daily",
        "market": "ashare",
        "start": "2026-01-01",
        "end": "2026-03-31",
        "universe": {
            "include": "all_a",
            "exclude_st": True,
            "exclude_suspended": True,
            "exclude_risk_warning": True,
            "min_listing_days": 120,
        },
        "execution": {"market_profile": "ashare_daily_default"},
        "capital": {"initial_cash": 100000, "max_positions": 10},
    },
}


def test_compile_valid_high_level_entry():
    result = compile_high_level_entry(VALID_HIGH_LEVEL_ENTRY)
    assert result["ok"] is True
    assert "yaml" in result
    assert "compiled" in result
    assert "signal_expression" in result["yaml"] or "entry" in result["yaml"].lower()
    assert "rsi_fast" in result["yaml"]


def test_compile_missing_strategy_section():
    result = compile_high_level_entry({"rules": {}, "factor_requirements": [], "experiment": {}})
    assert result["ok"] is False
    assert len(result["issues"]) > 0
    assert any("strategy" in i["message"].lower() or "id" in i["message"].lower() for i in result["issues"])


def test_compile_unknown_indicator():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["factor_requirements"] = [{
        "alias": "bad_factor",
        "indicator": "nonexistent_indicator_xyz",
        "source": "close",
        "period": 10,
        "reason": "test",
    }]
    result = compile_high_level_entry(data)
    assert result["ok"] is False
    assert any("nonexistent" in i["message"] for i in result["issues"])


def test_compile_duplicate_alias():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["factor_requirements"] = [
        {"alias": "dup", "indicator": "rsi", "source": "close", "period": 2, "reason": "a"},
        {"alias": "dup", "indicator": "ema", "source": "close", "period": 20, "reason": "b"},
    ]
    result = compile_high_level_entry(data)
    assert result["ok"] is False
    assert any("dup" in i["message"] and "duplicate" in i["message"].lower() for i in result["issues"])


def test_compile_with_exit_rules():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["rules"]["exit"] = {"any": [{"alias": "rsi_fast", "operator": ">", "value": 70}]}
    result = compile_high_level_entry(data)
    assert result["ok"] is True
    assert "exit" in result["yaml"].lower()


def test_compile_with_risk_controls():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["rules"]["risk"] = {"stop_loss_pct": 0.05, "take_profit_pct": 0.10, "max_holding_days": 20}
    result = compile_high_level_entry(data)
    assert result["ok"] is True
    assert "stop_loss" in result["yaml"]


def test_compile_missing_factor_requirements():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["factor_requirements"] = []
    data["rules"]["entry"]["all"] = [{"alias": "close", "operator": ">", "value": 10}]
    result = compile_high_level_entry(data)
    assert result["ok"] is True  # built-in aliases don't need factors


def test_compile_builtin_alias_shadow_warning():
    data = dict(VALID_HIGH_LEVEL_ENTRY)
    data["factor_requirements"] = [
        {"alias": "close", "indicator": "ema", "source": "close", "period": 10, "reason": "test"},
    ]
    result = compile_high_level_entry(data)
    assert result["ok"] is False
    assert any("close" in i["message"] and "shadow" in i["message"].lower() for i in result["issues"])
