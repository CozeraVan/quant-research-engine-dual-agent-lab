"""因子目录与三步向导的纯函数层（QRE-GUI-FACTOR-WIZARD-001）。

- 因子目录：枚举 factors.* 表列（命名规律 stock_daily_<category>_<price_col>，
  已实际确认 11 张表），按类别分组 + 基础行情字段组。
- 表达式/YAML 生成：比较 + 布尔（AND/OR），因子 vs 因子/数值，入/出场组。
  生成结果过 engine.validate_yaml 校验；只填入编辑器，不自动执行（安全闸）。
"""

from __future__ import annotations

import re
from typing import Any

import yaml

from quant_research_engine.gui.engine import validate_yaml

MARKET_FIELDS = ["open", "high", "low", "close", "pre_close", "vol", "amount"]

CATEGORY_LABELS = {
    "candle": "K线形态",
    "momentum": "动量",
    "overlap": "均线/重叠",
    "performance": "绩效",
    "statistics": "统计",
    "trend": "趋势",
    "volatility": "波动率",
    "volume": "成交量",
    "vortex": "涡流",
    "alpha191": "Alpha191 量价因子",
}

PRICE_COLUMN_LABELS = {
    "close": "收盘价",
    "typical_price": "典型价",
    "average_price": "均价",
}

# factors.stock_daily_<category>_<price_col>
_TABLE_PATTERN = re.compile(r"^stock_daily_(?P<category>[a-z]+)_(?P<price>close|typical_price|average_price)$")

# 表内的非因子列
_SKIP_COLUMNS = frozenset({"ts_code", "trade_date"})

COMPARISON_OPERATORS = [">", ">=", "<", "<=", "==", "!="]

# 基础价格表统一优先级（QRE-WIZARD-PRICE-BASIS-001）：同一策略内同类指标
# 默认 close；仅当某周期在 close 表不存在时整组回退到能全覆盖的价格表。
PRICE_BASIS_PREFERENCE = ("close", "typical_price", "average_price")


def parse_factor_table_name(table: str) -> tuple[str, str] | None:
    """Parse ``stock_daily_<category>_<price_col>`` → (category, price_col)."""
    match = _TABLE_PATTERN.match(table)
    if not match:
        return None
    return match.group("category"), match.group("price")


def unify_factor_price_basis(
    factor_fields: dict[str, str],
    column_lookup: Any,
) -> list[dict[str, str]]:
    """同一策略内同类因子统一基础价格表（就地改写 factor_fields）。

    背景（job#71 复盘）：向导按「列名首次出现的表」定映射，用户同选
    ema_5 + ema_200 时，ema_5 落到 close 表、ema_200 落到 typical_price
    表（close 表无 ema_200 列），生成的 YAML 把同一均线的不同周期混在
    两种基础价格上，语义偏离用户预期。

    规则：
    - 按类别（``stock_daily_<category>_<price>``）分组，非标准命名
      （public.stock_daily、alpha191 面板表等）不动；
    - 组内按 PRICE_BASIS_PREFERENCE 找第一张**覆盖全部所选列**的价格表，
      整组迁移过去（默认 close；close 缺某周期时整组回退，如
      ema_5+ema_200 → typical_price，保持同组同口径）；
    - 没有任何一张表全覆盖时，逐列落到优先级最高的存在表；某列在所有
      标准价格表都不存在时保持原样（交给缺因子检查/纠错层处理）。

    ``column_lookup(qualified_table) -> set[str]``（只读，与
    factor_correction 同一约定）。返回改写记录 [{alias, from, to}, ...]。
    """
    parsed: dict[str, tuple[str, str, str]] = {}  # alias -> (category, table, column)
    for alias, target in factor_fields.items():
        parts = str(target).rsplit(".", 1)
        if len(parts) != 2:
            continue
        table, column = parts
        short = table.split("factors.", 1)[-1]
        name_parsed = parse_factor_table_name(short)
        if name_parsed is None:
            continue
        parsed[str(alias)] = (name_parsed[0], table, column)

    by_category: dict[str, list[str]] = {}
    for alias, (category, _table, _column) in parsed.items():
        by_category.setdefault(category, []).append(alias)

    remaps: list[dict[str, str]] = []
    for category in sorted(by_category):
        aliases = by_category[category]
        tables = {
            price: f"factors.stock_daily_{category}_{price}"
            for price in PRICE_BASIS_PREFERENCE
        }
        columns = {price: column_lookup(table) for price, table in tables.items()}
        needed = {parsed[a][2] for a in aliases}
        # 整组统一：优先级最高的全覆盖表
        group_price = next(
            (price for price in PRICE_BASIS_PREFERENCE
             if columns[price] and needed <= columns[price]),
            None,
        )
        for alias in aliases:
            _cat, table, column = parsed[alias]
            target_table = None
            if group_price is not None:
                target_table = tables[group_price]
            else:
                # 无全覆盖表：逐列回退到优先级最高的存在表
                for price in PRICE_BASIS_PREFERENCE:
                    if column in columns[price]:
                        target_table = tables[price]
                        break
            if target_table is None or target_table == table:
                continue
            old = factor_fields[alias]
            factor_fields[alias] = f"{target_table}.{column}"
            remaps.append({"alias": alias, "from": str(old), "to": factor_fields[alias]})
    return remaps


def format_price_basis_note(remaps: list[dict[str, str]]) -> str:
    """「已统一基础价格口径」的中文提示行。"""
    items = "、".join(f"{r['alias']}: {r['from']} → {r['to']}" for r in remaps)
    return (
        "已统一同类指标的基础价格口径（同一策略内默认 close，"
        f"某周期在 close 表缺失时整组回退到能全覆盖的价格表）：{items}"
    )


