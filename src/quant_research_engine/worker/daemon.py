"""Worker daemon 主循环（QRE-SAAS M3）：轮询 → 执行 → 心跳 → 回传。

- 间隔轮询 lease（默认 15s，SAAS_WORKER_POLL_SECONDS 可配）；
- 拿到任务后由 runner.execute_job 执行，运行期间后台线程每 60s
  （SAAS_WORKER_HEARTBEAT_SECONDS 可配）发 heartbeat 续租；
- 结束后 result 回传（done / failed）；
- 所有异常兜底：单个 job 失败回传 failed 后继续轮询，daemon 不死；
  回传本身失败（网络）只记日志等下一租约（lease 过期后云端自动重排）。
- SIGTERM/SIGINT 优雅退出：正在执行的任务**等其完成并回传**后退出
  （取舍说明：放弃任务会让它等 lease 过期（15min）才重排，回测多为
  分钟级，等完成对用户更快；强杀由 systemd TimeoutStopSec 兜底）。

入口：`qre worker`（CLI 子命令）或
`python -m quant_research_engine.worker.daemon`。
"""

from __future__ import annotations

import os
import signal
from pathlib import Path
import threading
import time
from typing import Any, Callable

from quant_research_engine.worker.client import CloudClient, CloudError
from quant_research_engine.worker.runner import execute_job

DEFAULT_POLL_SECONDS = 15.0
DEFAULT_HEARTBEAT_SECONDS = 60.0
DEFAULT_STATUS_SECONDS = 15.0


def _upload_files_enabled() -> bool:
    # 产物文件上传统一开关（默认关：meta 里的 summary/chart_data 已够 Web 展示，
    # 大 CSV 走 OSS 直传是 M4；本地 staging 联调可开）
    return os.environ.get("QRE_WORKER_UPLOAD_FILES") == "1"


