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

import json
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from quant_research_engine.gui.engine import extract_run_summary, run_backtest

DEFAULT_START_YEARS = 2


def _persist_artifacts(record: dict[str, Any], output_dir: Path) -> None:
    """把 /tmp 沙箱产物目录整体复制到 RUNS_DIR/<run_id>/artifacts/（持久位置），
    并改写 run record（内存 + status.json）里 artifacts map 与 output_dir 的
    绝对路径指向持久副本。产物为空则不动作。
    """
    import shutil

    from quant_research_engine.gui import engine as gui_engine

    if not output_dir.is_dir() or not any(output_dir.iterdir()):
        return
    run_dir = gui_engine.RUNS_DIR / str(record.get("run_id"))
    persistent = run_dir / "artifacts"
    if persistent.exists():
        shutil.rmtree(persistent)
    run_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(output_dir, persistent)

    old_prefix = str(output_dir.resolve())
    new_prefix = str(persistent.resolve())
    artifacts = record.get("artifacts") or {}
    record["artifacts"] = {
        rel: (new_prefix + path[len(old_prefix):] if path.startswith(old_prefix) else path)
        for rel, path in artifacts.items()
    }
    record["output_dir"] = str(persistent)
    gui_engine._write_json(run_dir / "status.json", record)


def _job_params(job: dict[str, Any]) -> dict[str, Any]:
    # 17 协议字段名为 params_json；旧键 params 兼容兜底（C5 联调修复：
    # 此前只读 params，claim 下发的 params_json 被丢弃导致按默认参数跑）
    params = job.get("params") or job.get("params_json") or {}
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except (json.JSONDecodeError, TypeError):
            params = {}
    return params if isinstance(params, dict) else {}


def fill_guest_codes(codes: list[str], auto_fill: int | None,
                     pool_fn: Any = None) -> list[str]:
    """游客自选不足上限的随机补齐（2026-10-05 内测调整）：云端无行情库只打
    params.codes_auto_fill=N 标记，本机执行前从全量股票清单抽样补齐到 N 只。
    pool_fn 可注入（测试）；默认 universe.all_a_codes（本地全量库）。"""
    if not auto_fill or len(codes) >= int(auto_fill):
        return codes
    if pool_fn is None:
        from quant_research_engine.gui.universe import all_a_codes as pool_fn
    pool = [c for c in pool_fn() if c not in set(codes)]
    need = min(int(auto_fill) - len(codes), len(pool))
    import random as _random
    return codes + _random.sample(pool, need)


def _json_sanitize(obj: Any) -> Any:
    """递归把 NaN/Inf（含 numpy 浮点）替换为 None——json.dumps 默认把 NaN 写成
    裸 NaN token，是非法 JSON，浏览器 resp.json() 会抛 SyntaxError
    （symbol_detail 页面卡「加载中」的根因，2026-10-12）。"""
    import math

    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(v) for v in obj]
    return obj


def _execute_symbol_detail(job: dict[str, Any]) -> dict[str, Any]:
    """kind=symbol_detail：为父 job 的某只已交易个股按需补生成详情产物并回传。

    params: {parent_job_id, ts_code, run_id}。run 产物已持久化在
    RUNS_DIR/<run_id>/artifacts/（_persist_artifacts），此处复用批量同款
    build_lab_symbol_detail 组装（含 FRM 个股风险节），gzip 写进同目录
    _symbol_details/（幂等覆盖），files 清单只含这一个文件走既有
    meta/files 两阶段回传；ECS 侧收到后落父 job 目录。
    """
    import gzip
    import hashlib

    from quant_research_engine.gui.engine import RUNS_DIR

    params = _job_params(job)
    run_id = str(params.get("run_id") or "").strip()
    ts_code = str(params.get("ts_code") or "").strip().upper()
    if not run_id or not ts_code:
        raise RuntimeError("symbol_detail 任务缺少 run_id/ts_code")
    status_path = RUNS_DIR / run_id / "status.json"
    if not status_path.is_file():
        raise RuntimeError(f"run 记录不存在：{run_id}（本地产物可能已清理）")
    record = json.loads(status_path.read_text(encoding="utf-8"))

    from quant_research_engine.gui.lab_result import (
        _symbol_trade_stats,
        build_lab_symbol_detail,
    )

    stats = _symbol_trade_stats(record)
    if ts_code not in stats:
        raise RuntimeError(f"{ts_code} 在本次回测中无交易")
    data = build_lab_symbol_detail(record, ts_code, stats=stats)
    if not data:
        raise RuntimeError(f"{ts_code} 详情组装失败")
    try:
        _enrich_shared_symbol_detail(record, data, ts_code,
                                     single_symbol=(len(stats) == 1))
    except Exception:
        pass  # 补齐失败保留原始详情（与批量同策略降级；batch 模式字段非 None 时内部不动作）
    data.pop("benchmarks", None)
    data.pop("benchmark_note", None)

    blob = gzip.compress(json.dumps(_json_sanitize(data), ensure_ascii=False, default=str).encode("utf-8"))
    output_dir = Path(str(record.get("output_dir") or ""))
    if not output_dir.is_dir():
        raise RuntimeError(f"run 产物目录不存在：{output_dir}")
    detail_dir = output_dir / SYMBOL_DETAILS_DIRNAME
    detail_dir.mkdir(parents=True, exist_ok=True)
    path = detail_dir / f"{ts_code}.json.gz"
    path.write_bytes(blob)
    rel = f"{SYMBOL_DETAILS_DIRNAME}/{ts_code}.json.gz"
    files = [{
        "name": rel,
        "size": len(blob),
        "sha256": hashlib.sha256(blob).hexdigest(),
        "path": str(path),
    }]
    return {
        "summary": {"kind": "symbol_detail", "run_id": run_id, "ts_code": ts_code},
        "chart_data": {},
        "artifacts": [],
        "files": files,
        "data_until": None,
        "symbol_details": {"count": 1, "bytes": len(blob), "on_demand": True},
    }


