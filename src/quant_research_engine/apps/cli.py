from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Sequence

from quant_research_engine.config.loader import load_market_profile
from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.data.assembler import ResearchFrameAssembler
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.evaluation.engine import EvaluationEngine
from quant_research_engine.evaluation.models import EvaluationRequest, EvaluationResult
from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.portfolio.analytics import (
    summarize_batch_by,
    summarize_shared_orders_by,
    summarize_shared_trades_by,
    summarize_shared_failed_orders_by,
)
from quant_research_engine.portfolio.benchmark import summarize_benchmark_relative_performance
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.full_market_report import build_full_market_equity_curve
from quant_research_engine.portfolio.io import (
    batch_summary_markdown,
    shared_summary_markdown,
    write_batch_result,
    write_shared_cash_result,
    write_single_symbol_result,
)
from quant_research_engine.portfolio.report_manifest import ReportManifest
from quant_research_engine.portfolio.shared import SharedCashBacktestEngine, SharedCashBacktestRequest
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestEngine, SingleSymbolBacktestRequest
from quant_research_engine.preflight import PreflightRequest, PreflightRunner
from quant_research_engine.strategies.compiler import (
    compile_entry,
    compile_to_strategy_spec_dict,
    parse_high_level_entry,
)
from quant_research_engine.strategies.missing_factor import (
    emit_missing_factor_requests,
    extract_missing_factors,
)
from quant_research_engine.strategies.smoke_runner import run_strategy_smoke
from quant_research_engine.strategies.spec import StrategySpec
from quant_research_engine.evaluation.io import write_evaluation_output
from quant_research_engine.orchestration.research_run import ResearchRunRequest, run_research_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qre")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile_parser = subparsers.add_parser("profile", help="Load and summarize a market profile")
    profile_parser.add_argument("path", type=Path)

    report_files_parser = subparsers.add_parser("report-files", help="List files from a report manifest")
    report_files_parser.add_argument("manifest", type=Path)
    report_files_parser.add_argument("--role")
    report_files_parser.add_argument("--symbol")
    report_files_parser.add_argument("--window")
    report_files_parser.add_argument("--group-by")
    report_files_parser.add_argument("--window-size", type=int, default=None)
    report_files_parser.add_argument("--keys", action="store_true", help="Print manifest keys instead of paths.")
    report_files_parser.add_argument(
        "--check-exists",
        action="store_true",
        help="Return an error if any matched manifest file path is missing.",
    )
    report_files_parser.add_argument(
        "--validate-contents",
        action="store_true",
        help="Return an error if any matched manifest file has structural validation issues.",
    )
    report_files_parser.add_argument(
        "--require-match",
        action="store_true",
        help="Return an error if the selected filters match no manifest entries.",
    )
    report_files_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON file selection object on stdout.",
    )

    report_audit_parser = subparsers.add_parser("report-audit", help="Audit files from a report manifest")
    report_audit_parser.add_argument("manifest", type=Path)
    report_audit_parser.add_argument("--role")
    report_audit_parser.add_argument("--symbol")
    report_audit_parser.add_argument("--window")
    report_audit_parser.add_argument("--group-by")
    report_audit_parser.add_argument("--window-size", type=int, default=None)
    report_audit_parser.add_argument(
        "--require-match",
        action="store_true",
        help="Return an error if the selected filters match no manifest entries.",
    )
    report_audit_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON audit object on stdout.",
    )

    db_parser = subparsers.add_parser("db-smoke", help="Run a small read-only market data smoke check")
    db_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    db_parser.add_argument("--start", required=True, type=date.fromisoformat)
    db_parser.add_argument("--end", required=True, type=date.fromisoformat)
    db_parser.add_argument("--codes", nargs="*", default=None)
    db_parser.add_argument("--limit", type=int, default=5)

    factor_parser = subparsers.add_parser("factor-smoke", help="Run a small read-only factor data smoke check")
    factor_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    factor_parser.add_argument("--start", required=True, type=date.fromisoformat)
    factor_parser.add_argument("--end", required=True, type=date.fromisoformat)
    factor_parser.add_argument("--codes", nargs="*", default=None)
    factor_parser.add_argument("--logical-name", required=True)
    factor_parser.add_argument("--target", required=True, help="Qualified factor target, e.g. factors.table.column")

    benchmark_parser = subparsers.add_parser("benchmark-smoke", help="Run a small read-only benchmark data smoke check")
    benchmark_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    benchmark_parser.add_argument("--table", required=True, help="Qualified benchmark table, e.g. public.index_daily")
    benchmark_parser.add_argument("--start", required=True, type=date.fromisoformat)
    benchmark_parser.add_argument("--end", required=True, type=date.fromisoformat)
    benchmark_parser.add_argument("--codes", nargs="*", default=None)
    benchmark_parser.add_argument("--value-column", default="close")
    benchmark_parser.add_argument("--limit", type=int, default=None)

    metadata_parser = subparsers.add_parser("metadata-smoke", help="Run a small read-only security metadata smoke check")
    metadata_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    metadata_parser.add_argument("--codes", nargs="*", default=None)
    metadata_parser.add_argument("--limit", type=int, default=10)

    eval_parser = subparsers.add_parser("eval-smoke", help="Run a small expression evaluation smoke check")
    eval_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    eval_parser.add_argument("--start", required=True, type=date.fromisoformat)
    eval_parser.add_argument("--end", required=True, type=date.fromisoformat)
    eval_parser.add_argument("--codes", nargs="*", default=None)
    eval_parser.add_argument("--logical-name", required=True)
    eval_parser.add_argument("--target", required=True, help="Qualified factor target, e.g. factors.table.column")
    eval_parser.add_argument("--signal", required=True, help="Expression signal, e.g. 'rsi_2 < 10'")
    eval_parser.add_argument("--horizons", nargs="+", type=int, default=[1, 3, 5])
    eval_parser.add_argument("--round-trip-cost-rate", type=float, default=None)
    eval_parser.add_argument("--market-profile", type=Path, help="Optional market profile YAML for rough friction estimate.")

    eval_config_parser = subparsers.add_parser("eval-config", help="Run evaluation from a strategy YAML file")
    eval_config_parser.add_argument("strategy", type=Path)
    eval_config_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    eval_config_parser.add_argument("--start", required=True, type=date.fromisoformat)
    eval_config_parser.add_argument("--end", required=True, type=date.fromisoformat)
    eval_config_parser.add_argument("--codes", nargs="*", default=None)
    eval_config_parser.add_argument("--round-trip-cost-rate", type=float, default=None)
    eval_config_parser.add_argument("--market-profile", type=Path, help="Optional market profile YAML for rough friction estimate.")
    eval_config_parser.add_argument("--group-by", nargs="*", default=None, help="Optional grouping columns for event forward-return summaries, e.g. board industry")
    eval_config_parser.add_argument("--output-dir", type=Path, help="Optional output directory for durable evaluation artifacts.")
    eval_config_parser.add_argument("--random-baseline-seed", type=int, default=None, help="Optional seed for deterministic random-baseline comparison.")
    eval_config_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    preflight_parser = subparsers.add_parser("preflight", help="Run read-only data and factor checks before broad runs")
    preflight_parser.add_argument("strategy", type=Path)
    preflight_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    preflight_parser.add_argument("--start", required=True, type=date.fromisoformat)
    preflight_parser.add_argument("--end", required=True, type=date.fromisoformat)
    preflight_parser.add_argument("--codes", nargs="*", default=None)
    preflight_parser.add_argument("--min-factor-coverage", type=float, default=0.8)
    preflight_parser.add_argument("--benchmark-table")
    preflight_parser.add_argument("--benchmark-code")
    preflight_parser.add_argument("--benchmark-value-column", default="close")
    preflight_parser.add_argument("--output-json", type=Path)
    preflight_parser.add_argument("--output-dir", type=Path, help="Output directory for missing-factor request artifacts.")
    preflight_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    backtest_parser = subparsers.add_parser("backtest-single", help="Run a single-symbol portfolio backtest from YAML")
    backtest_parser.add_argument("strategy", type=Path)
    backtest_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    backtest_parser.add_argument("--symbol", required=True)
    backtest_parser.add_argument("--start", required=True, type=date.fromisoformat)
    backtest_parser.add_argument("--end", required=True, type=date.fromisoformat)
    backtest_parser.add_argument("--initial-cash", type=float, default=100000.0)
    backtest_parser.add_argument(
        "--market-profile",
        type=Path,
        help="Optional market profile YAML. Defaults to built-in zero-slippage A-share profile.",
    )
    backtest_parser.add_argument("--output-dir", type=Path, help="Optional directory for orders/trades/equity/summary files.")
    backtest_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    batch_parser = subparsers.add_parser("backtest-batch", help="Run independent per-symbol portfolio backtests from YAML")
    batch_parser.add_argument("strategy", type=Path)
    batch_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    batch_parser.add_argument("--start", required=True, type=date.fromisoformat)
    batch_parser.add_argument("--end", required=True, type=date.fromisoformat)
    batch_parser.add_argument("--codes", nargs="*", default=None)
    batch_parser.add_argument("--initial-cash", type=float, default=100000.0)
    batch_parser.add_argument("--group-by", nargs="*", default=None, help="Optional summary grouping columns, e.g. board industry")
    batch_parser.add_argument(
        "--group-rank-top-n",
        type=int,
        default=1,
        help="Number of top and bottom symbols to write per group when --group-by is used.",
    )
    batch_parser.add_argument(
        "--market-profile",
        type=Path,
        help="Optional market profile YAML. Defaults to built-in zero-slippage A-share profile.",
    )
    batch_parser.add_argument("--benchmark-table", help="Optional benchmark table, e.g. public.stock_daily or public.index_daily.")
    batch_parser.add_argument("--benchmark-code", help="Optional benchmark ts_code, e.g. 000300.SH or 000002.SZ.")
    batch_parser.add_argument("--benchmark-value-column", default="close")
    batch_parser.add_argument("--print-summary-md", action="store_true", help="Print a human-readable Markdown summary to stdout.")
    batch_parser.add_argument("--output-dir", type=Path, help="Optional directory for batch summary and per-symbol files.")
    batch_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    shared_parser = subparsers.add_parser("backtest-shared", help="Run a shared-cash multi-symbol portfolio backtest from YAML")
    shared_parser.add_argument("strategy", type=Path)
    shared_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    shared_parser.add_argument("--start", required=True, type=date.fromisoformat)
    shared_parser.add_argument("--end", required=True, type=date.fromisoformat)
    shared_parser.add_argument("--codes", nargs="*", default=None)
    shared_parser.add_argument("--initial-cash", type=float, default=100000.0)
    shared_parser.add_argument("--max-positions", type=int, required=True)
    shared_parser.add_argument(
        "--weight-model",
        choices=["equal_weight", "score_weight", "inverse_volatility"],
        default=None,
    )
    shared_parser.add_argument("--score-column", help="Required when --weight-model score_weight is used.")
    shared_parser.add_argument("--volatility-column", help="Required when --weight-model inverse_volatility is used.")
    shared_parser.add_argument("--stop-loss-pct", type=float, help="Optional long stop-loss percentage, e.g. 0.08.")
    shared_parser.add_argument("--take-profit-pct", type=float, help="Optional long take-profit percentage, e.g. 0.12.")
    shared_parser.add_argument("--trailing-stop-pct", type=float, help="Optional long trailing-stop percentage, e.g. 0.10.")
    shared_parser.add_argument(
        "--rebalance-interval-days",
        type=int,
        help="Optional fixed trading-day interval for shared-cash position rebalancing.",
    )
    shared_parser.add_argument(
        "--market-profile",
        type=Path,
        help="Optional market profile YAML. Defaults to built-in zero-slippage A-share profile.",
    )
    shared_parser.add_argument("--benchmark-table", help="Optional benchmark table, e.g. public.stock_daily or public.index_daily.")
    shared_parser.add_argument("--benchmark-code", help="Optional benchmark ts_code, e.g. 000300.SH or 000002.SZ.")
    shared_parser.add_argument("--benchmark-value-column", default="close")
    shared_parser.add_argument("--metadata-columns", nargs="*", default=None, help="Optional metadata columns to attach to shared-cash order, trade, and failed-order output rows.")
    shared_parser.add_argument("--group-by", nargs="*", default=None, help="Optional grouping columns for shared-cash order, trade, and failed-order summaries.")
    shared_parser.add_argument("--print-summary-md", action="store_true", help="Print a human-readable Markdown summary to stdout.")
    shared_parser.add_argument("--output-dir", type=Path, help="Optional directory for portfolio result files.")
    shared_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    compile_parser = subparsers.add_parser("compile", help="Compile a high-level strategy entry and optionally run preflight")
    compile_parser.add_argument("strategy", type=Path, help="Path to high-level strategy entry YAML.")
    compile_parser.add_argument("--output-dir", type=Path, help="Optional directory for compiled low-level spec and preflight artifacts.")
    compile_parser.add_argument("--preflight", action="store_true", help="Run preflight checks against the compiled low-level spec.")
    compile_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    compile_parser.add_argument("--start", type=date.fromisoformat, help="Preflight start date (required with --preflight).")
    compile_parser.add_argument("--end", type=date.fromisoformat, help="Preflight end date (required with --preflight).")
    compile_parser.add_argument("--codes", nargs="*", default=None)
    compile_parser.add_argument("--min-factor-coverage", type=float, default=0.8)
    compile_parser.add_argument("--run-id", default=None, help="Optional run-level identifier for durable output linkage.")

    smoke_parser = subparsers.add_parser("strategy-smoke", help="Run smoke validation for the three canonical strategy entries")
    smoke_parser.add_argument("--output-dir", type=Path, default=Path("outputs/strategy-entry-smoke"), help="Output directory for smoke artifacts and summary.")
    smoke_parser.add_argument("--strategies", nargs="*", default=None, help="Paths to strategy entry YAML files (defaults to the three canonical examples).")
    smoke_parser.add_argument("--no-preflight", action="store_true", help="Skip preflight even if a database is available.")
    smoke_parser.add_argument("--no-backtest", action="store_true", help="Skip backtest smoke even if preflight passes.")
    smoke_parser.add_argument("--start", type=date.fromisoformat, default=None, help="Preflight/backtest start date (optional, default 2024-01-01).")
    smoke_parser.add_argument("--end", type=date.fromisoformat, default=None, help="Preflight/backtest end date (optional, default 2024-02-01).")

    smoke_files_parser = subparsers.add_parser("smoke-files", help="Summarize latest smoke run artifacts")
    smoke_files_parser.add_argument("--output-dir", type=Path, default=None,
                                    help="Smoke output directory (default: outputs/strategy-entry-smoke/).")
    smoke_files_parser.add_argument("--json", action="store_true",
                                    help="Emit machine-readable JSON on stdout.")
    smoke_files_parser.add_argument("--strategy", type=str, default=None,
                                    help="Filter to a single strategy_id.")
    smoke_files_parser.add_argument("--role", type=str, default=None,
                                    help="Filter artifact role counts to a single role.")
    smoke_files_parser.add_argument("--latest", action="store_true",
                                    help="Use the latest smoke run directory (default when --output-dir is omitted).")
    smoke_files_parser.add_argument("--details", action="store_true",
                                    help="Print per-strategy stage statuses and artifact keys.")
    smoke_files_parser.add_argument("--output-file", type=Path, default=None,
                                    help="Export output to file (creates parent directories as needed).")
    smoke_files_parser.add_argument("--check-exists", action="store_true",
                                    help="Validate that all referenced artifact files exist on disk.")
    smoke_files_parser.add_argument("--require-match", action="store_true",
                                    help="Return exit code 2 when --strategy or --role selector matches nothing.")
    smoke_files_parser.add_argument("--list-missing", action="store_true",
                                    help="Print sorted missing artifact paths to stdout (requires --check-exists).")
    smoke_files_parser.add_argument("--quiet", action="store_true",
                                    help="Suppress normal stdout; exit code and stderr diagnostics are preserved.")
    smoke_files_parser.add_argument("--status-only", action="store_true",
                                    help="Emit only overall status (text) or minimal JSON; for automation.")
    smoke_files_parser.add_argument("--status-format", type=str, choices=["text", "json"], default=None,
                                    help="Force status output format (requires --status-only).")
    smoke_files_parser.add_argument("--status-reason", action="store_true",
                                    help="Include failure reason in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-code", action="store_true",
                                    help="Emit numeric status code (0/1) in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-meta", action="store_true",
                                    help="Include run_id and source_mode metadata in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-summary", action="store_true",
                                    help="Include strategy counts (total/pass/fail/skip) in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-fail-key", action="store_true",
                                    help="Include first failing strategy-id in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-fail-stage", action="store_true",
                                    help="Include first failing stage name in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-timestamp", action="store_true",
                                    help="Include run generation timestamp in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-output-dir", action="store_true",
                                    help="Include resolved run directory in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-manifest-path", action="store_true",
                                    help="Include resolved manifest file path in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-manifest-exists", action="store_true",
                                    help="Include manifest existence boolean in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-artifact-count", action="store_true",
                                    help="Include artifact total count in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-strategy-count", action="store_true",
                                    help="Include strategy total count in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-fail-count", action="store_true",
                                    help="Include failing-strategy count in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-skip-count", action="store_true",
                                    help="Include skipped-strategy count in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-pass-count", action="store_true",
                                    help="Include passed-strategy count in status-only output (requires --status-only).")
    smoke_files_parser.add_argument("--status-file", type=Path, default=None,
                                    help="Persist status output to file for CI (always written regardless of --quiet).")

    research_run_parser = subparsers.add_parser("research-run", help="Run preflight + eval + backtest as one orchestrated research run")
    research_run_parser.add_argument("strategy", type=Path, help="Path to strategy spec YAML or high-level entry YAML.")
    research_run_parser.add_argument("--start", required=True, type=date.fromisoformat, help="Start date (YYYY-MM-DD).")
    research_run_parser.add_argument("--end", required=True, type=date.fromisoformat, help="End date (YYYY-MM-DD).")
    research_run_parser.add_argument("--output-dir", type=Path, required=True, help="Output directory for all stage artifacts.")
    research_run_parser.add_argument("--db-url", help="Database URL. Defaults to QRE_MARKET_DB_URL or SR_MARKET_DB_URL.")
    research_run_parser.add_argument("--codes", nargs="*", default=None)
    research_run_parser.add_argument("--market-profile", type=Path, help="Optional market profile YAML.")
    research_run_parser.add_argument("--skip-preflight", action="store_true", help="Skip preflight stage.")
    research_run_parser.add_argument("--skip-eval", action="store_true", help="Skip evaluation stage.")
    research_run_parser.add_argument("--backtest-mode", choices=["batch", "shared"], default="batch", help="Backtest mode (default: batch).")
    research_run_parser.add_argument("--initial-cash", type=float, default=1_000_000, help="Initial cash for backtest (default: 1000000).")
    research_run_parser.add_argument("--min-factor-coverage", type=float, default=0.8)
    research_run_parser.add_argument("--group-by", nargs="*", default=None, help="Optional grouping columns for evaluation summaries.")
    research_run_parser.add_argument("--random-baseline-seed", type=int, default=None, help="Optional seed for deterministic random-baseline comparison.")
    research_run_parser.add_argument("--round-trip-cost-rate", type=float, default=None, help="Optional round-trip cost rate override.")
    research_run_parser.add_argument("--metadata-columns", nargs="*", default=None, help="Optional metadata columns for backtest outputs.")
    research_run_parser.add_argument("--window-size", type=int, default=None, help="Optional rolling window size for backtest.")
    research_run_parser.add_argument("--run-id", default=None, help="Optional run-level identifier (auto-generated if omitted).")

    gui_parser = subparsers.add_parser("gui", help="Launch the local browser backtest console")
    gui_parser.add_argument("--host", default="127.0.0.1", help="Host to bind the console server to.")
    gui_parser.add_argument("--port", type=int, default=8080, help="Port to bind the console server to.")
    gui_parser.add_argument("--debug", action="store_true", help="Run Flask in debug mode (not recommended for production).")

    return parser


