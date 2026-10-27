"""8081 回测台专属：ECharts 回测结果页（QRE-GUI-LAB-RESULT-023）。

只在 ``create_lab_app()`` 里注册，8080 管理台的 ``/runs/<run_id>``
（strategy_lab_routes + run_detail.html）保持零改动。

路由：
- ``GET /lab/runs/<run_id>``                  渲染 lab_result.html
- ``GET /api/lab/runs/<run_id>/chart-data``   图表数据 JSON
- ``GET /api/lab/runs/<run_id>/tag-analysis`` 赚钱效应归因 JSON（QRE-GUI-LAB-RESULT-024）

数据全部来自本地已有产物（equity_curve.csv / drawdown_curve.csv /
round_trips.csv / strategy_performance.json / risk_report.json）、
本地 PostgreSQL ``reference.index_daily`` 基准指数日线与
``cluster.company_tags`` 板块/关键词/动态标签，不造数据；
任一数据源缺失时对应字段为 None / 空数组 + note，由前端显示「暂无数据」。

QRE-GUI-LAB-RESULT-031：
- chart-data 新增 ``meta`` 块（回测参数信息条：区间/标的/资金/持仓/引擎/费率）。
- 新增 ``GET /api/lab/runs/<run_id>/risk-analysis``：FRM 风险报告
  （risk_report.json）转为前端图表就绪 JSON；无报告时 has_report=False，
  前端显示「生成风险报告」按钮走共享的 POST /api/runs/<id>/risk-report。

QRE-GUI-CONSOL-040（8081「回测管理」tab 改造为回测记录列表）：
- ``GET /api/lab/runs``：list_runs() 增强列表（+strategy_name/symbol_count，
  按创建时间倒序）。
- ``POST /api/lab/runs/<run_id>/delete``：删除 RUNS_DIR/<run_id> 目录
  （run_id 白名单校验防路径穿越；不动 request.json 里 output_dir 产物目录）。
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

from quant_research_engine.gui import engine as _engine
from quant_research_engine.gui.engine import _find_output_file, get_run

# 基准指数候选（默认第一个：上证指数）
BENCHMARKS: list[tuple[str, str]] = [
    ("000001.SH", "上证指数"),
    ("000300.SH", "沪深300"),
    ("000905.SH", "中证500"),
    ("000852.SH", "中证1000"),
    ("399006.SZ", "创业板指"),
]

# 买卖点散点上限：超过时按 |net_return| 保留 top N 并标注 sampled
TRADE_SCATTER_LIMIT = 500


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _f(value: str | None) -> float | None:
    try:
        return round(float(value), 6) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _equity_series(
    record: dict[str, Any],
) -> tuple[list[str], list[float | None], list[float | None] | None] | None:
    """返回 (dates, total_equity 序列, cumulative_return 序列|None)。

    cumulative_return 口径（faf9629 起由引擎写入）：交集口径日收益累乘的
    累计收益率（小数，如 0.15 = +15%），与 dates 等长；新股注资不贡献收益。
    旧产物缺该列时第三项为 None（调用方不落 cumret 键，前端回退旧口径）。
    """
    path = _find_output_file(record, "equity_curve.csv")
    if path is None:
        return None
    try:
        rows = _read_csv(path)
    except OSError:
        return None
    dates: list[str] = []
    equity: list[float | None] = []
    cumret: list[float | None] = []
    has_cumret = False
    for row in rows:
        d = (row.get("trade_date") or "").strip()
        v = _f(row.get("total_equity"))
        c = _f(row.get("cumulative_return"))
        if c is not None:
            has_cumret = True
        if d and v is not None:
            dates.append(d)
            equity.append(v)
            cumret.append(c)
    if not dates:
        return None
    return (dates, equity, cumret if has_cumret else None)


def _drawdown_series(record: dict[str, Any], dates: list[str]) -> list[float | None] | None:
    path = _find_output_file(record, "drawdown_curve.csv")
    if path is None:
        return None
    try:
        rows = _read_csv(path)
    except OSError:
        return None
    by_date = {(r.get("trade_date") or "").strip(): _f(r.get("drawdown_pct")) for r in rows}
    series = [by_date.get(d) for d in dates]
    return series if any(v is not None for v in series) else None


def _benchmark_series(dates: list[str]) -> tuple[dict[str, dict[str, Any]], str | None]:
    """从 reference.index_daily 取 5 个指数收盘，按策略交易日对齐（缺失补 None）。

    DB 不可用或表为空时返回 ({}, 错误说明)，前端降级为「暂无数据」。
    """
    if not dates:
        return {}, None
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            # 无 QRE_MARKET_DB_URL 环境变量时回退本地库默认连接串
            store = _store(DEFAULT_DB_URL)
        with store.market_engine.begin() as conn:
            rows = conn.execute(
                text(
                    "SELECT ts_code, trade_date, close FROM reference.index_daily "
                    "WHERE ts_code = ANY(:codes) AND trade_date BETWEEN :d0 AND :d1 "
                    "ORDER BY trade_date"
                ),
                {"codes": list(c for c, _ in BENCHMARKS), "d0": dates[0], "d1": dates[-1]},
            ).fetchall()
    except Exception as exc:  # DB 不可用：降级不报错
        return {}, f"基准指数数据不可用（{exc}）"
    closes: dict[str, dict[str, float]] = {code: {} for code, _ in BENCHMARKS}
    for ts_code, trade_date, close in rows:
        if close is not None:
            closes[ts_code][str(trade_date)] = float(close)
    result: dict[str, dict[str, Any]] = {}
    for code, name in BENCHMARKS:
        series = [closes[code].get(d) for d in dates]
        if any(v is not None for v in series):
            result[code] = {"name": name, "closes": series}
    if not result:
        return {}, "基准指数数据不可用（reference.index_daily 无该区间数据）"
    return result, None


def _trade_points(record: dict[str, Any]) -> dict[str, Any] | None:
    path = _find_output_file(record, "round_trips.csv")
    if path is None:
        return None
    try:
        rows = _read_csv(path)
    except OSError:
        return None
    points = []
    for r in rows:
        entry = (r.get("entry_date") or "").strip()
        exit_ = (r.get("exit_date") or "").strip()
        ret = _f(r.get("net_return"))
        if entry and exit_ and ret is not None:
            point = {
                "symbol": (r.get("symbol") or "").strip(),
                "entry_date": entry,
                "exit_date": exit_,
                "net_return": ret,
            }
            # QRE-SAAS-REPLAY-BOUNDARIES：round_trips.csv 本就写入价量列时补足到
            # 散点（重播事件源与 chip 文案用）；缺列不加键（不造值），旧产物自然
            # 降级为纯标的。仅对新生成的 run 生效，不回填历史。
            for key in ("quantity", "entry_price", "exit_price"):
                value = _f(r.get(key))
                if value is not None:
                    point[key] = value
            points.append(point)
    if not points:
        return None
    sampled = len(points) > TRADE_SCATTER_LIMIT
    if sampled:
        points.sort(key=lambda p: abs(p["net_return"]), reverse=True)
        points = points[: TRADE_SCATTER_LIMIT]
    return {"points": points, "total": len(rows), "sampled": sampled}


def _strategy_brief(record: dict[str, Any], perf: dict[str, Any] | None) -> dict[str, str]:
    """策略简介（名称 + 一句话开平仓描述），页面顶部小字展示。"""
    brief: dict[str, str] = {}
    if perf:
        name = perf.get("strategy_name") or perf.get("strategy_id")
        if name:
            brief["name"] = str(name)
    # 从 run 目录 strategy.yaml 的头部注释提取「策略名称/说明」
    from quant_research_engine.gui.engine import RUNS_DIR

    strategy_yaml = RUNS_DIR / record.get("run_id", "") / "strategy.yaml"
    if strategy_yaml.exists():
        try:
            for line in strategy_yaml.read_text(encoding="utf-8").splitlines():
                line = line.strip().lstrip("#").strip()
                if line.startswith("策略名称"):
                    brief.setdefault("name", line.partition(":")[2].strip())
                elif line.startswith("说明"):
                    brief["desc"] = line.partition(":")[2].strip()
                if "name" in brief and "desc" in brief:
                    break
        except OSError:
            pass
    return brief


def _fees_summary(record: dict[str, Any]) -> dict[str, Any] | None:
    """交易磨损汇总（QRE-LAB-UI-LANDING）：聚合 round_trips.csv 的真实费用列。

    返回佣金/印花税/过户费/总费用/毛收益/净收益/买入成交额合计与交易笔数；
    round_trips.csv 缺失或字段不全时返回 None（前端整块降级隐藏，不编数）。
    """
    path = _find_output_file(record, "round_trips.csv")
    if path is None:
        return None
    try:
        rows = _read_csv(path)
    except OSError:
        return None
    if not rows:
        return None
    agg = {"commission": 0.0, "stamp_tax": 0.0, "transfer_fee": 0.0,
           "total_cost": 0.0, "gross_pnl": 0.0, "net_pnl": 0.0, "invested": 0.0}
    for r in rows:
        for key, col in (("commission", "commission"), ("stamp_tax", "stamp_tax"),
                         ("transfer_fee", "transfer_fee"), ("total_cost", "total_cost"),
                         ("gross_pnl", "gross_pnl"), ("net_pnl", "net_pnl"),
                         ("invested", "entry_notional")):
            agg[key] += _f(r.get(col)) or 0.0
    if agg["invested"] <= 0 and agg["total_cost"] <= 0:
        return None
    out = {k: round(v, 2) for k, v in agg.items()}
    out["trades"] = len(rows)
    # 滑点未单列：引擎 price==price_raw 时默认无滑点，残差并入「过户费/滑点等」由前端口径说明
    out["other_cost"] = round(agg["total_cost"] - agg["commission"] - agg["stamp_tax"], 2)
    return out


def build_lab_chart_data(record: dict[str, Any]) -> dict[str, Any]:
    """组装 /api/lab/runs/<id>/chart-data 的 JSON payload。"""
    data: dict[str, Any] = {"ok": True, "run_id": record.get("run_id")}

    perf: dict[str, Any] | None = None
    perf_path = _find_output_file(record, "strategy_performance.json")
    if perf_path is not None:
        try:
            loaded = json.loads(perf_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                perf = loaded
        except (json.JSONDecodeError, OSError):
            perf = None

    data["brief"] = _strategy_brief(record, perf)
    data["meta"] = _run_meta(record, data["brief"])

    metrics: dict[str, Any] = {}
    if perf:
        total = perf.get("strategy_total_return")
        buy_hold = perf.get("buy_hold_return")
        excess = perf.get("excess_return_vs_buy_hold")
        # 引擎目前不写 excess/date_start/date_end（恒 None），降级为现算/取 run 区间
        if excess is None and isinstance(total, (int, float)) and isinstance(buy_hold, (int, float)):
            excess = total - buy_hold
        date_start = perf.get("date_start") or record.get("start")
        date_end = perf.get("date_end") or record.get("end")
        metrics = {
            "total_return": total,
            "excess_return": excess,
            "buy_hold_return": buy_hold,
            "sharpe": perf.get("sharpe"),
            "max_drawdown": perf.get("max_drawdown"),
            "win_rate": perf.get("win_rate"),
            "date_start": date_start,
            "date_end": date_end,
        }
        if isinstance(total, (int, float)) and date_start and date_end:
            try:
                from datetime import date as _date

                d0 = _date.fromisoformat(str(date_start))
                d1 = _date.fromisoformat(str(date_end))
                years = max((d1 - d0).days / 365.25, 1 / 365.25)
                metrics["annual_return"] = round((1 + total) ** (1 / years) - 1, 6)
            except (ValueError, OverflowError, ZeroDivisionError):
                metrics["annual_return"] = None
    data["metrics"] = metrics or None

    eq = _equity_series(record)
    if eq is None:
        data["dates"] = None
        data["equity"] = None
        data["cumret"] = None
        data["drawdown_pct"] = None
        data["benchmarks"] = None
    else:
        dates, equity, cumret = eq
        data["dates"] = dates
        data["equity"] = equity
        # cumret：交集口径累计收益率（小数，与 dates 等长），faf9629 后产物才有；
        # 旧产物（无 cumulative_return 列）不落键，前端回退 equity/base−1 旧口径
        if cumret is not None:
            data["cumret"] = cumret
        data["drawdown_pct"] = _drawdown_series(record, dates)
        benchmarks, bench_note = _benchmark_series(dates)
        data["benchmarks"] = benchmarks or None
        data["benchmark_note"] = bench_note

    trades = _trade_points(record)
    data["trades"] = trades
    data["fees_summary"] = _fees_summary(record)
    return data


# --- 赚钱效应归因（QRE-GUI-LAB-RESULT-024） ---

# B 层关键词 treemap 矩块上限：超出部分不显示
LAYER_B_TOP_N = 20

# B 层关键词停用词表（QRE-GUI-LAB-RESULT-027）：无行业/概念指向的泛词。
# 宁多滤勿留噪声；只作用于 B 层，A 层（行业分类）与 C 层（动态标签）不过滤。
NOISE_KEYWORDS: frozenset[str] = frozenset({
    # 通用泛词
    "其他", "有关", "相关", "国际", "公司", "集团", "股份", "科技", "发展",
    "投资", "控股", "中国", "企业", "业务", "产品", "项目", "服务", "技术",
    "产业", "行业", "市场", "系统", "设备", "材料", "信息", "电子", "网络",
    "智能", "数据", "管理", "工程", "建设", "制造", "生产", "销售", "综合",
    "通用", "领域", "方案", "平台", "应用", "研究", "开发", "设计", "数字",
    "高新", "新技术", "实业", "一体化", "国内", "全球", "全国", "龙头",
    "概念", "板块", "资源", "产品等", "有限公司", "股份有限公司",
    # 公司简介里截断出来的句子残片常用词
    "主营", "主要", "从事", "致力于", "专业", "领先", "知名", "优质",
    "一家", "提供商", "服务商", "制造商", "供应商", "运营商",
})

# 短英文白名单：本身是公认概念缩写，不按「无意义短英文」丢弃
_ASCII_TAG_WHITELIST: frozenset[str] = frozenset({
    "AI", "5G", "6G", "VR", "AR", "MR", "XR", "IoT", "CPO", "GPU", "CPU",
    "PCB", "HBM", "EDA", "MCU", "SoC", "LED", "OLED", "EV", "PEEK", "FSD",
    "PPP", "IDC", "AIGC", "AGI", "LLM", "API", "IP",
})

_TAG_MAX_LEN = 12


def is_noise_keyword(tag: str) -> bool:
    """B 层关键词是否噪声（纯函数，便于测试与扩充词表）。

    规则：命中停用词表；去空白后单字丢弃；长度 >12 的句子型丢弃；
    纯数字丢弃；纯 ASCII 且不在白名单的短英文（≤3 字符）丢弃。
    """
    t = (tag or "").strip()
    if len(t) <= 1 or len(t) > _TAG_MAX_LEN:
        return True
    if t in NOISE_KEYWORDS:
        return True
    if t.isdigit():
        return True
    if t.isascii() and len(t) <= 3 and t.upper() not in _ASCII_TAG_WHITELIST:
        return True
    return False


def _strip_tag_prefix(tag: str) -> str:
    """A 层 tag 显示名：去掉 `申万L1:`/`申万L2:` 等 `xxx:` 前缀。"""
    return tag.partition(":")[2] if ":" in tag else tag


def _symbol_trade_stats(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """按个股聚合 round_trips：total_pnl / trades / sum_ret / wins /
    best_ret / worst_ret（净收益率最值）/ sum_hold·hold_n（平均持仓天数用）。"""
    path = _find_output_file(record, "round_trips.csv")
    if path is None:
        return {}
    try:
        rows = _read_csv(path)
    except OSError:
        return {}
    stats: dict[str, dict[str, Any]] = {}
    for r in rows:
        sym = (r.get("symbol") or "").strip()
        pnl = _f(r.get("net_pnl"))
        ret = _f(r.get("net_return"))
        hold = _f(r.get("holding_days"))
        if not sym or pnl is None:
            continue
        s = stats.setdefault(sym, {"total_pnl": 0.0, "trades": 0, "sum_ret": 0.0, "wins": 0,
                                   "best_ret": None, "worst_ret": None,
                                   "sum_hold": 0.0, "hold_n": 0})
        s["total_pnl"] += pnl
        s["trades"] += 1
        s["sum_ret"] += ret or 0.0
        if ret is not None:
            s["best_ret"] = ret if s["best_ret"] is None else max(s["best_ret"], ret)
            s["worst_ret"] = ret if s["worst_ret"] is None else min(s["worst_ret"], ret)
        if hold is not None:
            s["sum_hold"] += hold
            s["hold_n"] += 1
        if pnl > 0:
            s["wins"] += 1
    return stats


def _fetch_company_tags(symbols: list[str]) -> tuple[list[tuple[str, str, str]], dict[str, str], str | None]:
    """批量查 cluster.company_tags + reference.stock_basic 名称（一次 IN 查询，不逐股）。

    返回 ([(ts_code, tag, layer)], {ts_code: name}, 错误说明或 None)。
    """
    if not symbols:
        return [], {}, None
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            store = _store(DEFAULT_DB_URL)
        with store.market_engine.begin() as conn:
            tag_rows = conn.execute(
                text(
                    "SELECT ts_code, tag, layer FROM cluster.company_tags "
                    "WHERE ts_code = ANY(:codes)"
                ),
                {"codes": symbols},
            ).fetchall()
            name_rows = conn.execute(
                text("SELECT ts_code, name FROM reference.stock_basic WHERE ts_code = ANY(:codes)"),
                {"codes": symbols},
            ).fetchall()
    except Exception as exc:  # DB 不可用：降级不报错
        return [], {}, f"标签数据不可用（{exc}）"
    names = {ts: (nm or "") for ts, nm in name_rows}
    return [(ts, tag, layer) for ts, tag, layer in tag_rows], names, None


def _fetch_industries(symbols: list[str]) -> dict[str, str]:
    """reference.stock_basic 的通用行业（tushare industry 字段），供 A 层兜底：
    申万行业标签不覆盖北交所个股，无 A 层 tag 时用通用行业入块（显示名加 ·通用 后缀）。
    DB 失败返回空 dict（调用方退化为「未标记」），不报错。
    """
    if not symbols:
        return {}
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            store = _store(DEFAULT_DB_URL)
        with store.market_engine.begin() as conn:
            rows = conn.execute(
                text("SELECT ts_code, industry FROM reference.stock_basic WHERE ts_code = ANY(:codes)"),
                {"codes": symbols},
            ).fetchall()
    except Exception:
        return {}
    return {ts: ind for ts, ind in rows if ind}


def _aggregate_tag_layers(
    stats: dict[str, dict[str, Any]],
    tag_rows: list[tuple[str, str, str]],
    names: dict[str, str],
    industries: dict[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """纯函数：个股交易统计 × 标签行 → A/B/C 三层 tag 聚合（含个股分位）。

    分位 = 按 total_pnl 在全 run 交易个股中的排名百分位（1-based rank / N，
    越小越靠前，前端显示「前 X.X%」）。
    A 层只保留 `申万L1:` 前缀的一级行业（QRE-GUI-LAB-RESULT-029，去掉前缀显示）；
    申万不覆盖的股票（北交所等）用 industries（stock_basic 通用行业）兜底，
    显示名加 `·通用` 后缀区分分类体系（QRE-GUI-CONSOL-045）；
    每层把没有任何该层 tag 的交易个股归入「未标记」块；B 层先经 is_noise_keyword
    过滤停用词（A/C 层不过滤），只保留按 |总净盈亏| 排序的前 LAYER_B_TOP_N 个，
    其余不显示（无合并块）。
    """
    layers: dict[str, dict[str, dict[str, Any]]] = {"A": {}, "B": {}, "C": {}}
    tagged: dict[str, set[str]] = {"A": set(), "B": set(), "C": set()}
    seen: set[tuple[str, str, str]] = set()  # (layer, 显示名, ts_code) 去重：A 层去前缀后同名只计一次
    for ts_code, tag, layer in tag_rows:
        s = stats.get(ts_code)
        if s is None or layer not in layers:
            continue
        if layer == "A":
            if not tag.startswith("申万L1:"):  # 029：A 层只留申万一级行业
                continue
            tag = _strip_tag_prefix(tag)
        elif layer == "B" and is_noise_keyword(tag):
            continue
        if (layer, tag, ts_code) in seen:
            continue
        seen.add((layer, tag, ts_code))
        tagged[layer].add(ts_code)
        bucket = layers[layer].setdefault(tag, {"tags": tag, "symbols": set(), "total_pnl": 0.0,
                                                "trades": 0, "sum_ret": 0.0, "wins": 0})
        bucket["symbols"].add(ts_code)
        bucket["total_pnl"] += s["total_pnl"]
        bucket["trades"] += s["trades"]
        bucket["sum_ret"] += s["sum_ret"]
        bucket["wins"] += s["wins"]

    # A 层兜底：无申万行业标签的个股（北交所等）按 stock_basic 通用行业入块，
    # 显示名加 ·通用 后缀区分分类体系；无通用行业的仍归「未标记」。
    if industries:
        for sym in set(stats) - tagged["A"]:
            ind = industries.get(sym)
            if not ind:
                continue
            tag = f"{ind}·通用"
            tagged["A"].add(sym)
            bucket = layers["A"].setdefault(tag, {"tags": tag, "symbols": set(), "total_pnl": 0.0,
                                                  "trades": 0, "sum_ret": 0.0, "wins": 0})
            s = stats[sym]
            bucket["symbols"].add(sym)
            bucket["total_pnl"] += s["total_pnl"]
            bucket["trades"] += s["trades"]
            bucket["sum_ret"] += s["sum_ret"]
            bucket["wins"] += s["wins"]

    # 缺该层任何 tag 的交易个股 → 「未标记」块
    for layer in layers:
        untagged = set(stats) - tagged[layer]
        if untagged:
            bucket = {"tags": "未标记", "symbols": untagged, "total_pnl": 0.0,
                      "trades": 0, "sum_ret": 0.0, "wins": 0}
            for sym in untagged:
                s = stats[sym]
                bucket["total_pnl"] += s["total_pnl"]
                bucket["trades"] += s["trades"]
                bucket["sum_ret"] += s["sum_ret"]
                bucket["wins"] += s["wins"]
            layers[layer]["未标记"] = bucket

    # 个股分位：total_pnl 降序排名
    ordered = sorted(stats.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True)
    n = len(ordered)
    percentile = {sym: round((i + 1) / n, 4) for i, (sym, _) in enumerate(ordered)}

    result: dict[str, list[dict[str, Any]]] = {}
    for layer, buckets in layers.items():
        items = []
        for tag, b in buckets.items():
            sym_items = []
            for sym in sorted(b["symbols"], key=lambda s: stats[s]["total_pnl"], reverse=True):
                s = stats[sym]
                sym_items.append({
                    "ts_code": sym,
                    "name": names.get(sym, ""),
                    "total_pnl": round(s["total_pnl"], 2),
                    "avg_ret": round(s["sum_ret"] / s["trades"], 6),
                    "trades": s["trades"],
                    "win_rate": round(s["wins"] / s["trades"], 6),
                    "percentile": percentile[sym],
                    # QRE-GUI-LAB-RESULT-027：下钻个股表新增列
                    "best_ret": round(s["best_ret"], 6) if s.get("best_ret") is not None else None,
                    "worst_ret": round(s["worst_ret"], 6) if s.get("worst_ret") is not None else None,
                    "avg_hold_days": round(s["sum_hold"] / s["hold_n"], 2) if s.get("hold_n") else None,
                })
            items.append({
                "tag": tag,
                "total_pnl": round(b["total_pnl"], 2),
                "avg_ret": round(b["sum_ret"] / b["trades"], 6) if b["trades"] else 0.0,
                "trades": b["trades"],
                "win_rate": round(b["wins"] / b["trades"], 6) if b["trades"] else 0.0,
                "symbols": sym_items,
            })
        # treemap 面积口径为 |总净盈亏|，排序同样按绝对值
        items.sort(key=lambda x: abs(x["total_pnl"]), reverse=True)
        # B 层关键词只铺前 LAYER_B_TOP_N 个，其余直接不显示（不做合并块）
        if layer == "B" and len(items) > LAYER_B_TOP_N:
            items = items[:LAYER_B_TOP_N]
        result[layer] = items
    return result


def _fetch_symbol_range_returns(
    symbols: list[str], start: str | None, end: str | None
) -> dict[str, float] | None:
    """批量查 public.stock_daily，算每股区间等权买入持有收益（末收/首收 - 1）。

    一次 IN 查询取全部 ts_code 区间内 (trade_date, close)，按 ts_code 分组在
    Python 里取首末收盘。任一个股区间内不足 2 个交易日则跳过。
    DB 失败 / 无起止日期 / 无数据 → None（降级，不报错）。
    """
    if not symbols or not start or not end:
        return None
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            store = _store(DEFAULT_DB_URL)
        with store.market_engine.begin() as conn:
            import os as _os
            _raw = _os.environ.get("QRE_PRICE_BASIS", "qfq") == "raw"
            _close_expr = "close * adj_factor" if _raw else "close"
            rows = conn.execute(
                text(
                    f"SELECT ts_code, trade_date, {_close_expr} FROM public.stock_daily "
                    "WHERE ts_code = ANY(:codes) AND trade_date BETWEEN :d0 AND :d1 "
                    "ORDER BY ts_code, trade_date"
                ),
                {"codes": symbols, "d0": start, "d1": end},
            ).fetchall()
    except Exception:
        return None
    closes: dict[str, list[float]] = {}
    for ts_code, _trade_date, close in rows:
        if close is not None:
            closes.setdefault(ts_code, []).append(float(close))
    rets = {ts: cs[-1] / cs[0] - 1 for ts, cs in closes.items() if len(cs) >= 2 and cs[0]}
    return rets or None


def _tag_bench_ret(symbols: list[str], rets: dict[str, float] | None) -> float | None:
    """纯函数：板块自然涨幅 = 板块内个股区间收益的等权平均（无数据 → None）。"""
    if not rets:
        return None
    vals = [rets[s] for s in symbols if s in rets]
    return round(sum(vals) / len(vals), 6) if vals else None


def build_lab_tag_analysis(record: dict[str, Any]) -> dict[str, Any]:
    """组装 /api/lab/runs/<id>/tag-analysis 的 JSON payload。"""
    data: dict[str, Any] = {"ok": True, "run_id": record.get("run_id"),
                            "layers": {"A": [], "B": [], "C": []}, "notes": {},
                            "filtered_count": 0}
    stats = _symbol_trade_stats(record)
    if not stats:
        data["notes"] = {"A": "无交易记录", "B": "无交易记录", "C": "无交易记录"}
        return data
    tag_rows, names, err = _fetch_company_tags(list(stats))
    if err:
        data["notes"] = {"A": err, "B": err, "C": err}
        return data
    # B 层停用词过滤计数（去重后的无效关键词个数，前端图下注明）
    data["filtered_count"] = len({
        tag for _, tag, layer in tag_rows if layer == "B" and is_noise_keyword(tag)
    })
    industries = _fetch_industries(list(stats))
    layers = _aggregate_tag_layers(stats, tag_rows, names, industries=industries)
    # QRE-GUI-LAB-RESULT-029：每个 tag 加 bench_ret = 板块内个股在 run 区间的
    # 等权买入持有自然收益；DB 失败整体降级 None，不报错。
    # QRE-GUI-LAB-RESULT-032：bench_ret 同时下沉到个股级（下钻表/个股详情对比用）。
    sym_rets = _fetch_symbol_range_returns(list(stats), record.get("start"), record.get("end"))
    for items in layers.values():
        for item in items:
            item["bench_ret"] = _tag_bench_ret([s["ts_code"] for s in item["symbols"]], sym_rets)
            for s in item["symbols"]:
                v = (sym_rets or {}).get(s["ts_code"])
                s["bench_ret"] = round(v, 6) if v is not None else None
    data["layers"] = layers
    for layer, items in layers.items():
        if not items:
            data["notes"][layer] = "暂无标签数据"
    return data


# --- 个股回测详情（QRE-GUI-LAB-RESULT-026） ---


def _percentile_map(stats: dict[str, dict[str, Any]]) -> dict[str, float]:
    """total_pnl 降序排名百分位（1-based rank / N）。"""
    ordered = sorted(stats.items(), key=lambda kv: kv[1]["total_pnl"], reverse=True)
    n = len(ordered)
    return {sym: round((i + 1) / n, 4) for i, (sym, _) in enumerate(ordered)}


def _read_csv_rounded(path: Path) -> list[dict[str, Any]]:
    """读 CSV 并把可转数字的列 round 到 6 位小数。"""
    rows = []
    for r in _read_csv(path):
        rows.append({k: (_f(v) if isinstance(_f(v), float) else v) for k, v in r.items()})
    return rows


def _symbol_output_dir(record: dict[str, Any], ts_code: str) -> Path | None:
    output_dir = record.get("output_dir")
    if not output_dir:
        return None
    p = Path(output_dir) / ts_code
    return p if p.is_dir() else None


def _fetch_stock_daily(ts_code: str, start: str | None, end: str | None) -> tuple[dict[str, Any] | None, str | None]:
    """DB public.stock_daily 日 K（OHLC + vol），按 run 起止取。失败降级 (None, note)。"""
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            store = _store(DEFAULT_DB_URL)
        with store.market_engine.begin() as conn:
            import os as _os
            if _os.environ.get("QRE_PRICE_BASIS", "qfq") == "raw":
                # 方案A：K线展示锚定最新价（原始价 × fac/fac_latest = 前复权@最新）
                _sql = (
                    "SELECT trade_date, "
                    "open * adj_factor / latest_fac, high * adj_factor / latest_fac, "
                    "low * adj_factor / latest_fac, close * adj_factor / latest_fac, vol "
                    "FROM public.stock_daily s "
                    "JOIN (SELECT adj_factor AS latest_fac FROM public.stock_daily "
                    "      WHERE ts_code = :c ORDER BY trade_date DESC LIMIT 1) t ON true "
                    "WHERE ts_code = :c AND (CAST(:d0 AS date) IS NULL OR trade_date >= CAST(:d0 AS date)) "
                    "AND (CAST(:d1 AS date) IS NULL OR trade_date <= CAST(:d1 AS date)) ORDER BY trade_date"
                )
            else:
                _sql = (
                    "SELECT trade_date, open, high, low, close, vol FROM public.stock_daily "
                    "WHERE ts_code = :c AND (CAST(:d0 AS date) IS NULL OR trade_date >= CAST(:d0 AS date)) "
                    "AND (CAST(:d1 AS date) IS NULL OR trade_date <= CAST(:d1 AS date)) ORDER BY trade_date"
                )
            rows = conn.execute(
                text(_sql),
                {"c": ts_code, "d0": start or None, "d1": end or None},
            ).fetchall()
    except Exception as exc:
        return None, f"行情数据不可用（{exc}）"
    if not rows:
        return None, "该股区间无行情数据"
    return {
        "dates": [str(r[0]) for r in rows],
        "ohlc": [[round(float(r[1]), 3), round(float(r[4]), 3), round(float(r[3]), 3), round(float(r[2]), 3)] for r in rows],
        "vols": [round(float(r[5] or 0), 2) for r in rows],
    }, None


# --- 策略因子副图（QRE-GUI-LAB-RESULT-036） ---

_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _strategy_factor_specs(record: dict[str, Any]) -> tuple[dict[str, tuple[str, str]], str, str]:
    """从 run 目录 strategy.yaml 提取因子映射与出入场表达式。

    返回 ({显示名: (schema_table, column)}, entry, exit)。表/列名逐段校验
    标识符，防注入；任何失败返回 ({}, "", "")。
    """
    import yaml

    from quant_research_engine.gui.engine import RUNS_DIR

    path = RUNS_DIR / record.get("run_id", "") / "strategy.yaml"
    if not path.exists():
        return {}, "", ""
    try:
        cfg = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}, "", ""
    specs: dict[str, tuple[str, str]] = {}
    factor_fields = ((cfg.get("data") or {}).get("factor_fields") or {})
    for name, ref in factor_fields.items():
        parts = str(ref).split(".")
        if len(parts) < 2 or not all(_IDENT_RE.match(p) for p in parts):
            continue
        specs[str(name)] = (".".join(parts[:-1]), parts[-1])
    sig = cfg.get("signal") or {}
    return specs, str(sig.get("entry") or ""), str(sig.get("exit") or "")


def _factor_thresholds(name: str, entry: str, exit_: str) -> list[float]:
    """提取该因子在出入场表达式里的数值阈值（如 rsi_14 > 30 → [30.0]）。"""
    vals: list[float] = []
    for expr in (entry, exit_):
        if not expr:
            continue
        for m in re.finditer(re.escape(name) + r"\s*[<>=!]+\s*(-?\d+(?:\.\d+)?)", expr):
            vals.append(float(m.group(1)))
        for m in re.finditer(r"(-?\d+(?:\.\d+)?)\s*[<>=!]+\s*" + re.escape(name), expr):
            vals.append(float(m.group(1)))
    return vals


def _macd_hist_candidates(specs: dict[str, tuple[str, str]]) -> list[tuple[str, str]]:
    """检测同表 macd_<P>+macds_<P> 同参数后缀被同时引用、而 macdh_<P> 未引用的情况。

    返回需补查的 [(table, hist_col)]；供 _fetch_factor_panels 自动补 MACD 柱
    （CR-2026-10-20 因子图表 TV 布局：DIF/DEA/HIST 合并单面板需要 HIST 数据）。
    """
    referenced = set(specs.values())
    found: dict[tuple[str, str], set[str]] = {}
    for table, col in specs.values():
        m = re.fullmatch(r"(macd|macds)_(.+)", col)
        if m:
            found.setdefault((table, m.group(2)), set()).add(m.group(1))
    out: list[tuple[str, str]] = []
    for (table, suffix), kinds in found.items():
        if kinds == {"macd", "macds"}:
            hist = f"macdh_{suffix}"
            if (table, hist) not in referenced:
                out.append((table, hist))
    return out


def _panel_display(table: str, column: str) -> dict[str, Any] | None:
    """QRE-FACTOR-DISPLAY-CONTRACT：因子列 → 呈现合同（注册表单一来源）。

    返回 display dict（chart_type/panel_id/role/series_type/axis/precision/
    color/price_basis/render_order）；未注册或旧注册表无 display 返回 None
    （前端走启发式回退）。纯读本地 JSON，不访问数据库。
    """
    from quant_research_engine.gui.factor_registry import load_registry

    info = load_registry().display(table, column)
    if info is None:
        return None
    disp = info.get("display")
    return dict(disp) if isinstance(disp, dict) else None


def _fetch_factor_panels(record: dict[str, Any], ts_code: str, dates: list[str]) -> tuple[list[dict[str, Any]] | None, str | None]:
    """按 K 线日期对齐拉取策略因子序列（含出入场阈值）。失败降级 (None, note)。

    每个 panel 带 ``col``（真实因子列名）供前端分组启发式；策略同时引用
    macd_<P>/macds_<P> 且表内存在 macdh_<P> 时自动补查 MACD 柱 panel（name=MACD柱），
    补全失败静默跳过（每股至多一次 information_schema 查询，且仅当检测到 macd 对时）。
    """
    specs, entry, exit_ = _strategy_factor_specs(record)
    if not specs or not dates:
        return None, None
    try:
        from sqlalchemy import text

        from quant_research_engine.gui.admin import _store
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        try:
            store = _store()
        except Exception:
            store = _store(DEFAULT_DB_URL)
        hist_specs: list[tuple[str, str]] = []  # [(table, hist_col)] 已确认存在的补查列
        with store.market_engine.begin() as conn:
            candidates = _macd_hist_candidates(specs)
            if candidates:
                try:  # 列存在性探测失败整体降级：不补 HIST，不影响原 panel
                    for table, hist in candidates:
                        schema, _, tname = table.partition(".")
                        if not tname:
                            schema, tname = "public", schema
                        hit = conn.execute(
                            text(
                                "SELECT 1 FROM information_schema.columns "
                                "WHERE table_schema = :s AND table_name = :t AND column_name = :c"
                            ),
                            {"s": schema, "t": tname, "c": hist},
                        ).first()
                        if hit:
                            hist_specs.append((table, hist))
                except Exception:
                    hist_specs = []
            raw: dict[str, dict[str, float]] = {}
            for name, (table, col) in specs.items():
                rows = conn.execute(
                    text(
                        f'SELECT trade_date, "{col}" FROM {table} '
                        "WHERE ts_code = :c AND trade_date BETWEEN :d0 AND :d1"
                    ),
                    {"c": ts_code, "d0": dates[0], "d1": dates[-1]},
                ).fetchall()
                raw[name] = {str(r[0]): float(r[1]) for r in rows if r[1] is not None}
            for table, hist in hist_specs:
                try:
                    rows = conn.execute(
                        text(
                            f'SELECT trade_date, "{hist}" FROM {table} '
                            "WHERE ts_code = :c AND trade_date BETWEEN :d0 AND :d1"
                        ),
                        {"c": ts_code, "d0": dates[0], "d1": dates[-1]},
                    ).fetchall()
                    raw[("MACD柱", hist)] = {str(r[0]): float(r[1]) for r in rows if r[1] is not None}
                except Exception:
                    pass  # 单列补查失败静默跳过
    except Exception as exc:
        return None, f"因子数据不可用（{exc}）"
    panels = []
    for name in specs:
        series = [round(raw[name][d], 4) if d in raw[name] else None for d in dates]
        if any(v is not None for v in series):
            table, col = specs[name]
            panels.append({
                "name": name,
                "col": col,
                "table": table,
                "values": series,
                "thresholds": _factor_thresholds(name, entry, exit_),
                # QRE-FACTOR-DISPLAY-CONTRACT：呈现合同随面板下发（未注册为 None）
                "display": _panel_display(table, col),
            })
    for table, hist in hist_specs:
        key = ("MACD柱", hist)
        if key not in raw:
            continue
        series = [round(raw[key][d], 4) if d in raw[key] else None for d in dates]
        if any(v is not None for v in series):
            panels.append({"name": "MACD柱", "col": hist, "table": table, "values": series,
                           "thresholds": [], "display": _panel_display(table, hist)})
    if not panels:
        return None, "该股区间无因子数据"
    return panels, None


def build_lab_symbol_detail(
    record: dict[str, Any],
    ts_code: str,
    *,
    stats: dict[str, dict[str, Any]] | None = None,
    round_trips_by_symbol: dict[str, list[dict[str, str]]] | None = None,
) -> dict[str, Any] | None:
    """组装 /api/lab/runs/<id>/symbol/<ts_code>/detail；个股无交易返回 None（404）。

    ``stats`` 可传入预算好的 _symbol_trade_stats 结果、``round_trips_by_symbol``
    可传入按 symbol 预分组的 round_trips 行；缺省时现场计算。
    批量场景（worker build_symbol_detail_files 逐股调用）必须传入，
    否则每股重复全量解析 round_trips.csv（O(股票数×交易数)，job 54 卡死根因之一）。
    """
    if stats is None:
        stats = _symbol_trade_stats(record)
    s = stats.get(ts_code)
    if s is None:
        return None
    names = _fetch_company_tags([ts_code])[1]
    pct_map = _percentile_map(stats)
    # QRE-GUI-LAB-RESULT-032：个股区间买入持有自然收益（对比策略交易收益用）
    bench = (_fetch_symbol_range_returns([ts_code], record.get("start"), record.get("end")) or {}).get(ts_code)
    data: dict[str, Any] = {
        "ok": True,
        "run_id": record.get("run_id"),
        "summary": {
            "ts_code": ts_code,
            "name": names.get(ts_code, ""),
            "total_pnl": round(s["total_pnl"], 2),
            "trades": s["trades"],
            "avg_ret": round(s["sum_ret"] / s["trades"], 6),
            "win_rate": round(s["wins"] / s["trades"], 6),
            "percentile": pct_map[ts_code],
            "bench_ret": round(bench, 6) if bench is not None else None,
        },
    }

    sym_dir = _symbol_output_dir(record, ts_code)
    # 交易明细：优先 <ts_code>/trades.csv，退到 round_trips.csv 过滤
    data["trades_source"] = None
    data["trades"] = None
    if sym_dir and (sym_dir / "trades.csv").exists():
        try:
            data["trades"] = _read_csv_rounded(sym_dir / "trades.csv")
            data["trades_source"] = "trades_csv"
        except OSError:
            pass
    if data["trades"] is None:
        rows: list[dict[str, str]] | None = None
        if round_trips_by_symbol is not None:
            rows = round_trips_by_symbol.get(ts_code) or []
        else:
            rt_path = _find_output_file(record, "round_trips.csv")
            if rt_path is not None:
                try:
                    rows = [r for r in _read_csv(rt_path) if (r.get("symbol") or "").strip() == ts_code]
                except OSError:
                    rows = None
        if rows is not None:
            data["trades"] = [{k: (_f(v) if isinstance(_f(v), float) else v) for k, v in r.items()} for r in rows] or None
            if data["trades"]:
                data["trades_source"] = "round_trips"

    for fname, key in (("orders.csv", "orders"), ("failed_orders.csv", "failed_orders")):
        data[key] = None
        if sym_dir and (sym_dir / fname).exists():
            try:
                data[key] = _read_csv_rounded(sym_dir / fname) or None
            except OSError:
                pass

    # 个股净值曲线
    data["equity"] = None
    if sym_dir and (sym_dir / "equity_curve.csv").exists():
        try:
            rows = _read_csv(sym_dir / "equity_curve.csv")
            dates = [(r.get("trade_date") or "").strip() for r in rows]
            values = [_f(r.get("total_equity")) for r in rows]
            pairs = [(d, v) for d, v in zip(dates, values) if d and v is not None]
            if pairs:
                data["equity"] = {"dates": [d for d, _ in pairs], "values": [v for _, v in pairs]}
        except OSError:
            pass

    kline, kline_note = _fetch_stock_daily(ts_code, record.get("start"), record.get("end"))
    data["kline"] = kline
    data["kline_note"] = kline_note

    # QRE-GUI-LAB-RESULT-036：策略因子副图（按 K 线日期对齐，含出入场阈值线）
    panels, factor_note = _fetch_factor_panels(record, ts_code, (kline or {}).get("dates") or [])
    data["factors"] = panels
    data["factor_note"] = factor_note

    # FRM-SYMBOL：个股级风险分析（基于区间日收盘价收益，刻画该股自身风险特征；
    # 策略组合层风险在 run 级 risk_report.json）。轻量配置：不做 VaR 回测/Bootstrap，
    # 保留 VaR/ES 三口径 + EWMA/GARCH 波动率 + 压力测试。失败降级 None 不拖垮详情。
    data["risk"] = None
    try:
        kl_dates = (kline or {}).get("dates") or []
        closes = [row[1] for row in (kline or {}).get("ohlc") or [] if row and row[1]]
        if len(closes) >= 60 and len(kl_dates) == len((kline or {}).get("ohlc") or []):
            import numpy as np
            import pandas as pd

            from quant_research_engine.risk.report import build_risk_report

            arr = np.asarray(closes, dtype=float)
            # stress 节按日期切情景窗口，要求 DatetimeIndex（与收益对齐从第 2 天起）
            rets = pd.Series(
                arr[1:] / arr[:-1] - 1.0,
                index=pd.DatetimeIndex(pd.to_datetime(kl_dates[1:])),
            )
            data["risk"] = build_risk_report(
                rets,
                config={"var_backtest": False, "stress": True, "bootstrap": False},
            )
    except Exception:
        data["risk"] = None

    # QRE-GUI-LAB-RESULT-033：净值曲线对比项——基准指数（按个股净值交易日对齐）
    if data["equity"]:
        benchmarks, bench_note = _benchmark_series(data["equity"]["dates"])
        data["benchmarks"] = benchmarks or None
        data["benchmark_note"] = bench_note
    else:
        data["benchmarks"] = None
        data["benchmark_note"] = None

    # QRE-GUI-LAB-RESULT-034：策略区间收益率（净值末/初-1），与自然涨幅同口径对比
    vals = (data["equity"] or {}).get("values") or []
    data["summary"]["total_ret_pct"] = (
        round(vals[-1] / vals[0] - 1, 6) if len(vals) >= 2 and vals[0] else None
    )
    return data


def _run_meta(record: dict[str, Any], brief: dict[str, str]) -> dict[str, Any]:
    """回测参数信息条（QRE-GUI-LAB-RESULT-031）：status.json 字段 + 费率。

    费率 = AShareMarketProfile 默认值叠加 record["profile_overrides"]；
    initial_cash 缺省 10 万、max_positions 缺省 10（与 gui/engine.py 一致）。
    """
    codes = record.get("codes") or []
    if isinstance(codes, str):  # 兼容历史 run 的空格拼接串
        codes = codes.split()
    overrides = record.get("profile_overrides") or {}
    fees: dict[str, Any] = {}
    try:
        from quant_research_engine.markets.ashare import AShareMarketProfile

        default_profile = AShareMarketProfile()
        for key in ("commission_rate", "min_commission", "stamp_tax_sell", "transfer_fee_rate"):
            val = overrides.get(key)
            fees[key] = float(val) if val is not None else float(getattr(default_profile, key))
        fees["overridden"] = any(overrides.get(k) is not None for k in fees if k != "overridden")
    except Exception:  # profile 模块不可用时降级
        fees = {"overridden": bool(overrides)}

    def _num(v: Any, default: float) -> float:
        try:
            return float(v) if v not in (None, "") else default
        except (TypeError, ValueError):
            return default

    return {
        "strategy_name": brief.get("name"),
        "date_start": record.get("start"),
        "date_end": record.get("end"),
        "mode": record.get("mode"),
        "whole_market": not codes,
        "random_n": record.get("random_n"),
        "n_codes": len(codes),
        "codes_sample": codes[:5],
        "initial_cash": _num(record.get("initial_cash"), 100_000.0),
        "max_positions": int(_num(record.get("max_positions"), 10)),
        "engine_impl": record.get("engine_impl") or "simulator",
        "fees": fees,
    }


# --- FRM 风险分析（QRE-GUI-LAB-RESULT-031） ---

HISTOGRAM_BINS = 40


def histogram_normal_data(
    returns: list[float], mean: float, std: float, n_bins: int = HISTOGRAM_BINS
) -> dict[str, Any] | None:
    """纯函数：日收益序列 → 直方图分箱 + 正态拟合曲线（与直方图同量纲）。

    返回 {"edges": [...(n_bins+1)], "counts": [...], "normal": [[x, y], ...]}；
    normal 的 y = 正态密度 × 样本数 × 箱宽，可直接与 counts 叠图。
    样本 <2 或 std <= 0 返回 None。
    """
    vals = [float(r) for r in returns if r is not None]
    if len(vals) < 2 or not std or std <= 0:
        return None
    lo, hi = min(vals), max(vals)
    if hi <= lo:
        return None
    width = (hi - lo) / n_bins
    edges = [round(lo + i * width, 8) for i in range(n_bins + 1)]
    counts = [0] * n_bins
    for v in vals:
        idx = min(int((v - lo) / width), n_bins - 1)
        counts[idx] += 1
    import math

    normal = []
    for i in range(n_bins):
        x = (edges[i] + edges[i + 1]) / 2
        pdf = math.exp(-0.5 * ((x - mean) / std) ** 2) / (std * math.sqrt(2 * math.pi))
        normal.append([round(x, 8), round(pdf * len(vals) * width, 4)])
    return {"edges": edges, "counts": counts, "normal": normal}


def daily_returns_from_cumret(cumret: list[Any] | None) -> list[float]:
    """累计收益率序列 → 日收益序列（SaaS FRM 直方图数据源）。

    SaaS 的 ``result_chart_data.cumret`` 是组合级“交集口径日收益累乘”的累计值，
    已剔除新股注资；日收益必须由相邻累计值还原，不能直接用 ``equity`` 的
    ``pct_change``（会重新引入注资跳变）。缺口/非有限值处重新起算，不造连续收益。
    """
    import math

    returns: list[float] = []
    prev: float | None = None
    for raw in cumret or []:
        try:
            value = float(raw)
        except (TypeError, ValueError):
            prev = None
            continue
        if not math.isfinite(value):
            prev = None
            continue
        if prev is not None:
            denominator = 1.0 + prev
            if denominator != 0:
                returns.append((1.0 + value) / denominator - 1.0)
        prev = value
    return returns


def histogram_from_cumret(
    cumret: list[Any] | None,
    mean: Any,
    std: Any,
    n_bins: int = HISTOGRAM_BINS,
) -> dict[str, Any] | None:
    """cumret + risk report 的 mean/std → 前端就绪直方图；退化输入返回 None。"""
    import math

    try:
        mean_f = float(mean)
        std_f = float(std)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(mean_f) or not math.isfinite(std_f):
        return None
    returns = daily_returns_from_cumret(cumret)
    if len(returns) < 2:
        return None
    return histogram_normal_data(returns, mean_f, std_f, n_bins)


def build_lab_risk_view(report: dict[str, Any]) -> dict[str, Any]:
    """纯函数：risk_report.json → 前端图表就绪视图（缺节一律 None/空，不抛错）。"""
    meta = report.get("meta") or {}
    dist = report.get("distribution") or {}
    view: dict[str, Any] = {
        "n_obs": meta.get("n_obs"),
        "dist": {
            "mean": dist.get("mean"),
            "std": dist.get("std"),
            "min": dist.get("min"),
            "max": dist.get("max"),
            "skew": dist.get("skew_sample"),
            "excess_kurtosis": dist.get("excess_kurtosis_sample"),
            "reject_normal": dist.get("reject_normal_5pct"),
        } if dist else None,
    }

    # VaR / ES 卡片：历史模拟口径（损失取正号）
    tail = report.get("tail") or {}
    var_es: dict[str, Any] = {}
    for level in ("95pct", "99pct"):
        hs = ((tail.get(level) or {}).get("historical_simulation")) or {}
        if isinstance(hs.get("var"), (int, float)):
            var_es[level] = {"var": hs.get("var"), "es": hs.get("es")}
    view["var_es"] = var_es or None

    # 波动率：EWMA / GARCH 条件波动（年化 ×√252）+ 波动状态分布
    vol = report.get("volatility") or {}
    ann = float(meta.get("annualization_factor") or 252)
    ewma_sig = ((vol.get("ewma_latest") or {}).get("volatility_forecast"))
    garch_sig = ((vol.get("garch11") or {}).get("latest_conditional_volatility"))
    regime = vol.get("regime") or {}
    view["volatility"] = {
        "ewma_annual": round(ewma_sig * ann ** 0.5, 6) if isinstance(ewma_sig, (int, float)) else None,
        "garch_annual": round(garch_sig * ann ** 0.5, 6) if isinstance(garch_sig, (int, float)) else None,
        "regime_counts": regime.get("counts") or None,
        "latest_regime": regime.get("latest"),
    } if vol else None

    # 压力测试：窗口内覆盖不足的情景（带 error）归入 skipped
    stress = report.get("stress") or {}
    scenarios: list[dict[str, Any]] = []
    skipped: list[str] = []
    for name, sc in (stress.get("scenarios") or {}).items():
        if not isinstance(sc, dict):
            continue
        if "error" in sc:
            skipped.append(str(sc.get("description") or name))
            continue
        scenarios.append({
            "name": name,
            "description": sc.get("description") or name,
            "cum_loss": sc.get("strategy_cumulative_loss"),
            "max_dd": sc.get("strategy_peak_trough_drawdown"),
        })
    view["stress"] = {"scenarios": scenarios, "skipped": skipped} if (scenarios or skipped) else None

    # VaR 回测：覆盖率 + 独立性合格灯
    var_bt = report.get("var_backtest") or {}
    if var_bt.get("enabled"):
        levels: dict[str, Any] = {}
        for level, lv in (var_bt.get("levels") or {}).items():
            cov = (lv or {}).get("coverage") or {}
            if not isinstance(cov.get("violation_rate"), (int, float)):
                continue
            levels[level] = {
                "violation_rate": cov.get("violation_rate"),
                "expected_rate": cov.get("expected_violation_rate"),
                "violations": cov.get("violations"),
                "n_obs": cov.get("n_obs"),
                "reject": bool(lv.get("reject_5pct")),
                "conclusion": lv.get("conclusion"),
            }
        view["var_backtest"] = levels or None
    else:
        view["var_backtest"] = None
    return view


def build_lab_risk_analysis(record: dict[str, Any]) -> dict[str, Any]:
    """组装 /api/lab/runs/<id>/risk-analysis 的 JSON payload。"""
    from quant_research_engine.gui import risk_report as risk_mod

    data: dict[str, Any] = {"ok": True, "run_id": record.get("run_id"), "has_report": False}
    report = risk_mod.load_risk_report(str(record.get("run_id")))
    if report is None:
        return data
    data["has_report"] = True
    data.update(build_lab_risk_view(report))

    # 直方图需要逐日收益原始序列（report 里只有统计量）：复用 FRM 模块的提取逻辑
    mean = ((data.get("dist") or {}).get("mean"))
    std = ((data.get("dist") or {}).get("std"))
    data["histogram"] = None
    if isinstance(mean, (int, float)) and isinstance(std, (int, float)):
        extracted = risk_mod.extract_strategy_returns(record)
        if extracted is not None:
            returns, _bench = extracted
            data["histogram"] = histogram_normal_data(list(returns), float(mean), float(std))
    return data


# --- 回测记录列表 + 删除（QRE-GUI-CONSOL-040，8081 独占） ---

# run_id 白名单：拒绝路径穿越与特殊字符
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _strategy_name_from_yaml(run_id: str) -> str | None:
    """从 run 目录 strategy.yaml 解析策略名（读取失败一律降级 None）。

    优先级：头部注释行 ``# 策略名称: XXX`` → YAML ``experiment.name``。
    """
    from quant_research_engine.gui.engine import RUNS_DIR

    path = RUNS_DIR / run_id / "strategy.yaml"
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("#"):
            break  # 头部注释块结束
        content = line.lstrip("#").strip()
        if content.startswith("策略名称"):
            name = content.partition(":")[2].strip()
            if name:
                return name
    try:
        import yaml

        cfg = yaml.safe_load(text) or {}
        name = (cfg.get("experiment") or {}).get("name")
        return str(name) if name else None
    except Exception:
        return None


def _excess_return_of(record: dict[str, Any]) -> float | None:
    """该 run 的超额收益率（总收益 − 买入持有；QRE-LAB-UI-LANDING-R5 记录表新增列）。
    仅 completed 且产物在的 run 有值，其余 None（前端显示「——」且排序恒排最后）。
    """
    if record.get("status") != "completed":
        return None
    path = _find_output_file(record, "strategy_performance.json")
    if path is None:
        return None
    try:
        perf = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(perf, dict):
        return None
    excess = perf.get("excess_return_vs_buy_hold")
    total, buy_hold = perf.get("strategy_total_return"), perf.get("buy_hold_return")
    if excess is None and isinstance(total, (int, float)) and isinstance(buy_hold, (int, float)):
        excess = total - buy_hold
    return round(excess, 6) if isinstance(excess, (int, float)) else None


def _reap_zombie_run(record: dict[str, Any]) -> dict[str, Any]:
    """僵尸 run 自愈（QRE-LAB-UI-LANDING-R6）：status=running 但执行器已死 → 标记 failed。

    判死规则（最小改动，不重执行器）：
    - status.json 无 gui_pid 的旧 running run → 一律视为僵尸（PID 记录缺失无法证活）；
    - executor=module：执行器跑在 GUI 进程内，status.json 的 gui_pid != 当前进程 PID
      （说明 GUI 已重启，旧进程连同回测一起死了）→ 僵尸；
    - executor=cli：子进程依附 GUI 启动，gui_pid 不一致同上；一致时再探活
      （os.kill(pid, 0)，进程不存在/无权限→视为死）。
    标记写回 status.json（error 注明检测原因与时间），request.json 不动。
    """
    if record.get("status") != "running":
        return record
    pid = record.get("gui_pid")
    dead_reason: str | None = None
    if not isinstance(pid, int) or pid <= 0:
        dead_reason = "无 gui_pid 记录（早于 R6 的 run），无法证明执行器存活"
    elif pid != os.getpid():
        dead_reason = f"执行器依附的 GUI 进程 PID {pid} 已退出（当前 PID {os.getpid()}）"
    else:
        try:
            os.kill(pid, 0)
        except OSError:
            dead_reason = f"GUI 进程 PID {pid} 探活失败"
    if dead_reason is None:
        return record
    record = dict(record)
    record["status"] = "failed"
    record["error"] = (
        f"僵尸 run 自动标记：{dead_reason}；检测时间 "
        + datetime.now(tz=timezone.utc).isoformat()
    )
    run_id = str(record.get("run_id") or "")
    if _RUN_ID_RE.match(run_id):
        try:
            (_engine.RUNS_DIR / run_id / "status.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass
    return record


def build_lab_runs_list() -> list[dict[str, Any]]:
    """list_runs() 增强：每条加 strategy_name / symbol_count，按创建时间倒序。

    symbol_count 为 None 表示全 A 股（codes 为空/缺省），前端显示「全 A 股」。
    """
    from quant_research_engine.gui.engine import list_runs

    items: list[dict[str, Any]] = []
    for record in list_runs():
        record = _reap_zombie_run(record)
        run_id = str(record.get("run_id") or "")
        codes = record.get("codes") or []
        if isinstance(codes, str):  # 兼容历史 run 的空格拼接串
            codes = codes.split()
        items.append({
            "run_id": run_id,
            "mode": record.get("mode"),
            "start": record.get("start"),
            "end": record.get("end"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "finished_at": record.get("finished_at"),
            "strategy_name": _strategy_name_from_yaml(run_id) or run_id,
            "symbol_count": len(codes) if codes else None,
            "excess_return": _excess_return_of(record),
        })
    items.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return items


def register_lab_result_routes(app: Flask) -> None:
    """注册 8081 lab 专属的回测结果可视化路由（8080 不注册）。"""

    @app.route("/api/lab/runs")
    def lab_runs_list():  # type: ignore[no-untyped-def]
        return jsonify({"ok": True, "runs": build_lab_runs_list()})

    @app.route("/api/lab/runs/<run_id>/delete", methods=["POST"])
    def lab_run_delete(run_id: str):  # type: ignore[no-untyped-def]
        import shutil

        from quant_research_engine.gui.engine import RUNS_DIR

        if not _RUN_ID_RE.match(run_id):
            return jsonify({"ok": False, "error": f"非法 run_id: {run_id}"}), 400
        base = RUNS_DIR.resolve()
        run_dir = (base / run_id).resolve()
        # 双保险：目录必须在 RUNS_DIR 内（白名单已挡穿越，此处防 symlink 等边角）
        if run_dir.parent != base or not run_dir.is_dir():
            return jsonify({"ok": False, "error": f"run {run_id} 不存在"}), 404
        # 只删 RUNS_DIR 下的 run 目录；status.json 里 output_dir 指向的回测产物不动
        shutil.rmtree(run_dir)
        return jsonify({"ok": True})

    @app.route("/lab/runs/<run_id>")
    def lab_run_result(run_id: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return render_template("error.html", message=f"Run {run_id} 不存在"), 404
        return render_template("lab_result.html", run_id=run_id, record=record)

    @app.route("/api/lab/runs/<run_id>/chart-data")
    def lab_run_chart_data(run_id: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return jsonify({"ok": False, "error": f"run {run_id} 不存在"}), 404
        return jsonify(build_lab_chart_data(record))

    @app.route("/api/lab/runs/<run_id>/tag-analysis")
    def lab_run_tag_analysis(run_id: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return jsonify({"ok": False, "error": f"run {run_id} 不存在"}), 404
        return jsonify(build_lab_tag_analysis(record))

    @app.route("/api/lab/runs/<run_id>/risk-analysis")
    def lab_run_risk_analysis(run_id: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return jsonify({"ok": False, "error": f"run {run_id} 不存在"}), 404
        return jsonify(build_lab_risk_analysis(record))

    @app.route("/lab/runs/<run_id>/symbols")
    def lab_run_symbols(run_id: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return render_template("error.html", message=f"Run {run_id} 不存在"), 404
        return render_template("lab_symbols.html", run_id=run_id)

    @app.route("/lab/runs/<run_id>/symbol/<ts_code>")
    def lab_run_symbol(run_id: str, ts_code: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return render_template("error.html", message=f"Run {run_id} 不存在"), 404
        return render_template("lab_symbol.html", run_id=run_id, ts_code=ts_code)

    @app.route("/api/lab/runs/<run_id>/symbol/<ts_code>/detail")
    def lab_run_symbol_detail(run_id: str, ts_code: str):  # type: ignore[no-untyped-def]
        record = get_run(run_id)
        if record is None:
            return jsonify({"ok": False, "error": f"run {run_id} 不存在"}), 404
        data = build_lab_symbol_detail(record, ts_code)
        if data is None:
            return jsonify({"ok": False, "error": f"{ts_code} 在该 run 中无交易"}), 404
        return jsonify(data)
