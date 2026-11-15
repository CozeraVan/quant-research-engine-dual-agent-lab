#!/usr/bin/env python3
"""F-21：独立重算 ema_250，与因子库存值在 2026-10-12…2026-10-26 窗口对账。

背景（14 号文档 F.3-21）：`ema_250` 在该窗口有 11 点独立重算不一致（max_abs=0.287911）。
本脚本只读：从 `public.stock_daily` 读取**全部历史**的原始价 × adj_factor（后复权），
用 pandas `ewm(span=250, adjust=False)` 重算，与 `factors.stock_daily_overlap_close.ema_250`
逐日对比，输出 max_abs 与逐日明细。全历史用于排除 2024 截断造成的种子/暖机误判；
**不写任何表、不重算全库。**
"""

from __future__ import annotations

import os
import sys

import pandas as pd
from sqlalchemy import create_engine, text

CODES = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000651.SZ"]
WINDOW = ("2026-10-12", "2026-10-26")


def main() -> int:
    eng = create_engine(os.environ["QRE_MARKET_DB_URL"])
    q = text("""
        SELECT d.ts_code, d.trade_date, d.close, d.adj_factor, o.ema_250
        FROM public.stock_daily d
        JOIN factors.stock_daily_overlap_close o
          ON o.ts_code = d.ts_code AND o.trade_date = d.trade_date
        WHERE d.ts_code = ANY(:codes)
        ORDER BY d.ts_code, d.trade_date
    """)
    df = pd.read_sql(q, eng, params={"codes": CODES}, parse_dates=["trade_date"])
    if df.empty:
        print("无数据")
        return 1
    df["hfq_close"] = pd.to_numeric(df.close) * pd.to_numeric(df.adj_factor)

    print(f"标的数 {df.ts_code.nunique()}，行数 {len(df)}")
    worst = 0.0
    for code, g in df.groupby("ts_code"):
        g = g.sort_values("trade_date").reset_index(drop=True)
        g["ema250_recalc"] = g.hfq_close.ewm(span=250, adjust=False).mean()
        w = g[(g.trade_date >= WINDOW[0]) & (g.trade_date <= WINDOW[1])].copy()
        if w.empty:
            continue
        w["abs_diff"] = (w.ema250_recalc - w.ema_250).abs()
        max_abs = float(w.abs_diff.max())
        worst = max(worst, max_abs)
        print(f"\n{code} 窗口内 {len(w)} 行，max_abs={max_abs:.6f}")
        cols = ["trade_date", "ema_250", "ema250_recalc", "abs_diff"]
        print(w[cols].to_string(index=False,
                                formatters={"trade_date": lambda d: d.strftime("%Y-%m-%d"),
                                            "ema_250": "{:.4f}".format,
                                            "ema250_recalc": "{:.4f}".format,
                                            "abs_diff": "{:.6f}".format}))
    print(f"\n全样本窗口内 max_abs = {worst:.6f}（此前记录 0.287911）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
