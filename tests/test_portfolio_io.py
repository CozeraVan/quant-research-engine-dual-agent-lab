import json

import pandas as pd
import pytest

from quant_research_engine.portfolio.batch import BatchBacktestResult
from quant_research_engine.portfolio.io import write_batch_result, write_shared_cash_result, write_single_symbol_result
from quant_research_engine.portfolio.shared import SharedCashBacktestResult
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult


def test_write_single_symbol_result_creates_standard_output_files(tmp_path):
    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "trade_date": pd.to_datetime(["2026-01-06"]),
                "side": ["buy"],
                "quantity": [100],
                "price": [10.0],
                "notional": [1000.0],
                "cost": [5.0],
            }
        ),
        trades=pd.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "entry_date": pd.to_datetime(["2026-01-06"]),
                "exit_date": pd.to_datetime(["2026-01-09"]),
                "quantity": [100],
                "entry_price": [10.0],
                "exit_price": [11.0],
                "gross_pnl": [100.0],
                "cost": [10.0],
                "net_pnl": [90.0],
            }
        ),
        equity_curve=pd.DataFrame(
            {
                "trade_date": pd.to_datetime(["2026-01-06"]),
                "cash": [9000.0],
                "position_quantity": [100],
                "market_value": [1000.0],
                "total_equity": [10000.0],
            }
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1, "max_drawdown": 0.0},
    )

    paths = write_single_symbol_result(result, tmp_path)

    assert paths["orders"].name == "orders.csv"
    assert paths["trades"].name == "trades.csv"
    assert paths["failed_orders"].name == "failed_orders.csv"
    assert paths["equity_curve"].name == "equity_curve.csv"
    assert paths["summary"].name == "summary.json"
    assert pd.read_csv(paths["orders"]).iloc[0]["symbol"] == "000001.SZ"
    assert json.loads(paths["summary"].read_text(encoding="utf-8"))["trade_count"] == 1


def test_write_batch_result_creates_summary_and_per_symbol_files(tmp_path):
    single_result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-01-30", periods=21, freq="B"),
                "total_equity": [
                    10000.0,
                    11000.0,
                    9900.0,
                    10100.0,
                    10200.0,
                    10300.0,
                    10400.0,
                    10500.0,
                    10600.0,
                    10700.0,
                    10800.0,
                    10900.0,
                    11000.0,
                    11100.0,
                    11200.0,
                    11300.0,
                    11400.0,
                    11500.0,
                    11600.0,
                    11700.0,
                    11800.0,
                ],
            }
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1, "max_drawdown": 0.0},
    )
    result = BatchBacktestResult(
        symbols=["000001.SZ"],
        results={"000001.SZ": single_result},
        summary=pd.DataFrame(
            {
                "symbol": ["000001.SZ"],
                "trade_count": [1],
                "win_rate": [1.0],
                "total_return": [0.05],
                "total_cost": [10.0],
            }
        ),
        summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
    )

    paths = write_batch_result(result, tmp_path)

    assert paths["summary"].name == "summary.csv"
    assert paths["summary_metrics"].name == "summary_metrics.json"
    assert paths["summary_markdown"].name == "summary.md"
    assert paths["report_manifest"].name == "report_manifest.json"
    assert paths["window_summary_M"].name == "window_summary_M.csv"
    assert paths["window_summary_Q"].name == "window_summary_Q.csv"
    assert paths["window_summary_Y"].name == "window_summary_Y.csv"
    assert paths["rolling_summary_20"].name == "rolling_summary_20.csv"
    assert paths["000001.SZ_orders"].name == "orders.csv"
    assert pd.read_csv(paths["summary"]).iloc[0]["symbol"] == "000001.SZ"
    window_summary = pd.read_csv(paths["window_summary_M"])
    assert window_summary["window"].tolist() == ["2026-01", "2026-02"]
    assert window_summary["symbol_count"].tolist() == [1, 1]
    quarterly = pd.read_csv(paths["window_summary_Q"])
    assert quarterly["window"].tolist() == ["2026Q1"]
    assert quarterly["symbol_count"].tolist() == [1]
    yearly = pd.read_csv(paths["window_summary_Y"])
    assert yearly["window"].astype(str).tolist() == ["2026"]
    assert yearly["symbol_count"].tolist() == [1]
    rolling_summary = pd.read_csv(paths["rolling_summary_20"])
    assert rolling_summary["window_size"].tolist() == [20, 20]
    assert rolling_summary["symbol_count"].tolist() == [1, 1]
    assert json.loads(paths["000001.SZ_summary"].read_text(encoding="utf-8"))["trade_count"] == 1
    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "batch_backtest_report_manifest"
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert manifest_by_key["summary"] == {
        "key": "summary",
        "path": "summary.csv",
        "filename": "summary.csv",
        "role": "summary",
    }
    assert manifest_by_key["window_summary_M"]["window"] == "M"
    assert manifest_by_key["rolling_summary_20"]["role"] == "rolling_summary"
    assert manifest_by_key["rolling_summary_20"]["window_size"] == 20
    assert manifest_by_key["000001.SZ_orders"]["symbol"] == "000001.SZ"
    assert manifest_by_key["000001.SZ_orders"]["role"] == "orders"
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "# Batch Backtest Summary" in markdown
    assert "## Aggregate Metrics" in markdown
    assert "| Symbol count | 1 |" in markdown
    assert "| Mean total return | 0.05 |" in markdown
    assert "## Top Symbols" in markdown
    assert "| 000001.SZ | 0.05 | 1 | 1.0 | 10.0 |" in markdown
    assert "## Bottom Symbols" in markdown
    assert "## Output Files" in markdown
    assert "| Report manifest | report_manifest.json |" in markdown
    assert "| Summary CSV | summary.csv |" in markdown
    assert "| Monthly window summary | window_summary_M.csv |" in markdown
    assert "| Quarterly window summary | window_summary_Q.csv |" in markdown
    assert "| Yearly window summary | window_summary_Y.csv |" in markdown
    assert "| Rolling summary 20 | rolling_summary_20.csv |" in markdown


