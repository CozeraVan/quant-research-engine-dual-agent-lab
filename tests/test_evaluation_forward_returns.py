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


def test_evaluation_engine_group_summary_is_empty_when_group_by_not_requested():
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1])

    result = engine.evaluate(make_research_frame(), request)

    assert result.group_summary.empty


def test_evaluation_engine_preserves_group_columns_in_events():
    frame = make_research_frame()
    frame["board"] = ["main_board", "main_board", "main_board", "star_market", "star_market", "star_market"]
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], group_by=["board"])

    result = engine.evaluate(frame, request)

    assert "board" in result.events.columns
    assert result.events.iloc[0]["board"] == "main_board"
    assert result.events.iloc[1]["board"] == "star_market"


def test_evaluation_engine_builds_group_summary_for_single_column():
    frame = make_research_frame()
    frame["board"] = ["main_board", "main_board", "main_board", "star_market", "star_market", "star_market"]
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], group_by=["board"])

    result = engine.evaluate(frame, request)

    assert not result.group_summary.empty
    assert list(result.group_summary.columns) == [
        "group_by", "group_value", "horizon", "event_count",
        "mean_forward_return", "median_forward_return", "win_rate",
    ]
    # One event per group: 000001.SZ on 2026-01-05 for main_board, 000002.SZ on 2026-01-06 for star_market
    main_row = result.group_summary[result.group_summary["group_value"] == "main_board"].iloc[0]
    assert main_row["group_by"] == "board"
    assert main_row["horizon"] == 1
    assert main_row["event_count"] == 1
    assert main_row["mean_forward_return"] == pytest.approx(0.1)
    assert main_row["win_rate"] == 1.0
    star_row = result.group_summary[result.group_summary["group_value"] == "star_market"].iloc[0]
    assert star_row["event_count"] == 1
    assert star_row["mean_forward_return"] == pytest.approx(0.1)


def test_evaluation_engine_builds_group_summary_for_multiple_columns():
    frame = make_research_frame()
    frame["board"] = ["main_board", "main_board", "main_board", "star_market", "star_market", "star_market"]
    frame["industry"] = ["bank", "bank", "bank", "tech", "tech", "tech"]
    engine = EvaluationEngine()
    request = EvaluationRequest(
        signal_expression="rsi_2 < 10",
        forward_horizons=[1],
        group_by=["board", "industry"],
    )

    result = engine.evaluate(frame, request)

    board_values = set(result.group_summary[result.group_summary["group_by"] == "board"]["group_value"])
    industry_values = set(result.group_summary[result.group_summary["group_by"] == "industry"]["group_value"])
    assert board_values == {"main_board", "star_market"}
    assert industry_values == {"bank", "tech"}


def test_evaluation_engine_builds_group_summary_for_multiple_horizons():
    frame = make_research_frame()
    frame["board"] = ["main_board", "main_board", "main_board", "star_market", "star_market", "star_market"]
    engine = EvaluationEngine()
    request = EvaluationRequest(
        signal_expression="rsi_2 < 10",
        forward_horizons=[1, 2],
        group_by=["board"],
    )

    result = engine.evaluate(frame, request)

    horizons = set(result.group_summary["horizon"])
    assert horizons == {1, 2}


def test_evaluation_engine_group_summary_includes_adjusted_metrics_when_cost_is_set():
    frame = make_research_frame()
    frame["board"] = ["main_board", "main_board", "main_board", "star_market", "star_market", "star_market"]
    engine = EvaluationEngine()
    request = EvaluationRequest(
        signal_expression="rsi_2 < 10",
        forward_horizons=[1],
        group_by=["board"],
        round_trip_cost_rate=0.02,
    )

    result = engine.evaluate(frame, request)

    assert "round_trip_cost_rate" in result.group_summary.columns
    assert "mean_adjusted_forward_return" in result.group_summary.columns
    assert "median_adjusted_forward_return" in result.group_summary.columns
    assert "adjusted_win_rate" in result.group_summary.columns
    main_row = result.group_summary[result.group_summary["group_value"] == "main_board"].iloc[0]
    assert main_row["round_trip_cost_rate"] == pytest.approx(0.02)
    assert main_row["mean_adjusted_forward_return"] == pytest.approx(0.08)
    assert main_row["adjusted_win_rate"] == 1.0


def test_evaluation_engine_raises_on_missing_group_column():
    engine = EvaluationEngine()
    request = EvaluationRequest(
        signal_expression="rsi_2 < 10",
        forward_horizons=[1],
        group_by=["board"],
    )

    with pytest.raises(ValueError, match="missing requested group columns"):
        engine.evaluate(make_research_frame(), request)


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


def test_random_baseline_empty_when_seed_is_none():
    result = EvaluationEngine().evaluate(
        make_research_frame(),
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1]),
    )
    assert result.random_baseline_summary.empty


def test_random_baseline_deterministic_with_fixed_seed():
    engine = EvaluationEngine()
    request = EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], random_baseline_seed=42)

    result1 = engine.evaluate(make_research_frame(), request)
    result2 = engine.evaluate(make_research_frame(), request)

    assert not result1.random_baseline_summary.empty
    assert result1.random_baseline_summary.equals(result2.random_baseline_summary)


def test_random_baseline_different_seeds_produce_different_baselines():
    engine = EvaluationEngine()
    result_a = engine.evaluate(
        make_research_frame(),
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], random_baseline_seed=42),
    )
    result_b = engine.evaluate(
        make_research_frame(),
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], random_baseline_seed=99),
    )
    assert not result_a.random_baseline_summary.empty
    assert not result_b.random_baseline_summary.empty
    assert not result_a.random_baseline_summary.equals(result_b.random_baseline_summary)


def test_random_baseline_has_correct_shape():
    result = EvaluationEngine().evaluate(
        make_research_frame(),
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], random_baseline_seed=42),
    )
    df = result.random_baseline_summary
    assert list(df.columns) == [
        "horizon", "event_count", "mean_forward_return", "median_forward_return", "win_rate",
    ]
    assert len(df) == 1
    assert df.iloc[0]["horizon"] == 1
    assert df.iloc[0]["event_count"] == 2


def test_random_baseline_handles_multiple_horizons():
    result = EvaluationEngine().evaluate(
        make_research_frame(),
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1, 2], random_baseline_seed=42),
    )
    df = result.random_baseline_summary
    assert len(df) == 2
    assert set(df["horizon"]) == {1, 2}


def test_random_baseline_returns_null_when_no_events():
    frame = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ"],
            "trade_date": pd.to_datetime(["2026-01-05", "2026-01-06"]),
            "close": [10.0, 11.0],
            "rsi_2": [20.0, 25.0],  # no signal triggered
        }
    )
    result = EvaluationEngine().evaluate(
        frame,
        EvaluationRequest(signal_expression="rsi_2 < 10", forward_horizons=[1], random_baseline_seed=42),
    )
    df = result.random_baseline_summary
    assert len(df) == 1
    assert df.iloc[0]["event_count"] == 0
    assert df.iloc[0]["mean_forward_return"] is None
