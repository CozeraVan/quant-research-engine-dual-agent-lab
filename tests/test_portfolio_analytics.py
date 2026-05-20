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
    summarize_shared_orders_by,
    summarize_shared_trades_by,
    summarize_shared_failed_orders_by,
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


# --- shared-cash order group summaries ---


def test_summarize_shared_orders_by_computes_grouped_metrics():
    orders = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "600000.SH", "688001.SH"],
            "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"]),
            "side": ["buy", "buy", "sell", "sell"],
            "quantity": [100, 200, 50, 100],
            "price": [10.0, 20.0, 15.0, 30.0],
            "notional": [1000.0, 4000.0, 750.0, 3000.0],
            "cost": [5.0, 20.0, 3.75, 15.0],
            "reason": ["entry"] * 4,
            "board": ["main_board", "main_board", "star_market", "star_market"],
        }
    )

    grouped = summarize_shared_orders_by(orders, "board")

    assert grouped["group_by"].tolist() == ["board", "board"]
    assert grouped["group_value"].tolist() == ["main_board", "star_market"]
    assert grouped["order_count"].tolist() == [2, 2]
    assert grouped["buy_order_count"].tolist() == [2, 0]
    assert grouped["sell_order_count"].tolist() == [0, 2]
    assert grouped["total_notional"].tolist() == pytest.approx([5000.0, 3750.0])
    assert grouped["buy_notional"].tolist() == pytest.approx([5000.0, 0.0])
    assert grouped["sell_notional"].tolist() == pytest.approx([0.0, 3750.0])
    assert grouped["total_cost"].tolist() == pytest.approx([25.0, 18.75])


def test_summarize_shared_orders_by_raises_on_missing_column():
    orders = pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]})
    with pytest.raises(ValueError, match="shared-cash orders must include board"):
        summarize_shared_orders_by(orders, "board")


def test_summarize_shared_orders_by_returns_empty_frame_when_input_empty():
    orders = pd.DataFrame(columns=["symbol", "side", "board"])
    grouped = summarize_shared_orders_by(orders, "board")
    assert len(grouped) == 0
    assert "group_by" in grouped.columns
    assert "group_value" in grouped.columns
    assert "order_count" in grouped.columns


def test_summarize_shared_orders_by_handles_no_column_empty_frame():
    grouped = summarize_shared_orders_by(pd.DataFrame(), "board")
    assert len(grouped) == 0
    assert "group_by" in grouped.columns
    assert "group_value" in grouped.columns
    assert "order_count" in grouped.columns
    assert "buy_order_count" in grouped.columns
    assert "sell_order_count" in grouped.columns
    assert "total_notional" in grouped.columns


def test_summarize_shared_orders_by_skips_nan_group_values():
    orders = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "side": ["buy", "sell"],
            "quantity": [100, 50],
            "price": [10.0, 15.0],
            "notional": [1000.0, 750.0],
            "cost": [5.0, 3.75],
            "board": ["main_board", None],
        }
    )

    grouped = summarize_shared_orders_by(orders, "board")

    assert len(grouped) == 1
    assert grouped["group_value"].tolist() == ["main_board"]
    assert grouped["order_count"].tolist() == [1]


# --- shared-cash trade group summaries ---


def test_summarize_shared_trades_by_computes_grouped_metrics():
    trades = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000001.SZ", "000002.SZ"],
            "entry_date": pd.to_datetime(["2026-01-06", "2026-01-08", "2026-01-07"]),
            "exit_date": pd.to_datetime(["2026-01-09", "2026-01-12", "2026-01-10"]),
            "quantity": [100, 100, 50],
            "entry_price": [10.0, 12.0, 20.0],
            "exit_price": [11.0, 10.0, 25.0],
            "gross_pnl": [100.0, -200.0, 250.0],
            "cost": [10.0, 10.0, 5.0],
            "net_pnl": [90.0, -210.0, 245.0],
            "exit_reason": ["holding_days"] * 3,
            "board": ["main_board", "main_board", "star_market"],
        }
    )

    grouped = summarize_shared_trades_by(trades, "board")

    assert grouped["group_by"].tolist() == ["board", "board"]
    assert grouped["group_value"].tolist() == ["main_board", "star_market"]
    assert grouped["trade_count"].tolist() == [2, 1]
    assert grouped["win_rate"].tolist() == pytest.approx([0.5, 1.0])
    assert grouped["gross_pnl"].tolist() == pytest.approx([-100.0, 250.0])
    assert grouped["net_pnl"].tolist() == pytest.approx([-120.0, 245.0])
    assert grouped["total_cost"].tolist() == pytest.approx([20.0, 5.0])


