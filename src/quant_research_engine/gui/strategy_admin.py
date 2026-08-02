"""策略管理（QRE-ADMIN-MANAGE-001 / STRAT-TAB-001）：删除 catalog 策略，
联动 refresh 注册表与本地回测产物。

删除范围：strategies/catalog 下的 YAML 文件、注册表条目（include 与 stopped）、
outputs/backtests/*/<strategy_id>/ 产物目录（路径白名单校验防越界）。
注意：不做"refresh 正在运行"检查——调用方（GUI 弹窗）负责提示风险。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from quant_research_engine.gui.refresh_registry import (
    CATALOG_DIR,
    DEFAULT_REGISTRY_PATH,
    clear_strategy_result_cache,
    unregister_strategy,
)

OUTPUTS_BACKTESTS = Path("outputs/backtests")


def find_strategy_file(strategy_id: str, catalog_dir: Path | None = None) -> Path | None:
    catalog_dir = catalog_dir or CATALOG_DIR
    matches = [p for p in catalog_dir.rglob("*.yaml") if p.stem == strategy_id]
    return matches[0] if matches else None


def strategy_catalog_info(strategy_id: str, catalog_dir: Path | None = None) -> dict[str, Any]:
    """从 catalog YAML 提取简介：头部注释块 + 实验名 + 出入场条件 + 持仓天数。"""
    path = find_strategy_file(strategy_id, catalog_dir)
    if path is None:
        return {}
    text = path.read_text(encoding="utf-8")
    comment_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            content = stripped.lstrip("#").strip()
            if content and not set(content) <= {"=", "-"}:
                comment_lines.append(content)
        elif comment_lines:
            break  # 只取文件头部注释块
    info: dict[str, Any] = {"file": str(path), "comments": comment_lines[:20]}
    try:
        import yaml

        spec = yaml.safe_load(text) or {}
        signal = spec.get("signal") or {}
        holding = spec.get("holding") or {}
        info["name"] = (spec.get("experiment") or {}).get("name")
        info["entry"] = signal.get("entry")
        info["exit"] = signal.get("exit")
        info["max_holding_days"] = holding.get("max_holding_days")
    except Exception:
        pass
    return info


def delete_strategy(
    strategy_id: str,
    *,
    catalog_dir: Path | None = None,
    registry_path: Path | None = None,
    outputs_backtests: Path | None = None,
) -> dict[str, Any]:
    """删除 catalog 策略 YAML + 移出注册表 + 删除本地回测产物目录。

    返回删除清单（deleted_files / deleted_dirs）。策略不存在抛 ValueError（中文）。
    产物删除带白名单：仅允许 backtests 根下 <批次>/<strategy_id> 形式的目录。
    """
    strategy_id = (strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("策略 ID 不能为空")
    catalog_dir = catalog_dir or CATALOG_DIR
    path = find_strategy_file(strategy_id, catalog_dir)
    if path is None:
        raise ValueError(f"策略不在 catalog 中: {strategy_id}")

    deleted_files = [str(path)]
    path.unlink()
    registry = unregister_strategy(strategy_id, registry_path)

    # 产物：仅 <backtests>/<batch>/<strategy_id> 一级（resolve 后 parent.parent 必须等于 backtests 根）
    backtests = (outputs_backtests or OUTPUTS_BACKTESTS).resolve()
    deleted_dirs: list[str] = []
    errors: list[str] = []
    if backtests.is_dir():
        for candidate in sorted(backtests.glob(f"*/{strategy_id}")):
            if not candidate.is_dir():
                continue
            resolved = candidate.resolve()
            if resolved.parent.parent != backtests or resolved.name != strategy_id:
                errors.append(f"越界拒绝: {candidate}")
                continue
            shutil.rmtree(resolved)
            deleted_dirs.append(str(resolved))
    clear_strategy_result_cache(strategy_id, outputs_backtests or OUTPUTS_BACKTESTS)

    return {
        "strategy_id": strategy_id,
        "deleted_files": deleted_files,
        "deleted_dirs": deleted_dirs,
        "registry": registry,
        "errors": errors,
        "note": f"已删除策略文件、注册表条目与 {len(deleted_dirs)} 处产物目录",
    }
