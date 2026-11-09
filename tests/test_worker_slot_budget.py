"""P0-10 在途预算记账与 heavy 限流（35 号 §3.2 第 1/2 条的调度落地）。

覆盖：
1. 未知全市场 heavy 每 worker 同时最多 1 个（第二个重槽被在途预算阻断，不 claim）；
2. 轻任务隔离保留：一个 heavy 在途时仍可放行一个轻任务（1.5+13.97 ≤ 15.5），
   第二个轻任务被阻断；
3. 认领前原子预留：claim 异常/空轮询释放占位，不泄漏预算；
4. claim 后按任务真实档位定账（重槽领到轻任务时释放多预留，槽位快照可证）；
5. 现有内存闸门语义不变（闸门不足仍暂缓）；
6. worker 预算小于单个未知全市场预算 → 重槽全部暂缓（保守默认生效）。
"""

from __future__ import annotations

import threading
import time

import pytest

from quant_research_engine.worker import daemon as worker_daemon
from quant_research_engine.worker.capacity import ADMISSION_BUDGET_GB
from quant_research_engine.worker.client import CloudError
from quant_research_engine.worker.daemon import WorkerDaemon

FULL_MARKET_JOB = {"id": 7, "kind": "full", "params": {}}
LIGHT_JOB = {"id": 8, "kind": "full", "params": {"codes": ["000001.SZ"]}}


class _FakeClient:
    def __init__(self, jobs=None, claim_exc=None):
        self.jobs = list(jobs or [])
        self.claim_exc = claim_exc
        self.claim_calls: list[str] = []
        self.worker_id = "w"
        self.base_url = "http://fake"

    def claim(self, wait_seconds=0, classes="any"):
        self.claim_calls.append(classes)
        if self.claim_exc is not None:
            raise self.claim_exc
        return self.jobs.pop(0) if self.jobs else None

    def heartbeat(self, job_id, progress=None, message=None):
        return {"cancel_requested": False}

    def report_result(self, job_id, payload):
        return {}

    def fail(self, job_id, error, error_class="engine_error"):
        return {}


class _Gate:
    def __init__(self):
        self.entered = threading.Event()
        self.release = threading.Event()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """隔离：沙箱目录落 tmp_path（daemon mkdtemp）；捕获 daemon 日志；拦截子进程。

    回收：teardown 停止所有 daemon 并释放所有闸门——槽位线程是 daemon 线程，
    遗留线程会在解释器关闭时触发 stdout 锁 fatal（CLI 实测），必须显式收干净。
    """
    import tempfile as _tempfile

    monkeypatch.setattr(_tempfile, "gettempdir", lambda: str(tmp_path))
    logs: list[str] = []
    monkeypatch.setattr(worker_daemon, "_log", logs.append)
    gates: dict[int, _Gate] = {}
    snapshots: list[dict] = []
    daemons: list[WorkerDaemon] = []
    threads: list[threading.Thread] = []

    def fake_subprocess(job, is_canceled=None, work_base=None):
        gate = gates.get(job["id"])
        if gate is not None:
            snapshots.append({"job_id": job["id"],
                              "slots": _current_daemon.slots_snapshot()})
            gate.entered.set()
            gate.release.wait(timeout=10)
        return {"summary": {}, "chart_data": {}, "files": [], "data_until": None}

    monkeypatch.setattr("quant_research_engine.worker.slots.execute_job_subprocess",
                        fake_subprocess)
    yield {"logs": logs, "gates": gates, "snapshots": snapshots,
           "daemons": daemons, "threads": threads}
    for daemon in daemons:
        daemon.stop()
    for gate in gates.values():
        gate.release.set()
    for t in threads:
        t.join(timeout=10)


_current_daemon: WorkerDaemon | None = None


def _daemon(env, client, **kwargs) -> WorkerDaemon:
    global _current_daemon
    daemon = WorkerDaemon(client, poll_seconds=0.02, heartbeat_seconds=3600,
                          # 真实短睡眠：避免 defer 槽位忙轮（测试里 sleep=None 会
                          # 把空轮询滚成百万次 claim），同时让出 GIL 给断言线程
                          sleep=lambda s: time.sleep(min(s, 0.02)), **kwargs)
    _current_daemon = daemon
    env["daemons"].append(daemon)
    return daemon


def _start_slot(env, daemon, name, classes, mem_fn=lambda: 999999.0,
                min_avail_mb: float = 0.0):
    t = threading.Thread(target=daemon._slot_loop,
                         args=(name, classes, min_avail_mb, mem_fn), daemon=True)
    t.start()
    env["threads"].append(t)
    return t


