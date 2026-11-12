#!/usr/bin/env python
"""《我不是股神》Windows 预览本地样本数据源（契约 + mock 先行，2026-11-12）。

背景：Windows 预览库 qre_ui_dev 只有 SaaS 业务表，没有行情/因子表；
生产行情库（tushare_data）禁止直连。本模块按
tests/test_trading_game_web.py::FakeStore 的最小 store 契约提供**合成样本**，
让真实的 PostgresGameDataProvider / GameSession / DailyGameEngine / 因子换算
与审计代码原样跑通：不连接任何数据库，不依赖 WSL 文件路径。

契约（PostgresGameDataProvider 消费侧，与 FakeStore 同构）：
  settings.tables.market_daily_table / qualified_table(name)
  latest_trade_date() -> date
  list_symbols_with_bars(start, end) -> list[str]
  load_raw_bars(symbol, start, end) -> list[dict]   # 原始价 + adj_factor；vol=手、amount=千元（生产单位）
  load_factor_history(symbols, requests, start, end) -> DataFrame
      # 列：ts_code, trade_date, 每个 request.logical_name（canonical）一列

口径（与 22_TRADING_GAME.md §15、43/45 号文档一致，不造第三套实现）：
  - K 线：固定锚点前复权 qfq = raw × adj_factor / anchor（provider 侧完成）；
  - 因子：在后复权 hfq = raw × adj_factor 上计算（模拟因子表落库口径），
    价格型列由 provider 按 gui.factor_registry 的族白名单除以 anchor；
  - EMA 用 SMA 种子（TA-Lib 口径）、BOLL 用 ddof=1，与 game/validation.py
    的独立重算一致，样本审计 mismatches 应为 0。

样本为确定性合成数据（固定随机种子）。代码键只是内部标识，游戏服务端
会做匿名映射，真实代码/日期不会到达前端。除权除息事件让 anchor ≠ 1，
确保价格型因子换算路径被真实覆盖。
"""

from __future__ import annotations

import math
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pandas as pd

SAMPLE_SEED = 20261112
N_DAYS = 1600  # >= warmup 250 + game 1250
END_DATE = date(2026, 11, 11)
# 合成样本内部键（主板 10% 涨跌幅口径），不代表任何真实行情。
SYMBOLS = ("600001.SH", "600002.SH", "000002.SZ")
# 交易日序号 -> adj_factor 乘数（除权除息事件）；anchor = 1.08 × 1.12 = 1.2096
EX_DIV = {500: 1.08, 1100: 1.12}

_O = "factors.stock_daily_overlap_close."
_T = "factors.stock_daily_overlap_typical_price."
_M = "factors.stock_daily_momentum_close."
_V = "factors.stock_daily_volatility_close."
_R = "factors.stock_daily_risk."
_L = "factors.stock_daily_liquidity."


def _trading_days(n: int, end: date) -> list[date]:
    days: list[date] = []
    cur = end
    while len(days) < n:
        if cur.weekday() < 5:
            days.append(cur)
        cur -= timedelta(days=1)
    days.reverse()
    return days


def _ema(values: list[float], span: int) -> list[float | None]:
    """TA-Lib 口径：SMA 种子 + alpha=2/(span+1)，与 validation.recompute_ema 一致。"""
    out: list[float | None] = [None] * len(values)
    if span <= 0 or len(values) < span:
        return out
    seed = sum(values[:span]) / span
    out[span - 1] = seed
    alpha = 2.0 / (span + 1.0)
    for i in range(span, len(values)):
        seed = values[i] * alpha + seed * (1.0 - alpha)
        out[i] = seed
    return out


