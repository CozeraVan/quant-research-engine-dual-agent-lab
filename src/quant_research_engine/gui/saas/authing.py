"""Authing OIDC 登录换票（QRE-AUTH-MEMBERSHIP / A3，18 号设计文档 §2/§5）。

流程：登录页按钮 → GET /saas/login/authing（302 到 Authing 托管登录页，
state 内存暂存 10 分钟）→ Authing 回调 GET /saas/login/callback?code&state
→ 本模块用 App Secret 调 token_endpoint 换 token → JWKS（RS256）验签
id_token（内存缓存公钥，kid 未命中强制刷新一次）→ 按 sub 关联/自动建档
users 行 → 签发本地 sessions token（前端 Bearer 机制零改动）。

requests/pyjwt 为惰性导入：未配置 AUTHING_APP_ID 或未安装依赖时，
相关端点返回 503，其余功能不受影响（ECS 精简 venv 需 pip install
'pyjwt[crypto]' requests，见 16 号文档）。
"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode

JWKS_CACHE_TTL_SECONDS = 3600
STATE_TTL_SECONDS = 600
HTTP_TIMEOUT_SECONDS = 10


class AuthingError(Exception):
    """用户可读的 Authing 链路错误（换票失败/验签失败/配置缺失）。"""


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
        raise AuthingError(f"Authing 返回了非 JSON 响应（HTTP {resp.status_code}）") from exc
    if resp.status_code != 200:
        desc = payload.get("error_description") or payload.get("error") or f"HTTP {resp.status_code}"
        raise AuthingError(f"Authing 换票失败：{desc}")
    return payload


def _authing_config(app: Any) -> dict[str, str]:
    from quant_research_engine.gui.saas.app import _cfg

    app_id = (_cfg(app, "AUTHING_APP_ID") or "").strip()
    secret = (_cfg(app, "AUTHING_APP_SECRET") or "").strip()
    host = (_cfg(app, "AUTHING_HOST") or "").strip().rstrip("/")
    if not app_id or not secret or not host:
        raise AuthingError("Authing 未配置（AUTHING_APP_ID/SECRET/HOST）")
    return {"app_id": app_id, "secret": secret, "host": host}


def _redirect_uri(app: Any) -> str:
    from quant_research_engine.gui.saas.app import _cfg

    uri = (_cfg(app, "AUTHING_REDIRECT_URI") or "").strip()
    if uri:
        return uri
    from flask import request

    return request.url_root.rstrip("/") + "/saas/login/callback"


def build_authorize_url(app: Any, state: str) -> str:
    cfg = _authing_config(app)
    query = urlencode({
        "client_id": cfg["app_id"],
        "redirect_uri": _redirect_uri(app),
        "response_type": "code",
        "scope": "openid profile phone",
        "state": state,
    })
    return f"{cfg['host']}/oidc/auth?{query}"


def new_state(app: Any) -> str:
    import secrets

    state = secrets.token_urlsafe(24)
    store = app.extensions.setdefault("authing_states", {})
    now = time.time()
    expired = [k for k, ts in store.items() if now - ts > STATE_TTL_SECONDS]
    for k in expired:
        store.pop(k, None)
    store[state] = now
    return state


def pop_state(app: Any, state: str) -> bool:
    store = app.extensions.setdefault("authing_states", {})
    ts = store.pop(state, None)
    return ts is not None and time.time() - ts <= STATE_TTL_SECONDS


def _jwks(app: Any, *, force_refresh: bool = False) -> dict:
    cfg = _authing_config(app)
    cached = app.extensions.get("authing_jwks")
    now = time.time()
    if cached and not force_refresh and now - cached[0] < JWKS_CACHE_TTL_SECONDS:
        return cached[1]
    url = f"{cfg['host']}/oidc/.well-known/jwks.json"
    try:
        jwks = _http_get_json(url)
    except Exception as exc:
        raise AuthingError(f"JWKS 拉取失败：{exc}") from exc
    app.extensions["authing_jwks"] = (now, jwks)
    return jwks


def verify_id_token(app: Any, id_token: str) -> dict:
    """JWKS 验签 id_token，返回 claims；验签失败抛 AuthingError。"""
    import jwt
    from jwt import PyJWK

    cfg = _authing_config(app)
    try:
        header = jwt.get_unverified_header(id_token)
    except jwt.PyJWTError as exc:
        raise AuthingError(f"id_token 格式非法：{exc}") from exc
    kid = header.get("kid")
    jwks = _jwks(app)
    keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    if kid not in keys:
        # kid 未命中：强制刷新一次 JWKS（密钥轮换场景）
        jwks = _jwks(app, force_refresh=True)
        keys = {k.get("kid"): k for k in jwks.get("keys", [])}
    jwk_data = keys.get(kid)
    if jwk_data is None:
        raise AuthingError("JWKS 中找不到匹配的签名密钥")
    try:
        claims = jwt.decode(
            id_token,
            key=PyJWK.from_dict(jwk_data).key,
            algorithms=["RS256"],
            audience=cfg["app_id"],
            issuer=f"{cfg['host']}/oidc",
        )
    except jwt.PyJWTError as exc:
        raise AuthingError(f"id_token 验签失败：{exc}") from exc
    if not claims.get("sub"):
        raise AuthingError("id_token 缺少 sub")
    return claims


def exchange_code(app: Any, code: str) -> dict:
    """授权码换 token 并验签 id_token，返回用户 claims。"""
    cfg = _authing_config(app)
    payload = _http_post_form(
        f"{cfg['host']}/oidc/token",
        {
            "grant_type": "authorization_code",
            "client_id": cfg["app_id"],
            "client_secret": cfg["secret"],
            "code": code,
            "redirect_uri": _redirect_uri(app),
        },
    )
    id_token = payload.get("id_token")
    if not id_token:
        raise AuthingError("Authing 未返回 id_token")
    return verify_id_token(app, id_token)
