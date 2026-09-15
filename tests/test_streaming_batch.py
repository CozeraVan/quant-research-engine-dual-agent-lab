"""流式批量回测（QRE 内存峰值控制，2026-09-14）测试：

- 分块结果与全量 BatchBacktestEngine 逐值一致（summary/交易数/收益）；
- output_dir 模式：逐股产物落盘 + 磁盘代理懒加载 + write_batch_result
  在流式结果上产出与全量路径一致的聚合文件；
- 分块边界（chunk_size=1）正确。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.io import write_batch_result
from quant_research_engine.portfolio.streaming_batch import (
    _DiskBackedSingleResult,
    run_batch_streaming,
)


def make_batch_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ"] * 6 + ["000002.SZ"] * 6,
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09", "2026-01-12"] * 2
            ),
            "open": [10.0, 10.2, 10.5, 10.8, 11.0, 11.2, 20.0, 19.8, 19.5, 19.0, 18.8, 18.6],
            "close": [10.1, 10.4, 10.7, 10.9, 11.1, 11.3, 19.9, 19.7, 19.3, 18.9, 18.7, 18.5],
            "rsi_2": [5.0, 20.0, 30.0, 40.0, 50.0, 60.0, 5.0, 20.0, 30.0, 40.0, 50.0, 60.0],
            "board": ["main_board"] * 6 + ["chinext"] * 6,
            "is_st": [False] * 12,
        }
    )


def _request(symbols=None) -> BatchBacktestRequest:
    return BatchBacktestRequest(
        symbols=symbols or ["000001.SZ", "000002.SZ"],
        initial_cash_per_symbol=100000.0,
        entry_signal="rsi_2 < 10",
        holding_days=3,
    )


def _full_reference():
    engine = BatchBacktestEngine(AShareMarketProfile())
    return engine.run(make_batch_frame(), _request())


def test_streaming_matches_full_run_summary():
    ref = _full_reference()
    frame = make_batch_frame()
    streamed = run_batch_streaming(
        frame_factory=lambda chunk: frame[frame["ts_code"].isin(chunk)].copy(),
        symbols=["000001.SZ", "000002.SZ"],
        request=_request(),
        market_profile=AShareMarketProfile(),
        chunk_size=1,
    )
    assert streamed.symbols == ref.symbols
    pd.testing.assert_frame_equal(
        streamed.summary.reset_index(drop=True), ref.summary.reset_index(drop=True)
    )
    assert streamed.summary_metrics == ref.summary_metrics


def test_streaming_with_output_dir_disk_proxy(tmp_path):
    ref = _full_reference()
    frame = make_batch_frame()
    out = tmp_path / "streamed"
    streamed = run_batch_streaming(
        frame_factory=lambda chunk: frame[frame["ts_code"].isin(chunk)].copy(),
        symbols=["000001.SZ", "000002.SZ"],
        request=_request(),
        market_profile=AShareMarketProfile(),
        output_dir=out,
        chunk_size=1,
    )
    # 逐股产物即时落盘 + 结果换磁盘代理
    for symbol in ("000001.SZ", "000002.SZ"):
        assert (out / symbol / "equity_curve.csv").exists()
        assert (out / symbol / "trades.csv").exists()
        assert isinstance(streamed.results[symbol], _DiskBackedSingleResult)
    # 代理懒加载与原始结果一致（CSV 往返后日期列为字符串，按值比较）
    proxy_trades = streamed.results["000001.SZ"].trades
    ref_trades = ref.results["000001.SZ"].trades
    assert proxy_trades["symbol"].tolist() == ref_trades["symbol"].tolist()
    assert proxy_trades["entry_date"].astype(str).tolist() == ref_trades["entry_date"].astype(str).str[:10].tolist()
    # 下游聚合写出器在流式结果上可用且 summary 一致
    paths = write_batch_result(streamed, out)
    assert paths["summary"].exists()
    written = pd.read_csv(paths["summary"])
    assert written["symbol"].tolist() == ref.summary["symbol"].tolist()
    assert written["total_return"].tolist() == pytest.approx(ref.summary["total_return"].tolist())
    metrics = json.loads(paths["summary_metrics"].read_text(encoding="utf-8"))
    assert metrics["total_trades"] == ref.summary_metrics["total_trades"]


def test_streaming_tolerates_empty_symbol_results(tmp_path):
    """回归（run 20260914T125635220084 崩溃根因）：无交易/无数据个股的空
    DataFrame（无列）落盘为无表头空文件，代理读回须容忍（对齐非流式内存态），
    全链路 write_batch_result（含全市场报告）不炸。"""
    frame = make_batch_frame()
    symbols = ["000001.SZ", "000002.SZ", "999999.XH"]  # 第三只不在 frame 里 → 空结果
    out = tmp_path / "streamed"
    streamed = run_batch_streaming(
        frame_factory=lambda chunk: frame[frame["ts_code"].isin(chunk)].copy(),
        symbols=symbols,
        request=_request(symbols),
        market_profile=AShareMarketProfile(),
        output_dir=out,
        chunk_size=1,
    )
    # 空结果个股的产物为无表头空文件；代理读回为空 DataFrame 而非抛错
    assert (out / "999999.XH" / "trades.csv").read_bytes() == b"\n"
    assert streamed.results["999999.XH"].trades.empty
    assert streamed.results["999999.XH"].equity_curve.empty
    # 全量收尾（write_batch_result 默认含全市场报告）不炸
    paths = write_batch_result(streamed, out)
    assert paths["summary"].exists()
    assert "equity_curve" in paths  # batch 模式的全市场净值曲线键
