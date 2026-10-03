"""R3 切片1：worker 实时状态上报 + 管理台展示测试（真实本地 PG 临时库）。

覆盖：POST /api/worker/status 鉴权（401/503）与入参校验、上报后
console overview workers_detail 透出槽位/内存数据、旧 worker（status NULL）
降级、缺 status 列旧库懒自愈 ALTER。
fixture 复制 test_gui_saas_console.py 的临时库模式。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import _WORKER_STATUS_ENSURED

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}

STATUS_BODY = {
    "worker_id": "home-worker",
    "mem_available_mb": 18324.5,
    "mem_total_mb": 31744.0,
    "slots": [
        {"name": "light-1", "kind": "light", "busy": True, "job_id": 42},
        {"name": "light-2", "kind": "light", "busy": False, "job_id": None},
        {"name": "heavy-1", "kind": "heavy", "busy": False, "job_id": None},
    ],
    "limits": {"light_slots": 2, "heavy_slots": 1,
               "light_min_avail_mb": 2000.0, "heavy_min_avail_mb": 6500.0},
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
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


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
                          "factor_requests, workers RESTART IDENTITY CASCADE"))


def _admin_headers(app, email="admin@example.com"):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        uid = conn.execute(
            text("INSERT INTO users (email, role) VALUES (:e, 'admin') RETURNING id"),
            {"e": email},
        ).scalar_one()
    return {"X-User-Id": str(uid)}


class TestWorkerStatusAuth:
    def test_bad_token_401(self, client):
        resp = client.post("/api/worker/status", json=STATUS_BODY,
                           headers={"X-Worker-Token": "wrong"})
        assert resp.status_code == 401

    def test_no_token_configured_503(self, saas_db, monkeypatch):
        monkeypatch.delenv("SAAS_WORKER_TOKEN", raising=False)
        app = create_saas_app()
        app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app.config["SAAS_WORKER_TOKEN"] = None
        try:
            resp = app.test_client().post("/api/worker/status", json=STATUS_BODY,
                                          headers=WORKER_HEADERS)
            assert resp.status_code == 503
        finally:
            engine = app.extensions.get("saas_engine")
            if engine is not None:
                engine.dispose()

    def test_missing_worker_id_400(self, client):
        body = {k: v for k, v in STATUS_BODY.items() if k != "worker_id"}
        assert client.post("/api/worker/status", json=body,
                           headers=WORKER_HEADERS).status_code == 400

    def test_bad_slots_type_400(self, client):
        body = {**STATUS_BODY, "slots": "not-a-list"}
        assert client.post("/api/worker/status", json=body,
                           headers=WORKER_HEADERS).status_code == 400


class TestWorkerStatusReport:
    def test_report_persists_and_refreshes_heartbeat(self, client, app):
        resp = client.post("/api/worker/status", json=STATUS_BODY, headers=WORKER_HEADERS)
        assert resp.get_json()["ok"] is True
        engine = app.extensions["saas_engine"]
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT last_heartbeat_at, status, status_at FROM workers WHERE name = 'home-worker'")
            ).mappings().one()
        assert row["last_heartbeat_at"] is not None and row["status_at"] is not None
        assert row["status"]["slots"][0]["job_id"] == 42
        assert row["status"]["limits"]["light_slots"] == 2

    def test_overview_workers_detail(self, client, app):
        headers = _admin_headers(app)
        client.post("/api/worker/status", json=STATUS_BODY, headers=WORKER_HEADERS)
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["ok"]
        assert len(d["workers_detail"]) == 1
        w = d["workers_detail"][0]
        assert w["name"] == "home-worker" and w["online"] is True
        assert w["mem_available_mb"] == pytest.approx(18324.5)
        assert w["mem_total_mb"] == pytest.approx(31744.0)
        assert len(w["slots"]) == 3
        busy = [s for s in w["slots"] if s["busy"]]
        assert len(busy) == 1 and busy[0]["job_id"] == 42 and busy[0]["kind"] == "light"
        assert w["limits"]["heavy_slots"] == 1
        assert w["status_at"] is not None and w["last_heartbeat_at"] is not None

    def test_legacy_worker_null_status_degrades(self, client, app):
        # 旧 worker 只走 claim 心跳：status 列为 NULL，overview 降级为空槽位
        headers = _admin_headers(app)
        client.post("/api/worker/jobs/claim", json={"worker_id": "old-worker"},
                    headers=WORKER_HEADERS)
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        w = [x for x in d["workers_detail"] if x["name"] == "old-worker"][0]
        assert w["online"] is True
        assert w["mem_available_mb"] is None and w["mem_total_mb"] is None
        assert w["slots"] == [] and w["limits"] == {}
        assert w["status_at"] is None

    def test_lazy_alter_on_legacy_db(self, client, app):
        # 缺 status 列的旧库：首次上报触发懒自愈 ALTER
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE workers DROP COLUMN status"))
            conn.execute(text("ALTER TABLE workers DROP COLUMN status_at"))
        _WORKER_STATUS_ENSURED.discard(id(engine))
        resp = client.post("/api/worker/status", json=STATUS_BODY, headers=WORKER_HEADERS)
        assert resp.get_json()["ok"] is True
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT status FROM workers WHERE name = 'home-worker'")
            ).mappings().one()
        assert row["status"]["mem_total_mb"] == pytest.approx(31744.0)

    def test_overview_empty_workers_detail(self, client, app):
        headers = _admin_headers(app)
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["workers_detail"] == []


class TestConsolePageBlock:
    def test_console_page_has_worker_resource_block(self, client):
        resp = client.get("/saas/console")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "ov-worker-res" in html and "Worker 资源" in html
        assert "workers_detail" in html
