#!/usr/bin/env python3
"""把经典策略全量队列的开始/终态事件追加到长期 Markdown 日志。

只读 fullscale.py 已有的 job_ids.json / results.jsonl，不接触浏览器、数据库或回测。
首次运行会补记当前已有事件；之后由 events_state.json 去重。其他 agent 可在会话
或 token 切换后直接重启本脚本，不需要恢复内存状态。
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(".tmp/classic-catalog-fullscale")
JOB_IDS = STATE_DIR / "job_ids.json"
RESULTS = STATE_DIR / "results.jsonl"
SEEN = STATE_DIR / "events_state.json"
EVENT_LOG = Path("docs/agent/40_CF_QUEUE_EVENT_LOG_2026-11-04.md")


def _load(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _cell(value) -> str:
    return str(value if value is not None else "—").replace("|", "\\|").replace("\n", " ")


def _append(row: str) -> None:
    EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with EVENT_LOG.open("a", encoding="utf-8") as handle:
        handle.write(row + "\n")


def scan() -> tuple[int, int]:
    seen = _load(SEEN, {"starts": [], "terminals": []})
    seen_starts = set(seen["starts"])
    seen_terminals = set(seen["terminals"])
    starts = 0
    terminals = 0
    observed_at = datetime.now().astimezone().isoformat(timespec="seconds")
    job_ids = _load(JOB_IDS, {})
    for cf_id in sorted(job_ids):
        job_id = int(job_ids[cf_id])
        key = f"{cf_id}:{job_id}"
        if key in seen_starts:
            continue
        _append(f"| {_cell(observed_at)} | 开始 | {_cell(cf_id)} | {_cell(job_id)} | 已提交并归属 user 6 |")
        seen_starts.add(key)
        starts += 1
    for line in RESULTS.read_text(encoding="utf-8").splitlines() if RESULTS.exists() else []:
        if not line.strip():
            continue
        result = json.loads(line)
        status = str(result.get("status") or "unknown")
        recorded_at = str(result.get("recorded_at") or observed_at)
        key = f"{result.get('cf_id')}:{recorded_at}:{status}"
        if key in seen_terminals:
            continue
        summary = result.get("summary") or {}
        trades = summary.get("total_trade_count")
        detail = f"交易数 {trades}" if trades is not None else (result.get("error") or result.get("error_class") or "—")
        _append(
            f"| {_cell(recorded_at)} | {_cell(status)} | {_cell(result.get('cf_id'))} | "
            f"{_cell(result.get('job_id'))} | {_cell(detail)} |"
        )
        seen_terminals.add(key)
        terminals += 1
    if starts or terminals or not SEEN.exists():
        SEEN.write_text(json.dumps({
            "starts": sorted(seen_starts), "terminals": sorted(seen_terminals),
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return starts, terminals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=float, default=20.0)
    args = parser.parse_args()
    while True:
        starts, terminals = scan()
        if starts or terminals:
            print(json.dumps({"starts": starts, "terminals": terminals}), flush=True)
        if args.once:
            return 0
        time.sleep(max(1.0, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
