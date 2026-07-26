"""Incremental backtest (P1) equivalence gates.

Gate semantics (docs/design/incremental_backtest.md §5):

- bootstrap: run_incremental with no checkpoint over [T0, T2] must equal a
  BatchBacktestEngine full run over the same window (ledgers + summary).
- incremental: full [T0, T2] ≡ incremental [T0, T1] + incremental [T1+1, T2]
  — cumulative ledgers byte-value equal, final checkpoint state equal to the
  single-window terminal state.
- plus: cross-boundary pendings, trailing-anchor continuation, new symbols
  appearing mid-history, idempotency, universe filtering, checkpoint IO.
"""

from __future__ import annotations

import io
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from quant_research_engine.markets.ashare import AShareMarketProfile
from quant_research_engine.orchestration.incremental import (
    IncrementalRequest,
    run_incremental,
)
from quant_research_engine.orchestration.incremental_state import (
    StrategyCheckpoint,
    SymbolState,
    compute_config_hash,
    load_checkpoint,
    save_checkpoint,
)
from quant_research_engine.portfolio.batch import BatchBacktestEngine, BatchBacktestRequest
from quant_research_engine.portfolio.single_symbol import SingleSymbolBacktestRequest
from quant_research_engine.portfolio.single_symbol_vectorized import (
    SingleSymbolVectorizedEngine,
)
from quant_research_engine.strategies.spec import StrategySpec

PROFILE = AShareMarketProfile()
DATES = pd.bdate_range("2024-01-01", periods=40)
T0, T1, T2 = DATES[0].date(), DATES[19].date(), DATES[39].date()


# ---------------------------------------------------------------------------
# fixtures: fake store + synthetic frames
# ---------------------------------------------------------------------------


class FakeStore:
    """In-memory MarketDataStore stand-in (read-only)."""

    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame

    def list_symbols_with_bars(self, start: date, end: date) -> list[str]:
        mask = (self.frame["trade_date"] >= pd.Timestamp(start)) & (
            self.frame["trade_date"] <= pd.Timestamp(end)
        )
        return sorted(self.frame.loc[mask, "ts_code"].astype(str).unique().tolist())

    def load_daily_bars(self, *, ts_codes, start, end, fields) -> pd.DataFrame:
        mask = (
            self.frame["ts_code"].isin(ts_codes)
            & (self.frame["trade_date"] >= pd.Timestamp(start))
            & (self.frame["trade_date"] <= pd.Timestamp(end))
        )
        return self.frame.loc[mask].reset_index(drop=True).copy()


def _rows(symbol: str, base: float, start_i: int = 0, n: int = 40) -> list[dict]:
    rows = []
    for i in range(start_i, start_i + n):
        o = base + ((i % 5) - 2) * 0.3
        c = o + (((i * 3) % 3) - 1) * 0.25
        rows.append(
            {
                "ts_code": symbol,
                "trade_date": DATES[i],
                "open": round(o, 2),
                "high": round(max(o, c) + 0.4, 2),
                "low": round(min(o, c) - 0.4, 2),
                "close": round(c, 2),
                "amount": 1e6,
                "is_st": False,
            }
        )
    return rows


def master_frame() -> pd.DataFrame:
    """A/B full history; C appears only from bar 25 (new listing)."""
    return pd.DataFrame(
        _rows("A.SZ", 10.0) + _rows("B.SZ", 50.0) + _rows("C.SZ", 20.0, start_i=25, n=15)
    )


def make_spec(entry: str = "close < open", holding: int = 4, **overrides) -> StrategySpec:
    defaults = {
        "name": "incremental_test",
        "signal_expression": entry,
        "exit_signal_expression": None,
        "market_fields": ["open", "high", "low", "close", "amount"],
        "factor_fields": [],
        "forward_horizons": [1],
        "holding_days": holding,
        "quantiles": None,
    }
    defaults.update(overrides)
    return StrategySpec(**defaults)


