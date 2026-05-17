from __future__ import annotations

import math

import pandas as pd


def summarize_benchmark_relative_performance(
    equity_curve: pd.DataFrame,
    benchmark: pd.DataFrame,
    *,
    benchmark_value_column: str = "close",
    periods_per_year: int = 252,
) -> dict[str, float | int | None]:
    aligned = _aligned_return_frame(equity_curve, benchmark, benchmark_value_column)
    if aligned.empty:
        return _empty_summary(0)

    portfolio_values = aligned["total_equity"]
    benchmark_values = aligned[benchmark_value_column]
    portfolio_returns = portfolio_values.pct_change().dropna()
    benchmark_returns = benchmark_values.pct_change().dropna()
    returns = pd.DataFrame(
        {
            "portfolio_return": portfolio_returns,
            "benchmark_return": benchmark_returns,
        }
    ).dropna()
    if returns.empty:
        summary = _empty_summary(len(aligned))
        summary["portfolio_total_return"] = _total_return(portfolio_values)
        summary["benchmark_total_return"] = _total_return(benchmark_values)
        summary["excess_total_return"] = (
            summary["portfolio_total_return"] - summary["benchmark_total_return"]
            if summary["portfolio_total_return"] is not None and summary["benchmark_total_return"] is not None
            else None
        )
        return summary

    excess_returns = returns["portfolio_return"] - returns["benchmark_return"]
    portfolio_total_return = _total_return(portfolio_values)
    benchmark_total_return = _total_return(benchmark_values)
    tracking_error = _annualized_std(excess_returns, periods_per_year)
    beta = _beta(returns["portfolio_return"], returns["benchmark_return"])
    alpha = _alpha(returns["portfolio_return"], returns["benchmark_return"], beta)
    return {
        "aligned_period_count": int(len(aligned)),
        "return_observation_count": int(len(returns)),
        "portfolio_total_return": portfolio_total_return,
        "benchmark_total_return": benchmark_total_return,
        "excess_total_return": (
            portfolio_total_return - benchmark_total_return
            if portfolio_total_return is not None and benchmark_total_return is not None
            else None
        ),
        "tracking_error": tracking_error,
        "information_ratio": (
            float(excess_returns.mean() * periods_per_year / tracking_error)
            if tracking_error is not None and tracking_error > 0
            else None
        ),
        "beta": beta,
        "alpha": alpha,
        "up_capture": _capture_ratio(returns, positive_benchmark=True),
        "down_capture": _capture_ratio(returns, positive_benchmark=False),
    }


def _aligned_return_frame(
    equity_curve: pd.DataFrame,
    benchmark: pd.DataFrame,
    benchmark_value_column: str,
) -> pd.DataFrame:
    if equity_curve.empty or benchmark.empty:
        return pd.DataFrame()
    required_equity_columns = {"trade_date", "total_equity"}
    if not required_equity_columns.issubset(equity_curve.columns):
        raise ValueError("equity_curve must contain trade_date and total_equity")
    if "trade_date" not in benchmark.columns or benchmark_value_column not in benchmark.columns:
        raise ValueError(f"benchmark must contain trade_date and {benchmark_value_column}")

    equity = equity_curve.loc[:, ["trade_date", "total_equity"]].copy()
    benchmark_frame = benchmark.loc[:, ["trade_date", benchmark_value_column]].copy()
    equity["trade_date"] = pd.to_datetime(equity["trade_date"])
    benchmark_frame["trade_date"] = pd.to_datetime(benchmark_frame["trade_date"])
    aligned = equity.merge(benchmark_frame, on="trade_date", how="inner").sort_values("trade_date")
    return aligned.dropna(subset=["total_equity", benchmark_value_column]).reset_index(drop=True)


def _empty_summary(aligned_period_count: int) -> dict[str, float | int | None]:
    return {
        "aligned_period_count": aligned_period_count,
        "return_observation_count": 0,
        "portfolio_total_return": None,
        "benchmark_total_return": None,
        "excess_total_return": None,
        "tracking_error": None,
        "information_ratio": None,
        "beta": None,
        "alpha": None,
        "up_capture": None,
        "down_capture": None,
    }


def _total_return(values: pd.Series) -> float | None:
    if values.empty:
        return None
    start = float(values.iloc[0])
    end = float(values.iloc[-1])
    if not math.isfinite(start) or start <= 0 or not math.isfinite(end):
        return None
    return end / start - 1


def _annualized_std(values: pd.Series, periods_per_year: int) -> float | None:
    if len(values) < 2:
        return None
    std = float(values.std(ddof=1))
    return std * math.sqrt(periods_per_year)


def _beta(portfolio_returns: pd.Series, benchmark_returns: pd.Series) -> float | None:
    if len(portfolio_returns) < 2:
        return None
    benchmark_variance = float(benchmark_returns.var(ddof=1))
    if benchmark_variance <= 0:
        return None
    covariance = float(portfolio_returns.cov(benchmark_returns))
    return covariance / benchmark_variance


def _alpha(
    portfolio_returns: pd.Series,
    benchmark_returns: pd.Series,
    beta: float | None,
) -> float | None:
    if beta is None:
        return None
    return float(portfolio_returns.mean() - beta * benchmark_returns.mean())


def _capture_ratio(returns: pd.DataFrame, *, positive_benchmark: bool) -> float | None:
    if positive_benchmark:
        subset = returns.loc[returns["benchmark_return"] > 0]
    else:
        subset = returns.loc[returns["benchmark_return"] < 0]
    if subset.empty:
        return None
    benchmark_return = float(subset["benchmark_return"].mean())
    if benchmark_return == 0:
        return None
    return float(subset["portfolio_return"].mean() / benchmark_return)
