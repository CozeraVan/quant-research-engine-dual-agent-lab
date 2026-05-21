from datetime import date

import pytest

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.preflight import (
    PreflightCheck,
    PreflightReport,
    PreflightRequest,
)
from quant_research_engine.strategies.missing_factor import (
    MissingFactorRequest,
    _build_missing_factor,
    _parse_category,
    _parse_column,
    _parse_source,
    emit_missing_factor_requests,
    extract_missing_factors,
)


class FakeSpec:
    """Minimal fake that exposes the two fields extract_missing_factors uses."""

    def __init__(self, name, factor_fields):
        self.name = name
        self.factor_fields = factor_fields


def _make_factor(logical_name, target):
    return FactorFieldRequest.from_target(logical_name, target)


def _make_report(*, checks=None, status="ok"):
    return PreflightReport(
        status=status,
        market_rows=3,
        latest_market_date="2026-01-05",
        requested_symbols=["000001.SZ"],
        loaded_symbols=["000001.SZ"],
        missing_symbols=[],
        factor_coverages={},
        checks=list(checks or []),
    )


def _make_request(start="2026-01-02", end="2026-01-05"):
    return PreflightRequest(
        ts_codes=["000001.SZ"],
        start=date.fromisoformat(start),
        end=date.fromisoformat(end),
        market_fields=["close"],
        factor_fields=[],
    )


# ---------------------------------------------------------------------------
# MissingFactorRequest
# ---------------------------------------------------------------------------

def test_missing_factor_request_to_dict_round_trips_all_fields():
    mf = MissingFactorRequest(
        strategy_id="rsi2_oversold_reversal",
        alias="rsi_fast",
        indicator="rsi",
        category="momentum",
        source="close",
        period=2,
        params={},
        output=None,
        expected_table="factors.stock_daily_momentum_close",
        expected_column="rsi_2",
        date_range={"start": "2024-01-01", "end": "2024-12-31"},
        reason="entry and exit threshold signal",
        required=True,
    )
    d = mf.to_dict()
    assert d["strategy_id"] == "rsi2_oversold_reversal"
    assert d["alias"] == "rsi_fast"
    assert d["indicator"] == "rsi"
    assert d["category"] == "momentum"
    assert d["source"] == "close"
    assert d["period"] == 2
    assert d["params"] == {}
    assert d["output"] is None
    assert d["expected_table"] == "factors.stock_daily_momentum_close"
    assert d["expected_column"] == "rsi_2"
    assert d["date_range"] == {"start": "2024-01-01", "end": "2024-12-31"}
    assert d["reason"] == "entry and exit threshold signal"
    assert d["required"] is True


def test_missing_factor_request_with_params_and_output():
    mf = MissingFactorRequest(
        strategy_id="macd_strategy",
        alias="macd_line",
        indicator="macd",
        category="momentum",
        source="close",
        period=None,
        params={"fast": 12, "slow": 26, "signal": 9},
        output="macd",
        expected_table="factors.stock_daily_momentum_close",
        expected_column="macd_12_26_9",
        date_range={"start": "2024-01-01", "end": "2024-02-01"},
        reason="MACD line for zero-axis position",
        required=True,
    )
    d = mf.to_dict()
    assert d["params"] == {"fast": 12, "slow": 26, "signal": 9}
    assert d["output"] == "macd"
    assert d["period"] is None


# ---------------------------------------------------------------------------
# Table name parsing
# ---------------------------------------------------------------------------

def test_parse_category_extracts_from_standard_table():
    assert _parse_category("stock_daily_momentum_close") == "momentum"
    assert _parse_category("stock_daily_overlap_typical_price") == "overlap"
    assert _parse_category("stock_daily_volatility_close") == "volatility"
    assert _parse_category("stock_daily_volume_close") == "volume"


def test_parse_category_returns_none_for_non_standard_table():
    assert _parse_category("custom_table") is None
    assert _parse_category("stock_daily") is None