def make_request(output_root: Path, spec_path: Path, watermark, **overrides) -> IncrementalRequest:
    defaults = {
        "strategy_path": spec_path,
        "start": T0,
        "end": T2,
        "output_root": output_root,
        "initial_cash": 1_000_000.0,
        "watermark": watermark,
    }
    defaults.update(overrides)
    return IncrementalRequest(**defaults)


@pytest.fixture
def spec_path(tmp_path: Path) -> Path:
    path = tmp_path / "incremental_test.yaml"
    path.write_text("experiment:\n  name: incremental_test\n", encoding="utf-8")
    return path


def batch_reference(frame: pd.DataFrame, entry="close < open", holding=4, **req_overrides):
    return BatchBacktestEngine(PROFILE).run(
        frame,
        BatchBacktestRequest(
            symbols=None,
            initial_cash_per_symbol=1_000_000.0,
            entry_signal=entry,
            holding_days=holding,
            engine_impl="vectorized",
            **req_overrides,
        ),
    )


# ---------------------------------------------------------------------------
# comparison helpers (csv round-trip = byte-level value equality)
# ---------------------------------------------------------------------------


def _roundtrip(df: pd.DataFrame) -> pd.DataFrame:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return pd.read_csv(buf)


def _expected_orders(batch) -> pd.DataFrame:
    frames = [batch.results[s].orders for s in sorted(batch.results) if not batch.results[s].orders.empty]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True)
    return _roundtrip(combined)


def _expected_trades(batch) -> pd.DataFrame:
    frames = [batch.results[s].trades for s in sorted(batch.results) if not batch.results[s].trades.empty]
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["symbol", "entry_date"], kind="stable").reset_index(drop=True)
    return _roundtrip(combined)


def _expected_equity(batch) -> pd.DataFrame:
    frames = []
    for symbol in sorted(batch.results):
        equity = batch.results[symbol].equity_curve
        if equity.empty:
            continue
        equity = equity.copy()
        equity.insert(0, "symbol", symbol)
        equity = equity.rename(columns={"position_quantity": "quantity"})
        frames.append(equity)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True)
    return _roundtrip(combined)


