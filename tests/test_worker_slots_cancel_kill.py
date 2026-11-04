"""P0-11 回归：取消/RSS 早停必须真正杀死子进程（2026-11-04）。

事故：job244 取消后子进程忽略 SIGTERM 继续跑 7 分钟、占 625MB，
只能手动 SIGKILL。根因：slots 只 terminate + join(5) 就放弃。
修复：`_terminate_child` 在宽限期后 SIGKILL 兜底。本测试构造一个
显式忽略 SIGTERM 的子进程，断言取消路径结束后它确实已退出并被回收。
"""

from __future__ import annotations

import os
import signal
import time

import pytest

from quant_research_engine.worker import slots


def test_cancel_kills_child_that_ignores_sigterm(tmp_path):
    pid_file = tmp_path / "child.pid"

    def runner(job, work_base=None):  # noqa: ARG001 - 签名与 _child_entry 约定一致
        pid_file.write_text(str(os.getpid()))
        signal.signal(signal.SIGTERM, signal.SIG_IGN)  # 模拟阻塞在长计算中的子进程
        while True:
            time.sleep(0.05)

    started = time.monotonic()
    with pytest.raises(RuntimeError, match="用户取消"):
        slots.execute_job_subprocess(
            {"id": 1},
            runner=runner,
            is_canceled=lambda: True,
            poll_seconds=0.2,
        )
    assert time.monotonic() - started < 30  # 宽限 + SIGKILL，不无限等待

    pid = int(pid_file.read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)  # 进程已退出且被 join 回收（非僵尸）


def test_normal_child_still_runs_to_completion():
    def runner(job, work_base=None):  # noqa: ARG001
        return {"ok": True, "echo": job["id"]}

    result = slots.execute_job_subprocess({"id": 7}, runner=runner, poll_seconds=0.2)
    assert result["echo"] == 7
