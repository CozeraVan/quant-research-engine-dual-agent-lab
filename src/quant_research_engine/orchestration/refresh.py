"""Continuous strategy refresh (M10.3): watermark detection, refresh state,
rolling-window computation, and delta reports between batches.

Idempotent by design: a refresh re-runs the catalog on a rolling window with
the vectorized runner; there is no incremental engine state to keep
consistent. All database access is read-only (R-QRE-005).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text

DELTA_MANIFEST_KIND = "strategy_refresh_delta_manifest"


# ---------------------------------------------------------------------------
# watermark + state
# ---------------------------------------------------------------------------


def data_watermark(store) -> date | None:
    """Latest trade_date in the market daily table (read-only)."""
    table = store.qualified_table(store.settings.tables.market_daily_table)
    with store.market_engine.begin() as conn:
        value = conn.execute(text(f"SELECT MAX(trade_date) FROM {table}")).scalar()
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@dataclass
class RefreshState:
    last_data_date: str | None = None
    last_run_at: str | None = None
    last_batch_dir: str | None = None
    window_years: int = 2
    codes: list[str] | None = None
    strategy_count: int = 0
    ok_count: int = 0
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RefreshState":
        return cls(
            last_data_date=payload.get("last_data_date"),
            last_run_at=payload.get("last_run_at"),
            last_batch_dir=payload.get("last_batch_dir"),
            window_years=int(payload.get("window_years", 2)),
            codes=payload.get("codes"),
            strategy_count=int(payload.get("strategy_count", 0)),
            ok_count=int(payload.get("ok_count", 0)),
            config=dict(payload.get("config", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_data_date": self.last_data_date,
            "last_run_at": self.last_run_at,
            "last_batch_dir": self.last_batch_dir,
            "window_years": self.window_years,
            "codes": self.codes,
            "strategy_count": self.strategy_count,
            "ok_count": self.ok_count,
            "config": self.config,
        }


def load_state(state_path: Path) -> RefreshState | None:
    if not state_path.exists():
        return None
    return RefreshState.from_dict(json.loads(state_path.read_text(encoding="utf-8")))


def save_state(state_path: Path, state: RefreshState) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def needs_refresh(data_date: date, state: RefreshState | None) -> bool:
    if state is None or not state.last_data_date:
        return True
    return data_date > date.fromisoformat(state.last_data_date)


def compute_window(data_date: date, window_years: int) -> tuple[date, date]:
    """Rolling window ending at the data watermark (calendar years)."""
    if window_years <= 0:
        raise ValueError("window_years must be positive")
    try:
        start = data_date.replace(year=data_date.year - window_years)
    except ValueError:  # Feb 29 → Feb 28
        start = data_date.replace(year=data_date.year - window_years, day=28)
    return start, data_date


# ---------------------------------------------------------------------------
# delta computation
# ---------------------------------------------------------------------------


def _load_batch_metrics(batch_dir: Path) -> dict[str, dict[str, Any]]:
    """Per-strategy status + metrics from a batch directory."""
    summary_path = batch_dir / "batch_summary.json"
    if not summary_path.exists():
        return {}
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    metrics: dict[str, dict[str, Any]] = {}
    for entry in payload.get("results", []):
        sid = entry.get("strategy_id", "")
        row: dict[str, Any] = {
            "status": entry.get("status"),
            "category": entry.get("category"),
        }
        metrics_path = Path(entry.get("output_dir", "")) / "backtest" / "summary_metrics.json"
        if metrics_path.exists():
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
            row.update(
                {
                    "mean_total_return": m.get("mean_total_return"),
                    "total_trades": m.get("total_trades"),
                    "positive_return_symbol_rate": m.get("positive_return_symbol_rate"),
                }
            )
        metrics[sid] = row
    return metrics


def compute_delta(previous_batch_dir: Path | None, new_batch_dir: Path) -> list[dict[str, Any]]:
    """Per-strategy delta rows between two batches (sorted by strategy_id)."""
    previous = _load_batch_metrics(previous_batch_dir) if previous_batch_dir else {}
    current = _load_batch_metrics(new_batch_dir)
    rows: list[dict[str, Any]] = []
    for sid in sorted(set(previous) | set(current)):
        prev = previous.get(sid)
        cur = current.get(sid)
        if prev is None:
            transition = "new"
        elif cur is None:
            transition = "removed"
        elif prev["status"] != cur["status"]:
            transition = f"{prev['status']}->{cur['status']}"
        else:
            transition = "unchanged"
        row: dict[str, Any] = {
            "strategy_id": sid,
            "category": (cur or prev).get("category"),
            "transition": transition,
            "status": cur["status"] if cur else None,
        }
        for key in ("mean_total_return", "total_trades", "positive_return_symbol_rate"):
            prev_v = prev.get(key) if prev else None
            cur_v = cur.get(key) if cur else None
            row[f"prev_{key}"] = prev_v
            row[f"current_{key}"] = cur_v
            row[f"delta_{key}"] = (
                cur_v - prev_v
                if isinstance(prev_v, (int, float)) and isinstance(cur_v, (int, float))
                else None
            )
        rows.append(row)
    return rows


def write_delta_report(
    output_dir: Path,
    *,
    data_date: date,
    window: tuple[date, date],
    previous_batch_dir: Path | None,
    new_batch_dir: Path,
    delta_rows: list[dict[str, Any]],
    generated_at: str | None = None,
) -> dict[str, Path]:
    """Write delta_report.json/md + report_manifest.json. Returns paths."""
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()

    paths = {
        "delta_report_json": output_dir / "delta_report.json",
        "delta_report_md": output_dir / "delta_report.md",
        "report_manifest": output_dir / "report_manifest.json",
    }
    payload = {
        "generated_at": generated_at,
        "data_date": str(data_date),
        "window": {"start": str(window[0]), "end": str(window[1])},
        "previous_batch_dir": str(previous_batch_dir) if previous_batch_dir else None,
        "new_batch_dir": str(new_batch_dir),
        "strategy_count": len(delta_rows),
        "changed": sum(1 for r in delta_rows if r["transition"] != "unchanged"),
        "rows": delta_rows,
    }
    paths["delta_report_json"].write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )

    lines = [
        "# Strategy Refresh Delta Report",
        "",
        f"- data_date: {data_date}",
        f"- window: {window[0]} → {window[1]}",
        f"- previous: {previous_batch_dir or '(none — first run)'}",
        f"- new: {new_batch_dir}",
        f"- strategies: {len(delta_rows)}; changed: {payload['changed']}",
        "",
        "> Screening evidence only — not a research conclusion (R-QRE-008).",
        "",
        "| strategy | transition | prev mean return | new mean return | delta |",
        "|---|---|---|---|---|",
    ]
    for row in delta_rows:
        lines.append(
            f"| {row['strategy_id']} | {row['transition']} | "
            f"{_fmt(row['prev_mean_total_return'])} | {_fmt(row['current_mean_total_return'])} | "
            f"{_fmt(row['delta_mean_total_return'])} |"
        )
    lines.append("")
    paths["delta_report_md"].write_text("\n".join(lines), encoding="utf-8")

    manifest = {
        "schema_version": 1,
        "kind": DELTA_MANIFEST_KIND,
        "generated_at": generated_at,
        "files": [
            {"key": key, "path": path.name, "filename": path.name, "role": role}
            for key, role in (
                ("delta_report_json", "refresh_delta_report"),
                ("delta_report_md", "refresh_delta_markdown"),
                ("report_manifest", "report_manifest"),
            )
            for path in [paths[key]]
        ],
    }
    paths["report_manifest"].write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    return paths


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)
