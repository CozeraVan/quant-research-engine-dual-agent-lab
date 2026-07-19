from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from quant_research_engine.portfolio.risk import summarize_equity_curve_by_window, summarize_equity_curve_rolling


def summarize_batch_summary(summary: pd.DataFrame) -> dict[str, Any]:
    if summary.empty:
        return {
            "symbol_count": 0,
            "traded_symbol_count": 0,
            "positive_return_symbol_rate": None,
            "mean_total_return": None,
            "median_total_return": None,
            "return_std": None,
            "return_p25": None,
            "return_p75": None,
            "best_symbol": None,
            "best_total_return": None,
            "worst_symbol": None,
            "worst_total_return": None,
            "total_trades": 0,
            "mean_trade_count": None,
            "total_cost": 0.0,
            "total_failed_orders": 0,
            "buy_hold_return": None,
            "mean_buy_hold_return": None,
            "median_buy_hold_return": None,
            "mean_excess_return_vs_buy_hold": None,
            "median_excess_return_vs_buy_hold": None,
        }

    returns = summary["total_return"].dropna()
    trade_counts = summary["trade_count"].fillna(0)
    best_index = returns.idxmax() if not returns.empty else None
    worst_index = returns.idxmin() if not returns.empty else None

    buy_hold_returns = summary["buy_hold_return"].dropna() if "buy_hold_return" in summary.columns else pd.Series(dtype=float)
    excess_returns = summary["excess_return_vs_buy_hold"].dropna() if "excess_return_vs_buy_hold" in summary.columns else pd.Series(dtype=float)

    return {
        "symbol_count": int(len(summary)),
        "traded_symbol_count": int((trade_counts > 0).sum()),
        "positive_return_symbol_rate": None if returns.empty else float((returns > 0).mean()),
        "mean_total_return": None if returns.empty else float(returns.mean()),
        "median_total_return": None if returns.empty else float(returns.median()),
        "return_std": None if len(returns) < 2 else float(returns.std()),
        "return_p25": None if returns.empty else float(returns.quantile(0.25)),
        "return_p75": None if returns.empty else float(returns.quantile(0.75)),
        "best_symbol": None if best_index is None else str(summary.loc[best_index, "symbol"]),
        "best_total_return": None if best_index is None else float(summary.loc[best_index, "total_return"]),
        "worst_symbol": None if worst_index is None else str(summary.loc[worst_index, "symbol"]),
        "worst_total_return": None if worst_index is None else float(summary.loc[worst_index, "total_return"]),
        "total_trades": int(trade_counts.sum()),
        "mean_trade_count": float(trade_counts.mean()),
        "total_cost": float(summary["total_cost"].fillna(0).sum()) if "total_cost" in summary.columns else 0.0,
        "total_failed_orders": (
            int(summary["failed_order_count"].fillna(0).sum()) if "failed_order_count" in summary.columns else 0
        ),
        "buy_hold_return": None if buy_hold_returns.empty else float(buy_hold_returns.mean()),
        "mean_buy_hold_return": None if buy_hold_returns.empty else float(buy_hold_returns.mean()),
        "median_buy_hold_return": None if buy_hold_returns.empty else float(buy_hold_returns.median()),
        "mean_excess_return_vs_buy_hold": None if excess_returns.empty else float(excess_returns.mean()),
        "median_excess_return_vs_buy_hold": None if excess_returns.empty else float(excess_returns.median()),
    }


def summarize_batch_by(summary: pd.DataFrame, group_column: str) -> pd.DataFrame:
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")
    if summary.empty:
        return pd.DataFrame(columns=[group_column])

    rows: list[dict[str, Any]] = []
    grouped = summary.dropna(subset=[group_column]).groupby(group_column, sort=True, dropna=True)
    for group_value, group_frame in grouped:
        row: dict[str, Any] = {group_column: group_value}
        row.update(summarize_batch_summary(group_frame))
        rows.append(row)
    return pd.DataFrame(rows)


