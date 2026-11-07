#!/usr/bin/env python3
"""Drive the public classic-catalog smoke through the existing browser session.

Plan mode is read-only apart from writing the local manifest. Execute mode submits
real public jobs, one at a time, and records results in a resumable JSONL file.
Credentials are never read: all public API calls run inside the WebBridge tab.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import create_engine, text

from quant_research_engine.data.settings import DatabaseSettings

SEED = 20261103
START = "2024-11-01"
END = "2026-10-30"
ENTRIES = ("nl", "wizard", "yaml")
STATE_DIR = Path(".tmp/classic-catalog-public-smoke")
PLAN_PATH = STATE_DIR / "plan.json"
RESULTS_PATH = STATE_DIR / "results.jsonl"

#: WebBridge 瞬断重试（CF-001 首跑即因 HTTP 502 Bad Gateway 终止：浏览器驱动/
#: 本地代理的瞬断是基础设施问题，不是策略失败，不应杀死整个 CF）。
#: 只对**传输层错误**（连接重置/超时/不可达）与 **502/503/504** 重试；
#: 命令级错误（payload ok=false，页面 JS 异常）与 4xx 是确定性失败，不重试。
#: 退避：0.5s 起倍增 + ≤0.25s 抖动，5 次尝试总睡眠 ≤ ~7.5s。
#: 提交重试安全：evaluate 里携带的 idempotency_key 不变，服务端按
#: (user_id, idempotency_key) 去重返回同一 job，不会重复建单。
WEBBRIDGE_MAX_ATTEMPTS = 5
WEBBRIDGE_BACKOFF_BASE_S = 0.5
WEBBRIDGE_BACKOFF_JITTER_S = 0.25
WEBBRIDGE_RETRY_STATUS = frozenset({502, 503, 504})

#: 命令级瞬断特征（WebBridge 把页面/网关侧瞬态故障报成 ok=false 的
#: extension_error）：CF-001/job227 等 2.6 小时后死在
#: 「evaluate: SyntaxError: Unexpected token '<', "<html>..." is not valid JSON」——
#: 页面 apiFetch 收到网关 HTML 错误页，r.json() 抛 SyntaxError。与传输层瞬断同罪：
#: 有限重试；确定性命令错误（JS 逻辑异常/业务拒绝）不重试。
#: 提交类调用重试安全由 payload 内 idempotency_key 保证（服务端去重）。
_TRANSIENT_COMMAND_PATTERNS = (
    "unexpected token '<'",   # 网关 HTML 错误页 → JSON.parse 失败
    "is not valid json",
    "failed to fetch",        # 页面网络错误
    "networkerror",
    "load failed",
    "bad gateway",
    "service unavailable",
    "gateway time-out",
    "gateway timeout",
    "timed out",
    "timeout",
)


def _is_transient_command_error(payload: dict[str, Any]) -> bool:
    """WebBridge 命令级错误是否瞬断（可重试）。ok=true 或确定性错误 → False。"""
    if not isinstance(payload, dict) or payload.get("ok"):
        return False
    text = " ".join(str(payload.get(key) or "") for key in ("error", "message", "detail")).lower()
    return any(pattern in text for pattern in _TRANSIENT_COMMAND_PATTERNS)

PUBLIC_SECTION_KEYS = {
    "experiment": {"name", "market_profile", "frequency"},
    "data": {"market_fields", "factor_fields"},
    "signal": {"entry", "exit"},
    "evaluation": {"forward_return_horizons", "quantiles"},
    "holding": {"max_holding_days"},
    "risk": {"stop_loss_pct", "take_profit_pct", "trailing_stop_pct"},
    "portfolio": {"weight_model", "score_column", "volatility_column", "rebalance_interval_days"},
    "universe": {"exclude_st", "exclude_suspended", "exclude_risk_warning", "min_listing_days", "min_amount"},
}


def public_yaml(yaml_text: str) -> str:
    """Strip legacy authoring-only keys while preserving executable strategy semantics."""
    source = yaml.safe_load(yaml_text)
    public = {
        section: {key: value for key, value in (source.get(section) or {}).items() if key in allowed}
        for section, allowed in PUBLIC_SECTION_KEYS.items() if section in source
    }
    return yaml.safe_dump(public, allow_unicode=True, sort_keys=False)


def expression_semantics(expression: str) -> str:
    normalized = expression.replace("&", " and ").replace("|", " or ")
    return ast.dump(ast.parse(normalized, mode="eval"), include_attributes=False)


def semantic_equal(left: str, right: str) -> bool:
    try:
        return expression_semantics(left) == expression_semantics(right)
    except (SyntaxError, ValueError):
        return left.strip() == right.strip()


def _operand(node: ast.AST) -> tuple[str, bool] | None:
    shifted = False
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr != "shift" or len(node.args) != 1:
            return None
        shifted = True
        node = node.func.value
    if isinstance(node, ast.Name):
        return node.id, shifted
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return str(node.value), shifted
    return None


def _condition(node: ast.AST) -> dict[str, Any] | None:
    if not isinstance(node, ast.Compare) or len(node.ops) != 1 or len(node.comparators) != 1:
        return None
    left = _operand(node.left)
    right = _operand(node.comparators[0])
    if left is None or right is None:
        return None
    op = node.ops[0]
    symbols = {ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<="}
    if type(op) not in symbols:
        return None
    return {
        "left": left[0], "left_shifted": left[1], "op": symbols[type(op)],
        "right": right[0], "right_shifted": right[1],
        "right_fixed": isinstance(node.comparators[0], ast.Constant),
    }


def _cross_condition(node: ast.AST) -> dict[str, Any] | None:
    if not isinstance(node, ast.BoolOp) or not isinstance(node.op, ast.And) or len(node.values) != 2:
        return None
    first, second = (_condition(value) for value in node.values)
    if first is None or second is None:
        return None
    direction = {(">", "<="): "crosses_above", ("<", ">="): "crosses_below"}.get((first["op"], second["op"]))
    if direction is None:
        return None
    if first["left"] != second["left"] or first["right"] != second["right"]:
        return None
    if first["left_shifted"] or first["right_shifted"] or not second["left_shifted"]:
        return None
    if not second["right_fixed"] and not second["right_shifted"]:
        return None
    return {
        "left": first["left"], "op": direction,
        "fixed": first["right"] if first["right_fixed"] else None,
        "right": None if first["right_fixed"] else first["right"],
    }


def _simple_condition(node: ast.AST) -> dict[str, Any] | None:
    cross = _cross_condition(node)
    if cross is not None:
        return cross
    cond = _condition(node)
    if cond is None or cond["left_shifted"] or cond["right_shifted"]:
        return None
    return {
        "left": cond["left"], "op": cond["op"],
        "fixed": cond["right"] if cond["right_fixed"] else None,
        "right": None if cond["right_fixed"] else cond["right"],
    }


def wizard_area(expression: str) -> dict[str, Any]:
    """Convert a two-level boolean expression to wizard state or reject it."""
    root = ast.parse(expression.replace("&", " and ").replace("|", " or "), mode="eval").body

    def is_bool(node: ast.AST) -> bool:
        return isinstance(node, ast.BoolOp)

    def comb(node: ast.AST) -> str:
        return "and" if isinstance(node.op, ast.And) else "or"

    direct = _simple_condition(root)
    if direct is not None:
        return {"groups": [{"comb": "and", "conds": [direct]}], "dividers": []}
    roots = root.values if is_bool(root) else [root]
    root_comb = comb(root) if is_bool(root) else "and"
    groups = []
    base_conditions = []
    for node in roots:
        direct = _simple_condition(node)
        if direct is not None:
            base_conditions.append(direct)
            continue
        if is_bool(node) and comb(node) != root_comb:
            conditions = [_simple_condition(value) for value in node.values]
            group_comb = comb(node)
        else:
            conditions = [None]
            group_comb = root_comb
        if not conditions or any(condition is None for condition in conditions):
            raise ValueError("expression exceeds wizard comparison/boolean capabilities")
        groups.append({"comb": group_comb, "conds": conditions})
    if base_conditions:
        groups.insert(0, {"comb": root_comb, "conds": base_conditions})
    return {"groups": groups, "dividers": [root_comb] * max(0, len(groups) - 1)}


def wizard_state(entry: str, exit_: str) -> dict[str, Any]:
    return {"entry": wizard_area(entry), "exit": wizard_area(exit_)}


def assign_entries(strategies: list[dict[str, Any]], seed: int = SEED) -> dict[str, str]:
    rng = random.Random(seed)
    assignment = {}
    categories = sorted({row["category"] for row in strategies})
    for category in categories:
        rows = [row for row in strategies if row["category"] == category]
        rng.shuffle(rows)
        offset = rng.randrange(len(ENTRIES))
        for index, row in enumerate(rows):
            assignment[row["strategy_id"]] = ENTRIES[(index + offset) % len(ENTRIES)]
    return assignment


def select_codes() -> list[str]:
    settings = DatabaseSettings.from_env()
    engine = create_engine(settings.market_db_url)
    with engine.connect() as conn:
        codes = conn.execute(text("""
            SELECT ts_code FROM public.stock_daily
            WHERE trade_date BETWEEN :start AND :end
            GROUP BY ts_code
            HAVING count(*) >= 400 AND min(trade_date) <= :start
            ORDER BY ts_code
        """), {"start": START, "end": END}).scalars().all()
    eligible = sorted(code for code in codes if not code.startswith("920"))
    if len(eligible) < 100:
        raise RuntimeError(f"only {len(eligible)} eligible symbols")
    return sorted(random.Random(SEED).sample(eligible, 100))


def build_plan(inventory_path: Path) -> dict[str, Any]:
    payload = json.loads(inventory_path.read_text(encoding="utf-8"))
    strategies = payload["strategies"]
    assignment = assign_entries(strategies)
    codes = select_codes()
    plan = {
        "created_at": datetime.now(timezone.utc).isoformat(), "seed": SEED,
        "start": START, "end": END, "codes": codes,
        "params": {
            "start": START, "end": END, "codes": codes, "mode": "batch",
            "initial_cash": 100000, "max_positions": 0, "max_holding_days": 20,
            "entry_price": "open", "exit_price": "open",
            "profile_overrides": {
                "commission_rate": 0.0003, "min_commission": 5.0,
                "stamp_tax_sell": 0.0005, "slippage_buy_rate": 0,
                "slippage_sell_rate": 0,
            },
        },
        "strategies": [{**row, "entry_mode": assignment[row["strategy_id"]]} for row in strategies],
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return plan


class Browser:
    def __init__(self, session: str = "classic-catalog-smoke", *,
                 max_attempts: int = WEBBRIDGE_MAX_ATTEMPTS,
                 sleep: Callable[[float], None] = time.sleep):
        self.session = session
        self.endpoint = os.environ.get("WEBBRIDGE_URL", "http://127.0.0.1:10086/command")
        self.max_attempts = max(1, int(max_attempts))
        self._sleep = sleep

    def evaluate(self, code: str) -> Any:
        """向 WebBridge 会话发 evaluate 命令；瞬断有限重试（见模块常量）。

        重试覆盖两层瞬断：
        1) **传输层**：urlopen 连接/超时错误、HTTP 502/503/504、daemon/代理返回
           非 JSON body（HTML 错误页 → json.load 抛 JSONDecodeError）；
        2) **命令层**：WebBridge 报 ok=false 且 message 命中瞬断特征（页面收到网关
           HTML 错误页的 JSON.parse SyntaxError、Failed to fetch、网关状态串等）。
        确定性失败（4xx、payload ok=false 的非瞬断消息）立即抛，不重试。
        提交类命令重试安全由 payload 内的 idempotency_key 保证（服务端去重，
        不重复建单）。
        """
        body = json.dumps({"action": "evaluate", "args": {"code": code}, "session": self.session}).encode()
        request = urllib.request.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"})
        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            payload = None
            try:
                with urllib.request.urlopen(request, timeout=180) as response:
                    payload = json.load(response)
            except json.JSONDecodeError as exc:
                # daemon/代理层返回 HTML 错误页（非 JSON）：瞬断
                last_error = exc
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code not in WEBBRIDGE_RETRY_STATUS:
                    raise RuntimeError(
                        f"WebBridge 请求失败（HTTP {exc.code}，不重试）：{exc}"
                    ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # URLError 含连接重置/拒绝；OSError 兜底 socket 类错误
                last_error = exc
            else:
                if payload.get("ok"):
                    data = payload["data"]
                    if data.get("type") == "object" and isinstance(data.get("value"), dict):
                        return data["value"]
                    return data.get("value")
                if not _is_transient_command_error(payload):
                    raise RuntimeError(payload)
                last_error = RuntimeError(payload)
            if attempt < self.max_attempts:
                self._sleep(WEBBRIDGE_BACKOFF_BASE_S * (2 ** (attempt - 1))
                            + random.uniform(0, WEBBRIDGE_BACKOFF_JITTER_S))
        raise RuntimeError(
            f"WebBridge 瞬断重试耗尽（{self.max_attempts} 次）：{last_error}"
        )

    def submit(self, row: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        strategy_id = row["strategy_id"]
        mode = row["entry_mode"]
        source_yaml = public_yaml(Path("strategies/catalog", row["yaml_path"]).read_text(encoding="utf-8"))
        compiled_yaml = source_yaml
        wizard = None
        entry_error = None
        equivalent = None
        if mode == "nl":
            description = (
                f"{row['description']} 入场规则：{row['declared_entry'] or row['entry']}；"
                f"出场规则：{row['declared_exit'] or row['exit'] or '按持仓期退出'}。"
            )
            code = (
                "(async()=>{const r=await apiFetch('/api/saas/nl/compile',{json:{description:"
                + json.dumps(description, ensure_ascii=False) + "}});const d=await r.json();"
                + "return {status:r.status,data:d};})()"
            )
            response = self.evaluate(code)
            data = response.get("data") or {}
            if response.get("status") != 200 or not data.get("ok"):
                entry_error = data.get("error") or data.get("code") or f"HTTP {response.get('status')}"
            else:
                compiled_yaml = data["yaml"]
                parsed = yaml.safe_load(compiled_yaml)
                equivalent = semantic_equal(parsed["signal"]["entry"], row["entry"]) and semantic_equal(
                    parsed["signal"].get("exit") or "", row["exit"]
                )
        elif mode == "wizard":
            try:
                wizard = wizard_state(row["entry"], row["exit"])
                setup = (
                    "(()=>{restoreWizardState(" + json.dumps(wizard, ensure_ascii=False) + ");"
                    + "refreshWizard();return {yaml:strategyYaml};})()"
                )
                compiled_yaml = self.evaluate(setup)["yaml"]
                parsed = yaml.safe_load(compiled_yaml)
                equivalent = semantic_equal(parsed["signal"]["entry"], row["entry"]) and semantic_equal(
                    parsed["signal"].get("exit") or "", row["exit"]
                )
            except (ValueError, SyntaxError) as exc:
                entry_error = str(exc)
                compiled_yaml = source_yaml
        # Uniform engine comparison always uses the original low-level YAML when an
        # entry cannot compile or changes semantics; entry failure is reported separately.
        run_yaml = compiled_yaml if equivalent is not False and entry_error is None else source_yaml
        payload = {
            "name": f"classic_20261103_{strategy_id}", "yaml": run_yaml,
            "nl_text": row["description"] if mode == "nl" else None,
            "entry_mode": mode, "wizard_state": wizard, "kind": "full", "params": params,
            "idempotency_key": f"classic-20261103-{strategy_id}-v4",
        }
        submit_code = (
            "(async()=>{const r=await apiFetch('/api/saas/jobs',{json:"
            + json.dumps(payload, ensure_ascii=False) + "});const d=await r.json();"
            + "return {status:r.status,data:d};})()"
        )
        response = self.evaluate(submit_code)
        data = response.get("data") or {}
        return {
            "strategy_id": strategy_id, "entry_mode": mode, "entry_error": entry_error,
            "semantic_equivalent": equivalent, "submit_http": response.get("status"),
            "job_id": data.get("job_id"), "submit_error": data.get("error"),
            "used_original_yaml": run_yaml == source_yaml,
        }

    def wait(self, job_id: int, timeout_s: int = 3600,
             sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
        """轮询 job 终态。evaluate 内建的瞬断重试使轮询本身可恢复
        （CF-001/job227：等待 2.6h 后一次网关 HTML 瞬断不该杀死整个等待）。"""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            code = (
                "(async()=>{const r=await apiFetch('/api/saas/jobs/" + str(job_id) + "');"
                + "const d=await r.json();const j=d.job||{};return {http:r.status,status:j.status,"
                + "error_class:j.error_class,error:j.error_message,summary:j.result&&j.result.summary};})()"
            )
            result = self.evaluate(code)
            if result.get("status") in {"completed", "failed", "expired", "canceled", "cancelled"}:
                return result
            sleep(5)
        raise TimeoutError(f"job {job_id} exceeded {timeout_s}s")


def append_result(result: dict[str, Any]) -> None:
    result = {**result, "recorded_at": datetime.now(timezone.utc).isoformat()}
    with RESULTS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=Path("docs/agent/classic_catalog/inventory.json"))
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--only", help="Execute one strategy id")
    parser.add_argument("--max-strategies", type=int)
    parser.add_argument("--no-wait", action="store_true")
    parser.add_argument("--retry-failed", action="store_true", help="Retry only non-completed strategies")
    args = parser.parse_args()
    if args.plan:
        plan = build_plan(args.inventory)
        print(json.dumps({"strategies": len(plan["strategies"]), "codes": len(plan["codes"]),
                          "entries": {mode: sum(row["entry_mode"] == mode for row in plan["strategies"]) for mode in ENTRIES},
                          "plan": str(PLAN_PATH)}, ensure_ascii=False))
        return 0
    if not args.execute:
        parser.error("use --plan or --execute")
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    done = set()
    if RESULTS_PATH.exists():
        for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines():
            previous = json.loads(line)
            if not args.retry_failed or previous.get("status") == "completed":
                done.add(previous["strategy_id"])
    rows = [row for row in plan["strategies"] if row["strategy_id"] not in done]
    if args.only:
        rows = [row for row in rows if row["strategy_id"] == args.only]
    if args.max_strategies:
        rows = rows[:args.max_strategies]
    browser = Browser()
    for index, row in enumerate(rows, 1):
        result = browser.submit(row, plan["params"])
        print(json.dumps({"index": index, **result}, ensure_ascii=False), flush=True)
        if result.get("job_id") and not args.no_wait:
            result.update(browser.wait(result["job_id"]))
            print(json.dumps({"finished": result["strategy_id"], "status": result.get("status"),
                              "trades": (result.get("summary") or {}).get("total_trade_count")}, ensure_ascii=False), flush=True)
        append_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
