"""新因子申请：联动 indicators_tushare（QRE-GUI-FACTOR-WIZARD-001）。

流程：备份 config/factors.yaml → 追加 entry → 后台线程跑
validate → plan → sample backfill（--execute，sample 级允许自动）→
状态 awaiting_execute_confirmation → 人工确认 POST execute → 全量 backfill。
任一步失败即停、中文报错、自动回滚 factors.yaml 备份。全局单任务锁。

repo 路径：env QRE_INDICATORS_REPO，默认 <项目根>/../indicators_tushare。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from quant_research_engine.gui.engine import GUI_BASE_DIR, _run_id

ENV_INDICATORS_REPO = "QRE_INDICATORS_REPO"

FACTOR_ADMIN_DIR = GUI_BASE_DIR / "factor-admin"

SAMPLE_VALIDATE_CMD = ["uv", "run", "python", "run_factor_admin.py", "validate", "--codes", "000001.SZ", "--sample-rows", "800"]
PLAN_CMD = ["uv", "run", "python", "run_factor_admin.py", "plan", "--baseline-ref", "HEAD"]
SAMPLE_BACKFILL_CMD = ["uv", "run", "python", "run_factor_admin.py", "backfill", "--baseline-ref", "HEAD", "--sample-codes", "000001.SZ", "--max-workers", "4", "--execute"]
FULL_BACKFILL_CMD = ["uv", "run", "python", "run_factor_admin.py", "backfill", "--baseline-ref", "HEAD", "--max-workers", "4", "--execute"]

# (step_name, cmd)；sample 链依次执行
SAMPLE_STEPS = [
    ("validate", SAMPLE_VALIDATE_CMD),
    ("plan", PLAN_CMD),
    ("sample_backfill", SAMPLE_BACKFILL_CMD),
]

# 全局单因子任务锁
_job_lock = threading.Lock()
_active_job_id: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def indicators_repo(env: dict[str, str] | None = None) -> Path:
    env = env if env is not None else os.environ
    configured = (env.get(ENV_INDICATORS_REPO) or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    # <workspace>/quant-research-engine-dual-agent-lab/src/quant_research_engine/gui/factor_admin.py
    # → <workspace>/indicators_tushare
    return Path(__file__).resolve().parents[4] / "indicators_tushare"


def config_path_for(repo: Path) -> Path:
    return repo / "config" / "factors.yaml"


# ---------------------------------------------------------------------------
# config/factors.yaml 读取与追加
# ---------------------------------------------------------------------------


def read_indicators(config_path: Path) -> dict[str, list[str]]:
    """返回已配置指标名去重列表 + 出现过的 price column 列表。"""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    entries = (data or {}).get("factors") or []
    names = sorted({str(e.get("name")) for e in entries if e.get("name")})
    columns = sorted({str(e.get("column")) for e in entries if e.get("column")})
    return {"names": names, "columns": columns}


def parse_periods(text: str) -> list[int]:
    """解析逗号分隔的正整数周期列表；格式错误抛 ValueError（中文）。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("周期不能为空：请输入逗号分隔的正整数，如 5,10,20")
    periods: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not re.fullmatch(r"\d+", part):
            raise ValueError(f"周期格式错误: '{part}'（应为逗号分隔的正整数，如 5,10,20）")
        value = int(part)
        if value <= 0:
            raise ValueError("周期必须是正整数")
        periods.append(value)
    return sorted(set(periods))


def _category_for_name(config_path: Path, name: str) -> str:
    """从现有配置中取同名指标的 category（指标名下拉即来源于已配置指标）。"""
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    for entry in (data or {}).get("factors") or []:
        if entry.get("name") == name and entry.get("category"):
            return str(entry["category"])
    raise ValueError(f"指标 '{name}' 不在 indicators_tushare 已配置列表中，无法确定类别")


def append_factor_entry(
    config_path: Path,
    *,
    name: str,
    column: str,
    periods: list[int],
    now: datetime | None = None,
) -> Path:
    """备份 factors.yaml 并追加新 entry（跟随文件现有 YAML 风格）。返回备份路径。"""
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")
    category = _category_for_name(config_path, name)
    stamp = (now or datetime.now(tz=timezone.utc)).strftime("%Y%m%dT%H%M%S")
    backup_path = config_path.with_suffix(config_path.suffix + f".bak-{stamp}")
    shutil.copy2(config_path, backup_path)

    periods_text = ", ".join(str(p) for p in periods)
    block = (
        f"\n  - name: {name}\n"
        f"    category: {category}\n"
        f"    column: {column}\n"
        f"    periods: [{periods_text}]\n"
    )
    with config_path.open("a", encoding="utf-8") as fh:
        fh.write(block)
    return backup_path


def rollback_config(config_path: Path, backup_path: Path) -> None:
    """从备份恢复 factors.yaml。"""
    if backup_path.exists():
        shutil.copy2(backup_path, config_path)


# ---------------------------------------------------------------------------
# 任务状态机
# ---------------------------------------------------------------------------


def _job_dir(job_id: str) -> Path:
    return FACTOR_ADMIN_DIR / job_id


