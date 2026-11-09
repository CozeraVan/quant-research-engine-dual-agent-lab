"""P0-9 §8.5 结果回传截断显式标记回归（CR-2026-11-03，压测实测立项）。

根因：`collect_result_files` 超 20 MiB 预算的文件直接 `continue` 跳过，不写任何
标记；item1 产出 1.1 GB / 5208 文件只回传 333 个 / 20 MiB，`symbol_details` 为
null（report_result 根本没转发它），前端无从判断结果不完整。

修复：worker 产出 `result_files` 元数据（truncated/included/skipped/预算）与
`symbol_details` 一并回传；服务端落 `results.result_files` JSONB 列（懒补列，
老库缺列降级），`/api/results/<id>/summary` 增量返回。旧 worker 不带这些字段
→ 服务端存 NULL，老结果/老库读取为 null，兼容。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import uuid
from pathlib import Path

import pytest

from quant_research_engine.gui.saas import create_saas_app
from quant_research_engine.worker import runner as runner_mod

WORKER_TOKEN = "test-worker-token"
WORKER_HEADERS = {"X-Worker-Token": WORKER_TOKEN}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_trunc_test_{uuid.uuid4().hex[:12]}"
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


def _make_record(tmp_path: Path, files: dict[str, bytes]) -> dict:
    """files: 相对名 -> 内容；写进 tmp_path 并登记为 artifacts。"""
    artifacts = {}
    for rel, blob in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(blob)
        artifacts[rel] = str(p)
    return {"run_id": "r1", "output_dir": str(tmp_path), "artifacts": artifacts}


# ---------------------------------------------------------------------------
# worker 侧：collect_result_files_with_meta
# ---------------------------------------------------------------------------

class TestCollectResultFilesMeta:
    def test_under_budget_not_truncated(self, tmp_path):
        record = _make_record(tmp_path, {
            "risk_report.json": b"r" * 100,
            "000001.SZ/trades.csv": b"t" * 50,
        })
        files, meta = runner_mod.collect_result_files_with_meta(record, max_total_bytes=1000)
        assert len(files) == 2
        assert meta["truncated"] is False
        assert meta["skipped_count"] == 0
        assert meta["skipped_bytes"] == 0
        assert meta["included_count"] == 2
        assert meta["included_bytes"] == 150
        assert meta["max_total_bytes"] == 1000
        assert meta["total_local_bytes"] == 150

    def test_over_budget_marks_truncated_with_counts(self, tmp_path):
        """压测根因回归：超预算文件必须留下 truncated 标记与跳过计数，不再静默。"""
        record = _make_record(tmp_path, {
            "risk_report.json": b"r" * 100,
            "a.csv": b"a" * 400,
            "b.csv": b"b" * 400,
            "c.csv": b"c" * 400,
        })
        files, meta = runner_mod.collect_result_files_with_meta(record, max_total_bytes=600)
        names = [f["name"] for f in files]
        # 优先级：risk_report.json 先行，其余按名典序；预算内尽量多带
        assert names[0] == "risk_report.json"
        assert meta["truncated"] is True
        assert meta["included_count"] == len(files)
        assert meta["skipped_count"] >= 1
        assert meta["included_bytes"] <= 600
        assert meta["skipped_bytes"] == meta["total_local_bytes"] - meta["included_bytes"]
        assert meta["skipped_files"]  # 非空名单（可观测）

    def test_skipped_files_list_capped_at_50(self, tmp_path):
        files = {f"f{i:03d}.csv": b"x" for i in range(120)}
        record = _make_record(tmp_path, files)
        _, meta = runner_mod.collect_result_files_with_meta(record, max_total_bytes=10)
        assert meta["truncated"] is True
        assert meta["included_count"] == 10  # 预算内尽量带
        assert meta["skipped_count"] == 110
        assert len(meta["skipped_files"]) == 50  # 名单封顶，元数据不爆
        assert meta["skipped_count"] > len(meta["skipped_files"])

    def test_missing_local_file_counted_not_truncated(self, tmp_path):
        """清单里有路径但文件不存在：记 missing_count（可观测），不算预算截断。"""
        record = {
            "run_id": "r1", "output_dir": str(tmp_path),
            "artifacts": {"ghost.csv": str(tmp_path / "ghost.csv"),
                          "real.csv": str(_write(tmp_path / "real.csv", b"x" * 10))},
        }
        files, meta = runner_mod.collect_result_files_with_meta(record, max_total_bytes=1000)
        assert [f["name"] for f in files] == ["real.csv"]
        assert meta["missing_count"] == 1
        assert meta["truncated"] is False

    def test_legacy_helper_still_returns_plain_list(self, tmp_path):
        """兼容：collect_result_files 原签名/返回形状不变（list of file entries）。"""
        record = _make_record(tmp_path, {"a.csv": b"x", "b.csv": b"y"})
        files = runner_mod.collect_result_files(record, max_total_bytes=1000)
        assert isinstance(files, list)
        assert sorted(f["name"] for f in files) == ["a.csv", "b.csv"]
        assert all({"name", "size", "sha256", "path"} <= set(f) for f in files)

    def test_symbol_detail_payload_carries_meta(self, tmp_path, monkeypatch):
        """symbol_detail 按需任务也要带 result_files/symbol_details 元数据。"""
        import quant_research_engine.gui.lab_result as lab_result

        monkeypatch.setattr(lab_result, "_symbol_trade_stats",
                            lambda record: {"000001.SZ": {"total_pnl": 1.0}})
        monkeypatch.setattr(lab_result, "build_lab_symbol_detail",
                            lambda *a, **kw: {"ok": True, "ts_code": "000001.SZ"})
        run_dir = tmp_path / "runs" / "run_x"
        (run_dir / "artifacts").mkdir(parents=True)
        blob = b"gzip-bytes"
        detail_dir = run_dir / "artifacts" / "_symbol_details"
        detail_dir.mkdir(parents=True)
        (detail_dir / "000001.SZ.json.gz").write_bytes(blob)
        record = {
            "run_id": "run_x", "output_dir": str(run_dir / "artifacts"),
            "artifacts": {"_symbol_details/000001.SZ.json.gz":
                          str(detail_dir / "000001.SZ.json.gz")},
        }
        (run_dir / "status.json").write_text(json.dumps(record), encoding="utf-8")

        import quant_research_engine.gui.engine as gui_engine
        orig_runs = gui_engine.RUNS_DIR
        gui_engine.RUNS_DIR = tmp_path / "runs"
        try:
            payload = runner_mod._execute_symbol_detail({
                "id": 5, "kind": "symbol_detail",
                "params": {"parent_job_id": 4, "ts_code": "000001.SZ", "run_id": "run_x"},
            })
        finally:
            gui_engine.RUNS_DIR = orig_runs
        assert payload["symbol_details"]["count"] == 1
        assert payload["result_files"]["truncated"] is False
        assert payload["result_files"]["included_count"] == 1
        assert len(payload["files"]) == 1


# ---------------------------------------------------------------------------
# client 转发
# ---------------------------------------------------------------------------

class TestReportResultForwardsMeta:
    def test_symbol_details_and_result_files_forwarded(self):
        from quant_research_engine.worker.client import CloudClient

        captured = {}

        def request_fn(method, path, payload):
            captured.update(payload or {})
            return 200, {"upload_token": "tok"}

        client = CloudClient("http://cloud.local", "t", worker_id="w", request_fn=request_fn)
        client.report_result(7, {
            "summary": {"a": 1}, "chart_data": {}, "data_until": "2026-03-01",
            "files": [{"name": "a.csv", "size": 1, "sha256": "s", "path": "/x"}],
            "symbol_details": {"count": 175, "truncated": True},
            "result_files": {"truncated": True, "skipped_count": 5000},
        })
        assert captured["symbol_details"] == {"count": 175, "truncated": True}
        assert captured["result_files"] == {"truncated": True, "skipped_count": 5000}
        # files 仍剥掉 path（既有契约）
        assert captured["files"] == [{"name": "a.csv", "size": 1, "sha256": "s"}]

    def test_old_payload_without_new_keys_still_works(self):
        from quant_research_engine.worker.client import CloudClient

        captured = {}

        def request_fn(method, path, payload):
            captured.update(payload or {})
            return 200, {"upload_token": "tok"}

        client = CloudClient("http://cloud.local", "t", worker_id="w", request_fn=request_fn)
        client.report_result(7, {"summary": {}, "chart_data": {}, "data_until": None,
                                 "files": []})
        assert "symbol_details" not in captured
        assert "result_files" not in captured


# ---------------------------------------------------------------------------
# 服务端：落库 + summary 暴露
# ---------------------------------------------------------------------------

def _write(path: Path, blob: bytes) -> Path:
    path.write_bytes(blob)
    return path


class TestServerResultFilesMeta:
    def _lease_and_meta(self, client, job_id, extra=None):
        client.post("/api/worker/jobs/claim", json={"worker_id": "w1"},
                    headers=WORKER_HEADERS)
        body = {"worker_id": "w1", "summary": {"total_return": 0.1},
                "chart_data": {}, "data_until": "2026-03-01", "files": []}
        body.update(extra or {})
        return client.post(f"/api/worker/jobs/{job_id}/result/meta", json=body,
                           headers=WORKER_HEADERS)

    def _create(self, client):
        resp = client.post("/api/saas/jobs", json={
            "yaml": "experiment:\n  name: t\ndata:\n  market_fields: [close]\nsignal:\n  entry: close > 0\n",
            "kind": "full", "params": {"start": "2026-01-01", "end": "2026-03-01"},
        }, headers={"X-User-Id": "1"})
        return resp.get_json()["job_id"]

    def test_meta_stores_result_files_and_summary_exposes_it(self, client):
        job_id = self._create(client)
        meta_payload = {
            "result_files": {"truncated": True, "included_count": 245,
                             "included_bytes": 20971504, "max_total_bytes": 20971520,
                             "skipped_count": 25781, "skipped_bytes": 1614485003,
                             "total_local_bytes": 1635200507,
                             "skipped_files": ["a.csv"], "missing_count": 0},
            "symbol_details": {"count": 175, "bytes": 16500000, "truncated": True},
        }
        resp = self._lease_and_meta(client, job_id, meta_payload)
        assert resp.status_code == 200 and resp.get_json()["status"] == "completed"
        summary = client.get(f"/api/results/{job_id}/summary",
                             headers={"X-User-Id": "1"}).get_json()
        assert summary["result_files"]["truncated"] is True
        assert summary["result_files"]["skipped_count"] == 25781
        assert summary["result_files"]["symbol_details"]["count"] == 175

    def test_legacy_meta_without_new_fields_returns_null(self, client):
        """旧 worker（不带新字段）→ result_files 为 null，前端不显示，兼容。"""
        job_id = self._create(client)
        resp = self._lease_and_meta(client, job_id)
        assert resp.status_code == 200
        summary = client.get(f"/api/results/{job_id}/summary",
                             headers={"X-User-Id": "1"}).get_json()
        assert summary["result_files"] is None

    def test_schema_file_declares_result_files_column(self):
        schema = Path("deploy/saas/cloud_schema.sql").read_text(encoding="utf-8")
        assert "result_files" in schema
