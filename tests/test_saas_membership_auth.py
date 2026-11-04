"""QRE-AUTH-MEMBERSHIP 后端切片测试（2026-11-04，36/37 号文档）。

覆盖：手机验证码改密（旧 session 全失效）、密码登录防爆破（5 次锁 15 分钟，
验证码路径不受影响）、/api/saas/membership 权益视图、membership 纯函数。
DB 为真实本地 PG 临时库（schema = deploy/saas/cloud_schema.sql）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
import sqlalchemy as sa

from quant_research_engine.gui.saas import create_saas_app, membership

WORKER_TOKEN = "test-worker-token"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_member_test_{uuid.uuid4().hex[:12]}"
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
    """每用例清空业务行，避免用户/失败计数跨用例污染。"""
    from quant_research_engine.gui.saas.app import _get_engine

    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(sa.text(
            "TRUNCATE results, jobs, strategies, strategy_watches, users, sessions, "
            "sms_codes RESTART IDENTITY CASCADE"
        ))
        if conn.execute(sa.text("SELECT to_regclass('public.login_attempts')")).scalar():
            conn.execute(sa.text("DELETE FROM login_attempts"))


def _sql(db: str, statement: str, **params):
    engine = sa.create_engine(f"postgresql+psycopg:///{db}")
    try:
        with engine.begin() as conn:
            result = conn.execute(sa.text(statement), params)
            return result.mappings().all() if result.returns_rows else []
    finally:
        engine.dispose()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _send_code(client, target: str):
    # 测试辅助只负责拿码：清 target 级限流，避免同用例内「注册发码 + 重置发码」
    # 被 60s 限流挡成 429（限流本身的断言在 test_gui_saas，不在这里测）。
    rl = client.application.extensions["rate_limit"]["target"]
    rl.pop(target, None)
    resp = client.post("/api/saas/auth/code", json={"target": target})
    assert resp.status_code == 200, resp.get_json()
    return resp


def _code_for(app, target: str) -> str:
    matches = [m["code"] for m in app.extensions["sent_codes"] if m["target"] == target]
    assert matches, "stub sender 未记录验证码"
    return matches[-1]


def _register(client, phone: str, password: str = "abc12345"):
    # 2026-11-04 起注册强制校验手机验证码：先走 stub 发码再注册。
    app = client.application
    _send_code(client, phone)
    code = _code_for(app, phone)
    resp = client.post("/api/saas/auth/register",
                       json={"phone": phone, "password": password, "code": code})
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


class TestResetPassword:
    def test_reset_revokes_sessions_and_switches_password(self, client, app):
        phone = "13800010001"
        reg = _register(client, phone, "oldpass123")
        old_token = reg["token"]
        assert client.get("/api/saas/me", headers=_bearer(old_token)).status_code == 200

        _send_code(client, phone)
        code = _code_for(app, phone)
        resp = client.post("/api/saas/auth/reset",
                           json={"phone": phone, "code": code,
                                 "new_password": "newpass456"})
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["ok"] is True
        # 改密不自动登录：不发 token
        assert "token" not in resp.get_json()

        # 旧 session 全部失效
        assert client.get("/api/saas/me", headers=_bearer(old_token)).status_code == 401
        # 新密码可登录（phone/password 别名，37 号文档 §2）
        ok = client.post("/api/saas/auth/login",
                         json={"phone": phone, "password": "newpass456"})
        assert ok.status_code == 200, ok.get_json()
        assert ok.get_json()["token"]
        # 旧密码失效
        old = client.post("/api/saas/auth/login",
                          json={"target": phone, "code": "oldpass123"})
        assert old.status_code == 401
        # 验证码单次：同一码再改密失败
        again = client.post("/api/saas/auth/reset",
                            json={"phone": phone, "code": code,
                                  "new_password": "another789"})
        assert again.status_code == 401

    def test_reset_rejects_bad_code_and_keeps_password(self, client, app):
        phone = "13800010002"
        _register(client, phone, "oldpass123")
        _send_code(client, phone)
        good = _code_for(app, phone)
        bad = "000000" if good != "000000" else "000001"
        resp = client.post("/api/saas/auth/reset",
                           json={"phone": phone, "code": bad,
                                 "new_password": "newpass456"})
        assert resp.status_code == 401
        assert "验证码" in resp.get_json()["error"]
        # 错码不消费验证码：正确码仍可用
        ok = client.post("/api/saas/auth/reset",
                         json={"phone": phone, "code": good,
                               "new_password": "newpass456"})
        assert ok.status_code == 200

    def test_reset_rejects_weak_password(self, client, app):
        phone = "13800010003"
        _register(client, phone, "oldpass123")
        _send_code(client, phone)
        code = _code_for(app, phone)
        for weak in ("short", "abcdefgh", "12345678"):
            resp = client.post("/api/saas/auth/reset",
                               json={"phone": phone, "code": code,
                                     "new_password": weak})
            assert resp.status_code == 400
            assert "密码至少 8 位" in resp.get_json()["error"]

    def test_reset_unknown_phone_404(self, client, app):
        phone = "13800010004"
        _send_code(client, phone)
        resp = client.post("/api/saas/auth/reset",
                           json={"phone": phone, "code": _code_for(app, phone),
                                 "new_password": "newpass456"})
        assert resp.status_code == 404
        assert "未注册" in resp.get_json()["error"]

    def test_reset_validates_input(self, client):
        for body in (
            {"phone": "not-a-phone", "code": "123456", "new_password": "newpass456"},
            {"phone": "13800010005", "code": "", "new_password": "newpass456"},
            {"phone": "13800010005", "code": "123456", "new_password": ""},
        ):
            resp = client.post("/api/saas/auth/reset", json=body)
            assert resp.status_code == 400, body


class TestPasswordLoginLockout:
    def test_five_failures_lock_15_minutes(self, client, app, saas_db):
        phone = "13800020001"
        _register(client, phone, "abc12345")
        for _ in range(5):
            resp = client.post("/api/saas/auth/login",
                               json={"phone": phone, "password": "wrong123"})
            assert resp.status_code == 401
        rows = _sql(saas_db, "SELECT fail_count, locked_until FROM login_attempts "
                             "WHERE target = :t", t=phone)
        assert len(rows) == 1 and rows[0]["fail_count"] == 5
        assert rows[0]["locked_until"] is not None

        # 第 6 次（即使密码正确）→ 429，文案可读
        locked = client.post("/api/saas/auth/login",
                             json={"phone": phone, "password": "abc12345"})
        assert locked.status_code == 429
        assert "密码错误次数过多" in locked.get_json()["error"]
        assert "15" in locked.get_json()["error"]

        # 验证码登录路径不受影响（另一个手机号 target）
        other = "13700002222"
        _send_code(client, other)
        code_login = client.post("/api/saas/auth/login",
                                 json={"target": other, "code": _code_for(app, other)})
        assert code_login.status_code == 200

        # 锁到期后可登录，成功即清空计数
        _sql(saas_db, "UPDATE login_attempts SET locked_until = now() - interval '1 minute' "
                      "WHERE target = :t", t=phone)
        ok = client.post("/api/saas/auth/login",
                         json={"phone": phone, "password": "abc12345"})
        assert ok.status_code == 200
        assert _sql(saas_db, "SELECT * FROM login_attempts WHERE target = :t", t=phone) == []

    def test_lock_is_per_target(self, client, app):
        _register(client, "13800020002", "abc12345")
        _register(client, "13800020003", "abc12345")
        for _ in range(5):
            client.post("/api/saas/auth/login",
                        json={"phone": "13800020002", "password": "wrong123"})
        assert client.post("/api/saas/auth/login",
                           json={"phone": "13800020002", "password": "abc12345"}
                           ).status_code == 429
        assert client.post("/api/saas/auth/login",
                           json={"phone": "13800020003", "password": "abc12345"}
                           ).status_code == 200

    def test_success_resets_fail_count_before_lock(self, client, app, saas_db):
        phone = "13800020004"
        _register(client, phone, "abc12345")
        for _ in range(4):
            assert client.post("/api/saas/auth/login",
                               json={"phone": phone, "password": "wrong123"}).status_code == 401
        assert client.post("/api/saas/auth/login",
                           json={"phone": phone, "password": "abc12345"}).status_code == 200
        assert _sql(saas_db, "SELECT * FROM login_attempts WHERE target = :t", t=phone) == []
        # 清零后仍可再失败 5 次才锁
        for _ in range(5):
            assert client.post("/api/saas/auth/login",
                               json={"phone": phone, "password": "wrong123"}).status_code == 401
        assert client.post("/api/saas/auth/login",
                           json={"phone": phone, "password": "abc12345"}).status_code == 429


class TestMembershipEndpoint:
    def test_requires_login(self, client):
        resp = client.get("/api/saas/membership")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "未登录"

    def test_member_payload_and_tiers(self, client):
        token = _register(client, "13800030001")["token"]
        body = client.get("/api/saas/membership", headers=_bearer(token)).get_json()
        assert body["ok"] is True
        mb = body["membership"]
        assert mb["tier"] == "member"
        assert mb["tier_label"] == "内测会员"
        assert mb["is_admin"] is False
        # 内测期会员全量不限（daily_full_limit=0）
        assert mb["daily_full"] == {"limit": "不限", "used": 0, "remaining": None,
                                    "unlimited": True}
        assert mb["watches"] == {"limit": 20, "used": 0, "remaining": 20,
                                 "unlimited": False}
        assert mb["scan_enabled"] is True
        assert "member_since" in mb and "member_expire_at" in mb

        tiers = body["tiers"]
        assert [t["tier"] for t in tiers] == ["guest", "member", "paid"]
        guest = tiers[0]
        assert guest["label"] == "游客"
        assert guest["daily_full_limit"] == 1
        assert guest["max_codes"] == 10
        assert guest["max_days"] == 3657
        assert guest["max_factor_fields"] == 20
        assert guest["max_factor_tables"] == 3
        assert guest["max_watches"] == 20
        assert guest["scan_enabled"] is True

    def test_counts_today_full_jobs_and_watches(self, client, app, saas_db):
        reg = _register(client, "13800030002")
        token, uid = reg["token"], reg["user"]["id"]
        created = client.post("/api/saas/jobs", headers=_bearer(token), json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "full",
            "name": "t", "params": {"cash": 1000000}})
        assert created.status_code == 200, created.get_json()
        # smoke 不占全量配额
        smoke = client.post("/api/saas/jobs", headers=_bearer(token), json={
            "yaml": "signal:\n  entry: 'true'\n", "kind": "smoke",
            "name": "t2", "params": {"cash": 1000000}})
        assert smoke.status_code == 200
        # 一条启用的监控
        sid = _sql(saas_db, "INSERT INTO strategies (user_id, name, yaml) "
                            "VALUES (:uid, 's1', 'x') RETURNING id", uid=uid)[0]["id"]
        _sql(saas_db, "INSERT INTO strategy_watches (strategy_id, user_id, scope_type, "
                      "scope_payload, enabled) VALUES (:sid, :uid, 'all_a', '{}'::jsonb, true)",
             sid=sid, uid=uid)

        mb = client.get("/api/saas/membership", headers=_bearer(token)).get_json()["membership"]
        assert mb["daily_full"]["used"] == 1
        assert mb["daily_full"]["unlimited"] is True
        assert mb["watches"]["used"] == 1
        assert mb["watches"]["remaining"] == 19

    def test_tier_table_comes_from_db(self, client, app, saas_db):
        token = _register(client, "13800030003")["token"]
        _sql(saas_db, "UPDATE tier_policies SET daily_full_limit = 5, max_watches = 7 "
                      "WHERE tier = 'guest'")
        try:
            # 60s 缓存：清掉进程内缓存再查
            app.extensions["tier_policy_cache"] = {}
            tiers = client.get("/api/saas/membership",
                               headers=_bearer(token)).get_json()["tiers"]
            guest = next(t for t in tiers if t["tier"] == "guest")
            assert guest["daily_full_limit"] == 5
            assert guest["max_watches"] == 7
        finally:
            _sql(saas_db, "UPDATE tier_policies SET daily_full_limit = 1, max_watches = 20 "
                          "WHERE tier = 'guest'")
            app.extensions.pop("tier_policy_cache", None)


class TestMembershipPureFunctions:
    def test_default_policy_covers_all_keys(self):
        for tier in ("guest", "member", "paid"):
            pol = membership.default_policy(tier)
            assert set(pol) == set(membership.POLICY_KEYS) | set(membership.POLICY_BOOL_KEYS) \
                | set(membership.POLICY_INT_KEYS)

    def test_unknown_tier_falls_back_to_member(self):
        assert membership.default_policy("vip") == membership.default_policy("member")
        assert membership.tier_label("vip") == "vip"
        assert membership.tier_label(None) == "内测会员"

    def test_normalize_policy_fills_missing_and_coerces(self):
        pol = membership.normalize_policy({"daily_full_limit": "5", "scan_enabled": 0}, "guest")
        assert pol["daily_full_limit"] == 5
        assert pol["max_codes"] == 10
        assert pol["scan_enabled"] is False
        assert membership.normalize_policy(None, "guest") == membership.default_policy("guest")

    def test_quota_view(self):
        member = membership.default_policy("member")
        assert membership.quota_view(member, 2) == {
            "limit": "不限", "used": 2, "remaining": None, "unlimited": True}
        guest = membership.default_policy("guest")
        assert membership.quota_view(guest, 0) == {
            "limit": 1, "used": 0, "remaining": 1, "unlimited": False}
        assert membership.quota_view(guest, 5)["remaining"] == 0
        assert membership.quota_view(guest, 1, is_admin=True)["limit"] == "不限"

    def test_is_quota_exceeded(self):
        guest = membership.default_policy("guest")
        assert membership.is_quota_exceeded(guest, 1) is True
        assert membership.is_quota_exceeded(guest, 0) is False
        assert membership.is_quota_exceeded(guest, 9, is_admin=True) is False
        assert membership.is_quota_exceeded(membership.default_policy("member"), 99) is False

    def test_is_watch_exceeded(self):
        guest = membership.default_policy("guest")
        assert membership.is_watch_exceeded(guest, 19) is False
        assert membership.is_watch_exceeded(guest, 20) is True
        assert membership.is_watch_exceeded({"max_watches": 0}, 999) is False

    def test_used_today_sql_is_full_jobs_of_user(self):
        sql = membership.USED_TODAY_SQL.lower()
        assert "from jobs" in sql and "kind = 'full'" in sql
        assert "j.user_id = u.id" in sql

class TestRegisterCode:
    """2026-11-04 注册强制手机验证码（Windows UI 复核发现的缺口收口）。"""

    def test_register_requires_code(self, client):
        resp = client.post("/api/saas/auth/register",
                           json={"phone": "13800040001", "password": "abc12345"})
        assert resp.status_code == 400
        assert "验证码" in resp.get_json()["error"]

    def test_register_rejects_wrong_code_without_consuming(self, client, app):
        phone = "13800040002"
        _send_code(client, phone)
        bad = client.post("/api/saas/auth/register",
                          json={"phone": phone, "password": "abc12345", "code": "000000"})
        assert bad.status_code == 401
        # 错码不消费：同一验证码仍可完成注册
        good = client.post("/api/saas/auth/register",
                           json={"phone": phone, "password": "abc12345",
                                 "code": _code_for(app, phone)})
        assert good.status_code == 200, good.get_json()
        assert good.get_json()["token"]
