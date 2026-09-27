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
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 403  # D1D2：匿名按游客校验（无单股参数）
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
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 403  # D1D2：匿名按游客校验（无单股参数）
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
                       headers={"X-User-Id": "1"}).status_code == 403  # D1D2：游客校验

    def test_dev_backdoor_enabled(self, client):
        resp = client.post("/api/saas/jobs", json={"yaml": "x"}, headers={"X-User-Id": "42"})
        assert resp.status_code == 200

    def test_quota_429(self, client, app):
        # D1D2 新口径：会员每日 3 次全量（kind=full），smoke 不占配额，超限 403
        login = self._login(client, app, "quota@example.com")
        token = login.get_json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        for _ in range(3):
            assert client.post("/api/saas/jobs", json={"yaml": "x"}, headers=headers).status_code == 200
        resp = client.post("/api/saas/jobs", json={"yaml": "x"}, headers=headers)
        assert resp.status_code == 403
        assert "3 次" in resp.get_json()["error"]
        # smoke 不占配额：超限后仍可提交 smoke
        assert client.post("/api/saas/jobs", json={"yaml": "x", "kind": "smoke"},
                           headers=headers).status_code == 200


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

    def test_result_files_nested_paths(self, client, tmp_path, app):
        """C5 修复：manifest 键含子目录（000001.SZ/trades.csv）时按完整相对路径匹配并保留子目录落盘。"""
        import hashlib
        import io as _io

        app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "uploads")
        job_id = _create_job(client).get_json()["job_id"]
        _lease(client)
        blob = b"date,pnl\n2026-01-01,1\n"
        digest = hashlib.sha256(blob).hexdigest()
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {"total_return": 0.1},
                                 "chart_data": {}, "data_until": "2026-09-04",
                                 "files": [{"name": "000001.SZ/trades.csv", "size": len(blob), "sha256": digest}]},
                           headers=WORKER_HEADERS).get_json()
        token = meta["upload_token"]
        ok = client.post(f"/api/worker/jobs/{job_id}/result/files?upload_token={token}",
                         data={"000001.SZ/trades.csv": (_io.BytesIO(blob), "000001.SZ/trades.csv")},
                         headers=WORKER_HEADERS).get_json()
        assert ok["status"] == "completed", ok
        assert (tmp_path / "uploads" / f"job_{job_id}" / "000001.SZ" / "trades.csv").read_bytes() == blob
        # 路径穿越仍拒绝
        job2 = _create_job(client).get_json()["job_id"]
        _lease(client, "w2")
        meta2 = client.post(f"/api/worker/jobs/{job2}/result/meta",
                            json={"worker_id": "w2", "summary": {"total_return": 0.1}, "chart_data": {},
                                  "data_until": "2026-09-04",
                                  "files": [{"name": "a.csv", "size": 1, "sha256": "x"}]},
                            headers=WORKER_HEADERS).get_json()
        resp = client.post(f"/api/worker/jobs/{job2}/result/files?upload_token={meta2['upload_token']}",
                           data={"../evil.csv": (_io.BytesIO(b"x"), "../evil.csv")},
                           headers=WORKER_HEADERS)
        assert resp.status_code == 400
        assert not (tmp_path / "uploads" / "evil.csv").exists()

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


