"""通用 OIDC 授权码适配器（业务无关，可复用到任意 Flask 项目）。

设计目标（36 号文档 §3）：把 `authing.py` 里的 Authing 专用逻辑抽象为
provider 可配置的通用客户端。Authing 与 Casdoor 仅是两组配置；未来项目
复用本模块 = 拷文件 + 配环境变量 + 一张 `auth_identities(provider, sub)` 表。

配置（env 或 app.config，env 优先，与 QRE `_cfg` 同语义）：
  authing（兼容存量，无需改任何现有变量）：
    AUTHING_HOST / AUTHING_APP_ID / AUTHING_APP_SECRET / AUTHING_REDIRECT_URI
    issuer 推导为 ``<AUTHING_HOST>/oidc``
  其他 provider（以 casdoor 为例）：
    CASDOOR_ISSUER / CASDOOR_CLIENT_ID / CASDOOR_CLIENT_SECRET / CASDOOR_REDIRECT_URI

端点通过 OIDC discovery（``<issuer>/.well-known/openid-configuration``）获取，
失败时回退 ``<issuer>/token`` 与 ``<issuer>/.well-known/jwks.json``。

requests/pyjwt 惰性导入：未安装依赖或未配置时仅相关调用报错，不影响其他功能。
"""

from __future__ import annotations

import os
import time
from typing import Any
from urllib.parse import urlencode

JWKS_CACHE_TTL_SECONDS = 3600
DISCOVERY_CACHE_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10


class OidcError(Exception):
    """用户可读的 OIDC 链路错误（配置缺失/换票失败/验签失败）。"""


def _setting(app: Any, key: str) -> str:
    value = os.environ.get(key)
    if value:
        return value.strip()
    try:
        value = app.config.get(key)
    except AttributeError:
        value = None
    return str(value).strip() if value else ""


def get_config(app: Any, provider: str) -> dict[str, str]:
    """返回 provider 的 issuer/client_id/client_secret/redirect_uri；缺配置抛错。"""
    provider = provider.lower().strip()
    if provider == "authing":
        host = _setting(app, "AUTHING_HOST").rstrip("/")
        cfg = {
            "issuer": f"{host}/oidc" if host else "",
            "client_id": _setting(app, "AUTHING_APP_ID"),
            "client_secret": _setting(app, "AUTHING_APP_SECRET"),
            "redirect_uri": _setting(app, "AUTHING_REDIRECT_URI"),
        }
    else:
        prefix = provider.upper()
        cfg = {
            "issuer": _setting(app, f"{prefix}_ISSUER").rstrip("/"),
            "client_id": _setting(app, f"{prefix}_CLIENT_ID"),
            "client_secret": _setting(app, f"{prefix}_CLIENT_SECRET"),
            "redirect_uri": _setting(app, f"{prefix}_REDIRECT_URI"),
        }
    if not cfg["issuer"] or not cfg["client_id"] or not cfg["client_secret"]:
        raise OidcError(f"OIDC provider 未配置：{provider}")
    if not cfg["redirect_uri"]:
        cfg["redirect_uri"] = _default_redirect_uri()
    return cfg


def _default_redirect_uri() -> str:
    """请求上下文内回退到本站回调；上下文外返回空串（配置检查/单元测试可用）。"""
    from flask import has_request_context, request

    if not has_request_context():
        return ""
    return request.url_root.rstrip("/") + "/saas/login/callback"


def _require_redirect_uri(cfg: dict[str, str], provider: str) -> str:
    if not cfg["redirect_uri"]:
        raise OidcError(f"OIDC provider 缺少 redirect_uri：{provider}")
    return cfg["redirect_uri"]


def _http_get_json(url: str) -> dict:
    import requests

    resp = requests.get(url, timeout=HTTP_TIMEOUT_SECONDS)
    resp.raise_for_status()
    return resp.json()


def _http_post_form(url: str, data: dict) -> dict:
    import requests

    resp = requests.post(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=HTTP_TIMEOUT_SECONDS,
    )
    try:
        payload = resp.json()
    except ValueError as exc:
        raise OidcError(f"OIDC 返回了非 JSON 响应（HTTP {resp.status_code}）") from exc
    if resp.status_code != 200:
        desc = payload.get("error_description") or payload.get("error") or f"HTTP {resp.status_code}"
        raise OidcError(f"OIDC 换票失败：{desc}")
    return payload


