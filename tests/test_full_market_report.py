import json

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.portfolio.batch import BatchBacktestResult
from quant_research_engine.portfolio.full_market_report import (
    build_trades_ledger,
    build_round_trips,
    build_symbol_performance,
    build_strategy_performance,
    build_full_market_equity_curve,
    build_drawdown_curve,
    build_trade_analysis,
    build_capital_usage,
    write_full_market_excel,
    write_full_market_report,
)
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult


def _make_single_result(symbol: str, trade_count: int = 2) -> SingleSymbolBacktestResult:
    dates = pd.date_range("2026-01-05", periods=trade_count * 3, freq="B")
    return SingleSymbolBacktestResult(
        orders=pd.DataFrame({
            "symbol": [symbol] * trade_count,
            "trade_date": dates[:trade_count],
            "side": ["buy"] * trade_count,
            "quantity": [100] * trade_count,
            "price": [10.0] * trade_count,
            "notional": [1000.0] * trade_count,
            "cost": [5.0] * trade_count,
        }),
        trades=pd.DataFrame({
            "symbol": [symbol] * trade_count,
            "entry_date": dates[:trade_count],
            "exit_date": dates[trade_count : trade_count * 2],
            "quantity": [100] * trade_count,
            "entry_price": [10.0] * trade_count,
            "exit_price": [11.0] * trade_count,
            "gross_pnl": [100.0] * trade_count,
            "cost": [10.0] * trade_count,
            "net_pnl": [90.0] * trade_count,
            "exit_reason": ["signal"] * trade_count,
        }),
        equity_curve=pd.DataFrame({
            "trade_date": pd.date_range("2026-01-05", periods=21, freq="B"),
            "cash": [9000.0] * 21,
            "position_quantity": [100] * 21,
            "market_value": [1000.0] * 21,
            "total_equity": np.linspace(10000.0, 11800.0, 21),
        }),
        failed_orders=pd.DataFrame(),
        summary={"initial_cash": 10000.0, "final_equity": 11800.0, "total_return": 0.18, "trade_count": trade_count, "win_rate": 1.0, "total_cost": 20.0},
    )


class TestBuildTradesLedger:
    def test_empty_results(self):
        result = build_trades_ledger({})
        assert result.empty
        assert "symbol" in result.columns
        assert "lot_count" in result.columns
        assert "commission" in result.columns

    def test_combines_symbol_orders(self):
        r1 = _make_single_result("000001.SZ")
        r2 = _make_single_result("000002.SZ")
        df = build_trades_ledger({"000001.SZ": r1, "000002.SZ": r2})
        assert len(df) == 4
        assert set(df["symbol"].unique()) == {"000001.SZ", "000002.SZ"}
        assert (df["side"] == "buy").all()
        assert (df["price_raw"] == 10.0).all()
        assert (df["price_executed"] == 10.0).all()
        assert (df["total_cost"] == 5.0).all()
        assert (df["status"] == "filled").all()
        assert df["commission"].isna().all()
        assert df["lot_count"].isna().all()
        assert df["realized_pnl"].isna().all()  # buy rows → null pnl

    def test_sell_rows_have_null_realized_pnl(self):
        r = _make_single_result("000001.SZ")
        r = SingleSymbolBacktestResult(
            orders=pd.DataFrame({
                "symbol": ["000001.SZ", "000001.SZ"],
                "trade_date": pd.date_range("2026-01-05", periods=2, freq="B"),
                "side": ["buy", "sell"],
                "quantity": [100, 100],
                "price": [10.0, 11.0],
                "notional": [1000.0, 1100.0],
                "cost": [5.0, 5.5],
            }),
            trades=r.trades, equity_curve=r.equity_curve,
            failed_orders=r.failed_orders, summary=r.summary,
        )
        df = build_trades_ledger({"000001.SZ": r})
        assert len(df) == 2
        buy_row = df[df["side"] == "buy"].iloc[0]
        sell_row = df[df["side"] == "sell"].iloc[0]
        assert pd.isna(buy_row["realized_pnl"])
        assert pd.isna(sell_row["realized_pnl"])
        assert sell_row["realized_pnl"] != sell_row["total_cost"]