def test_write_batch_result_can_write_grouped_metrics(tmp_path):
    single_results = {
        symbol: SingleSymbolBacktestResult(
            orders=pd.DataFrame({"symbol": [symbol], "side": ["buy"]}),
            trades=pd.DataFrame({"symbol": [symbol], "net_pnl": [0.0]}),
            equity_curve=pd.DataFrame(
                {
                    "trade_date": pd.date_range("2026-01-30", periods=21, freq="B"),
                    "total_equity": [
                        equity[0],
                        equity[1],
                        equity[2],
                        *([equity[2]] * 18),
                    ],
                }
            ),
            failed_orders=pd.DataFrame(),
            summary={"initial_cash": 100.0, "final_equity": equity[-1], "trade_count": 1},
        )
        for symbol, equity in {
            "000001.SZ": [100.0, 110.0, 121.0],
            "000002.SZ": [100.0, 95.0, 90.25],
            "600000.SH": [100.0, 100.0, 100.0],
            "688001.SH": [100.0, 120.0, 132.0],
        }.items()
    }
    result = BatchBacktestResult(
        symbols=["000001.SZ", "000002.SZ", "600000.SH", "688001.SH"],
        results=single_results,
        summary=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ", "600000.SH", "688001.SH"],
                "board": ["main_board", "main_board", "main_board", "star_market"],
                "total_return": [0.10, 0.04, -0.03, -0.02],
                "trade_count": [2, 4, 3, 1],
                "win_rate": [0.5, 0.25, 0.0, 1.0],
                "total_cost": [100.0, 90.0, 120.0, 80.0],
                "failed_order_count": [0, 0, 0, 0],
            }
        ),
    )

    paths = write_batch_result(result, tmp_path, group_by=["board"], group_rank_top_n=2)

    assert paths["group_by_board"].name == "group_by_board.csv"
    assert paths["group_by_board_ranked_symbols"].name == "group_by_board_ranked_symbols.csv"
    assert paths["window_summary_M_by_board"].name == "window_summary_M_by_board.csv"
    assert paths["window_summary_Q_by_board"].name == "window_summary_Q_by_board.csv"
    assert paths["window_summary_Y_by_board"].name == "window_summary_Y_by_board.csv"
    assert paths["window_summary_M_by_board_ranked_symbols"].name == "window_summary_M_by_board_ranked_symbols.csv"
    assert paths["window_summary_Q_by_board_ranked_symbols"].name == "window_summary_Q_by_board_ranked_symbols.csv"
    assert paths["window_summary_Y_by_board_ranked_symbols"].name == "window_summary_Y_by_board_ranked_symbols.csv"
    assert paths["rolling_summary_20_by_board"].name == "rolling_summary_20_by_board.csv"
    assert paths["rolling_summary_20_by_board_ranked_symbols"].name == "rolling_summary_20_by_board_ranked_symbols.csv"
    grouped = pd.read_csv(paths["group_by_board"])
    assert grouped["board"].tolist() == ["main_board", "star_market"]
    monthly_grouped = pd.read_csv(paths["window_summary_M_by_board"])
    assert monthly_grouped["board"].tolist() == ["main_board", "main_board", "star_market", "star_market"]
    assert monthly_grouped["window"].tolist() == ["2026-01", "2026-02", "2026-01", "2026-02"]
    assert monthly_grouped["symbol_count"].tolist() == [3, 3, 1, 1]
    quarterly_grouped = pd.read_csv(paths["window_summary_Q_by_board"])
    assert quarterly_grouped["window"].tolist() == ["2026Q1", "2026Q1"]
    yearly_grouped = pd.read_csv(paths["window_summary_Y_by_board"])
    assert yearly_grouped["window"].astype(str).tolist() == ["2026", "2026"]
    rolling_grouped = pd.read_csv(paths["rolling_summary_20_by_board"])
    assert rolling_grouped["board"].tolist() == ["main_board", "main_board", "star_market", "star_market"]
    assert rolling_grouped["window_size"].tolist() == [20, 20, 20, 20]
    rolling_ranked = pd.read_csv(paths["rolling_summary_20_by_board_ranked_symbols"])
    main_latest = rolling_ranked[
        (rolling_ranked["board"] == "main_board") & (rolling_ranked["end_date"] == "2026-02-27")
    ]
    assert main_latest["rank_type"].tolist() == ["top", "top", "bottom", "bottom"]
    monthly_window_ranked = pd.read_csv(paths["window_summary_M_by_board_ranked_symbols"])
    main_feb = monthly_window_ranked[
        (monthly_window_ranked["board"] == "main_board") & (monthly_window_ranked["window"] == "2026-02")
    ]
    assert main_feb["rank_type"].tolist() == ["top", "top", "bottom", "bottom"]
    assert main_feb["symbol"].tolist() == ["000001.SZ", "600000.SH", "000002.SZ", "600000.SH"]
    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert manifest_by_key["window_summary_M_by_board"] == {
        "key": "window_summary_M_by_board",
        "path": "window_summary_M_by_board.csv",
        "filename": "window_summary_M_by_board.csv",
        "role": "window_summary",
        "window": "M",
        "group_by": "board",
    }
    assert manifest_by_key["window_summary_M_by_board_ranked_symbols"]["role"] == "window_ranked_symbols"
    assert manifest_by_key["window_summary_M_by_board_ranked_symbols"]["window"] == "M"
    assert manifest_by_key["window_summary_M_by_board_ranked_symbols"]["group_by"] == "board"
    assert manifest_by_key["rolling_summary_20_by_board"]["role"] == "rolling_summary"
    assert manifest_by_key["rolling_summary_20_by_board"]["window_size"] == 20
    assert manifest_by_key["rolling_summary_20_by_board"]["group_by"] == "board"
    assert manifest_by_key["rolling_summary_20_by_board_ranked_symbols"]["role"] == "rolling_ranked_symbols"
    assert manifest_by_key["rolling_summary_20_by_board_ranked_symbols"]["window_size"] == 20
    assert manifest_by_key["rolling_summary_20_by_board_ranked_symbols"]["group_by"] == "board"
    ranked = pd.read_csv(paths["group_by_board_ranked_symbols"])
    assert ranked["rank_type"].tolist() == ["top", "top", "bottom", "bottom", "top", "bottom"]
    assert ranked["board"].tolist() == [
        "main_board",
        "main_board",
        "main_board",
        "main_board",
        "star_market",
        "star_market",
    ]
    assert ranked["symbol"].tolist() == [
        "000001.SZ",
        "000002.SZ",
        "600000.SH",
        "000002.SZ",
        "688001.SH",
        "688001.SH",
    ]
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "| Group by board | group_by_board.csv |" in markdown
    assert "| Group by board ranked symbols | group_by_board_ranked_symbols.csv |" in markdown
    assert "| Window summary M by board | window_summary_M_by_board.csv |" in markdown
    assert "| Window summary Q by board | window_summary_Q_by_board.csv |" in markdown
    assert "| Window summary Y by board | window_summary_Y_by_board.csv |" in markdown
    assert "| Window summary M by board ranked symbols | window_summary_M_by_board_ranked_symbols.csv |" in markdown
    assert "| Window summary Q by board ranked symbols | window_summary_Q_by_board_ranked_symbols.csv |" in markdown
    assert "| Window summary Y by board ranked symbols | window_summary_Y_by_board_ranked_symbols.csv |" in markdown
    assert "| Rolling summary 20 by board | rolling_summary_20_by_board.csv |" in markdown
    assert "| Rolling summary 20 by board ranked symbols | rolling_summary_20_by_board_ranked_symbols.csv |" in markdown
    assert "## Top Symbols" in markdown
    assert "| 000001.SZ | 0.1 | 2 |" in markdown
    assert "## Bottom Symbols" in markdown
    assert "| 600000.SH | -0.03 | 3 |" in markdown


