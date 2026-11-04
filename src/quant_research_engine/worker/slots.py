"""R2 多租户弹性调度：worker 槽位内存闸门 + 子进程隔离执行（2026-10-03）。

依据 N3 容量基线（docs/agent/14_LAUNCH_ROADMAP.md §10）：内存是回测并发的
硬约束（全A×2年单任务峰值 5.79G），CPU 余量充足。本模块提供两件套：

- ``mem_available_mb``：领取任务前的内存闸门——本机可用内存不足时槽位
  暂缓 claim，本机有其他负载（浏览器/手动计算/PG 高峰）时 worker 自动降速。
- ``execute_job_subprocess``：把 runner.execute_job 放进 fork 子进程执行。
  三个目的：① GIL 隔离，多槽真并行（N3 并发口径即多进程）；② 内存隔离，
  单任务失控（泄漏/爆内存）只死子进程，daemon 与兄弟任务不受影响；
  ③ 用户取消时可真正 terminate（单体执行时代只能"跑完丢弃结果"）。

P0-10（35 号容量模型，2026-11-03）新增两层内存安全：
- 子进程默认上限 14→**12GB**（R-MEM-001 规则 2：≤物理 50%）。item3 实测峰值
  13.97GB 已越线——超限任务允许**可读失败**（MemoryError / RSS 早停），
  禁止以提高上限绕过；尾段分块修复见 CF 后续安排。
- **RSS 早停看门狗**：父进程每 30s 采样子进程 VmRSS，超过 12GB 预算的 80%
  且持续上升时主动 terminate 并落可读「资源配额（早停）」错误——相比等
  RLIMIT/cgroup 在序列化末段才杀，可省 30–60 分钟无效计算；高位平台与单次
  尖峰不误杀（判定逻辑见 worker/capacity.rss_watchdog_verdict）。
"""

from __future__ import annotations

import multiprocessing
import os
import queue as queue_mod
import time
from collections import deque
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.worker.capacity import (
    RSS_POLL_SECONDS,
    early_abort_threshold_mb,
    rss_watchdog_verdict,
)

#: 回测子进程地址空间硬上限（GB；0 或负值=不限制，QRE_WORKER_CHILD_MEM_GB 可配）。
#: R-MEM-001 规则 2：单子进程峰值 ≤ 物理内存 50%（本机 23.5GiB → ≈11.7GiB，取 12）。
#: 原默认 14 已越线（item3 实测 13.97GB 靠运气未死）；超限由子进程抛可读
#: MemoryError（“任务超出资源配额”）而非被全局 OOM killer 裸 -9。
DEFAULT_CHILD_MEM_LIMIT_GB = 12.0


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
        # 挂死在退出路径）。正常 worker 子进程 VSZ 远小于 12G，守卫不改变配额语义。
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


def _child_rss_mb(pid: int) -> float | None:
    """子进程常驻内存（MB）：读 /proc/<pid>/status 的 VmRSS。
    进程已退出/读失败返回 None（看门狗跳过该次采样）。"""
    try:
        with open(f"/proc/{pid}/status", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return float(line.split()[1]) / 1024.0
    except (OSError, ValueError, IndexError):
        return None
    return None


def _child_entry(job: dict[str, Any], result_q: Any, runner: Callable[..., dict[str, Any]],
                 work_base: str | Path | None = None) -> None:
    """子进程入口：执行 runner 并把结果/异常文本塞进队列。

    P0-9（CR-2026-11-03）：work_base 由 daemon 自建并透传——沙箱目录归属明确
    （§8.7 终态后安全清理）；progress.json 也写在这里供父进程心跳读取（§8.11）。
    """
    _apply_child_memory_limit()
    try:
        payload = runner(job, work_base=work_base) if work_base is not None else runner(job)
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


def _terminate_child(proc: Any, *, grace_seconds: float = 5.0) -> None:
    """终止子进程：SIGTERM → 宽限内未退出则 SIGKILL。

    2026-11-04 修复：取消/早停原先只 ``terminate()`` + ``join(5)`` 就放弃，
    子进程若正阻塞在长计算中不响应 SIGTERM，会继续占用数 GB 内存（实测
    job244 取消后仍跑 7 分钟，只能手动 SIGKILL）。资源释放必须有兜底。
    """
    if not proc.is_alive():
        return
    proc.terminate()
    proc.join(timeout=grace_seconds)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=grace_seconds)