class TestBuildRoundTrips:
    def test_empty_results(self):
        result = build_round_trips({})
        assert result.empty
        assert "entry_notional" in result.columns
        assert "max_favorable_return" in result.columns

    def test_combines_symbol_trades(self):
        r1 = _make_single_result("000001.SZ")
        r2 = _make_single_result("000002.SZ")
        df = build_round_trips({"000001.SZ": r1, "000002.SZ": r2})
        assert len(df) == 4
        assert set(df["symbol"].unique()) == {"000001.SZ", "000002.SZ"}
        assert (df["gross_pnl"] == 100.0).all()
        assert (df["net_pnl"] == 90.0).all()
        assert (df["entry_price"] == 10.0).all()
        assert (df["exit_price"] == 11.0).all()
        assert df["holding_days"].notna().all()
        assert df["entry_notional"].notna().all()
        assert df["exit_notional"].notna().all()
        assert df["max_favorable_return"].isna().all()
        assert df["max_adverse_return"].isna().all()

    def test_gross_net_return_computed(self):
        r = _make_single_result("000001.SZ")
        df = build_round_trips({"000001.SZ": r})
        assert len(df) == 2
        assert df["gross_return"].iloc[0] == pytest.approx(0.1)  # 100 / 1000
        assert df["net_return"].iloc[0] == pytest.approx(0.09)  # 90 / 1000


class TestBuildSymbolPerformance:
    def test_empty_summary(self):
        df = build_symbol_performance(pd.DataFrame(), {})
        assert df.empty
        assert "symbol" in df.columns

    def test_derives_sharpe_and_drawdown(self):
        r = _make_single_result("000001.SZ")
        summary = pd.DataFrame([{
            "symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2,
            "win_rate": 1.0, "total_cost": 20.0, "win_count": 2,
            "loss_count": 0, "board": "main_board", "industry": "finance",
        }])
        df = build_symbol_performance(summary, {"000001.SZ": r})
        assert len(df) == 1
        row = df.iloc[0]
        assert row["symbol"] == "000001.SZ"
        assert row["board"] == "main_board"
        assert row["strategy_total_return"] == 0.18
        assert row["sharpe"] is not None
        assert row["max_drawdown"] is not None


class TestBuildFullMarketEquityCurve:
    def test_empty_results(self):
        df = build_full_market_equity_curve({})
        assert df.empty

    def test_aggregates_across_symbols(self):
        r1 = _make_single_result("000001.SZ")
        r2 = _make_single_result("000002.SZ")
        df = build_full_market_equity_curve({"000001.SZ": r1, "000002.SZ": r2})
        assert not df.empty
        assert "trade_date" in df.columns
        assert "total_equity" in df.columns
        assert "daily_return" in df.columns
        assert "cumulative_return" in df.columns
        assert "position_count" in df.columns
        assert df["total_equity"].iloc[0] == pytest.approx(20000.0)  # 2 × 10000
        assert df["position_count"].iloc[0] == 2


class TestBuildDrawdownCurve:
    def test_empty_equity(self):
        df = build_drawdown_curve(pd.DataFrame())
        assert df.empty

    def test_computes_running_peak_and_drawdown(self):
        eq = pd.DataFrame({
            "trade_date": pd.date_range("2026-01-05", periods=5, freq="B"),
            "total_equity": [100.0, 110.0, 95.0, 105.0, 120.0],
        })
        df = build_drawdown_curve(eq)
        assert len(df) == 5
        assert df["running_peak"].iloc[2] == 110.0
        assert df["drawdown"].iloc[2] == pytest.approx(-15.0)
        assert df["drawdown_pct"].iloc[2] == pytest.approx(-15.0 / 110.0)
        assert df["drawdown_duration_days"].iloc[2] == 1


class TestBuildStrategyPerformance:
    def test_aggregates_from_round_trips_and_equity(self):
        r = _make_single_result("000001.SZ")
        summary = pd.DataFrame([{
            "symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2,
            "win_rate": 1.0, "total_cost": 20.0,
        }])
        rt = build_round_trips({"000001.SZ": r})
        eq = build_full_market_equity_curve({"000001.SZ": r})
        perf = build_strategy_performance(
            {"symbol_count": 1, "traded_symbol_count": 1},
            summary, rt, eq,
            run_id="test-run", strategy_id="strat-1",
        )
        assert perf["run_id"] == "test-run"
        assert perf["total_trade_count"] == 2
        assert perf["winning_trade_count"] == 2
        assert perf["win_rate"] == 1.0
        assert perf["net_profit"] == pytest.approx(180.0)
        assert perf["sharpe"] is not None
        assert perf["largest_winning_trade"] == pytest.approx(90.0)
        assert "best_symbols" in perf
        assert "worst_symbols" in perf


