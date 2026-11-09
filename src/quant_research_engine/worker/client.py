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
import secrets
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

#: P0-9（CR-2026-11-03）：分片上传阈值。manifest 实测可达 1,537+ 个文件，单请求
#: part 数超过 Flask MAX_FORM_PARTS（默认 1000，服务端已放大到 5000）必 413；
#: 按文件数与字节数双阈值分批，兼顾 nginx client_max_body_size 与重传粒度。
UPLOAD_CHUNK_FILES = 100
UPLOAD_CHUNK_BYTES = 8 * 1024 * 1024


def _iter_upload_batches(
    files: dict[str, bytes],
    max_files: int = UPLOAD_CHUNK_FILES,
    max_bytes: int = UPLOAD_CHUNK_BYTES,
):
    """把文件 dict 切成上传批次（保持插入序）：满 max_files 或超 max_bytes 即切；
    单个超大文件独占一批（不丢文件，也不无限并批）。"""
    batch: dict[str, bytes] = {}
    size = 0
    for name, blob in files.items():
        if batch and (len(batch) >= max_files or size + len(blob) > max_bytes):
            yield batch
            batch, size = {}, 0
        batch[name] = blob
        size += len(blob)
    if batch:
        yield batch


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
        upload_fn: Callable[[int, str, dict[str, bytes]], dict[str, Any]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not base_url:
            raise ValueError("SAAS_CLOUD_URL 未配置")
        if not token:
            raise ValueError("SAAS_WORKER_TOKEN 未配置")
        self.base_url = base_url
        self._token = token
        self._timeout = timeout
        self.worker_id = worker_id or socket.gethostname()
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self._sleep = sleep
        self._request = request_fn or _urllib_request_fn(base_url, token, timeout)
        self._upload_fn = upload_fn  # 测试注入点；None 时走 urllib multipart

    @classmethod
    def from_env(cls, **kwargs: Any) -> "CloudClient":
        # 新变量名（17 协议）优先，旧 SAAS_* 兼容
        base = os.environ.get("QRE_SAAS_BASE_URL") or os.environ.get("SAAS_CLOUD_URL", "")
        token = os.environ.get("QRE_WORKER_TOKEN") or os.environ.get("SAAS_WORKER_TOKEN", "")
        worker_id = os.environ.get("QRE_WORKER_ID") or os.environ.get("SAAS_WORKER_ID") or None
        return cls(base_url=base, token=token, worker_id=worker_id, **kwargs)

    def upload_files(self, job_id: int, upload_token: str,
                     files: dict[str, bytes],
                     *,
                     chunk_files: int = UPLOAD_CHUNK_FILES,
                     chunk_bytes: int = UPLOAD_CHUNK_BYTES,
                     on_batch: Callable[[dict[str, bytes], dict[str, Any]], None] | None = None,
                     ) -> dict[str, Any]:
        """17 协议 §3.3 第二步：multipart 上传产物文件（stdlib 手工拼包）。

        P0-9（CR-2026-11-03）分片上传：manifest 可能 >1000 part（全市场回测实测
        1,537），单请求必被 Flask MAX_FORM_PARTS 拒（413，item2/job7 一个 blob
        都没落盘）。按文件数/字节数分批多次 POST 同一端点——服务端按 upload_token
        幂等、已落盘文件不进 remaining，天然支持断点续传与重复提交。任一批 4xx /
        传输失败即抛 CloudError（带 status），由 daemon 落终态分类。
        """
        if self._upload_fn is not None:
            return self._upload_fn(job_id, upload_token, files)
        if not files:
            return {}
        last: dict[str, Any] = {}
        for batch in _iter_upload_batches(files, chunk_files, chunk_bytes):
            last = self._upload_batch(job_id, upload_token, batch)
            if on_batch is not None:
                on_batch(batch, last)
            if last.get("status") == "completed":
                return last
        if last.get("status") != "completed":
            raise CloudError(
                f"分片上传后仍有文件未确认落盘（status={last.get('status')}）", None
            )
        return last

    def _upload_batch(self, job_id: int, upload_token: str,
                      batch: dict[str, bytes]) -> dict[str, Any]:
        """单批 multipart POST（一批 ≤ chunk_files 个 part）。"""
        boundary = secrets.token_hex(16)
        parts: list[bytes] = []
        for name, blob in batch.items():
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{name}"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()
                + blob + b"\r\n"
            )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)
        req = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/api/worker/jobs/{job_id}/result/files?upload_token={upload_token}",
            data=body, method="POST",
            headers={"X-Worker-Token": self._token,
                     "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as exc:
            # P0-9（CR-2026-11-03）：HTTP 层拒绝必须带状态码上抛，让调用方落
            # error_class=result_upload_http_<code>；否则只看到 Connection reset，
            # 日志写成「等租约过期重排」，把 413 掩盖成连接问题。
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:200]
            except Exception:  # 响应体读取失败不影响状态码上报
                pass
            raise CloudError(
                f"产物回传被云端拒绝（HTTP {exc.code}）：{detail}", exc.code
            ) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # 传输层失败统一成 CloudError(status=None)：daemon 归 result_upload_error
            # （可重试），且重跑 upload_files 可按 remaining 幂等续传。
            raise CloudError(f"产物回传传输失败：{exc}", None) from exc

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

    def claim(self, wait_seconds: float = 0, classes: str = "any") -> dict[str, Any] | None:
        """认领一个任务（17 协议 §3.1 长轮询）；无任务返回 None。

        classes（R2 任务分级）："light" 只领轻量任务（轻量槽专用），
        "any" 领任意任务（默认，与旧版行为一致）。
        """
        data = self._call("POST", "/api/worker/jobs/claim",
                          {"worker_id": self.worker_id, "wait_seconds": wait_seconds,
                           "classes": classes})
        return data.get("job")

    # 过渡版兼容别名
    lease = claim

    def heartbeat(self, job_id: int, progress: int | None = None, message: str | None = None) -> dict[str, Any]:
        return self._call("POST", f"/api/worker/jobs/{job_id}/heartbeat",
                          {"worker_id": self.worker_id, "progress": progress, "message": message})

    def report_result(self, job_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        """两步回传（17 协议 §3.3）：meta →（有文件时）files。

        P0-9（CR-2026-11-03 §8.5）：转发 ``symbol_details`` 与 ``result_files``
        截断/完整性元数据（此前被丢弃，压测记录的 symbol_details 恒 null 即此根因）；
        旧 worker payload 不带这两个键时不出现在请求体里（服务端存 NULL，兼容）。
        """
        meta = {"worker_id": self.worker_id,
                "summary": payload.get("summary"),
                "chart_data": payload.get("chart_data"),
                "data_until": payload.get("data_until"),
                "files": [{k: v for k, v in f.items() if k != "path"} for f in (payload.get("files") or [])]}
        for key in ("symbol_details", "result_files"):
            value = payload.get(key)
            if value is not None:
                meta[key] = value
        return self._call("POST", f"/api/worker/jobs/{job_id}/result/meta", meta)

    def report_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        """R3 切片1：上报实时状态（槽位占用 + 内存水位）。"""
        body = {"worker_id": self.worker_id, **payload}
        return self._call("POST", "/api/worker/status", body)

    def fail(self, job_id: int, error: str, error_class: str = "engine_error") -> dict[str, Any]:
        return self._call("POST", f"/api/worker/jobs/{job_id}/fail",
                          {"worker_id": self.worker_id, "error_class": error_class,
                           "error_message": error})