def summarize_batch_ranked_symbols_by(summary: pd.DataFrame, group_column: str, top_n: int = 5) -> pd.DataFrame:
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")
    if "symbol" not in summary.columns:
        raise ValueError("summary must include symbol")
    if "total_return" not in summary.columns:
        raise ValueError("summary must include total_return")
    if summary.empty:
        return pd.DataFrame(columns=[group_column, "rank_type", "rank", "symbol", "total_return"])

    rows: list[dict[str, Any]] = []
    grouped = summary.dropna(subset=[group_column]).groupby(group_column, sort=True, dropna=True)
    for group_value, group_frame in grouped:
        ranked = group_frame.dropna(subset=["total_return"]).copy()
        if ranked.empty:
            continue
        for rank_type, frame in (
            ("top", ranked.sort_values("total_return", ascending=False).head(top_n)),
            ("bottom", ranked.sort_values("total_return", ascending=True).head(top_n)),
        ):
            for rank, record in enumerate(frame.to_dict("records"), start=1):
                row = {
                    group_column: group_value,
                    "rank_type": rank_type,
                    "rank": rank,
                    "symbol": record.get("symbol"),
                    "total_return": record.get("total_return"),
                }
                for optional_column in ("trade_count", "win_rate", "total_cost"):
                    if optional_column in summary.columns:
                        row[optional_column] = record.get(optional_column)
                rows.append(row)
    return pd.DataFrame(rows)


def summarize_batch_window_summary(equity_curves: dict[str, pd.DataFrame], window: str = "M") -> pd.DataFrame:
    rows = _collect_window_return_rows(equity_curves, window)
    if rows.empty:
        return pd.DataFrame(columns=_batch_window_summary_columns())

    return _summarize_window_return_rows(rows, group_columns=["window"])


def _collect_window_return_rows(equity_curves: dict[str, pd.DataFrame], window: str) -> pd.DataFrame:
    """Vectorized row collection for summarize_batch_window_summary.

    Produces the same (window, symbol, total_return) row set as the previous
    per-symbol/per-window loop, where total_return = last_equity/first_equity - 1
    within each calendar window (NaN when the first equity is not positive).
    """
    parts: list[pd.DataFrame] = []
    for symbol, equity_curve in equity_curves.items():
        if equity_curve.empty:
            continue
        if not {"trade_date", "total_equity"}.issubset(equity_curve.columns):
            raise ValueError("equity_curve must contain trade_date and total_equity")
        frame = equity_curve.loc[:, ["trade_date", "total_equity"]].dropna(subset=["trade_date", "total_equity"])
        if frame.empty:
            continue
        frame = frame.sort_values("trade_date")
        dates = pd.to_datetime(frame["trade_date"])
        equity = frame["total_equity"].astype(float)
        labels = dates.dt.to_period(window).astype(str)
        grouped = equity.groupby(labels.values, sort=True)
        first = grouped.first()
        last = grouped.last()
        total_return = (last / first - 1).where(first > 0, np.nan)
        parts.append(
            pd.DataFrame(
                {
                    "window": np.asarray(first.index.astype(str)),
                    "symbol": symbol,
                    "total_return": total_return.to_numpy(),
                }
            )
        )
    if not parts:
        return pd.DataFrame(columns=["window", "symbol", "total_return"])
    return pd.concat(parts, ignore_index=True)


def summarize_batch_rolling_summary(equity_curves: dict[str, pd.DataFrame], window_size: int = 20) -> pd.DataFrame:
    rows = _collect_rolling_return_rows(equity_curves, window_size)
    if rows.empty:
        return pd.DataFrame(columns=_batch_rolling_summary_columns())

    return _summarize_window_return_rows(
        rows,
        group_columns=["window_size", "end_date"],
        output_columns=_batch_rolling_summary_columns(),
    )


