from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant_research_engine.portfolio.batch import BatchBacktestResult
from quant_research_engine.portfolio.analytics import (
    summarize_batch_by,
    summarize_batch_ranked_rolling_symbols_by,
    summarize_batch_ranked_symbols_by,
    summarize_batch_ranked_window_symbols_by,
    summarize_batch_rolling_summary,
    summarize_batch_rolling_summary_by,
    summarize_batch_window_summary_by,
    summarize_batch_window_summary,
)
from quant_research_engine.portfolio.risk import summarize_equity_curve_by_window, summarize_equity_curve_rolling
from quant_research_engine.portfolio.shared import SharedCashBacktestResult
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestResult


_SUMMARY_LABELS = {
    "initial_cash": "Initial cash",
    "final_equity": "Final equity",
    "total_return": "Total return",
    "trade_count": "Trade count",
    "win_rate": "Win rate",
    "total_cost": "Total cost",
    "max_drawdown": "Max drawdown",
    "max_drawdown_peak_date": "Max drawdown peak date",
    "max_drawdown_trough_date": "Max drawdown trough date",
    "max_drawdown_recovery_date": "Max drawdown recovery date",
    "max_drawdown_duration_days": "Max drawdown duration days",
    "rebalance_order_count": "Rebalance order count",
    "rebalance_notional": "Rebalance notional",
    "rebalance_cost": "Rebalance cost",
    "rebalance_turnover": "Rebalance turnover",
    "failed_rebalance_order_count": "Failed rebalance order count",
    "failed_rebalance_notional": "Failed rebalance notional",
    "benchmark_code": "Benchmark code",
    "benchmark_aligned_period_count": "Aligned period count",
    "benchmark_return_observation_count": "Return observation count",
    "benchmark_portfolio_total_return": "Portfolio total return",
    "benchmark_benchmark_total_return": "Benchmark total return",
    "benchmark_excess_total_return": "Excess total return",
    "benchmark_tracking_error": "Tracking error",
    "benchmark_information_ratio": "Information ratio",
    "benchmark_beta": "Beta",
    "benchmark_alpha": "Alpha",
    "benchmark_up_capture": "Up capture",
    "benchmark_down_capture": "Down capture",
    "symbol_count": "Symbol count",
    "traded_symbol_count": "Traded symbol count",
    "positive_return_symbol_rate": "Positive return symbol rate",
    "mean_total_return": "Mean total return",
    "median_total_return": "Median total return",
    "return_std": "Return standard deviation",
    "total_trades": "Total trades",
    "total_failed_orders": "Total failed orders",
}


