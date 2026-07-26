from __future__ import annotations

from dataclasses import dataclass, field
import math

from quant_research_engine.core.models import Order, OrderSide
from quant_research_engine.markets.base import OrderValidationResult


@dataclass(frozen=True)
class AShareMarketProfile:
    name: str = "ashare_daily_default"
    buy_lot: int = 100
    allow_odd_lot_sell: bool = True
    commission_rate: float = 0.0003
    min_commission: float = 5.0
    stamp_tax_sell: float = 0.0005
    transfer_fee_rate: float = 0.00001
    slippage_model: str = "percent"
    slippage_buy_rate: float = 0.0
    slippage_sell_rate: float = 0.0
    price_limit_by_board: dict[str, float] = field(
        default_factory=lambda: {
            "main_board": 0.10,
            "chinext": 0.20,
            "star_market": 0.20,
            "beijing": 0.30,
            "st": 0.05,
        }
    )

    @property
    def description(self) -> str:
        return "A-share daily market profile"

    def round_order_quantity(self, side: OrderSide, quantity: int) -> int:
        if quantity <= 0:
            return 0
        if side is OrderSide.SELL and self.allow_odd_lot_sell:
            return quantity
        return quantity // self.buy_lot * self.buy_lot

    def calculate_cost(self, side: OrderSide, notional: float) -> float:
        if notional <= 0:
            return 0.0
        commission = max(notional * self.commission_rate, self.min_commission)
        transfer_fee = notional * self.transfer_fee_rate
        stamp_tax = notional * self.stamp_tax_sell if side is OrderSide.SELL else 0.0
        return round(commission + transfer_fee + stamp_tax, 10)

    def calculate_cost_breakdown(self, side: OrderSide, notional: float) -> dict[str, float]:
        """Per-component cost breakdown; ``total`` matches calculate_cost exactly."""
        if notional <= 0:
            return {"commission": 0.0, "transfer_fee": 0.0, "stamp_tax": 0.0, "total": 0.0}
        commission = max(notional * self.commission_rate, self.min_commission)
        transfer_fee = notional * self.transfer_fee_rate
        stamp_tax = notional * self.stamp_tax_sell if side is OrderSide.SELL else 0.0
        return {
            "commission": commission,
            "transfer_fee": transfer_fee,
            "stamp_tax": stamp_tax,
            "total": round(commission + transfer_fee + stamp_tax, 10),
        }

    def apply_slippage(self, side: OrderSide, price: float) -> float:
        if self.slippage_model != "percent":
            raise ValueError(f"Unsupported slippage model: {self.slippage_model}")
        if side is OrderSide.BUY:
            return price * (1 + self.slippage_buy_rate)
        return price * (1 - self.slippage_sell_rate)

    def get_price_limit_rate(self, symbol: str, *, is_st: bool = False) -> float:
        if is_st:
            return self.price_limit_by_board["st"]
        if symbol.endswith(".BJ"):
            return self.price_limit_by_board["beijing"]
        if symbol.startswith(("300", "301")):
            return self.price_limit_by_board["chinext"]
        if symbol.startswith("688"):
            return self.price_limit_by_board["star_market"]
        return self.price_limit_by_board["main_board"]

    def is_limit_up(self, symbol: str, *, pre_close: float | None, price: float, is_st: bool = False) -> bool:
        if pre_close is None or not math.isfinite(pre_close) or pre_close <= 0:
            return False
        limit_price = round(pre_close * (1 + self.get_price_limit_rate(symbol, is_st=is_st)), 2)
        return price >= limit_price

    def is_limit_down(self, symbol: str, *, pre_close: float | None, price: float, is_st: bool = False) -> bool:
        if pre_close is None or not math.isfinite(pre_close) or pre_close <= 0:
            return False
        limit_price = round(pre_close * (1 - self.get_price_limit_rate(symbol, is_st=is_st)), 2)
        return price <= limit_price

    def validate_order(
        self,
        order: Order,
        *,
        is_suspended: bool,
        limit_up: bool,
        limit_down: bool,
    ) -> OrderValidationResult:
        if is_suspended:
            return OrderValidationResult(False, "suspended")
        if order.quantity <= 0:
            return OrderValidationResult(False, "non_positive_quantity")
        if order.side is OrderSide.BUY and limit_up:
            return OrderValidationResult(False, "limit_up_buy_blocked")
        if order.side is OrderSide.SELL and limit_down:
            return OrderValidationResult(False, "limit_down_sell_blocked")
        rounded_quantity = self.round_order_quantity(order.side, order.quantity)
        if rounded_quantity <= 0:
            return OrderValidationResult(False, "quantity_below_lot_size")
        return OrderValidationResult(True)
