from pathlib import Path
import textwrap

import pytest
import yaml

import pandas as pd

from quant_research_engine.evaluation.signals import evaluate_expression_signal
from quant_research_engine.strategies.compiler import (
    FactorRequirement,
    _INDICATOR_CATALOG,
    _build_table_name,
    _col_bollinger,
    _col_macd,
    _col_simple,
    compile_entry,
    compile_to_strategy_spec_dict,
    parse_high_level_entry,
)
from quant_research_engine.strategies.spec import StrategySpec


# ---------------------------------------------------------------------------
# column name builders
# ---------------------------------------------------------------------------

def test_col_simple_builds_indicator_period():
    assert _col_simple("rsi", "close", 2, {}, None) == "rsi_2"
    assert _col_simple("ema", "typical", 200, {}, None) == "ema_200"


def test_col_simple_raises_on_missing_period():
    with pytest.raises(ValueError, match="period is required"):
        _col_simple("rsi", "close", None, {}, None)


def test_col_macd_default_output():
    assert _col_macd("macd", "close", None, {"fast": 12, "slow": 26, "signal": 9}, None) == "macd_12_26_9"


def test_col_macd_signal_output():
    assert _col_macd("macd", "close", None, {"fast": 12, "slow": 26, "signal": 9}, "signal") == "macd_signal_12_26_9"


def test_col_macd_raises_on_missing_params():
    with pytest.raises(ValueError, match="MACD requires params"):
        _col_macd("macd", "close", None, {}, None)


def test_col_bollinger_upper():
    col = _col_bollinger("bollinger", "close", 20, {"stddev": 2.0}, "upper")
    assert col == "bbu_20_2_0_2_0"


def test_col_bollinger_lower():
    col = _col_bollinger("bollinger", "close", 20, {"stddev": 2.0}, "lower")
    assert col == "bbl_20_2_0_2_0"


def test_col_bollinger_raises_on_missing_period():
    with pytest.raises(ValueError, match="period is required"):
        _col_bollinger("bollinger", "close", None, {"stddev": 2.0}, "upper")


# ---------------------------------------------------------------------------
# table name builder
# ---------------------------------------------------------------------------

def test_build_table_name():
    assert _build_table_name("momentum", "close") == "stock_daily_momentum_close"
    assert _build_table_name("volatility", "hlc3") == "stock_daily_volatility_hlc3"


# ---------------------------------------------------------------------------
# indicator catalog
# ---------------------------------------------------------------------------

def test_catalog_has_expected_indicators():
    assert "rsi" in _INDICATOR_CATALOG
    assert "ema" in _INDICATOR_CATALOG
    assert "macd" in _INDICATOR_CATALOG
    assert "bollinger" in _INDICATOR_CATALOG
    assert "atr" in _INDICATOR_CATALOG
    assert _INDICATOR_CATALOG["rsi"][0] == "momentum"
    assert _INDICATOR_CATALOG["ema"][0] == "overlap"
    assert _INDICATOR_CATALOG["macd"][0] == "momentum"
    assert _INDICATOR_CATALOG["bollinger"][0] == "volatility"


# ---------------------------------------------------------------------------
# compile_entry — RSI2 (simple, single factor)
# ---------------------------------------------------------------------------

RSI2_YAML = textwrap.dedent("""\
    strategy:
      id: rsi2_oversold_reversal
      name: RSI2 Oversold Reversal
      family: mean_reversion
      direction: long_only
      version: "1.0.0"

    factor_requirements:
      - alias: rsi_fast
        indicator: rsi
        source: close
        period: 2
        required: true
        reason: entry and exit threshold signal

    rules:
      entry:
        all:
          - alias: rsi_fast
            operator: "<"
            value: 10
      exit:
        any:
          - alias: rsi_fast
            operator: ">"
            value: 70
      risk:
        stop_loss_pct: 0.08
        max_holding_days: 5

    experiment:
      id: rsi2_smoke
      frequency: daily
      market: ashare
      start: 2024-01-01
      end: 2024-02-01
      universe:
        include: all_a
        exclude_st: true
      execution:
        signal_date: t
        entry_execution: t_plus_1_open
        exit_execution: t_plus_1_open
        market_profile: ashare_daily_default
      capital:
        initial_cash: 1000000
      output:
        dir: outputs/rsi2_smoke/
""")