def _collect_rolling_return_rows(equity_curves: dict[str, pd.DataFrame], window_size: int) -> pd.DataFrame:
    """Vectorized row collection for summarize_batch_rolling_summary.

    Produces the same (window_size, end_date, symbol, total_return,
    max_drawdown) row set as the previous per-symbol/per-window loop:
    total_return = equity[end]/equity[start] - 1 (NaN when start <= 0),
    max_drawdown = min(equity / cummax(equity) - 1) within each window.
    """
    parts: list[pd.DataFrame] = []
    for symbol, equity_curve in equity_curves.items():
        if equity_curve.empty:
            continue
        if not {"trade_date", "total_equity"}.issubset(equity_curve.columns):
            raise ValueError("equity_curve must contain trade_date and total_equity")
        frame = equity_curve.loc[:, ["trade_date", "total_equity"]].dropna(subset=["trade_date", "total_equity"])
        if frame.empty:
            continue
        frame = frame.sort_values("trade_date").reset_index(drop=True)
        equity = frame["total_equity"].to_numpy(dtype=float)
        n = len(equity)
        if n < window_size:
            continue
        starts = equity[: n - window_size + 1]
        ends = equity[window_size - 1 :]
        total_returns = np.full(len(ends), np.nan)
        valid = starts > 0
        total_returns[valid] = ends[valid] / starts[valid] - 1.0
        windows = np.lib.stride_tricks.sliding_window_view(equity, window_size)
        running_max = np.maximum.accumulate(windows, axis=1)
        max_drawdowns = (windows / running_max - 1.0).min(axis=1)
        parts.append(
            pd.DataFrame(
                {
                    "window_size": window_size,
                    "end_date": frame["trade_date"].to_numpy()[window_size - 1 :],
                    "symbol": symbol,
                    "total_return": total_returns,
                    "max_drawdown": max_drawdowns,
                }
            )
        )
    if not parts:
        return pd.DataFrame(
            columns=["window_size", "end_date", "symbol", "total_return", "max_drawdown"]
        )
    return pd.concat(parts, ignore_index=True)


def summarize_batch_rolling_summary_by(
    summary: pd.DataFrame,
    equity_curves: dict[str, pd.DataFrame],
    group_column: str,
    window_size: int = 20,
) -> pd.DataFrame:
    if "symbol" not in summary.columns:
        raise ValueError("summary must include symbol")
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")

    columns = [group_column, *_batch_rolling_summary_columns()]
    if summary.empty:
        return pd.DataFrame(columns=columns)

    symbol_groups = (
        summary[["symbol", group_column]]
        .dropna(subset=["symbol", group_column])
        .drop_duplicates(subset=["symbol"], keep="first")
        .set_index("symbol")[group_column]
        .to_dict()
    )
    rows: list[dict[str, Any]] = []
    for symbol, equity_curve in equity_curves.items():
        if symbol not in symbol_groups:
            continue
        symbol_rolling = summarize_equity_curve_rolling(equity_curve, window_size=window_size)
        if symbol_rolling.empty:
            continue
        for record in symbol_rolling.to_dict("records"):
            rows.append(
                {
                    group_column: symbol_groups[symbol],
                    "window_size": record["window_size"],
                    "end_date": record["end_date"],
                    "symbol": symbol,
                    "total_return": record["total_return"],
                    "max_drawdown": record["max_drawdown"],
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)

    return _summarize_window_return_rows(
        pd.DataFrame(rows),
        group_columns=[group_column, "window_size", "end_date"],
        output_columns=columns,
    )


def summarize_batch_ranked_rolling_symbols_by(
    summary: pd.DataFrame,
    equity_curves: dict[str, pd.DataFrame],
    group_column: str,
    window_size: int = 20,
    top_n: int = 5,
) -> pd.DataFrame:
    if "symbol" not in summary.columns:
        raise ValueError("summary must include symbol")
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")

    columns = [group_column, "window_size", "end_date", "rank_type", "rank", "symbol", "total_return"]
    optional_columns = [column for column in ("trade_count", "win_rate", "total_cost") if column in summary.columns]
    columns.extend(optional_columns)
    if summary.empty:
        return pd.DataFrame(columns=columns)

    metadata_columns = ["symbol", group_column, *optional_columns]
    symbol_metadata = (
        summary[metadata_columns]
        .dropna(subset=["symbol", group_column])
        .drop_duplicates(subset=["symbol"], keep="first")
        .set_index("symbol")
    )
    rows: list[dict[str, Any]] = []
    for symbol, equity_curve in equity_curves.items():
        if symbol not in symbol_metadata.index:
            continue
        symbol_rolling = summarize_equity_curve_rolling(equity_curve, window_size=window_size)
        if symbol_rolling.empty:
            continue
        metadata = symbol_metadata.loc[symbol]
        for record in symbol_rolling.to_dict("records"):
            row = {
                group_column: metadata[group_column],
                "window_size": record["window_size"],
                "end_date": record["end_date"],
                "symbol": symbol,
                "total_return": record["total_return"],
            }
            for optional_column in optional_columns:
                row[optional_column] = metadata[optional_column]
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=columns)

    return _rank_window_symbol_rows(
        pd.DataFrame(rows),
        group_columns=[group_column, "window_size", "end_date"],
        columns=columns,
        top_n=top_n,
    )


