"""QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片）：运行态响应契约 + 游客取消矩阵。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql）。覆盖：
1. GET /api/jobs/<id> 在 queue_position 之外补充 worker_online（布尔，不泄露
   worker 名称/地址/资源）；queue_position 仅 queued 有。
2. /api/results/<id>/summary 的 409 体按现有任务数据增补 queue_position（仅
   queued）、worker_online、strategy_id、error_class、error_message、
   cancel_requested；failed 返回真实 error_message/error_class。
3. 409/取消的权限语义不变：匿名 401、其他用户 404、不存在与本人/他人错误体
   一致（不泄露存在性）、showcase verified 公开只读不变。
4. 游客取消复用 P0-2 qre_guest_sid/guest_key 归属：同会话可取消（queued 直接
   canceled、running 置 cancel_requested），异会话/无 Cookie 401，登录用户他人
   404，终态 409。
不启动真实 worker、不跑真实回测：running/failed 全部由 worker 协议端点模拟。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}
IP_A = "1.2.3.4"
IP_B = "9.9.9.9"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_first_ux_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
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
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "workers RESTART IDENTITY CASCADE"))


def _create_job(client, uid=1, kind="full", yaml_text="signal:\n  entry: 'true'\n", params=None):
    return client.post(
        "/api/saas/jobs",
        json={"yaml": yaml_text, "kind": kind, "params": params or {"cash": 1000000}, "name": "t"},
        headers={"X-User-Id": str(uid)},
    )


def _guest_submit(client, ip=IP_A, codes=("000001.SZ",), kind="full"):
    return client.post("/api/jobs", json={
        "yaml": "signal:\n  entry: true\n", "kind": kind,
        "params": {"codes": list(codes), "start": "2025-01-01", "end": "2026-01-01"},
    }, headers={"X-Forwarded-For": ip})


def _heartbeat(client, job_id, worker_id="w1"):
    return client.post(f"/api/worker/jobs/{job_id}/heartbeat",
                       json={"worker_id": worker_id, "progress": 10, "message": "回测中"},
                       headers=WORKER_HEADERS)


def _claim_and_run(client, job_id, worker_id="w1"):
    assert client.post("/api/worker/jobs/claim", json={"worker_id": worker_id},
                       headers=WORKER_HEADERS).status_code == 200
    assert _heartbeat(client, job_id, worker_id).status_code == 200


def _fail(client, job_id, worker_id="w1", error_class="strategy_compile_error",
          error_message="策略第 3 行 entry 表达式不合法", retryable=False):
    return client.post(f"/api/worker/jobs/{job_id}/fail",
                       json={"worker_id": worker_id, "error_class": error_class,
                             "error_message": error_message, "retryable": retryable},
                       headers=WORKER_HEADERS)


class TestJobRuntimeFields:
    """GET /api/jobs/<id>：queue_position（仅 queued）+ worker_online 布尔。"""

    def test_queued_reports_queue_position(self, client):
        ids = [_create_job(client).get_json()["job_id"] for _ in range(3)]
        body = client.get(f"/api/jobs/{ids[1]}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert body["status"] == "queued"
        assert body["queue_position"] == 1  # 前面还有第 1 个任务
        assert isinstance(body["worker_online"], bool)

    def test_running_has_no_queue_position_and_worker_online_true(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _claim_and_run(client, job_id)
        body = client.get(f"/api/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert body["status"] == "running"
        assert "queue_position" not in body  # 仅 queued 有排队位置
        assert body["worker_online"] is True  # 刚心跳 → 在线

    def test_worker_online_false_without_heartbeat(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        body = client.get(f"/api/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert body["worker_online"] is False

    def test_worker_online_false_when_stale(self, client, app):
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        with _get_engine(app).begin() as conn:
            conn.execute(text("INSERT INTO workers (name, last_heartbeat_at) "
                              "VALUES ('stale-w', now() - interval '10 minutes')"))
        job_id = _create_job(client).get_json()["job_id"]
        body = client.get(f"/api/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert body["worker_online"] is False

    def test_runtime_fields_do_not_leak_worker_details(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _claim_and_run(client, job_id, worker_id="home-secret-worker")
        body = client.get(f"/api/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        text = str(body.get("worker_online"))
        assert "home-secret-worker" not in str(body).replace(str(body.get("leased_by") or ""), "")
        assert text in ("True", "False")

    def test_guest_owner_sees_runtime_fields(self, client):
        job_id = _guest_submit(client).get_json()["job_id"]
        body = client.get(f"/api/jobs/{job_id}").get_json()["job"]
        assert body["status"] == "queued"
        assert body["queue_position"] == 0
        assert body["worker_online"] is False


class TestSummary409Contract:
    """/api/results/<id>/summary 未完成 409：运行态与真实失败原因。"""

    def test_queued_409_carries_runtime_fields(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        resp = client.get(f"/api/results/{job_id}/summary", headers={"X-User-Id": "1"})
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["ok"] is False
        assert body["status"] == "queued"
        assert body["queue_position"] == 0
        assert body["worker_online"] is False
        assert isinstance(body["strategy_id"], int)
        assert body["cancel_requested"] is False
        assert body["error_class"] is None and body["error_message"] is None
        assert "任务未完成（queued）" in body["error"]

    def test_failed_409_returns_real_error(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _claim_and_run(client, job_id)
        assert _fail(client, job_id).status_code == 200
        resp = client.get(f"/api/results/{job_id}/summary", headers={"X-User-Id": "1"})
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["status"] == "failed"
        assert body["error_class"] == "strategy_compile_error"
        assert body["error_message"] == "策略第 3 行 entry 表达式不合法"
        assert isinstance(body["strategy_id"], int)
        assert "queue_position" not in body  # 仅 queued

    def test_running_409_has_worker_online_but_no_queue_position(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _claim_and_run(client, job_id)
        body = client.get(f"/api/results/{job_id}/summary",
                          headers={"X-User-Id": "1"}).get_json()
        assert body["status"] == "running"
        assert body["worker_online"] is True
        assert "queue_position" not in body

    def test_409_permission_semantics_unchanged(self, client, app):
        job_id = _create_job(client).get_json()["job_id"]
        anon = app.test_client()
        missing = job_id + 9999
        # 匿名 401，且与不存在任务的错误体一致（不泄露存在性）
        assert anon.get(f"/api/results/{job_id}/summary").status_code == 401
        assert anon.get(f"/api/results/{missing}/summary").status_code == 401
        assert (anon.get(f"/api/results/{job_id}/summary").get_json()
                == anon.get(f"/api/results/{missing}/summary").get_json())
        # 其他用户 404，同样与不存在一致
        other = client.get(f"/api/results/{job_id}/summary", headers={"X-User-Id": "2"})
        other_missing = client.get(f"/api/results/{missing}/summary", headers={"X-User-Id": "2"})
        assert other.status_code == 404 and other_missing.status_code == 404
        assert other.get_json() == other_missing.get_json()
        # 本人 409（业务态）
        assert client.get(f"/api/results/{job_id}/summary",
                          headers={"X-User-Id": "1"}).status_code == 409

    def test_guest_owner_409_and_stranger_401(self, client, app):
        job_id = _guest_submit(client).get_json()["job_id"]
        owner = client.get(f"/api/results/{job_id}/summary")
        assert owner.status_code == 409
        assert owner.get_json()["queue_position"] == 0
        stranger = app.test_client()
        assert stranger.get(f"/api/results/{job_id}/summary",
                            headers={"X-Forwarded-For": IP_A}).status_code == 401

    def test_showcase_completed_readonly_unchanged(self, client, app):
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _ensure_signal_tables, _get_engine

        job_id = _create_job(client).get_json()["job_id"]
        _claim_and_run(client, job_id)
        client.post(f"/api/worker/jobs/{job_id}/result/meta",
                    json={"worker_id": "w1",
                          "summary": {"strategy_total_return": 0.2},
                          "chart_data": {"metrics": {}}, "files": []},
                    headers=WORKER_HEADERS)
        engine = _get_engine(app)
        _ensure_signal_tables(engine)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO showcase (job_id, title, subtitle, sort_order, is_active) "
                              "VALUES (:id, 't', 's', 1, true)"), {"id": job_id})
        anon = app.test_client()
        resp = anon.get(f"/api/results/{job_id}/summary")
        assert resp.status_code == 200
        assert resp.get_json()["readonly"] is True


class TestCancelMatrix:
    """取消端点：游客按会话归属；登录用户他人 404；终态 409。"""

    def test_logged_in_cancel_queued_and_running(self, client):
        q = _create_job(client).get_json()["job_id"]
        r = _create_job(client).get_json()["job_id"]
        resp = client.post(f"/api/jobs/{q}/cancel", headers={"X-User-Id": "1"})
        assert resp.status_code == 200 and resp.get_json()["status"] == "canceled"
        _claim_and_run(client, r)
        resp = client.post(f"/api/jobs/{r}/cancel", headers={"X-User-Id": "1"})
        assert resp.status_code == 200
        assert resp.get_json() == {"ok": True, "status": "running", "cancel_requested": True}
        assert _heartbeat(client, r).get_json()["cancel_requested"] is True

    def test_guest_same_session_can_cancel(self, client):
        queued = _guest_submit(client).get_json()["job_id"]
        resp = client.post(f"/api/jobs/{queued}/cancel")
        assert resp.status_code == 200 and resp.get_json()["status"] == "canceled"
        # 第二个任务用 smoke（不占游客每日 full 配额），走 worker 心跳进 running
        running = _guest_submit(client, codes=("600000.SH",), kind="smoke").get_json()["job_id"]
        _claim_and_run(client, running)
        resp = client.post(f"/api/jobs/{running}/cancel")
        assert resp.status_code == 200
        assert resp.get_json()["cancel_requested"] is True

    def test_guest_other_session_401(self, client, app):
        job_id = _guest_submit(client).get_json()["job_id"]
        stranger = app.test_client()
        resp = stranger.post(f"/api/jobs/{job_id}/cancel", headers={"X-Forwarded-For": IP_A})
        assert resp.status_code == 401
        # 与不存在任务的语义一致（不泄露存在性）
        missing = stranger.post(f"/api/jobs/{job_id + 9999}/cancel",
                                headers={"X-Forwarded-For": IP_A})
        assert missing.status_code == 401
        assert missing.get_json() == resp.get_json()

    def test_cookieless_cannot_cancel_legacy_session_job(self, client, app):
        """缺失会话 Cookie 的请求不得取消旧会话任务（哪怕同 IP）。"""
        job_id = _guest_submit(client).get_json()["job_id"]
        cookieless = app.test_client()
        resp = cookieless.post(f"/api/jobs/{job_id}/cancel", headers={"X-Forwarded-For": IP_A})
        assert resp.status_code == 401
        # 任务未被取消
        assert client.get(f"/api/jobs/{job_id}").get_json()["job"]["status"] == "queued"

    def test_guest_cannot_cancel_user_job(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        resp = client.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 401

    def test_logged_in_other_user_404_and_missing_matches(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        other = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-User-Id": "2"})
        missing = client.post(f"/api/jobs/{job_id + 9999}/cancel", headers={"X-User-Id": "2"})
        assert other.status_code == 404 and missing.status_code == 404
        assert other.get_json() == missing.get_json()

    def test_anonymous_missing_401(self, client, app):
        anon = app.test_client()
        resp = anon.post("/api/jobs/999999/cancel")
        assert resp.status_code == 401

    def test_terminal_cancel_409(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        assert client.post(f"/api/jobs/{job_id}/cancel", headers={"X-User-Id": "1"}).status_code == 200
        again = client.post(f"/api/jobs/{job_id}/cancel", headers={"X-User-Id": "1"})
        assert again.status_code == 409

    def test_guest_cancel_issues_cookie_when_missing(self, client, app):
        """无 Cookie 取消响应也带会话 Cookie（与 GET job 一致，便于后续轮询归属）。"""
        from http.cookies import SimpleCookie

        from quant_research_engine.gui.saas.app import GUEST_COOKIE_NAME

        job_id = _create_job(client).get_json()["job_id"]
        anon = app.test_client()
        resp = anon.post(f"/api/jobs/{job_id}/cancel")
        assert resp.status_code == 401
        jar = SimpleCookie()
        found = [raw for raw in resp.headers.get_all("Set-Cookie") or []
                 if GUEST_COOKIE_NAME in raw]
        assert found, "401 响应应顺手签发游客会话 Cookie"
        jar.load(found[0])
        assert jar[GUEST_COOKIE_NAME]["httponly"] is True