def _write_status(job_dir: Path, record: dict[str, Any]) -> None:
    record["updated_at"] = _now_iso()
    job_dir.mkdir(parents=True, exist_ok=True)
    (job_dir / "status.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def _append_log(job_dir: Path, text: str) -> None:
    job_dir.mkdir(parents=True, exist_ok=True)
    with (job_dir / "steps.log").open("a", encoding="utf-8") as fh:
        fh.write(text)


def get_job(job_id: str) -> dict[str, Any] | None:
    status_path = _job_dir(job_id) / "status.json"
    if not status_path.exists():
        return None
    try:
        record = json.loads(status_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    log_path = _job_dir(job_id) / "steps.log"
    if log_path.exists():
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        record["log_tail"] = "\n".join(lines[-50:])
    return record


def active_job_id() -> str | None:
    with _job_lock:
        return _active_job_id


def _set_active(job_id: str | None) -> None:
    global _active_job_id
    with _job_lock:
        _active_job_id = job_id


def _default_step_runner(cmd: list[str], cwd: Path, job_dir: Path) -> int:
    """Run one admin step, streaming output into steps.log. Returns returncode."""
    _append_log(job_dir, f"\n$ {' '.join(cmd)}\n")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=7200,
        )
    except Exception as exc:
        _append_log(job_dir, f"执行异常: {exc}\n")
        return 1
    if proc.stdout:
        _append_log(job_dir, proc.stdout[-8000:] + ("\n" if not proc.stdout.endswith("\n") else ""))
    if proc.stderr:
        _append_log(job_dir, "[stderr] " + proc.stderr[-4000:] + ("\n" if not proc.stderr.endswith("\n") else ""))
    _append_log(job_dir, f"exit_code={proc.returncode}\n")
    return proc.returncode


def start_factor_job(
    *,
    name: str,
    column: str,
    periods: list[int],
    repo: Path | None = None,
    step_runner: Callable[[list[str], Path, Path], int] | None = None,
) -> dict[str, Any]:
    """创建并启动 sample 链任务（后台线程）。已有任务在跑时抛 RuntimeError。"""
    repo = repo or indicators_repo()
    config_path = config_path_for(repo)
    runner = step_runner or _default_step_runner

    with _job_lock:
        global _active_job_id
        if _active_job_id is not None:
            raise RuntimeError("已有一个因子任务在执行，请等待其完成后再提交")
        job_id = _run_id()
        _active_job_id = job_id

    job_dir = _job_dir(job_id)
    record: dict[str, Any] = {
        "job_id": job_id,
        "name": name,
        "column": column,
        "periods": periods,
        "repo": str(repo),
        "status": "running",
        "step": "backup",
        "error": None,
        "created_at": _now_iso(),
    }
    _write_status(job_dir, record)

    backup_path: Path | None = None
    try:
        backup_path = append_factor_entry(config_path, name=name, column=column, periods=periods)
        _append_log(job_dir, f"已备份 {config_path} -> {backup_path}\n追加 entry: name={name} column={column} periods={periods}\n")
    except Exception as exc:
        record["status"] = "failed"
        record["error"] = f"写入因子配置失败：{exc}"
        _write_status(job_dir, record)
        _append_log(job_dir, record["error"] + "\n")
        _set_active(None)
        return record

    thread = threading.Thread(
        target=_run_sample_chain,
        args=(job_dir, record, repo, config_path, backup_path, runner),
        daemon=True,
    )
    thread.start()
    return record


def _run_sample_chain(
    job_dir: Path,
    record: dict[str, Any],
    repo: Path,
    config_path: Path,
    backup_path: Path,
    runner: Callable[[list[str], Path, Path], int],
) -> None:
    try:
        for step_name, cmd in SAMPLE_STEPS:
            record["step"] = step_name
            _write_status(job_dir, record)
            code = runner(cmd, repo, job_dir)
            if code != 0:
                record["status"] = "failed"
                record["error"] = f"步骤 {step_name} 失败（exit={code}），已回滚因子配置"
                rollback_config(config_path, backup_path)
                _append_log(job_dir, record["error"] + "\n")
                _write_status(job_dir, record)
                return
        record["status"] = "awaiting_execute_confirmation"
        record["step"] = "sample_done"
        _append_log(job_dir, "sample 链完成，等待人工确认全量回填\n")
        _write_status(job_dir, record)
    except Exception as exc:  # 防御：任何异常都要释放锁并留痕
        record["status"] = "failed"
        record["error"] = f"任务异常：{exc}，已回滚因子配置"
        rollback_config(config_path, backup_path)
        _append_log(job_dir, record["error"] + "\n")
        _write_status(job_dir, record)
    finally:
        _set_active(None)


def confirm_execute(
    job_id: str,
    *,
    step_runner: Callable[[list[str], Path, Path], int] | None = None,
) -> dict[str, Any]:
    """人工确认后执行全量回填。状态不是 awaiting_execute_confirmation 时抛 RuntimeError。"""
    record = get_job(job_id)
    if record is None:
        raise KeyError(f"任务不存在: {job_id}")
    if record["status"] != "awaiting_execute_confirmation":
        raise RuntimeError(f"任务当前状态为 {record['status']}，不能执行全量回填")

    repo = Path(record["repo"])
    runner = step_runner or _default_step_runner
    job_dir = _job_dir(job_id)

    with _job_lock:
        global _active_job_id
        if _active_job_id is not None:
            raise RuntimeError("已有一个因子任务在执行，请等待其完成后再确认")
        _active_job_id = job_id

    record["status"] = "running"
    record["step"] = "full_backfill"
    _write_status(job_dir, record)

    def _run() -> None:
        try:
            code = runner(FULL_BACKFILL_CMD, repo, job_dir)
            if code != 0:
                record["status"] = "failed"
                record["error"] = f"全量回填失败（exit={code}），配置保留在 factors.yaml 中（sample 已验证）"
            else:
                record["status"] = "completed"
                record["error"] = None
                _append_log(job_dir, "全量回填完成\n")
            _write_status(job_dir, record)
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"全量回填异常：{exc}"
            _append_log(job_dir, record["error"] + "\n")
            _write_status(job_dir, record)
        finally:
            _set_active(None)

    threading.Thread(target=_run, daemon=True).start()
    return record
