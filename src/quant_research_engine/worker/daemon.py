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

import inspect
import json
import os
import shutil
import signal
import tempfile
from pathlib import Path
import threading
import time
from typing import Any, Callable

from quant_research_engine.worker.capacity import (
    ADMISSION_BUDGET_GB,
    DEFAULT_WORKER_BUDGET_GB,
    BudgetLedger,
    job_tier,
)
from quant_research_engine.worker.client import CloudClient, CloudError

#: P0-9（CR-2026-11-03）：产物回传的 4xx 分类白名单，须与 saas/app.py 的 ERROR_CLASSES 一致。
#:  worker 不 import SaaS app（避免把 Flask 依赖拖进 worker 进程），故在此镜像一份；
#:  新增分类时两边同步（tests/test_result_upload_error_classes.py 锁一致性）。
_UPLOAD_HTTP_CLASSES = frozenset({400, 401, 403, 404, 409, 413, 422, 429})

#: 回传**可重试**状态（2026-11-09 CF-083 事故）：429 限流 / 502/503/504 网关瞬断。
#: 事故经过：2 路并行分片上传叠加心跳触发 nginx worker 通道限流（120r/m burst 30），
#: 429 被原分类当终态 → 已算完 135714 笔的结果整单白丢，还得人工重跑。
#: 重发安全性由 client.upload_files 的语义保证：服务端按 upload_token 幂等、
#: 已落盘文件不进 remaining，整轮重发等价断点续传（重复提交不产生重复产物）。
#: 重试耗尽后仍抛原异常，由既有分类逻辑落 result_upload_http_<code>。
_UPLOAD_RETRY_STATUSES = frozenset({429, 502, 503, 504})

#: 回传重试退避（秒）：总等待 65s，覆盖一次限流窗口而不占用租约太久。
_UPLOAD_RETRY_BACKOFF_S: tuple[float, ...] = (5.0, 15.0, 45.0)
from quant_research_engine.worker.runner import execute_job

DEFAULT_POLL_SECONDS = 15.0
DEFAULT_HEARTBEAT_SECONDS = 60.0
DEFAULT_STATUS_SECONDS = 15.0


def _upload_files_enabled() -> bool:
    # 产物文件上传统一开关（默认关：meta 里的 summary/chart_data 已够 Web 展示，
    # 大 CSV 走 OSS 直传是 M4；本地 staging 联调可开）
    return os.environ.get("QRE_WORKER_UPLOAD_FILES") == "1"


#: P0-9（CR-2026-11-03 §8.7）**主 Agent Required Fix（2026-11-03）**：沙箱目录的
#: 唯一删除前提是「completed **且** 云端完整副本已确认」。上传失败（failed）、
#: 上传开关关闭（blob 从未上云）、manifest 被 20 MiB 预算截断（云端缺文件）、
#: 取消/过期/未知终态——本地沙箱都可能是唯一完整副本（压测归档保护），一律保留。
#: 旧规则「安全终态即删」已废止：failed 时删本地=丢唯一副本。

#: P0-9（CR-2026-11-03 §8.11）：进度阶段——90% 以上留给回传段。终态 100 由服务端
#: 在置 completed 的同一事务落定（Required Fix job 212：completed 后 heartbeat 被拒），
#: worker 不发事后心跳。
_PROGRESS_UPLOADING = 95

#: runner 侧 progress.json 文件名（与 worker/runner.py 约定一致）
_PROGRESS_FILENAME = "progress.json"


def _cloud_copy_complete(payload: dict[str, Any]) -> bool:
    """云端完整副本判定（清理沙箱的唯一前提之一）。

    要求：payload 带 ``result_files`` 完整性元数据且未截断、无缺失文件。
    - 元数据缺失（旧 runner）→ 保守按不完整处理（保留本地）；
    - ``truncated=true`` → 云端只持有部分产物（20 MiB 预算跳过的文件只在本地），
      本地沙箱是唯一完整副本，保留；
    - ``missing_count>0`` → 清单有文件本地已缺失，同样不完整。
    """
    meta = payload.get("result_files")
    if not isinstance(meta, dict):
        return False
    if meta.get("truncated"):
        return False
    return not int(meta.get("missing_count") or 0)