def test_compile_rsi2_factor_targets():
    raw = yaml.safe_load(RSI2_YAML)
    entry = compile_entry(raw)
    assert entry.ok
    assert entry.strategy_id == "rsi2_oversold_reversal"
    assert len(entry.factor_targets) == 1
    assert entry.factor_targets["rsi_fast"] == "factors.stock_daily_momentum_close.rsi_2"


def test_compile_rsi2_signal_expression():
    raw = yaml.safe_load(RSI2_YAML)
    entry = compile_entry(raw)
    assert entry.signal_expression is not None
    assert "rsi_fast" in entry.signal_expression
    assert "< 10" in entry.signal_expression
    assert entry.exit_signal_expression is not None
    assert "> 70" in entry.exit_signal_expression


def test_compile_rsi2_to_strategy_spec():
    raw = yaml.safe_load(RSI2_YAML)
    entry = compile_entry(raw)
    spec_dict = compile_to_strategy_spec_dict(entry)
    spec = StrategySpec.from_mapping(spec_dict)
    assert spec.name == "rsi2_oversold_reversal"
    assert len(spec.factor_fields) == 1
    assert spec.factor_fields[0].logical_name == "rsi_fast"
    assert spec.factor_fields[0].qualified_table == "factors.stock_daily_momentum_close"
    assert spec.factor_fields[0].source_column == "rsi_2"
    assert spec.stop_loss_pct == 0.08
    assert spec.holding_days == 5


# ---------------------------------------------------------------------------
# compile_entry — EMA200 + Bollinger (multi-factor, multi-condition)
# ---------------------------------------------------------------------------

EMA200_BB_YAML = textwrap.dedent("""\
    strategy:
      id: ema200_bollinger_reversal
      name: EMA200 Bollinger Band Reversal
      family: mean_reversion
      direction: long_only

    factor_requirements:
      - alias: ema_200
        indicator: ema
        source: typical
        period: 200
        required: true
        reason: trend filter
      - alias: bb_upper
        indicator: bollinger
        source: close
        period: 20
        params:
          stddev: 2.0
        output: upper
        required: true
        reason: exit threshold
      - alias: bb_lower
        indicator: bollinger
        source: close
        period: 20
        params:
          stddev: 2.0
        output: lower
        required: true
        reason: entry threshold

    rules:
      entry:
        all:
          - alias: close
            operator: ">"
            alias_b: ema_200
          - alias: close
            operator: "<="
            alias_b: bb_lower
      exit:
        any:
          - alias: close
            operator: ">="
            alias_b: bb_upper

    experiment:
      id: ema200_bb_smoke
      frequency: daily
      market: ashare
      start: 2024-01-01
      end: 2024-02-01
      universe:
        include: all_a
      execution:
        signal_date: t
        entry_execution: t_plus_1_open
        exit_execution: t_plus_1_open
        market_profile: ashare_daily_default
      capital:
        initial_cash: 1000000
      output:
        dir: outputs/ema200_bb_smoke/
""")


def test_compile_ema200_bb_factor_targets():
    raw = yaml.safe_load(EMA200_BB_YAML)
    entry = compile_entry(raw)
    assert entry.ok
    assert len(entry.factor_targets) == 3
    assert entry.factor_targets["ema_200"] == "factors.stock_daily_overlap_typical.ema_200"
    assert entry.factor_targets["bb_upper"] == "factors.stock_daily_volatility_close.bbu_20_2_0_2_0"
    assert entry.factor_targets["bb_lower"] == "factors.stock_daily_volatility_close.bbl_20_2_0_2_0"


