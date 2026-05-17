import pandas as pd
import pytest

from quant_research_engine.evaluation.engine import EvaluationEngine
from quant_research_engine.evaluation.models import EvaluationRequest


def make_research_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ", "000002.SZ", "000002.SZ", "000002.SZ"],
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-05", "2026-01-06", "2026-01-07"]
            ),
            "close": [10.0, 11.0, 12.1, 20.0, 18.0, 19.8],
            "rsi_2": [5.0, 15.0, 8.0, 12.0, 6.0, 16.0],
        }
    )


def test_evaluation_engine_computes_forward_returns_for_signal_events():
    engine = EvaluationEngine()
    request = EvaluationRequest(
        signal_expression="rsi_2 < 10",
        forward_horizons=[1],
    )

    result = engine.evaluate(make_research_frame(), request)

    records = result.events[["ts_code", "trade_date", "forward_return_1"]].to_dict("records")
    assert records[0]["ts_code"] == "000001.SZ"
    assert records[0]["trade_date"] == pd.Timestamp("2026-01-05")
    assert records[0]["forward_return_1"] == pytest.approx(0.1)
    assert records[1]["ts_code"] == "000002.SZ"
    assert records[1]["trade_date"] == pd.Timestamp("2026-01-06")
    assert records[1]["forward_return_1"] == pytest.approx(0.1)


def test_evaluation_engine_summary_counts_events_and_mean_return():
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1])

    result = engine.evaluate(make_research_frame(), request)

    record = result.summary.to_dict("records")[0]
    assert record["horizon"] == 1
    assert record["event_count"] == 2
    assert record["mean_forward_return"] == pytest.approx(0.1)
    assert record["median_forward_return"] == pytest.approx(0.1)
    assert record["win_rate"] == 1.0


def test_evaluation_engine_drops_events_without_future_bar():
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1])

    result = engine.evaluate(make_research_frame(), request)

    assert not ((result.events["ts_code"] == "000001.SZ") & (result.events["trade_date"] == pd.Timestamp("2026-01-07"))).any()


def test_evaluation_engine_keeps_event_when_at_least_one_horizon_has_future_return():
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1, 2])

    result = engine.evaluate(make_research_frame(), request)

    event = result.events.loc[
        (result.events["ts_code"] == "000002.SZ") & (result.events["trade_date"] == pd.Timestamp("2026-01-06"))
    ].iloc[0]
    assert event["forward_return_1"] == pytest.approx(0.1)
    assert pd.isna(event["forward_return_2"])


def test_evaluation_engine_computes_daily_ic_and_rank_ic():
    frame = pd.DataFrame(
        {
            "ts_code": ["a", "b", "c", "a", "b", "c"],
            "trade_date": pd.to_datetime(
                ["2026-01-05", "2026-01-05", "2026-01-05", "2026-01-06", "2026-01-06", "2026-01-06"]
            ),
            "close": [10.0, 10.0, 10.0, 11.0, 12.0, 13.0],
            "factor": [1.0, 2.0, 3.0, 1.0, 1.0, 1.0],
        }
    )

    result = EvaluationEngine().evaluate(
        frame,
        EvaluationRequest(
            signal_expression="factor > 0",
            forward_horizons=[1],
            factor_columns=["factor"],
        ),
    )

    record = result.ic_summary.to_dict("records")[0]
    assert record["factor"] == "factor"
    assert record["horizon"] == 1
    assert record["observation_dates"] == 1
    assert record["mean_ic"] == pytest.approx(1.0)
    assert record["mean_rank_ic"] == pytest.approx(1.0)


def test_evaluation_engine_computes_quantile_forward_returns():
    frame = pd.DataFrame(
        {
            "ts_code": ["a", "b", "c", "d", "a", "b", "c", "d"],
            "trade_date": pd.to_datetime(
                [
                    "2026-01-05",
                    "2026-01-05",
                    "2026-01-05",
                    "2026-01-05",
                    "2026-01-06",
                    "2026-01-06",
                    "2026-01-06",
                    "2026-01-06",
                ]
            ),
            "close": [10.0, 10.0, 10.0, 10.0, 9.0, 10.0, 11.0, 12.0],
            "factor": [1.0, 2.0, 3.0, 4.0, 1.0, 1.0, 1.0, 1.0],
        }
    )

    result = EvaluationEngine().evaluate(
        frame,
        EvaluationRequest(
            signal_expression="factor > 0",
            forward_horizons=[1],
            factor_columns=["factor"],
            quantiles=2,
        ),
    )

    records = result.quantile_summary.sort_values("quantile").to_dict("records")
    assert records[0]["factor"] == "factor"
    assert records[0]["horizon"] == 1
    assert records[0]["quantile"] == 1
    assert records[0]["mean_forward_return"] == pytest.approx(-0.05)
    assert records[1]["quantile"] == 2
    assert records[1]["mean_forward_return"] == pytest.approx(0.15)


def test_evaluation_engine_computes_friction_adjusted_event_summary():
    result = EvaluationEngine().evaluate(
        make_research_frame(),
        EvaluationRequest(
            signal_expression="rsi_2 < 10",
            forward_horizons=[1],
            round_trip_cost_rate=0.02,
        ),
    )

    event = result.events.sort_values(["ts_code", "trade_date"]).iloc[0]
    assert event["forward_return_1"] == pytest.approx(0.1)
    assert event["adjusted_forward_return_1"] == pytest.approx(0.08)

    record = result.summary.to_dict("records")[0]
    assert record["round_trip_cost_rate"] == pytest.approx(0.02)
    assert record["mean_adjusted_forward_return"] == pytest.approx(0.08)
    assert record["adjusted_win_rate"] == 1.0