def test_write_shared_cash_result_creates_standard_output_files(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {
                "trade_date": pd.date_range("2026-01-30", periods=21, freq="B"),
                "total_equity": [
                    10000.0,
                    11000.0,
                    9900.0,
                    10100.0,
                    10200.0,
                    10300.0,
                    10400.0,
                    10500.0,
                    10600.0,
                    10700.0,
                    10800.0,
                    10900.0,
                    11000.0,
                    11100.0,
                    11200.0,
                    11300.0,
                    11400.0,
                    11500.0,
                    11600.0,
                    11700.0,
                    11800.0,
                ],
            }
        ),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": 10000.0,
            "final_equity": 10000.0,
            "trade_count": 1,
            "max_drawdown": 0.0,
            "rebalance_order_count": 2,
            "rebalance_turnover": 0.3,
            "benchmark_code": "000002.SZ",
            "benchmark_benchmark_total_return": -0.10,
            "benchmark_excess_total_return": 0.05,
            "benchmark_information_ratio": 1.2,
        },
    )

    paths = write_shared_cash_result(result, tmp_path)

    assert paths["orders"].name == "orders.csv"
    assert paths["trades"].name == "trades.csv"
    assert paths["failed_orders"].name == "failed_orders.csv"
    assert paths["equity_curve"].name == "equity_curve.csv"
    assert paths["summary"].name == "summary.json"
    assert paths["summary_markdown"].name == "summary.md"
    assert paths["report_manifest"].name == "report_manifest.json"
    assert paths["window_metrics_M"].name == "window_metrics_M.csv"
    assert paths["window_metrics_Q"].name == "window_metrics_Q.csv"
    assert paths["window_metrics_Y"].name == "window_metrics_Y.csv"
    assert paths["rolling_metrics_20"].name == "rolling_metrics_20.csv"
    summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert summary["trade_count"] == 1
    assert summary["max_drawdown"] == 0.0
    monthly = pd.read_csv(paths["window_metrics_M"])
    assert monthly["window"].tolist() == ["2026-01", "2026-02"]
    assert monthly["total_return"].tolist() == pytest.approx([0.0, 11800.0 / 11000.0 - 1])
    quarterly = pd.read_csv(paths["window_metrics_Q"])
    assert quarterly["window"].tolist() == ["2026Q1"]
    assert quarterly["total_return"].tolist() == pytest.approx([0.18])
    yearly = pd.read_csv(paths["window_metrics_Y"])
    assert yearly["window"].astype(str).tolist() == ["2026"]
    assert yearly["total_return"].tolist() == pytest.approx([0.18])
    rolling = pd.read_csv(paths["rolling_metrics_20"])
    assert rolling["window_size"].tolist() == [20, 20]
    assert rolling["start_date"].tolist() == ["2026-01-30", "2026-02-02"]
    assert rolling["end_date"].tolist() == ["2026-02-26", "2026-02-27"]
    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "shared_cash_backtest_report_manifest"
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert manifest_by_key["orders"]["role"] == "orders"
    assert manifest_by_key["window_metrics_M"]["role"] == "window_metrics"
    assert manifest_by_key["window_metrics_M"]["window"] == "M"
    assert manifest_by_key["rolling_metrics_20"]["role"] == "rolling_metrics"
    assert manifest_by_key["rolling_metrics_20"]["window_size"] == 20
    assert manifest_by_key["summary_markdown"]["path"] == "summary.md"
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "## Portfolio" in markdown
    assert "## Rebalance" in markdown
    assert "## Benchmark" in markdown
    assert "| Benchmark code | 000002.SZ |" in markdown
    assert "| Benchmark total return | -0.1 |" in markdown
    assert "## Output Files" in markdown
    assert "| Equity curve | equity_curve.csv |" in markdown
    assert "| Monthly window metrics | window_metrics_M.csv |" in markdown
    assert "| Quarterly window metrics | window_metrics_Q.csv |" in markdown
    assert "| Yearly window metrics | window_metrics_Y.csv |" in markdown
    assert "| Rolling metrics 20 | rolling_metrics_20.csv |" in markdown
    assert "| Report manifest | report_manifest.json |" in markdown
    assert "benchmark_benchmark_total_return" not in markdown


