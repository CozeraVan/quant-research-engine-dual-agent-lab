#!/usr/bin/env python3
"""从本地行情库导出 3–5 只匿名真实快照；不连接或修改生产库。"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from quant_research_engine.data.catalog import FactorFieldRequest
from quant_research_engine.data.postgres import PostgresDataStore
from quant_research_engine.data.settings import DatabaseSettings
from quant_research_engine.data.universe_rules import filter_untrusted_symbols
from quant_research_engine.game.data import PostgresGameDataProvider
from quant_research_engine.game.factors import factor_catalog

REQUIRED_BARS = 1500


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def export_snapshots(
    *,
    output_dir: Path,
    count: int = 3,
    seed: int = 20261112,
    candidate_limit: int = 20,
    date_offset_days: int = 3650,
) -> list[dict[str, Any]]:
    if not 3 <= count <= 5:
        raise ValueError("快照数量必须为 3–5 只")
    store = PostgresDataStore(DatabaseSettings.from_env())
    store.ping()
    provider = PostgresGameDataProvider(store, candidate_limit=candidate_limit)
    latest = provider.latest_trade_date()
    symbols = filter_untrusted_symbols(
        store.list_symbols_with_bars(date(2000, 1, 1), latest),
        load_start=date(2000, 1, 1),
    )
    random.Random(seed).shuffle(symbols)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, Any]] = []
    # 与 GUI 增选全集一致；不能只导 DEFAULT_CANONICALS 让真实副图空白。
    requests = []
    skipped_factor_targets = []
    for item in factor_catalog():
        try:
            requests.append(FactorFieldRequest.from_target(item["canonical"], item["canonical"]))
        except ValueError:
            # 少数上游列名含 %，不受 FactorFieldRequest DSL 支持；显式登记而非静默丢弃。
            skipped_factor_targets.append(item["canonical"])
    for source_symbol in symbols[:candidate_limit]:
        rows = [
            row for row in provider.load_raw_bars(source_symbol, date(2000, 1, 1), latest)
            if row.get("adj_factor") is not None and row["adj_factor"] > 0
        ][-REQUIRED_BARS:]
        if len(rows) < REQUIRED_BARS:
            continue
        anonymous = f"X{len(manifest) + 1:05d}B"
        offset = timedelta(days=date_offset_days)
        def shifted_day(value: Any) -> str:
            day = value.date() if hasattr(value, "date") else value
            return (day + offset).isoformat()

        bars = []
        for row in rows:
            item = {key: _clean(value) for key, value in row.items()}
            item["ts_code"] = anonymous
            item["trade_date"] = shifted_day(row["trade_date"])
            bars.append(item)
        start, end = rows[0]["trade_date"], rows[-1]["trade_date"]
        factor_frame = store.load_factor_history([source_symbol], requests, start, end)
        factors = []
        for source in factor_frame.to_dict("records"):
            item = {key: _clean(value) for key, value in source.items()}
            item["ts_code"] = anonymous
            item["trade_date"] = shifted_day(source["trade_date"])
            factors.append(item)
        payload = {
            "schema_version": 1,
            "symbol": anonymous,
            "display_name": "B",
            "bars": bars,
            "factors": factors,
        }
        path = output_dir / f"{anonymous.lower()}.json"
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        path.write_text(serialized, encoding="utf-8")
        manifest.append({
            "file": path.name,
            "symbol": anonymous,
            "bars": len(bars),
            "factor_rows": len(factors),
            "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        })
        if len(manifest) == count:
            break
    if len(manifest) < count:
        raise RuntimeError(f"候选 {candidate_limit} 只中仅 {len(manifest)} 只满足 {REQUIRED_BARS} 根")
    metadata = {
        "schema_version": 1,
        "seed": seed,
        "candidate_limit": candidate_limit,
        "date_offset_days": date_offset_days,
        "skipped_factor_targets": skipped_factor_targets,
        "snapshots": manifest,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/game_snapshots"))
    parser.add_argument("--count", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--candidate-limit", type=int, default=20)
    parser.add_argument("--date-offset-days", type=int, default=3650)
    args = parser.parse_args()
    manifest = export_snapshots(
        output_dir=args.output_dir,
        count=args.count,
        seed=args.seed,
        candidate_limit=args.candidate_limit,
        date_offset_days=args.date_offset_days,
    )
    print(json.dumps({"exported": len(manifest), "snapshots": manifest}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
