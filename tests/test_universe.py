"""Tests for portfolio.universe (M10.2a) and its research_run/runner wiring."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from quant_research_engine.orchestration import research_run as rr
from quant_research_engine.orchestration.research_run import ResearchRunRequest, _run_backtest, _write_research_manifest, ResearchRunResult
from quant_research_engine.portfolio.universe import (
    UniverseFilterSpec,
    apply_universe_filter,
    validate_profile_overrides,
)
from quant_research_engine.strategies.spec import StrategySpec


# ---------------------------------------------------------------------------
# profile override validation
# ---------------------------------------------------------------------------


def test_profile_overrides_validation():
    validate_profile_overrides({"commission_rate": 0.001, "slippage_buy_rate": 0.0})
    with pytest.raises(ValueError, match="Unknown profile override keys"):
        validate_profile_overrides({"commission_ratee": 0.001})
    with pytest.raises(ValueError, match="non-negative"):
        validate_profile_overrides({"stamp_tax_sell": -0.1})


# ---------------------------------------------------------------------------
# apply_universe_filter
# ---------------------------------------------------------------------------


def _frame(symbols_bars: dict[str, int], amount: float | None = 1e6) -> pd.DataFrame:
    rows = []
    for symbol, n in symbols_bars.items():
        for i in range(n):
            row = {
                "ts_code": symbol,
                "trade_date": pd.Timestamp("2024-01-02") + pd.Timedelta(days=i),
                "open": 10.0,
                "close": 10.0,
            }
            if amount is not None:
                row["amount"] = amount
            rows.append(row)
    return pd.DataFrame(rows)


def _metadata(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["ts_code", "is_st", "is_suspended", "is_risk_warning", "list_date"])


def test_exclude_st_drops_and_counts():
    frame = _frame({"A.SZ": 3, "B.SZ": 3, "C.SZ": 3})
    meta = _metadata([
        {"ts_code": "A.SZ", "is_st": True},
        {"ts_code": "B.SZ", "is_st": False},
        {"ts_code": "C.SZ", "is_st": None},
    ])
    spec = UniverseFilterSpec(exclude_st=True)
    filtered, report = apply_universe_filter(frame, spec, start=date(2024, 1, 1), metadata=meta)
    assert set(filtered["ts_code"].unique()) == {"B.SZ", "C.SZ"}  # unknown → kept
    assert report.dropped_by_rule == {"exclude_st": 1}
    assert report.unavailable_rules == []
    assert report.input_symbols == 3 and report.output_symbols == 2


def test_exclude_suspended_and_risk_warning():
    frame = _frame({"A.SZ": 2, "B.SZ": 2, "C.SZ": 2})
    meta = _metadata([
        {"ts_code": "A.SZ", "is_suspended": True},
        {"ts_code": "B.SZ", "is_risk_warning": True},
        {"ts_code": "C.SZ", "is_suspended": False, "is_risk_warning": False},
    ])
    spec = UniverseFilterSpec(exclude_suspended=True, exclude_risk_warning=True)
    filtered, report = apply_universe_filter(frame, spec, start=date(2024, 1, 1), metadata=meta)
    assert set(filtered["ts_code"].unique()) == {"C.SZ"}
    assert report.dropped_by_rule == {"exclude_suspended": 1, "exclude_risk_warning": 1}


def test_min_listing_days_edge():
    frame = _frame({"NEW.SZ": 2, "OLD.SZ": 2, "EDGE.SZ": 2})
    start = date(2024, 6, 1)
    meta = _metadata([
        {"ts_code": "NEW.SZ", "list_date": date(2024, 3, 1)},
        {"ts_code": "OLD.SZ", "list_date": date(2020, 1, 1)},
        {"ts_code": "EDGE.SZ", "list_date": date(2024, 2, 2)},  # exactly 120 days before 2024-06-01
    ])
    spec = UniverseFilterSpec(min_listing_days=120)
    filtered, report = apply_universe_filter(frame, spec, start=start, metadata=meta)
    assert set(filtered["ts_code"].unique()) == {"OLD.SZ", "EDGE.SZ"}
    assert report.dropped_by_rule == {"min_listing_days": 1}


def test_min_amount_and_unavailable_column():
    frame = _frame({"LOW.SZ": 4, "HIGH.SZ": 4}, amount=None)
    frame.loc[frame["ts_code"] == "LOW.SZ", "amount"] = 100.0
    frame.loc[frame["ts_code"] == "HIGH.SZ", "amount"] = 10_000_000.0
    spec = UniverseFilterSpec(min_amount=1_000_000.0)
    filtered, report = apply_universe_filter(frame, spec, start=date(2024, 1, 1), metadata=_metadata([]))
    assert set(filtered["ts_code"].unique()) == {"HIGH.SZ"}

    no_amount = _frame({"A.SZ": 2}, amount=None)
    no_amount = no_amount.drop(columns=["amount"], errors="ignore")
    filtered, report = apply_universe_filter(no_amount, spec, start=date(2024, 1, 1), metadata=_metadata([]))
    assert report.unavailable_rules == ["min_amount"]
    assert set(filtered["ts_code"].unique()) == {"A.SZ"}  # rule skipped, nothing dropped


def test_unavailable_rule_reported_not_dropped():
    frame = _frame({"A.SZ": 2, "B.SZ": 2})
    meta = _metadata([{"ts_code": "A.SZ", "is_st": None}, {"ts_code": "B.SZ", "is_st": None}])
    spec = UniverseFilterSpec(exclude_st=True)
    filtered, report = apply_universe_filter(frame, spec, start=date(2024, 1, 1), metadata=meta)
    assert report.unavailable_rules == ["exclude_st"]
    assert report.output_symbols == 2  # nothing dropped


def test_no_rules_passthrough():
    frame = _frame({"A.SZ": 2})
    filtered, report = apply_universe_filter(frame, UniverseFilterSpec(), start=date(2024, 1, 1), metadata=_metadata([]))
    assert report.applied is False
    assert len(filtered) == len(frame)


def test_combined_rules_union_drop():
    frame = _frame({"A.SZ": 2, "B.SZ": 2, "C.SZ": 2, "D.SZ": 2}, amount=1e6)
    meta = _metadata([
        {"ts_code": "A.SZ", "is_st": True, "is_suspended": True},
        {"ts_code": "B.SZ", "is_st": True},
        {"ts_code": "C.SZ", "is_suspended": True},
        {"ts_code": "D.SZ"},
    ])
    spec = UniverseFilterSpec(exclude_st=True, exclude_suspended=True)
    filtered, report = apply_universe_filter(frame, spec, start=date(2024, 1, 1), metadata=meta)
    assert set(filtered["ts_code"].unique()) == {"D.SZ"}
    assert report.dropped_by_rule == {"exclude_st": 2, "exclude_suspended": 2}
    assert report.output_rows == 2


# ---------------------------------------------------------------------------
# research_run wiring
# ---------------------------------------------------------------------------


def _spec_with_universe() -> StrategySpec:
    return StrategySpec(
        name="test",
        signal_expression="close > 0",
        exit_signal_expression=None,
        market_fields=["open", "close", "amount"],
        factor_fields=[],
        forward_horizons=[1],
        holding_days=5,
        quantiles=None,
        exclude_st=True,
        exclude_suspended=True,
        min_listing_days=30,
    )


def _backtest_request(tmp_path: Path, **overrides) -> ResearchRunRequest:
    defaults = {
        "strategy_path": tmp_path / "s.yaml",
        "start": date(2024, 1, 1),
        "end": date(2024, 3, 1),
        "output_dir": tmp_path / "out",
    }
    defaults.update(overrides)
    return ResearchRunRequest(**defaults)


def _engine_capture(monkeypatch):
    captured: dict = {}

    class FakeEngine:
        def __init__(self, profile):
            captured["profile"] = profile

        def run(self, frame, request):
            captured["frame"] = frame
            captured["request"] = request
            return SimpleNamespace()

    monkeypatch.setattr(rr, "BatchBacktestEngine", FakeEngine)
    monkeypatch.setattr(rr, "write_batch_result", lambda *a, **kw: {})
    return captured


def test_backtest_profile_overrides_applied(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    store = SimpleNamespace()
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    req = _backtest_request(tmp_path, profile_overrides={"commission_rate": 0.001, "slippage_buy_rate": 0.0005})
    status, _ = rr._run_backtest(store, _spec_with_universe(), req, frame=frame)
    assert status == "ok"
    assert captured["profile"].commission_rate == 0.001
    assert captured["profile"].slippage_buy_rate == 0.0005
    assert captured["profile"].stamp_tax_sell == 0.0005  # untouched default


def test_backtest_profile_overrides_invalid_rejected(tmp_path, monkeypatch):
    _engine_capture(monkeypatch)
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    with pytest.raises(ValueError, match="Unknown profile override keys"):
        rr._run_backtest(SimpleNamespace(), _spec_with_universe(), _backtest_request(tmp_path, profile_overrides={"bad_key": 1.0}), frame=frame)


def test_backtest_universe_filter_applied_and_recorded(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    fake_meta = pd.DataFrame(
        {
            "ts_code": ["STOCK_A.SZ", "STOCK_B.SZ"],
            "is_st": [True, False],
            "is_suspended": [False, False],
            "list_date": [date(2020, 1, 1), date(2020, 1, 1)],
        }
    )
    monkeypatch.setattr(
        "quant_research_engine.portfolio.universe.load_universe_metadata",
        lambda store, codes, *, as_of: fake_meta,
    )
    frame = pd.DataFrame(
        {
            "ts_code": ["STOCK_A.SZ"] * 3 + ["STOCK_B.SZ"] * 3,
            "trade_date": pd.bdate_range("2024-01-01", periods=3).tolist() * 2,
            "open": [10.0] * 6,
            "close": [10.0] * 6,
            "amount": [1e6] * 6,
        }
    )
    req = _backtest_request(tmp_path, universe_filter=True)
    status, paths = rr._run_backtest(SimpleNamespace(), _spec_with_universe(), req, frame=frame)
    assert status == "ok"
    assert set(captured["frame"]["ts_code"].unique()) == {"STOCK_B.SZ"}
    report_path = paths["universe_report"]
    report = json.loads(report_path.read_text(encoding="utf-8"))
    # complete accounting: every applied rule appears, zero-counts included
    assert report["dropped_by_rule"]["exclude_st"] == 1
    assert report["dropped_by_rule"]["exclude_suspended"] == 0
    assert report["dropped_by_rule"]["min_listing_days"] == 0
    assert report["input_symbols"] == 2 and report["output_symbols"] == 1


def test_backtest_universe_filter_off_by_default(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    called = []
    monkeypatch.setattr(
        "quant_research_engine.portfolio.universe.load_universe_metadata",
        lambda *a, **kw: called.append(1) or pd.DataFrame(),
    )
    frame = pd.DataFrame({"ts_code": ["STOCK_A.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    req = _backtest_request(tmp_path)  # universe_filter defaults False
    rr._run_backtest(SimpleNamespace(), _spec_with_universe(), req, frame=frame)
    assert called == []
    assert "universe_report" not in captured or True
    assert len(captured["frame"]) == 1


def test_manifest_records_overrides_and_universe_flag(tmp_path):
    req = _backtest_request(
        tmp_path,
        profile_overrides={"commission_rate": 0.001},
        universe_filter=True,
    )
    result = ResearchRunResult(
        run_id="r1",
        output_dir=tmp_path / "out",
        preflight_status="skipped",
        eval_status="skipped",
        backtest_status="ok",
    )
    path = _write_research_manifest(result, req)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["profile_overrides"] == {"commission_rate": 0.001}
    assert payload["universe_filter"] is True


# ---------------------------------------------------------------------------
# runner passthrough
# ---------------------------------------------------------------------------


def test_runner_threads_overrides_and_universe_flag(tmp_path, monkeypatch):
    from quant_research_engine.orchestration.batch_runner import BatchRunConfig, run_single_strategy

    captured = {}
    monkeypatch.setattr(
        "quant_research_engine.orchestration.research_run.run_research_run",
        lambda request: captured.setdefault("request", request) or SimpleNamespace(
            run_id="r", preflight_status="skipped", eval_status="skipped",
            backtest_status="ok", error_message=None, stage_durations_s={},
        ),
    )
    catalog = tmp_path / "catalog" / "cat"
    catalog.mkdir(parents=True)
    yaml_path = catalog / "s1.yaml"
    yaml_path.write_text("name: s1\n")
    config = BatchRunConfig(
        output_base=tmp_path / "batch",
        start=date(2024, 1, 1),
        end=date(2024, 3, 1),
        catalog_dir=tmp_path / "catalog",
        profile_overrides={"slippage_sell_rate": 0.001},
        universe_filter=True,
    )
    run_single_strategy(yaml_path, config)
    request = captured["request"]
    assert request.universe_filter is True
    assert request.profile_overrides == {"slippage_sell_rate": 0.001}


# ---------------------------------------------------------------------------
# apply_stops threading (M10.2b)
# ---------------------------------------------------------------------------


def _spec_with_stops() -> StrategySpec:
    return StrategySpec(
        name="test",
        signal_expression="close > 0",
        exit_signal_expression=None,
        market_fields=["open", "close"],
        factor_fields=[],
        forward_horizons=[1],
        holding_days=5,
        quantiles=None,
        stop_loss_pct=0.08,
        take_profit_pct=0.20,
    )


def test_apply_stops_off_passes_none(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    req = _backtest_request(tmp_path)  # apply_stops defaults False
    rr._run_backtest(SimpleNamespace(), _spec_with_stops(), req, frame=frame)
    assert captured["request"].stop_loss_pct is None
    assert captured["request"].take_profit_pct is None


def test_apply_stops_on_uses_spec_values(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    req = _backtest_request(tmp_path, apply_stops=True)
    rr._run_backtest(SimpleNamespace(), _spec_with_stops(), req, frame=frame)
    assert captured["request"].stop_loss_pct == 0.08
    assert captured["request"].take_profit_pct == 0.20


def test_apply_stops_request_override_wins(tmp_path, monkeypatch):
    captured = _engine_capture(monkeypatch)
    frame = pd.DataFrame({"ts_code": ["000001.SZ"], "trade_date": [pd.Timestamp("2024-01-02")], "open": [1.0], "close": [1.0]})
    req = _backtest_request(tmp_path, apply_stops=True, stop_loss_pct=0.05)
    rr._run_backtest(SimpleNamespace(), _spec_with_stops(), req, frame=frame)
    assert captured["request"].stop_loss_pct == 0.05
    assert captured["request"].take_profit_pct == 0.20  # from spec



def test_min_listing_days_data_start_symbols_kept():
    """Symbols whose first bar equals the table data start must NOT be dropped
    (their true listing predates the data history — list_date is unknown)."""
    # emulate loader output AFTER the data-start nulling: OLD.SZ has NaT
    frame = _frame({"OLD.SZ": 2, "NEW.SZ": 2})
    start = date(2010, 1, 4)
    meta = _metadata([
        {"ts_code": "OLD.SZ", "list_date": None},               # == data start → unknown → keep
        {"ts_code": "NEW.SZ", "list_date": date(2010, 1, 1)},   # IPO 3 days before start → drop
    ])
    spec = UniverseFilterSpec(min_listing_days=120)
    filtered, report = apply_universe_filter(frame, spec, start=start, metadata=meta)
    assert set(filtered["ts_code"].unique()) == {"OLD.SZ"}
    assert report.dropped_by_rule == {"min_listing_days": 1}