def test_compile_ema200_bb_signal_expression():
    raw = yaml.safe_load(EMA200_BB_YAML)
    entry = compile_entry(raw)
    assert entry.signal_expression is not None
    # Expressions use alias names (not full factor target paths) for runtime compatibility
    assert "(close > ema_200)" in entry.signal_expression
    assert "(close <= bb_lower)" in entry.signal_expression
    assert entry.exit_signal_expression is not None
    assert "(close >= bb_upper)" in entry.exit_signal_expression


def test_compile_ema200_bb_to_strategy_spec():
    raw = yaml.safe_load(EMA200_BB_YAML)
    entry = compile_entry(raw)
    spec_dict = compile_to_strategy_spec_dict(entry)
    spec = StrategySpec.from_mapping(spec_dict)
    assert spec.name == "ema200_bollinger_reversal"
    assert len(spec.factor_fields) == 3
    aliases = {f.logical_name for f in spec.factor_fields}
    assert aliases == {"ema_200", "bb_upper", "bb_lower"}


# ---------------------------------------------------------------------------
# compile_entry — MACD (multi-output, crossover)
# ---------------------------------------------------------------------------

MACD_YAML = textwrap.dedent("""\
    strategy:
      id: macd_zero_cross_momentum
      name: MACD Zero-Cross Momentum
      family: momentum
      direction: long_only

    factor_requirements:
      - alias: macd_line
        indicator: macd
        source: close
        params:
          fast: 12
          slow: 26
          signal: 9
        output: macd
        required: true
        reason: MACD line for crossover
      - alias: macd_signal
        indicator: macd
        source: close
        params:
          fast: 12
          slow: 26
          signal: 9
        output: signal
        required: true
        reason: MACD signal line for crossover

    rules:
      entry:
        all:
          - alias: macd_line
            operator: crosses_above
            alias_b: macd_signal
          - alias: macd_line
            operator: "<"
            value: 0

    experiment:
      id: macd_smoke
      frequency: daily
      market: ashare
      start: 2024-01-01
      end: 2024-02-01
      universe:
        include: all_a
      execution:
        signal_date: t
        entry_execution: t_plus_1_open
        exit_execution: t_plus_1_open
        market_profile: ashare_daily_default
      capital:
        initial_cash: 1000000
      output:
        dir: outputs/macd_smoke/
""")


def test_compile_macd_factor_targets():
    raw = yaml.safe_load(MACD_YAML)
    entry = compile_entry(raw)
    assert len(entry.factor_targets) == 2
    assert entry.factor_targets["macd_line"] == "factors.stock_daily_momentum_close.macd_12_26_9"
    assert entry.factor_targets["macd_signal"] == "factors.stock_daily_momentum_close.macd_signal_12_26_9"


def test_compile_macd_crossover_warning():
    raw = yaml.safe_load(MACD_YAML)
    entry = compile_entry(raw)
    assert entry.ok  # warning only, not error
    assert any("crossover" in i.message.lower() for i in entry.issues)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

def test_missing_strategy_section_raises():
    with pytest.raises(ValueError, match="strategy"):
        compile_entry({"factor_requirements": [], "experiment": {}})


def test_missing_factor_requirements_raises():
    with pytest.raises(ValueError, match="factor_requirements"):
        compile_entry({"strategy": {"id": "s", "name": "n", "family": "f", "direction": "d"}, "experiment": {}})


def test_unknown_indicator_produces_error():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: test
          name: Test
          family: custom
          direction: long_only
        factor_requirements:
          - alias: unknown_factor
            indicator: imaginary_indicator
            source: close
            period: 10
            required: true
            reason: testing
        experiment:
          id: test_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert not entry.ok
    assert any("unknown indicator" in i.message for i in entry.issues)


