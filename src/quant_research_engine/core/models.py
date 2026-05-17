from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class InstrumentType(str, Enum):
    STOCK = "stock"
    FUND = "fund"
    FOREX = "forex"
    CRYPTO = "crypto"
    FUTURES = "futures"
    OPTION = "option"


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    market: str
    type: InstrumentType


@dataclass(frozen=True)
class Bar:
    symbol: str
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None
    pre_close: float | None = None


@dataclass(frozen=True)
class Order:
    symbol: str
    trade_date: date
    side: OrderSide
    order_type: OrderType
    quantity: int
    price: float

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class Fill:
    symbol: str
    trade_date: date
    side: OrderSide
    quantity: int
    price: float
    cost: float

    @property
    def notional(self) -> float:
        return self.quantity * self.price


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    sellable_quantity: int
    cost_basis: float
    last_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price


@dataclass(frozen=True)
class AccountSnapshot:
    trade_date: date
    cash: float
    market_value: float

    @property
    def total_equity(self) -> float:
        return self.cash + self.market_value
