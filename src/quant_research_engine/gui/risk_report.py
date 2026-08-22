"""回测 run 风险分析集成（FRM 风险模块 R3）。

- ``extract_strategy_returns(record)``：从 run 产物定位组合级
  ``equity_curve.csv``（per-symbol 目录下的单标的文件排除），取
  ``daily_return`` 列（缺则 ``total_equity.pct_change()`` 退化），
  trade_date → DatetimeIndex（stress 情景窗口按日期切片需要）；
  若有 ``benchmark_close`` 列则一并返回基准逐日收益。
- ``finalize_risk_report(record)``：run 收尾钩子（engine 调用方负责
  try/except 兜底）。仅 completed run；调
  ``risk.report.build_risk_report``（var_backtest 默认开、stress 开、
  bootstrap 关——太慢，留给按需任务），JSON 原子写
  ``runs/<run_id>/risk_report.json``；markdown 节追加到产物
  ``summary.md``（幂等：先移除既有「## 风险分析」节再追加），
  无 summary.md 时写 ``runs/<run_id>/risk_report.md``。
- ``start_risk_report_job(record)``：按需生成（bootstrap 开），复用
  daily_jobs 的 start_script_job（lock_key=risk-report:<run_id>，
  in-process runner，不写 cmd）。
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd

from quant_research_engine.gui.engine import RUNS_DIR

RISK_SECTION_HEADER = "## 风险分析"


def risk_report_path(run_id: str) -> Path:
    return RUNS_DIR / run_id / "risk_report.json"


def load_risk_report(run_id: str) -> dict[str, Any] | None:
    """读取已生成的 risk_report.json；不存在/损坏返回 None。"""
    path = risk_report_path(run_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def evaluate_gate_risk(run_id: str | None) -> dict[str, Any]:
    """晋升闸风险判据（R4）：读 run 的 risk_report.json 给闸的 risk 节。

    - report 不存在/损坏 → ``status="unavailable"``（不判风险项、不阻断）。
    - ES99（历史模拟，日收益损失口径）> ``risk.constants.GATE_ES99_MAX``
      或 ``GATE_VAR_CONFIDENCE`` 节覆盖率 Kupiec LR 检验被拒绝（5% 显著）
      → ``status="warning"``，``reasons`` 记录触发项；否则 ``"ok"``。
    - 关键字段缺失（老格式 report）时该子项记 None、不触发 warning。
    """
    from quant_research_engine.risk import constants as risk_constants

    threshold = risk_constants.GATE_ES99_MAX
    var_conf = risk_constants.GATE_VAR_CONFIDENCE
    level_key = f"{int(round(var_conf * 100))}pct"
    risk: dict[str, Any] = {
        "status": "unavailable",
        "es99": None,
        "es99_threshold": threshold,
        "var_lr_reject": None,
        "var_confidence": var_conf,
        "reasons": [],
        "report_run_id": run_id,
    }
    if not run_id:
        return risk
    report = load_risk_report(str(run_id))
    if report is None:
        return risk

    tail = report.get("tail") or {}
    es99 = (((tail.get(level_key) or {}).get("historical_simulation") or {}).get("es"))
    var_bt = report.get("var_backtest") or {}
    coverage = ((var_bt.get("levels") or {}).get(level_key) or {}).get("coverage") or {}
    var_lr_reject = coverage.get("reject_5pct")

    risk["es99"] = es99 if isinstance(es99, (int, float)) else None
    risk["var_lr_reject"] = bool(var_lr_reject) if var_lr_reject is not None else None
    if risk["es99"] is not None and risk["es99"] > threshold:
        risk["reasons"].append("es99_exceeds_threshold")
    if risk["var_lr_reject"]:
        risk["reasons"].append("var_lr_rejected")
    risk["status"] = "warning" if risk["reasons"] else "ok"
    return risk


def _find_portfolio_equity_curve(record: dict[str, Any]) -> Path | None:
    """定位组合级 equity_curve.csv。

    优先产物树顶层 / backtest 目录下的组合级文件（列头含 daily_return 或
    total_equity 且不含 symbol 列）；per-symbol 目录（父目录名像股票代码）
    的文件排除。
    """
    candidates: list[Path] = []
    artifacts = record.get("artifacts") or {}
    for rel, abs_path in artifacts.items():
        if Path(rel).name == "equity_curve.csv" and Path(abs_path).exists():
            candidates.append(Path(abs_path))
    output_dir = record.get("output_dir")
    if output_dir and Path(output_dir).exists():
        for p in sorted(Path(output_dir).rglob("equity_curve.csv")):
            if p.is_file() and p not in candidates:
                candidates.append(p)

    def _is_portfolio_level(path: Path) -> bool:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                header = fh.readline().strip().split(",")
        except OSError:
            return False
        if "symbol" in header:
            return False
        return "daily_return" in header or "total_equity" in header

    portfolio = [p for p in candidates if _is_portfolio_level(p)]
    if not portfolio:
        return None
    # 有 daily_return 列的组合级文件优先（引擎组合口径，最小加工）。
    def _sort_key(path: Path) -> tuple[int, int]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                header = fh.readline()
        except OSError:
            header = ""
        return (0 if "daily_return" in header else 1, len(path.parts))

    return sorted(portfolio, key=_sort_key)[0]


def extract_strategy_returns(
    record: dict[str, Any],
) -> tuple[pd.Series, pd.Series | None] | None:
    """从 run 产物提取 (策略逐日收益, 基准逐日收益|None)；无产物返回 None。"""
    csv_path = _find_portfolio_equity_curve(record)
    if csv_path is None:
        return None
    try:
        frame = pd.read_csv(csv_path)
    except (OSError, ValueError):
        return None
    if "trade_date" not in frame.columns or frame.empty:
        return None

    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
    frame = frame.dropna(subset=["trade_date"]).sort_values("trade_date")
    frame = frame.set_index("trade_date")

    if "daily_return" in frame.columns:
        returns = pd.to_numeric(frame["daily_return"], errors="coerce").dropna()
    elif "total_equity" in frame.columns:
        equity = pd.to_numeric(frame["total_equity"], errors="coerce").dropna()
        returns = equity.pct_change().dropna()
    else:
        return None
    if len(returns) < 2:
        return None

    benchmark: pd.Series | None = None
    if "benchmark_close" in frame.columns:
        bench_close = pd.to_numeric(frame["benchmark_close"], errors="coerce").dropna()
        benchmark = bench_close.pct_change().dropna()
        if len(benchmark) < 2:
            benchmark = None
    return returns, benchmark


def generate_risk_report(
    record: dict[str, Any],
    *,
    bootstrap: bool = False,
) -> dict[str, Any] | None:
    """生成风险报告并落盘（JSON + markdown 节）。无法提取收益时返回 None。"""
    from quant_research_engine.risk.report import build_risk_report, render_risk_markdown

    extracted = extract_strategy_returns(record)
    if extracted is None:
        return None
    returns, benchmark = extracted

    report = build_risk_report(
        returns,
        benchmark=benchmark,
        config={
            "var_backtest": True,
            "stress": True,
            "bootstrap": bootstrap,
        },
    )
    report["meta"]["run_id"] = record.get("run_id")
    report["meta"]["bootstrap_on_demand"] = bootstrap

    run_dir = RUNS_DIR / str(record.get("run_id"))
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(risk_report_path(str(record.get("run_id"))), report)

    markdown = render_risk_markdown(report)
    summary_md = _find_summary_md(record)
    if summary_md is not None:
        _append_section_idempotent(summary_md, markdown)
    else:
        (run_dir / "risk_report.md").write_text(markdown, encoding="utf-8")
    return report


def finalize_risk_report(record: dict[str, Any]) -> dict[str, Any] | None:
    """run 收尾钩子：仅 completed run 自动生成（bootstrap 关）。

    调用方（engine._execute_and_finalize）负责 try/except 兜底，
    与 finalize_smoke / finalize_promotion_gate 同模式。
    """
    if record.get("status") != "completed":
        return None
    return generate_risk_report(record, bootstrap=False)


def start_risk_report_job(record: dict[str, Any]) -> dict[str, Any]:
    """按需生成风险分析（bootstrap 开），异步 job 复用 daily_jobs 基建。

    同一 run 重入抛 RuntimeError（路由层转 409）。
    """
    from quant_research_engine.gui.daily_jobs import start_script_job

    run_id = str(record.get("run_id"))

    def _runner(cmd: list[str], cwd: Path, job_dir: Path) -> int:
        log = job_dir / "output.log"
        job_dir.mkdir(parents=True, exist_ok=True)
        report = generate_risk_report(record, bootstrap=True)
        if report is None:
            log.write_text("未能从 run 产物提取逐日收益（缺组合级 equity_curve.csv）\n", encoding="utf-8")
            return 1
        log.write_text(
            f"risk_report.json 已生成（n={report['meta']['n_obs']}，bootstrap=开）\n",
            encoding="utf-8",
        )
        return 0

    return start_script_job(
        lock_key=f"risk-report:{run_id}",
        label=f"风险分析生成 run {run_id}",
        cmd=[],
        cwd=RUNS_DIR,
        runner=_runner,
    )


# --- internals ---


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _find_summary_md(record: dict[str, Any]) -> Path | None:
    """产物里的报告 markdown（summary.md）；优先 backtest 目录下组合级。"""
    artifacts = record.get("artifacts") or {}
    candidates: list[Path] = []
    for rel, abs_path in artifacts.items():
        if Path(rel).name == "summary.md" and Path(abs_path).exists():
            candidates.append(Path(abs_path))
    output_dir = record.get("output_dir")
    if output_dir and Path(output_dir).exists():
        for p in sorted(Path(output_dir).rglob("summary.md")):
            if p.is_file() and p not in candidates:
                candidates.append(p)
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: len(p.parts))[0]


def _append_section_idempotent(md_path: Path, section_md: str) -> None:
    """追加「## 风险分析」节；已存在则先移除旧节（到下一个同级标题或 EOF）。"""
    try:
        text = md_path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    lines = text.splitlines()
    out: list[str] = []
    skip = False
    for line in lines:
        if line.strip().startswith(RISK_SECTION_HEADER):
            skip = True
            continue
        if skip and line.startswith("## "):
            skip = False
        if not skip:
            out.append(line)
    new_text = "\n".join(out).rstrip() + "\n\n" + section_md.rstrip() + "\n"
    md_path.write_text(new_text, encoding="utf-8")
