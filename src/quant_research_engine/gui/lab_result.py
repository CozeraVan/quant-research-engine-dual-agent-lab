"""8081 回测台专属：ECharts 回测结果页（QRE-GUI-LAB-RESULT-023）。

只在 ``create_lab_app()`` 里注册，8080 管理台的 ``/runs/<run_id>``
（strategy_lab_routes + run_detail.html）保持零改动。

路由：
- ``GET /lab/runs/<run_id>``                  渲染 lab_result.html
- ``GET /api/lab/runs/<run_id>/chart-data``   图表数据 JSON
- ``GET /api/lab/runs/<run_id>/tag-analysis`` 赚钱效应归因 JSON（QRE-GUI-LAB-RESULT-024）

数据全部来自本地已有产物（equity_curve.csv / drawdown_curve.csv /
round_trips.csv / strategy_performance.json）、
本地 PostgreSQL ``reference.index_daily`` 基准指数日线与
``cluster.company_tags`` 板块/关键词/动态标签，不造数据；
任一数据源缺失时对应字段为 None / 空数组 + note，由前端显示「暂无数据」。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template

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


def _equity_series(record: dict[str, Any]) -> tuple[list[str], list[float | None]] | None:
    path = _find_output_file(record, "equity_curve.csv")
    if path is None:
        return None
    try:
        rows = _read_csv(path)
    except OSError:
        return None
    dates: list[str] = []
    equity: list[float | None] = []
    for row in rows:
        d = (row.get("trade_date") or "").strip()
        v = _f(row.get("total_equity"))
        if d and v is not None:
            dates.append(d)
            equity.append(v)
    return (dates, equity) if dates else None


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
            points.append(
                {
                    "symbol": (r.get("symbol") or "").strip(),
                    "entry_date": entry,
                    "exit_date": exit_,
                    "net_return": ret,
                }
            )
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

    metrics: dict[str, Any] = {}
    if perf:
        total = perf.get("strategy_total_return")
        metrics = {
            "total_return": total,
            "excess_return": perf.get("excess_return_vs_buy_hold"),
            "sharpe": perf.get("sharpe"),
            "max_drawdown": perf.get("max_drawdown"),
            "win_rate": perf.get("win_rate"),
            "date_start": perf.get("date_start"),
            "date_end": perf.get("date_end"),
        }
        if isinstance(total, (int, float)) and perf.get("date_start") and perf.get("date_end"):
            try:
                from datetime import date as _date

                d0 = _date.fromisoformat(str(perf["date_start"]))
                d1 = _date.fromisoformat(str(perf["date_end"]))
                years = max((d1 - d0).days / 365.25, 1 / 365.25)
                metrics["annual_return"] = round((1 + total) ** (1 / years) - 1, 6)
            except (ValueError, OverflowError, ZeroDivisionError):
                metrics["annual_return"] = None
    data["metrics"] = metrics or None

    eq = _equity_series(record)
    if eq is None:
        data["dates"] = None
        data["equity"] = None
        data["drawdown_pct"] = None
        data["benchmarks"] = None
    else:
        dates, equity = eq
        data["dates"] = dates
        data["equity"] = equity
        data["drawdown_pct"] = _drawdown_series(record, dates)
        benchmarks, bench_note = _benchmark_series(dates)
        data["benchmarks"] = benchmarks or None
        data["benchmark_note"] = bench_note

    trades = _trade_points(record)
    data["trades"] = trades
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


def _aggregate_tag_layers(
    stats: dict[str, dict[str, Any]],
    tag_rows: list[tuple[str, str, str]],
    names: dict[str, str],
) -> dict[str, list[dict[str, Any]]]:
    """纯函数：个股交易统计 × 标签行 → A/B/C 三层 tag 聚合（含个股分位）。

    分位 = 按 total_pnl 在全 run 交易个股中的排名百分位（1-based rank / N，
    越小越靠前，前端显示「前 X.X%」）。
    A 层纳入全部 A 层 tag（去掉 `申万L1:` 等前缀显示）；每层把没有任何
    该层 tag 的交易个股归入「未标记」块；B 层先经 is_noise_keyword 过滤
    停用词（A/C 层不过滤），只保留按 |总净盈亏| 排序的前 LAYER_B_TOP_N 个，
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
    layers = _aggregate_tag_layers(stats, tag_rows, names)
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
            rows = conn.execute(
                text(
                    "SELECT trade_date, open, high, low, close, vol FROM public.stock_daily "
                    "WHERE ts_code = :c AND (CAST(:d0 AS date) IS NULL OR trade_date >= CAST(:d0 AS date)) "
                    "AND (CAST(:d1 AS date) IS NULL OR trade_date <= CAST(:d1 AS date)) ORDER BY trade_date"
                ),
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


def build_lab_symbol_detail(record: dict[str, Any], ts_code: str) -> dict[str, Any] | None:
    """组装 /api/lab/runs/<id>/symbol/<ts_code>/detail；个股无交易返回 None（404）。"""
    stats = _symbol_trade_stats(record)
    s = stats.get(ts_code)
    if s is None:
        return None
    names = _fetch_company_tags([ts_code])[1]
    pct_map = _percentile_map(stats)
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
        rt_path = _find_output_file(record, "round_trips.csv")
        if rt_path is not None:
            try:
                rows = [r for r in _read_csv(rt_path) if (r.get("symbol") or "").strip() == ts_code]
                data["trades"] = [{k: (_f(v) if isinstance(_f(v), float) else v) for k, v in r.items()} for r in rows] or None
                if data["trades"]:
                    data["trades_source"] = "round_trips"
            except OSError:
                pass

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
    return data


def register_lab_result_routes(app: Flask) -> None:
    """注册 8081 lab 专属的回测结果可视化路由（8080 不注册）。"""

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
