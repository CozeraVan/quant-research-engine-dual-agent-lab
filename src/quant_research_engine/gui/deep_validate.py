"""策略深度验证（QRE-GUI-DEEP-VALIDATE-001）：策略 YAML → 逐日信号池 →
cluster-ashare 四关验证。

链路：
  1. spec_to_conditions（纯函数）：StrategySpec → 条件 JSON
     （name/expression/factor_fields/market_fields/used_fields/d0/d1），
     落盘 outputs/gui-console/deep-validate/<name>/conditions.json；
  2. subprocess 调 cluster-ashare analysis/pool_from_conditions.py 生成
     逐日池 parquet（DB 访问与因子口径全留在 cluster 侧，QRE 不碰库）；
  3. subprocess 调 cluster-ashare analysis/validate_factor.py
     --pool-parquet 跑四关验证（价格/评估缓存按区间命名 → 断点续跑）；
  4. parse_report_summary（纯函数）解析报告结论段 → job result.json。

口径：信号池 = T 日收盘满足**入场条件**的股票；出场/止盈止损/持仓参数不进池
（四关验证的是信号本身的选股能力）。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.gui.daily_jobs import WORKSPACE, start_script_job
from quant_research_engine.gui.engine import GUI_BASE_DIR
from quant_research_engine.gui.strategy_create import (
    DEFAULT_SANDBOX_DIR,
    _read_experiment_name,
    _safe_name,
    load_sandbox_yaml,
)
from quant_research_engine.gui.refresh_registry import CATALOG_DIR

# --- cluster-ashare 侧入口（只读调用，不改其代码） ---
CLUSTER_REPO = WORKSPACE / "cluster-ashare"
CLUSTER_PY = CLUSTER_REPO / ".venv" / "bin" / "python"
POOL_SCRIPT = CLUSTER_REPO / "analysis" / "pool_from_conditions.py"
VALIDATE_SCRIPT = CLUSTER_REPO / "analysis" / "validate_factor.py"
CLUSTER_OUT_DIR = CLUSTER_REPO / "outputs" / "factor_mining" / "validation"
BASIC_CACHE = CLUSTER_OUT_DIR / "daily_basic_cache.parquet"  # 存在则启用 gate4
QRE_CACHE_DIR = CLUSTER_OUT_DIR / "qre_cache"

QRE_SRC = WORKSPACE / "quant-research-engine-dual-agent-lab" / "src"

DEFAULT_D0 = "2015-01-01"
DEEP_VALIDATE_DIR = GUI_BASE_DIR / "deep-validate"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def cluster_available() -> str | None:
    """cluster-ashare 运行环境检查；可用返回 None，否则返回错误描述。"""
    if not CLUSTER_PY.exists():
        return f"cluster-ashare 解释器不存在: {CLUSTER_PY}"
    if not POOL_SCRIPT.exists():
        return f"信号池脚本不存在: {POOL_SCRIPT}"
    if not VALIDATE_SCRIPT.exists():
        return f"四关验证脚本不存在: {VALIDATE_SCRIPT}"
    return None


def locate_strategy_yaml(
    name: str,
    *,
    sandbox_dir: Path | None = None,
    catalog_dir: Path | None = None,
) -> str | None:
    """按策略名定位 YAML 文本：沙箱优先，其次 catalog（experiment.name 或
    文件 stem 匹配）。找不到返回 None。"""
    yaml_text = load_sandbox_yaml(name, sandbox_dir)
    if yaml_text is not None:
        return yaml_text
    catalog_dir = catalog_dir or CATALOG_DIR
    if catalog_dir.exists():
        for path in sorted(catalog_dir.rglob("*.yaml")):
            if path.stem == _safe_name(name):
                return path.read_text(encoding="utf-8")
        for path in sorted(catalog_dir.rglob("*.yaml")):
            if _read_experiment_name(path) == name:
                return path.read_text(encoding="utf-8")
    return None


# ---------------------------------------------------------------------------
# 转换器（纯函数）
# ---------------------------------------------------------------------------


def used_expression_fields(expression: str) -> set[str]:
    """表达式 AST 中引用的 Name 节点集合（排除方法名/属性名）。纯函数。"""
    tree = ast.parse(expression, mode="eval")
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
    return names


def spec_to_conditions(
    spec,
    *,
    d0: str,
    d1: str,
    qre_src: Path | None = None,
) -> dict[str, Any]:
    """StrategySpec → 条件 JSON（pool_from_conditions.py 的输入）。纯函数。

    只纳入**入场**表达式；factor_fields 原样透传（含未引用项，便于审计），
    used_fields 供 cluster 脚本只拉取被引用列。
    """
    expression = (spec.signal_expression or "").strip()
    if not expression:
        raise ValueError(f"策略 {spec.name} 无入场表达式（signal.entry）")
    factor_fields = {
        f.logical_name: f"{f.source_schema}.{f.source_table}.{f.source_column}"
        for f in (spec.factor_fields or [])
    }
    return {
        "name": spec.name,
        "expression": expression,
        "factor_fields": factor_fields,
        "market_fields": list(spec.market_fields or []),
        "used_fields": sorted(used_expression_fields(expression)),
        "d0": d0,
        "d1": d1,
        "qre_src": str(qre_src or QRE_SRC),
        "scope_note": "信号池=入场条件逐日筛选；出场/止盈止损/持仓参数不进池",
    }


# ---------------------------------------------------------------------------
# 报告解析（纯函数）
# ---------------------------------------------------------------------------


def parse_report_summary(md_text: str) -> dict[str, Any]:
    """解析四关验证报告 markdown：结论段 verdict + 四关关键数字。纯函数。"""
    result: dict[str, Any] = {"verdict": None, "conclusion": None, "gates": []}
    m = re.search(r"^## 0\. 结论\s*\n\s*\n(.*?)(?:\n## |\Z)",
                  md_text, re.M | re.S)
    if m:
        conclusion = " ".join(m.group(1).split())
        result["conclusion"] = conclusion
        vm = re.search(r"\*\*(GO|NO-GO)\*\*", conclusion)
        if vm:
            result["verdict"] = vm.group(1)
    gsec = re.search(r"^## 3\. 四关结果\s*\n(.*?)(?:\n## |\Z)",
                     md_text, re.M | re.S)
    if gsec:
        for line in gsec.group(1).splitlines():
            if not line.strip().startswith("|"):
                continue
            cells = [c.strip().strip("*").strip()
                     for c in line.strip().strip("|").split("|")]
            if len(cells) < 7 or not cells[0].startswith("gate"):
                continue
            result["gates"].append({
                "gate": cells[0],
                "days": cells[1],
                "mean_excess": cells[2],
                "t": cells[3],
                "pos_rate": cells[6],
            })
    return result


def parse_validate_stdout(stdout: str) -> dict[str, Any]:
    """从 validate_factor.py stdout 提取结论与报告路径。纯函数。"""
    out: dict[str, Any] = {}
    m = re.search(r"\[fv\] 最终结论: (\S+)", stdout)
    if m:
        out["verdict"] = m.group(1)
    m = re.search(r"\[fv\] 报告: (\S+)", stdout)
    if m:
        out["report_path"] = m.group(1)
    return out


# ---------------------------------------------------------------------------
# 异步 job
# ---------------------------------------------------------------------------


def _validate_date(value: str, label: str) -> None:
    if not _DATE_RE.match(value):
        raise ValueError(f"{label} 必须是 YYYY-MM-DD: {value!r}")
    date.fromisoformat(value)


def start_deep_validate_job(
    name: str,
    spec,
    *,
    d0: str | None = None,
    d1: str | None = None,
    work_dir: Path | None = None,
    runner: Callable[[list[str], Path, Path], int] | None = None,
    job_starter: Callable[..., dict[str, Any]] | None = None,
    subproc: Callable[..., subprocess.CompletedProcess] | None = None,
) -> dict[str, Any]:
    """提交异步深度验证（复用 daily_jobs.start_script_job，同名串行）。

    立即返回 {"ok", "job_id", "status": "running", ...}；后台线程依次跑
    pool_from_conditions.py 与 validate_factor.py，终态写 job_dir/result.json。
    同名策略在途时 start_script_job 抛 RuntimeError（路由层转 409）。
    """
    d0 = d0 or DEFAULT_D0
    d1 = d1 or date.today().isoformat()
    _validate_date(d0, "d0")
    _validate_date(d1, "d1")
    if d0 > d1:
        raise ValueError(f"d0({d0}) 晚于 d1({d1})")

    safe = _safe_name(name)
    work_dir = work_dir or (DEEP_VALIDATE_DIR / safe)
    work_dir.mkdir(parents=True, exist_ok=True)
    conditions = spec_to_conditions(spec, d0=d0, d1=d1)
    conditions_path = work_dir / "conditions.json"
    conditions_path.write_text(
        json.dumps(conditions, ensure_ascii=False, indent=2), encoding="utf-8")
    pool_path = work_dir / "pool.parquet"

    run_name = f"qre_{safe}"
    # 缓存键含区间（load_price_panel 对已存在缓存不做范围校验，靠文件名隔离）
    price_cache = QRE_CACHE_DIR / f"price_{d0}_{d1}.parquet"
    eval_cache = QRE_CACHE_DIR / f"eval_{run_name}_{d0}_{d1}.parquet"

    pool_cmd = [str(CLUSTER_PY), str(POOL_SCRIPT),
                "--conditions", str(conditions_path), "--out", str(pool_path)]
    validate_cmd = [str(CLUSTER_PY), str(VALIDATE_SCRIPT),
                    "--pool-parquet", str(pool_path), "--name", run_name,
                    "--d0", d0, "--d1", d1,
                    "--price-cache", str(price_cache),
                    "--eval-cache", str(eval_cache)]
    if BASIC_CACHE.exists():
        validate_cmd += ["--basic-cache", str(BASIC_CACHE)]

    def _run_step(cmd: list[str], job_dir: Path) -> tuple[int, str]:
        from quant_research_engine.gui.daily_jobs import _append_log

        _append_log(job_dir, f"$ {' '.join(cmd)}\n(cwd: {CLUSTER_REPO})\n\n")
        run = subproc or subprocess.run
        try:
            proc = run(cmd, cwd=str(CLUSTER_REPO), capture_output=True,
                       text=True, timeout=4 * 3600)
        except Exception as exc:
            _append_log(job_dir, f"执行异常: {exc}\n")
            return 1, ""
        if proc.stdout:
            _append_log(job_dir, proc.stdout[-20000:]
                        + ("" if proc.stdout.endswith("\n") else "\n"))
        if proc.stderr:
            _append_log(job_dir, "[stderr] " + proc.stderr[-8000:]
                        + ("" if proc.stderr.endswith("\n") else "\n"))
        _append_log(job_dir, f"\nexit_code={proc.returncode}\n")
        return proc.returncode, proc.stdout or ""

    def _worker(job_cmd: list[str], cwd: Path, job_dir: Path) -> int:
        from quant_research_engine.gui.daily_jobs import _append_log

        job_dir = Path(job_dir)
        result: dict[str, Any] = {
            "ok": False, "strategy": name, "d0": d0, "d1": d1,
            "scope_note": conditions["scope_note"],
            "conditions_path": str(conditions_path),
        }
        code, pool_out = _run_step(pool_cmd, job_dir)
        if code != 0:
            result["error"] = "信号池生成失败（详见日志）"
        else:
            m = re.search(r"(\d+) 个信号日，(\d+) 条记录，平均 ([\d.]+) 只/日",
                          pool_out)
            if m:
                result["pool"] = {"signal_days": int(m.group(1)),
                                  "rows": int(m.group(2)),
                                  "avg_size": float(m.group(3))}
            code, val_out = _run_step(validate_cmd, job_dir)
            parsed = parse_validate_stdout(val_out)
            report_path = parsed.get("report_path")
            if report_path and Path(report_path).exists():
                try:
                    summary = parse_report_summary(
                        Path(report_path).read_text(encoding="utf-8"))
                    result.update(summary)
                except OSError:
                    pass
            if parsed.get("verdict") and not result.get("verdict"):
                result["verdict"] = parsed["verdict"]
            if report_path:
                result["report_path"] = report_path
            if code != 0:
                result["error"] = "四关验证执行失败（详见日志）"
            elif not result.get("verdict"):
                result["error"] = "四关验证完成但未能解析结论（详见日志）"
                code = 1
        result["ok"] = code == 0
        result["finished_at"] = _now_iso()
        try:
            (job_dir / "result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8")
        except OSError:
            pass
        if code != 0:
            _append_log(job_dir, f"[deep-validate] failed: "
                        f"{result.get('error')}\n")
        return code

    starter = job_starter or start_script_job
    record = starter(
        lock_key=f"deep-validate:{safe}",
        label=f"深度验证 {name}（{d0}~{d1}）",
        cmd=pool_cmd + ["&&"] + validate_cmd,  # 展示用
        cwd=CLUSTER_REPO,
        runner=_worker if runner is None else runner,
    )
    return {"ok": True, "job_id": record["job_id"], "status": record["status"],
            "strategy": name, "d0": d0, "d1": d1,
            "conditions_path": str(conditions_path)}