def execute_job(job: dict[str, Any], *, work_base: str | Path | None = None) -> dict[str, Any]:
    """执行 leased job，返回 result 回传 payload（不含 status 字段）。

    回测失败抛 RuntimeError（调用方负责回传 failed）。
    """
    if job.get("kind") == "symbol_detail":
        return _execute_symbol_detail(job)
    strategy = job.get("strategy") or {}
    yaml_text = str(strategy.get("yaml") or "").strip()
    if not yaml_text:
        raise RuntimeError("job 缺少策略 yaml")
    # QRE-SAAS-005：公网 NL 产物前置安全闸——严格 schema + 信号表达式 AST 白名单
    # （引擎表达式求值器允许任意 getattr/方法调用，必须在执行前锁死）。
    # 因子上限按提交时角色权限从 params._factor_limits 注入（0=不限），缺失回退常量。
    from quant_research_engine.security.yaml_guard import validate_strategy_yaml

    params = _job_params(job)
    flimits = params.get("_factor_limits") if isinstance(params.get("_factor_limits"), dict) else {}
    verdict = validate_strategy_yaml(
        yaml_text,
        max_factor_fields=int(flimits.get("max_fields", 20)),
        max_factor_tables=int(flimits.get("max_tables", 3)),
    )
    if not verdict["ok"]:
        raise RuntimeError("策略 YAML 未通过安全校验：" + "；".join(verdict["issues"]))

    codes = params.get("codes") or []
    if isinstance(codes, str):
        codes = [c.strip() for c in codes.split(",") if c.strip()]
    # 游客自选不足上限的随机补齐（2026-10-05 内测调整）：云端只打标记，本机补齐
    codes = fill_guest_codes(codes, params.get("codes_auto_fill"))
    # 板块/概念范围（QRE-SAAS-METADATA）：params.universe={group,key} 在 worker
    # 本地解析成 codes（全量行情库只在本机）；与显式 codes 同时给时显式优先
    universe = params.get("universe")
    if not codes and isinstance(universe, dict) and universe.get("group") and universe.get("key"):
        from quant_research_engine.gui.universe import universe_members

        codes = universe_members(str(universe["group"]), str(universe["key"]))
        if not codes:
            raise RuntimeError(f"板块/概念无成分股：{universe['group']}/{universe['key']}")
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
        random_n=(int(params["random_n"]) if params.get("random_n") is not None else None),
        background=False,
    )
    # 产物持久化（缺陷修复）：/tmp 沙箱在 WSL 重启/清理后丢失，导致详情页全空。
    # 成功与失败路径都拷回（失败的部分产物/日志便于诊断）；/tmp 原件不动
    # （清理由既有逻辑决定，不引入新清理行为）。
    _persist_artifacts(record, output_dir)
    if record.get("status") != "completed":
        raise RuntimeError(f"回测失败：{record.get('error') or '未知错误'}")

    # FRM 风险报告回传：engine 收尾钩子把 risk_report.json 写在 run 目录根部，
    # 不在 artifacts map 里 → 从不上传 → 云端 FRM 模块恒隐藏。此处登记进
    # artifacts，使其随 files 通道落到云端 job 目录根（saas risk-analysis
    # 端点读 output_dir/risk_report.json）。缺失不拖垮回传。
    try:
        from quant_research_engine.gui.engine import RUNS_DIR as _RUNS_DIR

        _rp = _RUNS_DIR / str(record.get("run_id")) / "risk_report.json"
        if _rp.is_file():
            record.setdefault("artifacts", {})["risk_report.json"] = str(_rp)
    except Exception:
        pass

    summary = (extract_run_summary(record) or {}).get("metrics") or {}
    summary["run_id"] = record.get("run_id")
    summary["kind"] = job.get("kind")

    from quant_research_engine.gui.lab_result import build_lab_chart_data, build_lab_tag_analysis

    is_smoke = job.get("kind") == "smoke"

    chart_data = build_lab_chart_data(record)
    _fill_excess_return(record, chart_data)
    # 板块/个股归因：与 8081 结果页同一组装函数（数据形态完全一致），
    # 截断后挂到 chart_data.tag_analysis（体积控制见 trim_tag_analysis）。
    # smoke 只需最小结果摘要（成交数/收益/费用）证明链路通，跳过全量归因与
    # per-symbol 详情后处理（job 54 事故：smoke 跑了全市场 5533 只的明细构建）。
    # 8081 lab 流程 precheck 后接全量（record["full_params"] 链）不经此处，不受影响。
    if is_smoke:
        chart_data["tag_analysis"] = None
    else:
        try:
            chart_data["tag_analysis"] = trim_tag_analysis(build_lab_tag_analysis(record))
        except Exception:
            chart_data["tag_analysis"] = None  # 归因失败不拖垮回传（DB 降级等）

    # QRE-SAAS-SYMBOL-UX（C）：per-symbol 产物回传——实际触发交易的个股各生成
    # 一份详情 JSON（K线/买卖点/收益曲线/磨损明细/因子副图，gzip 压缩），
    # 云端个股详情页直接读文件渲染（ECS 无行情库，实时查库路径不可用）。
    if is_smoke:
        symbol_details_meta = {"count": 0, "bytes": 0, "truncated": False, "skipped": "smoke"}
    else:
        symbol_details_meta = build_symbol_detail_files(record)

    # 数据截止日期（静态快照声明）：优先净值曲线末日，回退 run 区间末日
    dates = chart_data.get("dates") or []
    data_until = summary.get("date_end") or (dates[-1] if dates else None) or end

    return {
        "summary": summary,
        "chart_data": chart_data,
        "artifacts": [],  # TODO(M4)：Excel/CSV 明细上传 OSS 后在此登记 oss_key
        "files": collect_result_files(record),
        "data_until": str(data_until),
        "symbol_details": symbol_details_meta,
    }


