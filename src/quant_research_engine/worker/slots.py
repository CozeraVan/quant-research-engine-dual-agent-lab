"""R2 多租户弹性调度：worker 槽位内存闸门 + 子进程隔离执行（2026-10-03）。

依据 N3 容量基线（docs/agent/14_LAUNCH_ROADMAP.md §10）：内存是回测并发的
硬约束（全A×2年单任务峰值 5.79G），CPU 余量充足。本模块提供两件套：

- ``mem_available_mb``：领取任务前的内存闸门——本机可用内存不足时槽位
  暂缓 claim，本机有其他负载（浏览器/手动计算/PG 高峰）时 worker 自动降速。
- ``execute_job_subprocess``：把 runner.execute_job 放进 fork 子进程执行。
  三个目的：① GIL 隔离，多槽真并行（N3 并发口径即多进程）；② 内存隔离，
  单任务失控（泄漏/爆内存）只死子进程，daemon 与兄弟任务不受影响；
  ③ 用户取消时可真正 terminate（单体执行时代只能"跑完丢弃结果"）。
"""

from __future__ import annotations

import multiprocessing
import os
import queue as queue_mod
from typing import Any, Callable

#: 回测子进程地址空间硬上限（GB；0 或负值=不限制，QRE_WORKER_CHILD_MEM_GB 可配）。
#: 全市场全期回测预算 12GB（23G 物理内存 ~50%），超限由子进程抛可读
#: MemoryError（“任务超出资源配额”）而非被全局 OOM killer 裸 -9。
DEFAULT_CHILD_MEM_LIMIT_GB = 14.0


def _apply_child_memory_limit() -> None:
    """子进程内设置 RLIMIT_AS 硬上限；非 Unix 或设置失败时静默跳过（不阻断任务）。"""
    try:
        limit_gb = float(os.environ.get("QRE_WORKER_CHILD_MEM_GB", DEFAULT_CHILD_MEM_LIMIT_GB))
    except ValueError:
        limit_gb = DEFAULT_CHILD_MEM_LIMIT_GB
    if limit_gb <= 0:
        return
    try:
        import resource

        limit_bytes = int(limit_gb * 1024**3)
        # 守卫：当前虚拟地址空间已超上限时不设置——RLIMIT_AS 低于当前 VSZ 会让
        # 进程进入"任何分配都失败"的病态（fork 自 pytest 等大进程时实测子进程
        # 挂死在退出路径）。正常 worker 子进程 VSZ 远小于 14G，守卫不改变配额语义。
        try:
            with open("/proc/self/stat", encoding="ascii") as fh:
                vsize = int(fh.read().rsplit(")", 1)[-1].split()[20])
        except (OSError, ValueError, IndexError):
            vsize = 0
        if vsize and vsize >= limit_bytes:
            return
        _soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        new_hard = limit_bytes if hard in (resource.RLIM_INFINITY, -1) else min(hard, limit_bytes)
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, new_hard))
    except (ImportError, OSError, ValueError):
        pass


def mem_available_mb(meminfo_path: str = "/proc/meminfo") -> float:
    """本机可用内存（MB）。读 /proc/meminfo 的 MemAvailable；
    读取失败（非 Linux）返回 inf（不限制，由槽位数兜底）。"""
    try:
        with open(meminfo_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return float("inf")


def mem_total_mb(meminfo_path: str = "/proc/meminfo") -> float | None:
    """本机物理内存总量（MB）。读 /proc/meminfo 的 MemTotal；
    读取失败（非 Linux）返回 None（管理台降级为不显示总量）。"""
    try:
        with open(meminfo_path, encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        pass
    return None


def _child_entry(job: dict[str, Any], result_q: Any, runner: Callable[..., dict[str, Any]]) -> None:
    """子进程入口：执行 runner 并把结果/异常文本塞进队列。"""
    _apply_child_memory_limit()
    try:
        payload = runner(job)
        result_q.put(("ok", payload))
    except MemoryError:
        limit_gb = os.environ.get("QRE_WORKER_CHILD_MEM_GB", DEFAULT_CHILD_MEM_LIMIT_GB)
        result_q.put((
            "err",
            f"MemoryError: 任务超出资源配额（回测子进程内存上限 {limit_gb}GB，"
            "QRE_WORKER_CHILD_MEM_GB 可调）；请缩小股票范围/区间或联系管理员",
        ))
    except Exception as exc:  # noqa: BLE001 —— 子进程内必须兜底，异常文本回传父进程
        result_q.put(("err", f"{type(exc).__name__}: {exc}"))


def execute_job_subprocess(
    job: dict[str, Any],
    *,
    runner: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    is_canceled: Callable[[], bool] | None = None,
    poll_seconds: float = 1.0,
) -> dict[str, Any]:
    """在 fork 子进程里执行一个 leased job，返回 result payload。

    - runner 抛异常 → RuntimeError（异常文本来自子进程）；
    - 子进程未产出结果就死（OOM 被杀/段错误）→ RuntimeError（注明 exitcode）；
    - is_canceled() 为 True → terminate 子进程并抛 RuntimeError("用户取消")。
    """
    if runner is None:
        from quant_research_engine.worker.runner import execute_job as runner  # 延迟导入（fork 友好）

    ctx = multiprocessing.get_context("fork")
    result_q: Any = ctx.Queue()
    proc = ctx.Process(target=_child_entry, args=(job, result_q, runner), daemon=True)
    proc.start()
    try:
        while True:
            try:
                status, payload = result_q.get(timeout=poll_seconds)
            except queue_mod.Empty:
                if is_canceled is not None and is_canceled():
                    proc.terminate()
                    proc.join(timeout=5)
                    raise RuntimeError("用户取消")
                if not proc.is_alive():
                    # 子进程没来得及放结果就退出：崩溃/OOM
                    proc.join(timeout=5)
                    try:
                        status, payload = result_q.get_nowait()
                    except queue_mod.Empty:
                        raise RuntimeError(
                            f"回测子进程异常退出（exitcode={proc.exitcode}；"
                            "负值通常为被信号杀死，-9 多为内存不足触发 OOM）"
                        )
                else:
                    continue
            proc.join(timeout=5)
            if status == "ok":
                return payload
            raise RuntimeError(str(payload))
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