def test_duplicate_alias_produces_error():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: test
          name: Test
          family: custom
          direction: long_only
        factor_requirements:
          - alias: dup
            indicator: rsi
            source: close
            period: 2
            required: true
            reason: first
          - alias: dup
            indicator: rsi
            source: close
            period: 14
            required: true
            reason: second
        experiment:
          id: test_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert not entry.ok
    assert any("duplicate alias" in i.message for i in entry.issues)


def test_builtin_alias_shadow_produces_error():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: test
          name: Test
          family: custom
          direction: long_only
        factor_requirements:
          - alias: close
            indicator: rsi
            source: close
            period: 2
            required: true
            reason: shadows built-in
        experiment:
          id: test_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert not entry.ok
    assert any("shadows a built-in" in i.message for i in entry.issues)


def test_missing_experiment_raises():
    with pytest.raises(ValueError, match="experiment"):
        compile_entry({
            "strategy": {"id": "s", "name": "n", "family": "f", "direction": "d"},
            "factor_requirements": [],
        })


# ---------------------------------------------------------------------------
# parse_high_level_entry file round-trip
# ---------------------------------------------------------------------------

def test_parse_high_level_entry_from_file(tmp_path):
    path = tmp_path / "strategy.yaml"
    path.write_text(RSI2_YAML, encoding="utf-8")
    raw = parse_high_level_entry(path)
    assert raw["strategy"]["id"] == "rsi2_oversold_reversal"


# ---------------------------------------------------------------------------
# FactorRequirement defaults
# ---------------------------------------------------------------------------

def test_factor_requirement_defaults():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: test
          name: Test
          family: custom
          direction: long_only
        factor_requirements:
          - alias: rsi_14
            indicator: rsi
            source: close
            period: 14
            required: false
            reason: optional factor
        experiment:
          id: test_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert entry.ok
    assert entry.factor_targets["rsi_14"] == "factors.stock_daily_momentum_close.rsi_14"


# ---------------------------------------------------------------------------
# compile_to_strategy_spec_dict
# ---------------------------------------------------------------------------

def test_compile_to_strategy_spec_dict_includes_universe_defaults():
    raw = yaml.safe_load(RSI2_YAML)
    entry = compile_entry(raw)
    d = compile_to_strategy_spec_dict(entry)
    assert d["universe"]["exclude_st"] is True
    assert d["holding"]["max_holding_days"] == 5
    assert d["risk"]["stop_loss_pct"] == 0.08


def test_compile_to_strategy_spec_dict_no_rules_exit():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: no_exit_strat
          name: No Exit
          family: custom
          direction: long_only
        factor_requirements:
          - alias: rsi_2
            indicator: rsi
            source: close
            period: 2
            required: true
            reason: entry
        rules:
          entry:
            all:
              - alias: rsi_2
                operator: "<"
                value: 30
        experiment:
          id: no_exit_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert entry.ok
    d = compile_to_strategy_spec_dict(entry)
    assert d["signal"]["exit"] is None


def test_compile_to_strategy_spec_dict_no_rules_section():
    raw = yaml.safe_load(textwrap.dedent("""\
        strategy:
          id: no_rules
          name: No Rules
          family: custom
          direction: long_only
        factor_requirements:
          - alias: rsi_2
            indicator: rsi
            source: close
            period: 2
            required: true
            reason: entry
        experiment:
          id: no_rules_smoke
          frequency: daily
          market: ashare
          start: 2024-01-01
          end: 2024-02-01
          universe:
            include: all_a
          execution:
            signal_date: t
            entry_execution: t_plus_1_open
            exit_execution: t_plus_1_open
            market_profile: ashare_daily_default
          capital:
            initial_cash: 1000000
    """))
    entry = compile_entry(raw)
    assert entry.ok
    d = compile_to_strategy_spec_dict(entry)
    assert d["signal"]["entry"] == "close > 0"  # fallback


