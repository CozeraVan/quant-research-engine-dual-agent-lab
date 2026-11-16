"""CLI 短信登录与本机 MCP 凭证管理。"""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
from typing import Any

from .client import AgentAPIClient, AgentAPIConfig, DEFAULT_BASE_URL, normalize_base_url

CREDENTIAL_SCHEMA = "qre-mcp-credentials-v1"


def credentials_path() -> Path:
    explicit = os.environ.get("QRE_MCP_CREDENTIALS", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    return config_home / "qre" / "mcp.json"


def load_credentials(path: Path | None = None) -> dict[str, Any] | None:
    target = path or credentials_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"MCP 凭证文件不可读或已损坏：{target}") from exc
    if data.get("schema") != CREDENTIAL_SCHEMA or not data.get("agent_token"):
        raise ValueError("MCP 凭证格式不正确，请重新登录")
    return data


def save_credentials(data: dict[str, Any], path: Path | None = None) -> Path:
    target = path or credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(target)
    return target


def login(phone: str, sms_code: str | None = None, *, base_url: str, path: Path | None = None) -> dict[str, Any]:
    """用既有短信登录创建专用 Agent token；不保存短信码或账号密码。"""
    base = normalize_base_url(base_url)
    # 登录端点在 /api/saas，不属于 /api/agent/v1；使用同一受控 requests 会话。
    import requests

    session = requests.Session()
    api_root = base[:-len("/api/agent/v1")]

    def post(path_name: str, payload: dict[str, Any], bearer: str = "") -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
        response = session.post(api_root + path_name, json=payload, headers=headers, timeout=30)
        data = response.json()
        if response.status_code >= 400 or not data.get("ok"):
            error = data.get("error")
            message = error.get("message") if isinstance(error, dict) else error
            raise ValueError(str(message or f"登录失败（HTTP {response.status_code}）"))
        return data

    post("/api/saas/auth/code", {"target": phone})
    if sms_code is None:
        sms_code = getpass.getpass("短信验证码：").strip()
    logged = post("/api/saas/auth/login", {"target": phone, "code": sms_code, "auth_mode": "sms"})
    session_token = logged["token"]
    created = post("/api/agent/v1/tokens", {
        "name": "qre-mcp-cli", "expires_days": 30, "nightly_only": False,
        "allow_full_market": False,
    }, session_token)
    data = {
        "schema": CREDENTIAL_SCHEMA,
        "base_url": api_root,
        "agent_token": created["token"]["plaintext"],
        "agent_token_id": created["token"]["id"],
        "session_token": session_token,
        "expires_at": created["token"]["expires_at"],
    }
    saved = save_credentials(data, path)
    return {"saved_to": str(saved), "expires_at": data["expires_at"], "phone": phone}


def logout(*, path: Path | None = None) -> bool:
    target = path or credentials_path()
    data = load_credentials(target)
    if data is None:
        return False
    try:
        AgentAPIClient(AgentAPIConfig(
            base_url=normalize_base_url(data["base_url"]), token=data["session_token"],
        )).request("POST", f"/tokens/{data['agent_token_id']}/revoke", {})
    finally:
        target.unlink(missing_ok=True)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="QRE MCP CLI 登录")
    parser.add_argument("--logout", action="store_true", help="吊销当前 Agent token 并删除本机凭证")
    parser.add_argument("--phone", help="手机号；缺省交互输入")
    args = parser.parse_args()
    if args.logout:
        print("已退出并删除本机凭证" if logout() else "本机没有已保存的 MCP 凭证")
        return
    phone = args.phone or input("手机号：").strip()
    result = login(
        phone,
        base_url=os.environ.get("QRE_API_BASE_URL", DEFAULT_BASE_URL),
    )
    print(json.dumps({"ok": True, "saved_to": result["saved_to"], "expires_at": result["expires_at"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
