"""QRE-SAAS-002 任务队列协议测试（真实本地 PG 临时库，schema 为 PG 方言）。

setUp：psql 以 van 身份经 unix socket 建临时库并 apply
deploy/saas/cloud_schema.sql；tearDown 关闭 engine 连接后 drop 库。
串行验证状态机（lease/heartbeat/result/过期重排/attempts 耗尽），
不并发测试 SKIP LOCKED 语义。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    schema = (
        subprocess.run(
            ["psql", f"postgresql:///{db_name}", "-v", "ON_ERROR_STOP=1",
             "-f", "deploy/saas/cloud_schema.sql"],
            check=True, capture_output=True, text=True,
        )
    )
    assert schema.returncode == 0
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture()
def app(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"  # 既有队列用例继续走 X-User-Id 后门
    app.config["SAAS_AUTH_CHANNEL"] = "stub"  # 验证码不真发，落 sent_codes
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
        from sqlalchemy import text
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))


def _create_job(client, uid=1, kind="full", yaml_text="signal:\n  entry: 'true'\n", params=None):
    return client.post(
        "/api/saas/jobs",
        json={"yaml": yaml_text, "kind": kind, "params": params or {"cash": 1000000}, "name": "t"},
        headers={"X-User-Id": str(uid)},
    )


def _lease(client, worker_id="w1"):
    return client.post("/api/saas/worker/jobs/lease", json={"worker_id": worker_id}, headers=WORKER_HEADERS)


def _result(client, job_id, body, worker_id="w1", token=WORKER_TOKEN):
    return client.post(
        f"/api/saas/worker/jobs/{job_id}/result",
        json={"worker_id": worker_id, **body},
        headers={"X-Worker-Token": token},
    )


class TestJobCreate:
    def test_create_auto_creates_placeholder_user(self, client):
        resp = _create_job(client, uid=7, kind="smoke")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] and body["status"] == "queued"
        detail = client.get(f"/api/saas/jobs/{body['job_id']}", headers={"X-User-Id": "7"}).get_json()["job"]
        assert detail["status"] == "queued"
        assert detail["kind"] == "smoke"
        assert detail["params"] == {"cash": 1000000}
        # 同一占位用户再次提交不报错（ON CONFLICT DO NOTHING）
        assert _create_job(client, uid=7).status_code == 200

    def test_create_validation(self, client):
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 401
        assert client.post("/api/saas/jobs", json={"kind": "full"}, headers={"X-User-Id": "1"}).status_code == 400
        assert _create_job(client, kind="bogus").status_code == 400
        assert client.post("/api/saas/jobs", json={"yaml": "x", "params": [1]},
                           headers={"X-User-Id": "1"}).status_code == 400

    def test_list_jobs_scoped_and_desc(self, client):
        _create_job(client, uid=1)
        _create_job(client, uid=1)
        _create_job(client, uid=2)
        jobs = client.get("/api/saas/jobs", headers={"X-User-Id": "1"}).get_json()["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["id"] > jobs[1]["id"]
        assert client.get("/api/saas/jobs", headers={"X-User-Id": "2"}).get_json()["jobs"][0]["user_id"] == 2
        assert client.get("/api/saas/jobs", headers={"X-User-Id": "99"}).get_json()["jobs"] == []

    def test_get_unknown_job_404(self, client):
        assert client.get("/api/saas/jobs/999").status_code == 401  # 未登录
        assert client.get("/api/saas/jobs/999", headers={"X-User-Id": "1"}).status_code == 404


class TestWorkerAuth:
    def test_wrong_token_401(self, client):
        _create_job(client)
        resp = client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"},
                           headers={"X-Worker-Token": "wrong"})
        assert resp.status_code == 401

    def test_token_unconfigured_503(self, app, client, monkeypatch):
        monkeypatch.delenv("SAAS_WORKER_TOKEN", raising=False)
        app.config["SAAS_WORKER_TOKEN"] = None
        resp = client.post("/api/saas/worker/jobs/lease", json={"worker_id": "w1"},
                           headers=WORKER_HEADERS)
        assert resp.status_code == 503

    def test_lease_requires_worker_id(self, client):
        resp = client.post("/api/saas/worker/jobs/lease", json={}, headers=WORKER_HEADERS)
        assert resp.status_code == 400


class TestLifecycle:
    def test_create_lease_heartbeat_done(self, client):
        job_id = _create_job(client).get_json()["job_id"]

        lease = _lease(client).get_json()
        assert lease["ok"] and lease["job"]["id"] == job_id
        assert lease["job"]["status"] == "leased"
        assert lease["job"]["attempts"] == 1
        assert lease["job"]["leased_by"] == "w1"
        assert lease["job"]["strategy"]["yaml"].startswith("signal:")
        first_expiry = lease["job"]["lease_expires_at"]
        assert first_expiry

        # 队列已空
        assert _lease(client).get_json()["job"] is None

        hb = client.post(f"/api/saas/worker/jobs/{job_id}/heartbeat",
                         json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        assert hb.status_code == 200
        assert hb.get_json()["lease_expires_at"] >= first_expiry
        # 他人心跳被拒
        assert client.post(f"/api/saas/worker/jobs/{job_id}/heartbeat",
                           json={"worker_id": "w2"}, headers=WORKER_HEADERS).status_code == 409

        resp = _result(client, job_id, {
            "status": "completed",
            "summary": {"total_return": 0.42},
            "chart_data": {"equity": [[1, 1.0]]},
            "artifacts": [{"kind": "excel", "oss_key": "k"}],
            "data_until": "2026-09-04",
        })
        assert resp.status_code == 200 and resp.get_json()["status"] == "completed"

        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "completed"
        assert detail["finished_at"]
        assert detail["result"]["summary"] == {"total_return": 0.42}
        assert detail["result"]["data_until"] == "2026-09-04"
        listed = client.get("/api/saas/jobs", headers={"X-User-Id": "1"}).get_json()["jobs"][0]
        assert listed["result_summary"] == {"total_return": 0.42}

    def test_result_wrong_worker_409_and_unknown_404(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        assert _result(client, job_id, {"status": "completed"}, worker_id="w2").status_code == 409
        assert _result(client, 999, {"status": "completed"}).status_code == 404
        assert _result(client, job_id, {"status": "bogus"}).status_code == 400

    def test_lease_expiry_requeues(self, client, app):
        from sqlalchemy import text

        job_id = _create_job(client).get_json()["job_id"]
        _lease(client, worker_id="w1")
        # Worker 宕机：lease 过期 → 可被其他 worker 重排
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"),
                         {"id": job_id})
        lease = _lease(client, worker_id="w2").get_json()
        assert lease["job"]["id"] == job_id
        assert lease["job"]["attempts"] == 2
        assert lease["job"]["leased_by"] == "w2"

    def test_failed_requeues_then_exhausts(self, client):
        job_id = _create_job(client).get_json()["job_id"]

        _lease(client)  # attempts=1
        resp = _result(client, job_id, {"status": "failed", "error": "boom"})
        assert resp.get_json()["status"] == "queued"  # attempts 1 < max 2 → 回队
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "queued" and detail["error_message"] == "boom"

        _lease(client)  # attempts=2
        resp = _result(client, job_id, {"status": "failed", "error": "boom again"})
        assert resp.get_json()["status"] == "failed"  # attempts 耗尽 → failed
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "failed"
        assert detail["error_message"] == "boom again"
        assert detail["finished_at"]
        # failed 任务不再被认领
        assert _lease(client).get_json()["job"] is None


class TestAuth:
    def _send_code(self, client, target="13800001111"):
        resp = client.post("/api/saas/auth/code", json={"target": target})
        assert resp.status_code == 200
        return resp

    def _code_for(self, app, target):
        sent = app.extensions["sent_codes"]
        matches = [m["code"] for m in sent if m["target"] == target]
        assert matches, "stub sender 未记录发出的验证码"
        return matches[-1]

    def _login(self, client, app, target="13800001111"):
        self._send_code(client, target)
        return client.post("/api/saas/auth/login",
                           json={"target": target, "code": self._code_for(app, target)})

    def test_full_flow_email_register_and_bearer(self, client, app):
        target = "user@example.com"
        resp = client.post("/api/saas/auth/code", json={"target": target})
        assert resp.get_json()["channel"] == "email"
        login = client.post("/api/saas/auth/login",
                            json={"target": target, "code": self._code_for(app, target)})
        assert login.status_code == 200
        body = login.get_json()
        assert body["ok"] and body["token"]
        assert body["user"]["email"] == target and body["user"]["phone"] is None
        token = body["token"]
        headers = {"Authorization": f"Bearer {token}"}

        me = client.get("/api/saas/me", headers=headers).get_json()["user"]
        assert me["email"] == target and me["quota_daily"] == 10

        created = client.post("/api/saas/jobs", json={"yaml": "x"}, headers=headers)
        assert created.status_code == 200
        jobs = client.get("/api/saas/jobs", headers=headers).get_json()["jobs"]
        assert jobs[0]["user_id"] == me["id"]

    def test_phone_channel_and_sms_target_column(self, client, app):
        login = self._login(client, app, "13912345678")
        assert login.status_code == 200
        user = login.get_json()["user"]
        assert user["phone"] == "13912345678" and user["email"] is None

    def test_wrong_code_401_and_code_single_use(self, client, app):
        target = "13800002222"
        self._send_code(client, target)
        good = self._code_for(app, target)
        bad_code = "000000" if good != "000000" else "000001"
        bad = client.post("/api/saas/auth/login", json={"target": target, "code": bad_code})
        assert bad.status_code == 401
        assert client.post("/api/saas/auth/login", json={"target": target, "code": good}).status_code == 200
        # 验证码一次性：复用失败
        assert client.post("/api/saas/auth/login", json={"target": target, "code": good}).status_code == 401

    def test_expired_code_401(self, client, app):
        from sqlalchemy import text

        target = "13800003333"
        self._send_code(client, target)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE sms_codes SET expires_at = now() - interval '1 minute' "
                              "WHERE phone = :t"), {"t": target})
        resp = client.post("/api/saas/auth/login",
                           json={"target": target, "code": self._code_for(app, target)})
        assert resp.status_code == 401

    def test_rate_limit_target_60s(self, client):
        target = "13800004444"
        assert client.post("/api/saas/auth/code", json={"target": target}).status_code == 200
        resp = client.post("/api/saas/auth/code", json={"target": target})
        assert resp.status_code == 429

    def test_rate_limit_ip_10_per_hour(self, client):
        for i in range(10):
            resp = client.post("/api/saas/auth/code", json={"target": f"138{i:08d}"},
                               environ_overrides={"REMOTE_ADDR": "9.9.9.9"})
            assert resp.status_code == 200
        resp = client.post("/api/saas/auth/code", json={"target": "13899999999"},
                           environ_overrides={"REMOTE_ADDR": "9.9.9.9"})
        assert resp.status_code == 429

    def test_send_failure_502(self, client, app):
        app.config["SAAS_AUTH_CHANNEL"] = "sms"
        resp = client.post("/api/saas/auth/code", json={"target": "13800005555"})
        assert resp.status_code == 502
        assert "短信通道未开通" in resp.get_json()["error"]

    def test_no_token_401(self, client):
        assert client.get("/api/saas/me").status_code == 401
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 401
        assert client.get("/api/saas/jobs").status_code == 401
        # 无效 token 401
        assert client.get("/api/saas/me",
                          headers={"Authorization": "Bearer bogus"}).status_code == 401

    def test_dev_backdoor_default_off(self, saas_db, monkeypatch):
        monkeypatch.delenv("SAAS_DEV_AUTH", raising=False)
        monkeypatch.delenv("SAAS_WORKER_TOKEN", raising=False)
        app2 = create_saas_app()
        app2.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app2.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
        c2 = app2.test_client()
        assert c2.post("/api/saas/jobs", json={"yaml": "x"},
                       headers={"X-User-Id": "1"}).status_code == 401

    def test_dev_backdoor_enabled(self, client):
        resp = client.post("/api/saas/jobs", json={"yaml": "x"}, headers={"X-User-Id": "42"})
        assert resp.status_code == 200

    def test_quota_429(self, client, app):
        from sqlalchemy import text

        login = self._login(client, app, "quota@example.com")
        token = login.get_json()["token"]
        uid = login.get_json()["user"]["id"]
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET quota_daily = 2 WHERE id = :uid"), {"uid": uid})
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/saas/jobs", json={"yaml": "x"}, headers=headers).status_code == 200
        assert client.post("/api/saas/jobs", json={"yaml": "x", "kind": "smoke"},
                           headers=headers).status_code == 200
        resp = client.post("/api/saas/jobs", json={"yaml": "x"}, headers=headers)
        assert resp.status_code == 429


class TestProtocolA2:
    """QRE-JOB-API：17 号协议对齐（claim 长轮询/心跳迁移/两步 result/fail 分类/取消/幂等/回收）。"""

    def test_claim_empty_is_200_null(self, client):
        resp = client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        assert resp.status_code == 200 and resp.get_json()["job"] is None

    def test_claim_returns_protocol_fields(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        job = client.post("/api/worker/jobs/claim", json={"worker_id": "w1"},
                          headers=WORKER_HEADERS).get_json()["job"]
        assert job["id"] == job_id and job["attempt"] == 1
        assert job["params_json"] == {"cash": 1000000}
        assert job["lease_expires_at"] and job["cancel_requested"] is False

    def test_heartbeat_progress_and_leased_to_running(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        hb = client.post(f"/api/worker/jobs/{job_id}/heartbeat",
                         json={"worker_id": "w1", "progress": 42, "message": "回测中"},
                         headers=WORKER_HEADERS).get_json()
        assert hb["ok"] and hb["cancel_requested"] is False
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "running"  # 首心跳驱动迁移
        assert detail["progress"] == 42 and detail["progress_message"] == "回测中"
        assert detail["heartbeat_at"]

    def test_result_two_step_with_files(self, client, tmp_path, app):
        import hashlib
        import io

        app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "uploads")
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        blob = b"trade_date,total_equity\n2026-01-05,100000\n"
        digest = hashlib.sha256(blob).hexdigest()
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {"total_return": 0.1},
                                 "chart_data": {}, "data_until": "2026-09-04",
                                 "files": [{"name": "equity_curve.csv", "size": len(blob), "sha256": digest}]},
                           headers=WORKER_HEADERS).get_json()
        assert meta["status"] == "uploading" and meta["upload_token"]
        token = meta["upload_token"]
        # 错误 token 401
        bad = client.post(f"/api/worker/jobs/{job_id}/result/files?upload_token=wrong",
                          data={"equity_curve.csv": (io.BytesIO(blob), "equity_curve.csv")},
                          headers=WORKER_HEADERS)
        assert bad.status_code == 401
        ok = client.post(f"/api/worker/jobs/{job_id}/result/files?upload_token={token}",
                         data={"equity_curve.csv": (io.BytesIO(blob), "equity_curve.csv")},
                         headers=WORKER_HEADERS).get_json()
        assert ok["status"] == "completed"
        assert (tmp_path / "uploads" / f"job_{job_id}" / "equity_curve.csv").read_bytes() == blob
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "completed" and detail["result"]["summary"]["total_return"] == 0.1

    def test_result_meta_empty_files_completes_immediately(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {}, "chart_data": {}, "files": []},
                           headers=WORKER_HEADERS).get_json()
        assert meta["status"] == "completed"

    def test_fail_non_retryable_goes_failed_directly(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)  # attempts=1 < max 2
        resp = client.post(f"/api/worker/jobs/{job_id}/fail",
                           json={"worker_id": "w1", "error_class": "strategy_compile_error",
                                 "error_message": "YAML 不合法"},
                           headers=WORKER_HEADERS).get_json()
        assert resp["status"] == "failed"  # 不可重试：不排队直接终态
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["error_class"] == "strategy_compile_error"

    def test_fail_bad_error_class_400(self, client):
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        resp = client.post(f"/api/worker/jobs/{job_id}/fail",
                           json={"worker_id": "w1", "error_class": "bogus"},
                           headers=WORKER_HEADERS)
        assert resp.status_code == 400

    def test_cancel_queued_direct_and_running_via_flag(self, client):
        # queued → 直接 canceled
        job1 = _create_job(client).get_json()["job_id"]
        resp = client.post(f"/api/jobs/{job1}/cancel", headers={"X-User-Id": "1"})
        assert resp.get_json()["status"] == "canceled"
        # running → cancel_requested，worker 心跳发现后 fail(canceled)
        job2 = _create_job(client).get_json()["job_id"]
        _lease(client)
        client.post(f"/api/worker/jobs/{job2}/heartbeat", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        resp = client.post(f"/api/jobs/{job2}/cancel", headers={"X-User-Id": "1"})
        assert resp.get_json()["cancel_requested"] is True
        hb = client.post(f"/api/worker/jobs/{job2}/heartbeat",
                         json={"worker_id": "w1"}, headers=WORKER_HEADERS).get_json()
        assert hb["cancel_requested"] is True
        # 终态取消 409；他人任务 404（job2 先置终态，避免回队干扰 job3 认领顺序）
        client.post(f"/api/worker/jobs/{job2}/fail",
                    json={"worker_id": "w1", "error_class": "strategy_compile_error",
                          "error_message": "canceled"}, headers=WORKER_HEADERS)
        job3 = _create_job(client).get_json()["job_id"]
        _lease(client)
        client.post(f"/api/saas/worker/jobs/{job3}/result",
                    json={"worker_id": "w1", "status": "done", "summary": {}, "chart_data": {}},
                    headers=WORKER_HEADERS)
        assert client.post(f"/api/jobs/{job3}/cancel", headers={"X-User-Id": "1"}).status_code == 409
        assert client.post(f"/api/jobs/{job2}/cancel", headers={"X-User-Id": "2"}).status_code == 404

    def test_idempotency_key_dedup(self, client):
        r1 = client.post("/api/jobs", json={"yaml": "x", "kind": "smoke",
                                            "idempotency_key": "abc-1"}, headers={"X-User-Id": "1"})
        r2 = client.post("/api/jobs", json={"yaml": "x", "kind": "smoke",
                                            "idempotency_key": "abc-1"}, headers={"X-User-Id": "1"})
        assert r1.get_json()["job_id"] == r2.get_json()["job_id"]
        assert r2.get_json()["deduped"] is True

    def test_lease_reaped_by_claim(self, client, app):
        from sqlalchemy import text

        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' WHERE id = :id"),
                         {"id": job_id})
        # claim 惰性回收：过期任务回队后可被重新认领
        job = client.post("/api/worker/jobs/claim", json={"worker_id": "w2"},
                          headers=WORKER_HEADERS).get_json()["job"]
        assert job["id"] == job_id and job["attempt"] == 2

    def test_hard_timeout_expires_smoke(self, client, app):
        from sqlalchemy import text

        job_id = _create_job(client, kind="smoke").get_json()["job_id"]
        _lease(client)
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET started_at = now() - interval '11 minutes', "
                              "lease_expires_at = now() + interval '10 minutes' WHERE id = :id"),
                         {"id": job_id})
        # 下次 claim 的惰性回收把超硬超时的 smoke 置 expired（租约未过期也要杀）
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "expired"