def test_parse_source_extracts_price_source():
    assert _parse_source("stock_daily_momentum_close") == "close"
    assert _parse_source("stock_daily_overlap_typical_price") == "typical_price"
    assert _parse_source("stock_daily_volatility_hlc3") == "hlc3"


# ---------------------------------------------------------------------------
# Column name parsing
# ---------------------------------------------------------------------------

def test_parse_column_simple_rsi():
    indicator, period, params, output = _parse_column("rsi_2")
    assert indicator == "rsi"
    assert period == 2
    assert params == {}
    assert output is None


def test_parse_column_simple_ema():
    indicator, period, params, output = _parse_column("ema_200")
    assert indicator == "ema"
    assert period == 200
    assert params == {}
    assert output is None


def test_parse_column_bollinger_upper():
    indicator, period, params, output = _parse_column("bbu_20_2_0_2_0")
    assert indicator == "bollinger"
    assert period == 20
    assert params == {"stddev": 2.0}
    assert output == "upper"


def test_parse_column_bollinger_lower():
    indicator, period, params, output = _parse_column("bbl_20_2_0_2_0")
    assert indicator == "bollinger"
    assert period == 20
    assert params == {"stddev": 2.0}
    assert output == "lower"


def test_parse_column_macd_line():
    indicator, period, params, output = _parse_column("macd_12_26_9")
    assert indicator == "macd"
    assert period is None
    assert params == {"fast": 12, "slow": 26, "signal": 9}
    assert output == "macd"


def test_parse_column_macd_signal():
    indicator, period, params, output = _parse_column("macd_signal_12_26_9")
    assert indicator == "macd"
    assert period is None
    assert params == {"fast": 12, "slow": 26, "signal": 9}
    assert output == "signal"


def test_parse_column_unknown_indicator_falls_back_to_column_name():
    indicator, period, params, output = _parse_column("custom_factor_5")
    assert indicator == "custom_factor_5"
    assert period == 5
    assert params == {}
    assert output is None


def test_parse_column_no_numeric_suffix():
    indicator, period, params, output = _parse_column("my_custom_factor")
    assert indicator == "my_custom_factor"
    assert period is None


# ---------------------------------------------------------------------------
# extract_missing_factors
# ---------------------------------------------------------------------------

