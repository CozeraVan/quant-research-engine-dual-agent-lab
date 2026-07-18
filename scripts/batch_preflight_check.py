#!/usr/bin/env python3
"""Check factor availability for all strategy catalog YAMLs against the database.

Usage:
  uv run python scripts/batch_preflight_check.py              # check all
  uv run python scripts/batch_preflight_check.py --category trend_following
  uv run python scripts/batch_preflight_check.py --output-json report.json
  uv run python scripts/batch_preflight_check.py --start 2024-01-01 --end 2024-06-01

Outputs a JSON report with per-strategy preflight status, factor coverage,
and missing factor details. Prints a human-readable summary table to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "strategies" / "catalog"


@dataclass
class StrategyCheckResult:
    strategy_id: str
    category: str
    yaml_path: str
    preflight_status: str  # ok | warning | error | db_unavailable
    factor_coverage: float | None = None
    universe_size: int | None = None
    missing_factors: list[str] = field(default_factory=list)
    error_message: str = ""
    duration_s: float = 0.0


def discover_strategies(catalog_dir: Path, category: str | None = None) -> list[Path]:
    """Find all low-level strategy YAML files in the catalog."""
    if category:
        target = catalog_dir / category
        if not target.is_dir():
            print(f"Category not found: {category}", file=sys.stderr)
            sys.exit(1)
        return sorted(target.glob("*.yaml"))
    return sorted(catalog_dir.rglob("*.yaml"))


def check_db() -> tuple[bool, str]:
    """Check if the database is reachable. Returns (available, message)."""
    try:
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings

        settings = DatabaseSettings.from_env()
        if not settings.market_db_url:
            return False, "QRE_MARKET_DB_URL / SR_MARKET_DB_URL not set"
        store = PostgresDataStore(settings)
        store.ping()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def run_preflight_check(
    yaml_path: Path,
    start: date,
    end: date,
) -> StrategyCheckResult:
    """Run preflight for a single strategy YAML. Returns check result."""
    t0 = time.perf_counter()

    rel = yaml_path.relative_to(CATALOG_DIR)
    category = rel.parts[0] if len(rel.parts) > 1 else "root"
    strategy_id = yaml_path.stem

    result = StrategyCheckResult(
        strategy_id=strategy_id,
        category=category,
        yaml_path=str(yaml_path),
        preflight_status="error",
    )

    try:
        from quant_research_engine.data.postgres import PostgresDataStore
        from quant_research_engine.data.settings import DatabaseSettings
        from quant_research_engine.preflight import PreflightRequest, PreflightRunner
        from quant_research_engine.strategies.spec import StrategySpec

        spec = StrategySpec.from_yaml(yaml_path)

        settings = DatabaseSettings.from_env()
        store = PostgresDataStore(settings)
        store.ping()

        preflight_req = PreflightRequest(
            ts_codes=None,
            start=start,
            end=end,
            market_fields=spec.market_fields,
            factor_fields=spec.factor_fields,
            min_factor_coverage=0.5,
            exclude_st=spec.exclude_st,
            exclude_suspended=spec.exclude_suspended,
            exclude_risk_warning=spec.exclude_risk_warning,
            min_listing_days=spec.min_listing_days,
            min_amount=spec.min_amount,
        )

        report = PreflightRunner(store).run(preflight_req)
        result.preflight_status = report.status
        result.factor_coverage = getattr(report, "factor_coverage", None)
        result.universe_size = getattr(report, "universe_size", None)

        # Extract missing factor details
        if hasattr(report, "missing_factors") and report.missing_factors:
            result.missing_factors = [
                str(mf) if not isinstance(mf, str) else mf
                for mf in report.missing_factors
            ]

        if hasattr(report, "missing_factor_requests") and report.missing_factor_requests:
            for mfr in report.missing_factor_requests:
                if hasattr(mfr, "expected_column"):
                    result.missing_factors.append(
                        f"{getattr(mfr, 'expected_table', '?')}.{mfr.expected_column}"
                    )

    except Exception as exc:
        result.preflight_status = "error"
        result.error_message = str(exc)

    result.duration_s = time.perf_counter() - t0
    return result


def print_summary(results: list[StrategyCheckResult]) -> None:
    """Print a human-readable summary table."""
    ok = sum(1 for r in results if r.preflight_status == "ok")
    warn = sum(1 for r in results if r.preflight_status == "warning")
    err = sum(1 for r in results if r.preflight_status == "error")
    total = len(results)

    print(f"\n{'='*80}")
    print(f"Preflight Check Summary: {total} strategies checked")
    print(f"  OK: {ok} | Warning: {warn} | Error: {err}")
    print(f"{'='*80}\n")

    # Print by status
    for status, label in [("error", "ERRORS"), ("warning", "WARNINGS"), ("ok", "READY")]:
        group = [r for r in results if r.preflight_status == status]
        if not group:
            continue
        print(f"--- {label} ({len(group)}) ---")
        for r in group[:20]:  # Show first 20 per group
            cov_str = f"{r.factor_coverage:.1%}" if r.factor_coverage is not None else "?"
            univ_str = str(r.universe_size) if r.universe_size is not None else "?"
            print(f"  [{r.category}] {r.strategy_id:50s}  cov={cov_str:>6s}  universe={univ_str:>6s}")
            if r.missing_factors:
                print(f"    missing: {', '.join(r.missing_factors[:5])}")
            if r.error_message:
                print(f"    error: {r.error_message[:120]}")
        if len(group) > 20:
            print(f"  ... and {len(group) - 20} more")
        print()


def write_json_report(
    results: list[StrategyCheckResult],
    output_path: Path,
    db_available: bool,
    db_message: str,
    start: str,
    end: str,
) -> None:
    """Write full results as JSON."""
    payload: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db_available": db_available,
        "db_message": db_message,
        "date_range": {"start": start, "end": end},
        "summary": {
            "total": len(results),
            "ok": sum(1 for r in results if r.preflight_status == "ok"),
            "warning": sum(1 for r in results if r.preflight_status == "warning"),
            "error": sum(1 for r in results if r.preflight_status == "error"),
        },
        "strategies": [
            {
                "strategy_id": r.strategy_id,
                "category": r.category,
                "yaml_path": r.yaml_path,
                "preflight_status": r.preflight_status,
                "factor_coverage": r.factor_coverage,
                "universe_size": r.universe_size,
                "missing_factors": r.missing_factors,
                "error_message": r.error_message,
                "duration_s": round(r.duration_s, 3),
            }
            for r in results
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Report written to {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Check factor availability for all strategy YAMLs")
    parser.add_argument("--category", help="Limit to one category directory")
    parser.add_argument("--start", default="2024-01-01", help="Start date (default: 2024-01-01)")
    parser.add_argument("--end", default="2024-03-01", help="End date (default: 2024-03-01)")
    parser.add_argument("--output-json", type=Path, help="Write full JSON report to this path")
    parser.add_argument("--ready-only", action="store_true", help="Only show strategies that pass preflight")
    args = parser.parse_args()

    if not CATALOG_DIR.is_dir():
        print(f"Catalog directory not found: {CATALOG_DIR}", file=sys.stderr)
        print("Run scripts/generate_strategy_yamls.py first.", file=sys.stderr)
        return 1

    # Discover YAML files
    yaml_paths = discover_strategies(CATALOG_DIR, args.category)
    if not yaml_paths:
        print(f"No strategy YAMLs found in {CATALOG_DIR}")
        return 1
    print(f"Found {len(yaml_paths)} strategy YAMLs")

    # Check DB availability
    db_available, db_message = check_db()
    if not db_available:
        print(f"Database not available: {db_message}")
        print("Set QRE_MARKET_DB_URL or SR_MARKET_DB_URL to run preflight checks.")
        return 1
    print("Database connected.")

    # Run preflight for each strategy
    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)
    results: list[StrategyCheckResult] = []

    for i, yp in enumerate(yaml_paths):
        print(f"[{i+1}/{len(yaml_paths)}] {yp.stem} ... ", end="", flush=True)
        result = run_preflight_check(yp, start_date, end_date)
        results.append(result)
        print(f"{result.preflight_status} ({result.duration_s:.1f}s)")
        if result.missing_factors and result.preflight_status != "ok":
            print(f"         missing: {', '.join(result.missing_factors[:3])}")

    # Print summary
    if args.ready_only:
        ready = [r for r in results if r.preflight_status == "ok"]
        print(f"\nReady strategies ({len(ready)}):")
        for r in ready:
            print(f"  {r.strategy_id}")
    else:
        print_summary(results)

    # Write JSON if requested
    if args.output_json:
        write_json_report(results, args.output_json, db_available, db_message, args.start, args.end)

    # Exit code: 0 if any passed, 1 if all failed
    ok_count = sum(1 for r in results if r.preflight_status in ("ok", "warning"))
    return 0 if ok_count > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
