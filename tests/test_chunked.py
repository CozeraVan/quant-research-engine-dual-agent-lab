"""Chunked vs unchunked batch backtest equivalence (memory-safe path).

The symbol-chunked path must produce byte-identical summary artifacts to the
unchunked path because batch engines are per-symbol independent.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.orchestration import research_run as rr
from quant_research_engine.orchestration.research_run import ResearchRunRequest
from quant_research_engine.strategies.spec import StrategySpec


def _frame(symbols=("A.SZ", "B.SZ", "C.SZ", "D.SZ", "E.SZ")) -> pd.DataFrame:
    rows = []
    opens = {"A.SZ": 10.0, "B.SZ": 20.0, "C.SZ": 30.0, "D.SZ": 40.0, "E.SZ": 50.0}
    for symbol in symbols:
        for i, d in enumerate(pd.bdate_range("2024-01-01", periods=8)):
            o = opens[symbol] * (1 + 0.01 * ((i % 3) - 1))
            rows.append(
                {
                    "ts_code": symbol,
                    "trade_date": d,
                    "open": round(o, 2),
                    "high": round(o * 1.02, 2),
                    "low": round(o * 0.98, 2),
                    "close": round(o * (1 + 0.005 * ((i % 2) * 2 - 1)), 2),
                    "amount": 1e6,
                }
            )
    return pd.DataFrame(rows)


def _spec() -> StrategySpec:
    return StrategySpec(
        name="chunk_test",
        signal_expression="close < open",
        exit_signal_expression=None,
        market_fields=["open", "high", "low", "close", "amount"],
        factor_fields=[],
        forward_horizons=[1],
        holding_days=3,
        quantiles=None,
    )


def _request(tmp_path: Path, out: str, **overrides) -> ResearchRunRequest:
    defaults = {
        "strategy_path": tmp_path / "s.yaml",
        "start": date(2024, 1, 1),
        "end": date(2024, 1, 31),
        "output_dir": tmp_path / out,
        "engine_impl": "vectorized",
        "compact": True,
    }
    defaults.update(overrides)
    return ResearchRunRequest(**defaults)


def test_chunked_backtest_matches_unchunked(tmp_path, monkeypatch):
    frame = _frame()
    spec = _spec()

    # unchunked reference
    ref_req = _request(tmp_path, "ref")
    status, _ = rr._run_backtest(SimpleNamespace(), spec, ref_req, frame=frame)
    assert status == "ok"

    # chunked: assembler slices the frame per chunk; store lists the symbols
    monkeypatch.setattr(
        rr.ResearchFrameAssembler,
        "build",
        lambda self, ts_codes, start, end, market_fields, factor_fields, **kw: frame.loc[
            frame["ts_code"].isin(ts_codes)
        ].copy(),
    )
    store = SimpleNamespace(
        list_symbols_with_bars=lambda start, end: ["A.SZ", "B.SZ", "C.SZ", "D.SZ", "E.SZ"]
    )
    chunked_req = _request(tmp_path, "chunked", symbol_chunk_size=2)
    status, _ = rr._run_backtest(store, spec, chunked_req, frame=None)
    assert status == "ok"

    ref_summary = (tmp_path / "ref" / "backtest" / "summary.csv").read_bytes()
    chunked_summary = (tmp_path / "chunked" / "backtest" / "summary.csv").read_bytes()
    assert ref_summary == chunked_summary

    ref_metrics = json.loads((tmp_path / "ref" / "backtest" / "summary_metrics.json").read_text())
    chunked_metrics = json.loads((tmp_path / "chunked" / "backtest" / "summary_metrics.json").read_text())
    assert ref_metrics == chunked_metrics


def test_chunked_backtest_rejects_nonpositive_size(tmp_path):
    with pytest.raises(ValueError, match="symbol_chunk_size"):
        rr._run_batch_chunked(
            SimpleNamespace(list_symbols_with_bars=lambda s, e: ["A.SZ"]),
            _spec(),
            _request(tmp_path, "x", symbol_chunk_size=0),
            None,
        )