def _wait_claims(client, count, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and len(client.claim_calls) < count:
        time.sleep(0.05)
    return len(client.claim_calls)


class TestHeavyBudgetGate:
    def test_second_unknown_fullmarket_heavy_blocked(self, env):
        gate = env["gates"].setdefault(7, _Gate())
        client = _FakeClient(jobs=[dict(FULL_MARKET_JOB)])
        daemon = _daemon(env, client)
        t1 = _start_slot(env, daemon, "heavy-1", "any")
        assert gate.entered.wait(5), "heavy-1 应进入执行"
        t2 = _start_slot(env, daemon, "heavy-2", "any")
        time.sleep(0.3)
        assert client.claim_calls == ["any"], "第二个未知全市场 heavy 不应被放行"
        assert any("在途预算" in line for line in env["logs"]), env["logs"]
        gate.release.set()

    def test_heavy_admitted_after_release(self, env):
        g1 = env["gates"].setdefault(7, _Gate())
        g2 = env["gates"].setdefault(9, _Gate())
        client = _FakeClient(jobs=[dict(FULL_MARKET_JOB),
                                   dict(FULL_MARKET_JOB, id=9)])
        daemon = _daemon(env, client)
        t1 = _start_slot(env, daemon, "heavy-1", "any")
        assert g1.entered.wait(5)
        _start_slot(env, daemon, "heavy-2", "any")
        time.sleep(0.2)
        assert client.claim_calls == ["any"]
        g1.release.set()
        assert _wait_claims(client, 2) == 2, "heavy-1 结束后 heavy-2 应认领"
        g2.release.set()

    def test_light_slot_admitted_alongside_one_heavy(self, env):
        gate = env["gates"].setdefault(7, _Gate())
        client = _FakeClient(jobs=[dict(FULL_MARKET_JOB)])
        daemon = _daemon(env, client)
        t1 = _start_slot(env, daemon, "heavy-1", "any")
        assert gate.entered.wait(5)
        client.jobs.append(dict(LIGHT_JOB))
        _start_slot(env, daemon, "light-1", "light")
        assert _wait_claims(client, 2) == 2, "heavy 在途时轻任务应放行（1.5+13.97≤15.5）"
        assert "light" in client.claim_calls
        gate.release.set()

    def test_second_light_blocked_while_heavy_running(self, env):
        """两个轻槽：light-1 跑第一个轻任务（闸门阻塞），light-2 的第二个轻任务
        被在途预算阻断（13.97+1.5+1.5 > 15.5）。"""
        heavy_gate = env["gates"].setdefault(7, _Gate())
        light_gate = env["gates"].setdefault(8, _Gate())
        client = _FakeClient(jobs=[dict(FULL_MARKET_JOB)])
        daemon = _daemon(env, client)
        _start_slot(env, daemon, "heavy-1", "any")
        assert heavy_gate.entered.wait(5)
        client.jobs.extend([dict(LIGHT_JOB), dict(LIGHT_JOB, id=12)])
        _start_slot(env, daemon, "light-1", "light")
        assert light_gate.entered.wait(5), "light-1 应进入第一个轻任务"
        _start_slot(env, daemon, "light-2", "light")
        time.sleep(0.3)
        assert client.claim_calls.count("light") == 1, "第二个轻任务不应被放行"
        assert any("在途预算" in line for line in env["logs"])
        heavy_gate.release.set()
        light_gate.release.set()

    def test_small_worker_budget_blocks_all_heavy(self, env):
        client = _FakeClient(jobs=[dict(FULL_MARKET_JOB)])
        daemon = _daemon(env, client, worker_budget_gb=2.0)
        _start_slot(env, daemon, "heavy-1", "any")
        time.sleep(0.3)
        assert client.claim_calls == []
        assert any("在途预算" in line for line in env["logs"])

    def test_memory_gate_still_applies(self, env):
        client = _FakeClient(jobs=[dict(LIGHT_JOB)])
        daemon = _daemon(env, client)
        _start_slot(env, daemon, "light-1", "light",
                    mem_fn=lambda: 500.0, min_avail_mb=2000.0)
        time.sleep(0.3)
        assert client.claim_calls == []
        assert any("闸门" in line for line in env["logs"])


class TestReservationLifecycle:
    def test_claim_error_releases_reservation(self, env):
        client = _FakeClient(claim_exc=CloudError("云端不可达"))
        daemon = _daemon(env, client)
        _start_slot(env, daemon, "light-1", "light")
        time.sleep(0.3)
        assert client.claim_calls
        # 停止并 join 后再断言：循环中间态本就持有占位（reserve→claim→release），
        # 泄漏判据是「迭代结束后不残留」
        daemon.stop()
        for t in env["threads"]:
            t.join(timeout=10)
        assert daemon._ledger.inflight_gb() == 0.0, "claim 失败后占位必须释放"

    def test_empty_claim_releases_reservation(self, env):
        client = _FakeClient(jobs=[])
        daemon = _daemon(env, client)
        _start_slot(env, daemon, "heavy-1", "any")
        time.sleep(0.3)
        assert client.claim_calls
        daemon.stop()
        for t in env["threads"]:
            t.join(timeout=10)
        assert daemon._ledger.inflight_gb() == 0.0

    def test_commit_uses_job_tier_after_claim(self, env):
        """重槽领到轻任务：执行期间槽位快照 budget=1.5/tier=light（多预留已释放）。"""
        gate = env["gates"].setdefault(8, _Gate())
        client = _FakeClient(jobs=[dict(LIGHT_JOB)])
        daemon = _daemon(env, client)
        _start_slot(env, daemon, "heavy-1", "any")
        assert gate.entered.wait(5)
        snap = env["snapshots"][-1]["slots"]
        busy = [s for s in snap if s.get("busy")]
        assert len(busy) == 1
        assert busy[0]["tier"] == "light"
        assert busy[0]["budget_gb"] == ADMISSION_BUDGET_GB["light"]
        assert daemon._ledger.inflight_gb() == pytest.approx(1.5, abs=0.01)
        # 定账为轻任务后另一个 heavy 也能进（1.5+13.97 ≤ 15.5）
        assert daemon._ledger.try_reserve("heavy-2", ADMISSION_BUDGET_GB["heavy"]) is True
        gate.release.set()