def test_shared_cash_summary_markdown_includes_failed_orders_section(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(),
        trades=pd.DataFrame(),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-06", "2026-01-06"]),
                "side": ["buy", "buy"],
                "quantity": [100, 100],
                "price": [10.0, 20.0],
                "notional": [1000.0, 2000.0],
                "reason": [None, "rebalance"],
                "failure_reason": ["limit_up_buy_blocked", "limit_down_sell_blocked"],
            }
        ),
        summary={
            "initial_cash": 10000.0,
            "final_equity": 10000.0,
            "trade_count": 0,
            "max_drawdown": 0.0,
            "failed_order_count": 2,
            "failed_order_count_by_reason": {"entry_exit": 1, "rebalance": 1},
            "failed_order_count_by_failure_reason": {"limit_up_buy_blocked": 1, "limit_down_sell_blocked": 1},
            "failed_order_notional_by_reason": {"entry_exit": 1000.0, "rebalance": 2000.0},
            "failed_order_notional_by_failure_reason": {"limit_up_buy_blocked": 1000.0, "limit_down_sell_blocked": 2000.0},
            "failed_order_count_by_side": {"buy": 2},
            "failed_order_notional_by_side": {"buy": 3000.0},
        },
    )

    paths = write_shared_cash_result(result, tmp_path)
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "## Failed Orders" in markdown
    assert "| Failed order count | 2 |" in markdown
    assert "Failed: limit up buy blocked" in markdown
    assert "Failed: limit down sell blocked" in markdown
    assert "| Failed by entry/exit count | 1 |" in markdown
    assert "| Failed by rebalance count | 1 |" in markdown
    assert "| Failed buy | 2 orders, ¥3,000.00 notional |" in markdown
    assert "{'entry_exit'" not in markdown
    assert "failed_order_count_by_reason" not in markdown


def test_shared_cash_summary_markdown_no_failed_orders_when_zero(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(),
        trades=pd.DataFrame(),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": 10000.0,
            "final_equity": 10000.0,
            "trade_count": 0,
            "max_drawdown": 0.0,
            "failed_order_count": 0,
            "failed_order_count_by_reason": {},
            "failed_order_count_by_failure_reason": {},
            "failed_order_notional_by_reason": {},
            "failed_order_notional_by_failure_reason": {},
            "failed_order_count_by_side": {},
            "failed_order_notional_by_side": {},
        },
    )

    paths = write_shared_cash_result(result, tmp_path)
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "## Failed Orders" not in markdown
    assert "failed_order_" not in markdown


def test_single_symbol_empty_failed_orders_writes_stable_headers(tmp_path):
    from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult

    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame(),
        trades=pd.DataFrame(),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 0},
    )

    paths = write_single_symbol_result(result, tmp_path)
    path = paths["failed_orders"]
    content = path.read_text(encoding="utf-8")
    header = content.strip().split("\n")[0] if content.strip() else ""

    assert "symbol" in header
    assert "trade_date" in header
    assert "side" in header
    assert "quantity" in header
    assert "price" in header
    assert "notional" in header
    assert "reason" in header


def test_shared_cash_empty_failed_orders_writes_stable_headers(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(),
        trades=pd.DataFrame(),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": 10000.0,
            "final_equity": 10000.0,
            "trade_count": 0,
            "max_drawdown": 0.0,
            "failed_order_count": 0,
            "failed_order_count_by_reason": {},
            "failed_order_count_by_failure_reason": {},
            "failed_order_notional_by_reason": {},
            "failed_order_notional_by_failure_reason": {},
        },
    )

    paths = write_shared_cash_result(result, tmp_path)
    path = paths["failed_orders"]
    content = path.read_text(encoding="utf-8")
    header = content.strip().split("\n")[0] if content.strip() else ""

    assert "symbol" in header
    assert "trade_date" in header
    assert "side" in header
    assert "quantity" in header
    assert "price" in header
    assert "notional" in header
    assert "reason" in header


def test_write_single_symbol_result_writes_run_manifest(tmp_path):
    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1},
    )
    run_request = {
        "command": "backtest-single",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {
            "symbol": "000001.SZ",
            "initial_cash": 10000.0,
            "holding_days": 2,
            "market_profile": "/tmp/market_profile.yaml",
        },
    }
    paths = write_single_symbol_result(result, tmp_path, run_request=run_request)

    assert "run_manifest" in paths
    assert paths["run_manifest"].name == "run_manifest.json"
    manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["kind"] == "portfolio_backtest_run_manifest"
    assert manifest["command"] == "backtest-single"
    assert manifest["strategy_path"] == "/tmp/strategy.yaml"
    assert manifest["request"]["symbol"] == "000001.SZ"
    assert manifest["request"]["market_profile"] == "/tmp/market_profile.yaml"
    assert "equity_curve" in manifest["artifacts"]
    assert "orders" in manifest["artifacts"]
    assert "summary" in manifest["artifacts"]


