#!/usr/bin/env python
"""CR-2026-10-04 模块二：策略信号扫描（本机 worker 侧，refresh 管线尾钩触发）。

链路：GET /api/worker/watches（X-Worker-Token）→ 按 scope 解析股票池 →
本地因子库/行情库加载面板 → 复用引擎 evaluation.signals.evaluate_expression_signal
（AST 白名单求值器，不重写）判最新交易日 entry/exit → POST /api/worker/signals
批量回传（云端唯一约束幂等，重跑安全）。

口径：日线收盘后 T+1 参考信号，不构成投资建议（页面同步免责）。

环境变量：QRE_SAAS_BASE_URL / QRE_WORKER_TOKEN（同 worker）、
QRE_MARKET_DB_URL（本地行情大库）、QRE_SIGNAL_SCAN_LOOKBACK_DAYS
（面板回看天数，默认 40——表达式仅含 shift(1) 类短回看，因子列均为预计算物化表）。

失败纪律：单个 watch 失败记日志继续；云端不可达记日志退出非零；幂等可重跑。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any

import pandas as pd
import yaml
from sqlalchemy import create_engine, text

DEFAULT_LOOKBACK_DAYS = 40
MAX_SIGNALS_PER_WATCH = 5000  # 单 watch 单日信号上限（防全 A 入口条件失控刷屏）
BATCH_SIZE = 2000


def _log(msg: str) -> None:
    import time
    print(f"[signal-scan {time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# --- 云端访问（stdlib urllib，与 worker client 同纪律） ---

def cloud_call(method: str, path: str, payload: dict | None = None, *,
               base_url: str, token: str, timeout: float = 60.0) -> dict:
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}", data=body, method=method,
        headers={"X-Worker-Token": token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def load_watches(*, base_url: str, token: str) -> list[dict[str, Any]]:
    return cloud_call("GET", "/api/worker/watches", base_url=base_url, token=token).get("watches") or []


def post_signals(events: list[dict[str, Any]], *, base_url: str, token: str) -> dict:
    return cloud_call("POST", "/api/worker/signals", {"events": events},
                      base_url=base_url, token=token, timeout=120.0)


# --- 信号计算（复用引擎求值器） ---

def parse_signal_spec(yaml_text: str) -> dict[str, Any]:
    """策略 YAML → 信号规格：entry/exit 表达式 + 因子/行情字段映射。"""
    cfg = yaml.safe_load(yaml_text) or {}
    data = cfg.get("data") or {}
    signal = cfg.get("signal") or {}
    return {
        "entry": signal.get("entry"),
        "exit": signal.get("exit"),
        "factor_fields": data.get("factor_fields") or {},
        "market_fields": data.get("market_fields") or [],
    }


def resolve_codes(scope_type: str, scope_payload: dict | None, engine) -> list[str]:
    """scope → ts_code 列表。last_run_universe/custom 用 payload 快照；
    sector 走 universe_members（本地全量库）；all_a 取最近交易日有行情的全体。"""
    payload = scope_payload or {}
    if scope_type in ("last_run_universe", "custom"):
        codes = payload.get("codes") or []
        return [str(c).strip() for c in codes if str(c).strip()]
    if scope_type == "sector":
        from quant_research_engine.gui.universe import universe_members
        return universe_members(str(payload.get("group") or ""), str(payload.get("key") or ""))
    if scope_type == "all_a":
        with engine.connect() as conn:
            latest = conn.execute(text("SELECT max(trade_date) FROM public.stock_daily")).scalar_one()
            if latest is None:
                return []
            rows = conn.execute(
                text("SELECT DISTINCT ts_code FROM public.stock_daily WHERE trade_date = :d"),
                {"d": latest},
            ).fetchall()
        return sorted(r[0] for r in rows)
    raise ValueError(f"未知 scope_type: {scope_type}")


def load_panel(engine, codes: list[str], spec: dict[str, Any],
               d0: date, d1: date) -> pd.DataFrame:
    """按 spec 拉取所需列合并面板（ts_code, trade_date, 引用列），
    sort(ts_code, trade_date)——口径与 evaluation engine 框架一致。"""
    used = set()
    import ast as _ast
    for expr in (spec.get("entry"), spec.get("exit")):
        if expr:
            for node in _ast.walk(_ast.parse(expr, mode="eval")):
                if isinstance(node, _ast.Name):
                    used.add(node.id)
    frames = []
    market_cols = [c for c in (spec.get("market_fields") or []) if c in used]
    # close 恒拉：信号事件的参考价列（即使表达式不引用）
    cols = sorted({*market_cols, "close"})
    col_sql = ", ".join(cols)
    frames.append(pd.read_sql(
        text(f"SELECT ts_code, trade_date, {col_sql} FROM public.stock_daily "
             "WHERE trade_date BETWEEN :d0 AND :d1 AND ts_code = ANY(:codes)"),
        engine, params={"d0": d0, "d1": d1, "codes": codes}))
    by_table: dict[str, list[tuple[str, str]]] = {}
    for alias, target in (spec.get("factor_fields") or {}).items():
        if alias not in used:
            continue
        parts = str(target).split(".")
        if len(parts) == 2:
            schema, table, column = "factors", parts[0], parts[1]
        elif len(parts) == 3:
            schema, table, column = parts
        else:
            raise ValueError(f"非法因子目标: {target!r}")
        by_table.setdefault(f"{schema}.{table}", []).append((alias, column))
    for qtable, pairs in sorted(by_table.items()):
        col_sql = ", ".join(sorted({c for _, c in pairs}))
        df = pd.read_sql(
            text(f"SELECT ts_code, trade_date, {col_sql} FROM {qtable} "
                 "WHERE trade_date BETWEEN :d0 AND :d1 AND ts_code = ANY(:codes)"),
            engine, params={"d0": d0, "d1": d1, "codes": codes})
        for alias, column in pairs:
            if alias != column:
                df = df.rename(columns={column: alias})
        frames.append(df)
    if not frames:
        raise ValueError("表达式未引用任何行情/因子列")
    panel = frames[0]
    for df in frames[1:]:
        panel = panel.merge(df, on=["ts_code", "trade_date"], how="left")
    panel["trade_date"] = pd.to_datetime(panel.trade_date)
    return panel.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def compute_signals(panel: pd.DataFrame, expression: str, signal_date: date) -> list[str]:
    """面板 + 表达式 → 信号日当日命中的 ts_code 列表。
    按 ts_code 分组逐组求值（shift 口径不跨股票边界）。"""
    if panel.empty or not expression:
        return []
    from quant_research_engine.evaluation.signals import evaluate_expression_signal

    hits: list[str] = []
    for ts_code, g in panel.groupby("ts_code", sort=False):
        mask = evaluate_expression_signal(g.reset_index(drop=True), expression)
        g2 = g.reset_index(drop=True).loc[mask]
        if (g2["trade_date"].dt.date == signal_date).any():
            hits.append(str(ts_code))
    return hits


def scan_watch(watch: dict[str, Any], engine, *, lookback_days: int = DEFAULT_LOOKBACK_DAYS,
               today: date | None = None) -> list[dict[str, Any]]:
    """单个 watch → 信号事件列表（空列表=无信号）。"""
    spec = parse_signal_spec(watch["yaml"])
    if not spec.get("entry") and not spec.get("exit"):
        _log(f"watch {watch['watch_id']}（{watch.get('strategy_name')}）无信号表达式，跳过")
        return []
    codes = resolve_codes(watch["scope_type"], watch.get("scope_payload"), engine)
    if not codes:
        _log(f"watch {watch['watch_id']} 股票池为空，跳过")
        return []
    with engine.connect() as conn:
        latest = conn.execute(text("SELECT max(trade_date) FROM public.stock_daily")).scalar_one()
    if latest is None:
        return []
    signal_date = latest if isinstance(latest, date) else latest.date()
    if today and signal_date > today:
        signal_date = today
    d0 = signal_date - timedelta(days=lookback_days)
    panel = load_panel(engine, codes, spec, d0, signal_date)
    closes = (panel.loc[panel["trade_date"].dt.date == signal_date, ["ts_code", "close"]]
              .set_index("ts_code")["close"] if "close" in panel.columns else pd.Series(dtype=float))
    events = []
    for sig_type, expr in (("entry", spec.get("entry")), ("exit", spec.get("exit"))):
        if not expr:
            continue
        for ts_code in compute_signals(panel, expr, signal_date)[:MAX_SIGNALS_PER_WATCH]:
            price = closes.get(ts_code)
            events.append({
                "watch_id": watch["watch_id"], "trade_date": signal_date.isoformat(),
                "ts_code": ts_code, "signal_type": sig_type,
                "price": None if price is None or pd.isna(price) else float(price),
            })
    return events


def main() -> int:
    base_url = os.environ.get("QRE_SAAS_BASE_URL") or os.environ.get("SAAS_CLOUD_URL", "")
    token = os.environ.get("QRE_WORKER_TOKEN") or os.environ.get("SAAS_WORKER_TOKEN", "")
    db_url = os.environ.get("QRE_MARKET_DB_URL", "")
    if not (base_url and token and db_url):
        _log("缺少 QRE_SAAS_BASE_URL / QRE_WORKER_TOKEN / QRE_MARKET_DB_URL，退出")
        return 2
    lookback = int(os.environ.get("QRE_SIGNAL_SCAN_LOOKBACK_DAYS", DEFAULT_LOOKBACK_DAYS))
    watches = load_watches(base_url=base_url, token=token)
    _log(f"拉到 {len(watches)} 个 enabled watch")
    if not watches:
        return 0
    engine = create_engine(db_url)
    total = 0
    for w in watches:
        try:
            events = scan_watch(w, engine, lookback_days=lookback)
        except Exception as exc:  # noqa: BLE001 —— 单 watch 失败不影响其余
            _log(f"watch {w.get('watch_id')} 扫描失败（{exc}），跳过")
            continue
        _log(f"watch {w['watch_id']}（{w.get('strategy_name')}，{w['scope_type']}）"
             f"信号 {len(events)} 条")
        for i in range(0, len(events), BATCH_SIZE):
            try:
                resp = post_signals(events[i:i + BATCH_SIZE], base_url=base_url, token=token)
                total += int(resp.get("inserted", 0))
            except (OSError, urllib.error.URLError) as exc:
                _log(f"watch {w['watch_id']} 回传失败（{exc}）")
    _log(f"完成：新增信号 {total} 条（重复自动去重）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
