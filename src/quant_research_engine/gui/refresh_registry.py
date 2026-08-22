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
DEFAULT_INCREMENTAL_ROOT = Path("outputs/refresh/incremental")
DEFAULT_GATES_DIR = Path("outputs/refresh/gates")


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


# ---------------------------------------------------------------------------
# 晋升全量回测闸（promotion gate）：outputs/refresh/gates/<name>.json
# ---------------------------------------------------------------------------
#
# 与 registry.json/state.json 同族的状态存储（outputs/refresh/ 下，不进 git 管理的
# catalog）。gate 语义：passed=全量回测达标；failed=未达标（日更跳过，forced 除外）；
# R4 风险判据：risk.status=warning 同效阻止日更（forced 除外），unavailable/缺失不阻断；
# 文件缺失=未评估=正常拾取（兼容存量策略）。


def _safe_gate_name(name: str) -> str:
    return name.replace("/", "_").replace("\\", "_").strip()


def gate_path(name: str, gates_dir: Path | None = None) -> Path:
    gates_dir = gates_dir or DEFAULT_GATES_DIR
    return gates_dir / f"{_safe_gate_name(name)}.json"


def load_gate(name: str, gates_dir: Path | None = None) -> dict[str, Any] | None:
    """读取策略的晋升闸结果；缺失或损坏返回 None。"""
    path = gate_path(name, gates_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def save_gate(name: str, payload: dict[str, Any], gates_dir: Path | None = None) -> Path:
    """原子写 gate 文件（tmp + os.replace）。"""
    import os

    gates_dir = gates_dir or DEFAULT_GATES_DIR
    gates_dir.mkdir(parents=True, exist_ok=True)
    path = gate_path(name, gates_dir)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)
    return path


def gate_blocks_daily(gate: dict[str, Any] | None) -> bool:
    """该 gate 结果是否阻止日更。

    ``gate == "failed"``（主判据未过）或 ``risk.status == "warning"``
    （R4 风险判据触发）且非 force 晋升 → 阻止；risk 缺失/unavailable 不阻断。
    """
    if not gate:
        return False
    if gate.get("forced"):
        return False
    if gate.get("gate") == "failed":
        return True
    return bool((gate.get("risk") or {}).get("status") == "warning")


def load_all_gates(gates_dir: Path | None = None) -> dict[str, dict[str, Any]]:
    """读取全部 gate 文件 → {strategy: payload}（坏文件跳过）。"""
    gates_dir = gates_dir or DEFAULT_GATES_DIR
    gates: dict[str, dict[str, Any]] = {}
    if not gates_dir.is_dir():
        return gates
    for path in sorted(gates_dir.glob("*.json")):
        if path.name.endswith(".tmp"):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            gates[str(data.get("strategy") or path.stem)] = data
    return gates


def list_catalog_strategies(
    catalog_dir: Path | None = None,
    *,
    skip_failed_gate: bool = False,
    gates_dir: Path | None = None,
) -> list[str]:
    """列出 catalog 策略 id。

    ``skip_failed_gate=True`` 时跳过 gate=failed 且非 forced 的策略
    （gate 缺失=未评估=正常拾取）；默认 False，注册/开关校验语义不变。
    """
    catalog_dir = catalog_dir or CATALOG_DIR
    if not catalog_dir.is_dir():
        return []
    ids = sorted(p.stem for p in catalog_dir.rglob("*.yaml"))
    if skip_failed_gate:
        ids = [sid for sid in ids if not gate_blocks_daily(load_gate(sid, gates_dir))]
    return ids


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

# 增量产物（outputs/refresh/incremental/<sid>/）中代表"新鲜度"的字段；
# 全量指标（excess_return_vs_buy_hold/max_drawdown/date_start 等）增量没有，仍取自全量批次。
_INCREMENTAL_METRIC_KEYS = (
    "symbol_count",
    "traded_symbol_count",
    "mean_total_return",
    "total_trades",
    "positive_return_symbol_rate",
)


def _load_batch_result(
    strategy_id: str, backtests_dir: Path
) -> tuple[dict[str, Any], Path, float] | None:
    """最新 strategy_performance.json → (metrics, path, mtime)。无结果/坏文件返回 None。"""
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
    return metrics, latest, latest.stat().st_mtime


def _load_incremental_result(
    strategy_id: str, incremental_root: Path
) -> tuple[dict[str, Any], Path, float] | None:
    """增量 summary_metrics.json + state.json watermark → (metrics, path, mtime)。

    date_end 取自 state.json 的 data_watermark/last_processed_date（缺字段时容错为 None，
    不伪造）。state.json 约 1MB 可整读，但只提取 watermark 字段。
    """
    metrics_path = incremental_root / strategy_id / "backtest" / "summary_metrics.json"
    if not metrics_path.is_file():
        return None
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    metrics = {k: payload.get(k) for k in _INCREMENTAL_METRIC_KEYS if payload.get(k) is not None}
    state_path = incremental_root / strategy_id / "state.json"
    watermark = None
    if state_path.is_file():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            watermark = state.get("data_watermark") or state.get("last_processed_date")
        except (json.JSONDecodeError, OSError):
            watermark = None
    if watermark:
        metrics["date_end"] = watermark
    return metrics, metrics_path, metrics_path.stat().st_mtime


