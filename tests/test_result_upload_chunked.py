"""P0-9 B 分片上传回归（CR-2026-11-03，压测实测立项）。

根因：worker 一个产物文件一个 multipart part，全市场回测 manifest 实测 1,537 part，
超过 Flask 3.1 默认 MAX_FORM_PARTS=1000 → 413，产物一个都回传不了（item2/job7）。
修复：worker 侧按「文件数/字节数」分批多次 POST 同一端点（服务端按 upload_token
幂等 + 已落盘文件跳过，天然断点续传），协议零变化。

覆盖：
1. 纯分批函数边界（100/101 文件、字节阈值、超大单文件、空清单）；
2. >1000 小文件分片（1024 个 1B 文件 → 多批请求，每批 part 数远低于 1000）；
3. 传输失败可重试（CloudError status=None → result_upload_error）与重复提交幂等；
4. 服务端：单包 >1000 part 仍 413（根因锁定）、分片全量落盘 → completed、
   sha256 不符 400、清单外文件 400；
5. daemon：manifest 有文件但本地缺失 → result_upload_error 落终态。
"""

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import urllib.error
import uuid
from pathlib import Path

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.worker import daemon as worker_daemon
from quant_research_engine.worker.client import CloudClient, CloudError, _iter_upload_batches

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_upload_test_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


@pytest.fixture()
def app(saas_db, tmp_path):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_UPLOAD_DIR"] = str(tmp_path / "uploads")
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "factor_requests, workers, worker_configs RESTART IDENTITY CASCADE"))


def _create_job(client, kind="full"):
    resp = client.post("/api/saas/jobs", json={
        "yaml": "experiment:\n  name: t\ndata:\n  market_fields: [close]\nsignal:\n  entry: close > 0\n",
        "kind": kind,
        "params": {"start": "2026-01-01", "end": "2026-03-01"},
    }, headers={"X-User-Id": "1"})
    assert resp.status_code == 200
    return resp.get_json()["job_id"]


def _lease(client, worker_id="w1"):
    resp = client.post("/api/worker/jobs/claim", json={"worker_id": worker_id},
                       headers=WORKER_HEADERS)
    return resp.get_json()["job"]


