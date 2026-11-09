"""P0-9 终态进度回归（2026-11-03 生产小样本实测 Required Fix）。

现象（job 212）：541 文件全部回传、result_files.truncated=false、job 已 completed，
但 jobs.progress=99 / progress_message='产物回传中 500/541 文件'。
根因：daemon 在 files 完成后才 heartbeat(100)，此时 job 已 completed，
heartbeat 的 WHERE 只放行 leased/running/uploading → 被拒，终态进度永远停在 99。

修复口径：服务端在把 job 置 completed 的同一事务里同步
progress=100 / progress_message='结果已回传'（meta-only completed 与旧单包
completed 同口径），不依赖 completed 后的 heartbeat；旧 worker（无上传心跳）
同样受益。未完成态不得虚构百分比（partial upload 保持 uploading 原值）。

覆盖：
1. files 全部落盘 → completed 且 progress=100、message='结果已回传'；
2. meta-only（无 blob）completed → progress=100、message='结果已回传'；
3. 部分上传（remaining 非空）→ 仍 uploading，progress 不被改成 100；
4. 旧单包 /result（done）completed → progress=100；
5. heartbeat 对 completed job 仍被拒（协议不变，证明不能依赖它）。
"""

from __future__ import annotations

import hashlib
import io
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import _get_engine

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}
TERMINAL_MESSAGE = "结果已回传"


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_tprog_test_{uuid.uuid4().hex[:12]}"
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
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "factor_requests, workers, worker_configs RESTART IDENTITY CASCADE"))


def _create_job(client):
    resp = client.post("/api/saas/jobs", json={
        "yaml": "experiment:\n  name: t\ndata:\n  market_fields: [close]\nsignal:\n  entry: close > 0\n",
        "kind": "full", "params": {"start": "2026-01-01", "end": "2026-03-01"},
    }, headers={"X-User-Id": "1"})
    return resp.get_json()["job_id"]


def _lease(client, worker_id="w1"):
    client.post("/api/worker/jobs/claim", json={"worker_id": worker_id},
                headers=WORKER_HEADERS)


def _job(client, job_id):
    return client.get(f"/api/saas/jobs/{job_id}", headers={"X-User-Id": "1"}).get_json()["job"]


def _upload(client, job_id, token, blobs):
    return client.post(
        f"/api/worker/jobs/{job_id}/result/files?upload_token={token}",
        data={n: (io.BytesIO(b), n) for n, b in blobs.items()},
        headers=WORKER_HEADERS)


class TestTerminalProgressOnCompleted:
    def test_files_completed_sets_progress_100(self, client):
        """job 212 回归：全部 blob 落盘 → completed 同一事务里 progress=100。"""
        job_id = _create_job(client)
        _lease(client)
        blobs = {f"f{i}.csv": b"x" for i in range(3)}
        files = [{"name": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                 for n, b in blobs.items()]
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {}, "chart_data": {},
                                 "data_until": "2026-03-01", "files": files},
                           headers=WORKER_HEADERS).get_json()
        # 分批上传（模拟 worker 分片 + 上传中心跳进度）
        names = list(blobs)
        for start in range(0, len(names), 2):
            chunk = names[start:start + 2]
            resp = _upload(client, job_id, meta["upload_token"],
                           {n: blobs[n] for n in chunk})
            assert resp.status_code == 200
            if resp.get_json()["status"] == "uploading":
                # 上传中途：心跳推进度（daemon 行为），仍不得提前 100
                client.post(f"/api/worker/jobs/{job_id}/heartbeat",
                            json={"worker_id": "w1", "progress": 99,
                                  "message": f"产物回传中 {start + len(chunk)}/{len(names)} 文件"},
                            headers=WORKER_HEADERS)
        assert resp.get_json()["status"] == "completed"
        job = _job(client, job_id)
        assert job["status"] == "completed"
        assert job["progress"] == 100
        assert job["progress_message"] == TERMINAL_MESSAGE

    def test_meta_only_completed_sets_progress_100(self, client):
        """meta-only（无 blob）completed：不虚构执行百分比，但终态可确定 100。"""
        job_id = _create_job(client)
        _lease(client)
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {}, "chart_data": {},
                                 "data_until": "2026-03-01", "files": []},
                           headers=WORKER_HEADERS).get_json()
        assert meta["status"] == "completed"
        job = _job(client, job_id)
        assert job["status"] == "completed"
        assert job["progress"] == 100
        assert job["progress_message"] == TERMINAL_MESSAGE

    def test_partial_upload_keeps_uploading_and_no_fake_100(self, client):
        """remaining 非空 → 仍 uploading；progress 不得被服务端改成 100。"""
        job_id = _create_job(client)
        _lease(client)
        blobs = {"a.csv": b"x", "b.csv": b"y"}
        files = [{"name": n, "size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                 for n, b in blobs.items()]
        meta = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                           json={"worker_id": "w1", "summary": {}, "chart_data": {},
                                 "data_until": "2026-03-01", "files": files},
                           headers=WORKER_HEADERS).get_json()
        resp = _upload(client, job_id, meta["upload_token"], {"a.csv": blobs["a.csv"]})
        assert resp.get_json()["status"] == "uploading"
        assert resp.get_json()["remaining"] == ["b.csv"]
        client.post(f"/api/worker/jobs/{job_id}/heartbeat",
                    json={"worker_id": "w1", "progress": 50, "message": "产物回传中 1/2 文件"},
                    headers=WORKER_HEADERS)
        job = _job(client, job_id)
        assert job["status"] == "uploading"
        assert job["progress"] == 50  # 心跳原值，不被篡改
        assert job["progress_message"] == "产物回传中 1/2 文件"

    def test_legacy_single_packet_completed_sets_progress_100(self, client):
        """旧单包 /result（done）completed 同口径落 100（旧 worker 兼容）。"""
        job_id = _create_job(client)
        _lease(client)
        resp = client.post(f"/api/saas/worker/jobs/{job_id}/result",
                           json={"worker_id": "w1", "status": "done",
                                 "summary": {}, "chart_data": {}},
                           headers=WORKER_HEADERS)
        assert resp.get_json()["status"] == "completed"
        job = _job(client, job_id)
        assert job["progress"] == 100
        assert job["progress_message"] == TERMINAL_MESSAGE

    def test_heartbeat_rejected_after_completed(self, client):
        """协议不变：completed 后 heartbeat 被拒（证明终态进度不能依赖它）。"""
        job_id = _create_job(client)
        _lease(client)
        client.post(f"/api/worker/jobs/{job_id}/result/meta",
                    json={"worker_id": "w1", "summary": {}, "chart_data": {},
                          "data_until": "2026-03-01", "files": []},
                    headers=WORKER_HEADERS)
        resp = client.post(f"/api/worker/jobs/{job_id}/heartbeat",
                           json={"worker_id": "w1", "progress": 100,
                                 "message": "结果已回传"},
                           headers=WORKER_HEADERS)
        assert resp.status_code == 409
