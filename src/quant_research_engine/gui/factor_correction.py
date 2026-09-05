"""因子名自动纠错层（QRE-NL-FACTOR-AUTOCORRECT-001）。

痛点：NL 编译链路里 DeepSeek 会编造数据库中不存在的因子列名
（如 ``rsi14``、``MACD``），生成的 YAML 在因子存在性检查处失败，
用户只看到红色报错不知道该怎么改。

本模块是纯函数层（零 DB、零 IO），供 ``gui/nl_compiler.compile_nl``
与 ``gui/strategy_lab_routes`` 的手工 YAML 通道复用：

- ``auto_fix_column``：保守自动纠正——只在归一化后等价（大小写/下划线
  差异，如 ``rsi14``→``rsi_14``）、唯一编辑距离 1 且与次优差距 ≥2、
  或唯一前缀匹配时才替换；其余一律不动，宁给候选列表不可错配。
- ``suggest_similar_columns``：归一化编辑距离排序的 Top-N 候选。
- ``correct_factor_fields``：对解析后的策略 mapping 做存在性校验 +
  自动纠正，返回纠正记录与未解决项（含候选）。
- ``COMMON_FACTOR_TARGETS``：常用已落库因子列清单，用于报错提示与
  NL 编译 prompt 注入（从源头减少编造）。
"""

from __future__ import annotations

from typing import Any, Callable

# 常用已落库因子列（与 strategies/compiler._INDICATOR_CATALOG 命名约定一致：
# factors.stock_daily_<类别>_<价格源>.<指标>_<周期>）。用于报错提示与 prompt 注入；
# 真实存在性仍以 column_lookup 对照库内 schema 为准。
COMMON_FACTOR_TARGETS: tuple[str, ...] = (
    "factors.stock_daily_momentum_close.rsi_14",
    "factors.stock_daily_momentum_close.rsi_6",
    "factors.stock_daily_overlap_close.sma_5",
    "factors.stock_daily_overlap_close.sma_10",
    "factors.stock_daily_overlap_close.sma_20",
    "factors.stock_daily_overlap_close.sma_60",
    "factors.stock_daily_overlap_close.ema_12",
    "factors.stock_daily_overlap_close.ema_26",
    "factors.stock_daily_momentum_close.macd_12_26_9",
    "factors.stock_daily_momentum_close.macd_signal_12_26_9",
    "factors.stock_daily_momentum_close.macd_histogram_12_26_9",
    "factors.stock_daily_volatility_close.bbu_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbm_20_2_0_2_0",
    "factors.stock_daily_volatility_close.bbl_20_2_0_2_0",
    "factors.stock_daily_volatility_close.atr_14",
    "factors.stock_daily_trend_close.adx_14",
    "factors.stock_daily_momentum_close.cci_14",
    "factors.stock_daily_volume_close.mfi_14",
)

TOP_N_SUGGESTIONS = 5

# 跨表兜底搜索用的标准因子表（类别 × 价格源），来自编译器命名约定。
_STANDARD_TABLE_SUFFIXES: tuple[str, ...] = (
    "momentum_close",
    "overlap_close",
    "volatility_close",
    "trend_close",
    "volume_close",
    "statistics_close",
    "candle_close",
    "performance_close",
)


def _normalize(name: str) -> str:
    """比较用归一化：小写 + 去下划线（rsi14 / RSI_14 / rsi_14 等价）。"""
    return name.lower().replace("_", "")


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (0 if ca == cb else 1),
                )
            )
        previous = current
    return previous[-1]


def suggest_similar_columns(
    column: str,
    candidates: list[str] | set[str],
    *,
    top_n: int = TOP_N_SUGGESTIONS,
) -> list[str]:
    """按归一化编辑距离排序的 Top-N 相似候选（确定性排序，距离相同按列名）。"""
    pool = sorted(candidates)
    norm = _normalize(column)
    ranked = sorted(pool, key=lambda c: (_levenshtein(norm, _normalize(c)), c))
    return ranked[:top_n]