def _fill_excess_return(record: dict[str, Any], chart_data: dict[str, Any]) -> None:
    """B 修复：shared_cash 模式引擎不写 buy_hold_return（恒 None），导致
    「超额收益 vs 持有不动」恒为「—」。此处补齐：实际交易个股在 run 区间的
    等权买入持有收益（与 batch 模式 mean(buy_hold_return) 同族口径），
    超额 = 策略全期总收益 − 该等权买入持有收益。DB 不可用保持 None 不报错。"""
    metrics = chart_data.get("metrics")
    if not isinstance(metrics, dict) or metrics.get("excess_return") is not None:
        return
    total = metrics.get("total_return")
    if not isinstance(total, (int, float)):
        return
    try:
        from quant_research_engine.gui.lab_result import (
            _fetch_symbol_range_returns,
            _symbol_trade_stats,
        )

        traded = list(_symbol_trade_stats(record))
        if not traded:
            return
        start = metrics.get("date_start") or record.get("start")
        end = metrics.get("date_end") or record.get("end")
        rets = _fetch_symbol_range_returns(traded, start, end)
    except Exception:
        return
    if not rets:
        return
    buy_hold = round(sum(rets.values()) / len(rets), 6)
    metrics["buy_hold_return"] = buy_hold
    metrics["excess_return"] = round(total - buy_hold, 6)
    metrics["buy_hold_note"] = f"等权买入持有（实际交易 {len(rets)} 只）"


#: per-symbol 详情产物总体积上限（gzip 后；超出按 |总净盈亏| 降序截断）
SYMBOL_DETAILS_MAX_BYTES = 15 * 1024 * 1024
SYMBOL_DETAILS_DIRNAME = "_symbol_details"