def test_write_single_symbol_result_no_run_manifest_when_not_requested(tmp_path):
    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1},
    )
    paths = write_single_symbol_result(result, tmp_path)
    assert "run_manifest" not in paths


def test_write_shared_cash_result_writes_run_manifest(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 0, "max_drawdown": 0.0},
    )
    run_request = {
        "command": "backtest-shared",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {
            "symbols": ["000001.SZ"],
            "max_positions": 5,
            "holding_days": 2,
            "market_profile": "/tmp/market_profile.yaml",
            "benchmark_table": "public.index_daily",
            "benchmark_code": "000300.SH",
            "benchmark_value_column": "close",
        },
    }
    paths = write_shared_cash_result(result, tmp_path, run_request=run_request)

    assert "run_manifest" in paths
    run_manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    assert run_manifest["kind"] == "portfolio_backtest_run_manifest"
    assert run_manifest["command"] == "backtest-shared"
    assert run_manifest["request"]["max_positions"] == 5
    assert run_manifest["request"]["market_profile"] == "/tmp/market_profile.yaml"
    assert run_manifest["request"]["benchmark_table"] == "public.index_daily"
    assert run_manifest["request"]["benchmark_code"] == "000300.SH"
    assert run_manifest["request"]["benchmark_value_column"] == "close"
    report_manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    manifest_keys = {item["key"] for item in report_manifest["files"]}
    assert "run_manifest" in manifest_keys
    run_manifest_entry = next(item for item in report_manifest["files"] if item["key"] == "run_manifest")
    assert run_manifest_entry["role"] == "run_manifest"
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "| Run manifest | run_manifest.json |" in markdown


def test_write_batch_result_writes_run_manifest(tmp_path):
    single_result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1, "max_drawdown": 0.0},
    )
    result = BatchBacktestResult(
        symbols=["000001.SZ"],
        results={"000001.SZ": single_result},
        summary=pd.DataFrame({"symbol": ["000001.SZ"], "trade_count": [1], "win_rate": [1.0], "total_return": [0.05], "total_cost": [10.0]}),
        summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
    )
    run_request = {
        "command": "backtest-batch",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {
            "symbols": ["000001.SZ"],
            "initial_cash_per_symbol": 50000.0,
            "holding_days": 2,
            "market_profile": "/tmp/market_profile.yaml",
            "group_by": ["board"],
            "group_rank_top_n": 3,
        },
    }
    paths = write_batch_result(result, tmp_path, run_request=run_request)

    assert "run_manifest" in paths
    run_manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    assert run_manifest["kind"] == "portfolio_backtest_run_manifest"
    assert run_manifest["command"] == "backtest-batch"
    assert run_manifest["request"]["initial_cash_per_symbol"] == 50000.0
    assert run_manifest["request"]["market_profile"] == "/tmp/market_profile.yaml"
    assert run_manifest["request"]["group_by"] == ["board"]
    assert run_manifest["request"]["group_rank_top_n"] == 3
    report_manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    manifest_keys = {item["key"] for item in report_manifest["files"]}
    assert "run_manifest" in manifest_keys
    run_manifest_entry = next(item for item in report_manifest["files"] if item["key"] == "run_manifest")
    assert run_manifest_entry["role"] == "run_manifest"
    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "| Run manifest | run_manifest.json |" in markdown


def test_batch_emitted_report_manifest_validates_run_manifest(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    single_result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1, "max_drawdown": 0.0},
    )
    result = BatchBacktestResult(
        symbols=["000001.SZ"],
        results={"000001.SZ": single_result},
        summary=pd.DataFrame({"symbol": ["000001.SZ"], "trade_count": [1], "win_rate": [1.0], "total_return": [0.05], "total_cost": [10.0]}),
        summary_metrics={"symbol_count": 1, "mean_total_return": 0.05, "total_trades": 1},
    )
    run_request = {
        "command": "backtest-batch",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {"symbols": ["000001.SZ"], "holding_days": 2},
    }
    paths = write_batch_result(result, tmp_path, run_request=run_request)
    manifest = ReportManifest.from_path(paths["report_manifest"])
    assert manifest.validate_contents(role="run_manifest") == []


def test_shared_emitted_report_manifest_validates_run_manifest(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    result = SharedCashBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 0, "max_drawdown": 0.0},
    )
    run_request = {
        "command": "backtest-shared",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {"symbols": ["000001.SZ"], "max_positions": 5, "holding_days": 2},
    }
    paths = write_shared_cash_result(result, tmp_path, run_request=run_request)
    manifest = ReportManifest.from_path(paths["report_manifest"])
    assert manifest.validate_contents(role="run_manifest") == []


