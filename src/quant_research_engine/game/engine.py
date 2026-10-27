"""《我不是股神》日线交易状态机（Kimi 重做版）。

只处理委托、成交、现金、持仓与费用；行情抽样和页面状态在其他模块。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quant_research_engine.core.models import Bar, Fill, Order, OrderSide, OrderType
from quant_research_engine.markets.ashare import AShareMarketProfile


class GameRuleError(ValueError):
    """订单或时间推进违反游戏规则。"""


def price_limits(previous_close: float) -> tuple[float, float]:
    """前收 ±10% 的委托上下限，API 展示与成交校验共用。"""
    return round(previous_close * 0.90, 2), round(previous_close * 1.10, 2)


@dataclass
class DailyGameEngine:
    initial_cash: float = 1_000_000.0
    market: AShareMarketProfile | None = None

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise GameRuleError("初始资金必须大于 0")
        self.market = self.market or AShareMarketProfile()
        self.cash = float(self.initial_cash)
        self.quantity = 0
        self.sellable = 0
        self.pending_order: Order | None = None
        self.trades: list[Fill] = []
        self.events: list[dict[str, Any]] = []
        self._costs = {"commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0}
        self._last_close: float | None = None

    @property
    def equity(self) -> float:
        return self.cash if self._last_close is None else self.cash + self.quantity * self._last_close

    @property
    def should_end(self) -> bool:
        return self.equity < self.initial_cash * 0.10

    @property
    def total_cost(self) -> float:
        return sum(self._costs.values())

    @property
    def cost_breakdown(self) -> dict[str, float]:
        return {**self._costs, "total": self.total_cost}

    def create_order(self, symbol: str, trade_date, side: OrderSide,
                     price: float, quantity: int, previous_close: float) -> Order:
        if self.pending_order is not None:
            raise GameRuleError("已有待结算委托，请先撤单或结算")
        if previous_close <= 0 or price <= 0:
            raise GameRuleError("价格必须大于 0")
        price = round(float(price), 2)
        lower, upper = price_limits(previous_close)
        if price < lower or price > upper:
            raise GameRuleError("委托价必须在前收盘价 ±10% 以内")
        rounded = self.market.round_order_quantity(side, quantity)
        if rounded <= 0 or rounded != quantity:
            raise GameRuleError("委托数量须为 100 股整数倍")
        if side is OrderSide.SELL and quantity > self.sellable:
            raise GameRuleError("可卖持仓不足（T+1 当日买入不可卖）")
        notional = price * quantity
        if side is OrderSide.BUY and notional + self.market.calculate_cost(side, notional) > self.cash:
            raise GameRuleError("现金不足，无法买入")
        order = Order(symbol=symbol, trade_date=trade_date, side=side,
                      order_type=OrderType.LIMIT, quantity=quantity, price=price)
        self.pending_order = order
        self.events.append({"type": "created", "order": order})
        return order

    def cancel_order(self) -> Order:
        if self.pending_order is None:
            raise GameRuleError("没有可撤销的委托")
        order = self.pending_order
        self.pending_order = None
        self.events.append({"type": "cancelled", "order": order})
        return order

    def settle_pending(self, bar: Bar) -> Fill | None:
        order = self.pending_order
        if order is None:
            raise GameRuleError("没有待结算委托")
        if order.trade_date != bar.trade_date:
            raise GameRuleError("订单日期与 K 线日期不一致")
        one_word = len({bar.open, bar.high, bar.low, bar.close}) == 1
        limit_up = one_word and self.market.is_limit_up(
            order.symbol, pre_close=bar.pre_close, price=bar.close)
        limit_down = one_word and self.market.is_limit_down(
            order.symbol, pre_close=bar.pre_close, price=bar.close)
        blocked = ((order.side is OrderSide.BUY and limit_up)
                   or (order.side is OrderSide.SELL and limit_down))
        if blocked or not (bar.low <= order.price <= bar.high):
            self.events.append({"type": "unfilled", "order": order,
                                "reason": "one_word_limit" if blocked else "price_not_touched"})
            self.pending_order = None
            return None

        notional = order.notional
        cost = self.market.calculate_cost(order.side, notional)
        if order.side is OrderSide.BUY:
            if notional + cost > self.cash:
                raise GameRuleError("现金不足，无法买入")
            self.cash -= notional + cost
            self.quantity += order.quantity
        else:
            if order.quantity > self.sellable:
                raise GameRuleError("可卖持仓不足（T+1 当日买入不可卖）")
            self.cash += notional - cost
            self.quantity -= order.quantity
            self.sellable -= order.quantity
        for key, value in self.market.calculate_cost_breakdown(order.side, notional).items():
            if key != "total":
                self._costs[key] += value
        fill = Fill(symbol=order.symbol, trade_date=order.trade_date,
                    side=order.side, quantity=order.quantity, price=order.price, cost=cost)
        self.trades.append(fill)
        self.events.append({"type": "filled", "order": order, "fill": fill})
        self.pending_order = None
        self._last_close = bar.close
        return fill

    def close_day(self, bar: Bar) -> float:
        if self.pending_order is not None and self.pending_order.trade_date <= bar.trade_date:
            self.events.append({"type": "unfilled", "order": self.pending_order,
                                "reason": "expired_at_close"})
            self.pending_order = None
        self.sellable = self.quantity
        self._last_close = bar.close
        return self.equity
