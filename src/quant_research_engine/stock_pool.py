"""最近交易日单条件股票池：只读行情与预计算因子，不计算指标。"""

from __future__ import annotations

import math
import re
from typing import Any

from sqlalchemy import create_engine, text

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_OPERATORS = {">", ">=", "<", "<=", "=", "!="}


def _field(value: Any, name: str) -> tuple[str, str, str]:
    parts = str(value or "").split(".")
    if len(parts) != 3 or any(not _IDENTIFIER.fullmatch(part) for part in parts):
        raise ValueError(f"{name} 必须是合法的 数据模式.表.字段")
    schema, table, column = parts
    if (schema, table) != ("public", "stock_daily") and schema != "factors":
        raise ValueError(f"{name} 只允许行情表或 factors 因子表")
    return schema, table, column


def normalize_condition(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("condition 须为对象")
    left = ".".join(_field(raw.get("left"), "左侧字段"))
    operator = str(raw.get("operator") or "")
    if operator not in _OPERATORS:
        raise ValueError("不支持的比较操作符")
    right_raw = raw.get("right")
    if isinstance(right_raw, str) and len(right_raw.split(".")) == 3:
        right: str | float = ".".join(_field(right_raw, "右侧字段"))
    else:
        try:
            right = float(right_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("右侧须为字段或数值") from exc
        if not math.isfinite(right):
            raise ValueError("右侧数值必须有限")
    return {"left": left, "operator": operator, "right": right}


def _quoted_field(canonical: str, alias: str) -> tuple[str, str, str]:
    schema, table, column = _field(canonical, alias)
    return schema, table, column


def _factor_join(canonical: str, alias: str) -> str:
    schema, table, column = _quoted_field(canonical, alias)
    return (
        f' JOIN "{schema}"."{table}" {alias} ON {alias}.ts_code=m.ts_code '
        f'AND {alias}.trade_date=m.trade_date'
    )


def _value_sql(canonical: str, alias: str) -> str:
    schema, table, column = _quoted_field(canonical, alias)
    if (schema, table) == ("public", "stock_daily"):
        return f'm."{column}"'
    return f'{alias}."{column}"'


def screen_latest_stock_pool(raw_condition: dict[str, Any], engine) -> dict[str, Any]:
    condition = normalize_condition(raw_condition)
    left, operator, right = condition["left"], condition["operator"], condition["right"]
    joins = ""
    if not left.startswith("public.stock_daily."):
        joins += _factor_join(left, "l")
    left_sql = _value_sql(left, "l")
    params: dict[str, Any] = {}
    if isinstance(right, str):
        if not right.startswith("public.stock_daily."):
            joins += _factor_join(right, "r")
        right_sql = _value_sql(right, "r")
    else:
        right_sql = ":right_number"
        params["right_number"] = right
    with engine.connect() as conn:
        latest = conn.execute(text("SELECT max(trade_date) FROM public.stock_daily")).scalar_one()
        if latest is None:
            return {"trade_date": None, "total_count": 0, "matched_count": 0,
                    "condition": condition, "stocks": []}
        params["latest"] = latest
        total = int(conn.execute(text(
            "SELECT count(*) FROM public.stock_daily WHERE trade_date=:latest"
        ), {"latest": latest}).scalar_one())
        rows = conn.execute(text(
            "SELECT m.ts_code,b.name,m.close," + left_sql + " AS left_value,"
            + right_sql + " AS right_value FROM public.stock_daily m "
            "LEFT JOIN reference.stock_basic b ON b.ts_code=m.ts_code "
            + joins + " WHERE m.trade_date=:latest AND " + left_sql
            + " " + operator + " " + right_sql + " ORDER BY m.ts_code"
        ), params).mappings().all()
    stocks = [{
        "ts_code": row["ts_code"], "name": row["name"],
        "close": float(row["close"]) if row["close"] is not None else None,
        "left_value": float(row["left_value"]) if row["left_value"] is not None else None,
        "right_value": float(row["right_value"]) if row["right_value"] is not None else None,
    } for row in rows]
    return {"trade_date": str(latest), "total_count": total, "matched_count": len(stocks),
            "condition": condition, "stocks": stocks}


def screen_latest_strategy_pool(yaml_text: str, engine, *, lookback_days: int = 400) -> dict[str, Any]:
    """StrategySpec entry → 最新截面；按股票分组求值，shift不跨标的。"""
    from datetime import timedelta
    import ast
    import pandas as pd
    import yaml
    from quant_research_engine.evaluation.signals import evaluate_expression_signal, referenced_fields
    from quant_research_engine.security.yaml_guard import validate_strategy_yaml

    verdict = validate_strategy_yaml(yaml_text)
    if not verdict.get("ok"):
        raise ValueError("；".join(verdict.get("issues") or ["策略YAML不合法"]))
    spec = yaml.safe_load(yaml_text) or {}
    data = spec.get("data") or {}
    expression = str((spec.get("signal") or {}).get("entry") or "").strip()
    if not expression:
        raise ValueError("策略缺少signal.entry")
    ast.parse(expression, mode="eval")
    used = referenced_fields(expression)
    market_columns = sorted((set(data.get("market_fields") or []) | {"close"}) & used | {"close"})
    for column in market_columns:
        _field(f"public.stock_daily.{column}", "行情字段")
    with engine.connect() as conn:
        latest = conn.execute(text("SELECT max(trade_date) FROM public.stock_daily")).scalar_one()
        if latest is None:
            return {"trade_date": None, "total_count": 0, "matched_count": 0,
                    "condition": {"expression": expression}, "stocks": []}
        total = int(conn.execute(text(
            "SELECT count(*) FROM public.stock_daily WHERE trade_date=:latest"
        ), {"latest": latest}).scalar_one())
        names = dict(conn.execute(text("SELECT ts_code,name FROM reference.stock_basic")).all())
    start = latest - timedelta(days=int(lookback_days))
    column_sql = ",".join(f'"{column}"' for column in market_columns)
    frame = pd.read_sql(text(
        f"SELECT ts_code,trade_date,{column_sql} FROM public.stock_daily "
        "WHERE trade_date BETWEEN :start AND :latest"
    ), engine, params={"start": start, "latest": latest})
    by_table: dict[str, list[tuple[str, str]]] = {}
    for alias, target in (data.get("factor_fields") or {}).items():
        if alias not in used:
            continue
        schema, table, column = _field(target, "因子字段")
        by_table.setdefault(f'"{schema}"."{table}"', []).append((str(alias), column))
    for table_sql, columns in by_table.items():
        select = ",".join(f'"{column}" AS "{alias}"' for alias, column in columns)
        factor = pd.read_sql(text(
            f"SELECT ts_code,trade_date,{select} FROM {table_sql} "
            "WHERE trade_date BETWEEN :start AND :latest"
        ), engine, params={"start": start, "latest": latest})
        frame = frame.merge(factor, on=["ts_code", "trade_date"], how="left")
    frame["trade_date"] = pd.to_datetime(frame["trade_date"])
    frame = frame.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)
    stocks = []
    for ts_code, group in frame.groupby("ts_code", sort=True):
        group = group.reset_index(drop=True)
        mask = evaluate_expression_signal(group, expression)
        latest_mask = group["trade_date"].dt.date == latest
        if not bool((mask & latest_mask).any()):
            continue
        close = group.loc[latest_mask, "close"].iloc[-1]
        stocks.append({"ts_code": str(ts_code), "name": names.get(ts_code),
                       "close": float(close) if pd.notna(close) else None,
                       "left_value": None, "right_value": None})
    return {"trade_date": str(latest), "total_count": total, "matched_count": len(stocks),
            "condition": {"expression": expression}, "lookback_days": int(lookback_days),
            "stocks": stocks}


def execute_stock_pool_job(job: dict[str, Any]) -> dict[str, Any]:
    from quant_research_engine.data.settings import DatabaseSettings

    params = job.get("params") or job.get("params_json") or {}
    if isinstance(params, str):
        import json
        params = json.loads(params)
    engine = create_engine(DatabaseSettings.from_env().market_db_url)
    try:
        if params.get("strategy_yaml"):
            result = screen_latest_strategy_pool(str(params["strategy_yaml"]), engine)
        else:
            result = screen_latest_stock_pool(params.get("condition"), engine)
    finally:
        engine.dispose()
    summary = {"kind": "stock_pool", **result}
    return {
        "summary": summary,
        "chart_data": {"stocks": result["stocks"], "condition": result["condition"]},
        "artifacts": [], "files": [],
        "result_files": {"truncated": False, "included_count": 0, "included_bytes": 0,
                         "skipped_count": 0, "skipped_bytes": 0, "missing_count": 0},
        "data_until": result["trade_date"],
    }