def summarize_batch_window_summary_by(
    summary: pd.DataFrame,
    equity_curves: dict[str, pd.DataFrame],
    group_column: str,
    window: str = "M",
) -> pd.DataFrame:
    if "symbol" not in summary.columns:
        raise ValueError("summary must include symbol")
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")

    columns = [group_column, *_batch_window_summary_columns()]
    if summary.empty:
        return pd.DataFrame(columns=columns)

    symbol_groups = (
        summary[["symbol", group_column]]
        .dropna(subset=["symbol", group_column])
        .drop_duplicates(subset=["symbol"], keep="first")
        .set_index("symbol")[group_column]
        .to_dict()
    )
    rows: list[dict[str, Any]] = []
    for symbol, equity_curve in equity_curves.items():
        if symbol not in symbol_groups:
            continue
        symbol_windows = summarize_equity_curve_by_window(equity_curve, window=window)
        if symbol_windows.empty:
            continue
        for record in symbol_windows.to_dict("records"):
            rows.append(
                {
                    group_column: symbol_groups[symbol],
                    "window": record["window"],
                    "symbol": symbol,
                    "total_return": record["total_return"],
                }
            )
    if not rows:
        return pd.DataFrame(columns=columns)

    return _summarize_window_return_rows(
        pd.DataFrame(rows),
        group_columns=[group_column, "window"],
        output_columns=columns,
    )


def summarize_batch_ranked_window_symbols_by(
    summary: pd.DataFrame,
    equity_curves: dict[str, pd.DataFrame],
    group_column: str,
    window: str = "M",
    top_n: int = 5,
) -> pd.DataFrame:
    if "symbol" not in summary.columns:
        raise ValueError("summary must include symbol")
    if group_column not in summary.columns:
        raise ValueError(f"summary must include {group_column}")

    columns = [group_column, "window", "rank_type", "rank", "symbol", "total_return"]
    optional_columns = [column for column in ("trade_count", "win_rate", "total_cost") if column in summary.columns]
    columns.extend(optional_columns)
    if summary.empty:
        return pd.DataFrame(columns=columns)

    metadata_columns = ["symbol", group_column, *optional_columns]
    symbol_metadata = (
        summary[metadata_columns]
        .dropna(subset=["symbol", group_column])
        .drop_duplicates(subset=["symbol"], keep="first")
        .set_index("symbol")
    )
    rows: list[dict[str, Any]] = []
    for symbol, equity_curve in equity_curves.items():
        if symbol not in symbol_metadata.index:
            continue
        symbol_windows = summarize_equity_curve_by_window(equity_curve, window=window)
        if symbol_windows.empty:
            continue
        metadata = symbol_metadata.loc[symbol]
        for record in symbol_windows.to_dict("records"):
            row = {
                group_column: metadata[group_column],
                "window": record["window"],
                "symbol": symbol,
                "total_return": record["total_return"],
            }
            for optional_column in optional_columns:
                row[optional_column] = metadata[optional_column]
            rows.append(row)
    if not rows:
        return pd.DataFrame(columns=columns)

    return _rank_window_symbol_rows(pd.DataFrame(rows), group_columns=[group_column, "window"], columns=columns, top_n=top_n)


