"""日更中心手动触发任务（QRE-ADMIN-CONSOLE-P3B-001）。

边界：只调各项目官方入口脚本（不经 sudo、不经 systemctl）；每条管线独立
单任务锁；后台线程跑 subprocess，输出落盘
outputs/gui-console/daily-jobs/<job_id>/{status.json,output.log}。
"""

from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.gui.engine import GUI_BASE_DIR, _run_id

UV_BIN = "/home/van/.local/bin/uv"
WORKSPACE = Path(__file__).resolve().parents[4]
QRE_ROOT = WORKSPACE / "quant-research-engine-dual-agent-lab"
QUANT_TS_DIR = WORKSPACE / "quant_ts"
INDICATORS_DIR = WORKSPACE / "indicators_tushare"

DAILY_JOBS_DIR = GUI_BASE_DIR / "daily-jobs"

PIPELINES: dict[str, dict[str, Any]] = {
    "quant-ts": {
        "label": "日线数据 quant_ts",
        "cmd": [UV_BIN, "run", "python", "sync_manager.py", "--mode", "daily"],
        "cwd": QUANT_TS_DIR,
        "unit": "quant-ts-daily.service",
        "log_dirs": [QUANT_TS_DIR / "logs"],
    },
    "indicators": {
        "label": "因子库 indicators_tushare",
        "cmd": [UV_BIN, "run", "python", "run_daily.py", "--max-workers", "4"],
        "cwd": INDICATORS_DIR,
        "unit": "indicators-tushare-daily.service",
        "log_dirs": [INDICATORS_DIR / "logs", INDICATORS_DIR / "repair_logs"],
    },
    "qre-refresh": {
        "label": "QRE 回测增量刷新",
        "cmd": [UV_BIN, "run", "python", "scripts/refresh_batch.py", "--jobs", "4"],
        "cwd": QRE_ROOT,
        "unit": "qre-refresh.service",
        "log_dirs": [],
    },
    "qre-barometer": {
        "label": "大盘风险风向标",
        "cmd": [UV_BIN, "run", "python", "-m", "quant_research_engine.risk.barometer_job"],
        "cwd": QRE_ROOT,
        "unit": "qre-barometer.service",
        "log_dirs": [],
    },
}

# 每条管线独立单任务锁
_pipeline_lock = threading.Lock()
_active_jobs: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def active_job(pipeline: str) -> str | None:
    with _pipeline_lock:
        return _active_jobs.get(pipeline)


def _write_status(job_dir: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = _now_iso()
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "status.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _append_log(job_dir: Path, text: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    with (job_dir / "output.log").open("a", encoding="utf-8") as fh:
        fh.write(text)


def get_daily_job(job_id: str) -> dict[str, Any] | None:
    status_path = DAILY_JOBS_DIR / job_id / "status.json"
    if not status_path.exists():
        return None
    try:
        record = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    log_path = DAILY_JOBS_DIR / job_id / "output.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        record["log_tail"] = "\n".join(lines[-50:])
    return record


def _default_runner(cmd: list[str], cwd: Path, job_dir: Path) -> int:
    _append_log(job_dir, f"$ {' '.join(cmd)}\n(cwd: {cwd})\n\n")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=6 * 3600,
        )
    except Exception as exc:
        _append_log(job_dir, f"执行异常: {exc}\n")
        return 1
    if proc.stdout:
        _append_log(job_dir, proc.stdout[-20000:] + ("" if proc.stdout.endswith("\n") else "\n"))
    if proc.stderr:
        _append_log(job_dir, "[stderr] " + proc.stderr[-8000:] + ("" if proc.stderr.endswith("\n") else "\n"))
    _append_log(job_dir, f"\nexit_code={proc.returncode}\n")
    return proc.returncode


def start_daily_job(
    pipeline: str,
    *,
    runner: Callable[[list[str], Path, Path], int] | None = None,
) -> dict[str, Any]:
    """启动一条管线的手动运行（后台线程）。重入抛 RuntimeError（路由层转 409）。"""
    spec = PIPELINES.get(pipeline)
    if spec is None:
        raise KeyError(f"未知管线: {pipeline}")
    return start_script_job(
        lock_key=pipeline,
        label=spec["label"],
        cmd=list(spec["cmd"]),
        cwd=Path(spec["cwd"]),
        runner=runner,
    )


def start_script_job(
    *,
    lock_key: str,
    label: str,
    cmd: list[str],
    cwd: Path,
    runner: Callable[[list[str], Path, Path], int] | None = None,
) -> dict[str, Any]:
    """通用官方脚本任务：指定锁键（可与管线锁共用）+ 后台线程 + 落盘日志。

    同一 lock_key 重入抛 RuntimeError（路由层转 409）。
    """
    with _pipeline_lock:
        if lock_key in _active_jobs:
            raise RuntimeError(f"「{label}」已有任务在运行，请等待完成后再触发")
        job_id = _run_id()
        _active_jobs[lock_key] = job_id

    job_dir = DAILY_JOBS_DIR / job_id
    record: dict[str, Any] = {
        "job_id": job_id,
        "pipeline": lock_key,
        "label": label,
        "cmd": " ".join(cmd),
        "cwd": str(cwd),
        "status": "running",
        "error": None,
        "created_at": _now_iso(),
    }
    _write_status(job_dir, record)

    def _run() -> None:
        run = runner or _default_runner
        try:
            code = run(list(cmd), cwd, job_dir)
            record["status"] = "completed" if code == 0 else "failed"
            if code != 0:
                record["error"] = f"脚本退出码 {code}（详见日志）"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"任务异常：{exc}"
            _append_log(job_dir, record["error"] + "\n")
        finally:
            _write_status(job_dir, record)
            with _pipeline_lock:
                _active_jobs.pop(lock_key, None)

    threading.Thread(target=_run, daemon=True).start()
    return record


# ---------------------------------------------------------------------------
# 最近日志（只读）
# ---------------------------------------------------------------------------


def journalctl_tail(
    unit: str,
    *,
    lines: int = 50,
    runner: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any]:
    """journalctl -u <unit> -n 50 --no-pager（读取不需 root）。

    失败时回退读项目 logs 目录最新文件 tail。返回 {"source", "text"}。
    """
    run = runner or subprocess.run
    try:
        proc = run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return {"source": "journalctl", "text": proc.stdout}
    except Exception:
        pass
    return _logfile_tail(unit, lines=lines)


def _logfile_tail(unit: str, *, lines: int = 50) -> dict[str, Any]:
    spec = next((s for s in PIPELINES.values() if s["unit"] == unit), None)
    log_dirs = spec["log_dirs"] if spec else []
    candidates: list[Path] = []
    for log_dir in log_dirs:
        if log_dir.is_dir():
            candidates.extend(log_dir.glob("*.log"))
    if not candidates:
        return {"source": "error", "text": f"journalctl 不可用，且未找到 {unit} 的项目日志文件"}
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    try:
        tail = latest.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
    except OSError as exc:
        return {"source": "error", "text": f"读取日志失败：{exc}"}
    return {"source": f"logfile:{latest.name}", "text": "\n".join(tail)}