def test_summarize_shared_trades_by_raises_on_missing_column():
    trades = pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]})
    with pytest.raises(ValueError, match="shared-cash trades must include board"):
        summarize_shared_trades_by(trades, "board")


def test_summarize_shared_trades_by_returns_empty_frame_when_input_empty():
    trades = pd.DataFrame(columns=["symbol", "net_pnl", "board"])
    grouped = summarize_shared_trades_by(trades, "board")
    assert len(grouped) == 0
    assert "trade_count" in grouped.columns
    assert "win_rate" in grouped.columns
    assert "gross_pnl" in grouped.columns


def test_summarize_shared_trades_by_handles_no_column_empty_frame():
    grouped = summarize_shared_trades_by(pd.DataFrame(), "board")
    assert len(grouped) == 0
    assert "group_by" in grouped.columns
    assert "group_value" in grouped.columns
    assert "trade_count" in grouped.columns
    assert "win_rate" in grouped.columns
    assert "gross_pnl" in grouped.columns
    assert "net_pnl" in grouped.columns


def test_summarize_shared_trades_by_skips_nan_group_values():
    trades = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "entry_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
            "exit_date": pd.to_datetime(["2026-01-09", "2026-01-10"]),
            "quantity": [100, 50],
            "entry_price": [10.0, 20.0],
            "exit_price": [11.0, 25.0],
            "gross_pnl": [100.0, 250.0],
            "cost": [10.0, 5.0],
            "net_pnl": [90.0, 245.0],
            "exit_reason": ["holding_days"] * 2,
            "board": ["main_board", None],
        }
    )

    grouped = summarize_shared_trades_by(trades, "board")

    assert len(grouped) == 1
    assert grouped["group_value"].tolist() == ["main_board"]


# --- shared-cash failed-order group summaries ---


def test_summarize_shared_failed_orders_by_computes_grouped_metrics():
    failed_orders = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ", "600000.SH"],
            "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07", "2026-01-08"]),
            "side": ["buy", "buy", "sell"],
            "quantity": [100, 200, 50],
            "price": [10.0, 20.0, 15.0],
            "notional": [1000.0, 4000.0, 750.0],
            "reason": [None, "entry_exit", "rebalance"],
            "failure_reason": ["limit_up_buy_blocked", "limit_up_buy_blocked", "limit_down_sell_blocked"],
            "board": ["main_board", "main_board", "star_market"],
        }
    )

    grouped = summarize_shared_failed_orders_by(failed_orders, "board")

    assert grouped["group_by"].tolist() == ["board", "board"]
    assert grouped["group_value"].tolist() == ["main_board", "star_market"]
    assert grouped["failed_order_count"].tolist() == [2, 1]
    assert grouped["failed_notional"].tolist() == pytest.approx([5000.0, 750.0])


def test_summarize_shared_failed_orders_by_raises_on_missing_column():
    failed_orders = pd.DataFrame({"symbol": ["000001.SZ"], "failure_reason": ["blocked"]})
    with pytest.raises(ValueError, match="shared-cash failed orders must include board"):
        summarize_shared_failed_orders_by(failed_orders, "board")


def test_summarize_shared_failed_orders_by_returns_empty_frame_when_input_empty():
    failed_orders = pd.DataFrame(columns=["symbol", "failure_reason", "board"])
    grouped = summarize_shared_failed_orders_by(failed_orders, "board")
    assert len(grouped) == 0
    assert "failed_order_count" in grouped.columns
    assert "failed_notional" in grouped.columns


def test_summarize_shared_failed_orders_by_handles_no_column_empty_frame():
    grouped = summarize_shared_failed_orders_by(pd.DataFrame(), "board")
    assert len(grouped) == 0
    assert "group_by" in grouped.columns
    assert "group_value" in grouped.columns
    assert "failed_order_count" in grouped.columns
    assert "failed_notional" in grouped.columns


def test_summarize_shared_failed_orders_by_skips_nan_group_values():
    failed_orders = pd.DataFrame(
        {
            "symbol": ["000001.SZ", "000002.SZ"],
            "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
            "side": ["buy", "sell"],
            "quantity": [100, 50],
            "price": [10.0, 15.0],
            "notional": [1000.0, 750.0],
            "reason": [None, "rebalance"],
            "failure_reason": ["blocked", "blocked"],
            "board": ["main_board", None],
        }
    )

    grouped = summarize_shared_failed_orders_by(failed_orders, "board")

    assert len(grouped) == 1
    assert grouped["group_value"].tolist() == ["main_board"]