def test_write_shared_cash_result_writes_grouped_artifacts(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ", "600000.SH"],
                "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07", "2026-01-08"]),
                "side": ["buy", "buy", "sell"],
                "quantity": [100, 200, 50],
                "price": [10.0, 20.0, 15.0],
                "notional": [1000.0, 4000.0, 750.0],
                "cost": [5.0, 20.0, 3.75],
                "reason": ["entry"] * 3,
                "board": ["main_board", "main_board", "star_market"],
            }
        ),
        trades=pd.DataFrame(
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
                "board": ["main_board", "star_market"],
            }
        ),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(
            {
                "symbol": ["688001.SH"],
                "trade_date": pd.to_datetime(["2026-01-08"]),
                "side": ["buy"],
                "quantity": [100],
                "price": [30.0],
                "notional": [3000.0],
                "reason": [None],
                "failure_reason": ["limit_up_buy_blocked"],
                "board": ["star_market"],
            }
        ),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 2, "max_drawdown": 0.0},
    )

    paths = write_shared_cash_result(result, tmp_path, group_by=["board"])

    assert paths["orders_by_board"].name == "orders_by_board.csv"
    assert paths["trades_by_board"].name == "trades_by_board.csv"
    assert paths["failed_orders_by_board"].name == "failed_orders_by_board.csv"

    orders_grouped = pd.read_csv(paths["orders_by_board"])
    assert orders_grouped["group_by"].tolist() == ["board", "board"]
    assert orders_grouped["order_count"].tolist() == [2, 1]

    trades_grouped = pd.read_csv(paths["trades_by_board"])
    assert trades_grouped["trade_count"].tolist() == [1, 1]

    failed_grouped = pd.read_csv(paths["failed_orders_by_board"])
    assert failed_grouped["failed_order_count"].tolist() == [1]

    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert manifest_by_key["orders_by_board"] == {
        "key": "orders_by_board",
        "path": "orders_by_board.csv",
        "filename": "orders_by_board.csv",
        "role": "shared_orders_group_summary",
        "group_by": "board",
    }
    assert manifest_by_key["trades_by_board"] == {
        "key": "trades_by_board",
        "path": "trades_by_board.csv",
        "filename": "trades_by_board.csv",
        "role": "shared_trades_group_summary",
        "group_by": "board",
    }
    assert manifest_by_key["failed_orders_by_board"] == {
        "key": "failed_orders_by_board",
        "path": "failed_orders_by_board.csv",
        "filename": "failed_orders_by_board.csv",
        "role": "shared_failed_orders_group_summary",
        "group_by": "board",
    }

    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "| Orders by board | orders_by_board.csv |" in markdown
    assert "| Trades by board | trades_by_board.csv |" in markdown
    assert "| Failed orders by board | failed_orders_by_board.csv |" in markdown


def test_write_shared_cash_result_grouped_empty_frames_write_stable_headers(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(columns=["symbol", "trade_date", "side", "quantity", "price", "notional", "cost", "reason", "industry"]),
        trades=pd.DataFrame(columns=["symbol", "entry_date", "exit_date", "quantity", "entry_price", "exit_price", "gross_pnl", "cost", "net_pnl", "exit_reason", "industry"]),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(columns=["symbol", "trade_date", "side", "quantity", "price", "notional", "reason", "failure_reason", "industry"]),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 0, "max_drawdown": 0.0},
    )

    paths = write_shared_cash_result(result, tmp_path, group_by=["industry"])

    orders_grouped = pd.read_csv(paths["orders_by_industry"])
    assert len(orders_grouped) == 0
    assert "group_by" in orders_grouped.columns

    trades_grouped = pd.read_csv(paths["trades_by_industry"])
    assert len(trades_grouped) == 0

    failed_grouped = pd.read_csv(paths["failed_orders_by_industry"])
    assert len(failed_grouped) == 0

    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert "orders_by_industry" in manifest_by_key
    assert manifest_by_key["orders_by_industry"]["role"] == "shared_orders_group_summary"


def test_shared_cash_grouped_report_manifest_validates_contents(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    (tmp_path / "orders_by_board.csv").write_text(
        "group_by,group_value,order_count,buy_order_count,sell_order_count,total_notional,buy_notional,sell_notional,total_cost\nboard,main_board,2,1,1,2000.0,1000.0,1000.0,10.0\n",
        encoding="utf-8",
    )
    (tmp_path / "trades_by_board.csv").write_text(
        "group_by,group_value,trade_count,win_rate,gross_pnl,net_pnl,total_cost\nboard,main_board,1,1.0,100.0,90.0,10.0\n",
        encoding="utf-8",
    )
    (tmp_path / "failed_orders_by_board.csv").write_text(
        "group_by,group_value,failed_order_count,failed_notional\nboard,main_board,1,1000.0\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "orders_by_board", "path": "orders_by_board.csv", "filename": "orders_by_board.csv", "role": "shared_orders_group_summary", "group_by": "board"},
                    {"key": "trades_by_board", "path": "trades_by_board.csv", "filename": "trades_by_board.csv", "role": "shared_trades_group_summary", "group_by": "board"},
                    {"key": "failed_orders_by_board", "path": "failed_orders_by_board.csv", "filename": "failed_orders_by_board.csv", "role": "shared_failed_orders_group_summary", "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    assert manifest.validate_contents() == []
    assert manifest.validate_contents(role="shared_orders_group_summary", group_by="board") == []


def test_shared_cash_grouped_report_manifest_reports_missing_columns(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    (tmp_path / "orders_by_board.csv").write_text("other,col\n1,2\n", encoding="utf-8")
    manifest_path = tmp_path / "report_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "kind": "shared_cash_backtest_report_manifest",
                "files": [
                    {"key": "orders_by_board", "path": "orders_by_board.csv", "filename": "orders_by_board.csv", "role": "shared_orders_group_summary", "group_by": "board"},
                ],
            }
        ),
        encoding="utf-8",
    )
    manifest = ReportManifest.from_path(manifest_path)
    issues = manifest.validate_contents()
    assert len(issues) == 1
    assert issues[0].code == "missing_columns"
    assert "order_count" in issues[0].message


def test_write_shared_cash_result_unchanged_when_group_by_omitted(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-30", periods=21, freq="B"), "total_equity": [10000.0] * 21}
        ),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 0, "max_drawdown": 0.0},
    )

    paths = write_shared_cash_result(result, tmp_path)

    assert "orders_by_" not in str(list(paths.keys()))
    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    roles = {item["role"] for item in manifest["files"]}
    assert "shared_orders_group_summary" not in roles
    assert "shared_trades_group_summary" not in roles
    assert "shared_failed_orders_group_summary" not in roles


