"""终态冒烟任务产物清理；策略与结果摘要不在删除范围。"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

_RUN_ID = re.compile(r"^[0-9A-Za-z_-]+$")
_TERMINAL = {"completed", "failed", "canceled", "cancelled", "expired"}


def cleanup_smoke_run(run_id: str, *, runs_dir: str | Path) -> bool:
    """删除终态冒烟 run 及其受管输出；正式、运行中或路径异常一律保留。"""
    if not _RUN_ID.fullmatch(str(run_id)):
        return False
    root = Path(runs_dir).resolve()
    run_dir = root / str(run_id)
    status_path = run_dir / "status.json"
    try:
        record: dict[str, Any] = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if record.get("status") not in _TERMINAL:
        return False
    if not record.get("precheck") and record.get("purpose") != "smoke":
        return False
    output = record.get("output_dir")
    if output:
        output_path = Path(str(output)).resolve()
        # 只允许 run 内部产物，或以 run_id 命名的独立输出目录。
        if output_path != run_dir and run_dir not in output_path.parents and output_path.name != run_id:
            return False
        if output_path != run_dir and output_path.exists():
            shutil.rmtree(output_path)
    if run_dir.exists():
        shutil.rmtree(run_dir)
    return True


def cleanup_smoke_upload(upload_root: str | Path, job_id: int, *, kind: str) -> bool:
    """云端只删除固定 job_<id> 目录，且仅 smoke 终态接收后调用。"""
    if kind != "smoke":
        return False
    job_dir = Path(upload_root) / f"job_{int(job_id)}"
    if not job_dir.is_dir():
        return True
    shutil.rmtree(job_dir)
    return True