def assert_ledgers_equal(state_dir: Path, batch, *, expect_failed: bool = False) -> None:
    orders = pd.read_csv(state_dir / "orders.csv").sort_values(
        ["symbol", "trade_date"], kind="stable"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(_expected_orders(batch), orders, check_dtype=False)

    trades = pd.read_csv(state_dir / "trades.csv").sort_values(
        ["symbol", "entry_date"], kind="stable"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(_expected_trades(batch), trades, check_dtype=False)

    equity = pd.read_csv(state_dir / "equity_curve.csv").sort_values(
        ["symbol", "trade_date"], kind="stable"
    ).reset_index(drop=True)
    pd.testing.assert_frame_equal(_expected_equity(batch), equity, check_dtype=False)

    summary = pd.read_csv(state_dir / "summary.csv")
    expected_summary = _roundtrip(batch.summary)
    pd.testing.assert_frame_equal(
        expected_summary, summary.reindex(columns=expected_summary.columns), check_dtype=False
    )

    if expect_failed:
        failed = pd.read_csv(state_dir / "failed_orders.csv")
        expected_failed = pd.concat(
            [batch.results[s].failed_orders for s in sorted(batch.results) if not batch.results[s].failed_orders.empty],
            ignore_index=True,
        ).sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True)
        pd.testing.assert_frame_equal(
            _roundtrip(expected_failed),
            failed.sort_values(["symbol", "trade_date"], kind="stable").reset_index(drop=True),
            check_dtype=False,
        )


# ---------------------------------------------------------------------------
# 1. checkpoint IO + config hash
# ---------------------------------------------------------------------------


def test_checkpoint_roundtrip_and_invalidation(tmp_path):
    state = SymbolState(
        cash=999_690.15,
        quantity=106_900,
        entry_date=date(2024, 2, 26),
        entry_price=9.35,
        entry_cost=309.85,
        entry_cost_parts={"commission": 299.85, "transfer_fee": 9.995, "stamp_tax": 0.0},
        trailing_anchor=9.80,
        pending_buy_date=None,
        pending_sell_date=date(2024, 3, 1),
        pending_sell_reason="stop_loss",
    )
    checkpoint = StrategyCheckpoint(
        strategy_id="s1",
        config_hash="abc123def456",
        last_processed_date=date(2024, 3, 1),
        data_watermark=date(2024, 3, 1),
        symbols={"000001.SZ": state},
    )
    path = save_checkpoint(tmp_path / "state.json", checkpoint)
    loaded = load_checkpoint(path)
    assert loaded is not None
    assert loaded.to_dict() == checkpoint.to_dict()
    # hash gate
    assert load_checkpoint(path, expected_config_hash="abc123def456") is not None
    assert load_checkpoint(path, expected_config_hash="000000000000") is None
    # schema gate
    payload = json.loads(path.read_text())
    payload["schema_version"] = 99
    path.write_text(json.dumps(payload))
    assert load_checkpoint(path) is None
    # corrupt + missing
    path.write_text("{not json")
    assert load_checkpoint(path) is None
    assert load_checkpoint(tmp_path / "missing.json") is None


def test_config_hash_changes_on_any_input(spec_path):
    base_args = (
        spec_path,
        "vectorized",
        {"commission_rate": 0.0003},
        {"stop_loss_pct": None},
        {"universe_filter": False},
    )
    base = compute_config_hash(*base_args)
    assert len(base) == 12
    assert compute_config_hash(*base_args) == base  # deterministic
    assert compute_config_hash(spec_path, "simulator", *base_args[2:]) != base
    assert compute_config_hash(spec_path, "vectorized", {"commission_rate": 0.0004}, *base_args[3:]) != base
    assert compute_config_hash(spec_path, "vectorized", base_args[2], {"stop_loss_pct": 0.08}, base_args[4]) != base
    assert compute_config_hash(spec_path, "vectorized", base_args[2], base_args[3], {"universe_filter": True}) != base
    other = spec_path.parent / "other.yaml"
    other.write_text("experiment:\n  name: changed\n", encoding="utf-8")
    assert compute_config_hash(other, *base_args[1:]) != base


# ---------------------------------------------------------------------------
# 2. bootstrap ≡ batch full run
# ---------------------------------------------------------------------------


def test_bootstrap_equals_full_batch(tmp_path, spec_path):
    frame = master_frame()
    store = FakeStore(frame)
    spec = make_spec()
    result = run_incremental(store, spec, make_request(tmp_path / "state", spec_path, T2))
    assert result.updated
    assert result.new_rows["orders"] > 0

    batch = batch_reference(frame)
    assert_ledgers_equal(tmp_path / "state" / "incremental_test", batch)


# ---------------------------------------------------------------------------
# 3. incremental ≡ full run (core gate, incl. warmup-dependent signal)
# ---------------------------------------------------------------------------


def test_incremental_equals_full_run(tmp_path, spec_path):
    frame = master_frame()
    store = FakeStore(frame)
    entry = "(close < open) | (close < close.rolling(3).mean())"
    spec = make_spec(entry=entry)
    out = tmp_path / "state"

    r1 = run_incremental(store, spec, make_request(out, spec_path, T1))
    assert r1.updated
    r2 = run_incremental(store, spec, make_request(out, spec_path, T2))
    assert r2.updated

    batch = batch_reference(frame, entry=entry)
    state_dir = out / "incremental_test"
    assert_ledgers_equal(state_dir, batch)

    # final checkpoint state ≡ single-window terminal state
    checkpoint = load_checkpoint(state_dir / "state.json")
    assert checkpoint is not None
    assert checkpoint.last_processed_date == T2
    engine = SingleSymbolVectorizedEngine(PROFILE)
    expected_states = {}
    for symbol, sub in frame.groupby("ts_code"):
        single = engine.run_working_incremental(
            sub,
            SingleSymbolBacktestRequest(
                symbol=symbol,
                initial_cash=1_000_000.0,
                entry_signal=entry,
                holding_days=4,
            ),
        )
        if single.final_state is not None:
            expected_states[symbol] = single.final_state
    assert set(checkpoint.symbols) == set(expected_states)
    for symbol, expected in expected_states.items():
        assert checkpoint.symbols[symbol] == expected, symbol


# ---------------------------------------------------------------------------
# 4. cross-boundary pending buy (signal on T1 executes at T1+1)
# ---------------------------------------------------------------------------


def test_cross_boundary_pending_buy(tmp_path, spec_path):
    dates = DATES[:6]
    frame = pd.DataFrame(
        {
            "ts_code": ["X.SZ"] * 6,
            "trade_date": dates,
            "open": [9.5] * 6,
            "high": [10.0] * 6,
            "low": [9.0] * 6,
            "close": [10.0, 10.0, 9.0, 10.0, 10.0, 10.0],  # signal only on bar 2
            "amount": [1e6] * 6,
        }
    )
    store = FakeStore(frame)
    spec = make_spec(entry="close < open", holding=2)
    t1, t2 = dates[2].date(), dates[5].date()
    out = tmp_path / "state"

    r1 = run_incremental(store, spec, make_request(out, spec_path, t1, end=t2))
    assert r1.new_rows["orders"] == 0  # signal bar is the window edge: no execution yet
    checkpoint = load_checkpoint(out / "incremental_test" / "state.json")
    assert checkpoint.symbols["X.SZ"].pending_buy_date == t1

    r2 = run_incremental(store, spec, make_request(out, spec_path, t2, end=t2))
    assert r2.new_rows["orders"] == 2  # buy at T1+1 open, holding-expiry sell later

    batch = batch_reference(frame, entry="close < open", holding=2)
    assert_ledgers_equal(out / "incremental_test", batch)


# ---------------------------------------------------------------------------
# 5. cross-boundary trailing-stop anchor continuation
# ---------------------------------------------------------------------------


def _trailing_frame() -> pd.DataFrame:
    dates = DATES[:10]
    return pd.DataFrame(
        {
            "ts_code": ["Y.SZ"] * 10,
            "trade_date": dates,
            "open": [10.0, 10.0, 9.5, 10.6, 11.4, 12.7, 12.4, 12.1, 12.0, 12.0],
            "high": [10.2, 10.2, 10.5, 11.0, 12.0, 13.0, 12.9, 12.3, 12.2, 12.2],
            "low": [9.8, 9.4, 9.8, 10.4, 11.2, 12.5, 12.0, 11.9, 11.8, 11.8],
            "close": [10.0, 9.5, 10.2, 10.8, 11.5, 12.8, 12.2, 12.0, 11.9, 11.9],
            "amount": [1e6] * 10,
        }
    )


def test_cross_boundary_trailing_anchor(tmp_path, spec_path):
    frame = _trailing_frame()
    dates = DATES[:10]
    t1, t2 = dates[5].date(), dates[9].date()
    store = FakeStore(frame)
    spec = make_spec(entry="close < open", holding=100)
    out = tmp_path / "state"
    req_kwargs = {"apply_stops": True, "trailing_stop_pct": 0.05, "end": t2}

    run_incremental(store, spec, make_request(out, spec_path, t1, **req_kwargs))
    checkpoint = load_checkpoint(out / "incremental_test" / "state.json")
    state = checkpoint.symbols["Y.SZ"]
    assert state.quantity > 0
    # anchor = max(entry fill price, highs up to T1)
    assert state.trailing_anchor == pytest.approx(13.0)
    assert state.entry_date == dates[2].date()

    run_incremental(store, spec, make_request(out, spec_path, t2, **req_kwargs))
    trades = pd.read_csv(out / "incremental_test" / "trades.csv")
    assert trades.iloc[0]["exit_reason"] == "trailing_stop"

    batch = batch_reference(
        frame, entry="close < open", holding=100, trailing_stop_pct=0.05
    )
    assert_ledgers_equal(out / "incremental_test", batch)


# ---------------------------------------------------------------------------
# 6. symbol appearing only in the second window
# ---------------------------------------------------------------------------


def test_new_symbol_in_second_window(tmp_path, spec_path):
    frame = master_frame()
    store = FakeStore(frame)
    spec = make_spec()
    out = tmp_path / "state"

    r1 = run_incremental(store, spec, make_request(out, spec_path, T1))
    assert "C.SZ" not in pd.read_csv(out / "incremental_test" / "summary.csv")["symbol"].values
    r2 = run_incremental(store, spec, make_request(out, spec_path, T2))
    assert r2.updated
    summary = pd.read_csv(out / "incremental_test" / "summary.csv")
    assert "C.SZ" in summary["symbol"].values

    batch = batch_reference(frame)
    assert_ledgers_equal(out / "incremental_test", batch)


# ---------------------------------------------------------------------------
# 7. idempotency: same watermark → no-op, ledgers untouched
# ---------------------------------------------------------------------------


def test_repeat_same_watermark_is_noop(tmp_path, spec_path):
    frame = master_frame()
    store = FakeStore(frame)
    spec = make_spec()
    out = tmp_path / "state"
    state_dir = out / "incremental_test"

    run_incremental(store, spec, make_request(out, spec_path, T1))
    run_incremental(store, spec, make_request(out, spec_path, T2))
    snapshot = {
        p.name: p.read_bytes()
        for p in state_dir.iterdir()
        if p.is_file()
    }
    again = run_incremental(store, spec, make_request(out, spec_path, T2))
    assert not again.updated
    assert set(again.new_rows.values()) == {0}
    for name, content in snapshot.items():
        assert (state_dir / name).read_bytes() == content, name


# ---------------------------------------------------------------------------
# 8. universe filter governs checkpoint membership and new entries
# ---------------------------------------------------------------------------


def test_universe_filter_excludes_symbols(tmp_path, spec_path, monkeypatch):
    frame = master_frame()
    store = FakeStore(frame)
    spec = make_spec(exclude_st=True)
    out = tmp_path / "state"

    metadata = pd.DataFrame(
        {
            "ts_code": ["A.SZ", "B.SZ", "C.SZ"],
            "is_st": [False, True, False],
            "is_suspended": [False, False, False],
            "is_risk_warning": [False, True, False],
            "list_date": pd.NaT,
        }
    )
    from quant_research_engine.portfolio import universe as universe_mod

    # incremental.py imports the loader lazily from the universe module.
    monkeypatch.setattr(universe_mod, "load_universe_metadata", lambda *a, **k: metadata)

    # phase 1: B excluded from the start
    run_incremental(
        store, spec, make_request(out, spec_path, T1, universe_filter=True)
    )
    state_dir = out / "incremental_test"
    summary1 = pd.read_csv(state_dir / "summary.csv")
    assert "B.SZ" not in summary1["symbol"].values
    assert "A.SZ" in summary1["symbol"].values
    checkpoint = load_checkpoint(state_dir / "state.json")
    assert "B.SZ" not in checkpoint.symbols

    # phase 2: B still excluded from new entries; C admitted
    run_incremental(
        store, spec, make_request(out, spec_path, T2, universe_filter=True)
    )
    orders = pd.read_csv(state_dir / "orders.csv")
    assert "B.SZ" not in orders["symbol"].values
    summary2 = pd.read_csv(state_dir / "summary.csv")
    assert "C.SZ" in summary2["symbol"].values

    # equivalence with a batch run on the filtered frame
    from quant_research_engine.portfolio.universe import (
        UniverseFilterSpec,
        apply_universe_filter,
    )

    filtered, _ = apply_universe_filter(
        frame, UniverseFilterSpec(exclude_st=True), start=T0, metadata=metadata
    )
    batch = batch_reference(filtered)
    assert_ledgers_equal(state_dir, batch)