def _summarize_window_return_rows(
    frame: pd.DataFrame,
    group_columns: list[str],
    output_columns: list[str] | None = None,
) -> pd.DataFrame:
    summary_rows: list[dict[str, Any]] = []
    for group_key, group in frame.groupby(group_columns, sort=True, dropna=True):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        returns = group["total_return"].dropna()
        best_index = returns.idxmax() if not returns.empty else None
        worst_index = returns.idxmin() if not returns.empty else None
        row = dict(zip(group_columns, group_values, strict=True))
        row.update(
            {
                "symbol_count": int(len(group)),
                "positive_return_symbol_rate": None if returns.empty else float((returns > 0).mean()),
                "mean_total_return": None if returns.empty else float(returns.mean()),
                "median_total_return": None if returns.empty else float(returns.median()),
                "return_std": None if len(returns) < 2 else float(returns.std()),
                "best_symbol": None if best_index is None else str(group.loc[best_index, "symbol"]),
                "best_total_return": None if best_index is None else float(group.loc[best_index, "total_return"]),
                "worst_symbol": None if worst_index is None else str(group.loc[worst_index, "symbol"]),
                "worst_total_return": None if worst_index is None else float(group.loc[worst_index, "total_return"]),
            }
        )
        summary_rows.append(row)
    return pd.DataFrame(summary_rows, columns=output_columns or _batch_window_summary_columns())


