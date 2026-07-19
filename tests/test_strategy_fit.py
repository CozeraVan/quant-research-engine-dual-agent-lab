"""Tests for analysis.strategy_fit (M10.1).

Covers exact statistics (binomial, hypergeometric, BH-FDR), the significance
framework (tiers, magnitude gate, free riders, meta-test), enrichment,
batch-level orchestration, outputs, and manifest audit parity.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from quant_research_engine.analysis.strategy_fit import (
    FitConfig,
    StrategyBatchData,
    analyze_batch,
    analyze_strategy,
    benjamini_hochberg,
    binomial_pvalue_ge,
    hypergeom_pvalue_ge,
    load_batch,
    write_fit_outputs,
)
from quant_research_engine.portfolio.report_manifest import ReportManifest


# ---------------------------------------------------------------------------
# exact statistics
# ---------------------------------------------------------------------------


def test_binomial_exact_known_values():
    assert binomial_pvalue_ge(3, 4) == pytest.approx(0.3125)          # (4+1)/16
    assert binomial_pvalue_ge(4, 5) == pytest.approx(0.1875)          # (5+1)/32
    assert binomial_pvalue_ge(5, 5) == pytest.approx(1 / 32)          # 1/32
    assert binomial_pvalue_ge(9, 10) == pytest.approx(11 / 1024)      # (10+1)/1024
    assert binomial_pvalue_ge(0, 10) == 1.0
    assert binomial_pvalue_ge(11, 10) == 0.0
    assert binomial_pvalue_ge(3, 0) == 1.0


def test_binomial_large_n_no_overflow():
    p = binomial_pvalue_ge(160, 250)
    assert 0.0 < p < 0.01  # 64% win rate over 250 trades is highly significant


def test_hypergeom_exact_known_value():
    # N=100, K=20, n=10, k=5: compute expected via direct formula
    from math import comb
    expected = sum(comb(20, i) * comb(80, 10 - i) for i in range(5, 11)) / comb(100, 10)
    assert hypergeom_pvalue_ge(100, 20, 10, 5) == pytest.approx(expected, rel=1e-9)
    assert hypergeom_pvalue_ge(100, 20, 10, 25) == 0.0
    assert hypergeom_pvalue_ge(100, 20, 0, 0) == 1.0


def test_benjamini_hochberg_values():
    assert benjamini_hochberg([0.01, 0.02, 0.03]) == pytest.approx([0.03, 0.03, 0.03])
    assert benjamini_hochberg([0.001, 0.5, 0.9]) == pytest.approx([0.003, 0.75, 0.9])
    assert benjamini_hochberg([]) == []


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _summary_row(symbol, trades, win_rate, total_return, buy_hold, excess):
    return {
        "symbol": symbol,
        "initial_cash": 1_000_000.0,
        "final_equity": 1_000_000.0 * (1 + total_return),
        "total_return": total_return,
        "trade_count": trades,
        "win_rate": win_rate,
        "total_cost": 100.0,
        "buy_hold_return": buy_hold,
        "excess_return_vs_buy_hold": excess,
        "order_count": trades * 2,
        "failed_order_count": 0,
    }


def _metadata(symbols, board_map=None):
    rows = []
    for s in symbols:
        rows.append(
            {
                "ts_code": s,
                "board": (board_map or {}).get(s, "main_board"),
                "industry_group": "tech" if s.endswith(".SZ") else "finance",
                "market_cap_bucket": "small" if s.endswith(".SZ") else "large",
                "liquidity_bucket": "high",
            }
        )
    return pd.DataFrame(rows)


def _strong_strategy_frame():
    """Strategy with a genuinely significant stock pool."""
    rows = []
    # 10 strong winners: 18/20 wins → binomial p ≈ 0.0002 (99.9% tier), excess > 0
    for i in range(10):
        rows.append(_summary_row(f"00000{i}.SZ", 20, 0.9, 0.30, 0.10, 0.20))
    # 30 random-ish symbols: 10/20 wins → p ≈ 0.59 (not significant)
    for i in range(30):
        rows.append(_summary_row(f"6000{i:02d}.SH", 20, 0.5, 0.01, 0.0, 0.01))
    # 5 free riders: profitable, excess <= 0
    for i in range(5):
        rows.append(_summary_row(f"3000{i:02d}.SZ", 20, 0.8, 0.25, 0.30, -0.05))
    # 5 below min_trades
    for i in range(5):
        rows.append(_summary_row(f"6880{i:02d}.SH", 2, 1.0, 0.50, 0.0, 0.50))
    return pd.DataFrame(rows)


def _noedge_strategy_frame():
    """No-edge strategy: 50% win rate everywhere, tiny positive excess."""
    return pd.DataFrame(
        [_summary_row(f"0000{i:02d}.SZ", 20, 0.5 + (i % 3) * 0.02, 0.01, 0.0, 0.005) for i in range(45)]
    )


# ---------------------------------------------------------------------------
# analyze_strategy
# ---------------------------------------------------------------------------


def test_analyze_strategy_significance_tiers_and_gates():
    frame = _strong_strategy_frame()
    symbols = frame["symbol"].tolist()
    metadata = _metadata(symbols)
    data = StrategyBatchData("test_strong", "test", frame)
    result = analyze_strategy(data, metadata, FitConfig(pool_tier=0.01, min_trades=5))

    summary = result.summary_row
    # eligible: 10 strong + 30 random = 40 (free riders excluded by gate
    # but they pass min_trades; free-riders counted separately)
    assert summary["eligible_symbols"] == 45
    assert summary["free_rider_count"] == 5
    # strong 10 at 99% (p≈0.006 ≤ 0.01); random 30 at 0.5 win rate → none
    assert summary["n_99"] == 10
    assert summary["pool_size"] == 10
    assert summary["pool_mean_excess"] == pytest.approx(0.20)
    # meta test: 10 significant at alpha 0.01 with expectation 0.45 → meta tier 99.9
    assert summary["meta_tier"] == "99.9"
    # stocks file contains only significant + gate-passing rows
    assert len(result.stock_rows) == 10
    assert all(r["in_pool"] for r in result.stock_rows)
    assert all(r["excess_return_vs_buy_hold"] > 0 for r in result.stock_rows)


def test_analyze_strategy_noedge_is_not_significant():
    frame = _noedge_strategy_frame()
    metadata = _metadata(frame["symbol"].tolist())
    data = StrategyBatchData("test_noedge", "test", frame)
    result = analyze_strategy(data, metadata, FitConfig(pool_tier=0.01, min_trades=5))

    summary = result.summary_row
    assert summary["eligible_symbols"] == 45
    # ~0-2 lucky symbols at 99%; meta tier must be empty (false positives ≈ expectation)
    assert summary["meta_tier"] == ""
    assert summary["pool_size"] <= 2


def test_analyze_strategy_unknown_metadata_bucket():
    frame = _strong_strategy_frame()
    # metadata covers only half the symbols
    metadata = _metadata(frame["symbol"].tolist()[:5])
    data = StrategyBatchData("test_partial_meta", "test", frame)
    result = analyze_strategy(data, metadata, FitConfig(pool_tier=0.01))
    boards = {r["board"] for r in result.stock_rows}
    assert "unknown" in boards


def test_enrichment_detects_concentration():
    # 8 winners all on chinext board vs 32 others on main_board
    rows = []
    for i in range(8):
        rows.append((_summary_row(f"3000{i:02d}.SZ", 20, 0.8, 0.30, 0.10, 0.20)))
    for i in range(32):
        rows.append((_summary_row(f"6000{i:02d}.SH", 20, 0.5, 0.01, 0.0, 0.01)))
    frame = pd.DataFrame(rows)
    metadata = _metadata(
        frame["symbol"].tolist(),
        board_map={s: "chinext" for s in frame["symbol"].tolist() if s.startswith("300")},
    )
    data = StrategyBatchData("test_enrich", "test", frame)
    result = analyze_strategy(data, metadata, FitConfig(pool_tier=0.01, min_class_size=5))

    board_rows = [r for r in result.class_rows if r["dimension"] == "board"]
    chinext = next(r for r in board_rows if r["class_value"] == "chinext")
    main = next(r for r in board_rows if r["class_value"] == "main_board")
    assert chinext["pool_count"] == 8
    assert chinext["p_value"] < main["p_value"]
    assert result.summary_row["best_dimension"] == "board"
    assert result.summary_row["best_class"] == "chinext"


# ---------------------------------------------------------------------------
# batch orchestration + outputs
# ---------------------------------------------------------------------------


def _make_batch_dir(tmp_path: Path) -> Path:
    batch = tmp_path / "batchTEST"
    strong = _strong_strategy_frame()
    noedge = _noedge_strategy_frame()
    results = []
    for sid, frame, category in (("strong_a", strong, "trend"), ("noedge_b", noedge, "mean_reversion")):
        out = batch / sid / "backtest"
        out.mkdir(parents=True)
        frame.to_csv(out / "summary.csv", index=False)
        results.append(
            {
                "strategy_id": sid,
                "category": category,
                "status": "ok",
                "output_dir": str(batch / sid),
            }
        )
    results.append({"strategy_id": "broken_c", "category": "breakout", "status": "error", "output_dir": str(batch / "broken_c")})
    (batch / "batch_summary.json").write_text(json.dumps({"results": results, "date_range": {"end": "2024-12-31"}}), encoding="utf-8")
    return batch


def test_load_batch_skips_error_and_missing(tmp_path):
    batch = _make_batch_dir(tmp_path)
    loaded, skipped = load_batch(batch)
    assert [d.strategy_id for d in loaded] == ["strong_a", "noedge_b"]
    assert skipped == [{"strategy_id": "broken_c", "category": "breakout", "reason": "status=error"}]


def test_analyze_batch_and_write_outputs(tmp_path):
    batch = _make_batch_dir(tmp_path)
    strong_frame = _strong_strategy_frame()
    metadata = _metadata(sorted(set(strong_frame["symbol"]) | set(_noedge_strategy_frame()["symbol"])))
    config = FitConfig(pool_tier=0.01, min_trades=5, min_class_size=5)
    summary_df, stocks_df, classes_df, skipped = analyze_batch(batch, metadata, config)

    assert set(summary_df["strategy_id"]) == {"strong_a", "noedge_b"}
    strong = summary_df.loc[summary_df["strategy_id"] == "strong_a"].iloc[0]
    assert strong["meta_tier"] == "99.9"
    noedge = summary_df.loc[summary_df["strategy_id"] == "noedge_b"].iloc[0]
    assert noedge["meta_tier"] == ""
    # global BH assigned
    assert classes_df["q_value"].notna().all()
    assert (classes_df["q_value"] >= classes_df["p_value"] - 1e-12).all()

    out = tmp_path / "fit_out"
    paths = write_fit_outputs(out, summary_df, stocks_df, classes_df, skipped, batch_dir=batch, config=config, generated_at="2026-07-19T00:00:00+00:00")
    for path in paths.values():
        assert path.exists()

    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    assert manifest["kind"] == "strategy_fit_report_manifest"
    # ReportManifest accepts the kind and validates contents with zero issues
    rm = ReportManifest.from_path(paths["report_manifest"])
    issues = rm.validate_contents()
    assert issues == []

    report_text = paths["strategy_fit_report"].read_text(encoding="utf-8")
    assert "strong_a" in report_text
    assert "broken_c" in report_text  # skipped listed

    stocks_loaded = pd.read_csv(paths["strategy_fit_stocks"])
    assert {"total_return", "buy_hold_return", "excess_return_vs_buy_hold"} <= set(stocks_loaded.columns)


def test_meta_test_under_random_noise():
    # 200 symbols at exact 50% win rate: nothing can be significant
    rows = [_summary_row(f"s{i:03d}", 20, 0.5, 0.0, 0.0, 0.0) for i in range(200)]
    frame = pd.DataFrame(rows)
    metadata = _metadata(frame["symbol"].tolist())
    data = StrategyBatchData("noise", "test", frame)
    result = analyze_strategy(data, metadata, FitConfig(pool_tier=0.01, min_trades=5, min_class_size=5))
    assert result.summary_row["meta_tier"] == ""
    assert result.summary_row["pool_size"] == 0
