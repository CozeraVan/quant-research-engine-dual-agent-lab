import pandas as pd
import pytest

from quant_research_engine.evaluation.signals import evaluate_expression_signal


def test_evaluate_expression_signal_supports_simple_comparison():
    frame = pd.DataFrame({"rsi_2": [5.0, 15.0, 9.0]})

    signal = evaluate_expression_signal(frame, "rsi_2 < 10")

    assert signal.tolist() == [True, False, True]


def test_evaluate_expression_signal_supports_boolean_and():
    frame = pd.DataFrame({"rsi_2": [5.0, 5.0, 15.0], "close": [11.0, 9.0, 11.0], "sma_20": [10.0, 10.0, 10.0]})

    signal = evaluate_expression_signal(frame, "rsi_2 < 10 and close > sma_20")

    assert signal.tolist() == [True, False, False]


def test_evaluate_expression_signal_rejects_function_calls():
    frame = pd.DataFrame({"rsi_2": [5.0]})

    with pytest.raises(ValueError, match="Unsupported expression"):
        evaluate_expression_signal(frame, "__import__('os').system('echo bad')")


def test_evaluate_expression_signal_rejects_unknown_columns():
    frame = pd.DataFrame({"rsi_2": [5.0]})

    with pytest.raises(ValueError, match="Unknown signal field"):
        evaluate_expression_signal(frame, "missing < 10")


def test_referenced_fields_collects_column_names():
    from quant_research_engine.evaluation.signals import referenced_fields

    fields = referenced_fields("((ema_5 > ema_200) and (ema_5.shift(1) <= ema_200.shift(1)))")
    assert fields == {"ema_5", "ema_200"}
    assert referenced_fields("close > open and amount > 1000") == {"close", "open", "amount"}
    assert referenced_fields(None) == set()
    assert referenced_fields("") == set()