def _post_meta(client, job_id, files, worker_id="w1"):
    resp = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                       json={"worker_id": worker_id, "summary": {"total_return": 0.1},
                             "chart_data": {}, "data_until": "2026-03-01",
                             "files": files},
                       headers=WORKER_HEADERS)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _manifest_entry(name: str, blob: bytes) -> dict:
    return {"name": name, "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest()}


# ---------------------------------------------------------------------------
# 纯分批函数
# ---------------------------------------------------------------------------

class TestIterUploadBatches:
    def test_exactly_max_files_is_one_batch(self):
        files = {f"f{i}.csv": b"x" for i in range(100)}
        assert len(list(_iter_upload_batches(files, 100, 8 * 1024 * 1024))) == 1

    def test_one_over_max_files_splits(self):
        files = {f"f{i}.csv": b"x" for i in range(101)}
        batches = list(_iter_upload_batches(files, 100, 8 * 1024 * 1024))
        assert [len(b) for b in batches] == [100, 1]

    def test_byte_threshold_splits(self):
        files = {"a": b"xxxx", "b": b"xxxx", "c": b"xxxx"}
        batches = list(_iter_upload_batches(files, 100, 8))
        assert [sorted(b) for b in batches] == [["a", "b"], ["c"]]

    def test_single_oversized_file_gets_own_batch(self):
        files = {"a": b"x" * 100, "b": b"y" * 100}
        batches = list(_iter_upload_batches(files, 100, 50))
        assert [sorted(b) for b in batches] == [["a"], ["b"]]

    def test_empty_manifest_yields_no_batches(self):
        assert list(_iter_upload_batches({}, 100, 8 * 1024 * 1024)) == []


# ---------------------------------------------------------------------------
# client 分片（假传输层：真实走 upload_files 的拼包/分批逻辑）
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _parse_multipart(body: bytes, content_type: str) -> dict[str, bytes]:
    boundary = content_type.split("boundary=")[1].strip().strip('"')
    out: dict[str, bytes] = {}
    for part in body.split(("--" + boundary).encode()):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        head, _, blob = part.partition(b"\r\n\r\n")
        name = None
        for line in head.split(b"\r\n"):
            if line.lower().startswith(b"content-disposition"):
                for seg in line.split(b";"):
                    seg = seg.strip()
                    if seg.startswith(b'name="'):
                        name = seg[len(b'name="'):-1].decode()
        if name is not None:
            out[name] = blob
    return out


class _FakeUploadServer:
    """记录每批请求与已落盘文件；按 manifest 结算 remaining/completed。"""

    def __init__(self, manifest: dict[str, str]):
        self.manifest = manifest
        self.landed: set[str] = set()
        self.batches: list[dict[str, bytes]] = []
        self.raise_once: Exception | None = None

    def __call__(self, req, timeout=None):
        files = _parse_multipart(req.data, req.headers["Content-type"])
        if self.raise_once is not None:
            exc, self.raise_once = self.raise_once, None
            raise exc
        self.batches.append(files)
        self.landed.update(files)
        remaining = sorted(set(self.manifest) - self.landed)
        if remaining:
            payload = {"ok": True, "status": "uploading",
                       "uploaded": sorted(files), "remaining": remaining}
        else:
            payload = {"ok": True, "status": "completed", "uploaded": sorted(files)}
        return _FakeResponse(json.dumps(payload).encode())


def _client(monkeypatch, server) -> CloudClient:
    monkeypatch.setattr("urllib.request.urlopen", server)
    return CloudClient(base_url="http://127.0.0.1:1", token="t", worker_id="w")


class TestClientChunkedUpload:
    def test_over_1000_small_files_split_into_many_requests(self, monkeypatch):
        """压测根因回归：1024 个 1B 文件（单包 1024 part > MAX_FORM_PARTS=1000 → 413）。
        分片后每批 ≤100 part，全部文件各到达一次，最终 completed。"""
        manifest = {f"f{i:04d}.csv": hashlib.sha256(b"x").hexdigest() for i in range(1024)}
        server = _FakeUploadServer(manifest)
        client = _client(monkeypatch, server)
        resp = client.upload_files(7, "tok", {name: b"x" for name in manifest})
        assert resp["status"] == "completed"
        assert len(server.batches) == 11  # 10×100 + 24
        assert all(len(b) <= 100 for b in server.batches)
        delivered = [n for b in server.batches for n in b]
        assert sorted(delivered) == sorted(manifest)
        assert len(delivered) == len(set(delivered))  # 无重复投递

    def test_transport_failure_raises_retryable_clouderror_then_resumes(self, monkeypatch):
        """传输失败 → CloudError(status=None)（daemon 归 result_upload_error 可重试）；
        重跑 upload_files 幂等续传（已落盘文件不重复计 remaining）。"""
        manifest = {f"f{i}.csv": "sha" for i in range(250)}
        server = _FakeUploadServer(manifest)
        server.raise_once = urllib.error.URLError("connection reset by peer")
        client = _client(monkeypatch, server)
        with pytest.raises(CloudError) as excinfo:
            client.upload_files(7, "tok", {n: b"x" for n in manifest})
        assert excinfo.value.status is None  # 传输层：可重试分类
        resp = client.upload_files(7, "tok", {n: b"x" for n in manifest})
        assert resp["status"] == "completed"
        assert server.landed == set(manifest)

    def test_duplicate_batch_submission_is_idempotent(self, monkeypatch):
        """重复提交同一批：覆盖写 + remaining 重算，不影响最终 completed。"""
        manifest = {"a.csv": "sha", "b.csv": "sha"}
        server = _FakeUploadServer(manifest)
        client = _client(monkeypatch, server)
        first = client._upload_batch(7, "tok", {"a.csv": b"x"})
        assert first["status"] == "uploading" and first["remaining"] == ["b.csv"]
        duplicate = client._upload_batch(7, "tok", {"a.csv": b"x"})
        assert duplicate["status"] == "uploading" and duplicate["remaining"] == ["b.csv"]
        final = client._upload_batch(7, "tok", {"b.csv": b"x"})
        assert final["status"] == "completed"
        assert server.landed == set(manifest)

    def test_http_4xx_still_raises_with_status(self, monkeypatch):
        """分片内任一批 4xx 仍带状态码上抛（result_upload_http_<code> 不可重试）。"""

        def _raise(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 413, "Request Entity Too Large",
                {"Content-Type": "text/plain"}, io.BytesIO(b"too many parts"))

        monkeypatch.setattr("urllib.request.urlopen", _raise)
        client = CloudClient(base_url="http://127.0.0.1:1", token="t", worker_id="w")
        with pytest.raises(CloudError) as excinfo:
            client.upload_files(7, "tok", {"a.csv": b"x"})
        assert excinfo.value.status == 413

    def test_unfinished_after_all_batches_raises(self, monkeypatch):
        """全部批次发完服务端仍不 completed（异常态）→ 抛错走可重试分类，不谎报成功。"""
        server = _FakeUploadServer({"a.csv": "sha", "b.csv": "sha"})
        client = _client(monkeypatch, server)

        def _always_uploading(req, timeout=None):
            files = _parse_multipart(req.data, req.headers["Content-type"])
            server.batches.append(files)
            server.landed.update(files)
            return _FakeResponse(json.dumps(
                {"ok": True, "status": "uploading", "uploaded": sorted(files),
                 "remaining": ["ghost.csv"]}).encode())

        monkeypatch.setattr("urllib.request.urlopen", _always_uploading)
        with pytest.raises(CloudError) as excinfo:
            client.upload_files(7, "tok", {"a.csv": b"x", "b.csv": b"x"})
        assert excinfo.value.status is None


# ---------------------------------------------------------------------------
# 服务端：分片落盘 / 根因锁定 / 校验
# ---------------------------------------------------------------------------

class TestServerChunkedUpload:
    def test_single_request_over_max_form_parts_still_413(self, client):
        """根因锁定：单包 part 数超过服务端 MAX_FORM_PARTS（现为 5000，压测 manifest
        实测 1,537、item3 更高达 26,026 文件）仍被 werkzeug 拒。配置放大只是抬高
        上限、不根治——分片上传才是任意大小 manifest 的解法。"""
        job_id = _create_job(client)
        _lease(client)
        blobs = {f"f{i:05d}.csv": b"x" for i in range(5001)}
        files = [_manifest_entry(n, b) for n, b in blobs.items()]
        meta = _post_meta(client, job_id, files)
        resp = client.post(
            f"/api/worker/jobs/{job_id}/result/files?upload_token={meta['upload_token']}",
            data={n: (io.BytesIO(b), n) for n, b in blobs.items()},
            headers=WORKER_HEADERS)
        assert resp.status_code == 413
        # 同一 manifest 分片上传必须成功（根因修复的正面证据）
        names = list(blobs)
        for start in range(0, len(names), 100):
            chunk = names[start:start + 100]
            resp = client.post(
                f"/api/worker/jobs/{job_id}/result/files?upload_token={meta['upload_token']}",
                data={n: (io.BytesIO(blobs[n]), n) for n in chunk},
                headers=WORKER_HEADERS)
            assert resp.status_code == 200, resp.get_json()
        assert resp.get_json()["status"] == "completed"
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "completed"

    def test_chunked_uploads_complete_1024_file_manifest(self, client, app):
        """1024 个文件分 11 批上传：每批 200 + remaining 递减，最终 completed 且全部落盘。"""
        job_id = _create_job(client)
        _lease(client)
        blobs = {f"f{i:04d}.csv": b"x" for i in range(1024)}
        files = [_manifest_entry(n, b) for n, b in blobs.items()]
        meta = _post_meta(client, job_id, files)
        token = meta["upload_token"]
        names = list(blobs)
        last = None
        for start in range(0, len(names), 100):
            chunk = names[start:start + 100]
            resp = client.post(
                f"/api/worker/jobs/{job_id}/result/files?upload_token={token}",
                data={n: (io.BytesIO(blobs[n]), n) for n in chunk},
                headers=WORKER_HEADERS)
            assert resp.status_code == 200, resp.get_json()
            last = resp.get_json()
            if last["status"] == "uploading":
                assert len(last["remaining"]) == len(names) - (start + 100)
        assert last["status"] == "completed"
        upload_dir = Path(app.config["SAAS_UPLOAD_DIR"]) / f"job_{job_id}"
        assert sorted(p.name for p in upload_dir.iterdir()) == sorted(names)
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "completed"

    def test_sha256_mismatch_rejected_and_job_stays_uploading(self, client):
        """sha256 不符 → 400，不落盘，job 不 completed（worker 会按 4xx 落 failed）。"""
        job_id = _create_job(client)
        _lease(client)
        blob = b"real-content"
        files = [{"name": "a.csv", "size": len(blob), "sha256": "0" * 64}]
        meta = _post_meta(client, job_id, files)
        resp = client.post(
            f"/api/worker/jobs/{job_id}/result/files?upload_token={meta['upload_token']}",
            data={"a.csv": (io.BytesIO(blob), "a.csv")}, headers=WORKER_HEADERS)
        assert resp.status_code == 400
        assert "校验失败" in resp.get_json()["error"]
        detail = client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]
        assert detail["status"] == "uploading"

    def test_file_outside_manifest_rejected(self, client):
        job_id = _create_job(client)
        _lease(client)
        blob = b"x"
        meta = _post_meta(client, job_id, [_manifest_entry("a.csv", blob)])
        resp = client.post(
            f"/api/worker/jobs/{job_id}/result/files?upload_token={meta['upload_token']}",
            data={"evil.csv": (io.BytesIO(blob), "evil.csv")}, headers=WORKER_HEADERS)
        assert resp.status_code == 400
        assert "不在清单内" in resp.get_json()["error"]


