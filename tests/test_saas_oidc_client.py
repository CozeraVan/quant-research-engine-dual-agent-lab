"""通用 OIDC 适配层（gui/saas/oidc_client.py）单元测试。

36 号文档：Authing 存量配置零改动即可用；Casdoor 仅加 CASDOOR_* 环境变量。
不依赖真实网络：discovery/JWKS/换票均以 monkeypatch 替换 HTTP 层。
"""

from __future__ import annotations

import pytest
from flask import Flask

from quant_research_engine.gui.saas import oidc_client


@pytest.fixture()
def app():
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.extensions = {}
    return app


def test_authing_config_uses_legacy_env(app, monkeypatch):
    monkeypatch.setenv("AUTHING_HOST", "https://demo.authing.cn/oidc/app1")
    monkeypatch.setenv("AUTHING_APP_ID", "app1")
    monkeypatch.setenv("AUTHING_APP_SECRET", "s3cret")
    cfg = oidc_client.get_config(app, "authing")
    assert cfg["issuer"] == "https://demo.authing.cn/oidc/app1/oidc"
    assert cfg["client_id"] == "app1"
    assert cfg["client_secret"] == "s3cret"


def test_casdoor_config_from_prefixed_env(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000/")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    cfg = oidc_client.get_config(app, "casdoor")
    assert cfg["issuer"] == "http://127.0.0.1:8000"
    assert cfg["client_id"] == "cid"


def test_missing_config_raises(app):
    with pytest.raises(oidc_client.OidcError):
        oidc_client.get_config(app, "casdoor")


def test_redirect_uri_defaults_to_request_root(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    with app.test_request_context("/saas/login", base_url="https://aguhuice.com/"):
        cfg = oidc_client.get_config(app, "casdoor")
    assert cfg["redirect_uri"] == "https://aguhuice.com/saas/login/callback"


def test_state_scoped_by_provider_and_expiry(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    state = oidc_client.new_state(app, "casdoor")
    assert not oidc_client.pop_state(app, "authing", state)  # provider 不匹配
    state = oidc_client.new_state(app, "casdoor")
    assert oidc_client.pop_state(app, "casdoor", state)
    assert not oidc_client.pop_state(app, "casdoor", state)  # 一次性
    state = oidc_client.new_state(app, "casdoor")
    app.extensions["oidc_states"][state] = ("casdoor", 0.0)  # 强制过期
    assert not oidc_client.pop_state(app, "casdoor", state)


def test_authorize_url_uses_discovery_endpoint(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    monkeypatch.setenv("CASDOOR_REDIRECT_URI", "https://x/cb")
    monkeypatch.setattr(oidc_client, "_http_get_json", lambda url: {
        "authorization_endpoint": "http://127.0.0.1:8000/login/oauth/authorize",
    })
    url = oidc_client.build_authorize_url(app, "casdoor", "st")
    assert url.startswith("http://127.0.0.1:8000/login/oauth/authorize?")
    assert "client_id=cid" in url and "state=st" in url


def test_endpoints_fallback_when_discovery_unavailable(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    monkeypatch.setattr(oidc_client, "_http_get_json", lambda url: (_ for _ in ()).throw(RuntimeError("down")))
    endpoints = oidc_client._endpoints(app, "casdoor")
    assert endpoints["token"] == "http://127.0.0.1:8000/token"
    assert endpoints["jwks"] == "http://127.0.0.1:8000/.well-known/jwks.json"


def test_exchange_code_requires_id_token(app, monkeypatch):
    monkeypatch.setenv("CASDOOR_ISSUER", "http://127.0.0.1:8000")
    monkeypatch.setenv("CASDOOR_CLIENT_ID", "cid")
    monkeypatch.setenv("CASDOOR_CLIENT_SECRET", "csec")
    monkeypatch.setattr(oidc_client, "_http_post_form", lambda url, data: {"access_token": "x"})
    with pytest.raises(oidc_client.OidcError):
        oidc_client.exchange_code(app, "casdoor", "code")