def latest_strategy_result(
    strategy_id: str,
    backtests_dir: Path | None = None,
    incremental_root: Path | None = None,
) -> dict[str, Any] | None:
    """该策略最新结果：全量批次 strategy_performance.json + 每日增量 summary_metrics.json 合并。

    - 新鲜度字段（date_end/symbol_count/traded_symbol_count/mean_total_return/
      total_trades/positive_return_symbol_rate）：增量 mtime 更新时取增量，
      date_end ← 增量 state.json 的 data_watermark/last_processed_date；
    - 全量指标（excess_return_vs_buy_hold/max_drawdown/date_start/strategy_name 等）：
      始终取最新全量批次，并附 full_metrics_as_of（该批次 date_end）供前端标注
      "截至 <date> 全量"；
    - source ∈ {"batch", "incremental", "merged"}；artifact_dir 指向最新来源所在目录
      （增量更新时为 outputs/refresh/incremental/<sid>/，供详情页下载链接）。
    无结果返回 None。
    """
    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR
    incremental_root = incremental_root or DEFAULT_INCREMENTAL_ROOT

    def _produce() -> dict[str, Any] | None:
        batch = _load_batch_result(strategy_id, backtests_dir)
        inc = _load_incremental_result(strategy_id, incremental_root)
        if batch is None and inc is None:
            return None

        source_mtimes: dict[str, float] = {}
        if batch is not None:
            source_mtimes["batch"] = batch[2]
        if inc is not None:
            source_mtimes["incremental"] = inc[2]

        if batch is None:
            return {
                "metrics": inc[0],
                "source": "incremental",
                "source_file": str(inc[1]),
                "artifact_dir": str(inc[1].parent.parent),  # outputs/refresh/incremental/<sid>/
                "mtime": inc[2],
                "source_mtimes": source_mtimes,
                "full_metrics_as_of": None,
            }

        metrics, batch_path, batch_mtime = batch
        merged = dict(metrics)
        use_incremental = inc is not None and inc[2] > batch_mtime
        full_metrics_as_of = metrics.get("date_end")
        if use_incremental:
            merged.update(inc[0])
            return {
                "metrics": merged,
                "source": "merged",
                "source_file": str(inc[1]),
                "artifact_dir": str(inc[1].parent.parent),
                "mtime": inc[2],
                "source_mtimes": source_mtimes,
                "full_metrics_as_of": full_metrics_as_of,
                "full_metrics_source_file": str(batch_path),
            }
        return {
            "metrics": merged,
            "source": "batch",
            "source_file": str(batch_path),
            "artifact_dir": str(batch_path.parent.parent),  # <...>/<sid>/
            "mtime": batch_mtime,
            "source_mtimes": source_mtimes,
            "full_metrics_as_of": full_metrics_as_of,
        }

    return _cached(f"strategy_result:{backtests_dir}:{incremental_root}:{strategy_id}", _produce)


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


def clear_strategy_result_cache(
    strategy_id: str,
    backtests_dir: Path | None = None,
    incremental_root: Path | None = None,
) -> None:
    from quant_research_engine.gui import admin as _admin

    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR
    incremental_root = incremental_root or DEFAULT_INCREMENTAL_ROOT
    _admin._cache.pop(f"strategy_result:{backtests_dir}:{incremental_root}:{strategy_id}", None)


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
    incremental_root: Path | None = None,
    gates_dir: Path | None = None,
) -> dict[str, Any]:
    """策略状态总览：refresh state + 注册表 v2 + 最近 delta + 每策略最新结果四列。"""
    from quant_research_engine.orchestration.refresh import load_state

    state = load_state(state_path or DEFAULT_STATE_PATH)
    registry = load_registry(registry_path)
    include, stopped = registry["include"], registry["stopped"]
    catalog = list_catalog_strategies(catalog_dir)
    delta = _latest_delta(delta_root or DEFAULT_DELTA_ROOT)
    backtests_dir = backtests_dir or DEFAULT_BACKTESTS_DIR
    incremental_root = incremental_root or DEFAULT_INCREMENTAL_ROOT

    delta_rows = {row["strategy_id"]: row for row in (delta or {}).get("rows", [])}
    all_gates = load_all_gates(gates_dir)
    strategies: list[dict[str, Any]] = []
    for sid in catalog:
        row = delta_rows.get(sid, {})
        gate = all_gates.get(sid)
        result = latest_strategy_result(sid, backtests_dir, incremental_root)
        metrics = (result or {}).get("metrics", {})
        full_as_of = (result or {}).get("full_metrics_as_of")
        date_end = metrics.get("date_end")
        strategies.append(
            {
                "strategy_id": sid,
                # 开启语义：include 空=默认全开（除非 stopped）；include 非空=在 include 且未 stopped
                "enabled": (sid not in stopped) and (not include or sid in include),
                "stopped": sid in stopped,
                "registered": sid in include,
                "status": row.get("status"),
                "date_start": metrics.get("date_start"),
                "date_end": date_end,
                "traded_symbol_count": metrics.get("traded_symbol_count"),
                "symbol_count": metrics.get("symbol_count"),
                "excess_return": metrics.get("excess_return_vs_buy_hold", metrics.get("benchmark_excess")),
                "max_drawdown": metrics.get("max_drawdown"),
                "source": (result or {}).get("source"),
                # 超额/回撤等全量指标落后于 date_end 时，前端据此标注"截至 <date> 全量"
                "full_metrics_as_of": full_as_of if full_as_of and date_end and full_as_of < date_end else None,
                # 晋升全量回测闸：None=未评估；failed 且非 forced 时将被日更跳过
                "gate": gate,
                "gate_blocks_daily": gate_blocks_daily(gate),
            }
        )

    gate_skipped = [s["strategy_id"] for s in strategies if s["gate_blocks_daily"]]
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
        "gate_skipped": gate_skipped,
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
