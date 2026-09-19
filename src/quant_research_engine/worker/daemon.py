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
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.client = client
        self.runner = runner
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self._sleep = sleep
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _run_job(self, job: dict[str, Any]) -> None:
        """执行单个 job：心跳线程 + 执行 + 两步回传。异常全部兜底。

        取消传播（17 协议 §5）：心跳响应 cancel_requested=true 时立即上报
        fail(canceled) 并跳过结果回传。注意：引擎执行是单体的，无法中途杀——
        取舍为「立即上报终态 + 本地跑完后丢弃结果」，单并发约束保持
        （本 job 线程未结束前不 claim 下一个）。
        """
        job_id = job["id"]
        done_event = threading.Event()
        canceled = threading.Event()

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
            payload = self.runner(job)
        except Exception as exc:
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
        self._run_job(job)
        return True

    def run_forever(self) -> None:
        _log(f"worker {self.client.worker_id} 启动，轮询 {self.client.base_url}")
        while not self._stop.is_set():
            self.run_once()
            self._sleep(self.poll_seconds)
        _log("收到退出信号，已退出主循环")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="qre worker", description="QRE SaaS 回测 Worker（出站轮询云端任务）")
    parser.add_argument("--poll-seconds", type=float,
                        default=float(os.environ.get("SAAS_WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS)))
    parser.add_argument("--heartbeat-seconds", type=float,
                        default=float(os.environ.get("SAAS_WORKER_HEARTBEAT_SECONDS", DEFAULT_HEARTBEAT_SECONDS)))
    parser.add_argument("--once", action="store_true", help="只跑一轮（调试用）")
    args = parser.parse_args(argv)

    client = CloudClient.from_env()
    daemon = WorkerDaemon(
        client,
        poll_seconds=args.poll_seconds,
        heartbeat_seconds=args.heartbeat_seconds,
    )

    def _handle_signal(signum: int, frame: Any) -> None:
        daemon.stop()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    if args.once:
        daemon.run_once()
        return 0
    daemon.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
