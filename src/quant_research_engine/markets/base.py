from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from quant_research_engine.core.models import Order, OrderSide


@dataclass(frozen=True)
class OrderValidationResult:
    allowed: bool
    reason: str = "ok"


class MarketProfile(Protocol):
    name: str

    def round_order_quantity(self, side: OrderSide, quantity: int) -> int:
        ...

    def calculate_cost(self, side: OrderSide, notional: float) -> float:
        ...

    def validate_order(
        self,
        order: Order,
        *,
        is_suspended: bool,
        limit_up: bool,
        limit_down: bool,
    ) -> OrderValidationResult:
        ...
