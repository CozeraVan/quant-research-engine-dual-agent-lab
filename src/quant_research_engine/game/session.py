"""匿名随机会话与逐日揭盲；真实代码、日期和未来行情只在服务端。"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass

from quant_research_engine.core.models import Bar, OrderSide
from quant_research_engine.game.engine import DailyGameEngine, GameRuleError, price_limits


@dataclass
class GameSession:
    symbol: str
    bars: list[Bar]
    start_index: int
    seed: int
    warmup_bars: int = 250
    game_bars: int = 1250
    display_name: str = "B"
    display_code: str = "X00001B"

    def __post_init__(self) -> None:
        required = self.warmup_bars + self.game_bars
        if len(self.bars) < required:
            raise GameRuleError(f"历史数据不足：至少需要 {required} 根 K 线")
        if self.start_index < 0 or self.start_index > len(self.bars) - required:
            raise GameRuleError("随机窗口越界")
        self.cursor = self.start_index + self.warmup_bars - 1
        self.phase = "closed"
        self.engine = DailyGameEngine()
        self.factors: dict[int, dict[str, float | None]] = {}
        self.loaded_canonicals: set[str] = set()
        self.selected_canonicals: tuple[str, ...] = ()
        self.settlement: dict | None = None
        self.price_anchor: float | None = None
        self.factor_audit: dict | None = None
        self.factor_errors: dict[str, str] = {}

    @property
    def end_index(self) -> int:
        return self.start_index + self.warmup_bars + self.game_bars - 1

    @property
    def finished(self) -> bool:
        return self.phase == "closed" and (self.cursor >= self.end_index or self.engine.should_end)

    @property
    def pending_order(self):
        return self.engine.pending_order

    @property
    def quantity(self) -> int:
        return self.engine.quantity

    @property
    def sellable(self) -> int:
        return self.engine.sellable

    @property
    def equity(self) -> float:
        return self.engine.equity

    @property
    def total_cost(self) -> float:
        return self.engine.total_cost

    @property
    def cost_breakdown(self) -> dict[str, float]:
        return self.engine.cost_breakdown

    @property
    def trades(self):
        return self.engine.trades

    def _masked(self, index: int) -> dict:
        bar = self.bars[index]
        return {
            "t": index - self.start_index + 1,
            "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
            "volume": bar.volume,
            "factors": self.factors.get(index, {}),
        }

    def _masked_open(self, index: int) -> dict:
        return {"t": index - self.start_index + 1, "open": self.bars[index].open}

    def public_history(self) -> list[dict]:
        if self.phase == "open":
            history = [self._masked(index) for index in range(self.start_index, self.cursor)]
            history.append(self._masked_open(self.cursor))
            return history
        return [self._masked(index) for index in range(self.start_index, self.cursor + 1)]

    def _previous_close(self) -> float:
        if self.cursor > 0:
            return self.bars[self.cursor - 1].close
        return self.bars[self.cursor].pre_close

    def decision_state(self) -> dict:
        lower, upper = price_limits(self._previous_close())
        decision = {
            "previous_close": self._previous_close(),
            "limit_lower": lower,
            "limit_upper": upper,
            "can_trade": self.phase == "open" and not self.finished,
        }
        if self.phase == "open":
            decision["next_open"] = self.bars[self.cursor].open
        return decision

    def advance(self) -> dict:
        if self.phase != "closed":
            raise GameRuleError("请先结算当前回合")
        if self.finished:
            raise GameRuleError("游戏已结束，不能继续推进")
        self.cursor += 1
        self.phase = "open"
        self.settlement = None
        return self._masked_open(self.cursor)

    def place_order(self, side: OrderSide, price: float, quantity: int):
        if self.phase != "open":
            raise GameRuleError("只能在决策阶段委托")
        if self.finished:
            raise GameRuleError("游戏已结束")
        return self.engine.create_order(
            self.symbol, self.bars[self.cursor].trade_date, side, price, quantity,
            self._previous_close())

    def cancel_order(self):
        if self.phase != "open":
            raise GameRuleError("只能在决策阶段撤单")
        return self.engine.cancel_order()

    def close_day(self) -> dict:
        if self.phase != "open":
            raise GameRuleError("当前不在决策阶段，无法结算")
        bar = self.bars[self.cursor]
        fill = None
        unfilled = "no_order"
        if self.pending_order is not None:
            fill = self.engine.settle_pending(bar)
            unfilled = None if fill is not None else self.engine.events[-1].get("reason", "unfilled")
        self.engine.close_day(bar)
        self.phase = "closed"
        self.settlement = {
            "t": self.cursor - self.start_index + 1,
            "open": bar.open, "high": bar.high, "low": bar.low, "close": bar.close,
            "volume": bar.volume,
            "fill": None if fill is None else {
                "side": fill.side.value, "price": fill.price,
                "quantity": fill.quantity, "cost": fill.cost,
            },
            "unfilled": unfilled,
        }
        return self._masked(self.cursor)

    def rewind(self) -> None:
        raise GameRuleError("时间不能回退")


@dataclass(frozen=True)
class GameSessionFactory:
    warmup_bars: int = 250
    game_bars: int = 1250

    def create(self, candidates: dict[str, list[Bar]], *, seed: int | None = None) -> GameSession:
        required = self.warmup_bars + self.game_bars
        eligible = [symbol for symbol in sorted(candidates) if len(candidates[symbol]) >= required]
        if not eligible:
            raise GameRuleError(f"历史数据不足：股票池没有至少 {required} 根 K 线的标的")
        actual_seed = secrets.randbits(64) if seed is None else seed
        rng = random.Random(actual_seed)
        symbol = rng.choice(eligible)
        start_index = rng.randint(0, len(candidates[symbol]) - required)
        return GameSession(symbol=symbol, bars=candidates[symbol], start_index=start_index,
                           seed=actual_seed, warmup_bars=self.warmup_bars, game_bars=self.game_bars)
