"""游戏只读行情与因子适配层；原始价 + adj_factor 固定锚点前复权。"""

from __future__ import annotations

import random
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import text

from quant_research_engine.core.models import Bar
from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.game.engine import GameRuleError
from quant_research_engine.game.factors import (
    DEFAULT_CANONICALS, price_scaled_canonicals, resolve_selection,
)
from quant_research_engine.game.session import GameSession, GameSessionFactory
from quant_research_engine.game.validation import audit_price_factors


def qfq_anchor(rows: list[dict[str, Any]]) -> float | None:
    """会话前复权锚点：可用行的最后一个 adj_factor（与 K 线同一口径）。"""
    usable = [row for row in rows if row.get("adj_factor") is not None and row["adj_factor"] > 0]
    if not usable:
        return None
    return float(usable[-1]["adj_factor"])


def bars_from_rows(rows: list[dict[str, Any]]) -> list[Bar]:
    usable = [row for row in rows if row.get("adj_factor") is not None and row["adj_factor"] > 0]
    anchor = qfq_anchor(rows)
    if anchor is None:
        return []
    result = []
    for row in usable:
        ratio = row["adj_factor"] / anchor
        result.append(Bar(
            symbol=str(row.get("ts_code") or ""), trade_date=row["trade_date"],
            open=float(row["open"]) * ratio, high=float(row["high"]) * ratio,
            low=float(row["low"]) * ratio, close=float(row["close"]) * ratio,
            pre_close=float(row["pre_close"]) * ratio,
            volume=float(row["vol"]) if row.get("vol") is not None else None,
            amount=float(row["amount"]) if row.get("amount") is not None else None,
        ))
    return result


class PostgresGameDataProvider:
    def __init__(self, store: Any, *, warmup_bars: int = 250, game_bars: int = 1250,
                 candidate_limit: int = 20, with_factors: bool = True) -> None:
        self.store = store
        self.factory = GameSessionFactory(warmup_bars=warmup_bars, game_bars=game_bars)
        self.candidate_limit = candidate_limit
        self.with_factors = with_factors

    def latest_trade_date(self) -> date:
        if hasattr(self.store, "latest_trade_date"):
            return self.store.latest_trade_date()
        table = self.store.qualified_table(self.store.settings.tables.market_daily_table)
        with self.store.market_engine.begin() as conn:
            return conn.execute(text(f"SELECT max(trade_date) FROM {table}")).scalar_one()

    def load_raw_bars(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        table = self.store.qualified_table(self.store.settings.tables.market_daily_table)
        query = text(
            "SELECT ts_code, trade_date, open, high, low, close, pre_close, vol, amount, adj_factor "
            f"FROM {table} WHERE ts_code = :symbol AND trade_date BETWEEN :start AND :end ORDER BY trade_date"
        )
        with self.store.market_engine.begin() as conn:
            return [dict(row) for row in conn.execute(
                query, {"symbol": symbol, "start": start, "end": end}).mappings()]

    def create_session(self, *, seed: int | None = None) -> GameSession:
        latest = self.latest_trade_date()
        symbols = self.store.list_symbols_with_bars(date(2000, 1, 1), latest)
        rng = random.Random(seed)
        rng.shuffle(symbols)
        required = self.factory.warmup_bars + self.factory.game_bars
        for symbol in symbols[:self.candidate_limit]:
            if hasattr(self.store, "load_raw_bars"):
                rows = self.store.load_raw_bars(symbol, date(2000, 1, 1), latest)
            else:
                rows = self.load_raw_bars(symbol, date(2000, 1, 1), latest)
            bars = bars_from_rows(rows)
            if len(bars) >= required:
                session = self.factory.create({symbol: bars}, seed=seed)
                session.price_anchor = qfq_anchor(rows)
                session.factor_errors = {}
                session.factor_audit = None
                if self.with_factors:
                    self.load_selected(session, DEFAULT_CANONICALS)
                return session
        raise GameRuleError(f"历史数据不足：前 {self.candidate_limit} 个候选均无至少 {required} 根 K 线")

    def load_selected(self, session: GameSession, canonicals) -> tuple[str, ...]:
        """只加载尚未读取的 canonical；同列不同口径互不覆盖。"""
        selected = resolve_selection(canonicals)
        session.selected_canonicals = selected
        targets = [canonical for canonical in selected if canonical not in session.loaded_canonicals]
        if not targets:
            return selected
        scaled = price_scaled_canonicals(targets)
        anchor = float(getattr(session, "price_anchor", None) or 1.0)
        errors = getattr(session, "factor_errors", None)
        if errors is None:
            errors = session.factor_errors = {}
        frames = []
        failed = False
        try:
            batch = self._load_factor_frame(session, targets)
        except Exception as exc:  # 因子表异常不得让开局 500
            failed = True
            batch = None
        if batch is not None and not batch.empty:
            frames.append(batch)
        if failed:
            for canonical in targets:
                try:
                    single = self._load_factor_frame(session, [canonical])
                except Exception as exc:
                    errors[canonical] = type(exc).__name__
                    continue
                if not single.empty and canonical in single.columns:
                    frames.append(single)
        session.loaded_canonicals.update(targets)
        if not frames:
            session.factor_audit = audit_price_factors(
                session.bars, session.factors, session.selected_canonicals)
            return selected

        def normalize_day(value):
            return value.date() if isinstance(value, pd.Timestamp) else value

        by_date: dict[Any, dict[str, Any]] = {}
        for frame in frames:
            for row in frame.to_dict("records"):
                day = normalize_day(row["trade_date"])
                current = by_date.setdefault(day, {})
                for canonical in targets:
                    if canonical not in row:
                        continue
                    value = row.get(canonical)
                    if value is not None and not pd.isna(value):
                        current[canonical] = float(value)
        for index, bar in enumerate(session.bars):
            row = by_date.get(bar.trade_date)
            if not row:
                continue
            values = {}
            for canonical, value in row.items():
                if scaled.get(canonical, False):
                    value = value / anchor if anchor else value
                values[canonical] = value
            if values:
                session.factors.setdefault(index, {}).update(values)
        session.factor_audit = audit_price_factors(
            session.bars, session.factors, session.selected_canonicals)
        return selected

    def _load_factor_frame(self, session: GameSession, targets) -> pd.DataFrame:
        requests = [FactorFieldRequest.from_target(canonical, canonical) for canonical in targets]
        return self.store.load_factor_history(
            [session.symbol], requests, session.bars[0].trade_date, session.bars[-1].trade_date)
