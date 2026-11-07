#!/usr/bin/env python3
"""Render the classic-catalog smoke JSONL as stable Markdown and JSON reports."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    anomalies = []
    for row in rows:
        summary = row.get("summary") or {}
        for key, value in summary.items():
            if not isinstance(value, (int, float)):
                continue
            if not math.isfinite(value):
                anomalies.append({"strategy_id": row["strategy_id"], "field": key, "issue": "nonfinite"})
            elif ("return" in key or "drawdown" in key) and abs(value) > 10:
                anomalies.append({"strategy_id": row["strategy_id"], "field": key, "issue": "extreme", "value": value})
    return {
        "total": len(rows),
        "unique_strategies": len({row["strategy_id"] for row in rows}),
        "status": dict(Counter(row.get("status") or "submit_failed" for row in rows)),
        "entry_mode": dict(Counter(row["entry_mode"] for row in rows)),
        "entry_errors": dict(Counter(row["entry_mode"] for row in rows if row.get("entry_error"))),
        "semantic_mismatch": sum(row.get("semantic_equivalent") is False for row in rows),
        "zero_trades": [row["strategy_id"] for row in rows if (row.get("summary") or {}).get("total_trade_count") == 0],
        "anomalies": anomalies,
        "failed": [
            {"strategy_id": row["strategy_id"], "job_id": row.get("job_id"),
             "entry_mode": row["entry_mode"], "error_class": row.get("error_class"),
             "error": row.get("error") or row.get("submit_error")}
            for row in rows if row.get("status") != "completed"
        ],
    }


def _pct(value: Any) -> str:
    return f"{value * 100:.4f}%" if isinstance(value, (int, float)) and math.isfinite(value) else "—"


def render(rows: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        "# 经典策略公网三入口与 100 股两年冒烟报告",
        "",
        "> 本报告验证入口、执行和统计管线；小样本收益不是策略有效性结论或投资建议。",
        "",
        f"- 总数 **{summary['total']}**（唯一 {summary['unique_strategies']}）；状态 `{summary['status']}`；入口 `{summary['entry_mode']}`。",
        f"- 入口能力错误 `{summary['entry_errors']}`；NL 语义不一致回退 **{summary['semantic_mismatch']}**；零交易 **{len(summary['zero_trades'])}**；数值异常 **{len(summary['anomalies'])}**。",
        "",
        "## 失败项",
        "",
        "| 策略 | 入口 | Job | 错误 |",
        "|---|---|---:|---|",
    ]
    for row in summary["failed"]:
        lines.append(f"| `{row['strategy_id']}` | {row['entry_mode']} | {row['job_id'] or '—'} | {row['error'] or '—'} |")
    lines.extend(["", "## 零交易项", "", "- " + "、".join(f"`{item}`" for item in summary["zero_trades"]), "",
                  "## 全量明细", "",
                  "| 策略 | 入口 | Job | 状态 | 交易数 | 总收益 | 最大回撤 | 入口/语义备注 |",
                  "|---|---|---:|---|---:|---:|---:|---|"])
    for row in rows:
        result = row.get("summary") or {}
        notes = []
        if row.get("entry_error"):
            notes.append("入口不支持，回退原 YAML")
        if row.get("semantic_equivalent") is False:
            notes.append("NL 语义不同，回退原 YAML")
        lines.append(
            f"| `{row['strategy_id']}` | {row['entry_mode']} | {row.get('job_id') or '—'} | "
            f"{row.get('status') or 'submit_failed'} | {result.get('total_trade_count', '—')} | "
            f"{_pct(result.get('strategy_total_return'))} | {_pct(result.get('max_drawdown'))} | {'；'.join(notes) or '—'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path(".tmp/classic-catalog-public-smoke/results.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/agent/classic_catalog"))
    args = parser.parse_args()
    rows = [json.loads(line) for line in args.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Retries append a new row; the latest attempt is authoritative for the report.
    rows = list({row["strategy_id"]: row for row in rows}.values())
    summary = audit(rows)
    payload = {"generated_at": datetime.now(timezone.utc).isoformat(), "summary": summary, "results": rows}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "smoke_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.output_dir / "SMOKE_REPORT.md").write_text(render(rows, summary), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