class TestResultsApi:
    """QRE-SAAS-RESULTS（B1+B2）：列表/详情/删除/未完成语义。"""

    def _completed_job(self, client, app, tmp_path, name="s", excess=0.1):
        """建 job → claim → meta 回传（含 chart_data.metrics.excess_return）→ completed。"""
        import json as _json

        resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "name": name,
                                              "params": {"start": "2026-01-01", "end": "2026-03-01"}},
                           headers={"X-User-Id": "1"})
        job_id = resp.get_json()["job_id"]
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        chart = {"metrics": {"excess_return": excess}, "dates": ["2026-01-05"],
                 "equity": [1.0], "tag_analysis": {"ok": True, "layers": {"A": [
                     {"tag": "银行", "total_pnl": 100.0, "trades": 2, "win_rate": 0.5,
                      "avg_ret": 0.01, "symbols_total": 1, "symbols_truncated": False,
                      "symbols": [{"ts_code": "000001.SZ", "name": "平安银行", "total_pnl": 100.0,
                                   "trades": 2, "win_rate": 0.5, "avg_ret": 0.01}]}]}}}
        client.post(f"/api/worker/jobs/{job_id}/result/meta",
                    json={"worker_id": "w1",
                          "summary": {"strategy_total_return": 0.2, "win_rate": 0.5,
                                      "max_drawdown": -0.1, "total_trade_count": 5,
                                      "symbol_count": 20},
                          "chart_data": chart, "data_until": "2026-02-27", "files": []},
                    headers=WORKER_HEADERS)
        return job_id

    def test_list_sort_pagination(self, client, app, tmp_path):
        j1 = self._completed_job(client, app, tmp_path, name="a", excess=0.3)
        j2 = self._completed_job(client, app, tmp_path, name="b", excess=0.1)
        resp = client.get("/api/results", headers={"X-User-Id": "1"}).get_json()
        assert resp["ok"] and resp["total"] == 2
        item = resp["items"][0]
        for key in ("strategy_name", "status", "date_start", "date_end", "symbol_count",
                    "excess_return", "max_drawdown", "win_rate", "total_trade_count",
                    "data_until", "created_at"):
            assert key in item
        assert item["excess_return"] == 0.1  # created_at 倒序，最新在前
        # 超额升序
        asc = client.get("/api/results?sort=excess_return&order=asc",
                         headers={"X-User-Id": "1"}).get_json()
        assert [i["excess_return"] for i in asc["items"]] == [0.1, 0.3]
        # 分页
        p1 = client.get("/api/results?page=1&page_size=1", headers={"X-User-Id": "1"}).get_json()
        assert p1["total"] == 2 and len(p1["items"]) == 1
        # 用户隔离
        assert client.get("/api/results", headers={"X-User-Id": "2"}).get_json()["total"] == 0
        # 未登录
        assert client.get("/api/results").status_code == 401

    def test_list_symbol_count_fallback(self, client, app, tmp_path):
        """symbol_count 兜底：summary 无该字段时按 params 推导（codes 数 / random_n / 全A=None）。"""
        import json as _json

        uid_seq = iter(range(100, 110))

        def mk(params):
            # 每个用例独立用户（D1D2 会员每日 3 次全量配额下避免互相挤占）
            uid = next(uid_seq)
            resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "name": "s",
                                                  "params": params},
                               headers={"X-User-Id": str(uid)})
            job_id = resp.get_json()["job_id"]
            client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
            client.post(f"/api/worker/jobs/{job_id}/result/meta",
                        json={"worker_id": "w1",
                              "summary": {"strategy_total_return": 0.1},  # 无 symbol_count
                              "chart_data": {"metrics": {}}, "data_until": "2026-02-27",
                              "files": []},
                        headers=WORKER_HEADERS)
            return uid

        uids = []
        uids.append(mk({"codes": ["000001.SZ"]}))
        uids.append(mk({"codes": "000001.SZ, 600519.SH"}))
        uids.append(mk({"random_n": 50}))
        uids.append(mk({}))  # 全 A
        # 列表按用户隔离：逐用户取自己的唯一一条记录验证兜底
        counts = []
        none_count = 0
        for uid in uids:
            items = client.get("/api/results", headers={"X-User-Id": str(uid)}).get_json()["items"]
            assert len(items) == 1
            sc = items[0]["symbol_count"]
            if sc is None:
                none_count += 1
            else:
                counts.append(sc)
        assert sorted(counts) == [1, 2, 50]
        assert none_count == 1

    def test_detail_endpoints(self, client, app, tmp_path):
        job_id = self._completed_job(client, app, tmp_path)
        h = {"X-User-Id": "1"}
        s = client.get(f"/api/results/{job_id}/summary", headers=h).get_json()
        assert s["summary"]["strategy_total_return"] == 0.2 and s["data_until"] == "2026-02-27"
        cd = client.get(f"/api/results/{job_id}/chart-data", headers=h).get_json()
        assert cd["metrics"]["excess_return"] == 0.1
        ta = client.get(f"/api/results/{job_id}/tag-analysis", headers=h).get_json()
        assert ta["layers"]["A"][0]["tag"] == "银行"
        sy = client.get(f"/api/results/{job_id}/symbols", headers=h).get_json()
        assert sy["symbols"][0]["ts_code"] == "000001.SZ"
        ra = client.get(f"/api/results/{job_id}/risk-analysis", headers=h).get_json()
        assert ra["ok"] and ra["has_report"] is False  # 产物无 risk_report.json
        # 个股无交易 → 404（格式合法但本次回测未交易）；格式非法 → 400 友好报错（SYMBOL-UX）
        d404 = client.get(f"/api/results/{job_id}/symbols/000002.SZ", headers=h)
        assert d404.status_code == 404
        d400 = client.get(f"/api/results/{job_id}/symbols/999999.XH", headers=h)
        assert d400.status_code == 400

    def test_unfinished_and_foreign_semantics(self, client, app, tmp_path):
        # 未完成（queued）→ 409；他人 → 404；不存在 → 404
        resp = client.post("/api/jobs", json={"yaml": "x", "kind": "full"}, headers={"X-User-Id": "1"})
        job_id = resp.get_json()["job_id"]
        r = client.get(f"/api/results/{job_id}/chart-data", headers={"X-User-Id": "1"})
        assert r.status_code == 409 and r.get_json()["status"] == "queued"
        assert client.get(f"/api/results/{job_id}/chart-data", headers={"X-User-Id": "2"}).status_code == 404
        assert client.get("/api/results/999/chart-data", headers={"X-User-Id": "1"}).status_code == 404
        assert client.get(f"/api/results/{job_id}/chart-data").status_code == 401

    def test_delete(self, client, app, tmp_path):
        app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "uploads")
        job_id = self._completed_job(client, app, tmp_path)
        job_dir = tmp_path / "uploads" / f"job_{job_id}"
        job_dir.mkdir(parents=True)
        (job_dir / "equity_curve.csv").write_text("x", encoding="utf-8")
        h = {"X-User-Id": "1"}
        assert client.delete(f"/api/results/{job_id}", headers=h).get_json()["ok"]
        assert not job_dir.exists()
        assert client.get(f"/api/results/{job_id}/summary", headers=h).status_code == 404
        # 重复删除 404；他人删除 404
        assert client.delete(f"/api/results/{job_id}", headers=h).status_code == 404


