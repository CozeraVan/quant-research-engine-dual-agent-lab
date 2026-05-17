from __future__ import annotations

from typing import Any

import pandas as pd


def summarize_equity_curve(
    equity_curve: pd.DataFrame,
    *,
    annualization_factor: int = 252,
    risk_free_rate: float = 0.0,
) -> dict[str, Any]:
    if equity_curve.empty or "total_equity" not in equity_curve.columns:
        return _empty_metrics()

    equity = equity_curve["total_equity"].dropna().astype(float)
    if equity.empty:
        return _empty_metrics()

    returns = equity.pct_change().dropna()
    start_equity = float(equity.iloc[0])
    end_equity = float(equity.iloc[-1])
    total_return = end_equity / start_equity - 1 if start_equity > 0 else None
    drawdown = equity / equity.cummax() - 1
    max_drawdown = float(drawdown.min()) if not drawdown.empty else None
    drawdown_period = _max_drawdown_period(equity_curve, equity, drawdown)

    annualized_return = None
    if total_return is not None and len(returns) > 0:
        annualized_return = float((1 + total_return) ** (annualization_factor / len(returns)) - 1)

    annualized_volatility = None
    sharpe = None
    if len(returns) > 1:
        volatility = float(returns.std())
        annualized_volatility = volatility * annualization_factor**0.5
        if volatility > 0:
            daily_risk_free = risk_free_rate / annualization_factor
            sharpe = float(((returns - daily_risk_free).mean() / volatility) * annualization_factor**0.5)

    return_drawdown_ratio = None
    if total_return is not None and max_drawdown is not None and max_drawdown < 0:
        return_drawdown_ratio = float(total_return / abs(max_drawdown))

    return {
        "period_count": int(len(equity)),
        "daily_return_count": int(len(returns)),
        "start_equity": start_equity,
        "end_equity": end_equity,
        "total_return": None if total_return is None else float(total_return),
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_volatility,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        **drawdown_period,
        "return_drawdown_ratio": return_drawdown_ratio,
    }