def _accepts_work_base(fn: Any) -> bool:
    """runner 是否接受 work_base 参数（execute_job 系接受；测试注入的简易
    runner 可能只收 job，按能力传参保持兼容）。"""
    try:
        return "work_base" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _read_progress(work_base: Path | None) -> tuple[int | None, str | None]:
    """读 runner 写的 progress.json → (percent, message)；缺失/损坏返回 (None, None)。"""
    if work_base is None:
        return None, None
    try:
        data = json.loads((Path(work_base) / _PROGRESS_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    if not isinstance(data, dict):
        return None, None
    percent = data.get("percent")
    message = data.get("message")
    return (percent if isinstance(percent, int) else None,
            message if isinstance(message, str) else None)


def _clamp_progress(progress: int | None, state: dict[str, Any]) -> int | None:
    """单调守卫：进度不得回退（前端进度条），并夹紧到 0–100。"""
    if progress is None:
        return None
    value = max(0, min(100, int(progress)))
    value = max(value, int(state.get("last") or 0))
    state["last"] = value
    return value


def _is_own_sandbox(path: Path, job_id: int) -> bool:
    """沙箱归属判定：必须在系统临时目录下、名字精确前缀匹配本 job。

    压测遗留目录（qre-worker-job7-* / job8-* 等）与他人进程产物因此永不被误删；
    临时目录之外的路径一律拒绝（防拼路径事故）。
    """
    try:
        resolved = Path(path).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
    except OSError:
        return False
    return resolved.parent == temp_root and resolved.name.startswith(
        f"qre-worker-job{job_id}-")


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
        max_heartbeat_failures: int = 3,
        status_seconds: float = DEFAULT_STATUS_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        worker_budget_gb: float | None = None,
    ) -> None:
        self.client = client
        self.runner = runner
        self.poll_seconds = poll_seconds
        self.heartbeat_seconds = heartbeat_seconds
        self.max_heartbeat_failures = max_heartbeat_failures
        self.status_seconds = status_seconds
        self._sleep = sleep
        self._stop = threading.Event()
        # R3 切片1：槽位实时状态表（线程安全），供 status 上报线程读取
        self._slot_lock = threading.Lock()
        self._slots: dict[str, dict[str, Any]] = {}
        # R3 切片2：期望配置比对——记录最近一次已提示的期望版本，避免每轮重复日志
        self._desired_logged_version: int | None = None
        # P0-10（35 号 §3.2）：worker 在途峰值预算记账——认领前原子预留，避免多个
        # 「尚未到峰值」的 heavy 同时放行（item3 峰值在认领后 40–70 分钟才出现）。
        # 默认 15.5GB = 23.5GiB 物理 − PG 峰值 5.4 − 系统 ~2.5；env 可覆盖。
        self.worker_budget_gb = (DEFAULT_WORKER_BUDGET_GB if worker_budget_gb is None
                                 else float(worker_budget_gb))
        self._ledger = BudgetLedger(self.worker_budget_gb)

    # --- R3 切片1：槽位状态跟踪 + 周期上报 ---

    def _slot_set(self, name: str, kind: str, busy: bool, job_id: int | None,
                  *, budget_gb: float | None = None, tier: str | None = None) -> None:
        """槽位状态更新。budget_gb/tier 仅在执行期间写入（P0-10 记账可见性）；
        缺键不写（条件键纪律：消费方按存在性判断，避免把空值当数据）。"""
        with self._slot_lock:
            entry: dict[str, Any] = {"name": name, "kind": kind, "busy": busy,
                                     "job_id": job_id}
            if budget_gb is not None:
                entry["budget_gb"] = budget_gb
            if tier is not None:
                entry["tier"] = tier
            self._slots[name] = entry

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

    _CONFIG_KEYS = ("light_slots", "heavy_slots", "light_min_avail_mb", "heavy_min_avail_mb")

    def _check_desired_config(self, desired: dict[str, Any] | None,
                              limits: dict[str, Any]) -> None:
        """R3 切片2：上报响应回带的期望配置与当前生效值比对，不一致记日志
        （同一 version 只提示一次；应用方式：本机执行 deploy/saas/worker-tune.sh）。"""
        if not desired:
            self._desired_logged_version = None
            return
        version = desired.get("version")
        diff = {k: (limits.get(k), desired.get(k))
                for k in self._CONFIG_KEYS
                if desired.get(k) is not None and limits.get(k) != desired.get(k)}
        if not diff:
            if self._desired_logged_version is not None:
                _log(f"期望配置 v{version} 已生效（与当前一致）")
                self._desired_logged_version = None
            return
        if version != self._desired_logged_version:
            detail = "，".join(f"{k}: 当前 {cur} → 期望 {want}" for k, (cur, want) in diff.items())
            _log(f"期望配置 v{version} 待应用（{detail}）；"
                 "本机执行 deploy/saas/worker-tune.sh 后重启 worker 生效")
            self._desired_logged_version = version

    def report_status_once(self, limits: dict[str, Any],
                           mem_fn: Callable[[], float] | None = None) -> bool:
        """上报一次状态；失败仅记日志返回 False，不抛异常。"""
        try:
            resp = self.client.report_status(self.build_status_payload(limits, mem_fn))
            self._check_desired_config((resp or {}).get("desired_config"), limits)
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

        P0-9（CR-2026-11-03）：沙箱目录由 daemon 自建并透传 runner（§8.7 归属
        明确）；心跳携带 progress（§8.11）；终态后按归属判定清理沙箱（§8.7）。
        """
        job_id = job["id"]
        done_event = threading.Event()
        canceled = threading.Event()
        cancel_state: dict[str, Any] = {"reported": False}
        progress_state: dict[str, Any] = {"last": 0}
        # §8.7：沙箱目录 daemon 自建（mkdtemp 归属本进程），终态后可安全清理；
        # 不接受 work_base 的 runner（测试注入）忽略它，目录保持为空并同样受清理管辖。
        work_base = Path(tempfile.mkdtemp(prefix=f"qre-worker-job{job_id}-"))
        if runner is None:
            base_runner = self.runner
            if _accepts_work_base(base_runner):
                run_fn: Callable[..., dict[str, Any]] = (
                    lambda j, _ev: base_runner(j, work_base=work_base))  # noqa: E731
            else:
                run_fn = lambda j, _ev: base_runner(j)  # noqa: E731
        else:
            run_fn = runner
        pass_work_base = _accepts_work_base(run_fn)

        def _beat_once() -> dict[str, Any]:
            progress, message = _read_progress(work_base)
            resp = self.client.heartbeat(
                job_id, progress=_clamp_progress(progress, progress_state),
                message=message)
            if resp.get("cancel_requested") and not canceled.is_set():
                canceled.set()
                _log(f"job {job_id} 收到取消标记，上报 canceled 并丢弃结果")
                try:
                    self.client.fail(job_id, "用户取消", error_class="canceled")
                    cancel_state["reported"] = True
                except Exception as exc:
                    _log(f"job {job_id} canceled 上报失败（{exc}）")
            return resp

        def _heartbeat_loop() -> None:
            failures = 0
            # 启动即报一次（§8.11）：leased → running 立即生效，并带上初始进度
            try:
                _beat_once()
            except Exception as exc:
                _log(f"job {job_id} 首次 heartbeat 失败（{exc}），继续执行")
            while not done_event.wait(self.heartbeat_seconds):
                try:
                    _beat_once()
                    failures = 0
                except Exception as exc:
                    # 单次失败可能是网络抖动，继续执行；连续失败达到阈值说明
                    # lease 已丢失（任务不存在/非运行中/leased_by 不匹配——服务端
                    # 已把任务标记过期），继续跑只是白费资源（job 54 白跑 25 分钟），
                    # 置 canceled 终止子进程并释放槽位；结果本来也回传不上去，
                    # 由云端按租约过期重排。
                    failures += 1
                    if failures >= self.max_heartbeat_failures:
                        if not canceled.is_set():
                            canceled.set()
                            _log(
                                f"job {job_id} heartbeat 连续 {failures} 次失败（{exc}），"
                                "判定 lease 丢失，终止执行并释放槽位"
                            )
                        return
                    _log(f"job {job_id} heartbeat 失败（{exc}），第 {failures} 次，继续执行")

        hb = threading.Thread(target=_heartbeat_loop, daemon=True)
        hb.start()
        final_status = "unknown"
        cloud_complete = False
        payload = None
        failure_run_id = None
        try:
            try:
                if pass_work_base:
                    payload = run_fn(job, canceled, work_base=work_base)
                else:
                    payload = run_fn(job, canceled)
            except Exception as exc:
                failure_run_id = getattr(exc, "run_id", None)
                if canceled.is_set():
                    # 用户取消且已上报 → canceled 终态；lease 丢失未上报 → unknown
                    final_status = "canceled" if cancel_state.get("reported") else "unknown"
                    return
                _log(f"job {job_id} 执行失败：{exc}")
                try:
                    resp = self.client.fail(job_id, str(exc))
                    final_status = str((resp or {}).get("status") or "failed")
                except Exception as report_exc:
                    _log(f"job {job_id} failed 回传失败（{report_exc}），等租约过期重排")
                    final_status = "unknown"
                return
            finally:
                done_event.set()
            if canceled.is_set():
                final_status = "canceled" if cancel_state.get("reported") else "unknown"
                return  # 已上报 canceled，丢弃结果
            final_status, cloud_complete = self._report_results(
                job_id, payload, progress_state=progress_state)
        finally:
            # §8.7：只在 completed 且云端完整副本确认时清理；其余一律保留本地
            # （上传失败/上传关闭/截断/取消/未知——本地可能是唯一完整副本）
            self._cleanup_work_base(job_id, work_base, final_status,
                                    cloud_complete=cloud_complete)
            if job.get("kind") == "smoke" and final_status in {
                    "completed", "failed", "canceled", "cancelled", "expired"}:
                from quant_research_engine.gui.engine import RUNS_DIR
                from quant_research_engine.smoke_cleanup import cleanup_smoke_run
                summary = (payload or {}).get("summary") or {}
                smoke_run_id = summary.get("run_id") or failure_run_id
                if smoke_run_id:
                    cleanup_smoke_run(str(smoke_run_id), runs_dir=RUNS_DIR)
                if _is_own_sandbox(work_base, job_id):
                    shutil.rmtree(work_base, ignore_errors=True)

    def _cleanup_work_base(self, job_id: int, work_base: Path | None, status: str,
                           *, cloud_complete: bool = False) -> None:
        """清理本进程自建沙箱（P0-9 §8.7，主 Agent Required Fix 修正）。

        唯一删除前提：``status == 'completed'`` **且** ``cloud_complete``
        （应传 blob 已确认完整回传、无截断）。failed/queued/unknown/canceled/
        expired 与云端副本未确认（上传关闭/截断）一律保留——本地沙箱可能是
        唯一完整副本（压测归档保护）；再叠加目录归属判定（防误删他人/遗留产物）。
        """
        if status != "completed" or not cloud_complete:
            _log(f"job {job_id} 云端完整副本未确认（status={status}），"
                 f"保留沙箱目录 {work_base}")
            return
        if work_base is None or not _is_own_sandbox(work_base, job_id):
            _log(f"job {job_id} 沙箱目录归属不匹配，跳过清理：{work_base}")
            return
        shutil.rmtree(work_base, ignore_errors=True)
        _log(f"job {job_id} 沙箱目录已清理：{work_base}")

    def _beat(self, job_id: int, progress: int | None, message: str | None,
              progress_state: dict[str, Any] | None = None) -> None:
        """尽力进度心跳（§8.11）：失败仅记日志，不中断回传主流程。"""
        if progress_state is not None:
            progress = _clamp_progress(progress, progress_state)
        heartbeat = getattr(self.client, "heartbeat", None)
        if heartbeat is None:
            return
        try:
            heartbeat(job_id, progress=progress, message=message)
        except Exception as exc:
            _log(f"job {job_id} 进度心跳失败（{exc}），继续回传")

    def _report_results(self, job_id: int, payload: dict[str, Any],
                        *, progress_state: dict[str, Any] | None = None) -> tuple[str, bool]:
        """两步回传（17 协议 §3.3）：meta → files；失败落终态（P0-9）。

        返回 ``(终态, 云端完整副本已确认)``。daemon 据此决定是否清理沙箱目录：
        **只有 completed 且应传 blob 已确认完整回传（上传开关开、全部批次
        completed、result_files 未截断/无缺失）才确认**——上传开关关闭时
        blob 从未上云，completed 也不确认（主 Agent Required Fix，2026-11-03）。
        """
        if not _upload_files_enabled():
            payload = {**payload, "files": []}  # 不上传则不报清单，云端直接 completed
        try:
            self._beat(job_id, _PROGRESS_UPLOADING, "计算完成，产物回传中", progress_state)
            meta = self.client.report_result(job_id, payload)
            upload_token = meta.get("upload_token")
            files = payload.get("files") or []
            cloud_complete = False
            if upload_token and files and _upload_files_enabled():
                blobs = {}
                for f in files:
                    blobs[f["name"]] = Path(f["path"]).read_bytes()
                total = len(blobs)
                done = 0

                def _on_batch(batch: dict[str, bytes], resp: dict[str, Any]) -> None:
                    nonlocal done
                    done += len(batch)
                    # 95→99 ramp：既报真实回传进度，也续租（上传阶段停发心跳会被
                    # 30 分钟上传硬超时杀；长回传更需要）
                    self._beat(job_id,
                               min(99, _PROGRESS_UPLOADING + round(4 * done / max(total, 1))),
                               f"产物回传中 {done}/{total} 文件", progress_state)

                resp = self._upload_with_retry(job_id, upload_token, blobs, _on_batch)
                if resp.get("status") != "completed":
                    raise CloudError(f"分片上传未确认完成：{resp}", None)
                cloud_complete = _cloud_copy_complete(payload)
            # 终态进度（100/结果已回传）由服务端在置 completed 的同一事务落定
            # （P0-9 Required Fix，job 212）：completed 后 heartbeat 会被拒，
            # 这里不再发事后心跳。
            _log(f"job {job_id} done，已回传")
            return "completed", cloud_complete
        except Exception as exc:
            # P0-9（CR-2026-11-03）：回传失败必须落终态。此前只打日志「等租约过期
            # 重排」，job 会滞留 uploading，随后被 _reap_expired 重排回 queued，
            # 同一份已算完的结果会**再算一遍**（压测实测：42 分钟 / 6GB 白跑）。
            status = getattr(exc, "status", None)
            # 4xx 归入 result_upload_http_<code>（云端已登记这些分类，均不可重试）；
            # 5xx 与传输错误归入 result_upload_error（可重试，值得再试一次）。
            if isinstance(status, int) and status in _UPLOAD_HTTP_CLASSES:
                error_class = f"result_upload_http_{status}"
            else:
                error_class = "result_upload_error"
            _log(f"job {job_id} 回传失败（{error_class}: {exc}），置 failed 避免整单重算")
            try:
                resp = self.client.fail(job_id, str(exc), error_class=error_class)
                return str((resp or {}).get("status") or "failed"), False
            except Exception as report_exc:
                _log(f"job {job_id} failed 上报也失败（{report_exc}），仍等租约过期兜底")
                return "unknown", False

    def _upload_with_retry(self, job_id: int, upload_token: str,
                           blobs: dict[str, bytes],
                           on_batch) -> dict[str, Any]:
        """分片上传带有限重试：仅对 429/502/503/504 重发（见模块常量）。

        为什么安全：服务端按 upload_token 幂等、已落盘文件不进 remaining，
        `client.upload_files()` 整轮重发等价断点续传，不会产生重复产物。
        为什么必要：2026-11-09 CF-083 的 429 被当终态，白丢一次完整计算（135714 笔）。
        非可重试状态（400/401/403/404/409/413/422 与协议错误）立即抛出，交由
        既有 `_UPLOAD_HTTP_CLASSES` 分类落终态，不做无意义重试。
        """
        attempts = len(_UPLOAD_RETRY_BACKOFF_S) + 1
        for index in range(1, attempts + 1):
            try:
                return self.client.upload_files(job_id, upload_token, blobs,
                                                on_batch=on_batch)
            except Exception as exc:
                status = getattr(exc, "status", None)
                retryable = isinstance(status, int) and status in _UPLOAD_RETRY_STATUSES
                if not retryable or index == attempts:
                    raise
                backoff = _UPLOAD_RETRY_BACKOFF_S[index - 1]
                _log(f"job {job_id} 回传遇 HTTP {status}（可重试，第 {index}/{attempts - 1} 次），"
                     f"{backoff:.0f}s 后重发（服务端按 upload_token 幂等，已落盘文件跳过）")
                self._sleep(backoff)
        raise AssertionError("unreachable: 重试循环必然 return 或 raise")

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
            "worker_budget_gb": self.worker_budget_gb,
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
        """单个槽位线程：内存闸门 → 在途预算预留 → claim → 子进程执行 → 循环；
        收到 stop 后跑完当前任务再退出（优雅退出语义与单槽一致）。

        P0-10（35 号 §3.2）：认领前按槽位类型的**最坏假设预算**原子预留
        （重槽按未知全市场 13.97GB、轻槽 1.5GB）——item3 级峰值出现在认领后
        40–70 分钟的聚合/报告段，认领瞬间的 MemAvailable 闸门看不见它；预留后
        才 claim，两个重槽不会同时放行。claim 到任务后按真实档位定账
        （重槽领到轻任务时释放多预留）。
        """
        from quant_research_engine.worker.slots import execute_job_subprocess

        def _runner(j: dict[str, Any], ev: threading.Event,
                    work_base: Path | None = None) -> dict[str, Any]:
            return execute_job_subprocess(j, is_canceled=ev.is_set, work_base=work_base)

        kind = "light" if classes == "light" else "heavy"
        assumed_gb = ADMISSION_BUDGET_GB[kind]
        _log(f"[{slot_name}] 槽位启动（classes={classes}，内存闸门 {min_avail_mb:.0f}MB，"
             f"准入预算 {assumed_gb:.2f}GB/任务，worker 在途预算 "
             f"{self.worker_budget_gb:.1f}GB）")
        self._slot_set(slot_name, kind, False, None)
        while not self._stop.is_set():
            avail = mem_fn()
            if avail < min_avail_mb:
                _log(f"[{slot_name}] 可用内存 {avail:.0f}MB < 闸门 {min_avail_mb:.0f}MB，暂缓领取")
                self._sleep(self.poll_seconds)
                continue
            # 在途预算闸门：原子预留成功才 claim（失败仅暂缓，不领任务）
            if not self._ledger.try_reserve(slot_name, assumed_gb):
                _log(f"[{slot_name}] 在途预算不足（已用 {self._ledger.inflight_gb():.2f}GB + "
                     f"本任务 {assumed_gb:.2f}GB > worker 预算 "
                     f"{self.worker_budget_gb:.1f}GB），暂缓领取")
                self._sleep(self.poll_seconds)
                continue
            # 日更排他锁存在时不认领新全量；认领后共享锁持有到执行和回传结束。
            refresh_context = None
            if kind == "heavy":
                from quant_research_engine.scheduling import RefreshInProgress, refresh_lock
                refresh_context = refresh_lock(exclusive=False, blocking=False)
                try:
                    refresh_context.__enter__()
                except RefreshInProgress:
                    self._ledger.release(slot_name)
                    _log(f"[{slot_name}] 行情/因子日更进行中，暂缓领取全量任务")
                    self._sleep(self.poll_seconds)
                    continue
            try:
                job = self.client.claim(wait_seconds=self.poll_seconds, classes=classes)
            except CloudError as exc:
                if refresh_context is not None:
                    refresh_context.__exit__(None, None, None)
                self._ledger.release(slot_name)
                _log(f"[{slot_name}] claim 失败：{exc}")
                self._sleep(self.poll_seconds)
                continue
            if not job:
                if refresh_context is not None:
                    refresh_context.__exit__(None, None, None)
                self._ledger.release(slot_name)
                continue
            # claim 成功：按任务真实档位定账（重槽领到轻任务时释放多预留）
            tier = job_tier(job)
            budget_gb = ADMISSION_BUDGET_GB[tier]
            self._ledger.commit(slot_name, budget_gb)
            _log(f"[{slot_name}] claimed job {job['id']}（kind={job.get('kind')}，"
                 f"档位 {tier}，准入预算 {budget_gb:.2f}GB）")
            self._slot_set(slot_name, kind, True, job["id"],
                           budget_gb=budget_gb, tier=tier)
            try:
                self._run_job(job, runner=_runner)
            finally:
                if refresh_context is not None:
                    refresh_context.__exit__(None, None, None)
                self._slot_set(slot_name, kind, False, None)
                self._ledger.release(slot_name)
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
            # P0-10：在途预算上限随状态上报（管理台可见，与准入闸门同源）
            "worker_budget_gb": self.worker_budget_gb,
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