def _log(msg: str) -> None:
    print(f"[worker {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


class WorkerDaemon:
    def __init__(
        self,
        client: CloudClient,
        *,
        runner: Callable[[dict[str, Any]], dict[str, Any]] = execute_job,
        poll_seconds: float = DEFAULT_POLL_SECONDS,
        heartbeat_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
        status_seconds: float = DEFAULT_STATUS_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.runner = runner
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.status_seconds = status_seconds
        self._sleep = sleep
        self._stop = threading.Event()
        # R3 切片1：槽位实时状态表（线程安全），供 status 上报线程读取
        self._slot_lock = threading.Lock()
        self._slots: dict[str, dict[str, Any]] = {}

    # --- R3 切片1：槽位状态跟踪 + 周期上报 ---

    def _slot_set(self, name: str, kind: str, busy: bool, job_id: int | None) -> None:
        with self._slot_lock:
            self._slots[name] = {"name": name, "kind": kind, "busy": busy, "job_id": job_id}

    def slots_snapshot(self) -> list[dict[str, Any]]:
        with self._slot_lock:
            return [dict(s) for s in self._slots.values()]

    def build_status_payload(self, limits: dict[str, Any],
                             mem_fn: Callable[[], float] | None = None) -> dict[str, Any]:
        """组装一次状态上报负载（纯函数便于测试）。"""
        from quant_research_engine.worker.slots import mem_available_mb, mem_total_mb

        avail = (mem_fn or mem_available_mb)()
        if avail == float("inf"):
            avail = None  # 非 Linux 读不到：JSONB 不能落 Infinity，降级 NULL
        return {
            "mem_available_mb": avail,
            "mem_total_mb": mem_total_mb(),
            "slots": self.slots_snapshot(),
            "limits": limits,
        }

    def report_status_once(self, limits: dict[str, Any],
                           mem_fn: Callable[[], float] | None = None) -> bool:
        """上报一次状态；失败仅记日志返回 False，不抛异常。"""
        try:
            self.client.report_status(self.build_status_payload(limits, mem_fn))
            return True
        except Exception as exc:  # noqa: BLE001 —— 上报失败不中断 worker
            _log(f"status 上报失败（{exc}）")
            return False

    def _status_loop(self, limits: dict[str, Any], mem_fn: Callable[[], float] | None) -> None:
        self.report_status_once(limits, mem_fn)  # 启动即报一次，管理台尽快可见
        while not self._stop.wait(self.status_seconds):
            self.report_status_once(limits, mem_fn)

    def _start_status_thread(self, limits: dict[str, Any],
                             mem_fn: Callable[[], float] | None = None) -> threading.Thread:
        t = threading.Thread(target=self._status_loop, name="status",
                             args=(limits, mem_fn), daemon=True)
        t.start()
        return t

    def stop(self) -> None:
        self._stop.set()

    def _run_job(self, job: dict[str, Any], runner: Callable[..., dict[str, Any]] | None = None) -> None:
        """执行单个 job：心跳线程 + 执行 + 两步回传。异常全部兜底。

        取消传播（17 协议 §5）：心跳响应 cancel_requested=true 时立即上报
        fail(canceled) 并跳过结果回传。runner 可接收 canceled 事件做提前终止
        （子进程模式可强杀）；不支持提前终止的单体 runner 则跑完后丢弃结果。
        """
        job_id = job["id"]
        done_event = threading.Event()
        canceled = threading.Event()
        if runner is None:
            base_runner = self.runner
            run_fn: Callable[..., dict[str, Any]] = lambda j, _ev: base_runner(j)  # noqa: E731
        else:
            run_fn = runner

        def _heartbeat_loop() -> None:
            while not done_event.wait(self.heartbeat_seconds):
                try:
                    resp = self.client.heartbeat(job_id)
                    if resp.get("cancel_requested") and not canceled.is_set():
                        canceled.set()
                        _log(f"job {job_id} 收到取消标记，上报 canceled 并丢弃结果")
                        try:
                            self.client.fail(job_id, "用户取消", error_class="canceled")
                        except Exception as exc:
                            _log(f"job {job_id} canceled 上报失败（{exc}）")
                except Exception as exc:  # 心跳失败不杀任务，租约过期由云端重排
                    _log(f"job {job_id} heartbeat 失败（{exc}），继续执行")

        hb = threading.Thread(target=_heartbeat_loop, daemon=True)
        hb.start()
        try:
            payload = run_fn(job, canceled)
        except Exception as exc:
            if canceled.is_set():
                return  # 已上报 canceled，不再重复报 failed
            _log(f"job {job_id} 执行失败：{exc}")
            try:
                self.client.fail(job_id, str(exc))
            except Exception as report_exc:
                _log(f"job {job_id} failed 回传失败（{report_exc}），等租约过期重排")
            return
        finally:
            done_event.set()
        if canceled.is_set():
            return  # 已上报 canceled，丢弃结果
        if not _upload_files_enabled():
            payload = {**payload, "files": []}  # 不上传则不报清单，云端直接 completed
        try:
            meta = self.client.report_result(job_id, payload)
            upload_token = meta.get("upload_token")
            files = payload.get("files") or []
            if upload_token and files and _upload_files_enabled():
                blobs = {}
                for f in files:
                    blobs[f["name"]] = Path(f["path"]).read_bytes()
                self.client.upload_files(job_id, upload_token, blobs)
            _log(f"job {job_id} done，已回传")
        except Exception as exc:
            _log(f"job {job_id} done 回传失败（{exc}），等租约过期重排")

    def run_once(self) -> bool:
        """单轮循环（测试友好）：领到并执行了一个任务返回 True，空轮 False。"""
        try:
            job = self.client.claim(wait_seconds=self.poll_seconds)
        except CloudError as exc:
            _log(f"claim 失败：{exc}")
            return False
        if not job:
            return False
        _log(f"claimed job {job['id']}（kind={job.get('kind')}，attempt={job.get('attempt')}）")
        self._slot_set("main", "light", True, job["id"])
        try:
            self._run_job(job)
        finally:
            self._slot_set("main", "light", False, None)
        return True

    def run_forever(self) -> None:
        _log(f"worker {self.client.worker_id} 启动，轮询 {self.client.base_url}")
        # R3 切片1：单槽旧模式等效上报（light_slots=1, heavy_slots=0）
        self._slot_set("main", "light", False, None)
        self._start_status_thread({
            "light_slots": 1, "heavy_slots": 0,
            "light_min_avail_mb": None, "heavy_min_avail_mb": None,
        })
        while not self._stop.is_set():
            self.run_once()
            self._sleep(self.poll_seconds)
        _log("收到退出信号，已退出主循环")

    # --- R2 多槽位模式（2026-10-03）：轻/重槽线程 + 内存闸门 + 子进程隔离 ---

    def _slot_loop(
        self,
        slot_name: str,
        classes: str,
        min_avail_mb: float,
        mem_fn: Callable[[], float],
    ) -> None:
        """单个槽位线程：内存够 → claim → 子进程执行 → 循环；收到 stop 后
        跑完当前任务再退出（优雅退出语义与单槽一致）。"""
        from quant_research_engine.worker.slots import execute_job_subprocess

        def _runner(j: dict[str, Any], ev: threading.Event) -> dict[str, Any]:
            return execute_job_subprocess(j, is_canceled=ev.is_set)

        _log(f"[{slot_name}] 槽位启动（classes={classes}，内存闸门 {min_avail_mb:.0f}MB）")
        self._slot_set(slot_name, "light" if classes == "light" else "heavy", False, None)
        while not self._stop.is_set():
            avail = mem_fn()
            if avail < min_avail_mb:
                _log(f"[{slot_name}] 可用内存 {avail:.0f}MB < 闸门 {min_avail_mb:.0f}MB，暂缓领取")
                self._sleep(self.poll_seconds)
                continue
            try:
                job = self.client.claim(wait_seconds=self.poll_seconds, classes=classes)
            except CloudError as exc:
                _log(f"[{slot_name}] claim 失败：{exc}")
                self._sleep(self.poll_seconds)
                continue
            if not job:
                continue
            _log(f"[{slot_name}] claimed job {job['id']}（kind={job.get('kind')}）")
            kind = "light" if classes == "light" else "heavy"
            self._slot_set(slot_name, kind, True, job["id"])
            try:
                self._run_job(job, runner=_runner)
            finally:
                self._slot_set(slot_name, kind, False, None)
        _log(f"[{slot_name}] 槽位退出")

    def run_slots_forever(
        self,
        light_slots: int,
        heavy_slots: int,
        light_min_avail_mb: float,
        heavy_min_avail_mb: float,
        mem_fn: Callable[[], float] | None = None,
    ) -> None:
        """多槽位主循环：轻量槽只领轻任务，重量槽领任意任务。"""
        if mem_fn is None:
            from quant_research_engine.worker.slots import mem_available_mb as mem_fn

        threads: list[threading.Thread] = []
        for i in range(light_slots):
            threads.append(threading.Thread(
                target=self._slot_loop, name=f"light-{i + 1}",
                args=(f"light-{i + 1}", "light", light_min_avail_mb, mem_fn), daemon=True))
        for i in range(heavy_slots):
            threads.append(threading.Thread(
                target=self._slot_loop, name=f"heavy-{i + 1}",
                args=(f"heavy-{i + 1}", "any", heavy_min_avail_mb, mem_fn), daemon=True))
        _log(
            f"worker {self.client.worker_id} 启动（R2 多槽位：轻 {light_slots} + 重 {heavy_slots}），"
            f"轮询 {self.client.base_url}"
        )
        limits = {
            "light_slots": light_slots,
            "heavy_slots": heavy_slots,
            "light_min_avail_mb": light_min_avail_mb,
            "heavy_min_avail_mb": heavy_min_avail_mb,
        }
        self._start_status_thread(limits, mem_fn)
        for t in threads:
            t.start()
        try:
            while any(t.is_alive() for t in threads):
                for t in threads:
                    t.join(timeout=0.5)
        except KeyboardInterrupt:
            self.stop()
        for t in threads:
            t.join()
        _log("全部槽位已退出")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="qre worker", description="QRE SaaS 回测 Worker（出站轮询云端任务）")
    parser.add_argument("--poll-seconds", type=float,
                        default=float(os.environ.get("SAAS_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS)))
    parser.add_argument("--heartbeat-seconds", type=float,
                        default=float(os.environ.get("SAAS_WORKER_HEARTBEAT_SECONDS", DEFAULT_HEARTBEAT_SECONDS)))
    # R3 切片1：状态上报间隔（槽位占用/内存水位）
    parser.add_argument("--status-seconds", type=float,
                        default=float(os.environ.get("QRE_WORKER_STATUS_SECONDS", DEFAULT_STATUS_SECONDS)))
    parser.add_argument("--once", action="store_true", help="只跑一轮（调试用）")
    # R2 多槽位（默认开：轻 2 + 重 3 = 内存预算 2×1.5G+3×6G=21G ≤ 25.6G）；
    # --light-slots 0 --heavy-slots 0 回退旧版单槽 run_once 循环
    parser.add_argument("--light-slots", type=int,
                        default=int(os.environ.get("QRE_WORKER_LIGHT_SLOTS", "2")))
    parser.add_argument("--heavy-slots", type=int,
                        default=int(os.environ.get("QRE_WORKER_HEAVY_SLOTS", "3")))
    parser.add_argument("--light-min-avail-mb", type=float,
                        default=float(os.environ.get("QRE_WORKER_LIGHT_MIN_AVAIL_MB", "2000")))
    parser.add_argument("--heavy-min-avail-mb", type=float,
                        default=float(os.environ.get("QRE_WORKER_HEAVY_MIN_AVAIL_MB", "6500")))
    args = parser.parse_args(argv)

    client = CloudClient.from_env()
    daemon = WorkerDaemon(
        client,
        poll_seconds=args.poll_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
        status_seconds=args.status_seconds,
    )

    def _handle_signal(signum: int, frame: Any) -> None:
        daemon.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if args.once:
        daemon.run_once()
        return 0
    if args.light_slots + args.heavy_slots > 0:
        daemon.run_slots_forever(
            light_slots=args.light_slots,
            heavy_slots=args.heavy_slots,
            light_min_avail_mb=args.light_min_avail_mb,
            heavy_min_avail_mb=args.heavy_min_avail_mb,
        )
        return 0
    daemon.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