def summarize_equity_curve_by_window(
    equity_curve: pd.DataFrame,
    *,
    window: str = "M",
    annualization_factor: int = 252,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    if window not in {"M", "Q", "Y"}:
        raise ValueError("window must be one of M, Q, or Y")
    if equity_curve.empty:
        return pd.DataFrame(columns=_window_metric_columns())
    required_columns = {"trade_date", "total_equity"}
    if not required_columns.issubset(equity_curve.columns):
        raise ValueError("equity_curve must contain trade_date and total_equity")

    frame = equity_curve.loc[:, ["trade_date", "total_equity"]].dropna(subset=["trade_date", "total_equity"]).copy()
    if frame.empty:
        return pd.DataFrame(columns=_window_metric_columns())
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date")
    frame["_window"] = frame["trade_date"].dt.to_period(window).astype(str)

    rows: list[dict[str, Any]] = []
    for window_label, group in frame.groupby("_window", sort=True):
        metrics = summarize_equity_curve(
            group.loc[:, ["trade_date", "total_equity"]],
            annualization_factor=annualization_factor,
            risk_free_rate=risk_free_rate,
        )
        rows.append(
            {
                "window": window_label,
                "start_date": group["trade_date"].iloc[0],
                "end_date": group["trade_date"].iloc[-1],
                **metrics,
            }
        )
    result = pd.DataFrame(rows, columns=_window_metric_columns())
    for column in ("max_drawdown_peak_date", "max_drawdown_trough_date", "max_drawdown_recovery_date"):
        result[column] = pd.to_datetime(result[column])
    return result


def summarize_equity_curve_rolling(
    equity_curve: pd.DataFrame,
    *,
    window_size: int,
    annualization_factor: int = 252,
    risk_free_rate: float = 0.0,
) -> pd.DataFrame:
    if window_size < 2:
        raise ValueError("window_size must be at least 2")
    if equity_curve.empty:
        return pd.DataFrame(columns=_rolling_metric_columns())
    required_columns = {"trade_date", "total_equity"}
    if not required_columns.issubset(equity_curve.columns):
        raise ValueError("equity_curve must contain trade_date and total_equity")

    frame = equity_curve.loc[:, ["trade_date", "total_equity"]].dropna(subset=["trade_date", "total_equity"]).copy()
    if frame.empty or len(frame) < window_size:
        return pd.DataFrame(columns=_rolling_metric_columns())
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values("trade_date").reset_index(drop=True)

    rows: list[dict[str, Any]] = []
    for end_position in range(window_size - 1, len(frame)):
        group = frame.iloc[end_position - window_size + 1 : end_position + 1]
        metrics = summarize_equity_curve(
            group,
            annualization_factor=annualization_factor,
            risk_free_rate=risk_free_rate,
        )
        rows.append(
            {
                "window_size": window_size,
                "start_date": group["trade_date"].iloc[0],
                "end_date": group["trade_date"].iloc[-1],
                **metrics,
            }
        )

    result = pd.DataFrame(rows, columns=_rolling_metric_columns())
    for column in ("max_drawdown_peak_date", "max_drawdown_trough_date", "max_drawdown_recovery_date"):
        result[column] = pd.to_datetime(result[column])
    return result


def _empty_metrics() -> dict[str, Any]:
    return {
        "period_count": 0,
        "daily_return_count": 0,
        "start_equity": None,
        "end_equity": None,
        "total_return": None,
        "annualized_return": None,
        "annualized_volatility": None,
        "sharpe": None,
        "max_drawdown": None,
        "max_drawdown_peak_date": None,
        "max_drawdown_trough_date": None,
        "max_drawdown_recovery_date": None,
        "max_drawdown_duration_days": None,
        "return_drawdown_ratio": None,
    }


def _window_metric_columns() -> list[str]:
    return [
        "window",
        "start_date",
        "end_date",
        "period_count",
        "daily_return_count",
        "start_equity",
        "end_equity",
        "total_return",
        "annualized_return",
        "annualized_volatility",
        "sharpe",
        "max_drawdown",
        "max_drawdown_peak_date",
        "max_drawdown_trough_date",
        "max_drawdown_recovery_date",
        "max_drawdown_duration_days",
        "return_drawdown_ratio",
    ]


def _rolling_metric_columns() -> list[str]:
    return [
        "window_size",
        "start_date",
        "end_date",
        "period_count",
        "daily_return_count",
        "start_equity",
        "end_equity",
        "total_return",
        "annualized_return",
        "annualized_volatility",
        "sharpe",
        "max_drawdown",
        "max_drawdown_peak_date",
        "max_drawdown_trough_date",
        "max_drawdown_recovery_date",
        "max_drawdown_duration_days",
        "return_drawdown_ratio",
    ]


def _max_drawdown_period(equity_curve: pd.DataFrame, equity: pd.Series, drawdown: pd.Series) -> dict[str, Any]:
    empty_period = {
        "max_drawdown_peak_date": None,
        "max_drawdown_trough_date": None,
        "max_drawdown_recovery_date": None,
        "max_drawdown_duration_days": None,
    }
    if drawdown.empty or "trade_date" not in equity_curve.columns:
        return empty_period

    dates = pd.to_datetime(equity_curve.loc[equity.index, "trade_date"])
    if dates.isna().all():
        return empty_period

    trough_label = drawdown.idxmin()
    trough_position = equity.index.get_loc(trough_label)
    through_trough = equity.iloc[: trough_position + 1]
    peak_label = through_trough.idxmax()
    peak_equity = float(equity.loc[peak_label])
    peak_date = dates.loc[peak_label]
    trough_date = dates.loc[trough_label]

    recovery_date = trough_date if float(drawdown.loc[trough_label]) >= 0 else None
    if recovery_date is None:
        after_trough = equity.iloc[trough_position + 1 :]
        recovered = after_trough[after_trough >= peak_equity]
        if not recovered.empty:
            recovery_date = dates.loc[recovered.index[0]]

    duration_days = None
    if pd.notna(peak_date) and pd.notna(trough_date):
        duration_days = int((trough_date - peak_date).days)

    return {
        "max_drawdown_peak_date": _date_string(peak_date),
        "max_drawdown_trough_date": _date_string(trough_date),
        "max_drawdown_recovery_date": _date_string(recovery_date),
        "max_drawdown_duration_days": duration_days,
    }


def _date_string(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date().isoformat()