# ---------------------------------------------------------------------------
# daemon：本地文件缺失 → 可重试回传失败终态
# ---------------------------------------------------------------------------

class TestDaemonMissingLocalFile:
    def test_missing_local_file_reports_result_upload_error(self, monkeypatch):
        """manifest 登记了文件但本地已缺失（被清理/未落盘）：不能静默少传，
        必须落 result_upload_error（可重试）而不是假装成功。"""
        calls: list[dict] = []

        class _Client:
            worker_id = "w"
            base_url = "http://127.0.0.1:1"

            def report_result(self, job_id, payload):
                return {"upload_token": "tok"}

            def upload_files(self, job_id, upload_token, blobs, **kwargs):
                raise AssertionError("本地文件缺失时不应走到上传")

            def fail(self, job_id, error, error_class="engine_error"):
                calls.append({"job_id": job_id, "error": error, "error_class": error_class})
                return {"ok": True}

        daemon = worker_daemon.WorkerDaemon.__new__(worker_daemon.WorkerDaemon)
        daemon.client = _Client()
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        daemon._report_results(7, {
            "summary": {},
            "files": [{"name": "a.csv", "path": "/definitely/missing/a.csv",
                       "size": 1, "sha256": "x"}],
        })
        assert calls and calls[0]["error_class"] == "result_upload_error"
        assert calls[0]["job_id"] == 7