def resolve_risk_controls(args: argparse.Namespace, spec: StrategySpec) -> dict[str, float | None]:
    return {
        "stop_loss_pct": args.stop_loss_pct if args.stop_loss_pct is not None else spec.stop_loss_pct,
        "take_profit_pct": args.take_profit_pct if args.take_profit_pct is not None else spec.take_profit_pct,
        "trailing_stop_pct": (
            args.trailing_stop_pct if args.trailing_stop_pct is not None else spec.trailing_stop_pct
        ),
    }


def resolve_weight_controls(args: argparse.Namespace, spec: StrategySpec) -> dict[str, str | None]:
    weight_model = args.weight_model if args.weight_model is not None else spec.weight_model
    return {
        "weight_model": weight_model or "equal_weight",
        "score_column": args.score_column if args.score_column is not None else spec.score_column,
        "volatility_column": (
            args.volatility_column if args.volatility_column is not None else spec.volatility_column
        ),
    }


def resolve_rebalance_controls(args: argparse.Namespace, spec: StrategySpec) -> dict[str, int | None]:
    return {
        "rebalance_interval_days": (
            args.rebalance_interval_days
            if args.rebalance_interval_days is not None
            else spec.rebalance_interval_days
        ),
    }


def resolve_round_trip_cost_rate(args: argparse.Namespace) -> float | None:
    if getattr(args, "round_trip_cost_rate", None) is not None:
        return args.round_trip_cost_rate
    market_profile_path = getattr(args, "market_profile", None)
    if market_profile_path is None:
        return None
    profile = load_market_profile(market_profile_path)
    if profile.slippage_model != "percent":
        raise ValueError(f"Unsupported slippage model for rough friction estimate: {profile.slippage_model}")
    buy_rate = profile.commission_rate + profile.transfer_fee_rate + profile.slippage_buy_rate
    sell_rate = profile.commission_rate + profile.transfer_fee_rate + profile.stamp_tax_sell + profile.slippage_sell_rate
    return buy_rate + sell_rate


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "profile":
        profile = load_market_profile(args.path)
        print(f"{profile.name}: {profile.description}")
        print(f"buy_lot={profile.buy_lot}")
        print(f"commission_rate={profile.commission_rate}")
        return 0

    if args.command == "report-files":
        try:
            manifest = ReportManifest.from_path(args.manifest)
            entries = manifest.files(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
                window_size=args.window_size,
            )
            paths = manifest.paths(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
                window_size=args.window_size,
            )

            missing_paths: list[Path] = []
            if args.check_exists:
                missing_paths = [path for path in paths if not path.exists()]

            content_issues: list = []
            if args.validate_contents:
                content_issues = manifest.validate_contents(
                    role=args.role,
                    symbol=args.symbol,
                    window=args.window,
                    group_by=args.group_by,
                    window_size=args.window_size,
                )

            no_matches = args.require_match and not entries

            if args.json:
                file_list: list[dict[str, str | None]] = []
                for entry in entries:
                    resolved_path = str(manifest.base_dir / entry.path)
                    item: dict[str, str | None] = {
                        "key": entry.key,
                        "path": resolved_path,
                        "filename": entry.filename,
                        "role": entry.role,
                    }
                    if entry.symbol is not None:
                        item["symbol"] = entry.symbol
                    if entry.window is not None:
                        item["window"] = entry.window
                    if entry.group_by is not None:
                        item["group_by"] = entry.group_by
                    if entry.window_size is not None:
                        item["window_size"] = entry.window_size
                    file_list.append(item)
                payload: dict[str, object] = {
                    "manifest_kind": manifest.kind,
                    "schema_version": manifest.schema_version,
                    "matched_files": len(entries),
                    "files": file_list,
                }
                print(json.dumps(payload, ensure_ascii=False))
                if missing_paths:
                    for path in missing_paths:
                        print(path, file=__import__("sys").stderr)
                    return 2
                if content_issues:
                    for issue in content_issues:
                        print(
                            f"{issue.key}\t{issue.code}\t{issue.path}\t{issue.message}",
                            file=__import__("sys").stderr,
                        )
                    return 2
                if no_matches:
                    print("no manifest entries matched filters", file=__import__("sys").stderr)
                    return 2
                return 0

            if missing_paths:
                for path in missing_paths:
                    print(path, file=__import__("sys").stderr)
                return 2
            if content_issues:
                for issue in content_issues:
                    print(
                        f"{issue.key}\t{issue.code}\t{issue.path}\t{issue.message}",
                        file=__import__("sys").stderr,
                    )
                return 2
            if no_matches:
                print("no manifest entries matched filters", file=__import__("sys").stderr)
                return 2
            if args.keys:
                for entry in entries:
                    print(entry.key)
            else:
                for path in paths:
                    print(path)
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2
        return 0

    if args.command == "report-audit":
        try:
            manifest = ReportManifest.from_path(args.manifest)
            entries = manifest.files(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
                window_size=args.window_size,
            )
            paths = manifest.paths(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
                window_size=args.window_size,
            )
            missing_paths = [path for path in paths if not path.exists()]
            issues = manifest.validate_contents(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
                window_size=args.window_size,
            )
            no_matches = args.require_match and not entries
            status = "failed" if missing_paths or issues or no_matches else "ok"

            if args.json:
                issue_list: list[dict[str, str]] = []
                for issue in issues:
                    issue_list.append({
                        "key": issue.key,
                        "code": issue.code,
                        "path": str(issue.path),
                        "message": issue.message,
                    })
                if no_matches:
                    issue_list.append({
                        "key": "manifest",
                        "code": "no_matches",
                        "path": str(args.manifest),
                        "message": "no manifest entries matched filters",
                    })
                payload = {
                    "manifest_kind": manifest.kind,
                    "schema_version": manifest.schema_version,
                    "matched_files": len(entries),
                    "missing_files": len(missing_paths),
                    "validation_issues": len(issues),
                    "status": status,
                    "issues": issue_list,
                }
                print(json.dumps(payload, ensure_ascii=False))
                if no_matches:
                    print("no manifest entries matched filters", file=__import__("sys").stderr)
                return 2 if status == "failed" else 0

            print(f"manifest_kind={manifest.kind}")
            print(f"matched_files={len(entries)}")
            print(f"missing_files={len(missing_paths)}")
            print(f"validation_issues={len(issues)}")
            print(f"status={status}")
            if no_matches:
                print("no manifest entries matched filters", file=__import__("sys").stderr)
            for issue in issues:
                print(
                    f"{issue.key}\t{issue.code}\t{issue.path}\t{issue.message}",
                    file=__import__("sys").stderr,
                )
            return 2 if status == "failed" else 0
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

    if args.command == "db-smoke":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            frame = store.load_daily_bars(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                limit=args.limit,
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"loaded_rows={len(frame)}")
        print(f"columns={','.join(frame.columns)}")
        if not frame.empty:
            print(f"date_min={frame['trade_date'].min().date()}")
            print(f"date_max={frame['trade_date'].max().date()}")
        return 0

    if args.command == "factor-smoke":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            request = FactorFieldRequest.from_target(args.logical_name, args.target)
            frame = store.load_factor_history(
                ts_codes=args.codes,
                field_requests=[request],
                start=args.start,
                end=args.end,
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"loaded_rows={len(frame)}")
        print(f"columns={','.join(frame.columns)}")
        if not frame.empty:
            print(f"date_min={frame['trade_date'].min().date()}")
            print(f"date_max={frame['trade_date'].max().date()}")
            print(f"non_null_{args.logical_name}={int(frame[args.logical_name].notna().sum())}")
        return 0

    if args.command == "benchmark-smoke":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            frame = store.load_benchmark_bars(
                table_name=args.table,
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                fields=[args.value_column],
                limit=args.limit,
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"loaded_rows={len(frame)}")
        print(f"columns={','.join(frame.columns)}")
        if not frame.empty:
            print(f"date_min={frame['trade_date'].min().date()}")
            print(f"date_max={frame['trade_date'].max().date()}")
            print(f"non_null_{args.value_column}={int(frame[args.value_column].notna().sum())}")
            returns = frame.sort_values(["ts_code", "trade_date"]).groupby("ts_code")[args.value_column].pct_change()
            print(f"return_observations={int(returns.notna().sum())}")
        return 0

    if args.command == "metadata-smoke":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            frame = store.load_security_metadata(ts_codes=args.codes)
            if args.limit is not None:
                frame = frame.head(args.limit)
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"loaded_rows={len(frame)}")
        print(f"columns={','.join(frame.columns)}")
        if not frame.empty:
            print(f"boards={','.join(sorted(frame['board'].dropna().astype(str).unique()))}")
            print(frame.to_csv(index=False).strip())
        return 0

    if args.command == "eval-smoke":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            request = FactorFieldRequest.from_target(args.logical_name, args.target)
            bars = store.load_daily_bars(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
            )
            factors = store.load_factor_history(
                ts_codes=args.codes,
                field_requests=[request],
                start=args.start,
                end=args.end,
            )
            frame = bars.merge(factors, on=["ts_code", "trade_date"], how="inner")
            result = EvaluationEngine().evaluate(
                frame,
                EvaluationRequest(
                    signal_expression=args.signal,
                    forward_horizons=args.horizons,
                    factor_columns=[args.logical_name],
                    round_trip_cost_rate=resolve_round_trip_cost_rate(args),
                ),
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"research_rows={len(frame)}")
        print(f"event_rows={len(result.events)}")
        if not result.summary.empty:
            print(result.summary.to_csv(index=False).strip())
        if not result.ic_summary.empty:
            print("ic_summary")
            print(result.ic_summary.to_csv(index=False).strip())
        return 0

    if args.command == "eval-config":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            spec = StrategySpec.from_yaml(args.strategy)
            frame = ResearchFrameAssembler(store).build(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                include_metadata=bool(args.group_by),
            )
            result = EvaluationEngine().evaluate(
                frame,
                EvaluationRequest(
                    signal_expression=spec.signal_expression,
                    forward_horizons=spec.forward_horizons,
                    factor_columns=[factor.logical_name for factor in spec.factor_fields],
                    quantiles=spec.quantiles,
                    round_trip_cost_rate=resolve_round_trip_cost_rate(args),
                    group_by=args.group_by,
                    random_baseline_seed=args.random_baseline_seed,
                ),
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"strategy={spec.name}")
        print(f"research_rows={len(frame)}")
        print(f"event_rows={len(result.events)}")
        if not result.summary.empty:
            print(result.summary.to_csv(index=False).strip())
        if not result.ic_summary.empty:
            print("ic_summary")
            print(result.ic_summary.to_csv(index=False).strip())
        if not result.quantile_summary.empty:
            print("quantile_summary")
            print(result.quantile_summary.to_csv(index=False).strip())
        if not result.group_summary.empty:
            print("group_summary")
            print(result.group_summary.to_csv(index=False).strip())
        if not result.random_baseline_summary.empty:
            print("random_baseline_summary")
            print(result.random_baseline_summary.to_csv(index=False).strip())
        if not result.factor_decay_summary.empty:
            print("factor_decay_summary")
            print(result.factor_decay_summary.to_csv(index=False).strip())
        if args.output_dir:
            write_evaluation_output(
                result=result,
                output_dir=args.output_dir,
                run_id=args.run_id,
                strategy_path=str(args.strategy),
                start=str(args.start),
                end=str(args.end),
                codes=args.codes,
                round_trip_cost_rate=args.round_trip_cost_rate,
                market_profile=str(args.market_profile) if args.market_profile else None,
                group_by=args.group_by,
                random_baseline_seed=args.random_baseline_seed,
            )
        return 0

    if args.command == "compile":
        try:
            raw = parse_high_level_entry(args.strategy)
            entry = compile_entry(raw)
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        # Print compilation summary
        print(f"strategy_id={entry.strategy_id}")
        print(f"name={entry.name}")
        print(f"family={entry.family}")
        print(f"direction={entry.direction}")
        if entry.version:
            print(f"version={entry.version}")
        print(f"compile_status={'ok' if entry.ok else 'error'}")
        print(f"factor_target_count={len(entry.factor_targets)}")
        for alias, target in entry.factor_targets.items():
            print(f"factor_target_{alias}={target}")
        if entry.signal_expression:
            print(f"signal_expression={entry.signal_expression}")
        if entry.exit_signal_expression:
            print(f"exit_signal_expression={entry.exit_signal_expression}")
        for issue in entry.issues:
            print(f"compile_issue_{issue.level}={issue.message}")

        # Write compiled low-level spec if output-dir provided
        if args.output_dir:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            spec_dict = compile_to_strategy_spec_dict(entry)
            compiled_path = args.output_dir / "compiled_strategy_spec.json"
            compiled_path.write_text(
                json.dumps(spec_dict, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )
            print(f"compiled_spec={compiled_path}")

        # Optionally run preflight
        if args.preflight:
            if not args.start or not args.end:
                print("--start and --end are required with --preflight", file=__import__("sys").stderr)
                return 2
            spec_dict = compile_to_strategy_spec_dict(entry)
            spec = StrategySpec.from_mapping(spec_dict)
            try:
                settings = (
                    DatabaseSettings(market_db_url=args.db_url)
                    if args.db_url
                    else DatabaseSettings.from_env()
                )
                store = PostgresDataStore(settings)
                store.ping()
            except Exception as exc:
                print(str(exc), file=__import__("sys").stderr)
                return 2
            preflight_req = PreflightRequest(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                min_factor_coverage=args.min_factor_coverage,
                exclude_st=spec.exclude_st,
                exclude_suspended=spec.exclude_suspended,
                exclude_risk_warning=spec.exclude_risk_warning,
                min_listing_days=spec.min_listing_days,
                min_amount=spec.min_amount,
            )
            report = PreflightRunner(store).run(preflight_req)
            print(f"preflight_status={report.status}")
            print(f"market_rows={report.market_rows}")
            print(f"loaded_symbols={len(report.loaded_symbols)}")
            for check in report.checks:
                print(f"check_{check.name}={check.status}")
            missing_factors = extract_missing_factors(report, spec, preflight_req)
            missing_count = len(missing_factors)
            print(f"missing_factor_count={missing_count}")
            if missing_count == 0:
                print("missing_factor_status=ok")
            else:
                print("missing_factor_status=pending")
                for mf in missing_factors:
                    print(f"missing_factor={mf.alias} required_table={mf.expected_table} required_column={mf.expected_column}")
            if args.output_dir:
                emit_missing_factor_requests(missing_factors, args.output_dir)

        if not entry.ok:
            return 2
        return 0

    if args.command == "preflight":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            spec = StrategySpec.from_yaml(args.strategy)
            preflight_req = PreflightRequest(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                min_factor_coverage=args.min_factor_coverage,
                exclude_st=spec.exclude_st,
                exclude_suspended=spec.exclude_suspended,
                exclude_risk_warning=spec.exclude_risk_warning,
                min_listing_days=spec.min_listing_days,
                min_amount=spec.min_amount,
                benchmark_table=args.benchmark_table,
                benchmark_code=args.benchmark_code,
                benchmark_value_column=args.benchmark_value_column,
            )
            report = PreflightRunner(store).run(preflight_req)
            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                payload = report.to_dict()
                payload["run_id"] = args.run_id
                args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

            missing_factors = extract_missing_factors(report, spec, preflight_req)
            if args.output_dir:
                request_path = emit_missing_factor_requests(missing_factors, args.output_dir)
                print(f"missing_factor_requests={request_path}")
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"status={report.status}")
        print(f"market_rows={report.market_rows}")
        print(f"latest_market_date={report.latest_market_date}")
        print(f"loaded_symbols={len(report.loaded_symbols)}")
        print(f"missing_symbols={','.join(report.missing_symbols)}")
        for logical_name, coverage in report.factor_coverages.items():
            print(f"factor_{logical_name}_non_null_rows={coverage.non_null_rows}")
            print(f"factor_{logical_name}_coverage_ratio={coverage.coverage_ratio}")
        print(f"joined_rows={report.joined_rows}")
        print(f"join_coverage_ratio={report.join_coverage_ratio}")
        print(f"metadata_rows={report.metadata_rows}")
        print(f"universe_total_symbols={report.universe_total_symbols}")
        print(f"universe_eligible_symbols={len(report.universe_eligible_symbols)}")
        for reason, symbols in report.universe_excluded_symbols.items():
            print(f"universe_excluded_{reason}={len(symbols)}")
        if args.benchmark_table or args.benchmark_code:
            print(f"benchmark_rows={report.benchmark_rows}")
            print(f"benchmark_non_null_rows={report.benchmark_non_null_rows}")
        for check in report.checks:
            print(f"check_{check.name}={check.status}")
        missing_count = len(missing_factors)
        print(f"missing_factor_count={missing_count}")
        if missing_count == 0:
            print("missing_factor_status=ok")
        else:
            print("missing_factor_status=pending")
            for mf in missing_factors:
                print(f"missing_factor={mf.alias} required_table={mf.expected_table} required_column={mf.expected_column}")
        return 2 if report.status == "error" else 0

    if args.command == "backtest-single":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            spec = StrategySpec.from_yaml(args.strategy)
            frame = ResearchFrameAssembler(store).build(
                ts_codes=[args.symbol],
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
            )
            market_profile = load_market_profile(args.market_profile) if args.market_profile else AShareMarketProfile()
            result = SingleSymbolBacktestEngine(market_profile).run(
                frame,
                SingleSymbolBacktestRequest(
                    symbol=args.symbol,
                    initial_cash=args.initial_cash,
                    entry_signal=spec.signal_expression,
                    exit_signal=spec.exit_signal_expression,
                    holding_days=spec.holding_days,
                ),
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"strategy={spec.name}")
        print(f"symbol={args.symbol}")
        print(f"orders={len(result.orders)}")
        print(f"trades={len(result.trades)}")
        for key, value in result.summary.items():
            print(f"{key}={value}")
        if args.output_dir:
            run_request = {
                "command": "backtest-single",
                "strategy_path": str(args.strategy),
                "request": {
                    "symbol": args.symbol,
                    "initial_cash": args.initial_cash,
                    "entry_signal": spec.signal_expression,
                    "exit_signal": spec.exit_signal_expression,
                    "holding_days": spec.holding_days,
                    "start": str(args.start),
                    "end": str(args.end),
                    "market_profile": str(args.market_profile) if args.market_profile else "built-in",
                },
            }
            paths = write_single_symbol_result(result, args.output_dir, run_request=run_request, run_id=args.run_id)
            for key, path in paths.items():
                print(f"{key}_path={path}")
        return 0

    if args.command == "backtest-batch":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            spec = StrategySpec.from_yaml(args.strategy)
            frame = ResearchFrameAssembler(store).build(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                include_metadata=True,
            )
            market_profile = load_market_profile(args.market_profile) if args.market_profile else AShareMarketProfile()
            result = BatchBacktestEngine(market_profile).run(
                frame,
                BatchBacktestRequest(
                    symbols=args.codes,
                    initial_cash_per_symbol=args.initial_cash,
                    entry_signal=spec.signal_expression,
                    exit_signal=spec.exit_signal_expression,
                    holding_days=spec.holding_days,
                    summary_metadata_columns=args.group_by,
                ),
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        if args.benchmark_table or args.benchmark_code:
            if not args.benchmark_table or not args.benchmark_code:
                print("--benchmark-table and --benchmark-code must be provided together", file=__import__("sys").stderr)
                return 2
            benchmark_frame = store.load_benchmark_bars(
                table_name=args.benchmark_table,
                ts_codes=[args.benchmark_code],
                start=args.start,
                end=args.end,
                fields=[args.benchmark_value_column],
            )
            full_market_eq = build_full_market_equity_curve(result.results, engine_mode="batch")
            benchmark_summary = summarize_benchmark_relative_performance(
                full_market_eq,
                benchmark_frame,
                benchmark_value_column=args.benchmark_value_column,
            )
            result.summary_metrics["benchmark_code"] = args.benchmark_code
            for key, value in benchmark_summary.items():
                result.summary_metrics[f"benchmark_{key}"] = value

        print(f"strategy={spec.name}")
        print(f"symbols={len(result.symbols)}")
        for key, value in result.summary_metrics.items():
            print(f"{key}={value}")
        for group_column in args.group_by or []:
            print(f"group_by={group_column}")
            print(summarize_batch_by(result.summary, group_column).to_csv(index=False).strip())
        print(result.summary.to_csv(index=False).strip())
        if args.print_summary_md:
            report_paths = {
                "summary": Path("summary.csv"),
                "summary_metrics": Path("summary_metrics.json"),
                "summary_markdown": Path("summary.md"),
                "report_manifest": Path("report_manifest.json"),
                "window_summary_M": Path("window_summary_M.csv"),
                "window_summary_Q": Path("window_summary_Q.csv"),
                "window_summary_Y": Path("window_summary_Y.csv"),
            }
            for group_column in args.group_by or []:
                report_paths[f"group_by_{group_column}"] = Path(f"group_by_{group_column}.csv")
                report_paths[f"group_by_{group_column}_ranked_symbols"] = Path(
                    f"group_by_{group_column}_ranked_symbols.csv"
                )
                for window in ("M", "Q", "Y"):
                    report_paths[f"window_summary_{window}_by_{group_column}"] = Path(
                        f"window_summary_{window}_by_{group_column}.csv"
                    )
                    report_paths[f"window_summary_{window}_by_{group_column}_ranked_symbols"] = Path(
                        f"window_summary_{window}_by_{group_column}_ranked_symbols.csv"
                    )
            print(batch_summary_markdown(result.summary_metrics, report_paths, result.summary).strip())
        if args.output_dir:
            run_request = {
                "command": "backtest-batch",
                "strategy_path": str(args.strategy),
                "request": {
                    "symbols": args.codes,
                    "initial_cash_per_symbol": args.initial_cash,
                    "entry_signal": spec.signal_expression,
                    "exit_signal": spec.exit_signal_expression,
                    "holding_days": spec.holding_days,
                    "start": str(args.start),
                    "end": str(args.end),
                    "market_profile": str(args.market_profile) if args.market_profile else "built-in",
                    "group_by": args.group_by,
                    "group_rank_top_n": args.group_rank_top_n,
                },
            }
            paths = write_batch_result(
                result,
                args.output_dir,
                group_by=args.group_by,
                group_rank_top_n=args.group_rank_top_n,
                run_request=run_request,
                run_id=args.run_id,
            )
            for key, path in paths.items():
                print(f"{key}_path={path}")
        return 0

    if args.command == "backtest-shared":
        try:
            settings = (
                DatabaseSettings(market_db_url=args.db_url)
                if args.db_url
                else DatabaseSettings.from_env()
            )
            store = PostgresDataStore(settings)
            store.ping()
            spec = StrategySpec.from_yaml(args.strategy)
            frame = ResearchFrameAssembler(store).build(
                ts_codes=args.codes,
                start=args.start,
                end=args.end,
                market_fields=spec.market_fields,
                factor_fields=spec.factor_fields,
                include_metadata=True,
            )
            market_profile = load_market_profile(args.market_profile) if args.market_profile else AShareMarketProfile()
            risk_controls = resolve_risk_controls(args, spec)
            weight_controls = resolve_weight_controls(args, spec)
            rebalance_controls = resolve_rebalance_controls(args, spec)
            metadata_columns = args.metadata_columns
            if args.group_by:
                extra = [col for col in args.group_by if col not in (metadata_columns or [])]
                metadata_columns = (metadata_columns or []) + extra
            result = SharedCashBacktestEngine(market_profile).run(
                frame,
                SharedCashBacktestRequest(
                    symbols=args.codes,
                    initial_cash=args.initial_cash,
                    entry_signal=spec.signal_expression,
                    exit_signal=spec.exit_signal_expression,
                    holding_days=spec.holding_days,
                    max_positions=args.max_positions,
                    **weight_controls,
                    **risk_controls,
                    **rebalance_controls,
                    metadata_columns=metadata_columns if metadata_columns else None,
                ),
            )
            if args.benchmark_table or args.benchmark_code:
                if not args.benchmark_table or not args.benchmark_code:
                    raise ValueError("--benchmark-table and --benchmark-code must be provided together")
                benchmark_frame = store.load_benchmark_bars(
                    table_name=args.benchmark_table,
                    ts_codes=[args.benchmark_code],
                    start=args.start,
                    end=args.end,
                    fields=[args.benchmark_value_column],
                )
                benchmark_summary = summarize_benchmark_relative_performance(
                    result.equity_curve,
                    benchmark_frame,
                    benchmark_value_column=args.benchmark_value_column,
                )
                result.summary["benchmark_code"] = args.benchmark_code
                for key, value in benchmark_summary.items():
                    result.summary[f"benchmark_{key}"] = value
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"strategy={spec.name}")
        print(f"symbols={0 if args.codes is None else len(args.codes)}")
        print(f"orders={len(result.orders)}")
        print(f"trades={len(result.trades)}")
        for key, value in result.summary.items():
            print(f"{key}={value}")
        for group_column in args.group_by or []:
            print(f"orders_by_{group_column}")
            print(summarize_shared_orders_by(result.orders, group_column).to_csv(index=False).strip())
            print(f"trades_by_{group_column}")
            print(summarize_shared_trades_by(result.trades, group_column).to_csv(index=False).strip())
            print(f"failed_orders_by_{group_column}")
            print(summarize_shared_failed_orders_by(result.failed_orders, group_column).to_csv(index=False).strip())
        if args.print_summary_md:
            print(shared_summary_markdown(result.summary).strip())
        if args.output_dir:
            run_request = {
                "command": "backtest-shared",
                "strategy_path": str(args.strategy),
                "request": {
                    "symbols": args.codes,
                    "initial_cash": args.initial_cash,
                    "entry_signal": spec.signal_expression,
                    "exit_signal": spec.exit_signal_expression,
                    "holding_days": spec.holding_days,
                    "max_positions": args.max_positions,
                    "weight_model": weight_controls["weight_model"],
                    "score_column": weight_controls["score_column"],
                    "volatility_column": weight_controls["volatility_column"],
                    "stop_loss_pct": risk_controls["stop_loss_pct"],
                    "take_profit_pct": risk_controls["take_profit_pct"],
                    "trailing_stop_pct": risk_controls["trailing_stop_pct"],
                    "rebalance_interval_days": rebalance_controls["rebalance_interval_days"],
                    "start": str(args.start),
                    "end": str(args.end),
                    "market_profile": str(args.market_profile) if args.market_profile else "built-in",
                    "benchmark_table": args.benchmark_table,
                    "benchmark_code": args.benchmark_code,
                    "benchmark_value_column": args.benchmark_value_column,
                    "metadata_columns": args.metadata_columns,
                    "group_by": args.group_by,
                },
            }
            paths = write_shared_cash_result(result, args.output_dir, run_request=run_request, group_by=args.group_by, run_id=args.run_id)
            for key, path in paths.items():
                print(f"{key}_path={path}")
        return 0

    if args.command == "strategy-smoke":
        import os

        # Resolve strategy paths
        if args.strategies:
            strategy_paths = [Path(p) for p in args.strategies]
        else:
            # Default: three canonical strategy entries relative to repo root
            repo_root = Path(__file__).resolve().parent.parent.parent.parent
            entry_dir = repo_root / "strategies" / "high_level"
            strategy_paths = [
                entry_dir / "rsi2_oversold_reversal_entry.yaml",
                entry_dir / "ema200_bollinger_reversal_entry.yaml",
                entry_dir / "macd_zero_cross_momentum_entry.yaml",
            ]

        # Convert start/end to strings for the runner
        preflight_start = str(args.start) if args.start else None
        preflight_end = str(args.end) if args.end else None

        try:
            summary = run_strategy_smoke(
                strategy_paths=strategy_paths,
                output_dir=args.output_dir,
                run_preflight=not args.no_preflight,
                run_backtest=not args.no_backtest,
                preflight_start=preflight_start,
                preflight_end=preflight_end,
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        # Print summary to stdout
        db_status = "configured" if summary.environment.get("db_configured") else "not configured"
        print(f"run_id={summary.run_id}")
        print(f"db_environment={db_status}")
        print(f"overall_status={summary.overall_status}")
        for s in summary.strategies:
            print(f"strategy={s.strategy_id} compile={s.compile} preflight={s.preflight} "
                  f"missing_factor={s.missing_factor} backtest_smoke={s.backtest_smoke}")
            if s.reason:
                print(f"  reason: {s.reason}")
            if s.artifacts:
                print(f"  artifact_count={len(s.artifacts)}")
                for key, path in sorted(s.artifacts.items()):
                    print(f"  artifact.{key}={path}")
            if s.durations_s:
                dur_parts = [f"{k}={v:.3f}s" for k, v in sorted(s.durations_s.items())]
                print(f"  durations: {', '.join(dur_parts)}")
        summary_path = args.output_dir / "smoke_summary.json"
        print(f"smoke_summary={summary_path}")
        manifest_path = args.output_dir / "smoke_report_manifest.json"
        print(f"smoke_report_manifest={manifest_path}")

        return 2 if summary.overall_status == "fail" else 0

    if args.command == "smoke-files":
        import sys as _sys

        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        default_root = repo_root / "outputs" / "strategy-entry-smoke"

        if args.output_dir:
            output_dir = args.output_dir
        else:
            candidates = sorted(
                [p for p in default_root.glob("*/smoke_summary.json") if p.is_file()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                print(f"No smoke runs found under {default_root}", file=_sys.stderr)
                return 2
            output_dir = candidates[0].parent

        summary_path = output_dir / "smoke_summary.json"
        manifest_path = output_dir / "smoke_report_manifest.json"

        if not summary_path.exists():
            print(f"smoke_summary.json not found at {summary_path}", file=_sys.stderr)
            return 2

        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"Failed to read smoke_summary.json: {exc}", file=_sys.stderr)
            return 2

        # Build artifact role counts from manifest (preferred) or summary
        artifact_roles: dict[str, int] = {}
        source_mode = "artifacts_fallback"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for f in manifest.get("files", []):
                    role = f.get("role", "")
                    if args.strategy and f.get("symbol") != args.strategy:
                        continue
                    if args.role and role != args.role:
                        continue
                    artifact_roles[role] = artifact_roles.get(role, 0) + 1
                if artifact_roles:
                    source_mode = "manifest"
            except (json.JSONDecodeError, OSError):
                pass  # manifest read failed; fall through to summary
        if not artifact_roles:
            for s in summary.get("strategies", []):
                if args.strategy and s["strategy_id"] != args.strategy:
                    continue
                for role in sorted(s.get("artifacts", {})):
                    if args.role and role != args.role:
                        continue
                    artifact_roles[role] = artifact_roles.get(role, 0) + 1

        # Filter strategies (deterministic ordering by strategy_id)
        strategies = sorted(
            summary.get("strategies", []),
            key=lambda s: s.get("strategy_id", ""),
        )
        if args.strategy:
            strategies = [s for s in strategies if s["strategy_id"] == args.strategy]

        # Strict selector no-match checks for --require-match
        require_match_fail = False
        if args.require_match:
            if args.strategy and not strategies:
                print(f"No matching strategy: {args.strategy}", file=_sys.stderr)
                require_match_fail = True
            if args.role and args.role not in artifact_roles:
                print(f"No matching role: {args.role}", file=_sys.stderr)
                require_match_fail = True

        # Collect referenced artifact paths for --check-exists
        missing_artifacts: list[str] = []
        if args.check_exists:
            artifact_paths: set[str] = set()
            if manifest_path.exists():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    for f in manifest.get("files", []):
                        if args.strategy and f.get("symbol") != args.strategy:
                            continue
                        if args.role and f.get("role") != args.role:
                            continue
                        path = f.get("path", "")
                        if path:
                            artifact_paths.add(path)
                except (json.JSONDecodeError, OSError):
                    pass
            if not artifact_paths:
                for s in strategies:
                    for rel_path in s.get("artifacts", {}).values():
                        artifact_paths.add(rel_path)
            for rel_path in sorted(artifact_paths):
                if not (output_dir / rel_path).is_file():
                    missing_artifacts.append(rel_path)

            if missing_artifacts and not args.json:
                for rel_path in missing_artifacts:
                    print(f"Missing artifact: {rel_path}", file=_sys.stderr)

        # --list-missing requires --check-exists
        if args.list_missing and not args.check_exists:
            print("--list-missing requires --check-exists", file=_sys.stderr)
            return 2

        # --status-format requires --status-only
        if args.status_format and not args.status_only:
            print("--status-format requires --status-only", file=_sys.stderr)
            return 2

        # --status-reason requires --status-only
        if args.status_reason and not args.status_only:
            print("--status-reason requires --status-only", file=_sys.stderr)
            return 2

        # --status-code requires --status-only
        if args.status_code and not args.status_only:
            print("--status-code requires --status-only", file=_sys.stderr)
            return 2

        # --status-meta requires --status-only
        if args.status_meta and not args.status_only:
            print("--status-meta requires --status-only", file=_sys.stderr)
            return 2

        # --status-summary requires --status-only
        if args.status_summary and not args.status_only:
            print("--status-summary requires --status-only", file=_sys.stderr)
            return 2

        # --status-fail-key requires --status-only
        if args.status_fail_key and not args.status_only:
            print("--status-fail-key requires --status-only", file=_sys.stderr)
            return 2

        # --status-fail-stage requires --status-only
        if args.status_fail_stage and not args.status_only:
            print("--status-fail-stage requires --status-only", file=_sys.stderr)
            return 2

        # --status-timestamp requires --status-only
        if args.status_timestamp and not args.status_only:
            print("--status-timestamp requires --status-only", file=_sys.stderr)
            return 2

        # --status-output-dir requires --status-only
        if args.status_output_dir and not args.status_only:
            print("--status-output-dir requires --status-only", file=_sys.stderr)
            return 2

        # --status-manifest-path requires --status-only
        if args.status_manifest_path and not args.status_only:
            print("--status-manifest-path requires --status-only", file=_sys.stderr)
            return 2

        # --status-manifest-exists requires --status-only
        if args.status_manifest_exists and not args.status_only:
            print("--status-manifest-exists requires --status-only", file=_sys.stderr)
            return 2

        # --status-artifact-count requires --status-only
        if args.status_artifact_count and not args.status_only:
            print("--status-artifact-count requires --status-only", file=_sys.stderr)
            return 2

        # --status-strategy-count requires --status-only
        if args.status_strategy_count and not args.status_only:
            print("--status-strategy-count requires --status-only", file=_sys.stderr)
            return 2

        # --status-fail-count requires --status-only
        if args.status_fail_count and not args.status_only:
            print("--status-fail-count requires --status-only", file=_sys.stderr)
            return 2

        # --status-skip-count requires --status-only
        if args.status_skip_count and not args.status_only:
            print("--status-skip-count requires --status-only", file=_sys.stderr)
            return 2

        # --status-pass-count requires --status-only
        if args.status_pass_count and not args.status_only:
            print("--status-pass-count requires --status-only", file=_sys.stderr)
            return 2

        status_code = 0 if summary.get("overall_status") == "ok" else 1

        # Compute strategy-count summary for --status-summary
        summary_total = len(strategies)
        summary_pass = 0
        summary_fail = 0
        summary_skip = 0
        for s in strategies:
            stages = [s.get(k, "unknown") for k in ("compile", "preflight", "missing_factor", "backtest_smoke")]
            if any(v not in ("pass", "skip", "unknown") for v in stages):
                summary_fail += 1
            elif all(v == "skip" for v in stages):
                summary_skip += 1
            else:
                summary_pass += 1

        # Derive failure reason from first failing strategy stage
        status_reason = ""
        if args.status_reason and summary.get("overall_status") == "fail":
            for s in summary.get("strategies", []):
                for stage in ("compile", "preflight", "missing_factor", "backtest_smoke"):
                    status_val = s.get(stage, "unknown")
                    if status_val not in ("pass", "skip"):
                        status_reason = f"{s['strategy_id']}: {stage}={status_val}"
                        break
                if status_reason:
                    break

        # Derive first failing strategy id for --status-fail-key
        fail_key = None
        if args.status_fail_key:
            for s in summary.get("strategies", []):
                stages = [s.get(k, "unknown") for k in ("compile", "preflight", "missing_factor", "backtest_smoke")]
                if any(v not in ("pass", "skip") for v in stages):
                    fail_key = s.get("strategy_id")
                    break

        # Derive first failing stage for --status-fail-stage
        fail_stage = None
        if args.status_fail_stage:
            for s in summary.get("strategies", []):
                for stage in ("compile", "preflight", "missing_factor", "backtest_smoke"):
                    status_val = s.get(stage, "unknown")
                    if status_val not in ("pass", "skip"):
                        fail_stage = stage
                        break
                if fail_stage:
                    break

        # Derive run timestamp for --status-timestamp
        timestamp = summary.get("generated_at") or ""

        # Derive output_dir for --status-output-dir
        output_dir_str = str(output_dir.resolve())

        # Derive manifest_path for --status-manifest-path
        manifest_path_str = str(manifest_path)

        # Derive manifest_exists for --status-manifest-exists
        manifest_exists = manifest_path.is_file()

        # Derive artifact_total for --status-artifact-count
        artifact_total = sum(artifact_roles.values())

        if args.status_only and args.status_format == "json":
            use_json = True
        elif args.status_only and args.status_format == "text":
            use_json = False
        else:
            use_json = args.json

        if use_json:
            if args.status_only:
                payload = {
                    "run_id": summary["run_id"],
                    "overall_status": summary["overall_status"],
                }
                if args.status_reason:
                    payload["reason"] = status_reason
                if args.status_code:
                    payload["status_code"] = status_code
                if args.status_meta:
                    payload["source_mode"] = source_mode
                if args.status_summary:
                    payload["strategy_total"] = summary_total
                    payload["strategy_pass"] = summary_pass
                    payload["strategy_fail"] = summary_fail
                    payload["strategy_skip"] = summary_skip
                if args.status_fail_key:
                    payload["fail_key"] = fail_key
                if args.status_fail_stage:
                    payload["fail_stage"] = fail_stage
                if args.status_timestamp:
                    payload["timestamp"] = timestamp or None
                if args.status_output_dir:
                    payload["output_dir"] = output_dir_str
                if args.status_manifest_path:
                    payload["manifest_path"] = manifest_path_str
                if args.status_manifest_exists:
                    payload["manifest_exists"] = manifest_exists
                if args.status_artifact_count:
                    payload["artifact_count"] = artifact_total
                if args.status_strategy_count:
                    payload["strategy_count"] = len(strategies)
                if args.status_fail_count:
                    payload["fail_count"] = summary_fail
                if args.status_skip_count:
                    payload["skip_count"] = summary_skip
                if args.status_pass_count:
                    payload["pass_count"] = summary_pass
            else:
                payload = {
                    "run_id": summary["run_id"],
                    "overall_status": summary["overall_status"],
                    "resolved_output_dir": str(output_dir.resolve()),
                    "source_mode": source_mode,
                    "strategy_count": len(strategies),
                    "artifact_role_counts": artifact_roles,
                }
            if not args.status_only:
                if args.details:
                    payload["strategies"] = [
                        {
                            "strategy_id": s.get("strategy_id", ""),
                            "compile": s.get("compile", "unknown"),
                            "preflight": s.get("preflight", "unknown"),
                            "missing_factor": s.get("missing_factor", "unknown"),
                            "backtest_smoke": s.get("backtest_smoke", "unknown"),
                            "artifacts": sorted(s.get("artifacts", {}).keys()),
                        }
                        for s in strategies
                    ]
                if args.strategy and strategies:
                    s = strategies[0]
                    payload["strategy"] = {
                        "strategy_id": s["strategy_id"],
                        "compile": s["compile"],
                        "preflight": s["preflight"],
                        "missing_factor": s["missing_factor"],
                        "backtest_smoke": s["backtest_smoke"],
                    }
                if args.check_exists:
                    payload["missing_artifact_count"] = len(missing_artifacts)
                    payload["missing_artifacts"] = missing_artifacts
            json_str = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
            if not args.quiet:
                print(json_str)
            if args.output_file:
                try:
                    args.output_file.parent.mkdir(parents=True, exist_ok=True)
                    args.output_file.write_text(json_str + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write output file {args.output_file}: {exc}", file=_sys.stderr)
                    return 2
            if args.status_file:
                try:
                    args.status_file.parent.mkdir(parents=True, exist_ok=True)
                    args.status_file.write_text(json_str + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write status file {args.status_file}: {exc}", file=_sys.stderr)
                    return 2
            if args.list_missing and missing_artifacts and not args.quiet:
                for rel_path in missing_artifacts:
                    print(rel_path)
            if args.check_exists and missing_artifacts:
                return 2
            if require_match_fail:
                return 2
            return 2 if summary["overall_status"] == "fail" else 0

        # Default text output
        if args.status_only:
            if args.status_code:
                text_status = str(status_code)
            else:
                text_status = summary["overall_status"]
            if args.status_reason:
                text_status = f"{text_status}\t{status_reason}"
            if args.status_meta:
                text_status = f"{text_status}\trun_id={summary['run_id']}\tsource_mode={source_mode}"
            if args.status_summary:
                text_status = f"{text_status}\ttotal={summary_total}\tpass={summary_pass}\tfail={summary_fail}\tskip={summary_skip}"
            if args.status_fail_key:
                text_status = f"{text_status}\tfail_key={fail_key or ''}"
            if args.status_fail_stage:
                text_status = f"{text_status}\tfail_stage={fail_stage or ''}"
            if args.status_timestamp:
                text_status = f"{text_status}\ttimestamp={timestamp}"
            if args.status_output_dir:
                text_status = f"{text_status}\toutput_dir={output_dir_str}"
            if args.status_manifest_path:
                text_status = f"{text_status}\tmanifest_path={manifest_path_str}"
            if args.status_manifest_exists:
                text_status = f"{text_status}\tmanifest_exists={'true' if manifest_exists else 'false'}"
            if args.status_artifact_count:
                text_status = f"{text_status}\tartifact_count={artifact_total}"
            if args.status_strategy_count:
                text_status = f"{text_status}\tstrategy_count={len(strategies)}"
            if args.status_fail_count:
                text_status = f"{text_status}\tfail_count={summary_fail}"
            if args.status_skip_count:
                text_status = f"{text_status}\tskip_count={summary_skip}"
            if args.status_pass_count:
                text_status = f"{text_status}\tpass_count={summary_pass}"
            if not args.quiet:
                print(text_status)
            if args.output_file:
                try:
                    args.output_file.parent.mkdir(parents=True, exist_ok=True)
                    args.output_file.write_text(text_status + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write output file {args.output_file}: {exc}", file=_sys.stderr)
                    return 2
            if args.status_file:
                try:
                    args.status_file.parent.mkdir(parents=True, exist_ok=True)
                    args.status_file.write_text(text_status + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write status file {args.status_file}: {exc}", file=_sys.stderr)
                    return 2
        else:
            lines: list[str] = []
            lines.append(f"run_id={summary['run_id']}")
            lines.append(f"resolved_output_dir={output_dir.resolve()}")
            lines.append(f"source_mode={source_mode}")
            lines.append(f"overall_status={summary['overall_status']}")
            lines.append(f"strategy_count={len(strategies)}")
            for s in strategies:
                lines.append(f"strategy={s['strategy_id']} compile={s['compile']} "
                             f"preflight={s['preflight']} missing_factor={s['missing_factor']} "
                             f"backtest_smoke={s['backtest_smoke']}")
            if args.details:
                for s in strategies:
                    lines.append(f"  strategy_id={s['strategy_id']}")
                    lines.append(f"    compile={s['compile']}")
                    lines.append(f"    preflight={s['preflight']}")
                    lines.append(f"    missing_factor={s['missing_factor']}")
                    lines.append(f"    backtest_smoke={s['backtest_smoke']}")
                    artifact_keys = sorted(s.get("artifacts", {}).keys())
                    lines.append(f"    artifacts={artifact_keys}")
            if artifact_roles:
                lines.append("artifact_role_summary:")
                for role, count in sorted(artifact_roles.items()):
                    lines.append(f"  {role}: {count}")
            text_out = "\n".join(lines)
            if not args.quiet:
                print(text_out)
            if args.output_file:
                try:
                    args.output_file.parent.mkdir(parents=True, exist_ok=True)
                    args.output_file.write_text(text_out + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write output file {args.output_file}: {exc}", file=_sys.stderr)
                    return 2
            if args.status_file:
                try:
                    args.status_file.parent.mkdir(parents=True, exist_ok=True)
                    args.status_file.write_text(text_out + "\n", encoding="utf-8")
                except OSError as exc:
                    print(f"Failed to write status file {args.status_file}: {exc}", file=_sys.stderr)
                    return 2

        if args.list_missing and missing_artifacts and not args.quiet:
            for rel_path in missing_artifacts:
                print(rel_path)
        if args.check_exists and missing_artifacts:
            return 2
        if require_match_fail:
            return 2
        return 2 if summary["overall_status"] == "fail" else 0

    if args.command == "research-run":
        try:
            request = ResearchRunRequest(
                strategy_path=args.strategy,
                start=args.start,
                end=args.end,
                output_dir=args.output_dir,
                run_id=args.run_id,
                db_url=args.db_url,
                codes=args.codes,
                market_profile_path=args.market_profile,
                skip_preflight=args.skip_preflight,
                skip_eval=args.skip_eval,
                backtest_mode=args.backtest_mode,
                initial_cash=args.initial_cash,
                min_factor_coverage=args.min_factor_coverage,
                group_by=args.group_by,
                random_baseline_seed=args.random_baseline_seed,
                round_trip_cost_rate=args.round_trip_cost_rate,
                metadata_columns=args.metadata_columns,
                window_size=args.window_size,
            )
            result = run_research_run(request)
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

        print(f"run_id={result.run_id}")
        print(f"preflight_status={result.preflight_status}")
        print(f"eval_status={result.eval_status}")
        print(f"backtest_status={result.backtest_status}")
        if result.manifest_path:
            print(f"research_manifest={result.manifest_path}")
        if result.report_manifest_path:
            print(f"report_manifest={result.report_manifest_path}")
        if result.error_message:
            print(f"error={result.error_message}", file=__import__("sys").stderr)
            return 2
        if result.backtest_status == "error":
            return 2
        for key, path in result.preflight_paths.items():
            print(f"preflight_{key}={path}")
        for key, path in result.eval_paths.items():
            print(f"eval_{key}={path}")
        for key, path in result.backtest_paths.items():
            print(f"backtest_{key}={path}")
        return 0

    if args.command == "gui":
        from quant_research_engine.gui.app import launch_gui

        launch_gui(host=args.host, port=args.port, debug=args.debug)
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
