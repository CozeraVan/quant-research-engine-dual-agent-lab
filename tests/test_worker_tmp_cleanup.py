"""P0-9 §8.7 worker 沙箱目录安全清理 + §8.11 进度真实更新回归。

§8.7：`/tmp/qre-worker-job<id>-*` job 结束后不清理（压测实测 3 项留下 3.63 GB）。
修复：daemon 自建沙箱目录（mkdtemp，前缀 qre-worker-job<id>-）并向下透传，
**只在安全终态**（completed/failed/canceled/expired）且**目录归属匹配**
（系统临时目录下 + 名字精确前缀匹配本 job）时清理；回队/终态未知/归属不匹配
一律保留（可能是唯一完整副本）。压测遗留目录不在清理范围（只删本进程自建的）。

§8.11：batch 全量 progress/progress_message 全程不更新（恒 0/None）。修复：
runner 守护线程按「逐股产物目录数 / 预期股票数」写 progress.json（真实百分比，
90% 封顶留给回传段；无逐股中间产物的模式只更新文案不虚构百分比）；daemon
心跳携带 progress/message（单调守卫），执行完 95「产物回传中」、分片上传期间
95→99 ramp、成功后 100。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from quant_research_engine.worker import daemon as worker_daemon
from quant_research_engine.worker import runner as runner_mod
from quant_research_engine.worker.daemon import WorkerDaemon
from quant_research_engine.worker.client import CloudClient, CloudError


class _FakeClient:
    """记录 fail/heartbeat/report_result/upload_files 调用；可编排返回与异常。"""

    def __init__(self, *, upload_exc=None, fail_exc=None, meta=None):
        self.worker_id = "w"
        self.base_url = "http://127.0.0.1:1"
        self.heartbeats: list[dict] = []
        self.fail_calls: list[dict] = []
        self.upload_calls: list[dict] = []
        self._upload_exc = upload_exc
        self._fail_exc = fail_exc
        self._meta = meta or {"upload_token": "tok"}

    def report_result(self, job_id, payload):
        return self._meta

    def upload_files(self, job_id, upload_token, blobs, **kwargs):
        self.upload_calls.append({"job_id": job_id, "files": sorted(blobs)})
        if self._upload_exc is not None:
            raise self._upload_exc
        # 真实客户端每批回调 on_batch（daemon 据此发 95→99 进度心跳）；假 client
        # 按“整批一次”模拟，保证进度ramp可观测。
        on_batch = kwargs.get("on_batch")
        if on_batch is not None:
            on_batch(blobs, {"ok": True, "status": "completed",
                             "uploaded": sorted(blobs)})
        return {"ok": True, "status": "completed", "uploaded": sorted(blobs)}

    def heartbeat(self, job_id, progress=None, message=None):
        self.heartbeats.append({"job_id": job_id, "progress": progress, "message": message})
        return {"ok": True, "cancel_requested": False}

    def fail(self, job_id, error, error_class="engine_error"):
        self.fail_calls.append({"job_id": job_id, "error": error, "error_class": error_class})
        if self._fail_exc is not None:
            raise self._fail_exc
        return {"ok": True, "job_id": job_id, "status": "failed"}


def _daemon(client) -> WorkerDaemon:
    daemon = WorkerDaemon.__new__(WorkerDaemon)
    daemon.client = client
    # __new__ 绕过 __init__：补齐 _run_job 用到的心跳属性
    daemon.heartbeat_seconds = 0.05
    daemon.max_heartbeat_failures = 3
    return daemon


@pytest.fixture()
def temp_root(tmp_path, monkeypatch):
    """把系统临时目录指到 tmp_path（沙箱目录创建与归属判定都走 gettempdir）。"""
    root = tmp_path / "tmproot"
    root.mkdir()
    monkeypatch.setattr(worker_daemon.tempfile, "gettempdir", lambda: str(root))
    return root


# ---------------------------------------------------------------------------
# §8.7 清理
# ---------------------------------------------------------------------------

class TestSandboxCleanup:
    """主 Agent Required Fix（2026-11-03）：清理前提从「安全终态」收紧为
    「completed **且** 云端完整副本已确认」——上传失败（failed）、上传开关关闭
    （blob 从未上云）、manifest 截断（云端缺文件）时本地沙箱可能是唯一完整副本
    （压测归档保护），一律保留。"""

    def _job(self):
        return {"id": 42, "kind": "full", "params": {}}

    def _payload(self, work_base, *, truncated=False, with_meta=True):
        (Path(work_base) / "artifacts").mkdir(parents=True, exist_ok=True)
        (Path(work_base) / "a.csv").write_bytes(b"x")
        payload = {
            "summary": {}, "chart_data": {}, "data_until": None,
            "files": [{"name": "a.csv", "path": str(Path(work_base) / "a.csv"),
                       "size": 1, "sha256": "x"}],
        }
        if with_meta:
            payload["result_files"] = {
                "truncated": truncated, "included_count": 1, "included_bytes": 1,
                "skipped_count": 3 if truncated else 0, "missing_count": 0,
            }
        return payload

    def test_sandbox_removed_only_after_confirmed_complete_upload(self, temp_root, monkeypatch):
        """completed + 上传开关开 + 全部批次确认 + 无截断 → 清理。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base)

        daemon = _daemon(_FakeClient())
        daemon._run_job(self._job(), runner=runner)
        assert list(temp_root.iterdir()) == [], "云端完整副本确认后沙箱应已清理"

    def test_upload_disabled_keeps_sandbox(self, temp_root, monkeypatch):
        """QRE_WORKER_UPLOAD_FILES!=1：meta-only completed，blob 从未上云——
        本地是唯一完整副本，不许删（主 Agent Required Fix 同类路径）。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: False)

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base)

        client = _FakeClient()
        daemon = _daemon(client)
        daemon._run_job(self._job(), runner=runner)
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_upload_failure_non_retryable_keeps_sandbox(self, temp_root, monkeypatch):
        """上传 413（不可重试 → failed）：本地完整产物是唯一副本，保留。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        client = _FakeClient(upload_exc=CloudError("HTTP 413", 413))

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base)

        daemon = _daemon(client)
        daemon._run_job(self._job(), runner=runner)
        assert client.fail_calls[0]["error_class"] == "result_upload_http_413"
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_sandbox_kept_when_job_requeued(self, temp_root, monkeypatch):
        """回传失败可重试 → job 回队（非终态）→ 沙箱保留（可能是唯一完整副本）。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        client = _FakeClient(upload_exc=CloudError("传输失败", None))
        # fail 回队语义
        client.fail = lambda job_id, error, error_class="engine_error": (
            client.fail_calls.append({"job_id": job_id, "error": error,
                                      "error_class": error_class}),
            {"ok": True, "job_id": job_id, "status": "queued"})[1]

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base)

        daemon = _daemon(client)
        daemon._run_job(self._job(), runner=runner)
        assert client.fail_calls[0]["error_class"] == "result_upload_error"
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_sandbox_kept_when_final_state_unknown(self, temp_root, monkeypatch):
        """fail 上报也失败 → 终态未知 → 绝不删本地产物。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        client = _FakeClient(upload_exc=CloudError("云端 5xx", 500),
                             fail_exc=CloudError("连不上", None))

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base)

        daemon = _daemon(client)
        daemon._run_job(self._job(), runner=runner)
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_runner_failure_keeps_sandbox(self, temp_root):
        """runner 抛异常 → failed：计算产物可能只存在于本地，保守保留。"""

        def runner(job, _ev=None, work_base=None):
            (Path(work_base) / "artifacts").mkdir(parents=True, exist_ok=True)
            raise RuntimeError("engine boom")

        client = _FakeClient()
        daemon = _daemon(client)
        daemon._run_job(self._job(), runner=runner)
        assert client.fail_calls
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_truncated_upload_keeps_sandbox(self, temp_root, monkeypatch):
        """§8.5 交互：completed 但 manifest 被 20 MiB 预算截断——云端只持有部分
        产物，本地沙箱是唯一完整副本，不许删。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base, truncated=True)

        daemon = _daemon(_FakeClient())
        daemon._run_job(self._job(), runner=runner)
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_missing_result_files_meta_keeps_sandbox(self, temp_root, monkeypatch):
        """payload 无 result_files 完整性元数据（旧 runner）：保守按不完整处理。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)

        def runner(job, _ev=None, work_base=None):
            return self._payload(work_base, with_meta=False)

        daemon = _daemon(_FakeClient())
        daemon._run_job(self._job(), runner=runner)
        kept = [p.name for p in temp_root.iterdir()]
        assert len(kept) == 1 and kept[0].startswith("qre-worker-job42-")

    def test_ownership_guard_rejects_foreign_name(self, temp_root):
        """归属判定：前缀不匹配本 job（别的 job / 压测遗留）→ 不删。"""
        foreign = temp_root / "qre-worker-job7-xeosz55e"  # 压测遗留命名
        foreign.mkdir()
        (foreign / "keep.bin").write_bytes(b"x")
        daemon = _daemon(_FakeClient())
        daemon._cleanup_work_base(42, foreign, "completed", cloud_complete=True)
        assert foreign.is_dir() and (foreign / "keep.bin").is_file()

    def test_ownership_guard_rejects_outside_tempdir(self, tmp_path):
        """归属判定：临时目录之外的路径一律不删（防拼路径事故）。"""
        outside = tmp_path / "qre-worker-job42-elsewhere"
        outside.mkdir()
        (outside / "keep.bin").write_bytes(b"x")
        daemon = _daemon(_FakeClient())
        daemon._cleanup_work_base(42, outside, "completed", cloud_complete=True)
        assert outside.is_dir()

    def test_ownership_guard_rejects_unconfirmed_cloud_copy(self, temp_root):
        """completed 但云端副本未确认 → 不删（唯一删除前提）。"""
        own = temp_root / "qre-worker-job42-abc"
        own.mkdir()
        daemon = _daemon(_FakeClient())
        daemon._cleanup_work_base(42, own, "completed", cloud_complete=False)
        assert own.is_dir()

    def test_ownership_guard_rejects_non_completed_status(self, temp_root):
        """failed/queued/unknown/canceled/expired 一律不删（保守保留）。"""
        own = temp_root / "qre-worker-job42-abc"
        own.mkdir()
        daemon = _daemon(_FakeClient())
        for status in ("failed", "queued", "unknown", "canceled", "expired"):
            daemon._cleanup_work_base(42, own, status, cloud_complete=True)
            assert own.is_dir(), status