def write_single_symbol_result(
    result: SingleSymbolBacktestResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    paths = {
        "orders": directory / "orders.csv",
        "trades": directory / "trades.csv",
        "failed_orders": directory / "failed_orders.csv",
        "equity_curve": directory / "equity_curve.csv",
        "summary": directory / "summary.json",
    }
    result.orders.to_csv(paths["orders"], index=False)
    result.trades.to_csv(paths["trades"], index=False)
    result.failed_orders.to_csv(paths["failed_orders"], index=False)
    result.equity_curve.to_csv(paths["equity_curve"], index=False)
    paths["summary"].write_text(
        json.dumps(_json_ready_summary(result.summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths


def write_shared_cash_result(
    result: SharedCashBacktestResult,
    output_dir: str | Path,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    paths = {
        "orders": directory / "orders.csv",
        "trades": directory / "trades.csv",
        "failed_orders": directory / "failed_orders.csv",
        "equity_curve": directory / "equity_curve.csv",
        "window_metrics_M": directory / "window_metrics_M.csv",
        "window_metrics_Q": directory / "window_metrics_Q.csv",
        "window_metrics_Y": directory / "window_metrics_Y.csv",
        "rolling_metrics_20": directory / "rolling_metrics_20.csv",
        "summary": directory / "summary.json",
        "summary_markdown": directory / "summary.md",
        "report_manifest": directory / "report_manifest.json",
    }
    result.orders.to_csv(paths["orders"], index=False)
    result.trades.to_csv(paths["trades"], index=False)
    result.failed_orders.to_csv(paths["failed_orders"], index=False)
    result.equity_curve.to_csv(paths["equity_curve"], index=False)
    for window in ("M", "Q", "Y"):
        summarize_equity_curve_by_window(result.equity_curve, window=window).to_csv(
            paths[f"window_metrics_{window}"],
            index=False,
        )
    summarize_equity_curve_rolling(result.equity_curve, window_size=20).to_csv(
        paths["rolling_metrics_20"],
        index=False,
    )
    paths["summary"].write_text(
        json.dumps(_json_ready_summary(result.summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths["summary_markdown"].write_text(shared_summary_markdown(result.summary, paths), encoding="utf-8")
    paths["report_manifest"].write_text(
        json.dumps(_shared_report_manifest(paths, directory), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths


def write_batch_result(
    result: BatchBacktestResult,
    output_dir: str | Path,
    group_by: list[str] | None = None,
    group_rank_top_n: int = 1,
) -> dict[str, Path]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {"summary": directory / "summary.csv"}
    paths["summary_metrics"] = directory / "summary_metrics.json"
    paths["summary_markdown"] = directory / "summary.md"
    paths["report_manifest"] = directory / "report_manifest.json"
    for window in ("M", "Q", "Y"):
        paths[f"window_summary_{window}"] = directory / f"window_summary_{window}.csv"
    paths["rolling_summary_20"] = directory / "rolling_summary_20.csv"
    result.summary.to_csv(paths["summary"], index=False)
    paths["summary_metrics"].write_text(
        json.dumps(_json_ready_summary(result.summary_metrics), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    equity_curves = {symbol: single_result.equity_curve for symbol, single_result in result.results.items()}
    for window in ("M", "Q", "Y"):
        summarize_batch_window_summary(equity_curves, window=window).to_csv(
            paths[f"window_summary_{window}"],
            index=False,
        )
    summarize_batch_rolling_summary(equity_curves, window_size=20).to_csv(
        paths["rolling_summary_20"],
        index=False,
    )
    for group_column in group_by or []:
        path = directory / f"group_by_{group_column}.csv"
        summarize_batch_by(result.summary, group_column).to_csv(path, index=False)
        paths[f"group_by_{group_column}"] = path
        ranked_path = directory / f"group_by_{group_column}_ranked_symbols.csv"
        summarize_batch_ranked_symbols_by(result.summary, group_column, top_n=group_rank_top_n).to_csv(
            ranked_path,
            index=False,
        )
        paths[f"group_by_{group_column}_ranked_symbols"] = ranked_path
        rolling_group_path = directory / f"rolling_summary_20_by_{group_column}.csv"
        summarize_batch_rolling_summary_by(result.summary, equity_curves, group_column, window_size=20).to_csv(
            rolling_group_path,
            index=False,
        )
        paths[f"rolling_summary_20_by_{group_column}"] = rolling_group_path
        ranked_rolling_group_path = directory / f"rolling_summary_20_by_{group_column}_ranked_symbols.csv"
        summarize_batch_ranked_rolling_symbols_by(
            result.summary,
            equity_curves,
            group_column,
            window_size=20,
            top_n=group_rank_top_n,
        ).to_csv(ranked_rolling_group_path, index=False)
        paths[f"rolling_summary_20_by_{group_column}_ranked_symbols"] = ranked_rolling_group_path
        for window in ("M", "Q", "Y"):
            window_group_path = directory / f"window_summary_{window}_by_{group_column}.csv"
            summarize_batch_window_summary_by(result.summary, equity_curves, group_column, window=window).to_csv(
                window_group_path,
                index=False,
            )
            paths[f"window_summary_{window}_by_{group_column}"] = window_group_path
            ranked_window_group_path = directory / f"window_summary_{window}_by_{group_column}_ranked_symbols.csv"
            summarize_batch_ranked_window_symbols_by(
                result.summary,
                equity_curves,
                group_column,
                window=window,
                top_n=group_rank_top_n,
            ).to_csv(ranked_window_group_path, index=False)
            paths[f"window_summary_{window}_by_{group_column}_ranked_symbols"] = ranked_window_group_path

    for symbol, single_result in result.results.items():
        symbol_dir = directory / symbol
        single_paths = write_single_symbol_result(single_result, symbol_dir)
        for name, path in single_paths.items():
            paths[f"{symbol}_{name}"] = path
    paths["summary_markdown"].write_text(
        batch_summary_markdown(result.summary_metrics, paths, result.summary),
        encoding="utf-8",
    )
    paths["report_manifest"].write_text(
        json.dumps(_batch_report_manifest(paths, directory), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return paths


def _json_ready_summary(summary: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in summary.items():
        if hasattr(value, "item"):
            clean[key] = value.item()
        else:
            clean[key] = value
    return clean


def shared_summary_markdown(summary: dict[str, Any], paths: dict[str, Path] | None = None) -> str:
    sections = [
        ("Portfolio", _portfolio_summary_items(summary)),
        ("Rebalance", _prefixed_summary_items(summary, ("rebalance_", "failed_rebalance_"))),
        ("Benchmark", _prefixed_summary_items(summary, ("benchmark_",))),
    ]
    lines = ["# Shared Cash Backtest Summary", ""]
    for title, items in sections:
        if not items:
            continue
        lines.extend([f"## {title}", "", "| metric | value |", "|---|---|"])
        lines.extend(f"| {_summary_label(key)} | {_format_markdown_value(value)} |" for key, value in items)
        lines.append("")
    if paths:
        lines.extend(["## Output Files", "", "| file | path |", "|---|---|"])
        for label, path in _shared_report_paths(paths):
            lines.append(f"| {label} | {path.name} |")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _shared_report_paths(paths: dict[str, Path]) -> list[tuple[str, Path]]:
    labels = {
        "orders": "Orders",
        "trades": "Trades",
        "failed_orders": "Failed orders",
        "equity_curve": "Equity curve",
        "window_metrics_M": "Monthly window metrics",
        "window_metrics_Q": "Quarterly window metrics",
        "window_metrics_Y": "Yearly window metrics",
        "rolling_metrics_20": "Rolling metrics 20",
        "summary": "Summary JSON",
        "summary_markdown": "Summary Markdown",
        "report_manifest": "Report manifest",
    }
    return [(labels[key], paths[key]) for key in labels if key in paths]


def _shared_report_manifest(paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    return {
        "kind": "shared_cash_backtest_report_manifest",
        "files": [_shared_manifest_entry(key, path, output_dir) for key, path in paths.items()],
    }


def _shared_manifest_entry(key: str, path: Path, output_dir: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": key,
        "path": path.relative_to(output_dir).as_posix() if path.is_relative_to(output_dir) else path.as_posix(),
        "filename": path.name,
        "role": _shared_manifest_role(key),
    }
    window = _shared_manifest_window(key)
    if window is not None:
        entry["window"] = window
    window_size = _shared_manifest_window_size(key)
    if window_size is not None:
        entry["window_size"] = window_size
    return entry


def _shared_manifest_role(key: str) -> str:
    if key.startswith("window_metrics_"):
        return "window_metrics"
    if key.startswith("rolling_metrics_"):
        return "rolling_metrics"
    if key == "summary_markdown":
        return "summary_markdown"
    if key == "report_manifest":
        return "report_manifest"
    return key


def _shared_manifest_window(key: str) -> str | None:
    if not key.startswith("window_metrics_"):
        return None
    return key.removeprefix("window_metrics_")


def _shared_manifest_window_size(key: str) -> int | None:
    if not key.startswith("rolling_metrics_"):
        return None
    return int(key.removeprefix("rolling_metrics_"))


def batch_summary_markdown(
    summary_metrics: dict[str, Any],
    paths: dict[str, Path],
    summary_frame: Any | None = None,
    top_n: int = 5,
) -> str:
    lines = ["# Batch Backtest Summary", ""]
    if summary_metrics:
        lines.extend(["## Aggregate Metrics", "", "| metric | value |", "|---|---|"])
        lines.extend(
            f"| {_summary_label(key)} | {_format_markdown_value(value)} |"
            for key, value in summary_metrics.items()
        )
        lines.append("")

    ranked_sections = _batch_ranked_symbol_sections(summary_frame, top_n=top_n)
    for title, rows in ranked_sections:
        if not rows:
            continue
        lines.extend([f"## {title}", "", "| symbol | total return | trade count | win rate | total cost |", "|---|---:|---:|---:|---:|"])
        lines.extend(
            "| "
            + " | ".join(_format_markdown_value(value) for value in row)
            + " |"
            for row in rows
        )
        lines.append("")

    lines.extend(["## Output Files", "", "| file | path |", "|---|---|"])
    for label, path in _batch_report_paths(paths):
        lines.append(f"| {label} | {path.name} |")
    return "\n".join(lines).rstrip() + "\n"


def _batch_ranked_symbol_sections(summary_frame: Any | None, top_n: int) -> list[tuple[str, list[list[Any]]]]:
    if summary_frame is None or getattr(summary_frame, "empty", True):
        return []
    columns = set(getattr(summary_frame, "columns", []))
    if "symbol" not in columns or "total_return" not in columns:
        return []

    ranked = summary_frame.dropna(subset=["total_return"]).copy()
    if ranked.empty:
        return []

    top = ranked.sort_values("total_return", ascending=False).head(top_n)
    bottom = ranked.sort_values("total_return", ascending=True).head(top_n)
    return [
        ("Top Symbols", _batch_symbol_rows(top)),
        ("Bottom Symbols", _batch_symbol_rows(bottom)),
    ]


def _batch_symbol_rows(frame: Any) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for record in frame.to_dict("records"):
        rows.append(
            [
                record.get("symbol"),
                record.get("total_return"),
                record.get("trade_count"),
                record.get("win_rate"),
                record.get("total_cost"),
            ]
        )
    return rows


def _batch_report_paths(paths: dict[str, Path]) -> list[tuple[str, Path]]:
    report_paths: list[tuple[str, Path]] = []
    if "summary" in paths:
        report_paths.append(("Summary CSV", paths["summary"]))
    if "summary_metrics" in paths:
        report_paths.append(("Summary metrics JSON", paths["summary_metrics"]))
    if "summary_markdown" in paths:
        report_paths.append(("Summary Markdown", paths["summary_markdown"]))
    if "report_manifest" in paths:
        report_paths.append(("Report manifest", paths["report_manifest"]))
    if "window_summary_M" in paths:
        report_paths.append(("Monthly window summary", paths["window_summary_M"]))
    if "window_summary_Q" in paths:
        report_paths.append(("Quarterly window summary", paths["window_summary_Q"]))
    if "window_summary_Y" in paths:
        report_paths.append(("Yearly window summary", paths["window_summary_Y"]))
    if "rolling_summary_20" in paths:
        report_paths.append(("Rolling summary 20", paths["rolling_summary_20"]))
    for key, path in paths.items():
        if key.startswith("rolling_summary_") and "_by_" in key:
            report_paths.append((_rolling_group_summary_label(key), path))
    for key, path in paths.items():
        if key.startswith("window_summary_") and "_by_" in key:
            report_paths.append((_window_group_summary_label(key), path))
    for key, path in paths.items():
        if key.startswith("group_by_"):
            report_paths.append((_summary_label(key), path))
    return report_paths


def _batch_report_manifest(paths: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    return {
        "kind": "batch_backtest_report_manifest",
        "files": [_batch_manifest_entry(key, path, output_dir) for key, path in paths.items()],
    }


def _batch_manifest_entry(key: str, path: Path, output_dir: Path) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "key": key,
        "path": path.relative_to(output_dir).as_posix() if path.is_relative_to(output_dir) else path.as_posix(),
        "filename": path.name,
        "role": _batch_manifest_role(key),
    }
    symbol = _batch_manifest_symbol(key)
    if symbol is not None:
        entry["symbol"] = symbol
    window = _batch_manifest_window(key)
    if window is not None:
        entry["window"] = window
    window_size = _batch_manifest_window_size(key)
    if window_size is not None:
        entry["window_size"] = window_size
    group_column = _batch_manifest_group_by(key)
    if group_column is not None:
        entry["group_by"] = group_column
    return entry


def _batch_manifest_role(key: str) -> str:
    if key == "summary":
        return "summary"
    if key == "summary_metrics":
        return "summary_metrics"
    if key == "summary_markdown":
        return "summary_markdown"
    if key == "report_manifest":
        return "report_manifest"
    if key.startswith("window_summary_") and key.endswith("_ranked_symbols"):
        return "window_ranked_symbols"
    if key.startswith("window_summary_"):
        return "window_summary"
    if key.startswith("rolling_summary_") and key.endswith("_ranked_symbols"):
        return "rolling_ranked_symbols"
    if key.startswith("rolling_summary_"):
        return "rolling_summary"
    if key.startswith("group_by_") and key.endswith("_ranked_symbols"):
        return "group_ranked_symbols"
    if key.startswith("group_by_"):
        return "group_summary"
    for role in ("orders", "trades", "failed_orders", "equity_curve", "summary"):
        if key.endswith(f"_{role}"):
            return role
    return "artifact"


def _batch_manifest_symbol(key: str) -> str | None:
    for role in ("orders", "trades", "failed_orders", "equity_curve", "summary"):
        suffix = f"_{role}"
        if key.endswith(suffix) and key != role:
            return key.removesuffix(suffix)
    return None


def _batch_manifest_window(key: str) -> str | None:
    if not key.startswith("window_summary_"):
        return None
    remainder = key.removeprefix("window_summary_")
    return remainder.split("_", maxsplit=1)[0]


def _batch_manifest_window_size(key: str) -> int | None:
    if not key.startswith("rolling_summary_"):
        return None
    remainder = key.removeprefix("rolling_summary_")
    return int(remainder.split("_by_", maxsplit=1)[0])


def _batch_manifest_group_by(key: str) -> str | None:
    if key.startswith("group_by_"):
        return key.removeprefix("group_by_").removesuffix("_ranked_symbols")
    if key.startswith("window_summary_") and "_by_" in key:
        suffix = key.split("_by_", maxsplit=1)[1]
        return suffix.removesuffix("_ranked_symbols")
    if key.startswith("rolling_summary_") and "_by_" in key:
        return key.split("_by_", maxsplit=1)[1].removesuffix("_ranked_symbols")
    return None


def _window_group_summary_label(key: str) -> str:
    window, suffix = key.removeprefix("window_summary_").split("_by_", maxsplit=1)
    if suffix.endswith("_ranked_symbols"):
        group_column = suffix.removesuffix("_ranked_symbols")
        return f"Window summary {window} by {group_column.replace('_', ' ')} ranked symbols"
    return f"Window summary {window} by {suffix.replace('_', ' ')}"


def _rolling_group_summary_label(key: str) -> str:
    window_size, group_column = key.removeprefix("rolling_summary_").split("_by_", maxsplit=1)
    if group_column.endswith("_ranked_symbols"):
        group_column = group_column.removesuffix("_ranked_symbols")
        return f"Rolling summary {window_size} by {group_column.replace('_', ' ')} ranked symbols"
    return f"Rolling summary {window_size} by {group_column.replace('_', ' ')}"


def _portfolio_summary_items(summary: dict[str, Any]) -> list[tuple[str, Any]]:
    return [
        (key, value)
        for key, value in summary.items()
        if not key.startswith("rebalance_")
        and not key.startswith("failed_rebalance_")
        and not key.startswith("benchmark_")
        and key != "benchmark_code"
    ]


def _prefixed_summary_items(summary: dict[str, Any], prefixes: tuple[str, ...]) -> list[tuple[str, Any]]:
    return [
        (key, value)
        for key, value in summary.items()
        if key.startswith(prefixes) or (key == "benchmark_code" and "benchmark_" in prefixes)
    ]


def _format_markdown_value(value: Any) -> str:
    if hasattr(value, "item"):
        value = value.item()
    return "" if value is None else str(value)


def _summary_label(key: str) -> str:
    if key in _SUMMARY_LABELS:
        return _SUMMARY_LABELS[key]
    return key.replace("_", " ").capitalize()
