"""策略状态：refresh 策略注册表 v2 + 持续更新状态 + 最新结果提取。

注册表文件 ``outputs/refresh/registry.json`` v2 格式：
  {"include": [...], "stopped": [...]}
  - include 为空 = 全量模式（catalog 全部视为开启，stopped 除外）；
  - include 非空 = 注册模式（仅 include − stopped 随 refresh 运行）；
  - stopped 内策略显示灰色（停止），下次 refresh 跳过。
兼容读取旧格式：纯数组 [...] 或 {"strategies": [...]}（视为 include，stopped=[]）。
refresh_batch.py 在注册表存在且有效时自动按表过滤（--strategies 优先），
注册表缺失时行为与现状完全一致（全量扫描），无需改 systemd unit。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant_research_engine.gui.admin import _cached

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CATALOG_DIR = PROJECT_ROOT / "strategies" / "catalog"
DEFAULT_REGISTRY_PATH = Path("outputs/refresh/registry.json")
DEFAULT_STATE_PATH = Path("outputs/refresh/state.json")
DEFAULT_DELTA_ROOT = Path("outputs/refresh/delta")
DEFAULT_BACKTESTS_DIR = Path("outputs/backtests")


# ---------------------------------------------------------------------------
# 注册表读写（v2：include + stopped，兼容旧格式）
# ---------------------------------------------------------------------------


def load_registry(path: Path | None = None) -> dict[str, list[str]]:
    """返回 {"include": [...], "stopped": [...]}（排序去重）。兼容旧格式。"""
    path = path or DEFAULT_REGISTRY_PATH
    include: list[str] = []
    stopped: list[str] = []
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = None
        if isinstance(payload, list):  # 旧格式：纯数组
            include = payload
        elif isinstance(payload, dict):
            if isinstance(payload.get("include"), list):
                include = payload["include"]
            elif isinstance(payload.get("strategies"), list):  # 旧格式：{"strategies": [...]}
                include = payload["strategies"]
            if isinstance(payload.get("stopped"), list):
                stopped = payload["stopped"]
    include = sorted({str(s) for s in include})
    stopped = sorted({str(s) for s in stopped})
    return {"include": include, "stopped": stopped}


def save_registry(data: dict[str, list[str]], path: Path | None = None) -> dict[str, list[str]]:
    path = path or DEFAULT_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = {
        "include": sorted({str(s) for s in data.get("include", [])}),
        "stopped": sorted({str(s) for s in data.get("stopped", [])}),
    }
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def register_strategy(strategy_id: str, path: Path | None = None) -> dict[str, list[str]]:
    strategy_id = (strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("策略 ID 不能为空")
    data = load_registry(path)
    data["include"] = sorted(set(data["include"]) | {strategy_id})
    data["stopped"] = [s for s in data["stopped"] if s != strategy_id]
    return save_registry(data, path)


def unregister_strategy(strategy_id: str, path: Path | None = None) -> dict[str, list[str]]:
    data = load_registry(path)
    data["include"] = [s for s in data["include"] if s != strategy_id]
    data["stopped"] = [s for s in data["stopped"] if s != strategy_id]
    return save_registry(data, path)


def set_strategy_stopped(
    strategy_id: str,
    stopped: bool,
    path: Path | None = None,
) -> dict[str, list[str]]:
    """切换持续更新开关（只改注册表，不触发任何运行）。"""
    strategy_id = (strategy_id or "").strip()
    if not strategy_id:
        raise ValueError("策略 ID 不能为空")
    data = load_registry(path)
    current = set(data["stopped"])
    if stopped:
        current.add(strategy_id)
    else:
        current.discard(strategy_id)
    data["stopped"] = sorted(current)
    return save_registry(data, path)


def list_catalog_strategies(catalog_dir: Path | None = None) -> list[str]:
    catalog_dir = catalog_dir or CATALOG_DIR
    if not catalog_dir.is_dir():
        return []
    return sorted(p.stem for p in catalog_dir.rglob("*.yaml"))


# ---------------------------------------------------------------------------
# per-strategy 最新回测结果提取（300s 缓存）
# ---------------------------------------------------------------------------

# 状态表四列使用的指标
RESULT_METRIC_KEYS = (
    "date_start",
    "date_end",
    "traded_symbol_count",
    "symbol_count",
    "excess_return_vs_buy_hold",
    "max_drawdown",
    "strategy_total_return",
    "buy_hold_return",
    "win_rate",
    "profit_factor",
    "total_trade_count",
    "strategy_name",
)


def latest_strategy_result(
    strategy_id: str,
    backtests_dir: Path | None = None,
) -> dict[str, Any] | None:
    """找该策略最新的 strategy_performance.json（mtime 最大），返回指标+产物目录。

    搜索 outputs/backtests/**/<strategy_id>/backtest/strategy_performance.json
    （覆盖普通批次与 refresh/<batch>/<sid> 布局）。无结果返回 None。
    """
    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR

    def _produce() -> dict[str, Any] | None:
        candidates = sorted(backtests_dir.glob(f"**/{strategy_id}/backtest/strategy_performance.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda p: p.stat().st_mtime)
        try:
            payload = json.loads(latest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        metrics = {k: payload.get(k) for k in RESULT_METRIC_KEYS if payload.get(k) is not None}
        # benchmark 超额兜底（存在 benchmark_excess* 键时取其一）
        if "excess_return_vs_buy_hold" not in metrics:
            for key, value in payload.items():
                if key.startswith("benchmark_") and "excess" in key and isinstance(value, (int, float)):
                    metrics["benchmark_excess"] = value
                    break
        return {
            "metrics": metrics,
            "source_file": str(latest),
            "artifact_dir": str(latest.parent.parent),  # <...>/<sid>/
            "mtime": latest.stat().st_mtime,
        }

    return _cached(f"strategy_result:{backtests_dir}:{strategy_id}", _produce)


def list_result_artifacts(artifact_dir: str | Path) -> list[dict[str, str]]:
    """列出产物目录下的文件（相对路径），供详情页下载链接。"""
    root = Path(artifact_dir)
    if not root.is_dir():
        return []
    files = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            files.append({"rel": str(p.relative_to(root)), "name": p.name})
    return files


def clear_strategy_result_cache(strategy_id: str, backtests_dir: Path | None = None) -> None:
    from quant_research_engine.gui import admin as _admin

    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR
    _admin._cache.pop(f"strategy_result:{backtests_dir}:{strategy_id}", None)


# ---------------------------------------------------------------------------
# 持续更新状态
# ---------------------------------------------------------------------------


def _latest_delta(delta_root: Path) -> dict[str, Any] | None:
    if not delta_root.is_dir():
        return None
    reports = sorted(delta_root.glob("*/delta_report.json"))
    if not reports:
        return None
    latest = reports[-1]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    payload["_dir"] = latest.parent.name
    return payload


def refresh_overview(
    *,
    state_path: Path | None = None,
    registry_path: Path | None = None,
    delta_root: Path | None = None,
    catalog_dir: Path | None = None,
    backtests_dir: Path | None = None,
) -> dict[str, Any]:
    """策略状态总览：refresh state + 注册表 v2 + 最近 delta + 每策略最新结果四列。"""
    from quant_research_engine.orchestration.refresh import load_state

    state = load_state(state_path or DEFAULT_STATE_PATH)
    registry = load_registry(registry_path)
    include, stopped = registry["include"], registry["stopped"]
    catalog = list_catalog_strategies(catalog_dir)
    delta = _latest_delta(delta_root or DEFAULT_DELTA_ROOT)
    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR

    delta_rows = {row["strategy_id"]: row for row in (delta or {}).get("rows", [])}
    strategies: list[dict[str, Any]] = []
    for sid in catalog:
        row = delta_rows.get(sid, {})
        result = latest_strategy_result(sid, backtests_dir)
        metrics = (result or {}).get("metrics", {})
        strategies.append(
            {
                "strategy_id": sid,
                # 开启语义：include 空=默认全开（除非 stopped）；include 非空=在 include 且未 stopped
                "enabled": (sid not in stopped) and (not include or sid in include),
                "stopped": sid in stopped,
                "registered": sid in include,
                "status": row.get("status"),
                "date_start": metrics.get("date_start"),
                "date_end": metrics.get("date_end"),
                "traded_symbol_count": metrics.get("traded_symbol_count"),
                "symbol_count": metrics.get("symbol_count"),
                "excess_return": metrics.get("excess_return_vs_buy_hold", metrics.get("benchmark_excess")),
                "max_drawdown": metrics.get("max_drawdown"),
            }
        )

    mode = "registry" if include else "full_catalog"
    return {
        "state": state.to_dict() if state else None,
        "registered": include,
        "stopped": stopped,
        "registry_effective": bool(include),
        # 语义：include 空=全量模式（默认全开启）；include 非空=仅注册策略模式
        "mode": mode,
        "catalog_total": len(catalog),
        "unregistered": [sid for sid in catalog if sid not in include],
        "latest_delta": (
            {
                "dir": delta["_dir"],
                "data_date": delta.get("data_date"),
                "strategy_count": delta.get("strategy_count"),
                "changed": delta.get("changed"),
            }
            if delta
            else None
        ),
        "strategies": strategies,
    }
