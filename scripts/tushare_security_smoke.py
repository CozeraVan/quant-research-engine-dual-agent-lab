#!/usr/bin/env python3
"""Smoke-download small Tushare samples for security-status metadata.

This utility is read-only. It fetches tiny samples from Tushare endpoints
that are relevant to security-status metadata discovery and prints the
returned shapes. It does not write to PostgreSQL or mutate any local files.
"""

from __future__ import annotations

import argparse
import os
import sys
from quant_research_engine.data.tushare_security import SmokeResult, TushareSecuritySource


def _emit_result(result: SmokeResult) -> None:
    status = "ok" if result.ok else "blocked"
    print(f"[{result.name}] {status}: {result.message}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trade-date",
        default="20200312",
        help="Tushare trade_date for date-scoped endpoints, default: 20200312",
    )
    parser.add_argument(
        "--head",
        type=int,
        default=5,
        help="Number of rows to print from each returned frame, default: 5",
    )
    args = parser.parse_args(argv)

    token = os.environ.get("TUSHARE_TOKEN")
    if not token:
        print("TUSHARE_TOKEN is not set", file=sys.stderr)
        return 2

    try:
        import tushare as ts
    except Exception as exc:  # pragma: no cover - import-time smoke path
        print(f"tushare import failed: {exc!r}", file=sys.stderr)
        return 2

    ts.set_token(token)
    source = TushareSecuritySource(ts.pro_api())
    results = source.probe(trade_date=args.trade_date, head=args.head)

    for result in results:
        _emit_result(result)
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