class TestBuiltinTestAccount:
    """QRE-ECS-C4：内置测试账号（env 配置即凭证，SMTP 未配期间的联调通道）。"""

    def test_test_account_login(self, client, app):
        app.config["SAAS_TEST_ACCOUNT_EMAIL"] = "tester@local"
        app.config["SAAS_TEST_ACCOUNT_PASSWORD"] = "pw123"
        resp = client.post("/api/saas/auth/login",
                           json={"target": "tester@local", "code": "pw123"})
        assert resp.status_code == 200
        token = resp.get_json()["token"]
        me = client.get("/api/saas/me", headers={"Authorization": f"Bearer {token}"}).get_json()
        assert me["user"]["email"] == "tester@local"
        # 错密码仍 401
        assert client.post("/api/saas/auth/login",
                           json={"target": "tester@local", "code": "wrong"}).status_code == 401

    def test_test_account_disabled_by_default(self, client):
        resp = client.post("/api/saas/auth/login",
                           json={"target": "tester@local", "code": "pw123"})
        assert resp.status_code == 401


class TestTiersD1D2:
    """QRE-SAAS-D1D2：注册/密码登录/游客提交/会员配额/游客清理。"""

    def _register(self, client, email="m1@example.com", pw="abc12345"):
        return client.post("/api/saas/auth/register", json={"email": email, "password": pw})

    def test_register_and_password_login(self, client):
        resp = self._register(client)
        assert resp.status_code == 200 and resp.get_json()["token"]
        assert resp.get_json()["user"]["tier"] == "member"
        # 重复注册 409
        assert self._register(client).status_code == 409
        # 弱密码/坏邮箱 400
        assert self._register(client, "m2@example.com", "short").status_code == 400
        assert self._register(client, "not-an-email", "abc12345").status_code == 400
        assert self._register(client, "m3@example.com", "abcdefgh").status_code == 400  # 无数字
        # 密码登录（与验证码通道并存）
        ok = client.post("/api/saas/auth/login", json={"target": "m1@example.com", "code": "abc12345"})
        assert ok.status_code == 200 and ok.get_json()["token"]
        bad = client.post("/api/saas/auth/login", json={"target": "m1@example.com", "code": "wrong123"})
        assert bad.status_code == 401

    def _guest_job(self, client, codes=("000001.SZ",), start="2025-01-01", end="2026-01-01", ip="1.2.3.4"):
        return client.post("/api/jobs", json={
            "yaml": "x", "kind": "full",
            "params": {"codes": list(codes), "start": start, "end": end},
        }, headers={"X-Forwarded-For": ip})

    def test_guest_submit_and_limits(self, client):
        resp = self._guest_job(client)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["guest"] is True and "次日清空" in body["note"]
        # 同 IP 当日第二次全量 → 403
        assert self._guest_job(client).status_code == 403
        # smoke 不占配额
        smoke = client.post("/api/jobs", json={"yaml": "x", "kind": "smoke",
            "params": {"codes": ["000001.SZ"], "start": "2025-01-01", "end": "2026-01-01"}},
            headers={"X-Forwarded-For": "1.2.3.4"})
        assert smoke.status_code == 200
        # 多股 → 403；区间超 2 年 → 403；缺区间 → 400
        assert self._guest_job(client, codes=("000001.SZ", "600000.SH"), ip="5.6.7.8").status_code == 403
        assert self._guest_job(client, start="2020-01-01", end="2026-01-01", ip="5.6.7.8").status_code == 403
        bad = client.post("/api/jobs", json={"yaml": "x", "kind": "full", "params": {"codes": ["000001.SZ"]}},
                          headers={"X-Forwarded-For": "5.6.7.8"})
        assert bad.status_code == 400

    def test_guest_views_own_job_by_ip(self, client, app):
        job_id = self._guest_job(client).get_json()["job_id"]
        # 同 IP 可查；异 IP 401
        ok = client.get(f"/api/jobs/{job_id}", headers={"X-Forwarded-For": "1.2.3.4"})
        assert ok.status_code == 200
        assert client.get(f"/api/jobs/{job_id}", headers={"X-Forwarded-For": "9.9.9.9"}).status_code == 401
        # worker 完成 → 游客按 IP 看结果端点
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        client.post(f"/api/worker/jobs/{job_id}/result/meta",
                    json={"worker_id": "w1", "summary": {"strategy_total_return": 0.1},
                          "chart_data": {"metrics": {"excess_return": 0.05}}, "files": []},
                    headers=WORKER_HEADERS)
        r = client.get(f"/api/results/{job_id}/summary", headers={"X-Forwarded-For": "1.2.3.4"})
        assert r.status_code == 200 and r.get_json()["summary"]["strategy_total_return"] == 0.1
        assert client.get(f"/api/results/{job_id}/summary",
                          headers={"X-Forwarded-For": "9.9.9.9"}).status_code == 401
        # 游客结果不在会员列表口径之外泄漏：/api/results 需登录
        assert client.get("/api/results", headers={"X-Forwarded-For": "1.2.3.4"}).status_code == 401

    def test_me_quota_fields(self, client):
        resp = self._register(client, "q@example.com")
        token = resp.get_json()["token"]
        me = client.get("/api/saas/me", headers={"Authorization": f"Bearer {token}"}).get_json()["user"]
        assert me["quota_limit"] == 3 and me["quota_remaining"] == 3 and me["tier"] == "member"
        client.post("/api/saas/jobs", json={"yaml": "x"},
                    headers={"Authorization": f"Bearer {token}"})
        me = client.get("/api/saas/me", headers={"Authorization": f"Bearer {token}"}).get_json()["user"]
        assert me["quota_remaining"] == 2

    def test_guest_cleanup(self, app, tmp_path):
        from sqlalchemy import text as _text

        from quant_research_engine.gui.saas.cleanup import cleanup_guest_jobs

        engine = app.extensions["saas_engine"]
        upload = tmp_path / "uploads"
        (upload / "job_1").mkdir(parents=True)
        with engine.begin() as conn:
            sid = conn.execute(
                _text("INSERT INTO strategies (user_id, name, yaml) VALUES (NULL, 'g', 'y') RETURNING id")
            ).scalar_one()
            jid = conn.execute(
                _text("INSERT INTO jobs (user_id, strategy_id, kind, guest_key, created_at) "
                      "VALUES (NULL, :sid, 'full', 'k1', now() - interval '1 day') RETURNING id"),
                {"sid": sid},
            ).scalar_one()
            conn.execute(
                _text("INSERT INTO results (job_id, user_id, summary, chart_data) "
                      "VALUES (:j, NULL, '{}', '{}')"), {"j": jid}
            )
        # jobs.user_id NULL 但 results.user_id NOT NULL 参照 users——游客 results 行怎么写？
        result = cleanup_guest_jobs(app.config["SAAS_DB_URL"], upload)
        assert result["jobs"] == 1 and result["dirs"] == 1
        with engine.connect() as conn:
            assert conn.execute(_text("SELECT count(*) FROM jobs WHERE guest_key='k1'")).scalar_one() == 0
            assert conn.execute(_text("SELECT count(*) FROM results WHERE job_id=:j"),
                                {"j": jid}).scalar_one() == 0
            assert conn.execute(_text("SELECT count(*) FROM strategies WHERE user_id IS NULL")).scalar_one() == 0