def test_write_shared_cash_result_grouped_with_no_column_empty_failed_orders(tmp_path):
    """Real shared-cash runs produce pd.DataFrame() for empty failed_orders (no columns)."""
    result = SharedCashBacktestResult(
        orders=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ"],
                "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
                "side": ["buy", "sell"],
                "quantity": [100, 50],
                "price": [10.0, 15.0],
                "notional": [1000.0, 750.0],
                "cost": [5.0, 3.75],
                "reason": ["entry"] * 2,
                "board": ["main_board", "star_market"],
            }
        ),
        trades=pd.DataFrame(
            {
                "symbol": ["000001.SZ", "000002.SZ"],
                "entry_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
                "exit_date": pd.to_datetime(["2026-01-09", "2026-01-10"]),
                "quantity": [100, 50],
                "entry_price": [10.0, 15.0],
                "exit_price": [11.0, 16.0],
                "gross_pnl": [100.0, 50.0],
                "cost": [10.0, 5.0],
                "net_pnl": [90.0, 45.0],
                "exit_reason": ["holding_days"] * 2,
                "board": ["main_board", "star_market"],
            }
        ),
        equity_curve=pd.DataFrame(
            {"trade_date": pd.date_range("2026-01-05", periods=5, freq="B"), "total_equity": [10000.0] * 5}
        ),
        failed_orders=pd.DataFrame(),  # real engine produces no-column empty
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 2, "max_drawdown": 0.0},
    )

    paths = write_shared_cash_result(result, tmp_path, group_by=["board"])

    # Grouped orders and trades should be written normally.
    orders_grouped = pd.read_csv(paths["orders_by_board"])
    assert len(orders_grouped) == 2
    assert "group_by" in orders_grouped.columns

    trades_grouped = pd.read_csv(paths["trades_by_board"])
    assert len(trades_grouped) == 2

    # The key fix: no-column empty failed_orders should produce a stable empty grouped CSV.
    failed_grouped = pd.read_csv(paths["failed_orders_by_board"])
    assert len(failed_grouped) == 0
    assert list(failed_grouped.columns) == ["group_by", "group_value", "failed_order_count", "failed_notional"]

    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    manifest_by_key = {item["key"]: item for item in manifest["files"]}
    assert "failed_orders_by_board" in manifest_by_key
    assert manifest_by_key["failed_orders_by_board"]["role"] == "shared_failed_orders_group_summary"


def test_write_single_symbol_result_includes_run_id(tmp_path):
    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1},
    )
    run_request = {
        "command": "backtest-single",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {"symbol": "000001.SZ", "initial_cash": 10000.0, "holding_days": 2},
    }
    paths = write_single_symbol_result(result, tmp_path, run_request=run_request, run_id="research-run-42")

    manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_id"] == "research-run-42"


def test_write_single_symbol_result_run_id_null_when_omitted(tmp_path):
    result = SingleSymbolBacktestResult(
        orders=pd.DataFrame({"symbol": ["000001.SZ"], "side": ["buy"]}),
        trades=pd.DataFrame({"symbol": ["000001.SZ"], "net_pnl": [90.0]}),
        equity_curve=pd.DataFrame({"trade_date": pd.to_datetime(["2026-01-05"]), "total_equity": [10000.0]}),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 10000.0, "trade_count": 1},
    )
    run_request = {
        "command": "backtest-single",
        "strategy_path": "/tmp/strategy.yaml",
        "request": {"symbol": "000001.SZ", "initial_cash": 10000.0, "holding_days": 2},
    }
    paths = write_single_symbol_result(result, tmp_path, run_request=run_request)

    manifest = json.loads(paths["run_manifest"].read_text(encoding="utf-8"))
    assert manifest["run_id"] is None


# ---- shared-cash full-market report integration tests ----


def test_write_shared_cash_result_includes_full_market_files(tmp_path):
    result = SharedCashBacktestResult(
        orders=pd.DataFrame({
            "symbol": ["000001.SZ", "000002.SZ"],
            "trade_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
            "side": ["buy", "buy"],
            "quantity": [100, 200],
            "price": [10.0, 20.0],
            "notional": [1000.0, 4000.0],
            "cost": [5.0, 20.0],
            "reason": ["entry"] * 2,
        }),
        trades=pd.DataFrame({
            "symbol": ["000001.SZ", "000002.SZ"],
            "entry_date": pd.to_datetime(["2026-01-06", "2026-01-07"]),
            "exit_date": pd.to_datetime(["2026-01-09", "2026-01-10"]),
            "quantity": [100, 200],
            "entry_price": [10.0, 20.0],
            "exit_price": [11.0, 22.0],
            "gross_pnl": [100.0, 400.0],
            "cost": [10.0, 40.0],
            "net_pnl": [90.0, 360.0],
            "exit_reason": ["signal"] * 2,
        }),
        equity_curve=pd.DataFrame({
            "trade_date": pd.date_range("2026-01-05", periods=5, freq="B"),
            "cash": [9000.0] * 5,
            "market_value": [1000.0] * 5,
            "total_equity": [10000.0] * 5,
            "position_count": [1] * 5,
        }),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": 10000.0, "final_equity": 10450.0,
            "total_return": 0.045, "sharpe": 1.5, "max_drawdown": -0.02,
            "max_drawdown_duration_days": 1, "total_cost": 75.0,
            "symbol_count": 2, "traded_symbol_count": 2,
            "trade_count": 2,
        },
    )

    paths = write_shared_cash_result(result, tmp_path)

    full_market_keys = [
        "trades_ledger", "round_trips", "symbol_performance",
        "strategy_performance", "full_market_equity_curve", "drawdown_curve",
        "trade_analysis", "capital_usage", "backtest_report",
    ]
    for key in full_market_keys:
        assert key in paths, f"Missing full-market key: {key}"
        assert paths[key].exists(), f"File missing for key: {key}"

    manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
    roles = {entry["role"] for entry in manifest["files"]}
    assert "trades_ledger" in roles
    assert "round_trips" in roles
    assert "symbol_performance" in roles
    assert "strategy_performance" in roles
    assert "full_market_equity_curve" in roles
    assert "drawdown_curve" in roles
    assert "trade_analysis" in roles
    assert "capital_usage" in roles
    assert "full_market_report_workbook" in roles

    # Shared-cash existing roles still present
    assert "orders" in roles
    assert "trades" in roles
    assert "equity_curve" in roles
    assert "summary" in roles

    markdown = paths["summary_markdown"].read_text(encoding="utf-8")
    assert "| Trades ledger |" in markdown
    assert "| Round trips |" in markdown
    assert "| Full-market equity curve |" in markdown
    assert "| Full-market report workbook |" in markdown