# ---------------------------------------------------------------------------
# End-to-end runtime compatibility
# ---------------------------------------------------------------------------

def test_compile_to_strategy_spec_evaluate_expression_rsi2():
    """Verify compiled expression evaluates correctly with StrategySpec + signals."""
    raw = yaml.safe_load(RSI2_YAML)
    entry = compile_entry(raw)
    assert entry.ok
    spec_dict = compile_to_strategy_spec_dict(entry)
    spec = StrategySpec.from_mapping(spec_dict)

    # Verify factor_fields map aliases to qualified targets
    assert spec.factor_fields[0].logical_name == "rsi_fast"
    assert spec.factor_fields[0].qualified_table == "factors.stock_daily_momentum_close"
    assert spec.factor_fields[0].source_column == "rsi_2"

    # Build a mock frame with alias-named columns (as the data assembler would)
    # Entry: rsi_fast < 10 → rows 0 (5.0) and 2 (8.0) are entry signals
    # Exit:  rsi_fast > 70 → row 1 (80.0) is exit signal
    frame = pd.DataFrame({
        "rsi_fast": [5.0, 80.0, 8.0],
        "close": [100.0, 101.0, 99.0],
        "open": [99.0, 100.0, 100.0],
        "high": [101.0, 102.0, 100.0],
        "low": [98.0, 99.0, 98.0],
        "pre_close": [100.0, 100.0, 101.0],
        "vol": [1000000, 1500000, 1200000],
        "amount": [1e8, 1.5e8, 1.2e8],
    })

    # Expression should use alias names and be evaluable by the signal engine
    signal = evaluate_expression_signal(frame, spec.signal_expression)
    assert signal.tolist() == [True, False, True]

    if spec.exit_signal_expression:
        exit_signal = evaluate_expression_signal(frame, spec.exit_signal_expression)
        assert exit_signal.tolist() == [False, True, False]


def test_compile_to_strategy_spec_evaluate_expression_ema200_bb():
    """Verify EMA200+Bollinger compiled expressions evaluate correctly."""
    raw = yaml.safe_load(EMA200_BB_YAML)
    entry = compile_entry(raw)
    assert entry.ok
    spec_dict = compile_to_strategy_spec_dict(entry)
    spec = StrategySpec.from_mapping(spec_dict)

    # Verify factor_fields map aliases to qualified targets
    logical_names = {f.logical_name for f in spec.factor_fields}
    assert logical_names == {"ema_200", "bb_upper", "bb_lower"}

    # Build mock frame with alias-named columns
    # Entry: close > ema_200 AND close <= bb_lower
    # Row 0: close 95.0 > 100.0 → skip. Row 1: close 101.0 > 100.0 AND <= 102.0 → entry.
    # Row 2: close 109.0 > 100.0 but 109.0 > 92.0 → no entry.
    # Exit: close >= bb_upper (108.0). Row 2: 109.0 >= 108.0 → exit.
    frame = pd.DataFrame({
        "close": [95.0, 101.0, 109.0],
        "open": [94.0, 100.0, 105.0],
        "high": [96.0, 102.0, 110.0],
        "low": [93.0, 99.0, 104.0],
        "pre_close": [96.0, 95.0, 101.0],
        "vol": [1000000, 1500000, 1200000],
        "amount": [1e8, 1.5e8, 1.2e8],
        "ema_200": [100.0, 100.0, 100.0],
        "bb_upper": [108.0, 108.0, 108.0],
        "bb_lower": [102.0, 102.0, 92.0],
    })

    # Entry: close > ema_200 AND close <= bb_lower
    entry_signal = evaluate_expression_signal(frame, spec.signal_expression)
    assert entry_signal.tolist() == [False, True, False]

    # Exit: close >= bb_upper
    if spec.exit_signal_expression:
        exit_signal = evaluate_expression_signal(frame, spec.exit_signal_expression)
        assert exit_signal.tolist() == [False, False, True]