def auto_fix_column(column: str, candidates: list[str] | set[str]) -> str | None:
    """保守自动纠正：仅以下三种无歧义情形返回替换列名，否则 None。

    1. 归一化后完全等价（大小写/下划线差异），如 ``rsi14``→``rsi_14``；
    2. 唯一候选的归一化编辑距离为 1，且次优距离 ≥3（明显更接近）；
    3. 唯一前缀匹配（归一化后候选以输入为前缀），如 ``macd``→``macd_12_26_9``
       （仅当库中 macd 系列只有一列时；有 signal/histogram 并列则不给自动纠正）。
    """
    pool = sorted(candidates)
    if not pool or column in pool:
        return None
    norm = _normalize(column)

    normalized_equal = [c for c in pool if _normalize(c) == norm]
    if normalized_equal:
        # 多个归一化等价（极端情况）时优先大小写也一致的
        for c in normalized_equal:
            if c.lower() == column.lower():
                return c
        return normalized_equal[0]

    distances = sorted((_levenshtein(norm, _normalize(c)), c) for c in pool)
    if distances and distances[0][0] == 1:
        if len(distances) == 1 or distances[1][0] >= 3:
            return distances[0][1]

    prefix_matches = [c for c in pool if _normalize(c).startswith(norm)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return None


def _candidate_pool(
    qualified_table: str,
    column_lookup: Callable[[str], set[str]],
) -> tuple[set[str], dict[str, set[str]]]:
    """同表候选优先；同表为空时跨标准因子表兜底（返回 同表列, 全表列 映射）。"""
    same_table = column_lookup(qualified_table)
    if same_table:
        return set(same_table), {qualified_table: set(same_table)}
    all_tables: dict[str, set[str]] = {}
    for suffix in _STANDARD_TABLE_SUFFIXES:
        table = f"factors.stock_daily_{suffix}"
        if table == qualified_table:
            continue
        columns = column_lookup(table)
        if columns:
            all_tables[table] = set(columns)
    return set(), all_tables


def correct_factor_fields(
    mapping: dict[str, Any],
    column_lookup: Callable[[str], set[str]],
) -> dict[str, Any]:
    """对策略 mapping 的 data.factor_fields 做存在性校验 + 自动纠正（就地改写 target）。

    Returns:
      {
        "corrections": [{"alias", "table", "from", "to"}, ...],   # 已自动替换
        "unresolved":  [{"alias", "table", "column",
                          "suggestions": [候选...],                 # Top-N
                          "suggestion_scope": "same_table"|"cross_table"|"none"}, ...],
      }
    """
    corrections: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []

    data = mapping.get("data") or {}
    factor_fields = data.get("factor_fields") or {}
    if not isinstance(factor_fields, dict):
        return {"corrections": corrections, "unresolved": unresolved}

    for alias, target in list(factor_fields.items()):
        parts = str(target).split(".")
        if len(parts) < 2:
            continue
        column = parts[-1]
        table = ".".join(parts[:-1])
        existing = column_lookup(table)
        if column in existing:
            continue  # 精确存在，不动

        same_table, pool_by_table = _candidate_pool(table, column_lookup)
        if same_table:
            fix = auto_fix_column(column, same_table)
            if fix is not None:
                factor_fields[alias] = f"{table}.{fix}"
                corrections.append({"alias": str(alias), "table": table, "from": column, "to": fix})
                continue
            unresolved.append({
                "alias": str(alias),
                "table": table,
                "column": column,
                "suggestions": suggest_similar_columns(column, same_table),
                "suggestion_scope": "same_table",
            })
        elif pool_by_table:
            all_columns: dict[str, str] = {}  # column -> table（同名冲突时先到先得，仅作提示）
            for tbl, cols in sorted(pool_by_table.items()):
                for col in cols:
                    all_columns.setdefault(col, tbl)
            fix = None
            if column in all_columns:
                fix = column  # 列名对、表写错：直接换表
            else:
                fix = auto_fix_column(column, set(all_columns))
            if fix is not None:
                new_table = all_columns[fix]
                factor_fields[alias] = f"{new_table}.{fix}"
                corrections.append({"alias": str(alias), "table": new_table, "from": column, "to": fix})
                continue
            qualified = [f"{all_columns[c]}.{c}" for c in suggest_similar_columns(column, set(all_columns))]
            unresolved.append({
                "alias": str(alias),
                "table": table,
                "column": column,
                "suggestions": qualified,
                "suggestion_scope": "cross_table",
            })
        else:
            unresolved.append({
                "alias": str(alias),
                "table": table,
                "column": column,
                "suggestions": [],
                "suggestion_scope": "none",
            })

    return {"corrections": corrections, "unresolved": unresolved}


def format_corrections_note(corrections: list[dict[str, str]]) -> str:
    """「已自动纠正 X→Y」的中文提示行。"""
    items = "、".join(f"{c['from']}→{c['to']}" for c in corrections)
    return f"已自动纠正因子名（原名为 LLM 编造/笔误，库中不存在）：{items}"


def format_unresolved_hint(unresolved: list[dict[str, Any]]) -> str:
    """未解决缺因子的 actionable 中文提示（候选 Top-N + 常用因子清单）。"""
    lines = ["以下因子名在因子库中不存在，请改用候选名后重新提交："]
    for item in unresolved:
        label = f"{item['alias']}（{item['table']}.{item['column']}）"
        if item["suggestions"]:
            lines.append(f"- {label}；库中相似候选：{'、'.join(item['suggestions'])}")
        else:
            lines.append(f"- {label}；库中暂无相似列")
    common = "、".join(t.rsplit(".", 1)[-1] for t in COMMON_FACTOR_TARGETS[:8])
    lines.append(f"常用已落库因子参考：{common} 等（完整目录见「新增策略」页因子目录）")
    return "\n".join(lines)