def _read_csv_f(path: Path) -> list[dict[str, Any]]:
    """读 CSV 并把可转数字的列转 float（与 lab_result._read_csv_rounded 同口径）。"""
    import csv

    from quant_research_engine.gui.lab_result import _f

    with path.open(newline="", encoding="utf-8") as fh:
        return [
            {k: (_f(v) if isinstance(_f(v), float) else v) for k, v in row.items()}
            for row in csv.DictReader(fh)
        ]


def _filter_symbol_csv(path: Path, ts_code: str) -> list[dict[str, Any]] | None:
    """从任务级 CSV 过滤出某只股票的行（shared 模式无 per-symbol 目录）。"""
    if not path.is_file():
        return None
    try:
        rows = [r for r in _read_csv_f(path) if str(r.get("symbol") or "").strip() == ts_code]
    except OSError:
        return None
    return rows or None


def _enrich_shared_symbol_detail(
    record: dict[str, Any], data: dict[str, Any], ts_code: str, *, single_symbol: bool
) -> None:
    """shared（共享资金）模式产物补齐：该模式引擎不产出 per-symbol 目录，
    build_lab_symbol_detail 的 equity/orders/failed_orders 全为 None。

    - orders/failed_orders：从任务级 orders.csv / failed_orders.csv 按 symbol 过滤
      （shared 模式订单只有 cost 总费用列，无佣金/印花税拆分，前端如实显示「—」）；
    - wear：任务级 round_trips 含真实费用拆分列，聚合出该股磨损
      （commission/stamp_tax/transfer_fee/total_cost/invested=买入成交额/gross/net）；
    - equity：仅当整个 run 实际只交易了这 1 只股票时，组合净值即该股策略净值
      （口径正确，直接取任务级 equity_curve.csv）；多股 shared run 无法按股拆净值，
      保持 None 前端整块隐藏（不编数），并回填 summary.total_ret_pct。
    """
    from quant_research_engine.gui.lab_result import _f

    output_dir = Path(str(record.get("output_dir") or ""))
    if data.get("orders") is None:
        rows = _filter_symbol_csv(output_dir / "orders.csv", ts_code)
        if rows:
            data["orders"] = rows
    if data.get("failed_orders") is None:
        rows = _filter_symbol_csv(output_dir / "failed_orders.csv", ts_code)
        if rows:
            data["failed_orders"] = rows

    trades = data.get("trades") or []
    if data.get("wear") is None and trades:
        agg = {"commission": 0.0, "stamp_tax": 0.0, "transfer_fee": 0.0,
               "total_cost": 0.0, "gross_pnl": 0.0, "net_pnl": 0.0, "invested": 0.0}
        for t in trades:
            for key, col in (("commission", "commission"), ("stamp_tax", "stamp_tax"),
                             ("transfer_fee", "transfer_fee"), ("total_cost", "total_cost"),
                             ("gross_pnl", "gross_pnl"), ("net_pnl", "net_pnl"),
                             ("invested", "entry_notional")):
                agg[key] += _f(t.get(col)) or 0.0
        if agg["invested"] > 0 or agg["total_cost"] > 0:
            data["wear"] = {k: round(v, 2) for k, v in agg.items()}
            data["wear"]["trades"] = len(trades)
            data["wear"]["other_cost"] = round(
                agg["total_cost"] - agg["commission"] - agg["stamp_tax"], 2)

    if data.get("equity") is None and single_symbol:
        eq_path = output_dir / "equity_curve.csv"
        if eq_path.is_file():
            try:
                rows = _read_csv_f(eq_path)
            except OSError:
                rows = []
            pairs = [
                (str(r.get("trade_date") or "").strip(), _f(str(r.get("total_equity")) if r.get("total_equity") is not None else None))
                for r in rows
            ]
            pairs = [(d, v) for d, v in pairs if d and v is not None]
            if pairs:
                data["equity"] = {"dates": [d for d, _ in pairs],
                                  "values": [v for _, v in pairs]}
                vals = data["equity"]["values"]
                if len(vals) >= 2 and vals[0]:
                    data.setdefault("summary", {})["total_ret_pct"] = round(vals[-1] / vals[0] - 1, 6)
    return None


