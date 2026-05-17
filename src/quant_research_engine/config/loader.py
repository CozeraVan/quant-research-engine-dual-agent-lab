from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from quant_research_engine.markets.ashare import AShareMarketProfile


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file)
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML file must contain a mapping: {path}")
    return loaded


def load_market_profile(path: str | Path) -> AShareMarketProfile:
    config = load_yaml(path)
    raw_profile = config.get("market_profile")
    if not isinstance(raw_profile, dict):
        raise ValueError("market_profile section is required")

    name = raw_profile.get("name", "ashare_daily_default")
    lot_size = raw_profile.get("lot_size", {})
    price_limit = raw_profile.get("price_limit", {})
    costs = raw_profile.get("costs", {})
    slippage = raw_profile.get("slippage", {})

    return AShareMarketProfile(
        name=name,
        buy_lot=int(lot_size.get("buy_lot", 100)),
        allow_odd_lot_sell=bool(lot_size.get("allow_odd_lot_sell", True)),
        commission_rate=float(costs.get("commission_rate", 0.0003)),
        min_commission=float(costs.get("min_commission", 5.0)),
        stamp_tax_sell=float(costs.get("stamp_tax_sell", 0.0005)),
        transfer_fee_rate=float(costs.get("transfer_fee_rate", 0.00001)),
        slippage_model=str(slippage.get("model", "percent")),
        slippage_buy_rate=float(slippage.get("buy_rate", 0.0)),
        slippage_sell_rate=float(slippage.get("sell_rate", 0.0)),
        price_limit_by_board={
            "main_board": float(price_limit.get("main_board", 0.10)),
            "chinext": float(price_limit.get("chinext", 0.20)),
            "star_market": float(price_limit.get("star_market", 0.20)),
            "beijing": float(price_limit.get("beijing", 0.30)),
            "st": float(price_limit.get("st", 0.05)),
        },
    )
