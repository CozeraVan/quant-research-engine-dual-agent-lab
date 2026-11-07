#!/usr/bin/env python3
"""Run classic strategies full-market/full-history as a numbered serial queue."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from driver import Browser, public_yaml

INVENTORY = Path("docs/agent/classic_catalog/inventory.json")
STATE_DIR = Path(".tmp/classic-catalog-fullscale")
STATE = STATE_DIR / "results.jsonl"
JOB_IDS = STATE_DIR / "job_ids.json"
START = "2009-01-05"
END = "2026-10-30"
OWNER_ID = 6  # 17157845743；用户指定全部 CF 结果归入此账号。
SSH_COMMAND = [
    "ssh", "-i", str(Path.home() / ".ssh" / "aguhuice_ed25519"),
    "-o", "BatchMode=yes", "deploy@47.119.127.40",
]
TERMINAL_STATES = {"completed", "failed", "expired", "canceled", "cancelled"}


def numbered_strategies() -> list[dict]:
    rows = json.loads(INVENTORY.read_text(encoding="utf-8"))["strategies"]
    return [{**row, "cf_id": f"CF-{index:03d}"} for index, row in enumerate(rows, 1)]


def _psql_command(sql: str, *, tuples_only: bool = False) -> list[str]:
    remote = ["sudo", "-n", "-u", "postgres", "psql", "-d", "aguhuice"]
    if tuples_only:
        remote += ["-At"]
    remote += ["-v", "ON_ERROR_STOP=1", "-c", sql]
    # SSH 会把远端参数重新拼成 shell 命令；必须作为单个、正确 quoting 的字符串传入。
    return SSH_COMMAND + [shlex.join(remote)]


def assign_owner(job_id: int, *, runner=subprocess.run) -> None:
    """备份并迁移 job/result/strategy 归属；重复执行不会覆盖原始备份口径。"""
    job_id = int(job_id)
    precheck = runner(
        _psql_command(f"SELECT count(*) FROM jobs WHERE id = {job_id}", tuples_only=True),
        check=True, capture_output=True, text=True,
    )
    if precheck.stdout.strip() != "1":
        raise RuntimeError(f"job {job_id} 归属预检失败：预期 1 行，得到 {precheck.stdout.strip()!r}")
    sql = f"""
BEGIN;
CREATE TABLE IF NOT EXISTS classic_owner_backup_job_{job_id}_jobs AS
  SELECT * FROM jobs WHERE id = {job_id} AND user_id <> {OWNER_ID};
CREATE TABLE IF NOT EXISTS classic_owner_backup_job_{job_id}_results AS
  SELECT * FROM results WHERE job_id = {job_id} AND user_id <> {OWNER_ID};
CREATE TABLE IF NOT EXISTS classic_owner_backup_job_{job_id}_strategies AS
  SELECT * FROM strategies WHERE id = (SELECT strategy_id FROM jobs WHERE id = {job_id})
    AND user_id <> {OWNER_ID};
UPDATE jobs SET user_id = {OWNER_ID} WHERE id = {job_id};
UPDATE results SET user_id = {OWNER_ID} WHERE job_id = {job_id};
UPDATE strategies SET user_id = {OWNER_ID}
  WHERE id = (SELECT strategy_id FROM jobs WHERE id = {job_id});
