from __future__ import annotations

import os
from datetime import date

import pandas as pd

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.data.interfaces import FactorDataStore, MarketDataStore, ReferenceDataStore

#: 分块装配的默认块大小（股票数；QRE_SHARED_CHUNK_SIZE 可配）
DEFAULT_ASSEMBLE_CHUNK_SIZE = 500


class ResearchFrameAssembler:
    def __init__(self, store: MarketDataStore | FactorDataStore | ReferenceDataStore) -> None:
        self.store = store

    def build(
        self,
        *,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        market_fields: list[str],
        factor_fields: list[FactorFieldRequest],
        include_metadata: bool = False,
        metadata_as_of: date | None = None,
        benchmark_table: str | None = None,
        benchmark_code: str | None = None,
        benchmark_value_column: str = "close",
    ) -> pd.DataFrame:
        bars = self.store.load_daily_bars(
            ts_codes=ts_codes,
            start=start,
            end=end,
            fields=market_fields,
        )
        frame = bars
        if factor_fields:
            factors = self.store.load_factor_history(
                ts_codes=ts_codes,
                field_requests=factor_fields,
                start=start,
                end=end,
            )
            frame = frame.merge(factors, on=["ts_code", "trade_date"], how="inner")
        if include_metadata:
            metadata = self.store.load_security_metadata(ts_codes=ts_codes, as_of=metadata_as_of)
            frame = frame.merge(metadata, on="ts_code", how="left")
        if benchmark_table and benchmark_code:
            benchmark_bars = self.store.load_benchmark_bars(
                table_name=benchmark_table,
                ts_codes=[benchmark_code],
                start=start,
                end=end,
                fields=[benchmark_value_column],
            )
            benchmark_bars = benchmark_bars.rename(columns={benchmark_value_column: "benchmark_close"})
            benchmark_bars["benchmark_return"] = (
                benchmark_bars.groupby("ts_code")["benchmark_close"].pct_change()
            )
            benchmark_cols = benchmark_bars[["trade_date", "benchmark_close", "benchmark_return"]].dropna(
                subset=["benchmark_close"]
            )
            frame = frame.merge(benchmark_cols, on="trade_date", how="left")
        return frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

    def build_chunked(
        self,
        *,
        ts_codes: list[str] | None,
        start: date,
        end: date,
        market_fields: list[str],
        factor_fields: list[FactorFieldRequest],
        metadata_columns: list[str] | None = None,
        chunk_size: int | None = None,
        metadata_as_of: date | None = None,
    ) -> pd.DataFrame:
        """按股票块流式装配（2026-10-18，job#71 全市场全期 OOM 修复）。

        与 ``build()`` 产出的行集/数值一致，差异仅在内存组织：
        - 按 chunk_size 只股票分块走 ``build()``（块内 bars×factors merge），
          块的中间拷贝随迭代释放，不再有全市场多份 merge 副本共存；
        - metadata 只并入 ``metadata_columns`` 指定列（默认撮合必需的
          is_st/is_suspended），避免十几列富 metadata 字符串膨胀到每根 K 线；
        - ts_code 转 category（categories=排序后的全量股票代码，与字符串字典序
          一致）：每格独立 Python str（~60B×行数）塌缩为 int 编码，
          全市场全期 ~1450 万行仅此一项省 ~1.5-2GB/份拷贝。

        返回 frame 未做全局排序（各块内部已按 ts_code/trade_date 有序，块间按
        代码序拼接）；消费方（SharedCashBacktestEngine._prepare_frame）自行排序。
        """
        chunk_size = chunk_size or int(
            os.environ.get("QRE_SHARED_CHUNK_SIZE", DEFAULT_ASSEMBLE_CHUNK_SIZE)
        )
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        metadata = self.store.load_security_metadata(ts_codes=ts_codes, as_of=metadata_as_of)
        wanted_meta = metadata_columns or ["is_st", "is_suspended"]
        meta_cols = ["ts_code"] + [c for c in dict.fromkeys(wanted_meta) if c in metadata.columns]
        meta_flags = metadata[meta_cols]
        meta_codes = set(meta_flags["ts_code"].dropna().astype(str))
        if ts_codes is None:
            # 股票全集 = 区间内有 K 线的代码 ∪ metadata 代码（与原 build 全量读取
            # 由 bars 驱动、metadata 左连的口径一致，不漏无 metadata 的代码）；
            # store 无 list_symbols_with_bars（测试桩）时退化为 metadata 代码集。
            bars_lister = getattr(self.store, "list_symbols_with_bars", None)
            bars_codes = set(bars_lister(start, end)) if callable(bars_lister) else set()
            all_codes = sorted(meta_codes | bars_codes)
        else:
            all_codes = sorted(str(c) for c in ts_codes)
        parts: list[pd.DataFrame] = []
        for offset in range(0, len(all_codes), chunk_size):
            chunk_codes = all_codes[offset:offset + chunk_size]
            chunk = self.build(
                ts_codes=chunk_codes,
                start=start,
                end=end,
                market_fields=market_fields,
                factor_fields=factor_fields,
                include_metadata=False,
            )
            if chunk.empty:
                continue
            chunk = chunk.merge(meta_flags, on="ts_code", how="left")
            chunk["ts_code"] = pd.Categorical(
                chunk["ts_code"].astype(str), categories=all_codes
            )
            parts.append(chunk)
        if not parts:
            return pd.DataFrame(columns=["ts_code", "trade_date"])
        return pd.concat(parts, ignore_index=True)