# ---------------------------------------------------------------------------
# §8.11 progress
# ---------------------------------------------------------------------------

class TestProgressSnapshot:
    def test_batch_percent_tracks_symbol_outputs(self, tmp_path):
        out = tmp_path / "artifacts"
        out.mkdir()
        assert runner_mod._progress_snapshot(out, 4, "batch")[0] == 5
        for i in range(2):
            d = out / f"00000{i}.SZ"
            d.mkdir()
            (d / "summary.csv").write_text("x")
        pct, msg, _done = runner_mod._progress_snapshot(out, 4, "batch")
        assert pct == 5 + round(85 * 2 / 4)
        assert msg == "回测中 2/4 只"

    def test_batch_percent_capped_at_90(self, tmp_path):
        out = tmp_path / "artifacts"
        out.mkdir()
        for i in range(10):
            d = out / f"s{i}"
            d.mkdir()
            (d / "summary.csv").write_text("x")
        pct, _msg, _done = runner_mod._progress_snapshot(out, 10, "batch")
        assert pct == 90  # 90% 以上留给回传段（daemon 95→100）

    def test_non_batch_mode_reports_phase_only(self, tmp_path):
        out = tmp_path / "artifacts"
        out.mkdir()
        pct, msg, _done = runner_mod._progress_snapshot(out, 100, "shared")
        assert pct is None  # 无逐股中间产物：不虚构百分比
        assert "shared" in msg

    def test_symbol_details_dir_not_counted(self, tmp_path):
        out = tmp_path / "artifacts"
        (out / "_symbol_details").mkdir(parents=True)
        (out / "_symbol_details" / "000001.SZ.json.gz").write_bytes(b"x")
        assert runner_mod._progress_snapshot(out, 10, "batch")[0] == 5


