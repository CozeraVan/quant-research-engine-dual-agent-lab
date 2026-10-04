"""R3 切片1：worker 侧槽位状态跟踪 + 状态上报逻辑单测（假 client 注入）。"""

from __future__ import annotations

import threading
import time

import pytest

from quant_research_engine.worker.daemon import WorkerDaemon
from quant_research_engine.worker.slots import mem_total_mb


class _FakeClient:
    def __init__(self, jobs=None, fail_on_status=False, desired_config=None):
        self.jobs = list(jobs or [])
        self.fail_on_status = fail_on_status
        self.desired_config = desired_config
        self.status_reports: list[dict] = []
        self.worker_id = "test-w"
        self.base_url = "http://fake"

    def claim(self, wait_seconds=0, classes="any"):
        return self.jobs.pop(0) if self.jobs else None

    def heartbeat(self, job_id, progress=None, message=None):
        return {"cancel_requested": False}

    def report_result(self, job_id, payload):
        return {}

    def fail(self, job_id, error, error_class="engine_error"):
        return {}

    def report_status(self, payload):
        if self.fail_on_status:
            raise RuntimeError("云端不可达")
        self.status_reports.append(payload)
        return {"ok": True, "desired_config": self.desired_config}


def test_mem_total_mb_parse(tmp_path):
    f = tmp_path / "meminfo"
    f.write_text("MemTotal:       32768 kB\nMemAvailable:   10485760 kB\n")
    assert mem_total_mb(str(f)) == pytest.approx(32.0)


def test_mem_total_mb_missing_returns_none():
    assert mem_total_mb("/nonexistent/meminfo") is None


class TestBuildStatusPayload:
    def test_payload_shape(self):
        client = _FakeClient()
        daemon = WorkerDaemon(client)
        daemon._slot_set("light-1", "light", True, 42)
        daemon._slot_set("heavy-1", "heavy", False, None)
        payload = daemon.build_status_payload(
            {"light_slots": 1, "heavy_slots": 1}, mem_fn=lambda: 12345.0)
        assert payload["mem_available_mb"] == pytest.approx(12345.0)
        assert payload["mem_total_mb"] is None or payload["mem_total_mb"] > 0
        assert payload["limits"]["light_slots"] == 1
        by_name = {s["name"]: s for s in payload["slots"]}
        assert by_name["light-1"] == {"name": "light-1", "kind": "light",
                                      "busy": True, "job_id": 42}
        assert by_name["heavy-1"]["busy"] is False

    def test_inf_mem_degrades_to_none(self):
        # 非 Linux 平台 mem_available_mb 返回 inf：JSONB 落不了 Infinity，降级 NULL
        daemon = WorkerDaemon(_FakeClient())
        payload = daemon.build_status_payload({}, mem_fn=lambda: float("inf"))
        assert payload["mem_available_mb"] is None


class TestReportStatusOnce:
    def test_success(self):
        client = _FakeClient()
        daemon = WorkerDaemon(client)
        assert daemon.report_status_once({"light_slots": 1}, mem_fn=lambda: 100.0) is True
        assert len(client.status_reports) == 1

    def test_failure_logs_and_continues(self, capsys):
        daemon = WorkerDaemon(_FakeClient(fail_on_status=True))
        assert daemon.report_status_once({}, mem_fn=lambda: 100.0) is False
        assert "status 上报失败" in capsys.readouterr().out