def test_shared_cash_manifest_validates_full_market_roles(tmp_path):
    from quant_research_engine.portfolio.report_manifest import ReportManifest

    result = SharedCashBacktestResult(
        orders=pd.DataFrame({
            "symbol": ["000001.SZ"],
            "trade_date": pd.to_datetime(["2026-01-06"]),
            "side": ["buy"],
            "quantity": [100],
            "price": [10.0],
            "notional": [1000.0],
            "cost": [5.0],
            "reason": ["entry"],
        }),
        trades=pd.DataFrame({
            "symbol": ["000001.SZ"],
            "entry_date": pd.to_datetime(["2026-01-06"]),
            "exit_date": pd.to_datetime(["2026-01-09"]),
            "quantity": [100],
            "entry_price": [10.0],
            "exit_price": [11.0],
            "gross_pnl": [100.0],
            "cost": [10.0],
            "net_pnl": [90.0],
            "exit_reason": ["signal"],
        }),
        equity_curve=pd.DataFrame({
            "trade_date": pd.date_range("2026-01-05", periods=5, freq="B"),
            "cash": [9000.0] * 5,
            "market_value": [1000.0] * 5,
            "total_equity": [10000.0, 10090.0, 10090.0, 10090.0, 10090.0],
            "position_count": [1] * 5,
        }),
        failed_orders=pd.DataFrame(),
        summary={
            "initial_cash": 10000.0, "final_equity": 10090.0,
            "total_return": 0.009, "sharpe": 1.0, "max_drawdown": 0.0,
            "max_drawdown_duration_days": 0, "total_cost": 15.0,
            "symbol_count": 1, "traded_symbol_count": 1, "trade_count": 1,
        },
    )

    paths = write_shared_cash_result(result, tmp_path)
    manifest = ReportManifest.from_path(paths["report_manifest"])
    issues = manifest.validate_contents()
    assert issues == []


def test_write_batch_result_compact_writes_symbol_month_returns(tmp_path):
    import json

    from quant_research_engine.portfolio.report_manifest import ReportManifest

    dates = list(pd.to_datetime(["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-05"]))
    equity_a = pd.DataFrame({
        "trade_date": dates,
        "total_equity": [100.0, 100.0, 100.0, 100.0, 105.0, 110.0],  # Jan flat, Feb +10%
    })
    equity_b = pd.DataFrame({
        "trade_date": dates,
        "total_equity": [100.0, 100.0, 100.0, 100.0, 95.0, 90.0],   # Jan flat, Feb -10%
    })
    singles = {}
    for symbol, curve in (("000001.SZ", equity_a), ("000002.SZ", equity_b)):
        singles[symbol] = SingleSymbolBacktestResult(
            orders=pd.DataFrame({"symbol": [symbol], "side": ["buy"]}),
            trades=pd.DataFrame({"symbol": [symbol], "net_pnl": [1.0]}),
            equity_curve=curve.assign(cash=0.0, position_quantity=0, market_value=curve["total_equity"]),
            failed_orders=pd.DataFrame(),
            summary={"initial_cash": 100.0, "final_equity": float(curve["total_equity"].iloc[-1]), "trade_count": 1},
        )
    result = BatchBacktestResult(
        symbols=["000001.SZ", "000002.SZ"],
        results=singles,
        summary=pd.DataFrame({"symbol": ["000001.SZ", "000002.SZ"], "trade_count": [1, 1], "total_return": [0.1, -0.1]}),
        summary_metrics={"symbol_count": 2},
    )

    paths = write_batch_result(result, tmp_path, compact=True)

    assert paths["symbol_month_returns"].exists()
    df = pd.read_csv(paths["symbol_month_returns"])
    assert set(df.columns) == {"window", "symbol", "total_return"}
    # oracle: each symbol has exactly 2024-01 and 2024-02 rows
    assert sorted(df["window"].unique()) == ["2024-01", "2024-02"]
    feb_a = df.loc[(df["symbol"] == "000001.SZ") & (df["window"] == "2024-02"), "total_return"].iloc[0]
    feb_b = df.loc[(df["symbol"] == "000002.SZ") & (df["window"] == "2024-02"), "total_return"].iloc[0]
    assert feb_a == pytest.approx(110.0 / 100.0 - 1)
    assert feb_b == pytest.approx(90.0 / 100.0 - 1)

    manifest = json.loads((tmp_path / "report_manifest.json").read_text(encoding="utf-8"))
    assert "symbol_month_returns" in {f["role"] for f in manifest["files"]}
    rm = ReportManifest.from_path(tmp_path / "report_manifest.json")
    assert rm.validate_contents() == []
