"""Durable missing-factor request queue (QRE-MISSING-FACTOR-QUEUE-001).

The queue is the operational handoff to the upstream `indicators_tushare`
project: strategies that need indicators/periods absent from the factor DB
get their requests consolidated here, upstream computes and ingests them,
and `recheck_fulfillment` marks entries fulfilled so shelved strategies can
be re-enabled.

Storage: a consolidated JSON file (default
`outputs/handoff/missing_factor_requests.json`). A DB mirror is a later
option pending the user's target-DB decision (write access per R-QRE-005).

Entry shape (backward-compatible with the M8.3 contract, plus queue fields):
  strategy_id, alias, indicator, category, source, period, params, output,
  expected_table, expected_column, date_range, reason, required,
  first_seen, last_seen, status ("pending" | "fulfilled"), fulfilled_at
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from quant_research_engine.strategies.missing_factor import (
    _parse_category,
    _parse_column,
    _parse_source,
)

DEFAULT_QUEUE_PATH = Path("outputs/handoff/missing_factor_requests.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# queue store
# ---------------------------------------------------------------------------


def load_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def save_queue(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(entries, key=lambda e: (e.get("status", "") != "pending", e.get("strategy_id", ""), e.get("alias", "")))
    path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_requests(
    entries: list[dict[str, Any]],
    requests: list[dict[str, Any]],
    *,
    seen_at: str | None = None,
) -> int:
    """Merge new requests into the queue. Dedup by (strategy_id, alias).

    Existing entries keep their first_seen and get last_seen/metadata refreshed;
    new entries are added with status "pending". Returns the number added.
    """
    seen_at = seen_at or _now_iso()
    index = {(e.get("strategy_id"), e.get("alias")): e for e in entries}
    added = 0
    for request in requests:
        key = (request.get("strategy_id"), request.get("alias"))
        existing = index.get(key)
        if existing is None:
            entry = dict(request)
            entry.setdefault("first_seen", seen_at)
            entry["last_seen"] = seen_at
            entry.setdefault("status", "pending")
            entry.setdefault("fulfilled_at", None)
            entries.append(entry)
            index[key] = entry
            added += 1
        else:
            existing.update({k: v for k, v in request.items() if k not in ("first_seen", "last_seen", "status", "fulfilled_at")})
            existing["last_seen"] = seen_at
    return added


def recheck_fulfillment(
    entries: list[dict[str, Any]],
    column_lookup: Callable[[str], set[str]],
    *,
    checked_at: str | None = None,
) -> dict[str, int]:
    """Mark pending entries fulfilled when their expected column now exists.

    ``column_lookup(qualified_table) -> set of column names`` (read-only).
    Returns counts: {"checked": n, "newly_fulfilled": n, "pending": n, "fulfilled": n}.
    """
    checked_at = checked_at or _now_iso()
    newly = 0
    pending = 0
    fulfilled = 0
    for entry in entries:
        if entry.get("status") == "fulfilled":
            fulfilled += 1
            continue
        columns = column_lookup(entry.get("expected_table", ""))
        if entry.get("expected_column") in columns:
            entry["status"] = "fulfilled"
            entry["fulfilled_at"] = checked_at
            newly += 1
            fulfilled += 1
        else:
            pending += 1
    return {"checked": len(entries), "newly_fulfilled": newly, "pending": pending, "fulfilled": fulfilled}


# ---------------------------------------------------------------------------
# request building from strategy specs
# ---------------------------------------------------------------------------


def find_missing_factor_columns(
    spec,
    column_lookup: Callable[[str], set[str]],
) -> list:
    """Factor fields of `spec` whose expected table/column is absent (read-only)."""
    missing = []
    for factor in getattr(spec, "factor_fields", []) or []:
        columns = column_lookup(factor.qualified_table)
        if factor.source_column not in columns:
            missing.append(factor)
    return missing


def build_requests_for_strategy(
    spec,
    missing_factors: list,
    *,
    strategy_id: str,
    start,
    end,
) -> list[dict[str, Any]]:
    """Build queue-ready request dicts for the given missing factor fields."""
    requests: list[dict[str, Any]] = []
    for factor in missing_factors:
        indicator, period, params, output = _parse_column(factor.source_column)
        requests.append(
            {
                "strategy_id": strategy_id,
                "alias": factor.logical_name,
                "indicator": indicator,
                "category": _parse_category(factor.source_table),
                "source": _parse_source(factor.source_table),
                "period": period,
                "params": params,
                "output": output,
                "expected_table": factor.qualified_table,
                "expected_column": factor.source_column,
                "date_range": {"start": str(start), "end": str(end)},
                "reason": f"factor required by strategy '{strategy_id}'",
                "required": True,
            }
        )
    requests.sort(key=lambda r: (r["strategy_id"], r["alias"]))
    return requests


def make_schema_column_lookup(store, cache: dict[str, set[str]] | None = None) -> Callable[[str], set[str]]:
    """Read-only per-table column lookup with caching (safe to share in-process)."""
    if cache is None:
        cache = {}

    def lookup(qualified_table: str) -> set[str]:
        if qualified_table not in cache:
            try:
                if store.table_exists(qualified_table):
                    cache[qualified_table] = set(store.get_table_columns(qualified_table))
                else:
                    cache[qualified_table] = set()
            except Exception:
                cache[qualified_table] = set()
        return cache[qualified_table]

    return lookup