def build_factor_groups(tables_columns: dict[str, list[str]]) -> list[dict[str, Any]]:
    """Group factor columns by category.

    ``tables_columns``: {table_name: [column, ...]}（不含 schema 前缀的 factors 表）。
    Returns [{group, label, items: [{table, column, label}]}, ...]，首组为行情字段。
    """
    groups: list[dict[str, Any]] = [
        {
            "group": "market",
            "label": "行情字段",
            "items": [
                {"table": "public.stock_daily", "column": field, "label": f"行情 · {field}"}
                for field in MARKET_FIELDS
            ],
        }
    ]
    by_category: dict[str, list[dict[str, str]]] = {}
    for table in sorted(tables_columns):
        parsed = parse_factor_table_name(table)
        if parsed is None:
            # alpha191 面板表无价格后缀，单独成组（与 admin.py 的纳管口径一致）
            if table == "stock_daily_alpha191":
                for column in tables_columns[table]:
                    if column in _SKIP_COLUMNS:
                        continue
                    by_category.setdefault("alpha191", []).append(
                        {
                            "table": f"factors.{table}",
                            "column": column,
                            "label": f"Alpha191 · {column}",
                        }
                    )
            continue
        category, price_col = parsed
        price_label = PRICE_COLUMN_LABELS.get(price_col, price_col)
        for column in tables_columns[table]:
            if column in _SKIP_COLUMNS:
                continue
            by_category.setdefault(category, []).append(
                {
                    "table": f"factors.{table}",
                    "column": column,
                    "label": f"{CATEGORY_LABELS.get(category, category)}({price_label}) · {column}",
                }
            )
    for category in sorted(by_category):
        groups.append(
            {
                "group": category,
                "label": CATEGORY_LABELS.get(category, category),
                "items": sorted(by_category[category], key=lambda item: item["column"]),
            }
        )
    return groups


def load_factor_tables_columns(db_url: str | None = None) -> dict[str, list[str]]:
    """实时枚举 factors schema 的表与列（只读 information_schema）。DB 不可用抛异常。"""
    from sqlalchemy import text

    from quant_research_engine.data.settings import DatabaseSettings
    from quant_research_engine.data.postgres import PostgresDataStore

    settings = DatabaseSettings(market_db_url=db_url) if db_url else DatabaseSettings.from_env()
    store = PostgresDataStore(settings)
    store.ping()
    try:
        with store.market_engine.begin() as conn:
            tables = [
                str(row[0])
                for row in conn.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'factors' ORDER BY 1")
                ).fetchall()
            ]
            result: dict[str, list[str]] = {}
            for table in tables:
                result[table] = [
                    str(row[0])
                    for row in conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = 'factors' AND table_name = :table ORDER BY ordinal_position"
                        ),
                        {"table": table},
                    ).fetchall()
                ]
            return result
    finally:
        store.close()


# ---------------------------------------------------------------------------
# 条件构建器（比较 + 布尔）
# ---------------------------------------------------------------------------


def build_condition(left: str, operator: str, right: str | float | int) -> str:
    """单条条件 → "(left op right)"。right 为数值时按字面量输出。"""
    left = (left or "").strip()
    if not left:
        raise ValueError("左操作数不能为空")
    if operator not in COMPARISON_OPERATORS:
        raise ValueError(f"不支持的运算符: {operator}")
    if isinstance(right, str):
        right = right.strip()
        if not right:
            raise ValueError("右操作数不能为空")
        try:
            right = float(right)
        except ValueError:
            pass  # 因子/字段别名
    return f"({left} {operator} {right})"


def combine_conditions(conditions: list[str], combinator: str = "and") -> str | None:
    """多条条件用 AND/OR 连接；空列表返回 None。"""
    conditions = [c for c in conditions if c]
    if not conditions:
        return None
    combinator = (combinator or "and").lower()
    if combinator not in ("and", "or"):
        raise ValueError(f"不支持的组合逻辑: {combinator}")
    glue = " and " if combinator == "and" else " or "
    return glue.join(conditions)


def build_strategy_yaml(
    *,
    name: str,
    factor_fields: dict[str, str],
    entry_expression: str,
    exit_expression: str | None = None,
    holding_days: int = 20,
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
) -> str:
    """生成完整低层策略 YAML 文本（过 validate_yaml 校验后返回）。"""
    name = (name or "").strip() or "wizard_strategy"
    if not entry_expression:
        raise ValueError("至少需要一条入场条件")
    signal: dict[str, Any] = {"entry": entry_expression}
    if exit_expression:
        signal["exit"] = exit_expression
    risk = {
        key: value
        for key, value in (
            ("stop_loss_pct", stop_loss_pct),
            ("take_profit_pct", take_profit_pct),
            ("trailing_stop_pct", trailing_stop_pct),
        )
        if value is not None
    }
    spec = {
        "experiment": {
            "name": name,
            "market_profile": "ashare_daily_default",
            "frequency": "daily",
        },
        "data": {
            "market_fields": list(MARKET_FIELDS),
            "factor_fields": dict(factor_fields),
        },
        "universe": {
            "exclude_st": True,
            "exclude_suspended": True,
            "exclude_risk_warning": True,
            "min_listing_days": 120,
        },
        "signal": signal,
        "holding": {"max_holding_days": int(holding_days)},
        "evaluation": {"forward_return_horizons": [1, 3, 5, 10, 20], "quantiles": 5},
    }
    if risk:
        spec["risk"] = risk
    yaml_text = yaml.safe_dump(spec, default_flow_style=False, allow_unicode=True, sort_keys=False)
    validation = validate_yaml(yaml_text)
    if not validation["valid"]:
        raise ValueError(f"生成的 YAML 未通过规格校验: {validation['error']}")
    return yaml_text