def _rank_window_symbol_rows(
    frame: pd.DataFrame,
    group_columns: list[str],
    columns: list[str],
    top_n: int,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for group_key, group in frame.groupby(group_columns, sort=True, dropna=True):
        group_values = group_key if isinstance(group_key, tuple) else (group_key,)
        ranked = group.dropna(subset=["total_return"]).copy()
        if ranked.empty:
            continue
        for rank_type, rank_frame in (
            ("top", ranked.sort_values("total_return", ascending=False).head(top_n)),
            ("bottom", ranked.sort_values("total_return", ascending=True).head(top_n)),
        ):
            for rank, record in enumerate(rank_frame.to_dict("records"), start=1):
                row = dict(zip(group_columns, group_values, strict=True))
                row.update(
                    {
                        "rank_type": rank_type,
                        "rank": rank,
                        "symbol": record["symbol"],
                        "total_return": record["total_return"],
                    }
                )
                for optional_column in ("trade_count", "win_rate", "total_cost"):
                    if optional_column in record:
                        row[optional_column] = record[optional_column]
                rows.append(row)
    return pd.DataFrame(rows, columns=columns)


def _batch_window_summary_columns() -> list[str]:
    return [
        "window",
        "symbol_count",
        "positive_return_symbol_rate",
        "mean_total_return",
        "median_total_return",
        "return_std",
        "best_symbol",
        "best_total_return",
        "worst_symbol",
        "worst_total_return",
    ]


def summarize_shared_orders_by(orders: pd.DataFrame, group_column: str) -> pd.DataFrame:
    columns = [
        "group_by",
        "group_value",
        "order_count",
        "buy_order_count",
        "sell_order_count",
        "total_notional",
        "buy_notional",
        "sell_notional",
        "total_cost",
    ]
    if orders.empty:
        return pd.DataFrame(columns=columns)
    if group_column not in orders.columns:
        raise ValueError(f"shared-cash orders must include {group_column}")
    rows: list[dict[str, Any]] = []
    grouped = orders.dropna(subset=[group_column]).groupby(group_column, sort=True, dropna=True)
    for group_value, group_frame in grouped:
        total_count = len(group_frame)
        buys = group_frame[group_frame["side"] == "buy"]
        sells = group_frame[group_frame["side"] == "sell"]
        buy_count = len(buys)
        sell_count = len(sells)
        buy_notional = float(buys["notional"].sum()) if buy_count > 0 else 0.0
        sell_notional = float(sells["notional"].sum()) if sell_count > 0 else 0.0
        rows.append({
            "group_by": group_column,
            "group_value": group_value,
            "order_count": total_count,
            "buy_order_count": buy_count,
            "sell_order_count": sell_count,
            "total_notional": buy_notional + sell_notional,
            "buy_notional": buy_notional,
            "sell_notional": sell_notional,
            "total_cost": float(group_frame["cost"].sum()) if "cost" in group_frame.columns else 0.0,
        })
    return pd.DataFrame(rows, columns=columns)


def summarize_shared_trades_by(trades: pd.DataFrame, group_column: str) -> pd.DataFrame:
    columns = [
        "group_by",
        "group_value",
        "trade_count",
        "win_rate",
        "gross_pnl",
        "net_pnl",
        "total_cost",
    ]
    if trades.empty:
        return pd.DataFrame(columns=columns)
    if group_column not in trades.columns:
        raise ValueError(f"shared-cash trades must include {group_column}")
    rows: list[dict[str, Any]] = []
    grouped = trades.dropna(subset=[group_column]).groupby(group_column, sort=True, dropna=True)
    for group_value, group_frame in grouped:
        trade_count = len(group_frame)
        wins = int((group_frame["net_pnl"] > 0).sum()) if trade_count > 0 else 0
        rows.append({
            "group_by": group_column,
            "group_value": group_value,
            "trade_count": trade_count,
            "win_rate": wins / trade_count if trade_count > 0 else None,
            "gross_pnl": float(group_frame["gross_pnl"].sum()) if trade_count > 0 else 0.0,
            "net_pnl": float(group_frame["net_pnl"].sum()) if trade_count > 0 else 0.0,
            "total_cost": float(group_frame["cost"].sum()) if trade_count > 0 else 0.0,
        })
    return pd.DataFrame(rows, columns=columns)


def summarize_shared_failed_orders_by(failed_orders: pd.DataFrame, group_column: str) -> pd.DataFrame:
    columns = [
        "group_by",
        "group_value",
        "failed_order_count",
        "failed_notional",
    ]
    if failed_orders.empty:
        return pd.DataFrame(columns=columns)
    if group_column not in failed_orders.columns:
        raise ValueError(f"shared-cash failed orders must include {group_column}")
    rows: list[dict[str, Any]] = []
    grouped = failed_orders.dropna(subset=[group_column]).groupby(group_column, sort=True, dropna=True)
    for group_value, group_frame in grouped:
        count = len(group_frame)
        rows.append({
            "group_by": group_column,
            "group_value": group_value,
            "failed_order_count": count,
            "failed_notional": float(group_frame["notional"].sum()) if count > 0 else 0.0,
        })
    return pd.DataFrame(rows, columns=columns)


def _batch_rolling_summary_columns() -> list[str]:
    return [
        "window_size",
        "end_date",
        "symbol_count",
        "positive_return_symbol_rate",
        "mean_total_return",
        "median_total_return",
        "return_std",
        "best_symbol",
        "best_total_return",
        "worst_symbol",
        "worst_total_return",
    ]
