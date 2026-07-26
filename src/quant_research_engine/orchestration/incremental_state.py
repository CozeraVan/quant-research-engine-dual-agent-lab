"""Incremental backtest checkpoint state (P1, batch mode).

File-based, per-strategy checkpoint living at
``outputs/state/<strategy_id>/state.json`` (see
``docs/design/incremental_backtest.md``). The checkpoint stores *resumable
state machine* content per symbol — open positions (entry info + trailing
anchor), live/dead pending orders, and per-symbol cash — never derived
results.

Invalidation semantics: :func:`load_checkpoint` returns ``None`` whenever the
schema version or the expected ``config_hash`` does not match, which the
caller treats as "no checkpoint" and falls back to a full rebuild.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


@dataclass
class SymbolState:
    """Resumable per-symbol engine state at the checkpoint boundary.

    ``pending_buy_date`` / ``pending_sell_date`` are *trigger bar* dates: the
    order executes at the first bar strictly after that date (per-symbol bar
    series). Storing the trigger rather than the execution date lets a
    pending scheduled at the last known bar survive until the execution bar
    appears in a later window.
    """

    cash: float
    quantity: int = 0
    entry_date: date | None = None
    entry_price: float | None = None
    entry_cost: float | None = None
    entry_cost_parts: dict[str, float] | None = None
    trailing_anchor: float | None = None
    pending_buy_date: date | None = None
    pending_sell_date: date | None = None
    pending_sell_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash": self.cash,
            "quantity": self.quantity,
            "entry_date": self.entry_date.isoformat() if self.entry_date else None,
            "entry_price": self.entry_price,
            "entry_cost": self.entry_cost,
            "entry_cost_parts": self.entry_cost_parts,
            "trailing_anchor": self.trailing_anchor,
            "pending_buy_date": self.pending_buy_date.isoformat() if self.pending_buy_date else None,
            "pending_sell_date": self.pending_sell_date.isoformat() if self.pending_sell_date else None,
            "pending_sell_reason": self.pending_sell_reason,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SymbolState":
        def _parse_date(value: Any) -> date | None:
            if value is None:
                return None
            return date.fromisoformat(str(value))

        return cls(
            cash=float(payload["cash"]),
            quantity=int(payload.get("quantity", 0)),
            entry_date=_parse_date(payload.get("entry_date")),
            entry_price=payload.get("entry_price"),
            entry_cost=payload.get("entry_cost"),
            entry_cost_parts=payload.get("entry_cost_parts"),
            trailing_anchor=payload.get("trailing_anchor"),
            pending_buy_date=_parse_date(payload.get("pending_buy_date")),
            pending_sell_date=_parse_date(payload.get("pending_sell_date")),
            pending_sell_reason=payload.get("pending_sell_reason"),
        )


@dataclass
class StrategyCheckpoint:
    """Per-strategy checkpoint (schema v1)."""

    strategy_id: str
    config_hash: str
    last_processed_date: date
    data_watermark: date
    symbols: dict[str, SymbolState] = field(default_factory=dict)
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "strategy_id": self.strategy_id,
            "config_hash": self.config_hash,
            "last_processed_date": self.last_processed_date.isoformat(),
            "data_watermark": self.data_watermark.isoformat(),
            "symbols": {symbol: state.to_dict() for symbol, state in sorted(self.symbols.items())},
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "StrategyCheckpoint":
        return cls(
            schema_version=int(payload["schema_version"]),
            strategy_id=str(payload["strategy_id"]),
            config_hash=str(payload["config_hash"]),
            last_processed_date=date.fromisoformat(str(payload["last_processed_date"])),
            data_watermark=date.fromisoformat(str(payload["data_watermark"])),
            symbols={
                str(symbol): SymbolState.from_dict(state)
                for symbol, state in (payload.get("symbols") or {}).items()
            },
        )


def compute_config_hash(
    spec_path: str | Path,
    engine_impl: str,
    profile_dict: dict[str, Any],
    stops_dict: dict[str, Any],
    universe_dict: dict[str, Any],
) -> str:
    """sha1[:12] over spec YAML bytes + engine + market/stop/universe params.

    Any change to any input changes the hash, which invalidates existing
    checkpoints (full-rebuild semantics).
    """
    digest = hashlib.sha1()
    digest.update(Path(spec_path).read_bytes())
    payload = {
        "engine_impl": engine_impl,
        "profile": profile_dict,
        "stops": stops_dict,
        "universe": universe_dict,
    }
    digest.update(json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()[:12]


def load_checkpoint(
    path: str | Path,
    expected_config_hash: str | None = None,
) -> StrategyCheckpoint | None:
    """Read a checkpoint; ``None`` when missing/corrupt/stale.

    Stale means: schema_version mismatch, or ``expected_config_hash`` given
    and different from the stored one. Callers treat ``None`` as "no
    checkpoint" and do a full (bootstrap) run.
    """
    path = Path(path)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        checkpoint = StrategyCheckpoint.from_dict(payload)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    if checkpoint.schema_version != SCHEMA_VERSION:
        return None
    if expected_config_hash is not None and checkpoint.config_hash != expected_config_hash:
        return None
    return checkpoint


def save_checkpoint(path: str | Path, checkpoint: StrategyCheckpoint) -> Path:
    """Persist the checkpoint as JSON. Written AFTER the ledgers."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(checkpoint.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path
