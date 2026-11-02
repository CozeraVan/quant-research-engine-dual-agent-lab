#!/usr/bin/env python3
"""M6 验收：模拟一个真实外部 AI Agent，只用文档化的 /api/agent/v1/* 接口跑完全流程。

流程（对齐设计文档 §12 验收方向）：
  发现 → 校验 → 建研究会话 → screen 抽样扫描 → 轮询 → 聚合排名 → 读结果 → 提交结论

只用 HTTP + Bearer 令牌，不碰任何内部模块——证明「凭 token 自描述接入」成立。
用法：uv run python .tmp/agent-m6/agent_client.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

import uuid

BASE = "http://127.0.0.1:18077/api/agent/v1"
RUN_TAG = uuid.uuid4().hex[:8]  # 每次运行唯一，避开历史幂等键
TOKEN = sys.argv[1] if len(sys.argv) > 1 else ""
if not TOKEN:
    print("用法：agent_client.py <agent token>")
    raise SystemExit(2)

BASE_YAML = """experiment:
  name: ema_period_scan
data:
  factor_fields:
    ema_fast: factors.stock_daily_overlap_typical_price.ema_5
    ema_slow: factors.stock_daily_overlap_typical_price.ema_200
signal:
  entry: 'ema_fast > ema_slow'
  exit: 'ema_fast < ema_slow'
evaluation:
  forward_return_horizons: [1, 5]
holding:
  max_holding_days: 20