class TestDaemonProgressHeartbeat:
    def _job(self):
        return {"id": 42, "kind": "full", "params": {}}

    def test_heartbeat_carries_progress_and_is_monotonic(self, temp_root, monkeypatch):
        """心跳携带 progress.json 的真实进度；watcher 回退时单调守卫生效；
        完成后最终心跳为 100。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: False)

        def runner(job, _ev=None, work_base=None):
            base = Path(work_base)
            (base / "artifacts").mkdir(parents=True)
            # 模拟批量流式：逐股产物陆续出现 + 一次故意回退
            for pct in (20, 60, 60, 30, 90):
                (base / "progress.json").write_text(json.dumps(
                    {"percent": pct, "message": f"回测中 {pct}", "total": 100}),
                    encoding="utf-8")
                time.sleep(0.06)
            return {"summary": {}, "chart_data": {}, "files": [], "data_until": None}

        client = _FakeClient()
        daemon = WorkerDaemon(client, heartbeat_seconds=0.05)
        daemon._run_job(self._job(), runner=runner)
        sent = [h["progress"] for h in client.heartbeats if h["progress"] is not None]
        assert sent, "心跳必须携带进度"
        assert sent == sorted(sent), f"进度不得回退：{sent}"
        # Required Fix（job 212）：终态 100 由服务端在 completed 事务落定，
        # worker 不再发 completed 后心跳（会被拒）；最后一条是回传段 95。
        assert sent[-1] == 95
        assert 100 not in sent
        assert 30 not in sent  # 回退值被单调守卫抬平

    def test_upload_batches_send_progress_heartbeats(self, temp_root, monkeypatch):
        """分片上传期间每批心跳（95→99 ramp），既报进度也续租。"""
        monkeypatch.setattr(worker_daemon, "_upload_files_enabled", lambda: True)
        blobs = {f"f{i}.csv": b"x" for i in range(250)}

        def runner(job, _ev=None, work_base=None):
            (Path(work_base) / "artifacts").mkdir(parents=True, exist_ok=True)
            return {"summary": {}, "chart_data": {}, "data_until": None,
                    "files": [{"name": n, "path": str(Path(work_base) / n),
                               "size": 1, "sha256": "x"} for n in blobs]}

        client = _FakeClient()
        daemon = _daemon(client)
        monkeypatch.setattr(worker_daemon.Path, "read_bytes", lambda self: b"x")
        daemon._report_results(42, runner(self._job(), work_base=temp_root / "wb"))
        upload_progress = [h["progress"] for h in client.heartbeats]
        assert upload_progress, "上传期间必须有心跳"
        assert upload_progress == sorted(upload_progress)
        # Required Fix（job 212）：终态 100 由服务端落定，worker 上传段只到 99，
        # 不发 completed 后心跳（会被拒）。
        assert upload_progress[-1] == 99
        assert 100 not in upload_progress
        assert any("回传" in (h["message"] or "") for h in client.heartbeats)
