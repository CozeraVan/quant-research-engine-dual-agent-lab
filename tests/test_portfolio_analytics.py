import pandas as pd
import pytest

from quant_research_engine.portfolio.analytics import (
    summarize_batch_by,
    summarize_batch_ranked_rolling_symbols_by,
    summarize_batch_ranked_window_symbols_by,
    summarize_batch_summary,
    summarize_batch_rolling_summary_by,
    summarize_batch_rolling_summary,
    summarize_batch_window_summary_by,
    summarize_batch_window_summary,
)


def test_summarize_batch_summary_computes_cross_sectional_metrics():
    summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "600000.SH"],
            "total_return": [0.10, -0.05, 0.02],
            "trade_count": [2, 0, 1],
            "total_cost": [100.0, 0.0, 80.0],
            "failed_order_count": [0, 1, 0],
        }
    )

    metrics = summarize_batch_summary(summary)

    assert metrics["symbol_count"] == 3
    assert metrics["traded_symbol_count"] == 2
    assert metrics["positive_return_symbol_rate"] == pytest.approx(2 / 3)
    assert metrics["mean_total_return"] == pytest.approx((0.10 - 0.05 + 0.02) / 3)
    assert metrics["median_total_return"] == pytest.approx(0.02)
    assert metrics["best_symbol"] == "000001.SZ"
    assert metrics["worst_symbol"] == "000002.SZ"
    assert metrics["total_trades"] == 3
    assert metrics["total_failed_orders"] == 1


def test_summarize_batch_summary_handles_empty_summary():
    metrics = summarize_batch_summary(pd.DataFrame())

    assert metrics["symbol_count"] == 0
    assert metrics["traded_symbol_count"] == 0
    assert metrics["positive_return_symbol_rate"] is None


def test_summarize_batch_by_computes_metrics_per_group():
    summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "688001.SH"],
            "board": ["main_board", "main_board", "star_market"],
            "total_return": [0.10, -0.05, 0.02],
            "trade_count": [2, 0, 1],
            "total_cost": [100.0, 0.0, 80.0],
            "failed_order_count": [0, 1, 0],
        }
    )

    grouped = summarize_batch_by(summary, "board")

    assert grouped["board"].tolist() == ["main_board", "star_market"]
    assert grouped["symbol_count"].tolist() == [2, 1]
    assert grouped["mean_total_return"].tolist() == pytest.approx([0.025, 0.02])
    assert grouped["total_failed_orders"].tolist() == [1, 0]


def test_summarize_batch_window_summary_computes_cross_sectional_months():
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 90.0, 81.0],
            }
        ),
    }

    summary = summarize_batch_window_summary(equity_curves, window="M")

    assert summary["window"].tolist() == ["2026-01", "2026-02"]
    assert summary["symbol_count"].tolist() == [2, 2]
    assert summary["positive_return_symbol_rate"].tolist() == pytest.approx([0.0, 0.5])
    assert summary["mean_total_return"].tolist() == pytest.approx([0.0, 0.0])
    assert summary["best_symbol"].tolist() == ["000001.SZ", "000001.SZ"]
    assert summary["best_total_return"].tolist() == pytest.approx([0.0, 0.10])
    assert summary["worst_symbol"].tolist() == ["000001.SZ", "000002.SZ"]
    assert summary["worst_total_return"].tolist() == pytest.approx([0.0, -0.10])


def test_summarize_batch_rolling_summary_computes_cross_sectional_end_dates():
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 90.0, 81.0],
            }
        ),
    }

    summary = summarize_batch_rolling_summary(equity_curves, window_size=2)

    assert summary["window_size"].tolist() == [2, 2]
    assert summary["end_date"].dt.strftime("%Y-%m-%d").tolist() == ["2026-01-06", "2026-01-07"]
    assert summary["symbol_count"].tolist() == [2, 2]
    assert summary["positive_return_symbol_rate"].tolist() == pytest.approx([0.5, 0.5])
    assert summary["mean_total_return"].tolist() == pytest.approx([0.0, 0.0])
    assert summary["best_symbol"].tolist() == ["000001.SZ", "000001.SZ"]
    assert summary["best_total_return"].tolist() == pytest.approx([0.10, 0.10])
    assert summary["worst_symbol"].tolist() == ["000002.SZ", "000002.SZ"]
    assert summary["worst_total_return"].tolist() == pytest.approx([-0.10, -0.10])


def test_summarize_batch_rolling_summary_by_computes_grouped_end_dates():
    batch_summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "688001.SH"],
            "board": ["main_board", "main_board", "star_market"],
        }
    )
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 90.0, 81.0],
            }
        ),
        "688001.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 120.0, 132.0],
            }
        ),
    }

    grouped = summarize_batch_rolling_summary_by(batch_summary, equity_curves, "board", window_size=2)

    assert grouped["board"].tolist() == ["main_board", "main_board", "star_market", "star_market"]
    assert grouped["window_size"].tolist() == [2, 2, 2, 2]
    assert grouped["end_date"].dt.strftime("%Y-%m-%d").tolist() == [
        "2026-01-06",
        "2026-01-07",
        "2026-01-06",
        "2026-01-07",
    ]
    assert grouped["symbol_count"].tolist() == [2, 2, 1, 1]
    assert grouped["positive_return_symbol_rate"].tolist() == pytest.approx([0.5, 0.5, 1.0, 1.0])
    assert grouped["mean_total_return"].tolist() == pytest.approx([0.0, 0.0, 0.20, 0.10])
    assert grouped["best_symbol"].tolist() == ["000001.SZ", "000001.SZ", "688001.SH", "688001.SH"]
    assert grouped["worst_symbol"].tolist() == ["000002.SZ", "000002.SZ", "688001.SH", "688001.SH"]


