"""GUI 策略创建闭环（P1）：查重 → 沙箱 → 冒烟 → 用户确认晋升 → catalog。

沙箱目录 ``outputs/sandbox/strategies/`` 独立于 ``strategies/catalog``——
refresh 日更只扫描 catalog，因此沙箱策略天然不会被日更拾取，无需额外隔离机制。
冒烟结果以 sidecar ``<name>.smoke.json`` 记录（与沙箱 YAML 同目录）。

目录均可注入（catalog_dir / sandbox_dir），便于测试。
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from quant_research_engine.gui.engine import extract_run_summary, validate_yaml
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


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """原子写 JSON（tmp + os.replace），避免并发读到半写文件。"""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


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
        "recorded_at": _now_iso(),
    }
    path = smoke_sidecar_path(name, sandbox_dir)
    _atomic_write_json(path, payload)
    return path


def read_smoke(name: str, sandbox_dir: Path | None = None) -> dict[str, Any] | None:
    """读取冒烟 sidecar；缺失或损坏返回 None。"""
    path = smoke_sidecar_path(name, sandbox_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


# 冒烟回写 sidecar 的关键指标（取自 engine.extract_run_summary 的 metrics）
SMOKE_METRIC_KEYS = (
    "total_trade_count",
    "strategy_total_return",
    "excess_return_vs_buy_hold",
    "max_drawdown",
)


def finalize_smoke(
    record: dict[str, Any],
    *,
    sandbox_dir: Path | None = None,
    summary: dict[str, Any] | None = None,
) -> Path | None:
    """run 结束时回写冒烟 sidecar：status=completed/failed + 关键指标 + 完成时间。

    由 engine._execute_and_finalize 在 run 收尾时调用（record 带 sandbox_strategy
    标记）；也可被 list_sandbox 用于自愈（GUI 重启丢线程导致 sidecar 滞留 running）。
    非沙箱冒烟 run（无标记）返回 None。
    """
    name = record.get("sandbox_strategy")
    if not name:
        return None
    status = "completed" if record.get("status") == "completed" else "failed"
    payload = read_smoke(name, sandbox_dir) or {}
    payload["run_id"] = record.get("run_id")
    payload["status"] = status
    payload["finished_at"] = record.get("finished_at") or _now_iso()
    if status == "completed":
        if summary is None:
            summary = extract_run_summary(record) or {}
        metrics_src = summary.get("metrics", {})
        payload["metrics"] = {k: metrics_src[k] for k in SMOKE_METRIC_KEYS if k in metrics_src}
        payload.pop("error", None)
    else:
        payload["error"] = record.get("error") or "冒烟回测失败（详见 run 日志）"
    sandbox_dir = sandbox_dir or DEFAULT_SANDBOX_DIR
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    path = smoke_sidecar_path(name, sandbox_dir)
    _atomic_write_json(path, payload)
    return path


def _self_heal_smoke(entry: dict[str, Any], sandbox_dir: Path) -> None:
    """sidecar 滞留 running 时查 run 终态补写（覆盖 GUI 重启丢后台线程的场景）。"""
    smoke = entry.get("smoke")
    if not smoke or smoke.get("status") != "running":
        return
    try:
        from quant_research_engine.gui.engine import get_run

        record = get_run(str(smoke.get("run_id") or ""))
    except Exception:
        return
    if record and record.get("status") in ("completed", "failed"):
        finalize_smoke(record, sandbox_dir=sandbox_dir)
        entry["smoke"] = read_smoke(entry["name"], sandbox_dir)


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
        _self_heal_smoke(entry, sandbox_dir)
        entries.append(entry)
    return entries


# ---------------------------------------------------------------------------
# 晋升全量回测闸（promotion gate）：run 收尾评估 + 结果落盘
# ---------------------------------------------------------------------------

# 写死的最简判据（QRE-GUI-PROMO-GATE-001）：交易次数 >= 30 且超额(对买入持有) > 0
GATE_MIN_TRADES = 30
GATE_METRIC_KEYS = (
    "total_trade_count",
    "strategy_total_return",
    "excess_return_vs_buy_hold",
    "max_drawdown",
)


def finalize_promotion_gate(
    record: dict[str, Any],
    *,
    gates_dir: Path | None = None,
    summary: dict[str, Any] | None = None,
) -> Path | None:
    """run 结束时评估晋升闸并回写 ``outputs/refresh/gates/<name>.json``。

    由 engine._execute_and_finalize 在 run 收尾时调用（record 带 promotion_gate
    标记）。判据写死：交易次数 >= 30 且 excess_return_vs_buy_hold > 0 → passed，
    否则 failed；run 本身失败也记 failed（附 error）。force 晋升的策略照常评估，
    ``forced=True`` 透传（日更不跳过，仅展示「强制在库」）。
    非晋升闸 run（无标记）返回 None。
    """
    if not record.get("promotion_gate"):
        return None
    name = record.get("promoted_strategy")
    if not name:
        return None
    from quant_research_engine.gui.refresh_registry import load_gate, save_gate

    forced = bool(record.get("promotion_forced"))
    payload = load_gate(name, gates_dir) or {}
    payload.update(
        {
            "strategy": name,
            "run_id": record.get("run_id"),
            "forced": forced,
            "criteria": {
                "min_trades": GATE_MIN_TRADES,
                "min_excess_return_vs_buy_hold": 0,
            },
            "evaluated_at": _now_iso(),
        }
    )
    if record.get("status") != "completed":
        payload["gate"] = "failed"
        payload["error"] = record.get("error") or "晋升全量回测失败（详见 run 日志）"
        payload.pop("metrics", None)
    else:
        if summary is None:
            summary = extract_run_summary(record) or {}
        metrics_src = summary.get("metrics", {})
        metrics = {k: metrics_src[k] for k in GATE_METRIC_KEYS if k in metrics_src}
        trades = metrics.get("total_trade_count")
        excess = metrics.get("excess_return_vs_buy_hold")
        passed = (
            isinstance(trades, (int, float))
            and trades >= GATE_MIN_TRADES
            and isinstance(excess, (int, float))
            and excess > 0
        )
        payload["gate"] = "passed" if passed else "failed"
        payload["metrics"] = metrics
        payload.pop("error", None)
    return save_gate(name, payload, gates_dir)


# ---------------------------------------------------------------------------
# 晋升 / 删除
# ---------------------------------------------------------------------------


def promote(
    name: str,
    category: str,
    *,
    catalog_dir: Path | None = None,
    sandbox_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """把沙箱策略复制到 ``strategies/catalog/<category>/`` 并从沙箱移除。

    冒烟 sidecar 保留在沙箱目录作为历史记录。
    状态闸：sidecar 缺失或 status != "completed" 时拒绝晋升
    （code=smoke_not_passed）；``force=True`` 为管理员绕过通道。
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

    if not force:
        smoke = read_smoke(spec_name, sandbox_dir) or read_smoke(name, sandbox_dir)
        if not smoke or smoke.get("status") != "completed":
            return {
                "ok": False,
                "code": "smoke_not_passed",
                "error": "未通过冒烟测试：请先在沙箱运行冒烟测试并等待通过后再晋升"
                "（管理员可用 force=true 强制晋升）。",
            }

    dest_dir = catalog_dir / category
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copy2(src, dest)
    src.unlink()
    result: dict[str, Any] = {"ok": True, "name": spec_name, "category": category, "path": str(dest)}
    if force:
        result["forced"] = True
    return result


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
