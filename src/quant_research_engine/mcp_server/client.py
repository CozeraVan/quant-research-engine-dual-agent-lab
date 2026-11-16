"""访问 QRE 外部 Agent API 的小型 HTTP 客户端。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import requests

DEFAULT_BASE_URL = "https://aguhuice.com"
API_SUFFIX = "/api/agent/v1"


class AgentAPIError(RuntimeError):
    """可安全展示给 MCP 调用方的上游错误。"""

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


def normalize_base_url(value: str) -> str:
    base = value.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise ValueError("QRE_API_BASE_URL 必须是 http(s) URL")
    if not base.endswith(API_SUFFIX):
        base += API_SUFFIX
    return base


@dataclass(frozen=True)
class AgentAPIConfig:
    base_url: str
    token: str
    timeout_seconds: float = 30.0
    max_response_bytes: int = 32 * 1024 * 1024

    @classmethod
    def from_env(cls) -> "AgentAPIConfig":
        token = os.environ.get("QRE_AGENT_TOKEN", "").strip()
        if not token:
            raise ValueError("缺少环境变量 QRE_AGENT_TOKEN")
        return cls(
            base_url=normalize_base_url(os.environ.get("QRE_API_BASE_URL", DEFAULT_BASE_URL)),
            token=token,
            timeout_seconds=float(os.environ.get("QRE_API_TIMEOUT_SECONDS", "30")),
            max_response_bytes=int(os.environ.get("QRE_API_MAX_RESPONSE_BYTES", str(32 * 1024 * 1024))),
        )


class AgentAPIClient:
    def __init__(self, config: AgentAPIConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self.session.request(
                method,
                f"{self.config.base_url}{path}",
                json=payload,
                headers={"Authorization": f"Bearer {self.config.token}", "Accept": "application/json"},
                timeout=self.config.timeout_seconds,
                stream=True,
            )
        except requests.RequestException as exc:
            raise AgentAPIError("QRE 上游连接失败，请稍后重试", code="upstream_unavailable") from exc

        with response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.config.max_response_bytes:
                raise AgentAPIError("QRE 响应超过 MCP 大小限制", status=response.status_code, code="response_too_large")
            raw = response.content
            if len(raw) > self.config.max_response_bytes:
                raise AgentAPIError("QRE 响应超过 MCP 大小限制", status=response.status_code, code="response_too_large")
            try:
                data = response.json()
            except ValueError as exc:
                raise AgentAPIError("QRE 上游返回了非 JSON 响应", status=response.status_code, code="invalid_upstream_response") from exc
            if response.status_code >= 400:
                error = data.get("error") if isinstance(data, dict) else None
                message = error.get("message") if isinstance(error, dict) else None
                code = error.get("code") if isinstance(error, dict) else None
                raise AgentAPIError(
                    str(message or f"QRE 请求失败（HTTP {response.status_code}）"),
                    status=response.status_code,
                    code=str(code or "upstream_error"),
                )
            if not isinstance(data, dict):
                raise AgentAPIError("QRE 上游 JSON 顶层必须是对象", code="invalid_upstream_response")
            return data