"""

STEPS: list[str] = []


def call(method: str, path: str, body: dict | None = None, query: str = "") -> tuple[int, dict]:
    url = f"{BASE}{path}" + (f"?{query}" if query else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw[:300]}


def check(name: str, cond: bool, detail: str = "") -> None:
    STEPS.append(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  :: {detail}" if detail else ""))
    if not cond:
        print("\n".join(STEPS))
        raise SystemExit(1)


def main() -> None:
    # 1) 发现：成本信封 + openapi + schema
    status, caps = call("GET", "/capabilities")
    check("GET /capabilities", status == 200 and caps.get("ok"), f"http={status}")
    profiles = [p["name"] for p in caps["capabilities"]["scale_profiles"]]
    check("成本信封含 4 档", len(profiles) == 4, ",".join(profiles))
    check("响应带免责声明", "disclaimer" in caps)

    status, doc = call("GET", "/openapi.json")
    check("GET /openapi.json", status == 200 and doc["openapi"]["info"]["version"] == "v1")
    check("openapi 不含未实现端点", "/jobs" not in doc["openapi"]["paths"])

    status, schema = call("GET", "/schema/strategy")
    check("GET /schema/strategy", status == 200 and schema["schema"]["type"] == "object")

    # 2) 校验：不执行、不计配额
    status, val = call("POST", "/validate", {
        "yaml": BASE_YAML,
        "params": {"random_n": 20, "start": "2024-01-02", "end": "2025-06-30"},
    })
    check("POST /validate 合法", status == 200 and val["validate"]["valid"] is True,
          json.dumps(val["validate"]["issues"], ensure_ascii=False))
    check("validate 不执行不计配额",
          val["validate"]["executed"] is False and val["validate"]["quota_charged"] is False)
    check("成本估计匹配档位", val["validate"]["cost_estimate"]["profile"] == "sample300_5y")

    status, bad = call("POST", "/validate", {"yaml": "signal: [", "params": {}})
    check("validate 拒绝非法 YAML", status == 200 and bad["validate"]["valid"] is False)

    # 3) 建研究会话（带预算）
    status, run = call("POST", "/research-runs", {
        "title": "M6 验收：EMA 周期是否有意义",
        "boundary_text": "只测 EMA 快慢线交叉，随机 20 只，近两年；不做投资建议",
        "todo": [{"step": 1, "what": "EMA 周期扫描 screen"},
                 {"step": 2, "what": "聚合排名"}],
        "budget": {"max_jobs": 10, "max_wall_clock_hours": 2},
    })
    check("POST /research-runs", status == 201, f"http={status} {json.dumps(run)[:200]}")
    run_id = run["research_run"]["id"]
    check("会话预算已收敛", run["research_run"]["budget"]["max_jobs"] == 10)

    # 4) screen 扫描（3 个配置）
    status, sweep = call("POST", "/sweeps", {
        "research_run_id": run_id,
        "base_yaml": BASE_YAML,
        "grid": {"data.factor_fields.ema_fast": [
            "factors.stock_daily_overlap_typical_price.ema_5",
            "factors.stock_daily_overlap_typical_price.ema_10",
            "factors.stock_daily_overlap_typical_price.ema_20",
        ]},
        "params": {"random_n": 20, "start": "2024-01-02", "end": "2025-06-30"},
        "stage": "screen",
        "idempotency_key": f"m6-screen-{RUN_TAG}",
        "labels": {"purpose": "m6-acceptance"},
    })
    check("POST /sweeps screen", status in (201, 202), f"http={status} {json.dumps(sweep)[:300]}")
    sweep_id = sweep["sweep"]["id"]
    check("展开 3 个配置", sweep["sweep"]["job_count"] == 3)

    # 幂等：同键不重复展开
    status, again = call("POST", "/sweeps", {
        "research_run_id": run_id, "base_yaml": BASE_YAML,
        "grid": {"data.factor_fields.ema_fast": [
            "factors.stock_daily_overlap_typical_price.ema_5"]},
        "params": {"random_n": 20, "start": "2024-01-02", "end": "2025-06-30"},
        "stage": "screen", "idempotency_key": f"m6-screen-{RUN_TAG}",
    })
    check("幂等键去重", status == 200 and again.get("deduped") is True)

    # 5) 轮询到终态
    deadline = time.time() + 600
    jobs = []
    while time.time() < deadline:
        status, detail = call("GET", f"/sweeps/{sweep_id}")
        jobs = detail.get("jobs", [])
        if jobs and all(j["status"] in ("completed", "failed", "canceled") for j in jobs):
            break
        time.sleep(5)
    check("3 个 job 全部终态", bool(jobs) and all(
        j["status"] in ("completed", "failed", "canceled") for j in jobs),
        json.dumps([(j["id"], j["status"]) for j in jobs]))
    done = [j for j in jobs if j["status"] == "completed"]
    check("至少 1 个 job 成功", len(done) >= 1, f"completed={len(done)}/{len(jobs)}")

    # 6) 聚合（只回数字）
    status, agg = call("GET", f"/sweeps/{sweep_id}/aggregate", query="sort_by=sharpe")
    check("GET aggregate", status == 200 and agg["aggregate"]["total"] == 3)
    check("聚合无解读字段", "不含任何投资建议" in agg["aggregate"]["note"])
    rows = agg["aggregate"]["rows"]
    check("聚合行含 config 与状态", all("config" in r and "status" in r for r in rows))
    numeric = [r for r in rows if r["total_return"] is not None]
    check("完成的 job 有数值", len(numeric) == len(done), f"numeric={len(numeric)} done={len(done)}")

    # 7) 读结果（默认不含 chart_data）
    if done:
        status, res = call("GET", f"/jobs/{done[0]['id']}/result")
        check("GET result", status == 200 and "summary" in res["result"], f"http={status}")
        check("result 默认不含 chart_data", "chart_data" not in res["result"])
        check("result 带 sweep/run 归属",
              res["result"]["sweep_id"] == sweep_id and res["result"]["research_run_id"] == run_id)
        status, chart = call("GET", f"/jobs/{done[0]['id']}/result/chart-data")
        check("chart-data 按需可取", status == 200 and "chart_data" in chart)
        status, missing = call("GET", f"/jobs/{done[0]['id']}/artifacts/../../etc/passwd")
        check(" artifacts 穿越被拒", status in (308, 404), f"http={status}")

    # 8) 会话用量 + 提交结论
    status, detail = call("GET", f"/research-runs/{run_id}")
    check("会话用量已记账", detail["research_run"]["usage"]["jobs_total"] == 3,
          json.dumps(detail["research_run"]["usage"]))
    status, concl = call("POST", f"/research-runs/{run_id}/conclusion", {
        "conclusion_text": "M6 验收：全流程打通；结论由外部 agent 提供，QRE 原样存储",
        "conclusion_table": rows,
    })
    check("POST conclusion", status == 200 and concl["research_run"]["status"] == "concluded")
    status, final = call("GET", f"/research-runs/{run_id}")
    check("结论原样读回", final["research_run"]["conclusion_text"].startswith("M6 验收"))

    print("\n".join(STEPS))
    print(f"\nM6 验收通过：run_id={run_id} sweep_id={sweep_id} "
          f"completed={len(done)}/{len(jobs)}")


if __name__ == "__main__":
    main()