def execute_job_subprocess(
    job: dict[str, Any],
    *,
    runner: Callable[..., dict[str, Any]] | None = None,
    is_canceled: Callable[[], bool] | None = None,
    poll_seconds: float = 1.0,
    work_base: str | Path | None = None,
    rss_fn: Callable[[int], float | None] | None = None,
    rss_limit_mb: float | None = None,
    rss_poll_seconds: float = RSS_POLL_SECONDS,
) -> dict[str, Any]:
    """在 fork 子进程里执行一个 leased job，返回 result payload。

    - runner 抛异常 → RuntimeError（异常文本来自子进程）；
    - 子进程未产出结果就死（OOM 被杀/段错误）→ RuntimeError（注明 exitcode）；
    - is_canceled() 为 True → terminate 子进程并抛 RuntimeError("用户取消")；
    - work_base（P0-9）：daemon 自建的沙箱目录，透传 runner——产物写在这里，
      终态后由 daemon 按归属判定清理（§8.7），progress.json 也供父进程心跳
      读取（§8.11）；None 时 runner 自建（旧行为）；
    - rss_fn/rss_limit_mb/rss_poll_seconds（P0-10 RSS 早停）：父进程按
      rss_poll_seconds 采样子进程 RSS，超过 rss_limit_mb（默认 12GB 的 80%）
      且持续上升 → terminate 并抛可读「资源配额（早停）」RuntimeError。
      rss_fn 为测试注入点（合成轨迹）；默认读 /proc/<pid>/status VmRSS。
    """
    if runner is None:
        from quant_research_engine.worker.runner import execute_job as runner  # 延迟导入（fork 友好）

    ctx = multiprocessing.get_context("fork")
    result_q: Any = ctx.Queue()
    proc = ctx.Process(target=_child_entry, args=(job, result_q, runner, work_base), daemon=True)
    proc.start()
    # P0-10 早停看门狗状态：采样窗口（单调上升判定）+ 上次采样时刻
    rss_reader = rss_fn or _child_rss_mb
    limit_mb = early_abort_threshold_mb() if rss_limit_mb is None else float(rss_limit_mb)
    samples: deque[float] = deque(maxlen=3)
    last_rss_at = 0.0
    try:
        while True:
            try:
                status, payload = result_q.get(timeout=poll_seconds)
            except queue_mod.Empty:
                if is_canceled is not None and is_canceled():
                    _terminate_child(proc)
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
                    # P0-10：RSS 早停——超过预算 80% 且持续上升才终止
                    # （平台/单次尖峰不误杀；峰值前拦下可省 30–60 分钟无效计算）
                    now = time.monotonic()
                    if now - last_rss_at >= rss_poll_seconds:
                        last_rss_at = now
                        rss_mb = rss_reader(proc.pid)
                        if rss_mb is not None:
                            samples.append(rss_mb)
                            if rss_watchdog_verdict(samples, limit_mb):
                                _terminate_child(proc)
                                raise RuntimeError(
                                    f"任务超出资源配额（早停）：子进程 RSS {rss_mb:.0f}MB "
                                    f"超过预算 {limit_mb:.0f}MB（12GB 的 80%）且持续上升；"
                                    "请缩小股票范围/区间或联系管理员"
                                )
                    continue
            proc.join(timeout=5)
            if status == "ok":
                return payload
            raise RuntimeError(str(payload))
    finally:
        _terminate_child(proc)