class TestSaasMetadata:
    """QRE-SAAS-METADATA：因子目录/板块名单元数据文件优先，缺失回退本地库。"""

    def test_factors_and_universes_from_metadata_file(self, client, app, tmp_path):
        import json as _json

        meta = {
            "generated_at": "2026-09-26T00:00:00Z",
            "factors": [{"group": "momentum", "label": "动量",
                         "items": [{"table": "factors.t", "column": "rsi_14", "label": "RSI"}]}],
            "universes": [{"group": "sw1", "label": "申万一级行业",
                           "items": [{"key": "电子", "count": 618}]}],
            "all_a_count": 5531,  # QRE-SAAS-LARGE-UNIVERSE-GUARD
        }
        (tmp_path / "metadata.json").write_text(_json.dumps(meta), encoding="utf-8")
        app.config["SAAS_METADATA_PATH"] = str(tmp_path / "metadata.json")
        f = client.get("/api/saas/factors", headers={"X-User-Id": "1"})
        u = client.get("/api/saas/universes", headers={"X-User-Id": "1"})
        assert f.get_json()["groups"][0]["label"] == "动量"
        assert u.get_json()["groups"][0]["items"][0] == {"key": "电子", "count": 618}
        assert u.get_json()["generated_at"] == "2026-09-26T00:00:00Z"
        assert u.get_json()["all_a_count"] == 5531  # 大范围护栏估算全部 A 股数量
        # 元数据对游客开放（只读目录；配额在提交环节收口）
        assert client.get("/api/saas/universes").status_code == 200

    def test_universes_all_a_count_absent_degrades_to_none(self, client, app, tmp_path):
        """旧版元数据文件（无 all_a_count）照常可用，护栏字段降级 None 不报错。"""
        import json as _json

        meta = {
            "generated_at": "2026-09-26T00:00:00Z",
            "factors": [{"group": "momentum", "label": "动量",
                         "items": [{"table": "factors.t", "column": "rsi_14", "label": "RSI"}]}],
            "universes": [{"group": "sw1", "label": "申万一级行业",
                           "items": [{"key": "电子", "count": 618}]}],
        }
        (tmp_path / "metadata.json").write_text(_json.dumps(meta), encoding="utf-8")
        app.config["SAAS_METADATA_PATH"] = str(tmp_path / "metadata.json")
        u = client.get("/api/saas/universes", headers={"X-User-Id": "1"})
        assert u.status_code == 200
        assert u.get_json()["ok"] and u.get_json()["all_a_count"] is None


