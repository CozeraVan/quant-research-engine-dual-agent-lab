from __future__ import annotations

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
        quantile_summary = self._build_quantile_summary(
            working,
            factor_columns,
            request.forward_horizons,
            request.quantiles,
        )
        group_summary = self._build_group_summary(
            events, request.forward_horizons, group_columns, request.round_trip_cost_rate
        )
        return EvaluationResult(
            events=events,
            summary=summary,
            ic_summary=ic_summary,
            quantile_summary=quantile_summary,
            group_summary=group_summary,
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

    @staticmethod
    def _optional_float(value: object) -> float | None:
        if pd.isna(value):
            return None
        return float(value)