COMMIT;
"""
    runner(_psql_command(sql), check=True, capture_output=True, text=True)


def wait_owner(job_id: int, timeout_s: int = 10800, *, runner=subprocess.run,
               sleep=time.sleep) -> dict:
    """归属已迁移后从只读 SQL 轮询，避免原浏览器账号失去 API 可见性。"""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        sql = f"""SELECT json_build_object(
  'status', j.status, 'error_class', j.error_class, 'error', j.error_message,
  'summary', (SELECT r.summary FROM results r WHERE r.job_id = j.id)
) FROM jobs j WHERE j.id = {int(job_id)}"""
        response = runner(_psql_command(sql, tuples_only=True),
                          check=True, capture_output=True, text=True)
        result = json.loads(response.stdout)
        if result.get("status") in TERMINAL_STATES:
            return result
        sleep(30)
    raise TimeoutError(f"job {job_id} exceeded {timeout_s}s")


def submit(browser: Browser, row: dict, key_version: str = "v1") -> dict:
    yaml_text = public_yaml(Path("strategies/catalog", row["yaml_path"]).read_text(encoding="utf-8"))
    params = {
        "start": START, "end": END, "mode": "batch", "initial_cash": 100000,
        "max_positions": 0, "max_holding_days": 20,
        "entry_price": "open", "exit_price": "open",
        "profile_overrides": {
            "commission_rate": 0.0003, "min_commission": 5.0,
            "stamp_tax_sell": 0.0005, "slippage_buy_rate": 0, "slippage_sell_rate": 0,
        },
    }
    payload = {
        "name": f"{row['cf_id']}_{row['strategy_id']}", "yaml": yaml_text,
        "entry_mode": "yaml", "kind": "full", "params": params,
        "idempotency_key": f"{row['cf_id']}-{row['strategy_id']}-{key_version}",
    }
    code = (
        "(async()=>{const r=await apiFetch('/api/saas/jobs',{json:"
        + json.dumps(payload, ensure_ascii=False) + "});const d=await r.json();"
        + "return {status:r.status,data:d};})()"
    )
    response = browser.evaluate(code)
    data = response.get("data") or {}
    return {"cf_id": row["cf_id"], "strategy_id": row["strategy_id"],
            "submit_http": response.get("status"), "job_id": data.get("job_id"),
            "submit_error": data.get("error")}


def retry_key_version(retry_counts: dict, cf_id: str) -> str:
    """幂等键版本：正常提交 v1；重跑一次 v2，以此类推（服务端按 key 去重）。"""
    return f"v{int(retry_counts.get(cf_id, 0)) + 1}"


def prepare_retry(retry_ids: list[str], job_ids: dict, retry_counts: dict) -> tuple[dict, dict]:
    """重跑准备：累加该 CF 的键版本，并摘掉旧 job 映射以强制重新提交。"""
    job_ids = dict(job_ids)
    retry_counts = dict(retry_counts)
    for cf_id in retry_ids:
        retry_counts[cf_id] = int(retry_counts.get(cf_id, 0)) + 1
        job_ids.pop(cf_id, None)
    return job_ids, retry_counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="CF id or strategy id")
    parser.add_argument("--resume", action="store_true")
    # 重跑指定 CF：服务端按 (user_id, idempotency_key) 去重，同键只会返回旧的
    # 失败 job，因此重跑必须换键。键版本按 CF 累计次数 v1→v2→v3，计数落盘，
    # 跨会话稳定（同一键的提交重试仍然安全，不会重复建单）。
    parser.add_argument("--retry", action="append", default=[], metavar="CF_ID",
                        help="resubmit this CF with a bumped idempotency key (repeatable)")
    args = parser.parse_args()
    retry_counts_path = STATE_DIR / "retry_counts.json"
    retry_counts = json.loads(retry_counts_path.read_text()) if retry_counts_path.exists() else {}
    done = set()
    if args.resume and STATE.exists():
        for line in STATE.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("status") == "completed":
                done.add(row["cf_id"])
    rows = numbered_strategies()
    if args.only:
        rows = [row for row in rows if row["cf_id"] == args.only or row["strategy_id"] == args.only]
    rows = [row for row in rows if row["cf_id"] not in done]
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    job_ids = json.loads(JOB_IDS.read_text()) if JOB_IDS.exists() else {}
    if args.retry:
        job_ids, retry_counts = prepare_retry(args.retry, job_ids, retry_counts)
        retry_counts_path.write_text(json.dumps(retry_counts, ensure_ascii=False) + "\n")
        JOB_IDS.write_text(json.dumps(job_ids, ensure_ascii=False, indent=2) + "\n")
    browser = Browser()
    for row in rows:
        if row["cf_id"] in job_ids:
            result = {"cf_id": row["cf_id"], "strategy_id": row["strategy_id"],
                      "job_id": job_ids[row["cf_id"]], "resumed": True}
        else:
            result = submit(browser, row, retry_key_version(retry_counts, row["cf_id"]))
            if result.get("job_id"):
                job_ids[row["cf_id"]] = result["job_id"]
                JOB_IDS.write_text(json.dumps(job_ids, ensure_ascii=False, indent=2) + "\n")
        if result.get("job_id"):
            assign_owner(result["job_id"])
            result["owner_user_id"] = OWNER_ID
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if result.get("job_id"):
            result.update(wait_owner(result["job_id"], timeout_s=10800))
            assign_owner(result["job_id"])
        result["recorded_at"] = datetime.now(timezone.utc).isoformat()
        with STATE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(json.dumps({"cf_id": row["cf_id"], "status": result.get("status"),
                          "trades": (result.get("summary") or {}).get("total_trade_count")}, ensure_ascii=False), flush=True)
        if result.get("status") != "completed":
            # Stop at the failed number; main agent dispatches repair before resume.
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
