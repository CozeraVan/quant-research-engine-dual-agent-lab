"""scripts/showcase_roller.py 的单元测试与引擎等价性测试。

单元测试（合成数据，无 DB 依赖）：
- 冻结点状态重建（reconstruct_states）；
- 单日/多日推进与 SingleSymbolBacktestEngine 逐行等价（roll_symbol）；
- 交集口径组合聚合（aggregate_portfolio，新股注入不计收益）；
- 费用/价格列/market profile 覆盖。

等价性测试（QRE_SHOWCASE_ROLLER_E2E=1 才启用，需本机 PG 大库）：
- CLI 全引擎跑 2025-01-01→2025-08-29（A）与 →2025-05-30（B，5 只股票）；
- 滚动器从 B 的冻结状态滚动到 2025-08-29；
- 逐日组合 daily_return 与 A 的组合净值曲线比对（≤1e-8），每股末净值一致。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

import showcase_roller as sr  # noqa: E402
from quant_research_engine.markets.ashare import AShareMarketProfile  # noqa: E402
from quant_research_engine.portfolio.single_symbol import (  # noqa: E402
    SingleSymbolBacktestEngine,
    SingleSymbolBacktestRequest,
)


# ---------------------------------------------------------------------------
# 合成数据工具
# ---------------------------------------------------------------------------


def _make_frame(closes: list[float], *, start: str = "2025-06-02", symbol: str = "000001.SZ") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame({
        "ts_code": symbol,
        "trade_date": dates,
        "open": closes,
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "pre_close": [closes[0]] + closes[:-1],
        "vol": 10000.0,
        "amount": 1000.0,
        "mom": closes,
    })


def _write_symbol_artifacts(directory: Path, result, symbol: str = "000001.SZ") -> None:
    from quant_research_engine.portfolio.io import write_single_symbol_result

    write_single_symbol_result(result, directory / symbol)


def _write_portfolio_curve(directory: Path, last_date: str) -> None:
    pd.DataFrame({
        "trade_date": [last_date],
        "cash": [0.0], "market_value": [0.0], "total_equity": [0.0],
        "daily_return": [0.0], "cumulative_return": [0.0],
        "position_count": [0], "turnover": [None],
    }).to_csv(directory / "equity_curve.csv", index=False)


ROLL_PARAMS = sr.RollParams(
    initial_cash=100_000.0,
    entry_signal="(mom > mom.shift(1))",
    exit_signal="(mom < mom.shift(1))",
    holding_days=0,
)


# ---------------------------------------------------------------------------
# 状态重建
# ---------------------------------------------------------------------------


class TestReconstructStates:
    def test_basic_state_and_freeze_equity(self, tmp_path: Path) -> None:
        frame = _make_frame([10, 11, 12, 11, 12, 13, 14, 15])
        engine = SingleSymbolBacktestEngine(AShareMarketProfile())
        req = SingleSymbolBacktestRequest(
            symbol="000001.SZ", initial_cash=100_000.0,
            entry_signal=ROLL_PARAMS.entry_signal,
            exit_signal=ROLL_PARAMS.exit_signal, holding_days=0,
        )
        result = engine.run(frame, req)
        assert not result.orders.empty
        _write_symbol_artifacts(tmp_path, result)
        last_date = str(frame.iloc[-1]["trade_date"].date())
        _write_portfolio_curve(tmp_path, last_date)

        freeze = sr.reconstruct_states(tmp_path)
        assert freeze.freeze_date == frame.iloc[-1]["trade_date"]
        assert set(freeze.states) == {"000001.SZ"}
        state = freeze.states["000001.SZ"]
        last = result.equity_curve.iloc[-1]
        assert state.cash == pytest.approx(float(last["cash"]), rel=0, abs=1e-12)
        assert state.quantity == int(last["position_quantity"])
        assert state.total_equity == pytest.approx(float(last["total_equity"]), abs=1e-9)
        if state.quantity > 0:
            buys = result.orders[result.orders["side"] == "buy"]
            assert state.entry_date == pd.Timestamp(buys.iloc[-1]["trade_date"])
            assert state.entry_price == pytest.approx(float(buys.iloc[-1]["price"]))
        assert freeze.equity_at_freeze["000001.SZ"] == pytest.approx(state.total_equity)

    def test_pending_sell_from_failed_orders(self, tmp_path: Path) -> None:
        symbol_dir = tmp_path / "000001.SZ"
        symbol_dir.mkdir()
        pd.DataFrame({
            "trade_date": ["2025-06-06"],
            "cash": [500.0], "position_quantity": [100],
            "market_value": [1200.0], "total_equity": [1700.0],
            "buy_hold_equity": [None],
        }).to_csv(symbol_dir / "equity_curve.csv", index=False)
        pd.DataFrame({
            "symbol": ["000001.SZ"], "trade_date": ["2025-06-02"], "side": ["buy"],
            "quantity": [100], "price": [10.0], "notional": [1000.0], "cost": [5.0],
        }).to_csv(symbol_dir / "orders.csv", index=False)
        pd.DataFrame({
            "symbol": ["000001.SZ"], "trade_date": ["2025-06-06"], "side": ["sell"],
            "quantity": [100], "price": [12.0], "notional": [1200.0],
            "reason": ["limit_down_sell_blocked"],
        }).to_csv(symbol_dir / "failed_orders.csv", index=False)
        _write_portfolio_curve(tmp_path, "2025-06-06")

        freeze = sr.reconstruct_states(tmp_path)
        state = freeze.states["000001.SZ"]
        assert state.pending_sell is True
        assert state.entry_date == pd.Timestamp("2025-06-02")
        assert state.bars_held == 1  # 06-02 入场 → 06-06 为入场后第 1 根 bar


# ---------------------------------------------------------------------------
# roll_symbol 与引擎逐行等价
# ---------------------------------------------------------------------------


def _engine_result(frame: pd.DataFrame, holding_days: int = 0,
                   stop_loss: float | None = None) -> object:
    engine = SingleSymbolBacktestEngine(AShareMarketProfile())
    return engine.run(frame, SingleSymbolBacktestRequest(
        symbol="000001.SZ", initial_cash=100_000.0,
        entry_signal=ROLL_PARAMS.entry_signal,
        exit_signal=ROLL_PARAMS.exit_signal,
        holding_days=holding_days,
        stop_loss_pct=stop_loss,
    ))


def _state_from_result(result, state_date: pd.Timestamp) -> sr.SymbolState:
    curve = result.equity_curve
    curve = curve.loc[pd.to_datetime(curve["trade_date"]) <= state_date]
    last = curve.iloc[-1]
    quantity = int(last["position_quantity"])
    entry_date = entry_price = None
    bars_held = 0
    if quantity > 0:
        buys = result.orders[result.orders["side"] == "buy"]
        entry_date = pd.Timestamp(buys.iloc[-1]["trade_date"])
        entry_price = float(buys.iloc[-1]["price"])
        dates = pd.to_datetime(curve["trade_date"])
        bars_held = int(((dates > entry_date) & (dates <= state_date)).sum())
    pending_sell = False
    if not result.failed_orders.empty:
        failed = result.failed_orders
        failed_sell = failed.loc[
            (failed["side"] == "sell")
            & (pd.to_datetime(failed["trade_date"]) == state_date)
        ]
        pending_sell = not failed_sell.empty
    return sr.SymbolState(
        symbol="000001.SZ", state_date=state_date,
        cash=float(last["cash"]), quantity=quantity,
        total_equity=float(last["total_equity"]),
        entry_date=entry_date, entry_price=entry_price,
        bars_held=bars_held, pending_sell=pending_sell,
    )


def _assert_roll_matches_engine(closes: list[float], split: int, *,
                                holding_days: int = 0, stop_loss: float | None = None) -> None:
    frame = _make_frame(closes)
    full = _engine_result(frame, holding_days=holding_days, stop_loss=stop_loss)
    freeze_date = pd.Timestamp(frame.iloc[split - 1]["trade_date"])
    base = _engine_result(frame.iloc[:split].copy(), holding_days=holding_days, stop_loss=stop_loss)
    state = _state_from_result(base, freeze_date)

    # 滚动窗口含冻结日前 3 个 bar 的 shift 上下文
    window = frame.iloc[max(split - 4, 0):].copy()
    params = sr.RollParams(
        initial_cash=100_000.0,
        entry_signal=ROLL_PARAMS.entry_signal,
        exit_signal=ROLL_PARAMS.exit_signal,
        holding_days=holding_days,
        stop_loss_pct=stop_loss,
    )
    days = sr.roll_symbol(state, window, params, AShareMarketProfile())

    expected = full.equity_curve.copy()
    expected["trade_date"] = pd.to_datetime(expected["trade_date"])
    expected = expected.loc[expected["trade_date"] > freeze_date].reset_index(drop=True)
    assert len(days) == len(expected)
    for day, (_, exp) in zip(days, expected.iterrows(), strict=True):
        assert day.trade_date == exp["trade_date"]
        assert day.cash == pytest.approx(float(exp["cash"]), rel=0, abs=1e-9)
        assert day.quantity == int(exp["position_quantity"])
        assert day.total_equity == pytest.approx(float(exp["total_equity"]), rel=0, abs=1e-9)


class TestRollSymbolEquivalence:
    def test_flat_at_freeze(self) -> None:
        # 单调交替，冻结日落在空仓日
        _assert_roll_matches_engine([10, 9, 10, 9, 10, 11, 12, 11, 12, 13, 12, 13], 6)

    def test_holding_at_freeze(self) -> None:
        _assert_roll_matches_engine([10, 11, 12, 13, 14, 15, 14, 13, 12, 13, 14, 15], 6)

    def test_holding_days_exit(self) -> None:
        _assert_roll_matches_engine([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21], 5, holding_days=3)

    def test_stop_loss(self) -> None:
        _assert_roll_matches_engine([10, 11, 12, 9, 8, 7, 8, 9, 10, 11, 10, 9], 3, stop_loss=0.1)

    def test_signal_on_freeze_day_schedules_next_bar(self) -> None:
        # 冻结日当日出入场信号：延展窗口中须在下一 bar 成交（全期回测末日不调度）
        closes = [10, 9, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
        _assert_roll_matches_engine(closes, 5)

    def test_empty_window(self) -> None:
        frame = _make_frame([10, 11, 12])
        params = ROLL_PARAMS
        assert sr.roll_symbol(None, frame.iloc[0:0], params, AShareMarketProfile()) == []

    def test_all_null_factor_column_no_crash(self) -> None:
        # 新股窗口因子全 NULL（object dtype None 列）：按 NaN→False 处理，不交易
        frame = _make_frame([10, 11, 12, 13])
        frame["mom"] = None
        frame["mom"] = frame["mom"].astype(object)
        days = sr.roll_symbol(None, frame, ROLL_PARAMS, AShareMarketProfile())
        assert len(days) == 4
        assert all(d.quantity == 0 and d.total_equity == 100_000.0 for d in days)


# ---------------------------------------------------------------------------
# 组合聚合（交集口径）
# ---------------------------------------------------------------------------


class TestAggregatePortfolio:
    def test_intersection_return_and_injection(self) -> None:
        d1, d2, d3 = pd.Timestamp("2025-06-03"), pd.Timestamp("2025-06-04"), pd.Timestamp("2025-06-05")

        def day(ts, eq, qty=0, entries=0, exits=0):
            return sr.RolledDay(trade_date=ts, cash=eq, quantity=qty,
                                market_value=0.0, total_equity=eq,
                                entries=entries, exits=exits)

        new_rows = {
            "A": [day(d1, 101.0), day(d2, 102.0), day(d3, 103.0)],
            "B": [day(d1, 201.0), day(d3, 204.0)],  # d2 缺席（停牌）
            "C": [day(d2, 300.0), day(d3, 303.0)],  # d2 新股注入
        }
        equity_at_freeze = {"A": 100.0, "B": 200.0}
        rows = sr.aggregate_portfolio(new_rows, equity_at_freeze)
        assert [r["trade_date"] for r in rows] == ["2025-06-03", "2025-06-04", "2025-06-05"]
        # d1: A+B 均在市（冻结日有权益）
        assert rows[0]["daily_return"] == pytest.approx((101 + 201) / (100 + 200) - 1)
        assert rows[0]["equity"] == pytest.approx(302.0)
        # d2: 交集仅 A（B 缺席、C 新注入）；C 的 300 进总额不贡献收益
        assert rows[1]["daily_return"] == pytest.approx(102 / 101 - 1)
        assert rows[1]["equity"] == pytest.approx(402.0)
        # d3: 当日在市 A/B/C；与 d2 的交集只有 A/C（B 在 d2 无行）
        assert rows[2]["daily_return"] == pytest.approx((103 + 303) / (102 + 300) - 1)
        assert rows[2]["n_positions"] == 0

    def test_counts(self) -> None:
        d1 = pd.Timestamp("2025-06-03")
        new_rows = {
            "A": [sr.RolledDay(d1, cash=1.0, quantity=100, market_value=9.0,
                               total_equity=10.0, entries=1)],
            "B": [sr.RolledDay(d1, cash=20.0, quantity=0, market_value=0.0,
                               total_equity=20.0, exits=1)],
        }
        rows = sr.aggregate_portfolio(new_rows, {"A": 10.0, "B": 20.0})
        assert rows[0]["n_positions"] == 1
        assert rows[0]["n_entries"] == 1
        assert rows[0]["n_exits"] == 1
        assert rows[0]["daily_return"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# 参数还原
# ---------------------------------------------------------------------------


class TestParams:
    def test_profile_overrides_match_gui_semantics(self) -> None:
        profile = sr._build_profile({"commission_rate": 0.001, "min_commission": 8,
                                     "slippage_buy_rate": 0, "unknown_key": 1})
        assert profile.commission_rate == 0.001
        assert profile.min_commission == 8
        assert profile.stamp_tax_sell == AShareMarketProfile().stamp_tax_sell

    def test_price_columns(self) -> None:
        assert sr._resolve_price_columns(None, None) == ("open", "open")
        assert sr._resolve_price_columns("close", None) == ("close", "close")
        assert sr._resolve_price_columns("open", "vwap") == ("open", "vwap")
        with pytest.raises(ValueError):
            sr._resolve_price_columns("bad", None)

    def test_build_roll_params_holding_override(self) -> None:
        yaml_text = (Path("/home/van/qre-outputs/gui-console/runs/20261011T135434249768/strategy.yaml")
                     .read_text(encoding="utf-8"))
        job = {"job_id": 58, "yaml": yaml_text,
               "params": {"mode": "batch", "initial_cash": 100000, "max_holding_days": None}}
        roll, market_fields, spec, profile = sr.build_roll_params(job)
        assert roll.holding_days == 20  # params 缺省 → YAML holding 节生效
        job2 = {"job_id": 58, "yaml": yaml_text,
                "params": {"mode": "batch", "max_holding_days": 0}}
        roll2, *_ = sr.build_roll_params(job2)
        assert roll2.holding_days == 0  # params 显式覆盖
        job3 = {"job_id": 1, "yaml": yaml_text, "params": {"mode": "shared"}}
        with pytest.raises(RuntimeError):
            sr.build_roll_params(job3)


# ---------------------------------------------------------------------------
# 等价性测试（slow，需本机 PG；QRE_SHOWCASE_ROLLER_E2E=1 启用）
# ---------------------------------------------------------------------------

E2E_ENABLED = os.environ.get("QRE_SHOWCASE_ROLLER_E2E") == "1"
E2E_DB_URL = "postgresql+psycopg://van:211589@127.0.0.1:5432/tushare_data"
E2E_CODES = ["000001.SZ", "600519.SH", "000002.SZ", "300750.SZ", "000063.SZ"]
JOB74_YAML = Path("/home/van/qre-outputs/gui-console/runs/20261019T033313476861/strategy.yaml")


@pytest.mark.skipif(not E2E_ENABLED, reason="等价性测试需 QRE_SHOWCASE_ROLLER_E2E=1 与本机 PG")
@pytest.mark.slow
class TestEngineEquivalenceE2E:
    def _run_cli(self, strategy: Path, start: str, end: str, out_dir: Path) -> None:
        cmd = [
            str(REPO_ROOT / ".venv/bin/python"), "-m", "quant_research_engine.apps.cli",
            "backtest-batch", str(strategy),
            "--start", start, "--end", end,
            "--codes", *E2E_CODES,
            "--initial-cash", "100000", "--output-dir", str(out_dir),
            "--db-url", E2E_DB_URL,
        ]
        env = dict(os.environ)
        env["QRE_PRICE_BASIS"] = "raw"
        proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env,
                              capture_output=True, text=True, timeout=600)
        assert proc.returncode == 0, f"CLI 失败: {proc.stderr[-2000:]}"

    def test_roll_equals_full_engine(self, tmp_path: Path) -> None:
        assert JOB74_YAML.is_file(), "job74 基线 strategy.yaml 不存在"
        dir_a, dir_b = tmp_path / "A", tmp_path / "B"
        self._run_cli(JOB74_YAML, "2025-01-01", "2025-08-29", dir_a)
        self._run_cli(JOB74_YAML, "2025-01-01", "2025-05-30", dir_b)

        os.environ["QRE_PRICE_BASIS"] = "raw"
        os.environ["QRE_MARKET_DB_URL"] = E2E_DB_URL
        sr.load_worker_env()
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings

        # 与基线 CLI/worker 同一构造：显式 db-url → price_basis 默认 qfq
        store = PostgresDataStore(DatabaseSettings(market_db_url=E2E_DB_URL))
        job = {
            "job_id": 74,
            "strategy_name": "wizard_ema_5_20261019",
            "yaml": JOB74_YAML.read_text(encoding="utf-8"),
            "params": {
                "mode": "batch", "initial_cash": 100000, "max_holding_days": 0,
                "entry_price": "open", "exit_price": "open",
                "profile_overrides": {
                    "commission_rate": 0.0003, "min_commission": 5,
                    "slippage_buy_rate": 0, "slippage_sell_rate": 0,
                    "stamp_tax_sell": 0.0005,
                },
            },
            "last_daily": None,
        }
        rows, diag = sr.roll_job(
            job, store, date(2025, 8, 29),
            artifacts_dir=dir_b, symbols=E2E_CODES, log=lambda *_: None,
        )
        assert rows, "滚动器未产出任何行"

        expected_curve = pd.read_csv(dir_a / "equity_curve.csv")
        expected_curve["trade_date"] = expected_curve["trade_date"].astype(str)
        expected_curve = expected_curve.loc[
            expected_curve["trade_date"] > "2025-05-30"
        ].reset_index(drop=True)
        assert len(rows) == len(expected_curve), (
            f"行数不一致: roller={len(rows)} engine={len(expected_curve)}"
        )
        for row, (_, exp) in zip(rows, expected_curve.iterrows(), strict=True):
            assert row["trade_date"] == exp["trade_date"]
            assert row["daily_return"] == pytest.approx(
                float(exp["daily_return"]), rel=1e-8, abs=1e-10
            ), f"{row['trade_date']} daily_return 不一致"
            assert row["equity"] == pytest.approx(
                float(exp["total_equity"]), rel=1e-8
            ), f"{row['trade_date']} equity 不一致"

        # 每股末净值一致
        freeze_b = sr.reconstruct_states(dir_b)
        del freeze_b
        for symbol in E2E_CODES:
            eq_a = pd.read_csv(dir_a / symbol / "equity_curve.csv")
            final_a = float(eq_a.iloc[-1]["total_equity"])
            # 重滚该股取末值（roll_job 不暴露每股明细，直接用 aggregate 输入重建）
            from quant_research_engine.data.assembler import ResearchFrameAssembler
            from quant_research_engine.strategies.spec import StrategySpec

            spec = StrategySpec.from_yaml(JOB74_YAML)
            state = sr.reconstruct_states(dir_b).states.get(symbol)
            params, market_fields, _, profile = sr.build_roll_params(job)
            frame = ResearchFrameAssembler(store).build(
                ts_codes=[symbol], start=date(2025, 5, 15), end=date(2025, 8, 29),
                market_fields=market_fields, factor_fields=spec.factor_fields,
                include_metadata=True,
            )
            days = sr.roll_symbol(state, frame, params, profile)
            assert days[-1].total_equity == pytest.approx(final_a, rel=1e-8), (
                f"{symbol} 末净值不一致: roller={days[-1].total_equity} engine={final_a}"
            )
