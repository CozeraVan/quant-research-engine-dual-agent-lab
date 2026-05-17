import pytest

from quant_research_engine.portfolio.weights import build_target_weights


def test_build_target_weights_equal_weight():
    weights = build_target_weights(["000001.SZ", "000002.SZ"], model="equal_weight")

    assert weights == {"000001.SZ": 0.5, "000002.SZ": 0.5}


def test_build_target_weights_score_weight_normalizes_positive_scores():
    weights = build_target_weights(
        ["000001.SZ", "000002.SZ", "600000.SH"],
        model="score_weight",
        scores={"000001.SZ": 1.0, "000002.SZ": 3.0, "600000.SH": -5.0},
    )

    assert weights == {"000001.SZ": 0.25, "000002.SZ": 0.75, "600000.SH": 0.0}


def test_build_target_weights_score_weight_falls_back_to_equal_when_scores_are_not_positive():
    weights = build_target_weights(
        ["000001.SZ", "000002.SZ"],
        model="score_weight",
        scores={"000001.SZ": 0.0, "000002.SZ": -1.0},
    )

    assert weights == {"000001.SZ": 0.5, "000002.SZ": 0.5}


def test_build_target_weights_inverse_volatility():
    weights = build_target_weights(
        ["000001.SZ", "000002.SZ"],
        model="inverse_volatility",
        volatilities={"000001.SZ": 0.2, "000002.SZ": 0.1},
    )

    assert weights["000001.SZ"] == pytest.approx(1 / 3)
    assert weights["000002.SZ"] == pytest.approx(2 / 3)


def test_build_target_weights_rejects_unknown_model():
    with pytest.raises(ValueError, match="Unsupported weight model"):
        build_target_weights(["000001.SZ"], model="unknown")
