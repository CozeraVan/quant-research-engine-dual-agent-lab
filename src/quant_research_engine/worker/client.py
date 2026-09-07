"""CloudClient：云端任务队列协议客户端（QRE-SAAS-002 协议的 Worker 侧）。

stdlib urllib 实现（项目 venv 无 requests，不引入新依赖）。所有请求带
X-Worker-Token、超时与指数退避有限重试（网络抖动/5xx 重试，最多
max_retries 次；401/409/4xx 业务错误不重试，直接抛 CloudError）。

配置走环境变量：SAAS_CLOUD_URL（如 https://aguhuice.com）、
SAAS_WORKER_TOKEN、SAAS_WORKER_ID（默认 hostname）。

测试注入：``request_fn(method, path, payload) -> (status, dict)`` 可替换
默认 urllib 传输（例如对接 Flask test_client 做本地闭环）。
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
from typing import Any, Callable

DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_BASE = 0.5  # 第 n 次重试前睡 backoff_base * 2^(n-1) 秒


class CloudError(RuntimeError):
    """云端返回非 2xx 或传输层最终失败。status=None 表示未拿到响应。"""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


RequestFn = Callable[[str, str, dict[str, Any] | None], tuple[int, dict[str, Any]]]


def _urllib_request_fn(base_url: str, token: str, timeout: float) -> RequestFn:
    def _do(method: str, path: str, payload: dict[str, Any] | None) -> tuple[int, dict[str, Any]]:
        body = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}{path}",
            data=body,
            method=method,
            headers={
                "X-Worker-Token": token,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            try:
                data = json.loads(exc.read().decode() or "{}")
            except (ValueError, UnicodeDecodeError):
                data = {}
            return exc.code, data
        # URLError / timeout 等传输错误向上抛，由重试层处理

    return _do


class CloudClient:
    def __init__(
        self,
        base_url: str,
        token: str,
        worker_id: str | None = None,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
        request_fn: RequestFn | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url:
            raise ValueError("SAAS_CLOUD_URL 未配置")
        if not token:
            raise ValueError("SAAS_WORKER_TOKEN 未配置")
        self.base_url = base_url
        self.worker_id = worker_id or socket.gethostname()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._request = request_fn or _urllib_request_fn(base_url, token, timeout)

    @classmethod
    def from_env(cls, **kwargs: Any) -> "CloudClient":
        return cls(
            base_url=os.environ.get("SAAS_CLOUD_URL", ""),
            token=os.environ.get("SAAS_WORKER_TOKEN", ""),
            worker_id=os.environ.get("SAAS_WORKER_ID") or None,
            **kwargs,
        )

    def _call(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """重试仅覆盖传输错误与 5xx；4xx 业务错误直接抛 CloudError。"""
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                status, data = self._request(method, path, payload)
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
            else:
                if 200 <= status < 300:
                    return data
                if status >= 500:
                    last_exc = CloudError(str(data.get("error") or f"云端 5xx（{status}）"), status)
                else:
                    raise CloudError(str(data.get("error") or f"云端拒绝（{status}）"), status)
            if attempt < self.max_retries:
                self._sleep(self.backoff_base * (2 ** (attempt - 1)))
        raise CloudError(f"云端不可达（重试 {self.max_retries} 次后放弃）：{last_exc}",
                         getattr(last_exc, "status", None))

    def lease(self) -> dict[str, Any] | None:
        """认领一个任务；无任务返回 None。"""
        data = self._call("POST", "/api/saas/worker/jobs/lease", {"worker_id": self.worker_id})
        return data.get("job")

    def heartbeat(self, job_id: int) -> None:
        self._call("POST", f"/api/saas/worker/jobs/{job_id}/heartbeat", {"worker_id": self.worker_id})

    def report_result(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self._call(
            "POST",
            f"/api/saas/worker/jobs/{job_id}/result",
            {"worker_id": self.worker_id, **payload},
        )