def _discovery(app: Any, provider: str) -> dict:
    """拉取并缓存 OIDC discovery 文档；失败返回空 dict（调用方回退默认端点）。"""
    cache = app.extensions.setdefault("oidc_discovery", {})
    cached = cache.get(provider)
    now = time.time()
    if cached and now - cached[0] < DISCOVERY_CACHE_TTL_SECONDS:
        return cached[1]
    cfg = get_config(app, provider)
    try:
        doc = _http_get_json(f"{cfg['issuer']}/.well-known/openid-configuration")
        if not isinstance(doc, dict):
            doc = {}
    except Exception:
        doc = {}
    cache[provider] = (now, doc)
    return doc


def _endpoints(app: Any, provider: str) -> dict[str, str]:
    cfg = get_config(app, provider)
    doc = _discovery(app, provider)
    return {
        "authorization": doc.get("authorization_endpoint") or f"{cfg['issuer']}/auth",
        "token": doc.get("token_endpoint") or f"{cfg['issuer']}/token",
        "jwks": doc.get("jwks_uri") or f"{cfg['issuer']}/.well-known/jwks.json",
    }


def build_authorize_url(app: Any, provider: str, state: str) -> str:
    cfg = get_config(app, provider)
    redirect_uri = _require_redirect_uri(cfg, provider)
    endpoints = _endpoints(app, provider)
    query = urlencode({
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile phone email",
        "state": state,
    })
    return f"{endpoints['authorization']}?{query}"


def new_state(app: Any, provider: str) -> str:
    import secrets

    state = secrets.token_urlsafe(24)
    store = app.extensions.setdefault("oidc_states", {})
    now = time.time()
    expired = [k for k, (_, ts) in store.items() if now - ts > STATE_TTL_SECONDS]
    for k in expired:
        store.pop(k, None)
    store[state] = (provider, now)
    return state


def pop_state(app: Any, provider: str, state: str) -> bool:
    store = app.extensions.setdefault("oidc_states", {})
    item = store.pop(state, None)
    if item is None:
        return False
    owner, ts = item
    return owner == provider and time.time() - ts <= STATE_TTL_SECONDS


def _jwks(app: Any, provider: str, *, force_refresh: bool = False) -> dict:
    cached = app.extensions.setdefault("oidc_jwks", {}).get(provider)
    now = time.time()
    if cached and not force_refresh and now - cached[0] < JWKS_CACHE_TTL_SECONDS:
        return cached[1]
    url = _endpoints(app, provider)["jwks"]
    try:
        jwks = _http_get_json(url)
    except Exception as exc:
        raise OidcError(f"JWKS 拉取失败：{exc}") from exc
    app.extensions["oidc_jwks"][provider] = (now, jwks)
    return jwks


def verify_id_token(app: Any, provider: str, id_token: str) -> dict:
    """JWKS 验签 id_token，返回 claims；验签失败抛 OidcError。"""
    import jwt
    from jwt import PyJWK

    cfg = get_config(app, provider)
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise OidcError(f"id_token 格式非法：{exc}") from exc
    kid = header.get("kid")
    jwks = _jwks(app, provider)
    keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    if kid not in keys:
        jwks = _jwks(app, provider, force_refresh=True)
        keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    jwk_data = keys.get(kid)
    if jwk_data is None:
        raise OidcError("JWKS 中找不到匹配的签名密钥")
    algorithms = ["RS256"]
    alg = header.get("alg")
    if alg and alg.startswith(("RS", "ES", "PS")):
        algorithms = [alg]
    try:
        claims = jwt.decode(
            id_token,
            key=PyJWK.from_dict(jwk_data).key,
            algorithms=algorithms,
            audience=cfg["client_id"],
            issuer=cfg["issuer"],
        )
    except jwt.PyJWTError as exc:
        raise OidcError(f"id_token 验签失败：{exc}") from exc
    if not claims.get("sub"):
        raise OidcError("id_token 缺少 sub")
    return claims


def exchange_code(app: Any, provider: str, code: str) -> dict:
    """授权码换 token 并验签 id_token，返回用户 claims。"""
    cfg = get_config(app, provider)
    redirect_uri = _require_redirect_uri(cfg, provider)
    token_url = _endpoints(app, provider)["token"]
    payload = _http_post_form(
        token_url,
        {
            "grant_type": "authorization_code",
            "client_id": cfg["client_id"],
            "client_secret": cfg["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    id_token = payload.get("id_token")
    if not id_token:
        raise OidcError("OIDC 未返回 id_token")
    return verify_id_token(app, provider, id_token)
