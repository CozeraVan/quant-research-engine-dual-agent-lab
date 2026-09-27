"""QRE-AUTH-MEMBERSHIP / A5：Authing OIDC 登录链路测试。

JWKS 验签正反例用本地生成的 RSA 密钥对 mock（_http_get_json 返回伪造 jwks.json），
token 换票走 _http_post_form mock，不发真实网络请求。DB 为真实本地 PG 临时库
（同 test_gui_saas.py 口径，schema 为 PG 方言）。
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from quant_research_engine.gui.saas import authing, create_saas_app

APP_ID = "test-app-id"
APP_SECRET = "test-app-secret"
HOST = "https://pool-demo.authing.cn"
ISSUER = f"{HOST}/oidc"
KID = "test-key-1"

WORKER_TOKEN = "test-worker-token"


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


@pytest.fixture(scope="module")
def rsa_keys():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, other


def _jwks_for(public_key) -> dict:
    jwk = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def _make_id_token(private_key, *, sub="authing-sub-1", aud=APP_ID, iss=ISSUER,
                   expires_in=3600, kid=KID, extra=None) -> str:
    now = int(time.time())
    claims = {
        "sub": sub, "iss": iss, "aud": aud,
        "iat": now, "exp": now + expires_in,
        "nickname": "测试用户", "phone": "13800000001",
        "picture": "https://cdn.example.com/avatar.png",
    }
    if extra:
        claims.update(extra)
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture()
def app(saas_db, rsa_keys, monkeypatch):
    key, _other = rsa_keys
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    app.config["AUTHING_APP_ID"] = APP_ID
    app.config["AUTHING_APP_SECRET"] = APP_SECRET
    app.config["AUTHING_HOST"] = HOST

    state = {"jwks": _jwks_for(key.public_key()), "id_token": None, "jwks_calls": 0}

    def fake_get_json(url):
        assert url == f"{HOST}/oidc/.well-known/jwks.json"
        state["jwks_calls"] += 1
        return state["jwks"]

    def fake_post_form(url, data):
        assert url == f"{HOST}/oidc/token"
        assert data["client_id"] == APP_ID and data["client_secret"] == APP_SECRET
        assert data["grant_type"] == "authorization_code" and data["code"]
        return {"id_token": state["id_token"], "access_token": "at"}

    monkeypatch.setattr(authing, "_http_get_json", fake_get_json)
    monkeypatch.setattr(authing, "_http_post_form", fake_post_form)
    app.extensions["mock_auth"] = state
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def _authorize_state(client) -> str:
    resp = client.get("/saas/login/authing")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith(f"{HOST}/oidc/auth?")
    qs = parse_qs(urlparse(loc).query)
    assert qs["client_id"] == [APP_ID]
    assert qs["response_type"] == ["code"]
    assert "openid" in qs["scope"][0]
    return qs["state"][0]


def _login(client, app, id_token):
    state = _authorize_state(client)
    app.extensions["mock_auth"]["id_token"] = id_token
    return client.get(f"/saas/login/callback?code=fake-code&state={state}")


class TestAuthorizeRedirect:
    def test_redirect_to_authing(self, client):
        state = _authorize_state(client)
        assert state

    def test_state_single_use(self, client, app, rsa_keys):
        key, _ = rsa_keys
        token = _make_id_token(key, sub="sub-state")
        state = _authorize_state(client)
        app.extensions["mock_auth"]["id_token"] = token
        ok = client.get(f"/saas/login/callback?code=c&state={state}")
        assert ok.status_code == 200
        # 同一 state 重放 → 400
        replay = client.get(f"/saas/login/callback?code=c&state={state}")
        assert replay.status_code == 400

    def test_bad_state_rejected(self, client):
        resp = client.get("/saas/login/callback?code=c&state=bogus")
        assert resp.status_code == 400
        assert "登录状态已失效" in resp.get_data(as_text=True)


class TestCallbackLogin:
    def test_first_login_creates_user(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-new-1", extra={"phone": "13900000002"}))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "登录成功" in html and "测试用户" in html
        import sqlalchemy as sa

        engine = sa.create_engine(f"postgresql+psycopg:///{saas_db}")
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT phone, nickname, avatar_url, tier, member_since "
                        "FROM users WHERE authing_id = 'sub-new-1'")
            ).mappings().one()
        engine.dispose()
        assert row["phone"] == "13900000002"
        assert row["nickname"] == "测试用户"
        assert row["avatar_url"].endswith("avatar.png")
        assert row["tier"] == "member" and row["member_since"] is not None

    def test_repeat_login_idempotent(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        r1 = _login(client, app, _make_id_token(key, sub="sub-repeat"))
        r2 = _login(client, app, _make_id_token(key, sub="sub-repeat"))
        assert r1.status_code == r2.status_code == 200
        import sqlalchemy as sa

        engine = sa.create_engine(f"postgresql+psycopg:///{saas_db}")
        with engine.connect() as conn:
            n = conn.execute(
                sa.text("SELECT count(*) FROM users WHERE authing_id = 'sub-repeat'")
            ).scalar_one()
        engine.dispose()
        assert n == 1

    def test_local_session_token_works(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-session"))
        assert resp.status_code == 200
        # 回调页内嵌 token，提取后用 Bearer 调 /api/saas/me
        html = resp.get_data(as_text=True)
        marker = "localStorage.setItem('saas_token', "
        token = html.split(marker, 1)[1].split(")", 1)[0].strip().strip('"').rstrip(';').strip('"')
        me = client.get("/api/saas/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.get_json()["user"]["tier"] == "member"

    def test_bad_signature_rejected(self, client, app, rsa_keys):
        _key, other = rsa_keys
        resp = _login(client, app, _make_id_token(other, sub="sub-badsig"))
        assert resp.status_code == 502
        assert "验签失败" in resp.get_data(as_text=True)

    def test_wrong_audience_rejected(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-badaud", aud="someone-else"))
        assert resp.status_code == 502

    def test_wrong_issuer_rejected(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-badiss", iss="https://evil.example/oidc"))
        assert resp.status_code == 502

    def test_expired_token_rejected(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-expired", expires_in=-10))
        assert resp.status_code == 502

    def test_jwks_refresh_on_unknown_kid(self, client, app, rsa_keys):
        key, _ = rsa_keys
        state = app.extensions["mock_auth"]
        calls_before = state["jwks_calls"]
        state["jwks"] = {"keys": []}  # 缓存里无匹配 kid
        resp = _login(client, app, _make_id_token(key, sub="sub-rotate"))
        # 首次缓存未命中 → 强制刷新一次后找到（fake 仍返回空） → 502
        assert resp.status_code == 502
        assert state["jwks_calls"] > calls_before


class TestJsonExchange:
    def test_post_exchange(self, client, app, rsa_keys):
        key, _ = rsa_keys
        state = _authorize_state(client)
        app.extensions["mock_auth"]["id_token"] = _make_id_token(key, sub="sub-json")
        resp = client.post("/api/saas/auth/authing", json={"code": "c", "state": state})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and data["token"] and data["user"]["tier"] == "member"

    def test_post_bad_state(self, client):
        resp = client.post("/api/saas/auth/authing", json={"code": "c", "state": "nope"})
        assert resp.status_code == 400

    def test_post_missing_code(self, client):
        resp = client.post("/api/saas/auth/authing", json={})
        assert resp.status_code == 400


class TestBindLegacyAccount:
    def _register_legacy(self, client, email, password="Passw0rd123"):
        resp = client.post("/api/saas/auth/register", json={"email": email, "password": password})
        assert resp.status_code == 200, resp.get_json()
        return resp.get_json()

    def _authing_token(self, client, app, rsa_keys, sub):
        key, _ = rsa_keys
        state = _authorize_state(client)
        app.extensions["mock_auth"]["id_token"] = _make_id_token(key, sub=sub)
        resp = client.post("/api/saas/auth/authing", json={"code": "c", "state": state})
        assert resp.status_code == 200
        return resp.get_json()["token"]

    def test_bind_success(self, client, app, saas_db, rsa_keys):
        self._register_legacy(client, "legacy-bind@example.com")
        token = self._authing_token(client, app, rsa_keys, "sub-bind-1")
        resp = client.post(
            "/api/saas/auth/bind",
            json={"email": "legacy-bind@example.com", "password": "Passw0rd123"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.get_json()
        data = resp.get_json()
        assert data["bound"] == "legacy-bind@example.com" and data["token"]
        import sqlalchemy as sa

        engine = sa.create_engine(f"postgresql+psycopg:///{saas_db}")
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT id FROM users WHERE authing_id = 'sub-bind-1'")
            ).mappings().one()
            old = conn.execute(
                sa.text("SELECT id FROM users WHERE email = 'legacy-bind@example.com'")
            ).mappings().one()
        engine.dispose()
        assert row["id"] == old["id"]
        # 新 token 属于旧账号（me 返回旧邮箱）
        me = client.get("/api/saas/me", headers={"Authorization": f"Bearer {data['token']}"})
        assert me.get_json()["user"]["email"] == "legacy-bind@example.com"

    def test_bind_wrong_password(self, client, app, rsa_keys):
        self._register_legacy(client, "legacy-wrong@example.com")
        token = self._authing_token(client, app, rsa_keys, "sub-bind-2")
        resp = client.post(
            "/api/saas/auth/bind",
            json={"email": "legacy-wrong@example.com", "password": "WrongPass1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_bind_requires_authing_session(self, client, app):
        legacy = self._register_legacy(client, "legacy-plain@example.com")
        resp = client.post(
            "/api/saas/auth/bind",
            json={"email": "legacy-plain@example.com", "password": "Passw0rd123"},
            headers={"Authorization": f"Bearer {legacy['token']}"},
        )
        assert resp.status_code == 400
        assert "不是 Authing 登录态" in resp.get_json()["error"]

    def test_bind_already_bound_conflict(self, client, app, rsa_keys):
        self._register_legacy(client, "legacy-taken@example.com")
        token1 = self._authing_token(client, app, rsa_keys, "sub-bind-3")
        ok = client.post(
            "/api/saas/auth/bind",
            json={"email": "legacy-taken@example.com", "password": "Passw0rd123"},
            headers={"Authorization": f"Bearer {token1}"},
        )
        assert ok.status_code == 200
        token2 = self._authing_token(client, app, rsa_keys, "sub-bind-4")
        dup = client.post(
            "/api/saas/auth/bind",
            json={"email": "legacy-taken@example.com", "password": "Passw0rd123"},
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert dup.status_code == 409

    def test_bind_requires_login(self, client):
        resp = client.post("/api/saas/auth/bind", json={"email": "a@b.c", "password": "x"})
        assert resp.status_code == 401


class TestAuthingNotConfigured:
    def test_redirect_503_without_config(self, saas_db):
        app = create_saas_app()
        app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        for key in ("AUTHING_APP_ID", "AUTHING_APP_SECRET", "AUTHING_HOST"):
            app.config[key] = ""
        client = app.test_client()
        resp = client.get("/saas/login/authing")
        assert resp.status_code == 503
        engine = app.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()


class TestLoginPage:
    def test_login_page_has_authing_primary(self, client):
        html = client.get("/saas/login").get_data(as_text=True)
        assert "/saas/login/authing" in html
        assert "手机号 / 扫码登录" in html
        # 邮箱密码降级为折叠次要入口
        assert "legacy-box" in html and "<details" in html
        # 老账号绑定入口
        assert "bind-box" in html and "/api/saas/auth/bind" in html

    def test_login_callback_template_no_token_on_error(self, client):
        html = client.get("/saas/login/callback?code=x&state=bad").get_data(as_text=True)
        assert "返回登录页" in html
        assert "localStorage.setItem" not in html
