"""维护区（QRE-ADMIN-MANAGE-001）：outputs/backtests 批次清理。

仅允许删除 outputs 符号链接解析后的 backtests 下的单级子目录；
refresh 等系统目录受保护不可删；路径白名单校验防越界。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from quant_research_engine.gui.admin import _cached

DEFAULT_BACKTESTS_DIR = Path("outputs/backtests")

# 系统目录：不可删除（refresh 批次、增量检查点等）
PROTECTED_BATCHES = frozenset({"refresh", "incremental"})

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _du_bytes(path: Path) -> int | None:
    try:
        proc = subprocess.run(["du", "-sb", str(path)], capture_output=True, text=True, timeout=120)
        if proc.returncode == 0:
            return int(proc.stdout.split()[0])
    except Exception:
        pass
    return None


def list_batches(backtests_dir: Path | None = None) -> dict[str, Any]:
    """列出批次目录：名称、修改时间、du 体积、策略目录数、是否受保护。"""
    root = (backtests_dir or DEFAULT_BACKTESTS_DIR).resolve()

    def _produce() -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if not root.is_dir():
            return result
        for p in sorted(root.iterdir()):
            if not p.is_dir():
                continue
            result.append(
                {
                    "name": p.name,
                    "mtime": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
                    "size_bytes": _du_bytes(p),
                    "strategy_count": sum(1 for c in p.iterdir() if c.is_dir()),
                    "protected": p.name in PROTECTED_BATCHES,
                }
            )
        return result

    batches = _cached(f"maintenance_batches:{root}", _produce)
    return {
        "backtests_dir": str(root),
        "batches": batches,
        "total_size_bytes": sum(b["size_bytes"] or 0 for b in batches if not b["protected"]),
    }


def delete_batches(
    names: list[str],
    backtests_dir: Path | None = None,
) -> dict[str, Any]:
    """删除所选批次目录（路径白名单校验）。返回逐项结果。"""
    root = (backtests_dir or DEFAULT_BACKTESTS_DIR).resolve()
    deleted: list[str] = []
    errors: list[str] = []
    for name in names:
        name = (name or "").strip()
        if not _NAME_PATTERN.match(name) or "/" in name or ".." in name:
            errors.append(f"非法批次名: {name!r}")
            continue
        if name in PROTECTED_BATCHES:
            errors.append(f"系统目录受保护，不可删除: {name}")
            continue
        target = (root / name).resolve()
        # 白名单：必须恰好是 root 的直接子目录
        if target.parent != root or not target.is_dir():
            errors.append(f"批次不存在或越界: {name}")
            continue
        shutil.rmtree(target)
        deleted.append(name)
    # 清缓存使列表即时刷新
    from quant_research_engine.gui import admin as _admin

    _admin._cache.pop(f"maintenance_batches:{root}", None)
    for key in [k for k in _admin._cache if k.startswith("overview_backtests:")]:
        _admin._cache.pop(key, None)
    return {"deleted": deleted, "errors": errors}
