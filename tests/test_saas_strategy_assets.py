"""CR-2026-10-04 模块一：策略资产化（entry_mode/wizard_state + 详情页）测试。

覆盖：新列懒自愈 ALTER + 存量推断、保存/upsert 落模式与快照、job 提交链路落模式、
详情 API 权限（401/404/200）与历史回测列表、详情页面结构。fixture 复制
test_gui_saas_console.py 的临时库模式。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import _STRATEGY_ASSET_ENSURED

WIZARD_STATE = {
    "entry": {"groups": [{"comb": "and", "conds": [
        {"left": "ema_5", "op": "crosses_above", "fixed": None, "right": "ema_200"}]}],
              "dividers": []},
    "exit": {"groups": [{"comb": "and", "conds": [
        {"left": "rsi_14", "op": ">", "fixed": "70", "right": None}]}],
             "dividers": []},
}


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
    app.config["SAAS_WORKER_TOKEN"] = "t"
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
                          "factor_requests, workers, worker_configs RESTART IDENTITY CASCADE"))


def _user(app, uid=1):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id, email) VALUES (:i, :e) ON CONFLICT (id) DO NOTHING"),
                     {"i": uid, "e": f"u{uid}@e.c"})
    return {"X-User-Id": str(uid)}


def _save(client, headers, **kw):
    body = {"name": "s1", "yaml": "signal:\n  entry: 'true'\n"}
    body.update(kw)
    return client.post("/api/saas/strategies", json=body, headers=headers)


class TestLazyColumns:
    def test_lazy_alter_and_legacy_inference(self, client, app):
        # 缺列旧库：插入两条存量策略（一条有 nl_text 一条没有），访问列表触发懒自愈 + 推断
        engine = app.extensions["saas_engine"]
        _user(app)
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE strategies DROP COLUMN entry_mode"))
            conn.execute(text("ALTER TABLE strategies DROP COLUMN wizard_state"))
        _STRATEGY_ASSET_ENSURED.discard(id(engine))
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO strategies (user_id, name, nl_text, yaml) VALUES "
                "(1, 'has_nl', '5日线上穿20日线', 'y: 1'), (1, 'no_nl', NULL, 'y: 1')"))
        d = client.get("/api/saas/strategies", headers={"X-User-Id": "1"}).get_json()
        assert d["ok"]
        modes = {s["name"]: s["entry_mode"] for s in d["strategies"]}
        assert modes == {"has_nl": "nl", "no_nl": "yaml"}


class TestSaveEntryMode:
    def test_save_wizard_with_snapshot(self, client, app):
        headers = _user(app)
        d = _save(client, headers, entry_mode="wizard", wizard_state=WIZARD_STATE).get_json()
        assert d["ok"] and not d["updated"]
        g = client.get("/api/saas/strategies/1", headers=headers).get_json()
        assert g["strategy"]["entry_mode"] == "wizard"
        assert g["strategy"]["wizard_state"]["entry"]["groups"][0]["conds"][0]["left"] == "ema_5"

    def test_invalid_entry_mode_400(self, client, app):
        headers = _user(app)
        assert _save(client, headers, entry_mode="bogus").status_code == 400

    def test_upsert_keeps_snapshot_when_not_provided(self, client, app):
        headers = _user(app)
        _save(client, headers, entry_mode="wizard", wizard_state=WIZARD_STATE)
        d = _save(client, headers, entry_mode="wizard").get_json()  # 不带快照更新
        assert d["updated"] is True
        g = client.get("/api/saas/strategies/1", headers=headers).get_json()
        assert g["strategy"]["wizard_state"] is not None  # COALESCE 保留旧快照

    def test_infer_from_nl_text(self, client, app):
        headers = _user(app)
        _save(client, headers, nl_text="均线金叉买入")  # 不显式传 entry_mode
        g = client.get("/api/saas/strategies/1", headers=headers).get_json()
        assert g["strategy"]["entry_mode"] == "nl"


class TestJobSubmitEntryMode:
    def test_create_job_stores_mode_and_snapshot(self, client, app):
        headers = _user(app)
        d = client.post("/api/saas/jobs", json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "smoke",
            "params": {"codes": ["000001"], "start": "2025-01-01", "end": "2025-06-01"},
            "name": "wz1", "entry_mode": "wizard", "wizard_state": WIZARD_STATE,
        }, headers=headers).get_json()
        assert d["ok"], d
        g = client.get(f"/api/saas/strategies/{d['strategy_id']}", headers=headers).get_json()
        assert g["strategy"]["entry_mode"] == "wizard"
        assert g["strategy"]["wizard_state"]["exit"]["groups"][0]["conds"][0]["fixed"] == "70"


class TestDetailApi:
    def _seed(self, client, app):
        headers = _user(app)
        _save(client, headers, entry_mode="nl", nl_text="原文")
        for i in range(2):
            client.post("/api/saas/jobs", json={
                "yaml": "signal:\n  entry: 'true'\n", "kind": "smoke",
                "params": {"codes": ["000001", "600519"], "start": "2025-01-01", "end": "2025-06-01"},
                "name": "s1", "entry_mode": "nl", "nl_text": "原文",
            }, headers=headers)
        return headers

    def test_guest_401(self, client):
        assert client.get("/api/saas/strategies/1/detail").status_code == 401

    def test_other_user_404(self, client, app):
        headers = self._seed(client, app)
        _user(app, uid=2)
        assert client.get("/api/saas/strategies/1/detail",
                          headers={"X-User-Id": "2"}).status_code == 404

    def test_detail_with_history(self, client, app):
        headers = self._seed(client, app)
        d = client.get("/api/saas/strategies/1/detail", headers=headers).get_json()
        assert d["ok"]
        assert d["strategy"]["entry_mode"] == "nl" and d["strategy"]["nl_text"] == "原文"
        assert len(d["jobs"]) == 2
        j = d["jobs"][0]
        assert j["status"] == "queued" and j["symbol_count"] == 2
        assert j["date_start"] == "2025-01-01"


class TestDetailPage:
    def test_page_structure(self, client):
        resp = client.get("/saas/strategies/1")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "sd-main" in html and "sd-src-nl" in html and "sd-src-wizard" in html
        assert "sd-src-yaml" in html and "sd-jobs-tbody" in html
        assert "sd-watch-card" in html  # 模块二：信号监控卡
        assert "/detail" in html
