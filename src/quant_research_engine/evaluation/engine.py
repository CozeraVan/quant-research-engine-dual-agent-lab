from __future__ import annotations

import numpy as np
import pandas as pd

from quant_research_engine.evaluation.models import EvaluationRequest, EvaluationResult
from quant_research_engine.evaluation.signals import evaluate_expression_signal


class EvaluationEngine:
    def evaluate(self, frame: pd.DataFrame, request: EvaluationRequest) -> EvaluationResult:
        self._validate_frame(frame, request)
        working = frame.copy()
        working["trade_date"] = pd.to_datetime(working["trade_date"])
        working = working.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)

        for horizon in request.forward_horizons:
            if horizon <= 0:
                raise ValueError("forward horizons must be positive")
            future_price = working.groupby("ts_code")[request.price_column].shift(-horizon)
            working[f"forward_return_{horizon}"] = future_price / working[request.price_column] - 1
            if request.round_trip_cost_rate is not None:
                if request.round_trip_cost_rate < 0:
                    raise ValueError("round_trip_cost_rate must be non-negative")
                working[f"adjusted_forward_return_{horizon}"] = (
                    working[f"forward_return_{horizon}"] - request.round_trip_cost_rate
                )

        working["signal"] = evaluate_expression_signal(working, request.signal_expression)
        forward_columns = [f"forward_return_{horizon}" for horizon in request.forward_horizons]
        adjusted_columns = (
            [f"adjusted_forward_return_{horizon}" for horizon in request.forward_horizons]
            if request.round_trip_cost_rate is not None
            else []
        )
        group_columns = request.group_by or []
        events = working.loc[working["signal"], ["ts_code", "trade_date", *forward_columns, *adjusted_columns, *group_columns]].copy()
        events = events.dropna(subset=forward_columns, how="all").reset_index(drop=True)
        summary = self._build_summary(events, request.forward_horizons, request.round_trip_cost_rate)
        factor_columns = request.factor_columns or []
        ic_summary = self._build_ic_summary(working, factor_columns, request.forward_horizons)
        factor_decay_summary = self._build_factor_decay_summary(ic_summary)
        quantile_summary = self._build_quantile_summary(
            working,
            factor_columns,
            request.forward_horizons,
            request.quantiles,
        )
        group_summary = self._build_group_summary(
            events, request.forward_horizons, group_columns, request.round_trip_cost_rate
        )
        random_baseline_summary = self._build_random_baseline_summary(
            working, request.forward_horizons, request.random_baseline_seed
        )
        regime_summary = self._build_regime_summary(
            working, events, request.forward_horizons, request.round_trip_cost_rate
        )
        return EvaluationResult(
            events=events,
            summary=summary,
            ic_summary=ic_summary,
            quantile_summary=quantile_summary,
            group_summary=group_summary,
            random_baseline_summary=random_baseline_summary,
            factor_decay_summary=factor_decay_summary,
            regime_summary=regime_summary,
        )

    def _validate_frame(self, frame: pd.DataFrame, request: EvaluationRequest) -> None:
        required_columns = {"ts_code", "trade_date", request.price_column, *(request.factor_columns or [])}
        missing = sorted(required_columns.difference(frame.columns))
        if missing:
            raise ValueError(f"research frame missing required columns: {missing}")
        if request.group_by:
            missing_group = sorted(set(request.group_by).difference(frame.columns))
            if missing_group:
                raise ValueError(f"research frame missing requested group columns: {missing_group}")

    def _build_summary(
        self,
        events: pd.DataFrame,
        horizons: list[int],
        round_trip_cost_rate: float | None = None,
    ) -> pd.DataFrame:
        rows = []
        for horizon in horizons:
            column = f"forward_return_{horizon}"
            series = events[column].dropna()
            row = {
                "horizon": horizon,
                "event_count": int(series.shape[0]),
                "mean_forward_return": None if series.empty else float(series.mean()),
                "median_forward_return": None if series.empty else float(series.median()),
                "win_rate": None if series.empty else float((series > 0).mean()),
            }
            if round_trip_cost_rate is not None:
                adjusted = events[f"adjusted_forward_return_{horizon}"].dropna()
                row.update(
                    {
                        "round_trip_cost_rate": round_trip_cost_rate,
                        "mean_adjusted_forward_return": None if adjusted.empty else float(adjusted.mean()),
                        "median_adjusted_forward_return": None if adjusted.empty else float(adjusted.median()),
                        "adjusted_win_rate": None if adjusted.empty else float((adjusted > 0).mean()),
                    }
                )
            rows.append(row)
        return pd.DataFrame(rows)

    def _build_group_summary(
        self,
        events: pd.DataFrame,
        horizons: list[int],
        group_columns: list[str],
        round_trip_cost_rate: float | None = None,
    ) -> pd.DataFrame:
        if not group_columns:
            return pd.DataFrame()
        rows = []
        for group_column in group_columns:
            for group_value, group_events in events.groupby(group_column, sort=False):
                for horizon in horizons:
                    column = f"forward_return_{horizon}"
                    series = group_events[column].dropna()
                    row: dict[str, object] = {
                        "group_by": group_column,
                        "group_value": group_value,
                        "horizon": horizon,
                        "event_count": int(series.shape[0]),
                        "mean_forward_return": None if series.empty else float(series.mean()),
                        "median_forward_return": None if series.empty else float(series.median()),
                        "win_rate": None if series.empty else float((series > 0).mean()),
                    }
                    if round_trip_cost_rate is not None:
                        adjusted = group_events[f"adjusted_forward_return_{horizon}"].dropna()
                        row.update(
                            {
                                "round_trip_cost_rate": round_trip_cost_rate,
                                "mean_adjusted_forward_return": (
                                    None if adjusted.empty else float(adjusted.mean())
                                ),
                                "median_adjusted_forward_return": (
                                    None if adjusted.empty else float(adjusted.median())
                                ),
                                "adjusted_win_rate": (
                                    None if adjusted.empty else float((adjusted > 0).mean())
                                ),
                            }
                        )
                    rows.append(row)
        return pd.DataFrame(rows)

    def _build_regime_summary(
        self,
        working: pd.DataFrame,
        events: pd.DataFrame,
        horizons: list[int],
        round_trip_cost_rate: float | None = None,
    ) -> pd.DataFrame:
        columns = ["regime", "horizon", "event_count", "mean_forward_return", "median_forward_return", "win_rate"]
        if round_trip_cost_rate is not None:
            columns.extend(["round_trip_cost_rate", "mean_adjusted_forward_return", "median_adjusted_forward_return", "adjusted_win_rate"])
        if events.empty:
            return pd.DataFrame(columns=columns)

        working = working.sort_values("trade_date").reset_index(drop=True)
        regime_labels = self._derive_regime_labels(working)
        if regime_labels.empty:
            return pd.DataFrame(columns=columns)

        events_with_regime = events.merge(
            regime_labels[["trade_date", "regime"]],
            on="trade_date",
            how="left",
        )

        rows = []
        for regime, group in events_with_regime.groupby("regime", sort=False):
            for horizon in horizons:
                column = f"forward_return_{horizon}"
                series = group[column].dropna()
                row: dict[str, object] = {
                    "regime": regime,
                    "horizon": horizon,
                    "event_count": int(series.shape[0]),
                    "mean_forward_return": None if series.empty else float(series.mean()),
                    "median_forward_return": None if series.empty else float(series.median()),
                    "win_rate": None if series.empty else float((series > 0).mean()),
                }
                if round_trip_cost_rate is not None:
                    adjusted_col = f"adjusted_forward_return_{horizon}"
                    adjusted = group[adjusted_col].dropna()
                    row.update({
                        "round_trip_cost_rate": round_trip_cost_rate,
                        "mean_adjusted_forward_return": None if adjusted.empty else float(adjusted.mean()),
                        "median_adjusted_forward_return": None if adjusted.empty else float(adjusted.median()),
                        "adjusted_win_rate": None if adjusted.empty else float((adjusted > 0).mean()),
                    })
                rows.append(row)
        return pd.DataFrame(rows, columns=columns)

    def _derive_regime_labels(self, working: pd.DataFrame) -> pd.DataFrame:
        """Derive deterministic regime labels, preferring explicit benchmark/market columns.

        Column precedence:
        1. ``benchmark_close`` — per-date benchmark/index close price.
        2. ``benchmark_return`` — pre-computed per-date benchmark return.
        3. Cross-sectional median ``close`` (fallback).

        Returns a DataFrame with columns ['trade_date', 'regime'] where regime
        is one of 'bull', 'bear', or 'neutral'.
        """
        daily = working.groupby("trade_date", sort=True)
        if "benchmark_close" in working.columns:
            benchmark_close = daily["benchmark_close"].first()
            market_returns = benchmark_close.pct_change().dropna()
        elif "benchmark_return" in working.columns:
            market_returns = daily["benchmark_return"].first().dropna()
        else:
            market_returns = daily["close"].median().pct_change().dropna()

        if len(market_returns) < 5:
            return pd.DataFrame(columns=["trade_date", "regime"])
        rolling = market_returns.rolling(window=min(20, len(market_returns)), min_periods=5).mean().dropna()
        result = pd.DataFrame({"trade_date": rolling.index, "regime": "neutral"}, index=rolling.index)
        result.loc[rolling > 0, "regime"] = "bull"
        result.loc[rolling < 0, "regime"] = "bear"
        return result.reset_index(drop=True)

    def _build_ic_summary(self, frame: pd.DataFrame, factor_columns: list[str], horizons: list[int]) -> pd.DataFrame:
        rows = []
        for factor in factor_columns:
            for horizon in horizons:
                forward_column = f"forward_return_{horizon}"
                daily_rows = []
                for trade_date, group in frame.groupby("trade_date", sort=True):
                    pair = group[[factor, forward_column]].dropna()
                    if len(pair) < 2:
                        continue
                    ic = pair[factor].corr(pair[forward_column])
                    rank_ic = pair[factor].rank(method="average").corr(pair[forward_column].rank(method="average"))
                    if pd.notna(ic) or pd.notna(rank_ic):
                        daily_rows.append(
                            {
                                "trade_date": trade_date,
                                "ic": ic,
                                "rank_ic": rank_ic,
                            }
                        )
                daily = pd.DataFrame(daily_rows)
                rows.append(
                    {
                        "factor": factor,
                        "horizon": horizon,
                        "observation_dates": int(len(daily)),
                        "mean_ic": None if daily.empty else self._optional_float(daily["ic"].mean()),
                        "mean_rank_ic": None if daily.empty else self._optional_float(daily["rank_ic"].mean()),
                        "ic_positive_rate": None if daily.empty else self._optional_float((daily["ic"] > 0).mean()),
                        "rank_ic_positive_rate": (
                            None if daily.empty else self._optional_float((daily["rank_ic"] > 0).mean())
                        ),
                    }
                )
        return pd.DataFrame(rows)

    def _build_factor_decay_summary(self, ic_summary: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "factor",
            "horizon",
            "base_horizon",
            "observation_dates",
            "mean_ic",
            "mean_rank_ic",
            "ic_decay_from_base",
            "rank_ic_decay_from_base",
        ]
        if ic_summary.empty:
            return pd.DataFrame(columns=columns)
        rows = []
        for factor in ic_summary["factor"].unique():
            factor_rows = ic_summary[ic_summary["factor"] == factor]
            base_idx = factor_rows["horizon"].idxmin()
            base_row = factor_rows.loc[base_idx]
            base_horizon = int(base_row["horizon"])
            base_mean_ic = base_row["mean_ic"]
            base_mean_rank_ic = base_row["mean_rank_ic"]
            for _, row in factor_rows.iterrows():
                horizon = int(row["horizon"])
                ic_decay: float | None = None
                rank_ic_decay: float | None = None
                if pd.notna(base_mean_ic) and base_mean_ic != 0 and pd.notna(row["mean_ic"]):
                    ic_decay = row["mean_ic"] - base_mean_ic
                if pd.notna(base_mean_rank_ic) and base_mean_rank_ic != 0 and pd.notna(row["mean_rank_ic"]):
                    rank_ic_decay = row["mean_rank_ic"] - base_mean_rank_ic
                rows.append(
                    {
                        "factor": factor,
                        "horizon": horizon,
                        "base_horizon": base_horizon,
                        "observation_dates": int(row["observation_dates"]),
                        "mean_ic": row["mean_ic"],
                        "mean_rank_ic": row["mean_rank_ic"],
                        "ic_decay_from_base": ic_decay,
                        "rank_ic_decay_from_base": rank_ic_decay,
                    }
                )
        return pd.DataFrame(rows, columns=columns)

    def _build_quantile_summary(
        self,
        frame: pd.DataFrame,
        factor_columns: list[str],
        horizons: list[int],
        quantiles: int | None,
    ) -> pd.DataFrame:
        if quantiles is None:
            return pd.DataFrame(columns=["factor", "horizon", "quantile", "row_count", "mean_forward_return"])
        if quantiles < 2:
            raise ValueError("quantiles must be at least 2")

        rows = []
        for factor in factor_columns:
            for horizon in horizons:
                forward_column = f"forward_return_{horizon}"
                daily_rows = []
                for _, group in frame.groupby("trade_date", sort=True):
                    pair = group[[factor, forward_column]].dropna().copy()
                    if pair[factor].nunique() < 2 or len(pair) < quantiles:
                        continue
                    try:
                        pair["quantile"] = pd.qcut(pair[factor], q=quantiles, labels=False, duplicates="drop") + 1
                    except ValueError:
                        continue
                    daily_rows.append(pair[["quantile", forward_column]])
                if not daily_rows:
                    for quantile in range(1, quantiles + 1):
                        rows.append(
                            {
                                "factor": factor,
                                "horizon": horizon,
                                "quantile": quantile,
                                "row_count": 0,
                                "mean_forward_return": None,
                            }
                        )
                    continue
                combined = pd.concat(daily_rows, ignore_index=True)
                for quantile in range(1, quantiles + 1):
                    series = combined.loc[combined["quantile"] == quantile, forward_column].dropna()
                    rows.append(
                        {
                            "factor": factor,
                            "horizon": horizon,
                            "quantile": quantile,
                            "row_count": int(len(series)),
                            "mean_forward_return": None if series.empty else float(series.mean()),
                        }
                    )
        return pd.DataFrame(rows)

    def _build_random_baseline_summary(
        self,
        working: pd.DataFrame,
        horizons: list[int],
        seed: int | None,
    ) -> pd.DataFrame:
        if seed is None:
            return pd.DataFrame(
                columns=["horizon", "event_count", "mean_forward_return", "median_forward_return", "win_rate"]
            )
        rng = np.random.default_rng(seed)
        rows = []
        for horizon in horizons:
            forward_col = f"forward_return_{horizon}"
            n_events = int((working["signal"] & working[forward_col].notna()).sum())
            valid_pool = working[working[forward_col].notna()]
            if n_events == 0 or len(valid_pool) < n_events:
                rows.append(
                    {
                        "horizon": horizon,
                        "event_count": n_events,
                        "mean_forward_return": None,
                        "median_forward_return": None,
                        "win_rate": None,
                    }
                )
                continue
            sampled_indices = rng.choice(len(valid_pool), size=n_events, replace=False)
            series = valid_pool.iloc[sampled_indices][forward_col]
            rows.append(
                {
                    "horizon": horizon,
                    "event_count": n_events,
                    "mean_forward_return": float(series.mean()),
                    "median_forward_return": float(series.median()),
                    "win_rate": float((series > 0).mean()),
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if pd.isna(value):
            return None
        return float(value)