def build_symbol_detail_files(
    record: dict[str, Any],
    max_total_bytes: int = SYMBOL_DETAILS_MAX_BYTES,
) -> dict[str, Any]:
    """为实际触发交易的个股生成详情产物（worker 侧，有行情库）。

    产物：<output_dir>/_symbol_details/<ts_code>.json.gz，内容即
    build_lab_symbol_detail 的 JSON（剔除 benchmarks——任务级 chart_data
    已含基准序列，云端按个股净值日期对齐注入，避免每股重复回传）。
    shared 模式经 _enrich_shared_symbol_detail 补齐 orders/wear/单票净值。
    文件登记进 record["artifacts"]，随既有 result/files 通道回传。
    失败不拖垮回传：整体 try 兜底，返回 {"count", "bytes", "truncated"}。
    """
    import gzip

    meta: dict[str, Any] = {"count": 0, "bytes": 0, "truncated": False}
    try:
        from quant_research_engine.gui.lab_result import (
            _symbol_trade_stats,
            build_lab_symbol_detail,
        )

        stats = _symbol_trade_stats(record)  # round_trips.csv 只解析一次，逐股复用
        if not stats:
            return meta
        # 按 symbol 预分组 round_trips 行，供 build_lab_symbol_detail 的
        # trades 兜底分支复用（避免每股重读全量 CSV 的第二个 O(n²) 点）
        from quant_research_engine.gui.lab_result import _find_output_file, _read_csv

        rt_by_symbol: dict[str, list[dict[str, str]]] = {}
        rt_path = _find_output_file(record, "round_trips.csv")
        if rt_path is not None:
            try:
                for r in _read_csv(rt_path):
                    sym = (r.get("symbol") or "").strip()
                    if sym:
                        rt_by_symbol.setdefault(sym, []).append(r)
            except OSError:
                rt_by_symbol = {}
        output_dir = Path(str(record.get("output_dir") or ""))
        if not output_dir.is_dir():
            return meta
        detail_dir = output_dir / SYMBOL_DETAILS_DIRNAME
        detail_dir.mkdir(parents=True, exist_ok=True)
        artifacts = record.setdefault("artifacts", {})
        # 与持仓盈亏相关性最高的优先（截断时保住头部）
        ordered = sorted(stats, key=lambda s: abs(stats[s]["total_pnl"]), reverse=True)
        single_symbol = len(ordered) == 1
        for ts_code in ordered:
            try:
                data = build_lab_symbol_detail(
                    record, ts_code, stats=stats, round_trips_by_symbol=rt_by_symbol
                )
            except Exception:
                continue
            if not data:
                continue
            try:
                _enrich_shared_symbol_detail(record, data, ts_code, single_symbol=single_symbol)
            except Exception:
                pass  # 补齐失败保留原始详情（降级，不拖垮产物）
            data.pop("benchmarks", None)
            data.pop("benchmark_note", None)
            blob = gzip.compress(
                json.dumps(_json_sanitize(data), ensure_ascii=False, default=str).encode("utf-8")
            )
            if meta["bytes"] + len(blob) > max_total_bytes:
                meta["truncated"] = True
                break
            rel = f"{SYMBOL_DETAILS_DIRNAME}/{ts_code}.json.gz"
            path = detail_dir / f"{ts_code}.json.gz"
            path.write_bytes(blob)
            artifacts[rel] = str(path)
            meta["count"] += 1
            meta["bytes"] += len(blob)
    except Exception:
        return meta
    return meta


#: 回传文件清单的成员上限（总体积；大文件留 worker 本地，M4 走 OSS 直传）
RESULT_FILES_MAX_BYTES = 20 * 1024 * 1024


def collect_result_files(record: dict[str, Any],
                         max_total_bytes: int = RESULT_FILES_MAX_BYTES) -> list[dict[str, Any]]:
    """收集 run 产物文件清单（17 协议 §3.3 files）：name/size/sha256 + 本地 path。
    幂等：同一 job 重复执行产物覆盖写（同 run_id 目录），清单重算即可。"""
    import hashlib

    files: list[dict[str, Any]] = []
    total = 0
    # per-symbol 详情产物（_symbol_details/）优先进入清单：它们是个股详情页
    # 在云端唯一的数据来源；其余大文件超限仍留 worker 本地（M4 走 OSS）
    ordered = sorted(
        (record.get("artifacts") or {}).items(),
        key=lambda kv: (0 if kv[0].startswith(SYMBOL_DETAILS_DIRNAME + "/") else 1, kv[0]),
    )
    for rel, abs_path in ordered:
        path = Path(abs_path)
        if not path.is_file():
            continue
        size = path.stat().st_size
        if total + size > max_total_bytes:
            continue  # 超体积上限的跳过（仍留本地，不进回传清单）
        files.append({
            "name": Path(rel).name if len(Path(rel).parts) == 1 else rel,
            "size": size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "path": str(path),
        })
        total += size
    return files


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
