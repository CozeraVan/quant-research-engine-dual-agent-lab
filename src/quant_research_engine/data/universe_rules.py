"""股票池卫生规则：把「历史不可信」的代码挡在自动解析的宇宙之外。

## 规则本体（QRE-UNIVERSE-NEEQ-LEGACY）

`920%.BJ`（北交所）代码在 **2021-11-15**（北交所开市）之前的历史是**三板残留**：
代码 2021 年才从全国股转系统平移过来，平移前的"价格"不是 A 股意义的市场价。
实测（`tushare_data.stock_daily`）：226 个 `920%.BJ` 代码带开市前数据，共 78,423 行，
其中 **74.7%** 是垃圾行——`close` 恒等于 `1`、`1→5.5→9→1→9→3.19` 式跳变、
成交 30 股、成交额 16.5 元，最早一条 2009-01-09。表里与正常日线**无缝拼接、无任何标记**。

它已经造成的后果（2026-10-29 P0-2 全库扫描）：
- job 66 `920556` 持仓期年化爆成 `5051142288902.57%`、job 58 `920832` 爆成 `3.58e+35%`；
- job 78 `920809.BJ` FRM 压力情景 `crash_2015` 策略累计收益 **+63125%**；
- job 66 `920641.BJ` 区间自然涨幅 **3681%**；
- job 58/66/74/78 四个全期任务 12.9%~22.6% 的毛盈亏来自 115 只这类个股
  （任务已按用户裁定删除，见 `CR-2026-10-29_polluted_jobs_purge.md`）。

**`stock_daily` 源数据一行未改**（纪律：源数据只读），所以脏行还在表里——
若不设这道闸，下次全期回测会再次被污染。

## 规则语义

只作用于**自动解析的全市场宇宙**（`codes` 为空时），不作用于用户显式指定的代码
——用户点名要某只股票是他的选择，引擎不替他改。

判定用**实际加载区间**而不是回测区间：增量路径会为指标 warm-up 多加载
`warmup_days` 天历史（`incremental.py` 用 `warmup_days*2`），
所以即便回测起点在北交所开市之后，warm-up 仍可能伸进脏数据里。
因此调用方必须传「本次会加载到的最早日期」，由本模块判断该日期是否已安全。
"""

from __future__ import annotations

from datetime import date, timedelta

#: 北交所开市日。此前 `920%.BJ` 代码的三板历史一律视为不可信。
BJ_MARKET_OPEN = date(2021, 11, 15)

#: 三板残留代码段（北交所）。用前缀判定：表内 920xxx 全部是 .BJ。
NEEQ_LEGACY_PREFIX = "920"


def is_neeq_legacy_code(ts_code: str) -> bool:
    """是否北交所（原三板）代码——2021-11-15 之前历史不可信。"""
    return str(ts_code).startswith(NEEQ_LEGACY_PREFIX)


def filter_untrusted_symbols(
    codes: list[str],
    *,
    load_start: date,
    warmup_days: int = 0,
) -> list[str]:
    """从**自动解析**的宇宙里剔除「加载区间会碰到三板残留脏数据」的北交所代码。

    Args:
        codes: 待过滤代码列表（已按自动规则解析出来的全集）。
        load_start: 本次实际会加载到的最早日期（回测起点，或回测起点减 warm-up）。
        warmup_days: 额外向前加载的天数（增量路径用；批处理/共享路径传 0）。

    Returns:
        过滤后的代码列表，顺序不变。加载区间整体在北交所开市之后时原样返回
        （那种情况下这些代码的数据是真实的北交所行情，没有理由排除）。

    注意：**不要**用它过滤用户显式指定的 `codes`——显式点名是用户的选择。
    """
    effective_start = load_start - timedelta(days=warmup_days)
    if effective_start >= BJ_MARKET_OPEN:
        return list(codes)
    return [c for c in codes if not is_neeq_legacy_code(c)]
