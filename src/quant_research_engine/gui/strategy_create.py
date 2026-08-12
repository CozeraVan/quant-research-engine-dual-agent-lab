"""GUI 策略创建闭环（P1）：查重 → 沙箱 → 冒烟 → 用户确认晋升 → catalog。

沙箱目录 ``outputs/sandbox/strategies/`` 独立于 ``strategies/catalog``——
refresh 日更只扫描 catalog，因此沙箱策略天然不会被日更拾取，无需额外隔离机制。
冒烟结果以 sidecar ``<name>.smoke.json`` 记录（与沙箱 YAML 同目录）。

目录均可注入（catalog_dir / sandbox_dir），便于测试。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quant_research_engine.gui.engine import validate_yaml
from quant_research_engine.gui.refresh_registry import CATALOG_DIR

DEFAULT_SANDBOX_DIR = Path("outputs/sandbox/strategies")

# catalog 类别白名单（与 strategies/catalog 下目录一一对应）
CATALOG_CATEGORIES = (
    "breakout",
    "composite",
    "cross_sectional",
    "kline_pattern",
    "mean_reversion",
    "price_volume",
    "trend_following",
)

# 冒烟测试默认标的（流动性好的大盘股）与窗口
SMOKE_DEFAULT_CODE = "600519.SH"
SMOKE_WINDOW_DAYS = 180


def _safe_name(name: str) -> str:
    """文件名安全的策略名（防路径穿越）。"""
    return name.replace("/", "_").replace("\\", "_").strip()


def _read_experiment_name(path: Path) -> str | None:
    """从 YAML 文件读 experiment.name；解析失败返回 None。"""
    try:
        import yaml as _yaml

        parsed = _yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    experiment = parsed.get("experiment")
    if not isinstance(experiment, dict):
        return None
    name = experiment.get("name")
    return str(name) if name else None


def parse_spec_name(yaml_text: str) -> str | None:
    """从 YAML 文本提取 experiment.name。"""
    try:
        import yaml as _yaml

        parsed = _yaml.safe_load(yaml_text)
    except Exception:
        return None
    if not isinstance(parsed, dict):
        return None
    experiment = parsed.get("experiment")
    if not isinstance(experiment, dict):
        return None
    name = experiment.get("name")
    return str(name).strip() if name else None


# ---------------------------------------------------------------------------
# 查重
# ---------------------------------------------------------------------------


def check_strategy_duplicate(
    name: str,
    *,
    catalog_dir: Path | None = None,
    sandbox_dir: Path | None = None,
    scan_sandbox: bool = True,
) -> str | None:
    """扫描 catalog 与沙箱，按 experiment.name 查重。

    命中时返回中文冲突描述（含来源与文件路径），否则返回 None。
    ``scan_sandbox=False`` 时只查 catalog（晋升时避免命中沙箱中的自身）。
    """
    name = (name or "").strip()
    if not name:
        return None
    catalog_dir = catalog_dir or CATALOG_DIR
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR

    if catalog_dir.exists():
        for path in sorted(catalog_dir.rglob("*.yaml")):
            if _read_experiment_name(path) == name:
                category = path.parent.name
                return f"catalog 已存在同名策略（类别 {category}）: {path}"
    if scan_sandbox and sandbox_dir.exists():
        for path in sorted(sandbox_dir.glob("*.yaml")):
            if _read_experiment_name(path) == name:
                return f"沙箱已存在同名策略: {path}"
    return None


# ---------------------------------------------------------------------------
# 沙箱读写
# ---------------------------------------------------------------------------


def sandbox_path(name: str, sandbox_dir: Path | None = None) -> Path:
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    return sandbox_dir / f"{_safe_name(name)}.yaml"


def smoke_sidecar_path(name: str, sandbox_dir: Path | None = None) -> Path:
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    return sandbox_dir / f"{_safe_name(name)}.smoke.json"


def save_to_sandbox(
    yaml_text: str,
    *,
    catalog_dir: Path | None = None,
    sandbox_dir: Path | None = None,
) -> dict[str, Any]:
    """校验 → 查重 → 落盘沙箱。返回 {"ok", "name", "path"} 或 {"ok": False, "code", "error"}。"""
    validation = validate_yaml(yaml_text)
    if not validation["valid"]:
        return {"ok": False, "code": "invalid_yaml", "error": validation["error"]}

    name = parse_spec_name(yaml_text)
    if not name:
        return {"ok": False, "code": "missing_name", "error": "experiment.name 不能为空"}

    conflict = check_strategy_duplicate(name, catalog_dir=catalog_dir, sandbox_dir=sandbox_dir)
    if conflict:
        return {"ok": False, "code": "duplicate_name", "error": f"策略名冲突：{conflict}"}

    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    path = sandbox_path(name, sandbox_dir)
    path.write_text(yaml_text, encoding="utf-8")
    return {"ok": True, "name": name, "path": str(path)}


def load_sandbox_yaml(name: str, sandbox_dir: Path | None = None) -> str | None:
    path = sandbox_path(name, sandbox_dir)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def record_smoke(
    name: str,
    run_id: str,
    *,
    status: str = "running",
    sandbox_dir: Path | None = None,
) -> Path:
    """把最近一次冒烟 run 写入 sidecar json。"""
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "status": status,
        "recorded_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    path = smoke_sidecar_path(name, sandbox_dir)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_sandbox(sandbox_dir: Path | None = None) -> list[dict[str, Any]]:
    """列出沙箱策略：名称、文件、mtime、最近一次冒烟记录。"""
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    entries: list[dict[str, Any]] = []
    if not sandbox_dir.exists():
        return entries
    for path in sorted(sandbox_dir.glob("*.yaml")):
        name = _read_experiment_name(path) or path.stem
        entry: dict[str, Any] = {
            "name": name,
            "file": str(path),
            "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
            "smoke": None,
        }
        sidecar = smoke_sidecar_path(path.stem, sandbox_dir)
        if sidecar.exists():
            try:
                entry["smoke"] = json.loads(sidecar.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# 晋升 / 删除
# ---------------------------------------------------------------------------


def promote(
    name: str,
    category: str,
    *,
    catalog_dir: Path | None = None,
    sandbox_dir: Path | None = None,
) -> dict[str, Any]:
    """把沙箱策略复制到 ``strategies/catalog/<category>/`` 并从沙箱移除。

    冒烟 sidecar 保留在沙箱目录作为历史记录。
    """
    category = (category or "").strip()
    if category not in CATALOG_CATEGORIES:
        return {
            "ok": False,
            "code": "invalid_category",
            "error": f"非法类别: {category or '(空)'}（可选: {', '.join(CATALOG_CATEGORIES)}）",
        }

    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    catalog_dir = catalog_dir or CATALOG_DIR
    src = sandbox_path(name, sandbox_dir)
    if not src.exists():
        return {"ok": False, "code": "not_found", "error": f"沙箱中不存在策略: {name}"}

    yaml_text = src.read_text(encoding="utf-8")
    spec_name = parse_spec_name(yaml_text) or name
    conflict = check_strategy_duplicate(spec_name, catalog_dir=catalog_dir, scan_sandbox=False)
    if conflict:
        return {"ok": False, "code": "duplicate_name", "error": f"策略名冲突：{conflict}"}

    dest_dir = catalog_dir / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    src.unlink()
    return {"ok": True, "name": spec_name, "category": category, "path": str(dest)}


def discard(name: str, *, sandbox_dir: Path | None = None) -> dict[str, Any]:
    """删除沙箱策略 YAML 及其冒烟 sidecar。"""
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    path = sandbox_path(name, sandbox_dir)
    if not path.exists():
        return {"ok": False, "code": "not_found", "error": f"沙箱中不存在策略: {name}"}
    deleted = [str(path)]
    path.unlink()
    sidecar = smoke_sidecar_path(name, sandbox_dir)
    if sidecar.exists():
        sidecar.unlink()
        deleted.append(str(sidecar))
    return {"ok": True, "deleted": deleted}
