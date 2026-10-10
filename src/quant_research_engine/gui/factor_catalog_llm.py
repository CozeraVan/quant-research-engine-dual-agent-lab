"""NL 编译专用真实因子目录快照（CR-2026-10-09 四层方案 第 1 层）。

LLM 没有真实因子目录时凭记忆编造列名（如 macd_signal_12_26_9，库内实为
macds_12_26_9）。本模块把 factors schema 全量列渲染成编译 prompt 用清单
（**平铺全列名**——2026-10-10 生产实测发现 macd@{...} 压缩语法 LLM 会误读，
不如实展开），落盘 configs/factor_catalog_llm.txt（入仓库，ECS 无库也能用）+
configs/factor_catalog_llm.json（机器可读，DB 不可用时作 factor 存在性
lookup 兜底，让纠错/重试层在 ECS 同样生效）；因子库更新后跑
scripts/gen_factor_catalog_llm.py 重新生成。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "factor_catalog_llm.txt"
)
DEFAULT_CATALOG_JSON_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "factor_catalog_llm.json"
)

_SKIP = frozenset({"ts_code", "trade_date"})


def render_catalog_text(tables_columns: dict[str, list[str]]) -> str:
    """factors 表列 → prompt 用目录文本（每表一行：全列名平铺 + 中文类目/价格源）。

    平铺而非压缩：LLM 对 macd@{12_26_9|...} 压缩语法会误读（生产实测），
    全量 559 列直接列出 token 成本可接受且零歧义。
    """
    from quant_research_engine.gui.factor_wizard import (
        CATEGORY_LABELS,
        PRICE_COLUMN_LABELS,
        parse_factor_table_name,
    )

    lines = [
        "行情字段（无需 factor_fields 声明，表达式直接用）：open high low close pre_close vol amount",
    ]
    for table in sorted(tables_columns):
        parsed = parse_factor_table_name(table)
        if parsed is not None:
            category, price_col = parsed
            label = f"{CATEGORY_LABELS.get(category, category)}/{PRICE_COLUMN_LABELS.get(price_col, price_col)}"
        elif table == "stock_daily_alpha191":
            label = "Alpha191 因子面板"
        else:
            label = table
        cols = "、".join(c for c in sorted(tables_columns[table]) if c not in _SKIP)
        lines.append(f"factors.{table}（{label}）：{cols}")
    return "\n".join(lines) + "\n"


def generate_catalog(path: Path | None = None, db_url: str | None = None) -> Path:
    """从本地因子库生成快照（txt + json 双格式）。返回 txt 路径。"""
    from quant_research_engine.gui.factor_wizard import load_factor_tables_columns

    tables_columns = load_factor_tables_columns(db_url)
    target = path or DEFAULT_CATALOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_catalog_text(tables_columns), encoding="utf-8")
    json_path = target.with_suffix(".json")
    json_path.write_text(
        json.dumps(tables_columns, ensure_ascii=False, indent=1), encoding="utf-8")
    return target


_CATALOG_CACHE: dict[str, Any] = {}


def load_catalog_text(path: Path | None = None) -> str | None:
    """读文本快照（mtime 缓存）；文件不存在返回 None（调用方回退旧口径）。"""
    target = path or DEFAULT_CATALOG_PATH
    try:
        mtime = target.stat().st_mtime
    except OSError:
        return None
    cached = _CATALOG_CACHE.get(str(target))
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        text = target.read_text(encoding="utf-8")
    except OSError:
        return None
    _CATALOG_CACHE[str(target)] = (mtime, text)
    return text


def catalog_column_lookup(path: Path | None = None) -> Any:
    """快照 JSON → column_lookup(table)->set(columns)；文件缺失返回 None。

    ECS 无行情库时让纠错/重试层照常工作（CR-2026-10-10 生产实测发现
    lookup=None 导致二层失效）。
    """
    target = path or DEFAULT_CATALOG_JSON_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    tables = {f"factors.{t}": set(cols) for t, cols in data.items()}
    tables.setdefault("public.stock_daily", set())  # 行情列不进 factor_fields，空集即可
    return lambda table: tables.get(table, set())
