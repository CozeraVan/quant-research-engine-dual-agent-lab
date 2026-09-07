"""runner：执行一个 leased job，产出可回传云端的 summary + chart_data。

执行链路完全复用 8081 回测台的既有路径，不 fork 引擎：

1. job 的 strategies.yaml + params → ``gui.engine.run_backtest(...)``
   （与 /api/strategies/<id>/run 同一入口；module executor 进程内执行，
   status.json/stdout.log/artifacts 落 outputs/gui-console/runs/<run_id>）。
2. kind=smoke → run_backtest(precheck=True)，即既有小样本预检
   （apply_precheck：前 20 只 + 截 180 天窗口）；kind=full → 全量参数原样。
3. 跑完后 summary = ``gui.engine.extract_run_summary``（优先
   strategy_performance.json，回退 stdout key=value）；
   chart_data = ``gui.lab_result.build_lab_chart_data``（与 8081 结果页
   同一序列化逻辑；基准指数查库失败时自动降级为 note，不影响回传）。
4. artifacts 恒为 []——Excel/CSV 明细上 OSS 是 M4 的事（TODO(M4)）。

本地大库连接：run_backtest(db_url=None) 时引擎走
DatabaseSettings.from_env()（QRE_MARKET_DB_URL），Worker 部署用只读账号
qre_worker_ro 的连接串注入该环境变量即可；引擎数据层（data/postgres.py、
assembler、portfolio/*）经核查只发 SELECT，全部写入均为本地文件
（run 目录 status.json/stdout.log/risk_report.json），只读账号可跑通。

params 约定（全部可选）：
    codes: list[str]（缺省=全市场）, start/end: YYYY-MM-DD（缺省=近 2 年）,
    mode: "shared"(默认)/"batch"/"single", initial_cash, max_positions,
    engine_impl, stop_loss_pct, take_profit_pct, trailing_stop_pct,
    profile_overrides: dict
"""

from __future__ import annotations

import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from quant_research_engine.gui.engine import extract_run_summary, run_backtest

DEFAULT_START_YEARS = 2


def _job_params(job: dict[str, Any]) -> dict[str, Any]:
    params = job.get("params") or {}
    return params if isinstance(params, dict) else {}


def execute_job(job: dict[str, Any], *, work_base: str | Path | None = None) -> dict[str, Any]:
    """执行 leased job，返回 result 回传 payload（不含 status 字段）。

    回测失败抛 RuntimeError（调用方负责回传 failed）。
    """
    strategy = job.get("strategy") or {}
    yaml_text = str(strategy.get("yaml") or "").strip()
    if not yaml_text:
        raise RuntimeError("job 缺少策略 yaml")
    # QRE-SAAS-005：公网 NL 产物前置安全闸——严格 schema + 信号表达式 AST 白名单
    # （引擎表达式求值器允许任意 getattr/方法调用，必须在执行前锁死）。
    from quant_research_engine.security.yaml_guard import validate_strategy_yaml

    verdict = validate_strategy_yaml(yaml_text)
    if not verdict["ok"]:
        raise RuntimeError("策略 YAML 未通过安全校验：" + "；".join(verdict["issues"]))
    params = _job_params(job)

    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    end = str(params.get("end") or date.today().isoformat())
    start = str(
        params.get("start")
        or (date.fromisoformat(end) - timedelta(days=365 * DEFAULT_START_YEARS)).isoformat()
    )

    # 产物目录独立（worker 本地临时区），run 记录仍走既有 RUNS_DIR
    base = Path(work_base) if work_base else Path(tempfile.mkdtemp(prefix=f"qre-worker-job{job.get('id')}-"))
    output_dir = base / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)

    record = run_backtest(
        yaml_text=yaml_text,
        mode=str(params.get("mode") or "shared"),
        start=start,
        end=end,
        codes=",".join(codes),
        initial_cash=(str(params["initial_cash"]) if params.get("initial_cash") is not None else None),
        max_positions=(str(params["max_positions"]) if params.get("max_positions") is not None else None),
        output_dir=str(output_dir),
        db_url=params.get("db_url") or os.environ.get("QRE_MARKET_DB_URL"),
        profile_overrides=params.get("profile_overrides"),
        engine_impl=str(params.get("engine_impl") or "simulator"),
        stop_loss_pct=params.get("stop_loss_pct"),
        take_profit_pct=params.get("take_profit_pct"),
        trailing_stop_pct=params.get("trailing_stop_pct"),
        precheck=(job.get("kind") == "smoke"),
        background=False,
    )
    if record.get("status") != "completed":
        raise RuntimeError(f"回测失败：{record.get('error') or '未知错误'}")

    summary = (extract_run_summary(record) or {}).get("metrics") or {}
    summary["run_id"] = record.get("run_id")
    summary["kind"] = job.get("kind")

    from quant_research_engine.gui.lab_result import build_lab_chart_data, build_lab_tag_analysis

    chart_data = build_lab_chart_data(record)
    # 板块/个股归因：与 8081 结果页同一组装函数（数据形态完全一致），
    # 截断后挂到 chart_data.tag_analysis（体积控制见 trim_tag_analysis）。
    try:
        chart_data["tag_analysis"] = trim_tag_analysis(build_lab_tag_analysis(record))
    except Exception:
        chart_data["tag_analysis"] = None  # 归因失败不拖垮回传（DB 降级等）

    # 数据截止日期（静态快照声明）：优先净值曲线末日，回退 run 区间末日
    dates = chart_data.get("dates") or []
    data_until = summary.get("date_end") or (dates[-1] if dates else None) or end

    return {
        "summary": summary,
        "chart_data": chart_data,
        "artifacts": [],  # TODO(M4)：Excel/CSV 明细上传 OSS 后在此登记 oss_key
        "data_until": str(data_until),
    }


#: 归因回传截断口径：板块/标签聚合全量保留（热力图与榜单所需），
#: 每个板块内的个股明细只留按 |总净盈亏| 排序的 TOP/BOTTOM 各 TAG_SYMBOL_TOP_N 只
#: （全市场 run 可能几千只，全量回传会让 results.chart_data 爆到 MB 级）；
#: 附 symbols_total 记录截断前数量，前端可提示「仅显示前/后 N」。
TAG_SYMBOL_TOP_N = 50


def trim_tag_analysis(data: dict[str, Any], top_n: int = TAG_SYMBOL_TOP_N) -> dict[str, Any]:
    """截断 build_lab_tag_analysis 的个股明细（纯函数）。"""
    if not isinstance(data, dict):
        return data
    trimmed = dict(data)
    layers = {}
    for layer, items in (data.get("layers") or {}).items():
        new_items = []
        for item in items or []:
            item = dict(item)
            symbols = item.get("symbols") or []
            item["symbols_total"] = len(symbols)
            if len(symbols) > top_n * 2:
                # symbols 已按 total_pnl 降序；取头部 top_n + 尾部 top_n
                item["symbols"] = symbols[:top_n] + symbols[-top_n:]
                item["symbols_truncated"] = True
            else:
                item["symbols_truncated"] = False
            new_items.append(item)
        layers[layer] = new_items
    trimmed["layers"] = layers
    return trimmed