def _macd(closes: list[float]) -> tuple[list, list, list]:
    e12, e26 = _ema(closes, 12), _ema(closes, 26)
    dif = [None if a is None or b is None else a - b for a, b in zip(e12, e26)]
    valid = [v for v in dif if v is not None]
    dea_valid = _ema(valid, 9)
    dea: list[float | None] = [None] * len(closes)
    it = iter(dea_valid)
    for i, v in enumerate(dif):
        if v is not None:
            dea[i] = next(it)
    hist = [None if d is None or s is None else 2.0 * (d - s) for d, s in zip(dif, dea)]
    return dif, dea, hist


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    gains = losses = 0.0
    ag = al = 0.0
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        g, l = max(chg, 0.0), max(-chg, 0.0)
        if i <= period:
            gains += g
            losses += l
            if i == period:
                ag, al = gains / period, losses / period
                out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
        else:
            ag = (ag * (period - 1) + g) / period
            al = (al * (period - 1) + l) / period
            out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
    return out


def _boll(closes: list[float], period: int = 20, mult: float = 2.0):
    """ddof=1，与 validation.recompute_boll 一致。"""
    n = len(closes)
    mid: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    upper: list[float | None] = [None] * n
    for i in range(period - 1, n):
        window = closes[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / (period - 1)
        dev = math.sqrt(max(variance, 0.0))
        mid[i] = mean
        lower[i] = mean - mult * dev
        upper[i] = mean + mult * dev
    return lower, mid, upper


def _return_std(closes: list[float], period: int = 21) -> list[float | None]:
    rets = [None] + [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
    out: list[float | None] = [None] * len(closes)
    for i in range(period, len(closes)):
        window = rets[i - period + 1:i + 1]
        mean = sum(window) / period
        variance = sum((v - mean) ** 2 for v in window) / (period - 1)
        out[i] = math.sqrt(max(variance, 0.0))
    return out


def _avg_turnover(vols: list[float], period: int = 5) -> list[float | None]:
    out: list[float | None] = [None] * len(vols)
    for i in range(period - 1, len(vols)):
        out[i] = sum(vols[i - period + 1:i + 1]) / period / 1e8
    return out


def _build_symbol(symbol: str, seed: int) -> dict:
    rng = random.Random(seed)
    days = _trading_days(N_DAYS, END_DATE)
    rows: list[dict] = []
    closes_raw: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    vols: list[float] = []
    adjs: list[float] = []
    prev_close = round(rng.uniform(12.0, 28.0), 2)
    adj = 1.0
    for i, day in enumerate(days):
        mult = EX_DIV.get(i)
        if mult:
            adj *= mult
        ret = max(-0.095, min(0.095, rng.gauss(0.0004, 0.016)))
        close = prev_close * (1.0 + ret)
        gap = max(-0.09, min(0.09, rng.gauss(0.0, 0.006)))
        open_ = prev_close * (1.0 + gap)
        if mult:
            # 除权除息：原始价按事件下落，hfq 序列保持连续
            close /= mult
            open_ /= mult
        close = round(close, 2)
        open_ = round(open_, 2)
        # high/low 与 open 至少差 1 tick：前复权缩放后余量仍 > 半 tick(0.005)，
        # 开盘价限价委托必成交（与真实行情同 tick 精度的行为一致）。
        high = max(round(max(open_, close) * (1.0 + abs(rng.gauss(0.0, 0.004))), 2),
                   open_ + 0.01, close)
        low = max(min(round(min(open_, close) * (1.0 - abs(rng.gauss(0.0, 0.004))), 2),
                      open_ - 0.01, close), 0.01)
        pre_close = prev_close if not mult else round(prev_close / mult, 2)
        # 生产单位：vol=手（1 手=100 股）、amount=千元（46 号任务单 T1）。
        # 先按股/元生成（随机序列与取整不变），再换算落库；
        # 均价（元/股）= amount×1000/(vol×100) = amount*10/vol，逐根断言见
        # tests/test_trading_game_windows_fixes.py::test_sample_vol_amount_production_units。
        vol_shares = round(rng.uniform(2e6, 9e6) * (1.0 + 0.4 * math.sin(i / 17.0)), 0)
        amount_yuan = round(vol_shares * (open_ + close) / 2.0, 2)
        vol = vol_shares / 100.0
        amount = amount_yuan / 1000.0
        rows.append({
            "ts_code": symbol, "trade_date": day,
            "open": open_, "high": high, "low": low, "close": close,
            "pre_close": pre_close, "vol": vol, "amount": amount,
            "adj_factor": adj,
        })
        closes_raw.append(close)
        highs.append(high)
        lows.append(low)
        # 流动性样本因子保持股数输入：生产公式是 ts_mean(turnover_rate,5)
        # （见 docs/agent/change_requests/factor_specs_p4p5p7.md），样本本就是合成占位，
        # 沿用股数序列使因子值与单位修复前逐位一致，不被 vol 单位变更连带缩放。
        vols.append(vol_shares)
        adjs.append(adj)
        prev_close = close

    # 因子表口径：hfq = raw × adj_factor
    hfq = [c * a for c, a in zip(closes_raw, adjs)]
    hfq_typical = [(h + l + c) / 3.0 * a for h, l, c, a in zip(highs, lows, closes_raw, adjs)]
    dif, dea, hist = _macd(hfq)
    bbl, bbm, bbu = _boll(hfq)
    factors = {
        _O + "ema_5": _ema(hfq, 5),
        _O + "ema_20": _ema(hfq, 20),
        _O + "ema_60": _ema(hfq, 60),
        _O + "ema_250": _ema(hfq, 250),
        _M + "macd_12_26_9": dif,
        _M + "macds_12_26_9": dea,
        _M + "macdh_12_26_9": hist,
        _M + "rsi_14": _rsi(hfq),
        _V + "bbl_20_2_0_2_0": bbl,
        _V + "bbm_20_2_0_2_0": bbm,
        _V + "bbu_20_2_0_2_0": bbu,
        # 目录增选样本：同列不同价格口径 / 风险 / 流动性
        _T + "ema_5": _ema(hfq_typical, 5),
        _R + "return_std_21d": _return_std(hfq),
        _L + "avg_turnover_5d": _avg_turnover(vols),
    }
    return {"rows": rows, "factors": factors}


class SampleGameStore:
    """FakeStore 同构契约的本地样本实现；零数据库连接。"""

    settings = SimpleNamespace(tables=SimpleNamespace(market_daily_table="public.stock_daily"))

    def __init__(self, seed: int = SAMPLE_SEED) -> None:
        self._days = _trading_days(N_DAYS, END_DATE)
        self._data = {sym: _build_symbol(sym, seed + i) for i, sym in enumerate(SYMBOLS)}

    def qualified_table(self, name: str) -> str:
        return name

    def latest_trade_date(self) -> date:
        return self._days[-1]

    def list_symbols_with_bars(self, start: date, end: date) -> list[str]:
        if start > self._days[-1] or end < self._days[0]:
            return []
        return list(SYMBOLS)

    def load_raw_bars(self, symbol: str, start: date, end: date) -> list[dict]:
        return [r for r in self._data[symbol]["rows"] if start <= r["trade_date"] <= end]

    def load_factor_history(self, symbols, requests, start: date, end: date) -> pd.DataFrame:
        columns = ["ts_code", "trade_date"]
        for req in requests:
            if req.logical_name not in columns:
                columns.append(req.logical_name)
        records = []
        for sym in symbols:
            data = self._data.get(sym)
            if data is None:
                continue
            for i, day in enumerate(self._days):
                if not (start <= day <= end):
                    continue
                rec = {"ts_code": sym, "trade_date": pd.Timestamp(day)}
                for req in requests:
                    series = data["factors"].get(req.logical_name)
                    value = None if series is None else series[i]
                    # 未预置的 canonical 给 NaN（模拟列存在但无数据），不抛异常
                    rec[req.logical_name] = float("nan") if value is None else round(value, 4)
                records.append(rec)
        return pd.DataFrame(records, columns=columns)