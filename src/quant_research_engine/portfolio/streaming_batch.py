"""批量回测的流式（分块）执行器（内存峰值控制，2026-09-14 缺陷修复）。

背景：批处理原路径把整个股票池的日线+因子 frame 一次性装内存
（5000 只 × 5 年 + 因子 join 实测峰值 7.7G，被 2G cgroup OOM）。
本模块按股票块流式处理：加载一块 → 跑引擎 → 个股产物立即落盘 →
结果换成磁盘懒加载代理 → 释放，峰值有界（块大小 QRE_BATCH_CHUNK_SIZE，
默认 250 只）。

产物格式零变化：复用 BatchBacktestEngine（块内）+ write_single_symbol_result
（逐股落盘）+ write_batch_result 下游全部聚合函数。聚合输入只有
每股 summary 行（小）与磁盘代理（orders/trades/equity_curve 读盘），
equity 窗口/滚动汇总与全市场报告的读取是逐股瞬时的。

``_DiskBackedSingleResult``：与 SingleSymbolBacktestResult 同属性签名
（orders/trades/failed_orders/equity_curve/summary），DataFrame 属性
从个股产物 CSV 懒加载（用完即释放），summary 常驻（很小）。
"""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Iterator

import pandas as pd

from quant_research_engine.portfolio.batch import (
    BatchBacktestEngine,
    BatchBacktestRequest,
    BatchBacktestResult,
)
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult

DEFAULT_CHUNK_SIZE = 250
#: 股票数超过该值才走流式（小样本维持原路径，零行为变化风险）
STREAMING_MIN_SYMBOLS = DEFAULT_CHUNK_SIZE


def chunk_size_from_env() -> int:
    try:
        return max(1, int(os.environ.get("QRE_BATCH_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)))
    except ValueError:
        return DEFAULT_CHUNK_SIZE


class _DiskBackedSingleResult:
    """磁盘懒加载的 SingleSymbolBacktestResult 代理（签名一致）。"""

    def __init__(self, symbol: str, directory: Path, summary: dict[str, Any]) -> None:
        self.symbol = symbol
        self._dir = directory
        self.summary = summary

    def _read(self, name: str) -> pd.DataFrame:
        path = self._dir / name
        if not path.exists():
            return pd.DataFrame()
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            # 无交易/无数据个股的 orders/trades/equity_curve 是空 DataFrame（无列），
            # to_csv 只写出一个换行——与非流式路径的内存态空 DataFrame 对齐，容忍读回。
            return pd.DataFrame()

    @property
    def orders(self) -> pd.DataFrame:
        return self._read("orders.csv")

    @property
    def trades(self) -> pd.DataFrame:
        return self._read("trades.csv")

    @property
    def failed_orders(self) -> pd.DataFrame:
        return self._read("failed_orders.csv")

    @property
    def equity_curve(self) -> pd.DataFrame:
        return self._read("equity_curve.csv")


def _chunks(items: list[str], size: int) -> Iterator[list[str]]:
    for i in range(0, len(items), size):
        yield items[i:i + size]


def run_batch_streaming(
    *,
    frame_factory: Callable[[list[str]], pd.DataFrame],
    symbols: list[str],
    request: BatchBacktestRequest,
    market_profile: Any,
    output_dir: str | Path | None = None,
    chunk_size: int | None = None,
) -> BatchBacktestResult:
    """分块流式批量回测。

    - ``frame_factory(chunk_symbols)`` 返回该块的研究 frame（装配器按块加载）；
    - 块内用既有 BatchBacktestEngine 跑（口径完全一致）；
    - output_dir 非空时每只股跑完立即 ``write_single_symbol_result`` 落盘，
      结果对象换磁盘代理后释放；
    - 返回的 BatchBacktestResult.summary / summary_metrics 与全量路径
      逐行/逐值一致（summary 行由块内同一 _summary_row 产出，聚合函数
      summarize_batch_summary 作用在同内容拼接表上）。
    """
    from quant_research_engine.portfolio.analytics import summarize_batch_summary
    from quant_research_engine.portfolio.io import write_single_symbol_result

    chunk = chunk_size or chunk_size_from_env()
    engine = BatchBacktestEngine(market_profile)
    results: dict[str, Any] = {}
    summary_parts: list[pd.DataFrame] = []

    for chunk_symbols in _chunks(list(symbols), chunk):
        frame = frame_factory(chunk_symbols)
        chunk_result = engine.run(frame, replace(request, symbols=chunk_symbols))
        summary_parts.append(chunk_result.summary)
        for symbol in chunk_symbols:
            single = chunk_result.results[symbol]
            if output_dir is not None:
                symbol_dir = Path(output_dir) / symbol
                write_single_symbol_result(single, symbol_dir)
                results[symbol] = _DiskBackedSingleResult(symbol, symbol_dir, single.summary)
            else:
                results[symbol] = single
        del frame, chunk_result  # 块级释放

    summary = (
        pd.concat(summary_parts, ignore_index=True)
        if summary_parts
        else pd.DataFrame()
    )
    return BatchBacktestResult(
        symbols=list(symbols),
        results=results,
        summary=summary,
        summary_metrics=summarize_batch_summary(summary),
    )
