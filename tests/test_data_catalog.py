import pytest

from quant_research_engine.data.catalog import FactorFieldRequest


def test_factor_field_request_parses_qualified_factor_target():
    request = FactorFieldRequest.from_target("ema_20", "factors.stock_daily_overlap_close.ema_20")

    assert request.logical_name == "ema_20"
    assert request.source_schema == "factors"
    assert request.source_table == "stock_daily_overlap_close"
    assert request.source_column == "ema_20"
    assert request.qualified_table == "factors.stock_daily_overlap_close"


def test_factor_field_request_defaults_schema_to_factors():
    request = FactorFieldRequest.from_target("rsi_2", "stock_daily_momentum_close.rsi_2")

    assert request.source_schema == "factors"
    assert request.source_table == "stock_daily_momentum_close"
    assert request.source_column == "rsi_2"


def test_factor_field_request_rejects_invalid_target():
    with pytest.raises(ValueError, match="Invalid factor target"):
        FactorFieldRequest.from_target("bad", "factors.stock_daily_overlap_close")
