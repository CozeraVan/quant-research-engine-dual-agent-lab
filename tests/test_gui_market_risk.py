"""管理台「大盘风险」风向标（QRE-RISK-BAROMETER-M3-010）：数据层 fake store、
路由、空数据/错误降级；deploy timer/service 静态校验；CLI 入口。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from quant_research_engine.gui import admin, market_risk
from quant_research_engine.gui.market_risk import market_risk_overview


def _clear_cache() -> None:
    admin._cache.clear()


class _FakeResult:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


def _mkt_row(day: dt.date, score: float, alert: str = "green"):
    indicators = {
        "median_sigma": 0.02,
        "dispersion_equal_weight": 0.01,
        "avg_pairwise_corr_equal_weight": 0.25,
        "var_breach_ratio": 0.005,
    }
    scores = {"total_score": score, "warmup": False}
    alert_d = {
        "alert": alert,
        "corr_change": 0.03,
        "corr_jump_threshold": 0.10,
        "corr_exceed": False,
        "breach_ratio_latest": 0.005,
        "breach_ratio_threshold": 0.03,
        "breach_exceed": False,
    }
    return (day, 5500, indicators, scores, alert_d)


class _FakeConn:
    def __init__(self, market_rows, board_rows, latest):
        self._market_rows = market_rows
        self._board_rows = board_rows
        self._latest = latest

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        sql = str(clause)
        if "max(trade_date)" in sql:
            return _FakeResult(scalar=self._latest)
        if "scope = 'market'" in sql:
            return _FakeResult(rows=self._market_rows)
        return _FakeResult(rows=self._board_rows)


class _FakeEngine:
    def __init__(self, conn):
        self._conn = conn

    def begin(self):
        return self._conn


class _FakeStore:
    def __init__(self, conn):
        self.market_engine = _FakeEngine(conn)

    def close(self):
        pass


@pytest.fixture(autouse=True)
def clear_cache():
    _clear_cache()
    yield
    _clear_cache()


def _patch_store(monkeypatch, conn):
    monkeypatch.setattr(market_risk, "_store", lambda db_url=None: _FakeStore(conn))


class TestOverview:
    def test_happy_path(self, monkeypatch):
        d0, d1 = dt.date(2026, 8, 19), dt.date(2026, 8, 20)
        market_rows = [_mkt_row(d1, 55.0), _mkt_row(d0, 40.0)]  # DESC 返回
        board_rows = [
            ("industry:银行", 42, {"median_sigma": 0.015, "var_breach_ratio": 0.0}, {"total_score": 30.0, "warmup": False}, {"alert": "green"}),
            ("industry:电子", 300, {"median_sigma": 0.03, "var_breach_ratio": 0.02}, {"total_score": 88.0, "warmup": False}, {"alert": "amber"}),
            ("cluster:连跌:3日", 564, {"median_sigma": 0.04, "var_breach_ratio": 0.03}, None, {"alert": None}),
        ]
        _patch_store(monkeypatch, _FakeConn(market_rows, board_rows, d1))
        out = market_risk_overview()
        assert out["ok"] is True and out["empty"] is False
        assert out["latest_date"] == "2026-08-20"
        # series 反转为升序
        assert out["series"]["dates"] == ["2026-08-19", "2026-08-20"]
        assert out["series"]["total_score"] == [40.0, 55.0]
        assert out["market"]["total_score"] == 55.0
        assert out["market"]["alert_detail"]["corr_jump_threshold"] == 0.10
        # 行业按分数降序、簇按突破占比排序
        assert [e["name"] for e in out["industries"]] == ["电子", "银行"]
        assert out["clusters"][0]["name"] == "连跌:3日"
        assert out["clusters"][0]["total_score"] is None  # 簇分数 M2 不算

    def test_empty_table(self, monkeypatch):
        _patch_store(monkeypatch, _FakeConn([], [], None))
        out = market_risk_overview()
        assert out["ok"] is True and out["empty"] is True
        assert "暂无数据" in out["note"]

    def test_db_error_degrades(self, monkeypatch):
        def _boom(db_url=None):
            raise RuntimeError("no db")

        monkeypatch.setattr(market_risk, "_store", _boom)
        out = market_risk_overview()
        assert out["ok"] is False and "数据库不可用" in out["error"]

    def test_query_error_degrades(self, monkeypatch):
        class _BadConn(_FakeConn):
            def execute(self, clause, params=None):
                raise RuntimeError("relation market_risk.daily does not exist")

        _patch_store(monkeypatch, _BadConn([], [], None))
        out = market_risk_overview()
        assert out["ok"] is False and "查询失败" in out["error"]

    def test_route_200(self, monkeypatch):
        d1 = dt.date(2026, 8, 20)
        _patch_store(monkeypatch, _FakeConn([_mkt_row(d1, 55.0)], [], d1))
        from quant_research_engine.gui.app import create_app

        client = create_app().test_client()
        resp = client.get("/api/admin/market-risk")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["market"]["alert"] == "green"


class TestAdminPage:
    def test_admin_tab_present(self):
        from quant_research_engine.gui.app import create_app

        client = create_app().test_client()
        html = client.get("/admin").get_data(as_text=True)
        assert 'data-tab="risk"' in html
        assert "大盘风险" in html
        assert "/api/admin/market-risk" in html

    def test_admin_layman_guide_present(self):
        """通俗说明块：面向一般投资人的备注（风险分数/红绿灯/四指标白话）。"""
        from quant_research_engine.gui.app import create_app

        client = create_app().test_client()
        html = client.get("/admin").get_data(as_text=True)
        assert "怎么看懂这个页面" in html
        assert "现在市场整体危险吗" in html
        assert "不构成投资建议" in html
        assert "同步程度" in html and "传染" in html

    def test_timer_units_include_barometer(self):
        units = {u["unit"] for u in admin.TIMER_UNITS}
        assert "qre-barometer.timer" in units

    def test_timer_install_hint(self):
        class _Proc:
            returncode = 3
            stdout = ""

        def _runner(cmd, **kw):
            return _Proc()

        entries = admin.timer_status(runner=_runner)
        baro = next(e for e in entries if e["unit"] == "qre-barometer.timer")
        assert baro["status"] == "not_installed"
        assert "qre-barometer" in baro["install_hint"]


class TestDeployFiles:
    ROOT = Path(__file__).resolve().parents[1] / "deploy" / "hardened"

    def test_timer_static(self):
        content = (self.ROOT / "qre-barometer.timer").read_text(encoding="utf-8")
        assert "OnCalendar=Mon..Fri *-*-* 18:30:00" in content
        assert "Persistent=true" in content
        assert "WantedBy=timers.target" in content

    def test_service_static(self):
        content = (self.ROOT / "qre-barometer.service").read_text(encoding="utf-8")
        assert "quant_research_engine.risk.barometer_job" in content
        assert "Type=oneshot" in content
        assert "Persistent" not in content  # Persistent 属 timer 侧
        assert "User=van" in content

    def test_daily_jobs_pipeline_registered(self):
        from quant_research_engine.gui.daily_jobs import PIPELINES

        spec = PIPELINES["qre-barometer"]
        assert spec["unit"] == "qre-barometer.service"
        assert "barometer_job" in " ".join(spec["cmd"])


class TestCli:
    def test_barometer_parser(self):
        from quant_research_engine.apps.cli import build_parser

        args = build_parser().parse_args(["barometer", "--date", "2026-08-20"])
        assert args.command == "barometer"
        assert args.date == "2026-08-20"
        assert args.chunk == "year"

    def test_barometer_handler_dispatch(self, monkeypatch):
        from quant_research_engine.apps import cli

        captured = {}

        def _fake_main(argv):
            captured["argv"] = argv

        monkeypatch.setattr(
            "quant_research_engine.risk.barometer_job.main", _fake_main
        )
        assert cli.main(["barometer", "--date", "2026-08-20", "--no-cluster"]) == 0
        assert captured["argv"] == ["--date", "2026-08-20", "--no-cluster"]
