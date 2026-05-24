from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from quant_research_engine.evaluation.models import EvaluationResult


def _manifest_role(key: str) -> str:
    if key == "summary":
        return "evaluation_summary"
    if key == "group_summary" or key.startswith("group_summary_by_"):
        return "evaluation_group_summary"
    if key == "random_baseline_summary":
        return "random_baseline_summary"
    if key == "run_manifest":
        return "run_manifest"
    return key


def _manifest_group_by(key: str) -> str | None:
    if key.startswith("group_summary_by_"):
        return key.removeprefix("group_summary_by_")
    return None


def _manifest_entry(key: str, path: Path, output_dir: Path) -> dict[str, object]:
    entry: dict[str, object] = {
        "key": key,
        "path": path.relative_to(output_dir).as_posix(),
        "filename": path.name,
        "role": _manifest_role(key),
    }
    group_by_col = _manifest_group_by(key)
    if group_by_col is not None:
        entry["group_by"] = group_by_col
    return entry


def write_evaluation_output(
    result: EvaluationResult,
    output_dir: Path,
    *,
    run_id: str | None = None,
    strategy_path: str,
    start: str | None = None,
    end: str | None = None,
    codes: list[str] | None = None,
    round_trip_cost_rate: float | None = None,
    market_profile: str | None = None,
    group_by: list[str] | None = None,
    random_baseline_seed: int | None = None,
) -> dict[str, Path]:
    """Write evaluation CSVs, run_manifest.json, and report_manifest.json.

    Returns a dict mapping artifact keys to Paths.
    """
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    artifact_paths: dict[str, Path] = {}

    events_path = directory / "events.csv"
    result.events.to_csv(events_path, index=False)
    artifact_paths["events"] = events_path

    if not result.summary.empty:
        p = directory / "summary.csv"
        result.summary.to_csv(p, index=False)
        artifact_paths["summary"] = p

    if not result.ic_summary.empty:
        p = directory / "ic_summary.csv"
        result.ic_summary.to_csv(p, index=False)
        artifact_paths["ic_summary"] = p

    if not result.quantile_summary.empty:
        p = directory / "quantile_summary.csv"
        result.quantile_summary.to_csv(p, index=False)
        artifact_paths["quantile_summary"] = p

    if not result.group_summary.empty:
        p = directory / "group_summary.csv"
        result.group_summary.to_csv(p, index=False)
        artifact_paths["group_summary"] = p
        for group_column in sorted(result.group_summary["group_by"].dropna().unique()):
            per_col = result.group_summary[result.group_summary["group_by"] == group_column]
            p_col = directory / f"group_summary_by_{group_column}.csv"
            per_col.to_csv(p_col, index=False)
            artifact_paths[f"group_summary_by_{group_column}"] = p_col

    if not result.random_baseline_summary.empty:
        p = directory / "random_baseline_summary.csv"
        result.random_baseline_summary.to_csv(p, index=False)
        artifact_paths["random_baseline_summary"] = p

    if not result.factor_decay_summary.empty:
        p = directory / "factor_decay_summary.csv"
        result.factor_decay_summary.to_csv(p, index=False)
        artifact_paths["factor_decay_summary"] = p

    run_manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "evaluation_run_manifest",
        "run_id": run_id,
        "command": "eval-config",
        "strategy_path": strategy_path,
        "start": start,
        "end": end,
        "codes": codes,
        "round_trip_cost_rate": round_trip_cost_rate,
        "market_profile": market_profile,
        "group_by": group_by,
        "random_baseline_seed": random_baseline_seed,
        "artifacts": sorted(artifact_paths.keys()),
    }
    run_manifest_path = directory / "run_manifest.json"
    run_manifest_path.write_text(
        json.dumps(run_manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["run_manifest"] = run_manifest_path

    files = sorted(
        (_manifest_entry(key, path, directory) for key, path in artifact_paths.items()),
        key=lambda f: str(f["key"]),
    )
    report_manifest_payload: dict[str, object] = {
        "schema_version": 1,
        "kind": "evaluation_report_manifest",
        "files": files,
    }
    report_manifest_path = directory / "report_manifest.json"
    report_manifest_path.write_text(
        json.dumps(report_manifest_payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["report_manifest"] = report_manifest_path

    return artifact_paths
