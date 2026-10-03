"""R2 多租户弹性调度 切片2：worker 槽位内存闸门 + 子进程隔离执行。"""

from __future__ import annotations

import threading
import time

import pytest

from quant_research_engine.worker.daemon import WorkerDaemon
from quant_research_engine.worker.slots import execute_job_subprocess, mem_available_mb


# --- 子进程用顶层 runner（fork 模式可继承；放模块级避免闭包引用问题） ---

def _runner_ok(job):
    return {"summary": {"job": job["id"]}, "chart_data": None, "files": []}


def _runner_raise(job):
    raise ValueError("策略编译失败：YAML 不合法")


def _runner_crash(job):
    import os
    os._exit(137)  # 模拟 OOM 被杀：不放结果直接死


def _runner_sleep(job):
    time.sleep(60)
    return {"summary": {}, "chart_data": None, "files": []}


class TestMemGate:
    def test_parse_meminfo(self, tmp_path):
        f = tmp_path / "meminfo"
        f.write_text("MemTotal:       32768 kB\nMemAvailable:   10485760 kB\nBuffers: 1 kB\n")
        assert mem_available_mb(str(f)) == pytest.approx(10240.0)

    def test_missing_file_returns_inf(self):
        assert mem_available_mb("/nonexistent/meminfo") == float("inf")


class TestSubprocessExecution:
    def test_success(self):
        payload = execute_job_subprocess({"id": 7}, runner=_runner_ok)
        assert payload["summary"] == {"job": 7}

    def test_runner_exception_propagates(self):
        with pytest.raises(RuntimeError, match="策略编译失败"):
            execute_job_subprocess({"id": 1}, runner=_runner_raise)

    def test_crash_reports_exitcode(self):
        with pytest.raises(RuntimeError, match="exitcode=137"):
            execute_job_subprocess({"id": 1}, runner=_runner_crash)

    def test_cancel_terminates_child(self):
        t0 = time.monotonic()
        with pytest.raises(RuntimeError, match="用户取消"):
            execute_job_subprocess({"id": 1}, runner=_runner_sleep,
                                   is_canceled=lambda: True, poll_seconds=0.2)
        assert time.monotonic() - t0 < 10  # 被强杀而不是跑满 60s


class _FakeClient:
    """槽位测试用假 CloudClient：记录 claim 的 classes，返回预制任务。"""

    def __init__(self, jobs_by_classes):
        self.jobs_by_classes = jobs_by_classes
        self.claim_calls: list[str] = []
        self.worker_id = "test-w"
        self.base_url = "http://fake"

    def claim(self, wait_seconds=0, classes="any"):
        self.claim_calls.append(classes)
        q = self.jobs_by_classes.get(classes) or []
        return q.pop(0) if q else None

    def heartbeat(self, job_id, progress=None, message=None):
        return {"cancel_requested": False}

    def report_result(self, job_id, payload):
        return {}

    def fail(self, job_id, error, error_class="engine_error"):
        return {}


class TestSlotScheduling:
    def test_light_slot_claims_light_only_and_memory_gate(self):
        client = _FakeClient({"light": [], "any": []})
        daemon = WorkerDaemon(client, poll_seconds=0.05, sleep=lambda s: None)
        gate = {"avail": 100.0}  # 低于 200MB 闸门 → 不 claim

        def mem_fn():
            return gate["avail"]

        t = threading.Thread(target=daemon._slot_loop,
                             args=("light-1", "light", 200.0, mem_fn), daemon=True)
        t.start()
        time.sleep(0.2)
        assert client.claim_calls == []  # 内存不足，未发起 claim
        gate["avail"] = 10000.0
        time.sleep(0.2)
        assert client.claim_calls and set(client.claim_calls) == {"light"}
        daemon.stop()
        t.join(timeout=5)
        assert not t.is_alive()

    def test_run_slots_forever_starts_all_slots(self):
        client = _FakeClient({"light": [], "any": []})
        daemon = WorkerDaemon(client, poll_seconds=0.05, sleep=lambda s: None)
        t = threading.Thread(
            target=daemon.run_slots_forever,
            args=(2, 3, 100.0, 100.0),
            kwargs={"mem_fn": lambda: 99999.0},
            daemon=True,
        )
        t.start()
        time.sleep(0.3)
        light_claims = [c for c in client.claim_calls if c == "light"]
        any_claims = [c for c in client.claim_calls if c == "any"]
        assert light_claims and any_claims
        daemon.stop()
        t.join(timeout=10)
        assert not t.is_alive()
