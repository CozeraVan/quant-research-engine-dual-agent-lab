"""QRE-SAAS-ADMIN-E1E3 后台管理测试（真实本地 PG 临时库）。

覆盖：路由权限（401/403/200）、E1 总览指标、E2 用户列表/tier 调整/禁用恢复、
因子申请审核流转、E3 worker 在线状态/失败任务查看/重试/取消、管理台页面与禁链纪律。
fixture 复制 test_gui_saas.py 的临时库模式（TRUNCATE 列表加 workers）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

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


def _make_user(app, email, role="user", status="active", tier="member"):
    engine = app.extensions["saas_engine"]
    with engine.begin() as conn:
        return conn.execute(
            text("INSERT INTO users (email, role, status, tier) VALUES (:e, :r, :s, :t) RETURNING id"),
            {"e": email, "r": role, "s": status, "t": tier},
        ).scalar_one()


def _admin_headers(app, email="admin@example.com"):
    uid = _make_user(app, email, role="admin")
    return {"X-User-Id": str(uid)}, uid


def _create_job(client, uid=1, kind="full", yaml_text="signal:\n  entry: 'true'\n"):
    return client.post(
        "/api/saas/jobs",
        json={"yaml": yaml_text, "kind": kind, "params": {"cash": 1000000}, "name": "t"},
        headers={"X-User-Id": str(uid)},
    )


def _fail_job(client, uid=1):
    job_id = _create_job(client, uid=uid).get_json()["job_id"]
    client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
    client.post(f"/api/worker/jobs/{job_id}/fail",
                json={"worker_id": "w1", "error_class": "strategy_compile_error",
                      "error_message": "YAML 不合法"},
                headers=WORKER_HEADERS)
    return job_id


class TestAdminAuth:
    def test_unauthenticated_401(self, client):
        assert client.get("/api/saas/console/overview").status_code == 401
        assert client.get("/api/saas/console/users").status_code == 401
        assert client.get("/api/saas/console/factor-requests").status_code == 401
        assert client.get("/api/saas/console/workers").status_code == 401
        assert client.get("/api/saas/console/jobs").status_code == 401

    def test_member_forbidden_403(self, client, app):
        _make_user(app, "m@example.com")
        for url in ("/api/saas/console/overview", "/api/saas/console/users",
                    "/api/saas/console/factor-requests", "/api/saas/console/workers",
                    "/api/saas/console/jobs"):
            resp = client.get(url, headers={"X-User-Id": "1"})
            assert resp.status_code == 403, url
        assert client.post("/api/saas/console/users/1/tier", json={"tier": "paid"},
                           headers={"X-User-Id": "1"}).status_code == 403

    def test_admin_ok_and_me_is_admin(self, client, app):
        headers, _ = _admin_headers(app)
        assert client.get("/api/saas/console/overview", headers=headers).status_code == 200
        me = client.get("/api/saas/me", headers=headers).get_json()["user"]
        assert me["is_admin"] is True and me["role"] == "admin"
        _make_user(app, "m@example.com")
        me2 = client.get("/api/saas/me", headers={"X-User-Id": "2"}).get_json()["user"]
        assert me2["is_admin"] is False

    def test_admin_via_bearer_token(self, client, app):
        resp = client.post("/api/saas/auth/register",
                           json={"email": "boss@example.com", "password": "abc12345"})
        token = resp.get_json()["token"]
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE users SET role = 'admin' WHERE email = 'boss@example.com'"))
        assert client.get("/api/saas/console/overview",
                          headers={"Authorization": f"Bearer {token}"}).status_code == 200


class TestOverview:
    def test_metrics(self, client, app):
        headers, _ = _admin_headers(app)
        _create_job(client, uid=2)  # 排队中 ×1
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["ok"]
        assert d["users"]["total"] == 2  # admin + 占位用户
        assert d["jobs"]["total"] == 1 and d["jobs"]["today"] == 1
        assert d["jobs"]["queued"] == 0 and d["jobs"]["running"] == 1
        assert d["workers"]["online"] == 1 and d["workers"]["total"] == 1
        assert d["pending_factor_requests"] == 0
        assert d["jobs_today_success_rate"] is None  # 今日无终态
        assert "loadavg" in d["server"] and "disk" in d["server"]

    def test_queued_split_by_weight(self, client, app):
        # R2：队列深度按轻/重分级展示
        headers, _ = _admin_headers(app)
        client.post("/api/saas/jobs", json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "full",
            "params": {"codes": ["000001"], "start": "2025-01-01", "end": "2026-01-01"}, "name": "l"},
            headers={"X-User-Id": "2"})
        client.post("/api/saas/jobs", json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "full",
            "params": {"universe": {"group": "market", "key": "all"}}, "name": "h"},
            headers={"X-User-Id": "2"})
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["jobs"]["queued"] == 2
        assert d["jobs"]["queued_light"] == 1 and d["jobs"]["queued_heavy"] == 1


class TestUsers:
    def test_list_and_tier(self, client, app):
        headers, _ = _admin_headers(app)
        _create_job(client, uid=2)
        d = client.get("/api/saas/console/users", headers=headers).get_json()
        assert d["quota_limit"] == 3
        u2 = next(u for u in d["users"] if u["id"] == 2)
        assert u2["job_count"] == 1 and u2["used_today"] == 1 and u2["tier"] == "member"
        # 调 tier
        r = client.post("/api/saas/console/users/2/tier", json={"tier": "paid"}, headers=headers)
        assert r.get_json()["tier"] == "paid"
        u2 = next(u for u in client.get("/api/saas/console/users", headers=headers).get_json()["users"] if u["id"] == 2)
        assert u2["tier"] == "paid"
        # 非法 tier / 不存在用户
        assert client.post("/api/saas/console/users/2/tier", json={"tier": "guest"}, headers=headers).status_code == 400
        assert client.post("/api/saas/console/users/999/tier", json={"tier": "paid"}, headers=headers).status_code == 404

    def test_disable_and_enable(self, client, app):
        headers, admin_uid = _admin_headers(app)
        resp = client.post("/api/saas/auth/register",
                           json={"email": "bad@example.com", "password": "abc12345"})
        token = resp.get_json()["token"]
        uid = resp.get_json()["user"]["id"]
        bearer = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/saas/me", headers=bearer).status_code == 200
        # 禁用：既有 session 立即失效 + 再登录 403
        r = client.post(f"/api/saas/console/users/{uid}/status", json={"status": "disabled"}, headers=headers)
        assert r.get_json()["status"] == "disabled"
        assert client.get("/api/saas/me", headers=bearer).status_code == 401
        login = client.post("/api/saas/auth/login", json={"target": "bad@example.com", "code": "abc12345"})
        assert login.status_code == 403
        # 恢复：旧 session 复效
        r = client.post(f"/api/saas/console/users/{uid}/status", json={"status": "active"}, headers=headers)
        assert r.get_json()["ok"]
        assert client.get("/api/saas/me", headers=bearer).status_code == 200
        # 边界：不能禁用自己 / 非法状态 / 不存在用户
        assert client.post(f"/api/saas/console/users/{admin_uid}/status",
                           json={"status": "disabled"}, headers=headers).status_code == 400
        assert client.post(f"/api/saas/console/users/{uid}/status",
                           json={"status": "bogus"}, headers=headers).status_code == 400
        assert client.post("/api/saas/console/users/999/status",
                           json={"status": "disabled"}, headers=headers).status_code == 404


class TestFactorReview:
    def _submit(self, client, uid=3):
        return client.post("/api/saas/factor-requests",
                           json={"factors": ["rsi_99"], "strategy_name": "s"},
                           headers={"X-User-Id": str(uid)})

    def test_review_flow(self, client, app):
        headers, _ = _admin_headers(app)
        rid = self._submit(client).get_json()["id"]
        d = client.get("/api/saas/console/factor-requests", headers=headers).get_json()
        assert len(d["requests"]) == 1 and d["requests"][0]["status"] == "pending"
        assert d["requests"][0]["user_email"] is None  # 占位用户无邮箱
        # 批准
        r = client.post(f"/api/saas/console/factor-requests/{rid}/review",
                        json={"action": "approve", "note": "已排期入库"}, headers=headers)
        assert r.get_json()["status"] == "approved"
        d = client.get("/api/saas/console/factor-requests?status=approved", headers=headers).get_json()
        assert d["requests"][0]["note"] == "已排期入库" and d["requests"][0]["reviewed_at"]
        # 重复审核 409；非法 action 400
        assert client.post(f"/api/saas/console/factor-requests/{rid}/review",
                           json={"action": "reject"}, headers=headers).status_code == 409
        # 拒绝流转
        rid2 = self._submit(client, uid=4).get_json()["id"]
        r = client.post(f"/api/saas/console/factor-requests/{rid2}/review",
                        json={"action": "reject", "note": "数据源无此字段"}, headers=headers)
        assert r.get_json()["status"] == "rejected"
        assert client.post(f"/api/saas/console/factor-requests/{rid2}/review",
                           json={"action": "bogus"}, headers=headers).status_code == 400
        # 用户侧可见审核结果
        mine = client.get("/api/saas/factor-requests", headers={"X-User-Id": "4"}).get_json()
        assert mine["requests"][0]["status"] == "rejected"
        # 非法 status 过滤 400
        assert client.get("/api/saas/console/factor-requests?status=bogus", headers=headers).status_code == 400


class TestWorkers:
    def test_online_offline(self, client, app):
        headers, _ = _admin_headers(app)
        d = client.get("/api/saas/console/workers", headers=headers).get_json()
        assert d["workers"] == []
        _create_job(client, uid=2)
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"}, headers=WORKER_HEADERS)
        d = client.get("/api/saas/console/workers", headers=headers).get_json()
        w = d["workers"][0]
        assert w["name"] == "w1" and w["online"] is True and w["active_jobs"] == 1
        # 心跳停 4 分钟 → 离线
        engine = app.extensions["saas_engine"]
        with engine.begin() as conn:
            conn.execute(text("UPDATE workers SET last_heartbeat_at = now() - interval '4 minutes'"))
        d = client.get("/api/saas/console/workers", headers=headers).get_json()
        assert d["workers"][0]["online"] is False


class TestJobs:
    def test_failed_list_retry_cancel(self, client, app):
        headers, _ = _admin_headers(app)
        job_id = _fail_job(client, uid=2)
        # 失败任务默认列表（含错误摘要）
        d = client.get("/api/saas/console/jobs", headers=headers).get_json()
        j = d["jobs"][0]
        assert j["id"] == job_id and j["status"] == "failed"
        assert j["error_class"] == "strategy_compile_error" and j["error_message"] == "YAML 不合法"
        # 重试：回队 + attempts 清零 + 错误清空
        r = client.post(f"/api/saas/console/jobs/{job_id}/retry", headers=headers)
        assert r.get_json()["status"] == "queued"
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "2"}).get_json()["job"]
        assert detail["status"] == "queued" and detail["attempts"] == 0 and detail["error_message"] is None
        # 重试非终态 409；不存在 409
        assert client.post(f"/api/saas/console/jobs/{job_id}/retry", headers=headers).status_code == 409
        assert client.post("/api/saas/console/jobs/999/retry", headers=headers).status_code == 409
        # 取消排队任务 → canceled；终态再取消 409；重试已取消 → queued
        r = client.post(f"/api/saas/console/jobs/{job_id}/cancel", headers=headers)
        assert r.get_json()["status"] == "canceled"
        assert client.post(f"/api/saas/console/jobs/{job_id}/cancel", headers=headers).status_code == 409
        assert client.post("/api/saas/console/jobs/999/cancel", headers=headers).status_code == 404
        assert client.post(f"/api/saas/console/jobs/{job_id}/retry", headers=headers).get_json()["status"] == "queued"
        # 非法 status 过滤 400
        assert client.get("/api/saas/console/jobs?status=bogus", headers=headers).status_code == 400


class TestConsolePage:
    def test_page_structure_and_no_banned_strings(self, client):
        resp = client.get("/saas/console")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        for marker in ('data-tab="overview"', 'data-tab="users"', 'data-tab="factors"',
                       'data-tab="workers"', 'data-tab="jobs"', "/api/saas/console/overview"):
            assert marker in html
        # 禁链纪律（12 号文档 §7）：SaaS 页面（含管理台自身）不得出现内网端口/旧管理路径字样
        for page in ("/saas/console", "/saas/", "/saas/new", "/saas/login"):
            body = client.get(page).get_data(as_text=True)
            for banned in ("/admin", "factor-admin", "factor-create", "8080", "8081"):
                assert banned not in body, f"{page} 含禁链 {banned}"

    def test_nav_entry_not_injected(self, client):
        # QRE-SAAS-ADMIN-TUNNEL：管理台改 SSH 隧道访问，顶栏不再注入「管理台」入口
        html = client.get("/saas/").get_data(as_text=True)
        assert "管理台" not in html
        assert "is_admin" not in html


class TestTierPolicies:
    """N1b/N1c：角色权限参数化（tier_policies 表 + 管理台读写 + 配额检查接入）。"""

    def test_auth_gate(self, client, app):
        assert client.get("/api/saas/console/policies").status_code == 401
        uid = _make_user(app, "plain@example.com")
        h = {"X-User-Id": str(uid)}
        assert client.get("/api/saas/console/policies", headers=h).status_code == 403

    def test_seed_and_update(self, client, app):
        headers, _ = _admin_headers(app)
        d = client.get("/api/saas/console/policies", headers=headers).get_json()
        assert d["ok"]
        by_tier = {p["tier"]: p for p in d["policies"]}
        # 种子行：三级权限与代码常量一致
        assert by_tier["guest"]["daily_full_limit"] == 1
        assert by_tier["guest"]["max_codes"] == 1 and by_tier["guest"]["max_days"] > 0
        assert by_tier["member"]["daily_full_limit"] == 3
        assert by_tier["member"]["max_codes"] == 0 and by_tier["member"]["max_days"] == 0
        assert by_tier["paid"]["daily_full_limit"] == 3
        # 更新 member 日限额 → 生效且入库
        r = client.post("/api/saas/console/policies/member", json={"daily_full_limit": 5}, headers=headers)
        assert r.get_json()["ok"] and r.get_json()["updated"] == ["daily_full_limit"]
        d2 = client.get("/api/saas/console/policies", headers=headers).get_json()
        assert {p["tier"]: p for p in d2["policies"]}["member"]["daily_full_limit"] == 5
        # 校验：非法角色名 / 非法数值 / 空更新
        assert client.post("/api/saas/console/policies/bad name!", json={"daily_full_limit": 1}, headers=headers).status_code == 400
        assert client.post("/api/saas/console/policies/member", json={"daily_full_limit": -1}, headers=headers).status_code == 400
        assert client.post("/api/saas/console/policies/member", json={}, headers=headers).status_code == 400

    def test_member_quota_follows_policy(self, client, app):
        # 改 member 日限额为 1 → 会员第二次提交被拒；admin 不受限
        headers, admin_uid = _admin_headers(app)
        client.post("/api/saas/console/policies/member", json={"daily_full_limit": 1}, headers=headers)
        uid = _make_user(app, "u@example.com")
        h = {"X-User-Id": str(uid)}
        assert _create_job(client, uid=uid).status_code == 200
        r = _create_job(client, uid=uid)
        assert r.status_code == 403 and "每日" in r.get_json()["error"]
        assert _create_job(client, uid=admin_uid).status_code == 200  # admin 不限
        # 恢复默认 3
        client.post("/api/saas/console/policies/member", json={"daily_full_limit": 3}, headers=headers)

    def test_factor_limits_follow_policy(self, client, app):
        # N4b 接入 N1：管理台把 member 因子上限调低到 5 → 6 因子策略提交即 400；
        # 恢复 20 后同策略放行；0 = 不限
        headers, _ = _admin_headers(app)
        uid = _make_user(app, "f@example.com")
        fields = "\n".join(
            f"    f{i}: factors.stock_daily_momentum_close.rsi_14" for i in range(6)
        )
        yaml_text = (
            "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
            f"  factor_fields:\n{fields}\nsignal:\n  entry: f0 > 0\n"
        )
        client.post("/api/saas/console/policies/member", json={"max_factor_fields": 5}, headers=headers)
        r = _create_job(client, uid=uid, yaml_text=yaml_text)
        assert r.status_code == 400 and "因子数量超限" in r.get_json()["error"]
        # params 透传给 worker 的上限也跟随 policy
        client.post("/api/saas/console/policies/member", json={"max_factor_fields": 20}, headers=headers)
        r2 = _create_job(client, uid=uid, yaml_text=yaml_text)
        assert r2.status_code == 200
        detail = client.get(f"/api/saas/jobs/{r2.get_json()['job_id']}",
                            headers={"X-User-Id": str(uid)}).get_json()["job"]
        assert detail["params"]["_factor_limits"] == {"max_fields": 20, "max_tables": 3}

    def test_overview_guest_stats(self, client, app):
        headers, _ = _admin_headers(app)
        # 造一条游客任务（无 X-User-Id，走 guest 通道：单股 + 2 年内区间）
        r = client.post("/api/saas/jobs", json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "full",
            "params": {"codes": ["000001"], "start": "2026-01-01", "end": "2026-09-01"},
            "name": "guest-t"})
        assert r.status_code == 200, r.get_json()
        d = client.get("/api/saas/console/overview", headers=headers).get_json()
        assert d["ok"] and d["guests"]["today"] == 1 and d["guests"]["unique_visitors"] == 1

    def test_console_page_has_policies_tab(self, client):
        html = client.get("/saas/console").get_data(as_text=True)
        assert 'data-tab="policies"' in html and "/api/saas/console/policies" in html
        assert 'id="ov-guests"' in html