def test_summarize_batch_ranked_rolling_symbols_by_lists_top_and_bottom_per_group_end_date():
    batch_summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "600000.SH", "688001.SH"],
            "board": ["main_board", "main_board", "main_board", "star_market"],
            "trade_count": [2, 4, 3, 1],
            "win_rate": [0.5, 0.25, 0.0, 1.0],
            "total_cost": [100.0, 90.0, 120.0, 80.0],
        }
    )
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 95.0, 90.25],
            }
        ),
        "600000.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 100.0, 100.0],
            }
        ),
        "688001.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07"]),
                "total_equity": [100.0, 120.0, 132.0],
            }
        ),
    }

    ranked = summarize_batch_ranked_rolling_symbols_by(
        batch_summary,
        equity_curves,
        "board",
        window_size=2,
        top_n=2,
    )

    main_second = ranked[
        (ranked["board"] == "main_board") & (ranked["end_date"] == pd.Timestamp("2026-01-07"))
    ]
    assert main_second["rank_type"].tolist() == ["top", "top", "bottom", "bottom"]
    assert main_second["rank"].tolist() == [1, 2, 1, 2]
    assert main_second["symbol"].tolist() == ["000001.SZ", "600000.SH", "000002.SZ", "600000.SH"]
    assert main_second["total_return"].tolist() == pytest.approx([0.10, 0.0, -0.05, 0.0])
    assert main_second["trade_count"].tolist() == [2, 3, 4, 3]
    star_second = ranked[
        (ranked["board"] == "star_market") & (ranked["end_date"] == pd.Timestamp("2026-01-07"))
    ]
    assert star_second["symbol"].tolist() == ["688001.SH", "688001.SH"]
    assert star_second["rank_type"].tolist() == ["top", "bottom"]


def test_summarize_batch_window_summary_by_computes_grouped_window_metrics():
    batch_summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "688001.SH"],
            "board": ["main_board", "main_board", "star_market"],
        }
    )
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 95.0, 90.25],
            }
        ),
        "688001.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 120.0, 132.0],
            }
        ),
    }

    grouped = summarize_batch_window_summary_by(batch_summary, equity_curves, "board", window="M")

    assert grouped["board"].tolist() == ["main_board", "main_board", "star_market", "star_market"]
    assert grouped["window"].tolist() == ["2026-01", "2026-02", "2026-01", "2026-02"]
    assert grouped["symbol_count"].tolist() == [2, 2, 1, 1]
    assert grouped["positive_return_symbol_rate"].tolist() == pytest.approx([0.0, 0.5, 0.0, 1.0])
    assert grouped["mean_total_return"].tolist() == pytest.approx([0.0, 0.025, 0.0, 0.10])
    assert grouped["best_symbol"].tolist() == ["000001.SZ", "000001.SZ", "688001.SH", "688001.SH"]
    assert grouped["worst_symbol"].tolist() == ["000001.SZ", "000002.SZ", "688001.SH", "688001.SH"]


def test_summarize_batch_ranked_window_symbols_by_lists_top_and_bottom_per_group_window():
    batch_summary = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "600000.SH", "688001.SH"],
            "board": ["main_board", "main_board", "main_board", "star_market"],
            "trade_count": [2, 4, 3, 1],
            "win_rate": [0.5, 0.25, 0.0, 1.0],
            "total_cost": [100.0, 90.0, 120.0, 80.0],
        }
    )
    equity_curves = {
        "000001.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 110.0, 121.0],
            }
        ),
        "000002.SZ": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 95.0, 90.25],
            }
        ),
        "600000.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 100.0, 100.0],
            }
        ),
        "688001.SH": pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-30", "2026-02-02", "2026-02-03"]),
                "total_equity": [100.0, 120.0, 132.0],
            }
        ),
    }

    ranked = summarize_batch_ranked_window_symbols_by(batch_summary, equity_curves, "board", window="M", top_n=2)

    main_feb = ranked[(ranked["board"] == "main_board") & (ranked["window"] == "2026-02")]
    assert main_feb["rank_type"].tolist() == ["top", "top", "bottom", "bottom"]
    assert main_feb["rank"].tolist() == [1, 2, 1, 2]
    assert main_feb["symbol"].tolist() == ["000001.SZ", "600000.SH", "000002.SZ", "600000.SH"]
    assert main_feb["total_return"].tolist() == pytest.approx([0.10, 0.0, -0.05, 0.0])
    assert main_feb["trade_count"].tolist() == [2, 3, 4, 3]
    star_feb = ranked[(ranked["board"] == "star_market") & (ranked["window"] == "2026-02")]
    assert star_feb["symbol"].tolist() == ["688001.SH", "688001.SH"]
    assert star_feb["rank_type"].tolist() == ["top", "bottom"]
