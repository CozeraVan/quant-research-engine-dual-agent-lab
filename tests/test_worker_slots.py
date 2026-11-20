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
    def test_heavy_slot_waits_for_daily_refresh(self, tmp_path, monkeypatch):
        from quant_research_engine.scheduling import refresh_lock
        lock_path = tmp_path / "schedule.lock"
        monkeypatch.setenv("QRE_SCHEDULING_LOCK_PATH", str(lock_path))
        client = _FakeClient({"any": []})
        daemon = WorkerDaemon(client, poll_seconds=0.02,
                              sleep=lambda s: time.sleep(min(s, 0.02)))
        with refresh_lock(lock_path, exclusive=True):
            thread = threading.Thread(target=daemon._slot_loop,
                                      args=("heavy-1", "any", 0.0, lambda: 99999.0), daemon=True)
            thread.start()
            time.sleep(0.15)
            assert client.claim_calls == []
        deadline = time.monotonic() + 3
        while not client.claim_calls and time.monotonic() < deadline:
            time.sleep(0.02)
        assert client.claim_calls
        daemon.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()

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


def _runner_raises_memory_error(job):
    raise MemoryError("Unable to allocate (模拟超限)")


class TestChildMemoryLimit:
    def test_memory_error_raises_readable_quota_error(self, monkeypatch):
        # 子进程 MemoryError（RLIMIT_AS 超配额的真实表现）必须转成可读
        # 「任务超出资源配额」而不是裸 exitcode/-9。
        # 注意：不在 fork 子进程里真实分配 GB 级内存——pytest 父进程带线程，
        # fork 子进程在极限内存下 exit/join 队列有挂死风险（2026-10-18 全量套件实测）。
        monkeypatch.setenv("QRE_WORKER_CHILD_MEM_GB", "1")
        with pytest.raises(RuntimeError, match="任务超出资源配额"):
            execute_job_subprocess({"id": 1}, runner=_runner_raises_memory_error)

    def test_apply_limit_sets_rlimit_as(self, monkeypatch):
        import resource

        from quant_research_engine.worker.slots import _apply_child_memory_limit

        monkeypatch.setenv("QRE_WORKER_CHILD_MEM_GB", "0")  # 0 = 不限制
        soft_before, hard_before = resource.getrlimit(resource.RLIMIT_AS)
        _apply_child_memory_limit()
        assert resource.getrlimit(resource.RLIMIT_AS) == (soft_before, hard_before)

    def test_under_limit_unaffected(self, monkeypatch):
        monkeypatch.setenv("QRE_WORKER_CHILD_MEM_GB", "8")
        payload = execute_job_subprocess({"id": 2}, runner=_runner_ok)
        assert payload["summary"] == {"job": 2}


class TestChildMemLimitDefault:
    """P0-10：子进程默认上限 14→12GB，与 R-MEM-001 规则 2（≤物理 50%）对齐。
    超限任务允许可读失败，禁止以提高上限绕过（尾段分块修复见 CF 后续）。"""

    def test_default_is_12_gb(self):
        from quant_research_engine.worker.slots import DEFAULT_CHILD_MEM_LIMIT_GB

        assert DEFAULT_CHILD_MEM_LIMIT_GB == 12.0

    def test_memory_error_message_mentions_12gb_default(self, monkeypatch):
        # env 未显式设置时（delenv 后）MemoryError 文案应报默认 12GB
        monkeypatch.delenv("QRE_WORKER_CHILD_MEM_GB", raising=False)
        with pytest.raises(RuntimeError, match="任务超出资源配额"):
            execute_job_subprocess({"id": 3}, runner=_runner_raises_memory_error)


class TestRssEarlyAbort:
    """P0-10 RSS 早停看门狗（35 §3.2 第 4 条）：超 12GB 预算 80%（9830MB）且
    持续上升 → 主动终止并落可读资源配额错误；平台/单次尖峰不误杀。
    全部用合成轨迹（注入 rss_fn），不起真实内存压力。"""

    THRESHOLD = 0.8 * 12 * 1024  # 9830.4 MB

    def _trajectory(self, values):
        it = iter(values)
        return lambda pid: next(it, values[-1])

    def test_rising_through_threshold_aborts_with_readable_error(self):
        gate = threading.Event()

        def _sleep_runner(job):
            gate.wait(timeout=10)
            return {"summary": {}, "files": []}

        with pytest.raises(RuntimeError, match="资源配额（早停）") as excinfo:
            execute_job_subprocess(
                {"id": 4}, runner=_sleep_runner,
                rss_fn=self._trajectory([8000, 9500, 10000, 10500]),
                rss_limit_mb=self.THRESHOLD, rss_poll_seconds=0.05)
        assert "9830" in str(excinfo.value)
        gate.set()

    def test_plateau_above_threshold_not_killed(self):
        """高位平台（稳态聚合）：不终止，任务正常完成。"""
        gate = threading.Event()

        def _sleep_runner(job):
            time.sleep(0.4)
            return {"summary": {"job": 5}, "files": []}

        payload = execute_job_subprocess(
            {"id": 5}, runner=_sleep_runner,
            rss_fn=self._trajectory([9500, 9900, 9950, 9950, 9950]),
            rss_limit_mb=self.THRESHOLD, rss_poll_seconds=0.05)
        assert payload["summary"] == {"job": 5}

    def test_single_spike_not_killed(self):
        gate = threading.Event()

        def _sleep_runner(job):
            time.sleep(0.4)
            return {"summary": {"job": 6}, "files": []}

        payload = execute_job_subprocess(
            {"id": 6}, runner=_sleep_runner,
            rss_fn=self._trajectory([8000, 10500, 9000, 9000, 9000]),
            rss_limit_mb=self.THRESHOLD, rss_poll_seconds=0.05)
        assert payload["summary"] == {"job": 6}

    def test_default_threshold_is_80pct_of_child_limit(self):
        from quant_research_engine.worker.capacity import early_abort_threshold_mb
        from quant_research_engine.worker.slots import DEFAULT_CHILD_MEM_LIMIT_GB

        assert early_abort_threshold_mb() == pytest.approx(0.8 * 12 * 1024, abs=0.1)
        assert DEFAULT_CHILD_MEM_LIMIT_GB == 12.0
