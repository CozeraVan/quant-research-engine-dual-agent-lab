"""把已完成的回测核心产物导出到用户本地目录。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from .client import AgentAPIClient, AgentAPIConfig

COMPACT_ARTIFACTS = (
    "report_manifest.json",
    "summary_metrics.json",
    "strategy_performance.json",
    "equity_curve.csv",
    "drawdown_curve.csv",
    "round_trips.csv",
    "trades_ledger.csv",
    "symbol_performance.csv",
    "summary.md",
    "backtest_report.html",
)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def export_backtest(client: AgentAPIClient, job_id: int, output_root: Path) -> dict[str, Any]:
    """下载核心产物到 `<output_root>/job_<id>`；校验 hash 后原子改名。

    不覆盖既有目录，避免误删用户历史结果。缺省不下载逐股目录、图片和 Excel。
    """
    payload = client.request("GET", f"/jobs/{job_id}/result")
    result = payload.get("result")
    if not isinstance(result, dict) or result.get("status") != "completed":
        raise ValueError("仅可导出已完成回测")
    available = {
        item.get("name"): item for item in result.get("artifacts", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    selected = [name for name in COMPACT_ARTIFACTS if name in available]
    destination = output_root.expanduser().resolve() / f"job_{job_id}"
    if destination.exists():
        raise FileExistsError(f"导出目录已存在：{destination}")
    output_root.expanduser().mkdir(parents=True, exist_ok=True)
    temporary = output_root.expanduser().resolve() / f".job_{job_id}.partial"
    if temporary.exists():
        raise FileExistsError(f"存在未完成的导出目录：{temporary}")
    temporary.mkdir()
    downloaded: list[dict[str, Any]] = []
    try:
        _write_json(temporary / "result.json", payload)
        for name in selected:
            content = client.download_artifact(job_id, name)
            expected = available[name].get("sha256")
            actual = hashlib.sha256(content).hexdigest()
            if expected and actual != expected:
                raise ValueError(f"产物 SHA-256 校验失败：{name}")
            (temporary / name).write_bytes(content)
            downloaded.append({"name": name, "size": len(content), "sha256": actual})
        manifest = {
            "schema_version": "qre-local-export-v1",
            "job_id": job_id,
            "run_id": (result.get("summary") or {}).get("run_id"),
            "profile": "compact",
            "files": [{"name": "result.json", "size": (temporary / "result.json").stat().st_size}] + downloaded,
            "disclaimer": "本研究结果仅供研究使用，不构成投资建议。",
        }
        _write_json(temporary / "local_manifest.json", manifest)
        temporary.rename(destination)
    except Exception:
        shutil.rmtree(temporary)  # 仅清理本轮新建的 partial，避免留下半成品
        raise
    return {"output_dir": str(destination), "file_count": len(downloaded) + 2,
            "bytes": sum(item["size"] for item in downloaded), "manifest": manifest}


def main() -> None:
    parser = argparse.ArgumentParser(description="导出 QRE 回测核心结果到本地")
    parser.add_argument("job_id", type=int)
    parser.add_argument("--output", type=Path, default=Path("qre-results"))
    args = parser.parse_args()
    result = export_backtest(
        AgentAPIClient(AgentAPIConfig.from_user()), args.job_id, args.output,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