def test_no_missing_factors_when_all_checks_pass():
    spec = FakeSpec("test_strategy", [_make_factor("rsi_2", "factors.stock_daily_momentum_close.rsi_2")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:rsi_2", status="ok", message="found"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert result == []


def test_no_missing_factors_when_checks_are_warnings_not_errors():
    spec = FakeSpec("test_strategy", [_make_factor("rsi_2", "factors.stock_daily_momentum_close.rsi_2")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:rsi_2", status="warning", message="low coverage"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert result == []


def test_missing_factor_when_table_does_not_exist():
    spec = FakeSpec("rsi2_strategy", [_make_factor("rsi_2", "factors.stock_daily_momentum_close.rsi_2")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:rsi_2", status="error", message="missing factor table factors.stock_daily_momentum_close"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert len(result) == 1
    mf = result[0]
    assert mf.strategy_id == "rsi2_strategy"
    assert mf.alias == "rsi_2"
    assert mf.expected_table == "factors.stock_daily_momentum_close"
    assert mf.expected_column == "rsi_2"
    assert mf.required is True
    assert mf.date_range == {"start": "2026-01-02", "end": "2026-01-05"}


def test_missing_factor_when_column_does_not_exist():
    spec = FakeSpec("ema_strategy", [_make_factor("ema_200", "factors.stock_daily_overlap_typical_price.ema_200")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:ema_200", status="error", message="missing factor column factors.stock_daily_overlap_typical_price.ema_200"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert len(result) == 1
    mf = result[0]
    assert mf.alias == "ema_200"
    assert mf.indicator == "ema"
    assert mf.period == 200
    assert mf.category == "overlap"
    assert mf.source == "typical_price"


def test_multiple_missing_factors_are_sorted():
    spec = FakeSpec("multi_strategy", [
        _make_factor("macd_line", "factors.stock_daily_momentum_close.macd_12_26_9"),
        _make_factor("rsi_2", "factors.stock_daily_momentum_close.rsi_2"),
        _make_factor("ema_200", "factors.stock_daily_overlap_typical_price.ema_200"),
    ])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:ema_200", status="error", message="missing"),
        PreflightCheck(name="factor_schema:macd_line", status="error", message="missing"),
        PreflightCheck(name="factor_schema:rsi_2", status="error", message="missing"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert len(result) == 3
    aliases = [mf.alias for mf in result]
    assert aliases == ["ema_200", "macd_line", "rsi_2"]


def test_missing_factor_ignores_unknown_logical_name():
    spec = FakeSpec("test_strategy", [_make_factor("known", "factors.stock_daily_momentum_close.rsi_2")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="factor_schema:unknown_alias", status="error", message="missing"),
        PreflightCheck(name="factor_schema:known", status="error", message="missing"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert len(result) == 1
    assert result[0].alias == "known"


def test_extract_missing_factors_ignores_non_schema_checks():
    spec = FakeSpec("test_strategy", [_make_factor("rsi_2", "factors.stock_daily_momentum_close.rsi_2")])
    request = _make_request()
    report = _make_report(checks=[
        PreflightCheck(name="market_rows", status="error", message="no data"),
        PreflightCheck(name="factor_coverage:rsi_2", status="error", message="bad coverage"),
    ])
    result = extract_missing_factors(report, spec, request)
    assert result == []


# ---------------------------------------------------------------------------
# emit_missing_factor_requests
# ---------------------------------------------------------------------------

def test_emit_writes_json_to_output_dir(tmp_path):
    mf = MissingFactorRequest(
        strategy_id="test",
        alias="rsi_2",
        indicator="rsi",
        category="momentum",
        source="close",
        period=2,
        params={},
        output=None,
        expected_table="factors.stock_daily_momentum_close",
        expected_column="rsi_2",
        date_range={"start": "2026-01-01", "end": "2026-01-05"},
        reason="needed",
        required=True,
    )
    path = emit_missing_factor_requests([mf], tmp_path)
    assert path == tmp_path / "missing_factor_requests.json"
    assert path.exists()
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["alias"] == "rsi_2"


def test_emit_empty_list_writes_empty_array(tmp_path):
    path = emit_missing_factor_requests([], tmp_path)
    assert path.exists()
    import json
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == []


def test_emit_creates_output_directory(tmp_path):
    out = tmp_path / "nested" / "output"
    mf = MissingFactorRequest(
        strategy_id="test",
        alias="x",
        indicator="x",
        category=None,
        source="close",
        period=None,
        params={},
        output=None,
        expected_table="factors.tbl",
        expected_column="col",
        date_range={"start": "2026-01-01", "end": "2026-01-05"},
        reason="needed",
        required=True,
    )
    path = emit_missing_factor_requests([mf], out)
    assert path.exists()
    assert path.parent == out


# ---------------------------------------------------------------------------
# _build_missing_factor
# ---------------------------------------------------------------------------

def test_build_missing_factor_derives_indicator_from_column():
    factor = _make_factor("rsi_fast", "factors.stock_daily_momentum_close.rsi_2")
    request = _make_request()
    mf = _build_missing_factor(
        strategy_id="st1",
        logical_name="rsi_fast",
        factor=factor,
        request=request,
    )
    assert mf.indicator == "rsi"
    assert mf.period == 2
    assert mf.category == "momentum"
    assert mf.source == "close"
    assert mf.required is True


def test_build_missing_factor_required_is_always_true():
    factor = _make_factor("opt_factor", "factors.stock_daily_volatility_close.atr_14")
    request = _make_request()
    mf = _build_missing_factor(
        strategy_id="st2",
        logical_name="opt_factor",
        factor=factor,
        request=request,
    )
    assert mf.required is True
