#!/usr/bin/env python
"""经典策略展示页增量日更滚动器（QRE-SAAS-SHOWCASE 阶段二 worker 侧）。

冻结的全市场全期 batch 回测（showcase 基线 job）之后，每个交易日只推进
「当日组合日收益」并推送 ECS showcase_daily 表：

- 冻结点组合状态从本机 run 产物重建（每股 equity_curve.csv 末行现金/持仓
  + orders.csv 入场信息 + failed_orders.csv 未决出场），不重跑历史；
- 每股用与引擎同一装配器（ResearchFrameAssembler.build）加载冻结日前后短
  窗口的行情+因子，信号用引擎同一 evaluate_expression_signal 求值；
- 逐日推进严格复刻 SingleSymbolBacktestEngine 的行处理顺序与费用模型
  （T 日收盘出信号 → T+1 开盘价成交，佣金/印花税/过户费同 AShareMarketProfile）；
- 组合日收益用 faf9629 的「交集口径」（昨∩今在市股票），与冻结基线曲线连贯；
- 推送幂等（ECS 端 ON CONFLICT upsert；本地只送 last_daily 之后的行）。

机密（QRE_SAAS_BASE_URL / QRE_WORKER_TOKEN）从 /etc/qre-saas-worker.env
解析注入环境，绝不打印 token。

用法：
    uv run python scripts/showcase_roller.py [--date YYYY-MM-DD] [--dry-run]
    uv run python scripts/showcase_roller.py --push [--job 74]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pandas as pd  # noqa: E402

from quant_research_engine.core.models import Order, OrderSide, OrderType  # noqa: E402
from quant_research_engine.evaluation.signals import evaluate_expression_signal  # noqa: E402
from quant_research_engine.markets.ashare import AShareMarketProfile  # noqa: E402

WORKER_ENV_PATH = Path("/etc/qre-saas-worker.env")
RUNS_ROOT = Path("/home/van/qre-outputs/gui-console/runs")

#: job_id → 冻结基线 run 目录（strategy.yaml 的 experiment.name 须与 ECS
#: 下发的 strategy_name 一致，加载时校验）。
JOB_RUN_MAP = {
    74: "20261019T033313476861",
    58: "20261011T135434249768",
    66: "20261013T022229180230",
}

PRICE_COLUMN_CHOICES = ("open", "close", "vwap")
#: 状态日前向缓冲（日历日）：保证冻结日行与其 shift(1) 上下文进入窗口
SIGNAL_WARMUP_DAYS = 15
PUSH_CHUNK_SIZE = 500  # ECS 端单次上限


# ---------------------------------------------------------------------------
# 配置与 ECS 通道
# ---------------------------------------------------------------------------


def load_worker_env(path: Path = WORKER_ENV_PATH) -> dict[str, str]:
    """解析 KEY=VALUE env 文件并注入 os.environ（与 systemd EnvironmentFile
    同语义：无条件覆盖，尤其代理变量必须按文件显式置空生效）。"""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
            os.environ[key] = value
            if not value:
                # 显式置空（如 HTTP_PROXY=）：urllib 会忽略空串，但部分库
                # 读 os.environ 存在性，直接删除最贴近 EnvironmentFile 语义
                os.environ.pop(key, None)
    return values


def _http_json(method: str, url: str, token: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("X-Worker-Token", token)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"ECS {method} {url} -> HTTP {exc.code}: {detail}") from exc


def fetch_showcase_jobs(base_url: str, token: str) -> list[dict[str, Any]]:
    data = _http_json("GET", f"{base_url}/api/worker/showcase/jobs", token)
    if not data.get("ok"):
        raise RuntimeError(f"ECS showcase jobs 拉取失败: {data}")
    return list(data.get("jobs") or [])


def push_daily_rows(base_url: str, token: str, job_id: int, rows: list[dict[str, Any]]) -> int:
    pushed = 0
    for offset in range(0, len(rows), PUSH_CHUNK_SIZE):
        chunk = rows[offset:offset + PUSH_CHUNK_SIZE]
        data = _http_json(
            "POST", f"{base_url}/api/worker/showcase/jobs/{job_id}/daily", token,
            {"rows": chunk},
        )
        if not data.get("ok"):
            raise RuntimeError(f"job {job_id} 日更推送失败: {data}")
        pushed += len(chunk)
    return pushed


# ---------------------------------------------------------------------------
# 冻结点状态重建
# ---------------------------------------------------------------------------


@dataclass
class SymbolState:
    symbol: str
    state_date: pd.Timestamp          # 全期回测中该股最后一根 bar 日期
    cash: float
    quantity: int
    total_equity: float               # state_date 当日的组合权益（该股）
    entry_date: pd.Timestamp | None   # 当前持仓的入场日（无持仓为 None）
    entry_price: float | None
    bars_held: int                    # state_date 时 entry_index 起算的 bar 偏移
    pending_sell: bool                # state_date 出场校验失败重排到下一 bar
    fresh: bool = False               # True = 基线窗口内无该行（新股），从零起步


@dataclass
class FreezeState:
    freeze_date: pd.Timestamp
    states: dict[str, SymbolState]
    equity_at_freeze: dict[str, float]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def resolve_run_dir(job_id: int, strategy_name: str, runs_root: Path = RUNS_ROOT) -> Path:
    run_id = JOB_RUN_MAP.get(int(job_id))
    if run_id is None:
        raise RuntimeError(f"job {job_id} 无本地基线 run 映射（JOB_RUN_MAP）")
    run_dir = runs_root / run_id
    yaml_path = run_dir / "strategy.yaml"
    if not yaml_path.is_file():
        raise RuntimeError(f"基线 run 缺少 strategy.yaml: {run_dir}")
    import yaml as _yaml

    name = str((_yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {})
               .get("experiment", {}).get("name", ""))
    if name != strategy_name:
        raise RuntimeError(
            f"job {job_id} 映射校验失败：run {run_id} experiment.name={name!r} "
            f"!= ECS strategy_name={strategy_name!r}"
        )
    artifacts = run_dir / "artifacts"
    if not artifacts.is_dir():
        raise RuntimeError(f"基线 run 缺少 artifacts/: {run_dir}")
    return artifacts


def reconstruct_states(artifacts_dir: Path) -> FreezeState:
    """从基线 run 产物重建冻结点每股状态。

    - 冻结日 = 组合级 equity_curve.csv 末行日期；
    - 每股状态 = 该股 equity_curve.csv 末行（cash/持仓/权益）+ orders.csv
      最近一笔买入（入场日/价）+ failed_orders.csv 末日未决卖出；
    - equity_at_freeze：每股在冻结日当日的权益（交集口径首日的分母来源；
      仅冻结日当日有 bar 的股票有值）。
    """
    portfolio_curve = _read_csv(artifacts_dir / "equity_curve.csv")
    if portfolio_curve.empty:
        raise RuntimeError(f"组合级 equity_curve.csv 为空: {artifacts_dir}")
    freeze_date = pd.Timestamp(str(portfolio_curve.iloc[-1]["trade_date"]))

    states: dict[str, SymbolState] = {}
    equity_at_freeze: dict[str, float] = {}
    for child in sorted(artifacts_dir.iterdir()):
        if not child.is_dir() or child.name.startswith("_"):
            continue
        symbol = child.name
        curve = _read_csv(child / "equity_curve.csv")
        if curve.empty:
            continue  # 基线窗口无 bar 的股票（新股占位目录）
        curve["trade_date"] = pd.to_datetime(curve["trade_date"])
        last = curve.iloc[-1]
        state_date = pd.Timestamp(last["trade_date"])
        cash = float(last["cash"])
        quantity = int(last["position_quantity"])
        total_equity = float(last["total_equity"])

        at_freeze = curve.loc[curve["trade_date"] == freeze_date]
        if not at_freeze.empty:
            equity_at_freeze[symbol] = float(at_freeze.iloc[0]["total_equity"])

        entry_date: pd.Timestamp | None = None
        entry_price: float | None = None
        bars_held = 0
        if quantity > 0:
            orders = _read_csv(child / "orders.csv")
            if not orders.empty and "side" in orders.columns:
                buys = orders.loc[orders["side"] == "buy"]
                if not buys.empty:
                    last_buy = buys.iloc[-1]
                    entry_date = pd.Timestamp(str(last_buy["trade_date"]))
                    entry_price = float(last_buy["price"])
                    bars_held = int(
                        ((curve["trade_date"] > entry_date)
                         & (curve["trade_date"] <= state_date)).sum()
                    )
            if entry_date is None:
                raise RuntimeError(f"{symbol} 持仓 {quantity} 但 orders.csv 无买入记录")

        pending_sell = False
        failed = _read_csv(child / "failed_orders.csv")
        if not failed.empty and "side" in failed.columns:
            failed["trade_date"] = pd.to_datetime(failed["trade_date"])
            sells = failed.loc[
                (failed["side"] == "sell") & (failed["trade_date"] == state_date)
            ]
            pending_sell = not sells.empty

        states[symbol] = SymbolState(
            symbol=symbol,
            state_date=state_date,
            cash=cash,
            quantity=quantity,
            total_equity=total_equity,
            entry_date=entry_date,
            entry_price=entry_price,
            bars_held=bars_held,
            pending_sell=pending_sell,
        )
    return FreezeState(freeze_date=freeze_date, states=states, equity_at_freeze=equity_at_freeze)


# ---------------------------------------------------------------------------
# 每股逐日推进（严格复刻 SingleSymbolBacktestEngine 行处理语义）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RollParams:
    initial_cash: float
    entry_signal: str
    exit_signal: str | None
    holding_days: int                  # 0 = 不限
    entry_price_column: str = "open"
    exit_price_column: str = "open"
    mark_price_column: str = "close"
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None


@dataclass
class RolledDay:
    trade_date: pd.Timestamp
    cash: float
    quantity: int
    market_value: float
    total_equity: float
    entries: int = 0
    exits: int = 0


def _row_flag(row: Any, column: str, profile: AShareMarketProfile) -> bool:
    """与 SingleSymbolBacktestEngine._row_flag 同口径（含 ``or`` 回退语义）。"""
    value = getattr(row, column, None)
    if value is not None and pd.notna(value):
        return bool(value)
    if column in ("limit_up", "limit_down"):
        def _opt(col: str) -> float | None:
            v = getattr(row, col, None)
            if v is None or pd.isna(v):
                return None
            return float(v)

        pre_close = _opt("raw_pre_close") or _opt("pre_close")
        price = _opt("raw_open") or float(row["open"])
        is_st = _row_flag(row, "is_st", profile)
        if column == "limit_up":
            return profile.is_limit_up(str(row.ts_code), pre_close=pre_close, price=price, is_st=is_st)
        return profile.is_limit_down(str(row.ts_code), pre_close=pre_close, price=price, is_st=is_st)
    return False


def roll_symbol(
    state: SymbolState | None,
    working: pd.DataFrame,
    params: RollParams,
    profile: AShareMarketProfile,
) -> list[RolledDay]:
    """从冻结点状态（或新股零状态）逐 bar 推进到窗口末。

    ``working`` 为装配器输出的该股 frame（含信号求值所需的全部历史上下文行，
    且必须覆盖 state.state_date 当日行；新股则为其全部早期 bar）。
    行处理顺序/费用/校验与 SingleSymbolBacktestEngine.run 逐语句对应。
    """
    if params.trailing_stop_pct is not None:
        raise NotImplementedError("trailing_stop 滚动暂不支持（showcase 三 job 均未启用）")
    if working.empty:
        return []

    working = working.sort_values("trade_date").reset_index(drop=True)
    working["trade_date"] = pd.to_datetime(working["trade_date"])
    # 新股窗口内因子列全 NULL 时 psycopg 给 object dtype 的 None 列，比较会
    # TypeError；转数值（None→NaN，比较结果 False）与 evaluate_expression_signal
    # 的 fillna(False) 口径一致——全期引擎遇到 float64 NaN 列时行为相同。
    from quant_research_engine.evaluation.signals import referenced_fields

    for column in referenced_fields(params.entry_signal) | referenced_fields(params.exit_signal):
        if column in working.columns:
            working[column] = pd.to_numeric(working[column], errors="coerce")
    working["entry_signal"] = evaluate_expression_signal(working, params.entry_signal)
    if params.exit_signal is not None:
        working["exit_signal"] = evaluate_expression_signal(working, params.exit_signal)
    n_rows = len(working)

    if state is None or state.fresh:
        start_idx = 0
        cash = params.initial_cash
        quantity = 0
        entry_pos: int | None = None
        entry_price: float | None = None
        pending_sell_index: int | None = None
        pending_sell_reason: str | None = None
    else:
        matches = working.index[working["trade_date"] == state.state_date]
        if len(matches) == 0:
            raise RuntimeError(
                f"{state.symbol} 冻结日 {state.state_date.date()} 行不在装配窗口内"
            )
        start_idx = int(matches[0])
        cash = state.cash
        quantity = state.quantity
        entry_pos = (start_idx - state.bars_held) if quantity > 0 else None
        entry_price = state.entry_price if quantity > 0 else None
        pending_sell_index = start_idx + 1 if state.pending_sell else None
        pending_sell_reason = "exit_signal" if state.pending_sell else None

    pending_buy_index: int | None = None
    day_rows: list[tuple[pd.Timestamp, float, int, float, float]] = []
    fills: dict[pd.Timestamp, list[int]] = {}  # trade_date -> [n_entries, n_exits]

    def _fill(ts: pd.Timestamp, slot: int) -> None:
        entry = fills.setdefault(ts, [0, 0])
        entry[slot] += 1

    def _schedule_exit(index: int, row: Any) -> None:
        """出场信号/风控调度到下一 bar（与引擎 elif 链优先级一致）。"""
        nonlocal pending_sell_index, pending_sell_reason
        if (
            params.stop_loss_pct is not None
            and float(row[params.mark_price_column]) <= float(entry_price) * (1 - params.stop_loss_pct)
            and index + 1 < n_rows
        ):
            if pending_sell_index is None or index + 1 < pending_sell_index:
                pending_sell_index = index + 1
                pending_sell_reason = "stop_loss"
        elif (
            params.take_profit_pct is not None
            and float(row[params.mark_price_column]) >= float(entry_price) * (1 + params.take_profit_pct)
            and index + 1 < n_rows
        ):
            if pending_sell_index is None or index + 1 < pending_sell_index:
                pending_sell_index = index + 1
                pending_sell_reason = "take_profit"
        elif (
            params.exit_signal is not None
            and bool(row.get("exit_signal", False))
            and index + 1 < n_rows
        ):
            if pending_sell_index is None or index + 1 < pending_sell_index:
                pending_sell_index = index + 1
                pending_sell_reason = "exit_signal"

    for index in range(start_idx, n_rows):
        row = working.iloc[index]
        trade_date = row["trade_date"]

        if index == start_idx and state is not None and not state.fresh:
            # 冻结日行：状态已是该日收盘后结果，只补做「末日信号调度」——
            # 全期回测在此日为止（index+1 == len），未调度的入场/出场信号
            # 在延展窗口中等价于调度到下一 bar。持仓期出场若应在冻结日触发，
            # 基线产物中必然已经成交（不可能仍持仓），无需补。
            if quantity > 0:
                if pending_sell_index is None:
                    _schedule_exit(index, row)
            elif bool(row["entry_signal"]):
                pending_buy_index = index + 1
            continue

        # 1. 待定买入执行
        if pending_buy_index == index and quantity == 0:
            price_raw = float(row[params.entry_price_column])
            price = profile.apply_slippage(OrderSide.BUY, price_raw)
            raw_quantity = int(cash // price)
            buy_quantity = profile.round_order_quantity(OrderSide.BUY, raw_quantity)
            if buy_quantity <= 0:
                pending_buy_index = None
            else:
                order = Order(
                    symbol=str(row["ts_code"]),
                    trade_date=trade_date.date(),
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=buy_quantity,
                    price=price,
                )
                validation = profile.validate_order(
                    order,
                    is_suspended=_row_flag(row, "is_suspended", profile),
                    limit_up=_row_flag(row, "limit_up", profile),
                    limit_down=_row_flag(row, "limit_down", profile),
                )
                if not validation.allowed:
                    pending_buy_index = None
                else:
                    cost = profile.calculate_cost(OrderSide.BUY, order.notional)
                    if order.notional + cost > cash:
                        shrunk = profile.fit_buy_quantity_to_cash(buy_quantity, price, cash)
                        if shrunk > 0:
                            buy_quantity = shrunk
                            order = Order(
                                symbol=str(row["ts_code"]),
                                trade_date=trade_date.date(),
                                side=OrderSide.BUY,
                                order_type=OrderType.MARKET,
                                quantity=buy_quantity,
                                price=price,
                            )
                            cost = profile.calculate_cost(OrderSide.BUY, order.notional)
                        else:
                            pending_buy_index = None
                            order = None
                    if order is not None:
                        cash -= order.notional + cost
                        quantity = buy_quantity
                        entry_pos = index
                        entry_price = price
                        _fill(trade_date, 0)
                        pending_buy_index = None

        # 2. 持仓管理（待定出场执行 / 新出场调度）
        if quantity > 0 and entry_pos is not None:
            sell_reason: str | None = None
            if pending_sell_index is not None and index == pending_sell_index:
                sell_reason = pending_sell_reason or "exit_signal"
            elif params.holding_days > 0 and index == entry_pos + params.holding_days:
                sell_reason = "holding_period"
            else:
                _schedule_exit(index, row)

            if sell_reason is not None:
                price_raw = float(row[params.exit_price_column])
                price = profile.apply_slippage(OrderSide.SELL, price_raw)
                order = Order(
                    symbol=str(row["ts_code"]),
                    trade_date=trade_date.date(),
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    quantity=quantity,
                    price=price,
                )
                validation = profile.validate_order(
                    order,
                    is_suspended=_row_flag(row, "is_suspended", profile),
                    limit_up=_row_flag(row, "limit_up", profile),
                    limit_down=_row_flag(row, "limit_down", profile),
                )
                if not validation.allowed:
                    pending_sell_index = index + 1
                    pending_sell_reason = sell_reason
                else:
                    cost = profile.calculate_cost(OrderSide.SELL, order.notional)
                    cash += order.notional - cost
                    quantity = 0
                    entry_pos = None
                    entry_price = None
                    pending_sell_index = None
                    pending_sell_reason = None
                    _fill(trade_date, 1)

        # 3. 入场信号调度
        if quantity == 0 and pending_buy_index is None and bool(row["entry_signal"]) and index + 1 < n_rows:
            pending_buy_index = index + 1

        # 4. 收盘估值
        mark_price = float(row[params.mark_price_column])
        market_value = quantity * mark_price
        day_rows.append((trade_date, cash, quantity, market_value, cash + market_value))

    days: list[RolledDay] = []
    for trade_date, cash_v, qty_v, mv_v, eq_v in day_rows:
        n_entries, n_exits = fills.get(trade_date, [0, 0])
        days.append(RolledDay(
            trade_date=trade_date, cash=cash_v, quantity=qty_v,
            market_value=mv_v, total_equity=eq_v,
            entries=n_entries, exits=n_exits,
        ))
    return days


# ---------------------------------------------------------------------------
# 组合级聚合（faf9629 交集口径）
# ---------------------------------------------------------------------------


def aggregate_portfolio(
    new_rows: dict[str, list[RolledDay]],
    equity_at_freeze: dict[str, float],
) -> list[dict[str, Any]]:
    """把每股新推进的日记录聚合成组合级逐日行（交集口径日收益）。

    首日的前一全局交易日 = 冻结日，分母取自基线产物中冻结日当日在市股票
    的权益；之后各日的前一全局交易日为上一个有行日期。当日新进入股票
    （新股/复牌）自带资金进入总和但不贡献当日收益。
    """
    by_date: dict[pd.Timestamp, dict[str, RolledDay]] = {}
    for symbol, days in new_rows.items():
        for day in days:
            by_date.setdefault(day.trade_date, {})[symbol] = day
    if not by_date:
        return []

    rows: list[dict[str, Any]] = []
    prev_equity: dict[str, float] = dict(equity_at_freeze)
    for trade_date in sorted(by_date):
        today = by_date[trade_date]
        total_equity = sum(d.total_equity for d in today.values())
        cash = sum(d.cash for d in today.values())
        market_value = sum(d.market_value for d in today.values())
        n_positions = sum(1 for d in today.values() if d.quantity > 0)
        n_entries = sum(d.entries for d in today.values())
        n_exits = sum(d.exits for d in today.values())
        numerator = 0.0
        denominator = 0.0
        for symbol, day in today.items():
            prev = prev_equity.get(symbol)
            if prev is not None:
                numerator += day.total_equity
                denominator += prev
        daily_return = (numerator / denominator - 1.0) if denominator > 0 else None
        rows.append({
            "trade_date": trade_date.date().isoformat(),
            "daily_return": daily_return if daily_return is not None else 0.0,
            "equity": total_equity,
            "cash": cash,
            "market_value": market_value,
            "n_positions": n_positions,
            "n_entries": n_entries,
            "n_exits": n_exits,
        })
        prev_equity = {symbol: day.total_equity for symbol, day in today.items()}
    return rows


# ---------------------------------------------------------------------------
# 任务级滚动
# ---------------------------------------------------------------------------


def _build_profile(overrides: dict[str, Any] | None) -> AShareMarketProfile:
    from dataclasses import replace

    profile = AShareMarketProfile()
    if overrides:
        valid = {
            k: float(v) for k, v in overrides.items()
            if v is not None and hasattr(profile, k)
        }
        if valid:
            profile = replace(profile, **valid)
    return profile


def _resolve_price_columns(entry_price: Any, exit_price: Any) -> tuple[str, str]:
    entry_col = str(entry_price).strip() if entry_price not in (None, "") else "open"
    exit_col = str(exit_price).strip() if exit_price not in (None, "") else entry_col
    for col in (entry_col, exit_col):
        if col not in PRICE_COLUMN_CHOICES:
            raise ValueError(f"无效成交价列: {col!r}（可选 {'/'.join(PRICE_COLUMN_CHOICES)}）")
    return entry_col, exit_col


def build_roll_params(job: dict[str, Any]) -> tuple[RollParams, list[str], Any, AShareMarketProfile]:
    """从 ECS job（yaml + params）还原引擎请求参数。返回 (roll_params,
    market_fields, spec, profile)。"""
    from quant_research_engine.strategies.spec import StrategySpec

    import yaml as _yaml

    spec = StrategySpec.from_mapping(_yaml.safe_load(str(job["yaml"])))
    params = job.get("params") or {}
    if str(params.get("mode") or "batch") != "batch":
        raise RuntimeError(f"job {job.get('job_id')} 非 batch 模式，滚动器不支持")
    # max_holding_days 显式给时覆盖 YAML（与 worker runner 同口径）
    holding_days = (
        int(params["max_holding_days"])
        if params.get("max_holding_days") is not None
        else spec.holding_days
    )
    entry_col, exit_col = _resolve_price_columns(params.get("entry_price"), params.get("exit_price"))
    market_fields = list(spec.market_fields)
    for col in (entry_col, exit_col):
        if col not in market_fields:
            market_fields.append(col)
    roll = RollParams(
        initial_cash=float(params.get("initial_cash") or 100_000.0),
        entry_signal=spec.signal_expression,
        exit_signal=spec.exit_signal_expression,
        holding_days=holding_days,
        entry_price_column=entry_col,
        exit_price_column=exit_col,
        stop_loss_pct=params.get("stop_loss_pct") or spec.stop_loss_pct,
        take_profit_pct=params.get("take_profit_pct") or spec.take_profit_pct,
        trailing_stop_pct=params.get("trailing_stop_pct") or spec.trailing_stop_pct,
    )
    return roll, market_fields, spec, _build_profile(params.get("profile_overrides"))


def _symbols_with_new_bars(store: Any, start: date, end: date) -> set[str]:
    from sqlalchemy import text

    table = store.qualified_table(store.settings.tables.market_daily_table)
    frame = pd.read_sql_query(
        text(
            f"SELECT DISTINCT ts_code FROM {table} "
            "WHERE trade_date > :start AND trade_date <= :end"
        ),
        con=store.market_engine,
        params={"start": start, "end": end},
    )
    return set(frame["ts_code"].astype(str))


def latest_trade_date(store: Any) -> date:
    from sqlalchemy import text

    table = store.qualified_table(store.settings.tables.market_daily_table)
    frame = pd.read_sql_query(
        text(f"SELECT max(trade_date) AS d FROM {table}"),
        con=store.market_engine,
    )
    return pd.Timestamp(frame.iloc[0]["d"]).date()


def roll_job(
    job: dict[str, Any],
    store: Any,
    target_date: date,
    *,
    runs_root: Path = RUNS_ROOT,
    artifacts_dir: Path | None = None,
    symbols: list[str] | None = None,
    log: Any = print,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """滚动单个 showcase job 至 target_date，返回 (待推送行, 诊断信息)。

    ``artifacts_dir``/``symbols`` 为测试注入口：缺省按 JOB_RUN_MAP 解析基线
    产物、股票集取「冻结日后有新 bar」的全市场股票。
    """
    from quant_research_engine.data.assembler import ResearchFrameAssembler

    job_id = int(job["job_id"])
    if artifacts_dir is None:
        artifacts_dir = resolve_run_dir(job_id, str(job["strategy_name"]), runs_root)
    freeze = reconstruct_states(artifacts_dir)
    roll_params, market_fields, spec, profile = build_roll_params(job)

    last_daily = job.get("last_daily")
    last_daily_date = pd.Timestamp(str(last_daily)).date() if last_daily else None
    if target_date <= freeze.freeze_date.date():
        return [], {"job_id": job_id, "note": "目标日期不晚于冻结日，无需滚动"}

    assembler = ResearchFrameAssembler(store)
    metadata = store.load_security_metadata(ts_codes=None)
    meta_flags = metadata[["ts_code", "is_st", "is_suspended"]].copy()

    if symbols is None:
        active = _symbols_with_new_bars(store, freeze.freeze_date.date(), target_date)
        # 待处理股票 = 冻结窗口后有新 bar 的（含新股）；其余股票不可能有新行
        symbols = sorted(active)
    new_rows: dict[str, list[RolledDay]] = {}
    n_fresh = 0
    for pos, symbol in enumerate(symbols, 1):
        state = freeze.states.get(symbol)
        if state is None:
            state = SymbolState(
                symbol=symbol, state_date=freeze.freeze_date,
                cash=roll_params.initial_cash, quantity=0, total_equity=0.0,
                entry_date=None, entry_price=None, bars_held=0,
                pending_sell=False, fresh=True,
            )
            win_start = freeze.freeze_date.date() + timedelta(days=1)
            n_fresh += 1
        else:
            win_start = state.state_date.date() - timedelta(days=SIGNAL_WARMUP_DAYS)
        frame = assembler.build(
            ts_codes=[symbol],
            start=win_start,
            end=target_date,
            market_fields=market_fields,
            factor_fields=spec.factor_fields,
            include_metadata=False,
        )
        if frame.empty:
            continue
        frame = frame.merge(meta_flags, on="ts_code", how="left")
        frame = frame.loc[frame["ts_code"].astype(str) == symbol]
        days = roll_symbol(None if state.fresh else state, frame, roll_params, profile)
        days = [d for d in days if d.trade_date.date() > freeze.freeze_date.date()]
        if days:
            new_rows[symbol] = days
        if pos % 500 == 0:
            log(f"  job {job_id}: {pos}/{len(symbols)} 股已处理")

    rows = aggregate_portfolio(new_rows, freeze.equity_at_freeze)
    pending_rows = [r for r in rows if last_daily_date is None or r["trade_date"] > last_daily_date.isoformat()]
    diag = {
        "job_id": job_id,
        "freeze_date": freeze.freeze_date.date().isoformat(),
        "last_daily": last_daily_date.isoformat() if last_daily_date else None,
        "target_date": target_date.isoformat(),
        "symbols_with_new_bars": len(symbols),
        "fresh_symbols": n_fresh,
        "rolled_symbols": len(new_rows),
        "rows_total": len(rows),
        "rows_to_push": len(pending_rows),
    }
    return pending_rows, diag


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="经典策略展示页增量日更滚动器")
    parser.add_argument("--date", type=date.fromisoformat, default=None,
                        help="滚动到的交易日（默认：数据库最新交易日）")
    parser.add_argument("--job", type=int, action="append", default=None,
                        help="只滚动指定 job_id（默认全部激活 showcase job）")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="只打印不上送（默认）")
    mode.add_argument("--push", action="store_true",
                      help="推送 ECS showcase_daily（幂等 upsert）")
    args = parser.parse_args(argv)

    env = load_worker_env()
    base_url = os.environ.get("QRE_SAAS_BASE_URL")
    token = os.environ.get("QRE_WORKER_TOKEN")
    if not base_url or not token:
        print("缺少 QRE_SAAS_BASE_URL / QRE_WORKER_TOKEN（/etc/qre-saas-worker.env）", file=sys.stderr)
        return 2

    from quant_research_engine.data.postgres import PostgresDataStore
    from quant_research_engine.data.settings import DatabaseSettings

    # 与 worker/CLI 基线执行同一构造路径：显式 market_db_url，price_basis 取
    # 默认 "qfq"（表内现存的原始价按原样读取，不做 ×adj_factor 复权）。
    # 冻结基线 job 74/58/66 即此口径（产物成交价为原始价），必须保持一致。
    db_url = os.environ.get("QRE_MARKET_DB_URL")
    if not db_url:
        print("缺少 QRE_MARKET_DB_URL（/etc/qre-saas-worker.env）", file=sys.stderr)
        return 2
    store = PostgresDataStore(DatabaseSettings(market_db_url=db_url))
    store.ping()

    target = args.date or latest_trade_date(store)
    print(f"滚动目标交易日: {target}")

    jobs = fetch_showcase_jobs(base_url, token)
    if args.job:
        wanted = set(args.job)
        jobs = [j for j in jobs if int(j["job_id"]) in wanted]
    if not jobs:
        print("无匹配的激活 showcase job")
        return 0

    exit_code = 0
    for job in jobs:
        job_id = int(job["job_id"])
        try:
            rows, diag = roll_job(job, store, target)
        except Exception as exc:
            print(f"job {job_id} 滚动失败: {exc}", file=sys.stderr)
            exit_code = 1
            continue
        print(
            f"job {job_id} [{job.get('strategy_name')}] 冻结日={diag.get('freeze_date')} "
            f"last_daily={diag.get('last_daily')} 新bar股数={diag.get('symbols_with_new_bars')} "
            f"(新股 {diag.get('fresh_symbols')}) 滚动股数={diag.get('rolled_symbols')} "
            f"待推送 {diag.get('rows_to_push')} 行"
        )
        for r in rows:
            print(
                f"  {r['trade_date']} daily_return={r['daily_return']:.10f} "
                f"equity={r['equity']:.2f} n_pos={r['n_positions']} "
                f"entries={r['n_entries']} exits={r['n_exits']}"
            )
        if args.push and rows:
            pushed = push_daily_rows(base_url, token, job_id, rows)
            print(f"job {job_id} 已推送 {pushed} 行（幂等 upsert）")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
