"""P0-9 §8.15 reaper 防重算加固回归（CR-2026-11-03，压测实测立项）。

根因：`_reap_expired` 把「uploading + 租约过期 + attempts<max」重排回 queued。
若 worker 在回传中途死亡（meta 已入库、blob 缺失），同一份 42 分钟 / 6 GB 的
全市场计算会被**整单重算**（压测实测 job7 的场景；A+C 修复后 worker 会主动
fail，但进程被 kill 在回传中途仍走重排路径）。

修复：uploading 且已有 results 行 → 直接 failed（error_class=result_upload_error，
可读 message「回传中断、结果不完整」），不回队；无 results 行的 uploading 维持
原语义（attempts<max 回队）；running/leased 不受影响（重试会覆盖 results）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest
from sqlalchemy import text

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.gui.saas.app import _get_engine, _reap_expired

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_reap_test_{uuid.uuid4().hex[:12]}"
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


def _create_job(client, kind="full"):
    resp = client.post("/api/saas/jobs", json={
        "yaml": "experiment:\n  name: t\ndata:\n  market_fields: [close]\nsignal:\n  entry: close > 0\n",
        "kind": kind,
        "params": {"start": "2026-01-01", "end": "2026-03-01"},
    }, headers={"X-User-Id": "1"})
    return resp.get_json()["job_id"]


def _lease(client, worker_id="w1"):
    client.post("/api/worker/jobs/claim", json={"worker_id": worker_id},
                headers=WORKER_HEADERS)


def _uploading_with_results(client, job_id, worker_id="w1"):
    """lease + meta（带一个文件清单）→ uploading 且 results 行已存在。"""
    _lease(client, worker_id)
    resp = client.post(f"/api/worker/jobs/{job_id}/result/meta",
                       json={"worker_id": worker_id, "summary": {"total_return": 0.1},
                             "chart_data": {}, "data_until": "2026-03-01",
                             "files": [{"name": "a.csv", "size": 1, "sha256": "x" * 64}]},
                       headers=WORKER_HEADERS)
    assert resp.get_json()["status"] == "uploading"
    return resp.get_json()["upload_token"]


def _expire_lease(app, job_id):
    engine = _get_engine(app)
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET lease_expires_at = now() - interval '1 minute' "
                          "WHERE id = :id"), {"id": job_id})


def _reap(app):
    engine = _get_engine(app)
    with engine.begin() as conn:
        _reap_expired(conn)


def _job(app, job_id):
    engine = _get_engine(app)
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM jobs WHERE id = :id"),
                            {"id": job_id}).mappings().first()


class TestReapUploadingWithResults:
    def test_uploading_with_results_goes_failed_not_requeued(self, client, app):
        """压测根因回归：回传中途死亡（meta 已入库）+ 租约过期 → failed 终态，
        不回队（回队 = 42 分钟整单重算）。"""
        job_id = _create_job(client)
        _uploading_with_results(client, job_id)
        _expire_lease(app, job_id)
        _reap(app)
        row = _job(app, job_id)
        assert row["status"] == "failed"
        assert row["error_class"] == "result_upload_error"
        assert "回传" in row["error_message"] and "不完整" in row["error_message"]
        assert row["finished_at"] is not None
        assert row["leased_by"] is None and row["lease_expires_at"] is None
        assert row["attempts"] == 1  # 不消耗重试次数（从未重新执行）

    def test_requeue_path_no_longer_touches_uploading_with_results(self, client, app):
        """再跑一次 reap（幂等）：failed 终态不被后续 reap 改动。"""
        job_id = _create_job(client)
        _uploading_with_results(client, job_id)
        _expire_lease(app, job_id)
        _reap(app)
        _reap(app)
        assert _job(app, job_id)["status"] == "failed"

    def test_uploading_without_results_row_still_requeues(self, client, app):
        """防御路径：uploading 但 results 行缺失（meta 事务未落成的理论态）→
        维持原语义回队（attempts<max），不误杀。"""
        job_id = _create_job(client)
        _lease(client)
        engine = _get_engine(app)
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET status='uploading' WHERE id = :id"),
                         {"id": job_id})
        _expire_lease(app, job_id)
        _reap(app)
        row = _job(app, job_id)
        assert row["status"] == "queued" and row["attempts"] == 1  # 回队不涨 attempts（claim 才涨）

    def test_running_with_results_row_still_requeues(self, client, app):
        """running + results 行（上一轮回传失败回队后重跑）→ 仍按租约语义回队，
        新 attempt 会覆盖 results；防重算只针对 uploading 态。"""
        job_id = _create_job(client)
        _uploading_with_results(client, job_id)
        engine = _get_engine(app)
        with engine.begin() as conn:
            conn.execute(text("UPDATE jobs SET status='running' WHERE id = :id"),
                         {"id": job_id})
        _expire_lease(app, job_id)
        _reap(app)
        row = _job(app, job_id)
        assert row["status"] == "queued" and row["attempts"] == 1  # 回队不涨 attempts（claim 才涨）

    def test_leased_without_results_still_requeues(self, client, app):
        """普通 leased 租约过期 → 回队（既有行为不变）。"""
        job_id = _create_job(client)
        _lease(client)
        _expire_lease(app, job_id)
        _reap(app)
        row = _job(app, job_id)
        assert row["status"] == "queued" and row["attempts"] == 1  # 回队不涨 attempts（claim 才涨）
