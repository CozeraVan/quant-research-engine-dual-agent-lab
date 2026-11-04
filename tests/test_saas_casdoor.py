"""QRE-AUTH-MEMBERSHIP / Casdoor 自建登录链路测试（36 号文档 §3）。

链路：/saas/login/casdoor 302 → Casdoor authorize → /saas/login/callback
换票验签（mock）→ auth_identities(provider, sub) 建档/关联 → 本地 session token。
JWKS 与 token 端点全部 mock，不发真实网络请求；DB 为真实本地 PG 临时库。
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

from quant_research_engine.gui.saas import authing, create_saas_app, oidc_client

CLIENT_ID = "qre-local-test"
CLIENT_SECRET = "test-client-secret"
ISSUER = "http://casdoor.test"
REDIRECT_URI = "http://localhost:8099/saas/login/callback"
KID = "casdoor-key-1"
AUTHORIZE_URL = f"{ISSUER}/login/oauth/authorize"
TOKEN_URL = f"{ISSUER}/api/login/oauth/access_token"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_casdoor_test_{uuid.uuid4().hex[:12]}"
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


def _make_id_token(private_key, *, sub="casdoor-sub-1", aud=CLIENT_ID, iss=ISSUER,
                   expires_in=3600, kid=KID, extra=None) -> str:
    now = int(time.time())
    claims = {
        "sub": sub, "iss": iss, "aud": aud,
        "iat": now, "exp": now + expires_in,
        "name": "本地管理员", "preferred_username": "admin",
        "email": "admin@example.com",
    }
    if extra:
        claims.update(extra)
    return pyjwt.encode(claims, private_key, algorithm="RS256", headers={"kid": kid})


@pytest.fixture()
def app(saas_db, rsa_keys, monkeypatch):
    key, _other = rsa_keys
    for var in ("CASDOOR_ISSUER", "CASDOOR_CLIENT_ID", "CASDOOR_CLIENT_SECRET",
                "CASDOOR_REDIRECT_URI"):
        monkeypatch.delenv(var, raising=False)
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = "test-worker-token"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    app.config["CASDOOR_ISSUER"] = ISSUER
    app.config["CASDOOR_CLIENT_ID"] = CLIENT_ID
    app.config["CASDOOR_CLIENT_SECRET"] = CLIENT_SECRET
    app.config["CASDOOR_REDIRECT_URI"] = REDIRECT_URI

    state = {"jwks": _jwks_for(key.public_key()), "id_token": None,
             "jwks_calls": 0, "token_calls": []}

    def fake_get_json(url):
        if url.endswith("/.well-known/openid-configuration"):
            return {
                "issuer": ISSUER,
                "authorization_endpoint": AUTHORIZE_URL,
                "token_endpoint": TOKEN_URL,
                "jwks_uri": f"{ISSUER}/.well-known/jwks.json",
            }
        assert url == f"{ISSUER}/.well-known/jwks.json", url
        state["jwks_calls"] += 1
        return state["jwks"]

    def fake_post_form(url, data):
        assert url == TOKEN_URL, url
        state["token_calls"].append(dict(data))
        assert data["client_id"] == CLIENT_ID
        assert data["client_secret"] == CLIENT_SECRET
        assert data["grant_type"] == "authorization_code"
        assert data["redirect_uri"] == REDIRECT_URI
        return {"id_token": state["id_token"], "access_token": "at"}

    monkeypatch.setattr(oidc_client, "_http_get_json", fake_get_json)
    monkeypatch.setattr(oidc_client, "_http_post_form", fake_post_form)
    app.extensions["mock_casdoor"] = state
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


def _authorize_state(client) -> str:
    resp = client.get("/saas/login/casdoor")
    assert resp.status_code == 302
    loc = resp.headers["Location"]
    assert loc.startswith(f"{AUTHORIZE_URL}?")
    qs = parse_qs(urlparse(loc).query)
    assert qs["client_id"] == [CLIENT_ID]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == [REDIRECT_URI]
    assert "openid" in qs["scope"][0]
    return qs["state"][0]


def _login(client, app, id_token):
    state = _authorize_state(client)
    app.extensions["mock_casdoor"]["id_token"] = id_token
    return client.get(f"/saas/login/callback?code=fake-code&state={state}")


def _sql(db: str, statement: str, **params):
    import sqlalchemy as sa

    engine = sa.create_engine(f"postgresql+psycopg:///{db}")
    try:
        with engine.begin() as conn:
            result = conn.execute(sa.text(statement), params)
            return result.mappings().all() if result.returns_rows else []
    finally:
        engine.dispose()


class TestAuthorizeRedirect:
    def test_redirect_to_casdoor(self, client):
        assert _authorize_state(client)

    def test_next_is_stored_in_flask_session(self, client):
        resp = client.get("/saas/login/casdoor?next=/saas/jobs/78%3Fx%3D1%23risk")
        assert resp.status_code == 302
        with client.session_transaction() as flask_session:
            assert flask_session["casdoor_next"] == "/saas/jobs/78?x=1#risk"

    def test_callback_uses_stored_next(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = client.get("/saas/login/casdoor?next=/saas/jobs/78%3Fx%3D1%23risk")
        state = parse_qs(urlparse(resp.headers["Location"]).query)["state"][0]
        app.extensions["mock_casdoor"]["id_token"] = _make_id_token(key, sub="sub-next")
        callback = client.get(f"/saas/login/callback?code=c&state={state}")
        assert callback.status_code == 200
        assert 'const NEXT = "/saas/jobs/78?x=1#risk";' in callback.get_data(as_text=True)

    def test_state_single_use(self, client, app, rsa_keys):
        key, _ = rsa_keys
        token = _make_id_token(key, sub="sub-state")
        state = _authorize_state(client)
        app.extensions["mock_casdoor"]["id_token"] = token
        assert client.get(f"/saas/login/callback?code=c&state={state}").status_code == 200
        replay = client.get(f"/saas/login/callback?code=c&state={state}")
        assert replay.status_code == 400

    def test_bad_state_rejected(self, client):
        resp = client.get("/saas/login/callback?code=c&state=bogus")
        assert resp.status_code == 400
        assert "登录状态已失效" in resp.get_data(as_text=True)


class TestCallbackLogin:
    def test_first_login_creates_user_and_identity(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(
            key, sub="sub-new-1",
            extra={"nickname": "测试用户", "phone": "13900000002",
                   "picture": "https://cdn.example.com/a.png"},
        ))
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "登录成功" in html and "测试用户" in html
        rows = _sql(
            saas_db,
            "SELECT u.id, u.phone, u.nickname, u.avatar_url, u.tier, u.email, "
            "u.authing_id, u.member_since FROM users u "
            "JOIN auth_identities i ON i.user_id = u.id "
            "WHERE i.provider = 'casdoor' AND i.sub = 'sub-new-1'",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["phone"] == "13900000002"
        assert row["nickname"] == "测试用户"
        assert row["avatar_url"].endswith("a.png")
        assert row["tier"] == "member" and row["member_since"] is not None
        assert row["authing_id"] is None and row["email"] is None

    def test_repeat_login_idempotent(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        r1 = _login(client, app, _make_id_token(key, sub="sub-repeat"))
        r2 = _login(client, app, _make_id_token(key, sub="sub-repeat"))
        assert r1.status_code == r2.status_code == 200
        users = _sql(saas_db, "SELECT count(*) AS n FROM users u JOIN auth_identities i "
                              "ON i.user_id = u.id WHERE i.sub = 'sub-repeat'")
        identities = _sql(saas_db, "SELECT count(*) AS n FROM auth_identities "
                                   "WHERE provider = 'casdoor' AND sub = 'sub-repeat'")
        assert users[0]["n"] == 1 and identities[0]["n"] == 1

    def test_local_session_token_works(self, client, app, rsa_keys):
        key, _ = rsa_keys
        resp = _login(client, app, _make_id_token(key, sub="sub-session"))
        assert resp.status_code == 200
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
        resp = _login(client, app, _make_id_token(key, sub="sub-badiss",
                                                  iss="https://evil.example"))
        assert resp.status_code == 502

    def test_disabled_user_rejected(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        rows = _sql(
            saas_db,
            "INSERT INTO users (nickname, tier, status) "
            "VALUES ('停用用户', 'member', 'disabled') RETURNING id",
        )
        uid = rows[0]["id"]
        _sql(saas_db, "INSERT INTO auth_identities (user_id, provider, sub) "
                      "VALUES (:uid, 'casdoor', 'sub-disabled')", uid=uid)
        resp = _login(client, app, _make_id_token(key, sub="sub-disabled"))
        assert resp.status_code == 403
        assert "账号已被禁用" in resp.get_data(as_text=True)

    def test_phone_conflict_leaves_phone_null(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        _sql(saas_db, "INSERT INTO users (phone, tier) VALUES ('13700000009', 'member')")
        resp = _login(client, app, _make_id_token(
            key, sub="sub-phone-dup", extra={"phone": "13700000009"}))
        assert resp.status_code == 200
        rows = _sql(saas_db, "SELECT u.phone FROM users u JOIN auth_identities i "
                             "ON i.user_id = u.id WHERE i.sub = 'sub-phone-dup'")
        assert rows[0]["phone"] is None

    def test_identity_isolated_by_provider(self, client, app, saas_db, rsa_keys):
        key, _ = rsa_keys
        _sql(saas_db, "INSERT INTO users (authing_id, nickname) "
                      "VALUES ('shared-sub', 'Authing 老用户')")
        resp = _login(client, app, _make_id_token(key, sub="shared-sub"))
        assert resp.status_code == 200
        rows = _sql(saas_db, "SELECT id, authing_id, nickname FROM users "
                             "WHERE authing_id = 'shared-sub' "
                             "OR id IN (SELECT user_id FROM auth_identities "
                             "WHERE provider = 'casdoor' AND sub = 'shared-sub')")
        assert len(rows) == 2

    def test_casdoor_state_never_uses_authing_exchange(self, client, app, rsa_keys, monkeypatch):
        key, _ = rsa_keys

        def boom(*_args, **_kwargs):
            raise AssertionError("Casdoor state 不应走 Authing 换票")

        monkeypatch.setattr(authing, "exchange_code", boom)
        state = _authorize_state(client)
        app.extensions["mock_casdoor"]["id_token"] = _make_id_token(key, sub="sub-not-authing")
        resp = client.get(f"/saas/login/callback?code=c&state={state}")
        assert resp.status_code == 200


class TestNotConfigured:
    def test_redirect_503_without_config(self, saas_db, monkeypatch):
        for var in ("CASDOOR_ISSUER", "CASDOOR_CLIENT_ID", "CASDOOR_CLIENT_SECRET",
                    "CASDOOR_REDIRECT_URI"):
            monkeypatch.delenv(var, raising=False)
        app = create_saas_app()
        app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        for key in ("CASDOOR_ISSUER", "CASDOOR_CLIENT_ID", "CASDOOR_CLIENT_SECRET"):
            app.config[key] = ""
        client = app.test_client()
        resp = client.get("/saas/login/casdoor")
        assert resp.status_code == 503
        assert resp.get_json()["ok"] is False
        engine = app.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()


class TestLoginPage:
    def test_casdoor_entry_rendered_when_configured(self, client):
        html = client.get("/saas/login").get_data(as_text=True)
        assert "/saas/login/casdoor" in html
        assert "使用 Casdoor 账号登录" in html
        assert "/saas/login/authing" in html

    def test_casdoor_entry_hidden_without_config(self, saas_db, monkeypatch):
        for var in ("CASDOOR_ISSUER", "CASDOOR_CLIENT_ID", "CASDOOR_CLIENT_SECRET",
                    "CASDOOR_REDIRECT_URI"):
            monkeypatch.delenv(var, raising=False)
        app = create_saas_app()
        app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        for key in ("CASDOOR_ISSUER", "CASDOOR_CLIENT_ID", "CASDOOR_CLIENT_SECRET"):
            app.config[key] = ""
        client = app.test_client()
        html = client.get("/saas/login").get_data(as_text=True)
        assert "/saas/login/casdoor" not in html
        assert "/saas/login/authing" in html
        engine = app.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()