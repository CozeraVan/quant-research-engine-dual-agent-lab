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
from quant_research_engine.portfolio.analytics import summarize_batch_by
from quant_research_engine.portfolio.benchmark import summarize_benchmark_relative_performance
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
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
from quant_research_engine.strategies.spec import StrategySpec


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
    batch_parser.add_argument("--print-summary-md", action="store_true", help="Print a human-readable Markdown summary to stdout.")
    batch_parser.add_argument("--output-dir", type=Path, help="Optional directory for batch summary and per-symbol files.")

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
    shared_parser.add_argument("--print-summary-md", action="store_true", help="Print a human-readable Markdown summary to stdout.")
    shared_parser.add_argument("--output-dir", type=Path, help="Optional directory for portfolio result files.")

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


def _eval_manifest_role(key: str) -> str:
    if key == "summary":
        return "evaluation_summary"
    if key == "group_summary":
        return "evaluation_group_summary"
    if key == "random_baseline_summary":
        return "random_baseline_summary"
    if key == "run_manifest":
        return "run_manifest"
    return key


def _write_evaluation_output(
    *,
    result: EvaluationResult,
    output_dir: Path,
    args: argparse.Namespace,
    strategy_path: str,
) -> None:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    artifact_paths: dict[str, Path] = {}

    events_path = directory / "events.csv"
    result.events.to_csv(events_path, index=False)
    artifact_paths["events"] = events_path

    if not result.summary.empty:
        p = directory / "summary.csv"
        result.summary.to_csv(p, index=False)
        artifact_paths["summary"] = p

    if not result.ic_summary.empty:
        p = directory / "ic_summary.csv"
        result.ic_summary.to_csv(p, index=False)
        artifact_paths["ic_summary"] = p

    if not result.quantile_summary.empty:
        p = directory / "quantile_summary.csv"
        result.quantile_summary.to_csv(p, index=False)
        artifact_paths["quantile_summary"] = p

    if not result.group_summary.empty:
        p = directory / "group_summary.csv"
        result.group_summary.to_csv(p, index=False)
        artifact_paths["group_summary"] = p

    if not result.random_baseline_summary.empty:
        p = directory / "random_baseline_summary.csv"
        result.random_baseline_summary.to_csv(p, index=False)
        artifact_paths["random_baseline_summary"] = p

    run_manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "evaluation_run_manifest",
        "command": "eval-config",
        "strategy_path": strategy_path,
        "start": str(args.start),
        "end": str(args.end),
        "codes": args.codes,
        "round_trip_cost_rate": args.round_trip_cost_rate,
        "market_profile": str(args.market_profile) if args.market_profile else None,
        "group_by": args.group_by,
        "random_baseline_seed": args.random_baseline_seed,
        "artifacts": sorted(artifact_paths.keys()),
    }
    run_manifest_path = directory / "run_manifest.json"
    run_manifest_path.write_text(
        json.dumps(run_manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["run_manifest"] = run_manifest_path

    files = sorted(
        (
            {
                "key": key,
                "path": path.relative_to(directory).as_posix(),
                "filename": path.name,
                "role": _eval_manifest_role(key),
            }
            for key, path in artifact_paths.items()
        ),
        key=lambda f: f["key"],
    )
    report_manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "evaluation_report_manifest",
        "files": files,
    }
    report_manifest_path = directory / "report_manifest.json"
    report_manifest_path.write_text(
        json.dumps(report_manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


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
            )
            paths = manifest.paths(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
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
            )
            paths = manifest.paths(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
            )
            missing_paths = [path for path in paths if not path.exists()]
            issues = manifest.validate_contents(
                role=args.role,
                symbol=args.symbol,
                window=args.window,
                group_by=args.group_by,
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
        if args.output_dir:
            _write_evaluation_output(
                result=result,
                output_dir=args.output_dir,
                args=args,
                strategy_path=str(args.strategy),
            )
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
            report = PreflightRunner(store).run(
                PreflightRequest(
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
            )
            if args.output_json:
                args.output_json.parent.mkdir(parents=True, exist_ok=True)
                args.output_json.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
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
                    "holding_days": spec.holding_days,
                    "start": str(args.start),
                    "end": str(args.end),
                    "market_profile": str(args.market_profile) if args.market_profile else "built-in",
                },
            }
            paths = write_single_symbol_result(result, args.output_dir, run_request=run_request)
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
                    holding_days=spec.holding_days,
                ),
            )
        except Exception as exc:
            print(str(exc), file=__import__("sys").stderr)
            return 2

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
            result = SharedCashBacktestEngine(market_profile).run(
                frame,
                SharedCashBacktestRequest(
                    symbols=args.codes,
                    initial_cash=args.initial_cash,
                    entry_signal=spec.signal_expression,
                    holding_days=spec.holding_days,
                    max_positions=args.max_positions,
                    **weight_controls,
                    **risk_controls,
                    **rebalance_controls,
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
                },
            }
            paths = write_shared_cash_result(result, args.output_dir, run_request=run_request)
            for key, path in paths.items():
                print(f"{key}_path={path}")
        return 0

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
