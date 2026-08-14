"""Tests for evaluation.alpha191 (Alpha191 leaderboard) and scripts/eval_alpha191.py CLI."""

from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.evaluation.alpha191 import (
    ALL_ALPHA_FACTORS,
    AlphaEvalConfig,
    build_leaderboard,
    daily_rank_ic,
    evaluate_alpha_factors,
)

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT / "scripts" / "eval_alpha191.py"


def _load_script_module():
    spec = importlib.util.spec_from_file_location("eval_alpha191_script", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _synthetic_panel(n_days: int = 40, n_codes: int = 30) -> pd.DataFrame:
    """close 由因子驱动：factor 越大未来收益越高 → 正 rank IC。"""
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2026-01-01", periods=n_days)
    rows = []
    for i in range(n_codes):
        code = f"{i:06d}.SZ"
        factor = rng.normal(size=n_days)
        noise = rng.normal(scale=0.01, size=n_days)
        # 次日收益 ≈ 因子暴露 + 噪声，滚动构造价格
        rets = np.roll(factor, 1) * 0.01 + noise
        rets[0] = 0.0
        close = 10.0 * np.cumprod(1 + rets)
        for d, f, c in zip(dates, factor, close):
            rows.append({"ts_code": code, "trade_date": d, "close": c, "alpha001": f})
    return pd.DataFrame(rows)


class _FakeStore:
    """最小 store：按 FactorFieldRequest 从合成面板切列。"""

    def __init__(self, panel: pd.DataFrame):
        self.panel = panel

    def load_daily_bars(self, *, ts_codes, start, end, fields):
        return self.panel[["ts_code", "trade_date", *fields]].copy()

    def load_factor_history(self, *, ts_codes, field_requests, start, end):
        columns = ["ts_code", "trade_date", *[r.source_column for r in field_requests]]
        return self.panel[columns].copy()


def test_build_leaderboard_sorts_by_abs_ic_and_marks_star():
    rows = [
        {"factor": "alpha001", "mean_rank_ic": 0.06, "icir": 0.5, "ic_win_rate": 0.60,
         "top_minus_bottom": 0.01, "observation_dates": 100, "significant": "★"},
        {"factor": "alpha002", "mean_rank_ic": -0.08, "icir": -0.7, "ic_win_rate": 0.62,
         "top_minus_bottom": -0.02, "observation_dates": 100, "significant": "★"},
        {"factor": "alpha003", "mean_rank_ic": None, "icir": None, "ic_win_rate": None,
         "top_minus_bottom": None, "observation_dates": 0, "significant": ""},
    ]
    board = build_leaderboard(rows)
    assert list(board["factor"]) == ["alpha002", "alpha001", "alpha003"]
    assert list(board.columns) == [
        "factor", "mean_rank_ic", "icir", "ic_win_rate",
        "top_minus_bottom", "observation_dates", "significant",
    ]


def test_daily_rank_ic_positive_on_synthetic_panel():
    panel = _synthetic_panel()
    ic = daily_rank_ic(panel, "alpha001", horizon=1)
    assert len(ic) > 30
    assert ic.mean() > 0.3  # 构造上因子驱动次日收益


def test_evaluate_alpha_factors_end_to_end_synthetic():
    panel = _synthetic_panel()
    config = AlphaEvalConfig(start=date(2026, 1, 1), end=date(2026, 3, 1), batch_size=1)
    rows = evaluate_alpha_factors(_FakeStore(panel), ["alpha001"], config)
    assert len(rows) == 1
    row = rows[0]
    assert row["factor"] == "alpha001"
    assert row["mean_rank_ic"] is not None and row["mean_rank_ic"] > 0.2
    assert row["ic_win_rate"] is not None and row["ic_win_rate"] > 0.8
    assert row["icir"] is not None and row["icir"] > 0
    # 正 IC 因子：高分位组收益高于低分位组 → Q5-Q1 > 0
    assert row["top_minus_bottom"] is not None and row["top_minus_bottom"] > 0
    assert row["observation_dates"] > 30
    assert row["significant"] == "★"


def test_evaluate_alpha_factors_failure_row_does_not_abort():
    panel = _synthetic_panel()

    class _BrokenStore(_FakeStore):
        def load_factor_history(self, **kwargs):
            raise RuntimeError("column does not exist")

    config = AlphaEvalConfig(start=date(2026, 1, 1), end=date(2026, 3, 1))
    # 取数阶段即失败属于配置错误，应抛出
    with pytest.raises(RuntimeError):
        evaluate_alpha_factors(_BrokenStore(panel), ["alpha001"], config)


def test_cli_main_writes_sorted_csv(tmp_path, monkeypatch):
    module = _load_script_module()
    output = tmp_path / "leaderboard.csv"

    class _FakePG:
        def __init__(self, settings):
            pass

        def ping(self):
            return True

        def close(self):
            pass

    fake_rows = [
        {"factor": "alpha001", "mean_rank_ic": 0.03, "icir": 0.2, "ic_win_rate": 0.52,
         "top_minus_bottom": 0.005, "observation_dates": 200, "significant": ""},
        {"factor": "alpha006", "mean_rank_ic": -0.07, "icir": -0.9, "ic_win_rate": 0.58,
         "top_minus_bottom": -0.011, "observation_dates": 200, "significant": "★"},
        {"factor": "alpha012", "mean_rank_ic": 0.05, "icir": 0.4, "ic_win_rate": 0.51,
         "top_minus_bottom": 0.008, "observation_dates": 200, "significant": ""},
    ]

    monkeypatch.setattr(module, "PostgresDataStore", _FakePG)
    captured = {}

    def _fake_evaluate(store, factors, config):
        captured["factors"] = factors
        return [r for r in fake_rows if r["factor"] in factors]

    monkeypatch.setattr(module, "evaluate_alpha_factors", _fake_evaluate)
    rc = module.main([
        "--start", "2025-08-01", "--end", "2026-08-13",
        "--factors", "alpha001,alpha006,alpha012",
        "--db-url", "postgresql+psycopg:///fake",
        "--output", str(output),
    ])
    assert rc == 0
    assert captured["factors"] == ["alpha001", "alpha006", "alpha012"]

    board = pd.read_csv(output)
    assert list(board.columns) == [
        "factor", "mean_rank_ic", "icir", "ic_win_rate",
        "top_minus_bottom", "observation_dates", "significant",
    ]
    # 按 |mean_rank_ic| 降序
    assert list(board["factor"]) == ["alpha006", "alpha012", "alpha001"]
    assert board.loc[0, "significant"] == "★"


def test_cli_resolve_factors_validation():
    module = _load_script_module()
    assert module.resolve_factors("all") == ALL_ALPHA_FACTORS
    assert len(ALL_ALPHA_FACTORS) == 191
    assert module.resolve_factors("alpha001, alpha191") == ["alpha001", "alpha191"]
    with pytest.raises(ValueError, match="未知"):
        module.resolve_factors("alpha999")