class TestBuildTradeAnalysis:
    def test_empty_round_trips(self):
        ta = build_trade_analysis(pd.DataFrame())
        assert ta["win_loss_counts"] == {"win": 0, "loss": 0}
        assert ta["percent_profitable"] is None

    def test_with_trades(self):
        r = _make_single_result("000001.SZ")
        rt = build_round_trips({"000001.SZ": r})
        ta = build_trade_analysis(rt)
        assert ta["win_loss_counts"]["win"] == 2
        assert ta["percent_profitable"] == 1.0
        assert ta["average_pnl"] == pytest.approx(90.0)
        assert ta["largest_winning_trade"] == pytest.approx(90.0)


class TestBuildCapitalUsage:
    def test_computes_cagr(self):
        r = _make_single_result("000001.SZ")
        eq = build_full_market_equity_curve({"000001.SZ": r})
        cu = build_capital_usage(eq, {"net_profit": 180.0, "strategy_total_return": 0.18, "max_drawdown": 0.0})
        assert "cagr" in cu
        assert "average_margin_used" in cu
        assert cu["average_margin_used"] is None
        assert cu["margin_call_count"] == 0


class TestWriteFullMarketExcel:
    def test_creates_workbook_with_all_sheets(self, tmp_path):
        eq = pd.DataFrame({"trade_date": pd.date_range("2026-01-05", periods=2, freq="B"), "total_equity": [100.0, 110.0]})
        dd = build_drawdown_curve(eq)
        tl = pd.DataFrame({"symbol": ["000001.SZ"], "trade_date": ["2026-01-06"], "side": ["buy"], "quantity": [100]})
        path = write_full_market_excel(
            tmp_path, {}, tl, pd.DataFrame(), pd.DataFrame(),
            eq, dd, {}, {},
        )
        assert path.name == "backtest_report.xlsx"
        assert path.exists()

        from openpyxl import load_workbook
        wb = load_workbook(str(path))
        sheet_names = wb.sheetnames
        assert "Overview" in sheet_names
        assert "TradesLedger" in sheet_names
        assert "RoundTrips" in sheet_names
        assert "SymbolPerformance" in sheet_names
        assert "EquityCurve" in sheet_names
        assert "DrawdownCurve" in sheet_names
        assert "TradeAnalysis" in sheet_names
        assert "CapitalUsage" in sheet_names
        assert "Artifacts" in sheet_names


