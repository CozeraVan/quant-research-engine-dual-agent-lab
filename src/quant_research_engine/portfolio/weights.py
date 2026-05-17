from __future__ import annotations

from collections.abc import Mapping


def build_target_weights(
    symbols: list[str],
    *,
    model: str = "equal_weight",
    scores: Mapping[str, float] | None = None,
    volatilities: Mapping[str, float] | None = None,
) -> dict[str, float]:
    if not symbols:
        return {}
    if model == "equal_weight":
        return _equal_weights(symbols)
    if model == "score_weight":
        return _positive_normalized_weights(symbols, scores or {})
    if model == "inverse_volatility":
        inverse_volatility_scores = {
            symbol: 1 / value
            for symbol, value in (volatilities or {}).items()
            if value > 0
        }
        return _positive_normalized_weights(symbols, inverse_volatility_scores)
    raise ValueError(f"Unsupported weight model: {model}")


def _equal_weights(symbols: list[str]) -> dict[str, float]:
    weight = 1 / len(symbols)
    return {symbol: weight for symbol in symbols}


def _positive_normalized_weights(symbols: list[str], values: Mapping[str, float]) -> dict[str, float]:
    positive_values = {symbol: max(float(values.get(symbol, 0.0)), 0.0) for symbol in symbols}
    total = sum(positive_values.values())
    if total <= 0:
        return _equal_weights(symbols)
    return {symbol: value / total for symbol, value in positive_values.items()}
