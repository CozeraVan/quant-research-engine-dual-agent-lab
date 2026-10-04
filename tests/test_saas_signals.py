"""CR-2026-10-04 模块二：策略信号监控 + 站内信号中心测试。

覆盖：watch CRUD/上限/scan_enabled 403/权限 404、worker 侧 watches/signals 接口鉴权与
幂等回传、信号中心筛选分页/未读红点/mark-read、详情页监控卡数据、扫描脚本
信号计算正确性（合成面板）与空信号。fixture 复制 test_gui_saas_console.py 模式。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}

YAML_TEXT = """experiment:
  name: t
data:
  market_fields: [open, close]
  factor_fields:
    ema_5: factors.stock_daily_overlap_close.ema_5
signal:
  entry: "(ema_5 > close) and (ema_5.shift(1) <= close.shift(1))"
  exit: "rsi_14 > 70"
"""


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    subprocess.run(
        ["psql", f"postgresql:///{db_name}", "-v", "ON_ERROR_STOP=1",
         "-f", "deploy/saas/cloud_schema.sql"],
        check=True, capture_output=True, text=True,
    )
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def app(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean(app):
    from quant_research_engine.gui.saas.app import _get_engine
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "factor_requests, workers, worker_configs, strategy_watches, "
                          "signal_events RESTART IDENTITY CASCADE"))
        conn.execute(text("UPDATE tier_policies SET scan_enabled = true, max_watches = 20"))


def _user(app, uid=1):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email) VALUES (:i, :e) ON CONFLICT (id) DO NOTHING"),
                     {"i": uid, "e": f"u{uid}@e.c"})
    return {"X-User-Id": str(uid)}


def _strategy(app, uid=1, name="s1"):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO strategies (user_id, name, yaml) VALUES (:u, :n, :y) RETURNING id"),
            {"u": uid, "n": name, "y": YAML_TEXT},
        ).scalar_one()


class TestWatchCrud:
    def test_create_default_snapshot_scope(self, client, app):
        headers = _user(app)
        sid = _strategy(app)
        # 先跑一个带 codes 的 job，last_run_universe 默认快照取它的 codes
        client.post("/api/saas/jobs", json={
            "yaml": YAML_TEXT, "kind": "smoke",
            "params": {"codes": ["000001", "600519"], "start": "2025-01-01", "end": "2025-06-01"},
            "name": "s1"}, headers=headers)
        d = client.post(f"/api/saas/strategies/{sid}/watch", json={"enabled": True},
                        headers=headers).get_json()
        assert d["ok"], d
        det = client.get(f"/api/saas/strategies/{sid}/detail", headers=headers).get_json()
        assert det["watch"]["enabled"] is True
        assert det["watch"]["scope_type"] == "last_run_universe"
        assert det["watch"]["scope_payload"]["codes"] == ["000001.SZ", "600519.SH"]  # 提交时已规范化
        assert det["recent_signals_7d"] == 0

    def test_update_and_delete(self, client, app):
        headers = _user(app)
        sid = _strategy(app)
        client.post(f"/api/saas/strategies/{sid}/watch", json={"enabled": True}, headers=headers)
        d = client.post(f"/api/saas/strategies/{sid}/watch",
                        json={"enabled": True, "scope_type": "custom",
                              "scope_payload": {"codes": ["300750"]}}, headers=headers).get_json()
        assert d["updated"] is True
        det = client.get(f"/api/saas/strategies/{sid}/detail", headers=headers).get_json()
        assert det["watch"]["scope_payload"]["codes"] == ["300750"]
        d = client.delete(f"/api/saas/strategies/{sid}/watch", headers=headers).get_json()
        assert d["ok"]
        assert client.delete(f"/api/saas/strategies/{sid}/watch",
                             headers=headers).status_code == 404

    def test_guest_401_and_other_user_404(self, client, app):
        _user(app)
        sid = _strategy(app)
        assert client.post(f"/api/saas/strategies/{sid}/watch", json={}).status_code == 401
        _user(app, uid=2)
        assert client.post(f"/api/saas/strategies/{sid}/watch", json={},
                           headers={"X-User-Id": "2"}).status_code == 404

    def test_bad_scope_type_400(self, client, app):
        headers = _user(app)
        sid = _strategy(app)
        assert client.post(f"/api/saas/strategies/{sid}/watch",
                           json={"scope_type": "bogus"}, headers=headers).status_code == 400

    def test_max_watches_limit_403(self, client, app):
        headers = _user(app)
        s1 = _strategy(app, name="s1")
        s2 = _strategy(app, name="s2")
        engine = app.extensions["saas_engine"]
        from quant_research_engine.gui.saas.app import _ensure_tier_policies
        _ensure_tier_policies(engine)
        with engine.begin() as conn:
            conn.execute(text("UPDATE tier_policies SET max_watches = 1 WHERE tier = 'member'"))
        assert client.post(f"/api/saas/strategies/{s1}/watch", json={}, headers=headers).get_json()["ok"]
        d = client.post(f"/api/saas/strategies/{s2}/watch", json={}, headers=headers)
        assert d.status_code == 403 and "上限" in d.get_json()["error"]

    def test_scan_disabled_403(self, client, app):
        headers = _user(app)
        sid = _strategy(app)
        engine = app.extensions["saas_engine"]
        from quant_research_engine.gui.saas.app import _ensure_tier_policies
        _ensure_tier_policies(engine)
        with engine.begin() as conn:
            conn.execute(text("UPDATE tier_policies SET scan_enabled = false WHERE tier = 'member'"))
        assert client.post(f"/api/saas/strategies/{sid}/watch", json={},
                           headers=headers).status_code == 403


class TestWorkerSignalApis:
    def _seed_watch(self, client, app, enabled=True, tier="member"):
        headers = _user(app)
        sid = _strategy(app)
        client.post(f"/api/saas/strategies/{sid}/watch",
                    json={"enabled": enabled, "scope_type": "custom",
                          "scope_payload": {"codes": ["000001"]}}, headers=headers)
        return sid

    def test_watches_auth(self, client, app):
        assert client.get("/api/worker/watches").status_code == 401
        assert client.post("/api/worker/signals", json={"events": []}).status_code == 401

    def test_watches_payload_and_enabled_filter(self, client, app):
        self._seed_watch(client, app, enabled=True)
        self._seed_watch(client, app, enabled=False)  # type: ignore[arg-type]
        # 修正：第二个建在不同策略上且停用
        d = client.get("/api/worker/watches", headers=WORKER_HEADERS).get_json()
        assert d["ok"] and len(d["watches"]) == 1
        w = d["watches"][0]
        assert w["scope_type"] == "custom" and w["scope_payload"]["codes"] == ["000001"]
        assert "entry" in w["yaml"] and w["strategy_name"] == "s1"

    def test_signals_ingest_idempotent(self, client, app):
        sid = self._seed_watch(client, app)
        wid = client.get("/api/worker/watches", headers=WORKER_HEADERS).get_json()["watches"][0]["watch_id"]
        events = [{"watch_id": wid, "trade_date": "2026-10-03", "ts_code": "000001.SZ",
                   "signal_type": "entry", "price": 10.5}]
        d1 = client.post("/api/worker/signals", json={"events": events},
                         headers=WORKER_HEADERS).get_json()
        assert d1["inserted"] == 1
        d2 = client.post("/api/worker/signals", json={"events": events},
                         headers=WORKER_HEADERS).get_json()
        assert d2["inserted"] == 0  # 幂等重跑

    def test_signals_validation_400(self, client, app):
        assert client.post("/api/worker/signals", json={"events": "x"},
                           headers=WORKER_HEADERS).status_code == 400
        bad = [{"watch_id": 1, "trade_date": "2026-13-01", "ts_code": "x", "signal_type": "entry"}]
        assert client.post("/api/worker/signals", json={"events": bad},
                           headers=WORKER_HEADERS).status_code == 400


class TestSignalCenter:
    def _seed_events(self, client, app):
        headers = _user(app)
        sid = _strategy(app)
        client.post(f"/api/saas/strategies/{sid}/watch",
                    json={"enabled": True, "scope_type": "custom",
                          "scope_payload": {"codes": ["000001"]}}, headers=headers)
        wid = client.get("/api/worker/watches", headers=WORKER_HEADERS).get_json()["watches"][0]["watch_id"]
        events = [
            {"watch_id": wid, "trade_date": "2026-10-01", "ts_code": "000001.SZ", "signal_type": "entry", "price": 10.5},
            {"watch_id": wid, "trade_date": "2026-10-02", "ts_code": "600519.SH", "signal_type": "exit", "price": 1700.0},
        ]
        client.post("/api/worker/signals", json={"events": events}, headers=WORKER_HEADERS)
        return headers, sid

    def test_list_filter_pagination(self, client, app):
        headers, sid = self._seed_events(client, app)
        d = client.get("/api/saas/signals", headers=headers).get_json()
        assert d["total"] == 2
        d = client.get("/api/saas/signals?signal_type=entry", headers=headers).get_json()
        assert d["total"] == 1 and d["items"][0]["ts_code"] == "000001.SZ"
        d = client.get("/api/saas/signals?ts_code=600519.SH", headers=headers).get_json()
        assert d["total"] == 1 and d["items"][0]["signal_type"] == "exit"
        d = client.get("/api/saas/signals?date_from=2026-10-02", headers=headers).get_json()
        assert d["total"] == 1
        d = client.get(f"/api/saas/signals?strategy_id={sid}&page_size=1&page=2",
                       headers=headers).get_json()
        assert d["total"] == 2 and len(d["items"]) == 1
        assert client.get("/api/saas/signals?signal_type=bogus", headers=headers).status_code == 400
        assert client.get("/api/saas/signals", ).status_code == 401

    def test_unread_and_mark_read(self, client, app):
        headers, _ = self._seed_events(client, app)
        d = client.get("/api/saas/signals/unread-count", headers=headers).get_json()
        assert d["unread"] == 2  # 从未读过 → 全部未读
        client.post("/api/saas/signals/mark-read", json={}, headers=headers)
        d = client.get("/api/saas/signals/unread-count", headers=headers).get_json()
        assert d["unread"] == 0

    def test_detail_watch_fields(self, client, app):
        headers, sid = self._seed_events(client, app)
        det = client.get(f"/api/saas/strategies/{sid}/detail", headers=headers).get_json()
        assert det["watch"]["scope_type"] == "custom"
        assert det["recent_signals_7d"] == 2  # 信号日期 10-01/02 在最近 7 天内


class TestScanScript:
    """deploy/saas/signal_scan.py 纯函数（合成面板，无 DB 无网络）。"""

    @staticmethod
    def _load():
        import importlib.util
        from pathlib import Path
        path = Path(__file__).resolve().parents[1] / "deploy" / "saas" / "signal_scan.py"
        spec = importlib.util.spec_from_file_location("signal_scan", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_parse_signal_spec(self):
        spec = self._load().parse_signal_spec(YAML_TEXT)
        assert "ema_5" in spec["entry"] and spec["exit"] == "rsi_14 > 70"
        assert spec["factor_fields"]["ema_5"] == "factors.stock_daily_overlap_close.ema_5"

    def test_compute_signals_correctness(self):
        import pandas as pd
        compute_signals = self._load().compute_signals
        # A 股：close [10,11,12]，ema_5 [12,11,11]→ d2 上穿？构造 entry: ema_5 > close
        # shift 口径：B 股验证不跨股票边界（B 的首行 shift 不应取 A 的末行）
        panel = pd.DataFrame({
            "ts_code": ["A", "A", "A", "B", "B", "B"],
            "trade_date": pd.to_datetime(["2026-09-28", "2026-09-29", "2026-09-30"] * 2),
            "close": [10.0, 11.0, 12.0, 20.0, 19.0, 18.0],
            "ema_5": [12.0, 11.0, 13.0, 25.0, 19.5, 17.0],
        })
        import datetime as _dt
        d = _dt.date(2026, 9, 30)
        # entry: 上穿 = (ema_5 > close) and (ema_5.shift(1) <= close.shift(1))
        hits = compute_signals(panel, "(ema_5 > close) and (ema_5.shift(1) <= close.shift(1))", d)
        assert hits == ["A"]  # A：9-29 (11<=11) → 9-30 (13>12) 上穿；B：19.5>19 且 25>20 非上穿
        # 空信号：条件成立但不在信号日 / 恒假表达式
        assert compute_signals(panel, "close > 1000", d) == []
        assert compute_signals(panel, "ema_5 > close", _dt.date(2026, 9, 27)) == []