class TestWriteFullMarketReport:
    def test_writes_all_artifacts(self, tmp_path):
        r1 = _make_single_result("000001.SZ")
        r2 = _make_single_result("000002.SZ")
        result = BatchBacktestResult(
            symbols=["000001.SZ", "000002.SZ"],
            results={"000001.SZ": r1, "000002.SZ": r2},
            summary=pd.DataFrame([
                {"symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2, "win_rate": 1.0, "total_cost": 20.0},
                {"symbol": "000002.SZ", "total_return": 0.12, "trade_count": 2, "win_rate": 0.5, "total_cost": 20.0},
            ]),
            summary_metrics={
                "symbol_count": 2, "traded_symbol_count": 2,
                "positive_return_symbol_rate": 1.0, "mean_total_return": 0.15,
                "median_total_return": 0.15, "total_cost": 40.0,
            },
        )
        paths = write_full_market_report(result, tmp_path, run_id="test-run")

        assert paths["trades_ledger"].name == "trades_ledger.csv"
        assert paths["round_trips"].name == "round_trips.csv"
        assert paths["symbol_performance"].name == "symbol_performance.csv"
        assert paths["strategy_performance"].name == "strategy_performance.json"
        assert paths["equity_curve"].name == "equity_curve.csv"
        assert paths["drawdown_curve"].name == "drawdown_curve.csv"
        assert paths["trade_analysis"].name == "trade_analysis.json"
        assert paths["capital_usage"].name == "capital_usage.json"
        assert paths["backtest_report"].name == "backtest_report.xlsx"

        assert pd.read_csv(paths["trades_ledger"]).iloc[0]["symbol"] == "000001.SZ"
        assert pd.read_csv(paths["round_trips"]).iloc[0]["symbol"] == "000001.SZ"
        strat_perf = json.loads(paths["strategy_performance"].read_text(encoding="utf-8"))
        assert strat_perf["run_id"] == "test-run"
        assert strat_perf["total_trade_count"] == 4

    def test_handles_empty_results(self, tmp_path):
        result = BatchBacktestResult(
            symbols=[],
            results={},
            summary=pd.DataFrame(),
            summary_metrics={},
        )
        paths = write_full_market_report(result, tmp_path)
        assert all(p.exists() for p in paths.values())
        assert paths["trades_ledger"].stat().st_size > 0


class TestBatchResultIntegration:
    def test_write_batch_result_includes_full_market_files(self, tmp_path):
        from quant_research_engine.portfolio.io import write_batch_result

        r = _make_single_result("000001.SZ")
        result = BatchBacktestResult(
            symbols=["000001.SZ"],
            results={"000001.SZ": r},
            summary=pd.DataFrame([{
                "symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2,
                "win_rate": 1.0, "total_cost": 20.0,
            }]),
            summary_metrics={"symbol_count": 1, "traded_symbol_count": 1},
        )
        paths = write_batch_result(result, tmp_path)

        assert "trades_ledger" in paths
        assert "round_trips" in paths
        assert "symbol_performance" in paths
        assert "strategy_performance" in paths
        assert "backtest_report" in paths
        assert paths["backtest_report"].exists()

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

    def test_existing_roles_still_present(self, tmp_path):
        from quant_research_engine.portfolio.io import write_batch_result

        r = _make_single_result("000001.SZ")
        result = BatchBacktestResult(
            symbols=["000001.SZ"],
            results={"000001.SZ": r},
            summary=pd.DataFrame([{
                "symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2,
                "win_rate": 1.0, "total_cost": 20.0,
            }]),
            summary_metrics={"symbol_count": 1},
        )
        paths = write_batch_result(result, tmp_path)
        manifest = json.loads(paths["report_manifest"].read_text(encoding="utf-8"))
        roles = {entry["role"] for entry in manifest["files"]}
        assert "summary" in roles
        assert "summary_metrics" in roles
        assert "summary_markdown" in roles
        assert "window_summary" in roles
        assert "rolling_summary" in roles
        assert "orders" in roles
        assert "trades" in roles


class TestManifestValidation:
    def test_new_roles_in_required_columns(self):
        from quant_research_engine.portfolio.report_manifest import _REQUIRED_COLUMNS_BY_ROLE
        assert "trades_ledger" in _REQUIRED_COLUMNS_BY_ROLE
        assert "round_trips" in _REQUIRED_COLUMNS_BY_ROLE
        assert "symbol_performance" in _REQUIRED_COLUMNS_BY_ROLE
        assert "full_market_equity_curve" in _REQUIRED_COLUMNS_BY_ROLE
        assert "drawdown_curve" in _REQUIRED_COLUMNS_BY_ROLE
        assert "full_market_report_workbook" in _REQUIRED_COLUMNS_BY_ROLE
        assert "strategy_performance" in _REQUIRED_COLUMNS_BY_ROLE
        assert "trade_analysis" in _REQUIRED_COLUMNS_BY_ROLE
        assert "capital_usage" in _REQUIRED_COLUMNS_BY_ROLE

    def test_manifest_validation_passes_for_generated_report(self, tmp_path):
        from quant_research_engine.portfolio.io import write_batch_result
        from quant_research_engine.portfolio.report_manifest import ReportManifest

        r = _make_single_result("000001.SZ")
        result = BatchBacktestResult(
            symbols=["000001.SZ"],
            results={"000001.SZ": r},
            summary=pd.DataFrame([{
                "symbol": "000001.SZ", "total_return": 0.18, "trade_count": 2,
                "win_rate": 1.0, "total_cost": 20.0,
            }]),
            summary_metrics={"symbol_count": 1},
        )
        paths = write_batch_result(result, tmp_path)
        manifest = ReportManifest.from_path(paths["report_manifest"])
        issues = manifest.validate_contents()
        assert issues == []