class TestDesiredConfigComparison:
    """R3 切片2：status 响应回带的期望配置与当前生效 limits 比对记日志。"""

    LIMITS = {"light_slots": 2, "heavy_slots": 3,
              "light_min_avail_mb": 2000.0, "heavy_min_avail_mb": 6500.0}

    def test_mismatch_logs_once_per_version(self, capsys):
        desired = {"worker_id": "test-w", "light_slots": 1, "heavy_slots": 3,
                   "light_min_avail_mb": 2000, "heavy_min_avail_mb": 6500, "version": 5}
        daemon = WorkerDaemon(_FakeClient(desired_config=desired))
        assert daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0) is True
        out = capsys.readouterr().out
        assert "期望配置 v5 待应用" in out and "light_slots" in out
        # 同 version 第二次上报不再重复提示
        daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0)
        assert "期望配置" not in capsys.readouterr().out
        # 新版本再提示
        daemon.client.desired_config = {**desired, "version": 6, "light_slots": 2}
        daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0)
        assert "期望配置 v6" in capsys.readouterr().out

    def test_matching_config_no_log_then_transition(self, capsys):
        desired = {"worker_id": "test-w", "light_slots": 2, "heavy_slots": 3,
                   "light_min_avail_mb": 2000, "heavy_min_avail_mb": 6500, "version": 5}
        daemon = WorkerDaemon(_FakeClient(desired_config=desired))
        daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0)
        assert "期望配置" not in capsys.readouterr().out

    def test_applied_transition_logs_back_to_consistent(self, capsys):
        desired = {"worker_id": "test-w", "light_slots": 1, "heavy_slots": 3,
                   "light_min_avail_mb": 2000, "heavy_min_avail_mb": 6500, "version": 5}
        daemon = WorkerDaemon(_FakeClient(desired_config=desired))
        daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0)
        assert "待应用" in capsys.readouterr().out
        # 管理员应用后 worker 重启，limits 变为期望值 → 记录「已生效」
        daemon.report_status_once({**self.LIMITS, "light_slots": 1}, mem_fn=lambda: 100.0)
        assert "期望配置 v5 已生效" in capsys.readouterr().out

    def test_no_desired_config_silent(self, capsys):
        daemon = WorkerDaemon(_FakeClient(desired_config=None))
        daemon.report_status_once(self.LIMITS, mem_fn=lambda: 100.0)
        assert "期望配置" not in capsys.readouterr().out


class TestSlotTracking:
    def test_legacy_run_once_marks_main_slot_busy(self):
        job = {"id": 7, "kind": "full", "params_json": {}}
        client = _FakeClient(jobs=[job])
        daemon = WorkerDaemon(client, poll_seconds=0.01, heartbeat_seconds=0.05)
        entered = threading.Event()
        release = threading.Event()

        def blocking_runner(j):
            entered.set()
            release.wait(timeout=10)
            return {"summary": {}, "chart_data": None, "files": []}

        daemon.runner = blocking_runner
        t = threading.Thread(target=daemon.run_once, daemon=True)
        t.start()
        assert entered.wait(timeout=5)
        snap = {s["name"]: s for s in daemon.slots_snapshot()}
        assert snap["main"]["busy"] is True and snap["main"]["job_id"] == 7
        assert snap["main"]["kind"] == "light"
        release.set()
        t.join(timeout=10)
        snap = {s["name"]: s for s in daemon.slots_snapshot()}
        assert snap["main"]["busy"] is False and snap["main"]["job_id"] is None

    def test_slot_loop_marks_slot_busy(self, monkeypatch):
        monkeypatch.setattr(
            "quant_research_engine.worker.slots.mem_total_mb", lambda *a, **k: 1024.0)
        job = {"id": 9, "kind": "full", "params_json": {}}
        client = _FakeClient(jobs=[job])
        daemon = WorkerDaemon(client, poll_seconds=0.02, heartbeat_seconds=0.05,
                              sleep=lambda s: None)
        entered = threading.Event()
        release = threading.Event()

        def fake_subprocess(j, is_canceled=None):
            entered.set()
            release.wait(timeout=10)
            return {"summary": {}, "chart_data": None, "files": []}

        monkeypatch.setattr(
            "quant_research_engine.worker.slots.execute_job_subprocess", fake_subprocess)
        t = threading.Thread(target=daemon._slot_loop,
                             args=("light-1", "light", 0.0, lambda: 99999.0), daemon=True)
        t.start()
        assert entered.wait(timeout=5)
        snap = {s["name"]: s for s in daemon.slots_snapshot()}
        assert snap["light-1"] == {"name": "light-1", "kind": "light",
                                   "busy": True, "job_id": 9}
        release.set()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            snap = {s["name"]: s for s in daemon.slots_snapshot()}
            if not snap["light-1"]["busy"]:
                break
            time.sleep(0.02)
        daemon.stop()
        t.join(timeout=5)
        assert snap["light-1"]["busy"] is False

    def test_status_loop_reports_until_stopped(self):
        client = _FakeClient()
        daemon = WorkerDaemon(client, status_seconds=0.05)
        t = daemon._start_status_thread({"light_slots": 2}, lambda: 500.0)
        deadline = time.monotonic() + 5
        while len(client.status_reports) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        daemon.stop()
        t.join(timeout=5)
        assert len(client.status_reports) >= 2
        assert client.status_reports[0]["limits"] == {"light_slots": 2}
