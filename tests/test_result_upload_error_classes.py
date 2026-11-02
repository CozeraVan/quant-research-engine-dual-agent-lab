"""P0-9 结果回传缺陷回归（CR-2026-11-03，压测实测立项）。

覆盖三件事：
1. 服务端 `MAX_FORM_PARTS` 足够大——全市场回测 manifest 实测 1,537 part，
   Flask 3.1 默认 1000 会 413，产物一个都回传不了；
2. worker 客户端把 HTTP 拒绝升级为带 status 的 CloudError（不再退化成 Connection reset）；
3. daemon 回传失败落终态 failed + 分类 error_class，不再「等租约过期重排」
   （否则同一份已算完的结果会被 reaper 重排再算一遍）。

另锁 worker 与 SaaS 两侧的分类白名单一致性（两边各一份定义，禁止漂移）。
"""

from __future__ import annotations

import io
import urllib.error

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import ERROR_CLASSES, NON_RETRYABLE
from quant_research_engine.worker import daemon as worker_daemon
from quant_research_engine.worker.client import CloudClient, CloudError

WORKER_TOKEN = "test-worker-token"


@pytest.fixture()
def app():
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = "postgresql+psycopg:///qre_saas_test_none"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    yield app


class TestMaxFormParts:
    def test_max_form_parts_raised_above_measured_manifest(self, app):
        """压测实测 manifest 1,537 part → 413；配置必须显著大于该值。"""
        limit = app.config.get("MAX_FORM_PARTS")
        assert isinstance(limit, int) and limit >= 1537 * 2, (
            f"MAX_FORM_PARTS={limit} 不足以覆盖全市场回传（实测 1,537 part）"
        )


class TestUploadHttpClassification:
    def test_http_error_becomes_clouderror_with_status(self, monkeypatch):
        """HTTPError 必须带状态码上抛，否则调用方只能看到 Connection reset。"""

        def _fake_urlopen(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 413, "Request Entity Too Large",
                {"Content-Type": "text/plain"}, io.BytesIO(b"too many parts"),
            )

        monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
        client = CloudClient(base_url="http://127.0.0.1:1", token="t", worker_id="w")
        with pytest.raises(CloudError) as excinfo:
            client.upload_files(1, "tok", {"a.csv": b"x"})
        assert excinfo.value.status == 413
        assert "413" in str(excinfo.value)

    def test_success_path_unaffected(self, monkeypatch):
        class _Resp:
            def read(self):
                return b'{"ok": true}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: _Resp())
        client = CloudClient(base_url="http://127.0.0.1:1", token="t", worker_id="w")
        assert client.upload_files(1, "tok", {"a.csv": b"x"}) == {"ok": True}


class TestErrorClassConsistency:
    def test_worker_mirror_matches_saas_classes(self):
        """worker 不 import SaaS app，白名单在此镜像；两边必须一致。"""
        for code in worker_daemon._UPLOAD_HTTP_CLASSES:
            assert f"result_upload_http_{code}" in ERROR_CLASSES, code
        assert "result_upload_error" in ERROR_CLASSES

    def test_upload_4xx_classes_are_non_retryable(self):
        """4xx 回传失败不可重试：重试只会把同一份结果再算一遍。"""
        for code in (400, 401, 403, 404, 409, 413, 422, 429):
            assert f"result_upload_http_{code}" in NON_RETRYABLE, code

    def test_transport_upload_error_is_retryable(self):
        """B1 修正：传输/5xx 的 result_upload_error 必须**可重试**——
        与 17_JOB_PROTOCOL §3.4 及 daemon 注释一致。此前误放进 NON_RETRYABLE，
        导致连接重置也直接 failed，与文档矛盾。"""
        assert "result_upload_error" in ERROR_CLASSES
        assert "result_upload_error" not in NON_RETRYABLE


class TestDaemonUploadFailure:
    """daemon 回传失败必须落终态。用最小假 client 捕获 fail() 调用参数。"""

    def _daemon_with_failing_upload(self, exc: Exception, fail_calls: list):
        from quant_research_engine.worker.daemon import WorkerDaemon

        class _Client:
            worker_id = "w"
            base_url = "http://127.0.0.1:1"

            def report_result(self, job_id, payload):
                return {"upload_token": "tok"}

            def upload_files(self, job_id, upload_token, blobs):
                raise exc

            def fail(self, job_id, error, error_class="engine_error"):
                fail_calls.append({"job_id": job_id, "error": error,
                                   "error_class": error_class})
                return {"ok": True}

        daemon = WorkerDaemon.__new__(WorkerDaemon)
        daemon.client = _Client()
        return daemon

    def _run_upload(self, daemon, job_id, monkeypatch):
        """走到 upload_files：开上传开关 + 给一个文件 + 读字节不落盘。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        monkeypatch.setattr(worker_daemon.Path, "read_bytes", lambda self: b"x")
        daemon._report_results(job_id, {"summary": {},
                                        "files": [{"name": "a.csv", "path": "/x"}]})

    def test_http_413_reports_failed_with_status_class(self, monkeypatch):
        calls: list[dict] = []
        daemon = self._daemon_with_failing_upload(
            CloudError("产物回传被云端拒绝（HTTP 413）：too many parts", 413), calls)
        self._run_upload(daemon, 7, monkeypatch)
        assert calls and calls[0]["error_class"] == "result_upload_http_413"
        assert calls[0]["job_id"] == 7

    def test_transport_error_reports_retryable_class(self, monkeypatch):
        calls: list[dict] = []
        daemon = self._daemon_with_failing_upload(
            CloudError("云端不可达（重试 3 次后放弃）"), calls)
        self._run_upload(daemon, 8, monkeypatch)
        assert calls and calls[0]["error_class"] == "result_upload_error"

    def test_http_500_classified_as_transport_error(self, monkeypatch):
        """5xx 不走 result_upload_http_500（保持可重试语义），归入 result_upload_error。"""
        calls: list[dict] = []
        daemon = self._daemon_with_failing_upload(
            CloudError("云端 5xx（500）", 500), calls)
        self._run_upload(daemon, 10, monkeypatch)
        assert calls and calls[0]["error_class"] == "result_upload_error"

    def test_upload_disabled_skips_files_and_succeeds(self, monkeypatch):
        calls: list[dict] = []
        daemon = self._daemon_with_failing_upload(RuntimeError("不应被调用"), calls)
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: False)
        daemon._report_results(9, {"summary": {}, "files": [{"name": "a", "path": "/x"}]})
        assert calls == []  # 不上传即不回传失败，更不会 fail