class TestStrategyLibrary:
    """QRE-SAAS-D3：我的策略库（CRUD/隔离/同名 upsert/引用禁删/回填读取）。"""

    def _save(self, client, name="s1", yaml="yaml-v1", uid="1"):
        return client.post("/api/saas/strategies", json={"name": name, "yaml": yaml},
                           headers={"X-User-Id": uid})

    def test_crud_and_isolation(self, client):
        r = self._save(client)
        assert r.status_code == 200 and r.get_json()["ok"]
        sid = r.get_json()["strategy_id"]
        # 同名 upsert（更新不新建）
        r2 = self._save(client, yaml="yaml-v2")
        assert r2.get_json()["strategy_id"] == sid and r2.get_json()["updated"] is True
        got = client.get(f"/api/saas/strategies/{sid}", headers={"X-User-Id": "1"}).get_json()
        assert got["strategy"]["yaml"] == "yaml-v2"
        # 列表
        lst = client.get("/api/saas/strategies", headers={"X-User-Id": "1"}).get_json()
        assert len(lst["strategies"]) == 1 and lst["strategies"][0]["job_count"] == 0
        # 隔离：他人不可见/不可读
        assert client.get("/api/saas/strategies", headers={"X-User-Id": "2"}).get_json()["strategies"] == []
        assert client.get(f"/api/saas/strategies/{sid}", headers={"X-User-Id": "2"}).status_code == 404
        # 未登录 401
        assert client.get("/api/saas/strategies").status_code == 401
        # 重命名 + 同名冲突 409
        self._save(client, name="s2")
        rn = client.post(f"/api/saas/strategies/{sid}/rename", json={"name": "s2"},
                         headers={"X-User-Id": "1"})
        assert rn.status_code == 409
        rn = client.post(f"/api/saas/strategies/{sid}/rename", json={"name": "s1-new"},
                         headers={"X-User-Id": "1"})
        assert rn.get_json()["ok"]
        # 无引用可删
        d = client.delete(f"/api/saas/strategies/{sid}", headers={"X-User-Id": "1"})
        assert d.get_json()["ok"]
        assert client.delete(f"/api/saas/strategies/{sid}", headers={"X-User-Id": "1"}).status_code == 404

    def test_submit_upserts_strategy_and_referenced_delete_blocked(self, client):
        # 提交回测自动入库：同名复用
        for _ in range(2):
            client.post("/api/jobs", json={"yaml": "y1", "kind": "smoke", "name": "my-strat"},
                        headers={"X-User-Id": "1"})
        lst = client.get("/api/saas/strategies", headers={"X-User-Id": "1"}).get_json()
        assert len(lst["strategies"]) == 1
        sid = lst["strategies"][0]["id"]
        assert lst["strategies"][0]["job_count"] == 2
        # 被 jobs 引用 → 禁删 409
        d = client.delete(f"/api/saas/strategies/{sid}", headers={"X-User-Id": "1"})
        assert d.status_code == 409 and "不允许删除" in d.get_json()["error"]
