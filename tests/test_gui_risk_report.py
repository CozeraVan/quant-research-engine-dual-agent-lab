"""gui.risk_report 单测（FRM 风险模块 R3）：收益提取、finalize 钩子、
markdown 追加幂等、run_detail 模板渲染、按需生成 job 端点。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.gui import risk_report as rr


@pytest.fixture()
def fake_run(tmp_path):
    """构造一个 completed run：output_dir 含组合级 + per-symbol equity curve、summary.md。"""
    rng = np.random.default_rng(7)
    n = 160
    dates = pd.bdate_range("2025-01-02", periods=n)
    rets = rng.normal(0.0003, 0.012, n)
    equity = 1_000_000.0 * np.cumprod(1.0 + rets)

    output_dir = tmp_path / "out" / "run1"
    bt = output_dir / "backtest"
    bt.mkdir(parents=True)
    frame = pd.DataFrame({
        "trade_date": dates.strftime("%Y-%m-%d"),
        "cash": 500_000.0,
        "market_value": 500_000.0,
        "total_equity": equity,
        "daily_return": [None] + list(rets[1:]),
        "cumulative_return": equity / equity[0] - 1.0,
        "position_count": 2,
        "turnover": 0.0,
    })
    # daily_return 首行空（引擎口径）；用与 equity 一致的 pct_change 填充更真实
    frame["daily_return"] = frame["total_equity"].pct_change()
    frame.to_csv(bt / "equity_curve.csv", index=False)
    sym_dir = bt / "000001.SZ"
    sym_dir.mkdir()
    pd.DataFrame({
        "symbol": "000001.SZ",
        "trade_date": dates.strftime("%Y-%m-%d"),
        "total_equity": equity,
    }).to_csv(sym_dir / "equity_curve.csv", index=False)
    (bt / "summary.md").write_text("# Batch Backtest Summary\n\n## Aggregate Metrics\n\n| a | b |\n", encoding="utf-8")

    record = {
        "run_id": "testrun001",
        "status": "completed",
        "output_dir": str(output_dir),
        "artifacts": {},
    }
    return record, rets, dates


class TestExtractStrategyReturns:
    def test_prefers_portfolio_level_with_daily_return(self, fake_run):
        record, rets, dates = fake_run
        extracted = rr.extract_strategy_returns(record)
        assert extracted is not None
        returns, benchmark = extracted
        assert benchmark is None  # 无 benchmark_close 列
        assert isinstance(returns.index, pd.DatetimeIndex)
        assert len(returns) == len(rets) - 1
        expected = pd.Series(rets[1:], index=dates[1:])
        pd.testing.assert_series_equal(
            returns.reset_index(drop=True), expected.reset_index(drop=True),
            check_names=False, atol=1e-12,
        )

    def test_excludes_per_symbol_files(self, fake_run):
        record, _, _ = fake_run
        # 删掉组合级，只剩 per-symbol（含 symbol 列）→ 应返回 None
        Path(record["output_dir"], "backtest", "equity_curve.csv").unlink()
        assert rr.extract_strategy_returns(record) is None

    def test_pct_change_fallback_without_daily_return(self, fake_run):
        record, _, _ = fake_run
        bt = Path(record["output_dir"], "backtest")
        frame = pd.read_csv(bt / "equity_curve.csv").drop(columns=["daily_return"])
        frame.to_csv(bt / "equity_curve.csv", index=False)
        extracted = rr.extract_strategy_returns(record)
        assert extracted is not None
        returns, _ = extracted
        assert len(returns) == len(frame) - 1

    def test_no_equity_curve_returns_none(self, tmp_path):
        record = {"run_id": "x", "status": "completed", "output_dir": str(tmp_path), "artifacts": {}}
        assert rr.extract_strategy_returns(record) is None


class TestFinalizeHook:
    def test_finalize_writes_json_and_appends_markdown(self, fake_run, monkeypatch, tmp_path):
        record, _, _ = fake_run
        monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
        report = rr.finalize_risk_report(record)
        assert report is not None
        json_path = tmp_path / "runs" / "testrun001" / "risk_report.json"
        assert json_path.exists()
        loaded = json.loads(json_path.read_text(encoding="utf-8"))
        assert loaded["meta"]["run_id"] == "testrun001"
        assert loaded["meta"]["sections"]["stress"] is True
        assert loaded["meta"]["sections"]["bootstrap"] is False

        summary = Path(record["output_dir"], "backtest", "summary.md").read_text(encoding="utf-8")
        assert "# Batch Backtest Summary" in summary  # 既有结构保留
        assert "## 风险分析" in summary
        assert "### VaR 回测" in summary

    def test_finalize_idempotent_no_duplicate_section(self, fake_run, monkeypatch, tmp_path):
        record, _, _ = fake_run
        monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
        rr.finalize_risk_report(record)
        rr.finalize_risk_report(record)
        summary = Path(record["output_dir"], "backtest", "summary.md").read_text(encoding="utf-8")
        assert summary.count("## 风险分析") == 1

    def test_finalize_skips_failed_run(self, fake_run, monkeypatch, tmp_path):
        record, _, _ = fake_run
        monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
        record["status"] = "failed"
        assert rr.finalize_risk_report(record) is None
        assert not (tmp_path / "runs" / "testrun001" / "risk_report.json").exists()

    def test_finalize_writes_md_next_to_json_without_summary_md(self, fake_run, monkeypatch, tmp_path):
        record, _, _ = fake_run
        monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
        Path(record["output_dir"], "backtest", "summary.md").unlink()
        assert rr.finalize_risk_report(record) is not None
        assert (tmp_path / "runs" / "testrun001" / "risk_report.md").exists()


class TestEngineHookWiring:
    def test_execute_and_finalize_invokes_risk_hook(self, tmp_path, monkeypatch):
        """run 收尾对 completed run 调 finalize_risk_report；异常被吞。"""
        from quant_research_engine.gui import engine

        monkeypatch.setattr(engine, "RUNS_DIR", tmp_path / "runs")
        run_dir = tmp_path / "runs" / "hookrun"
        run_dir.mkdir(parents=True)
        record = {"run_id": "hookrun", "executor": "module", "status": "running"}

        monkeypatch.setattr(engine, "_run_via_module", lambda **kw: None)
        calls = []
        monkeypatch.setattr(rr, "finalize_risk_report", lambda rec: calls.append(rec["status"]))
        engine._execute_and_finalize(record, run_dir, [], {})
        assert calls == ["completed"]

        # 钩子抛异常不影响 run 状态
        record2 = {"run_id": "hookrun", "executor": "module", "status": "running"}
        def _boom(rec):
            raise RuntimeError("boom")
        monkeypatch.setattr(rr, "finalize_risk_report", _boom)
        engine._execute_and_finalize(record2, run_dir, [], {})
        status = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        assert status["status"] == "completed"


# --- Flask 端点与模板 ---


@pytest.fixture()
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
    monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.daily_jobs.DAILY_JOBS_DIR", tmp_path / "daily-jobs")

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _write_run(tmp_path, run_id: str, status: str = "completed") -> Path:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "status.json").write_text(
        json.dumps({"run_id": run_id, "status": status, "artifacts": {}}), encoding="utf-8"
    )
    return run_dir


class TestRiskReportEndpoints:
    def test_post_run_not_found(self, app_client):
        resp = app_client.post("/api/runs/nope/risk-report")
        assert resp.status_code == 404

    def test_post_run_not_completed(self, app_client, tmp_path):
        _write_run(tmp_path, "runrun1", status="running")
        resp = app_client.post("/api/runs/runrun1/risk-report")
        assert resp.status_code == 400

    def test_post_starts_job_and_poll(self, app_client, tmp_path, monkeypatch):
        _write_run(tmp_path, "runok1", status="completed")
        monkeypatch.setattr(
            rr, "generate_risk_report",
            lambda record, bootstrap=False: {"meta": {"n_obs": 10, "bootstrap_on_demand": bootstrap}},
        )
        resp = app_client.post("/api/runs/runok1/risk-report")
        assert resp.status_code == 200
        job_id = resp.get_json()["job_id"]

        deadline = time.time() + 10
        job = {}
        while time.time() < deadline:
            poll = app_client.get(f"/api/runs/runok1/risk-report/job/{job_id}")
            assert poll.status_code == 200
            job = poll.get_json()
            if job["status"] in ("completed", "failed"):
                break
            time.sleep(0.05)
        assert job["status"] == "completed"
        assert job["pipeline"] == "risk-report:runok1"

    def test_post_conflict_409(self, app_client, tmp_path, monkeypatch):
        import threading

        _write_run(tmp_path, "runbusy", status="completed")
        gate = threading.Event()

        def _slow(record, bootstrap=False):
            gate.wait(5)
            return {"meta": {"n_obs": 1}}

        monkeypatch.setattr(rr, "generate_risk_report", _slow)
        resp1 = app_client.post("/api/runs/runbusy/risk-report")
        assert resp1.status_code == 200
        time.sleep(0.1)
        resp2 = app_client.post("/api/runs/runbusy/risk-report")
        assert resp2.status_code == 409
        gate.set()

    def test_poll_job_not_found(self, app_client):
        resp = app_client.get("/api/runs/runok1/risk-report/job/999")
        assert resp.status_code == 404


class TestRunDetailTemplate:
    def test_detail_with_risk_report_renders_cards(self, app_client, tmp_path, fake_run, monkeypatch):
        record, _, _ = fake_run
        monkeypatch.setattr(rr, "RUNS_DIR", tmp_path / "runs")
        run_dir = _write_run(tmp_path, "testrun001", status="completed")
        (run_dir / "status.json").write_text(json.dumps(record), encoding="utf-8")
        rr.finalize_risk_report(record)
        resp = app_client.get("/runs/testrun001")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "尾部风险 VaR / ES" in html
        assert "VaR 回测（HIT / LR）" in html
        assert "压力测试（历史情景回放）" in html
        assert 'id="btn-risk-report"' not in html

    def test_detail_without_risk_report_shows_button(self, app_client, tmp_path):
        _write_run(tmp_path, "oldrun1", status="completed")
        resp = app_client.get("/runs/oldrun1")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "未生成风险分析" in html
        assert 'id="btn-risk-report"' in html

    def test_detail_failed_run_no_button(self, app_client, tmp_path):
        _write_run(tmp_path, "failrun1", status="failed")
        resp = app_client.get("/runs/failrun1")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert 'id="btn-risk-report"' not in html


# --- R7：组合与衍生品风险（portfolio 扩展节 + 可选闸判据） ---


def _portfolio_section(dv01=400.0, delta=1.0):
    return {
        "meta": {"legs": {"equity": True, "fixed_income": True, "options": True}},
        "fixed_income": {
            "n_positions": 1,
            "total_market_value": 1_000_000.0,
            "dv01": dv01,
            "duration": 4.0,
            "convexity": 20.0,
            "kr01": {
                "key_tenors": [1.0, 5.0],
                "kr01": [100.0, 300.0],
                "kr01_sum": dv01,
            },
        },
        "options": {
            "n_positions": 1,
            "delta": delta,
            "gamma": 0.02,
            "vega": 20.0,
            "theta": -4.0,
            "rho": 3.0,
        },
        "dgv_var": {"method": "normal", "confidence": 0.99, "var": 123.45},
    }


def _write_report_with_portfolio(tmp_path, monkeypatch, run_id="rid-r7", portfolio=None):
    """把含/不含 portfolio 节的假 risk_report.json 落到假 RUNS_DIR。"""
    runs_dir = tmp_path / "runs"
    (runs_dir / run_id).mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"n_obs": 100},
        "tail": {"99pct": {"historical_simulation": {"es": 0.02}}},
        "var_backtest": {"levels": {"99pct": {"coverage": {"reject_5pct": False}}}},
    }
    if portfolio is not None:
        payload["portfolio"] = portfolio
    (runs_dir / run_id / "risk_report.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )
    monkeypatch.setattr(rr, "RUNS_DIR", runs_dir)


class TestRunDetailPortfolioCard:
    def test_card_rendered_when_portfolio_section_present(self, app_client, tmp_path, monkeypatch):
        _write_run(tmp_path, "runwithderiv", status="completed")
        _write_report_with_portfolio(tmp_path, monkeypatch, run_id="runwithderiv",
                                     portfolio=_portfolio_section())
        resp = app_client.get("/runs/runwithderiv")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "衍生品风险（组合层）" in html
        assert "KR01" in html
        assert "组合 Greeks" in html
        assert "DGV" in html

    def test_card_absent_without_portfolio_section(self, app_client, tmp_path, monkeypatch):
        """老格式 risk_report.json（无 portfolio 节）→ 不显示卡片、页面不炸。"""
        _write_run(tmp_path, "runnod", status="completed")
        _write_report_with_portfolio(tmp_path, monkeypatch, run_id="runnod", portfolio=None)
        resp = app_client.get("/runs/runnod")
        assert resp.status_code == 200
        html = resp.data.decode("utf-8")
        assert "衍生品风险" not in html


class TestGateDerivativeLimits:
    def test_default_disabled_zero_behavior_change(self, tmp_path, monkeypatch):
        """阈值默认 None：即使 report 有 portfolio 节也不追加判据、不加新键。"""
        from quant_research_engine.risk import constants as risk_constants

        assert risk_constants.GATE_DV01_MAX is None
        assert risk_constants.GATE_GREEKS_MAX is None
        _write_report_with_portfolio(tmp_path, monkeypatch, portfolio=_portfolio_section())
        risk = rr.evaluate_gate_risk("rid-r7")
        assert risk["status"] == "ok"
        assert risk["reasons"] == []
        assert set(risk) == {
            "status", "es99", "es99_threshold", "var_lr_reject",
            "var_confidence", "reasons", "report_run_id",
        }  # 与 R4 输出逐键一致

    def test_dv01_limit_exceeded_warns(self, tmp_path, monkeypatch):
        from quant_research_engine.risk import constants as risk_constants

        monkeypatch.setattr(risk_constants, "GATE_DV01_MAX", 100.0)
        _write_report_with_portfolio(tmp_path, monkeypatch, portfolio=_portfolio_section(dv01=400.0))
        risk = rr.evaluate_gate_risk("rid-r7")
        assert risk["status"] == "warning"
        assert "dv01_exceeds_limit" in risk["reasons"]
        assert risk["dv01"] == 400.0
        assert risk["dv01_threshold"] == 100.0

    def test_dv01_under_limit_ok(self, tmp_path, monkeypatch):
        from quant_research_engine.risk import constants as risk_constants

        monkeypatch.setattr(risk_constants, "GATE_DV01_MAX", 1000.0)
        _write_report_with_portfolio(tmp_path, monkeypatch, portfolio=_portfolio_section(dv01=400.0))
        risk = rr.evaluate_gate_risk("rid-r7")
        assert risk["status"] == "ok"
        assert risk["dv01"] == 400.0

    def test_greeks_limit_exceeded_warns(self, tmp_path, monkeypatch):
        from quant_research_engine.risk import constants as risk_constants

        monkeypatch.setattr(risk_constants, "GATE_GREEKS_MAX", {"delta": 0.5})
        _write_report_with_portfolio(tmp_path, monkeypatch, portfolio=_portfolio_section(delta=-1.0))
        risk = rr.evaluate_gate_risk("rid-r7")
        assert risk["status"] == "warning"
        assert "greek_delta_exceeds_limit" in risk["reasons"]
        assert risk["greeks"]["delta"] == -1.0

    def test_enabled_but_no_portfolio_section_no_trigger(self, tmp_path, monkeypatch):
        """启用判据但 report 无 portfolio 节（老 run）→ 子项 None、不触发。"""
        from quant_research_engine.risk import constants as risk_constants

        monkeypatch.setattr(risk_constants, "GATE_DV01_MAX", 100.0)
        monkeypatch.setattr(risk_constants, "GATE_GREEKS_MAX", {"delta": 1.0})
        _write_report_with_portfolio(tmp_path, monkeypatch, portfolio=None)
        risk = rr.evaluate_gate_risk("rid-r7")
        assert risk["status"] == "ok"
        assert risk["dv01"] is None and risk["greeks"] is None
        assert risk["reasons"] == []
