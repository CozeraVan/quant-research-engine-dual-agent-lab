"""NL 编译专用真实因子目录快照（CR-2026-10-09 四层方案 第 1 层）。

LLM 没有真实因子目录时凭记忆编造列名（如 macd_signal_12_26_9，库内实为
macds_12_26_9）。本模块把 factors schema 全量列压缩成编译 prompt 用清单，
落盘 configs/factor_catalog_llm.txt（入仓库，ECS 无库也能用；因子库更新后跑
scripts/gen_factor_catalog_llm.py 重新生成）。

压缩格式：按指标基名分组——``macd@{12_26_9|6_13_5}`` 表示存在
macd_12_26_9 与 macd_6_13_5 两列；无参数列直接列名。559 列压缩后 ~120 行。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "factor_catalog_llm.txt"
)

_SKIP = frozenset({"ts_code", "trade_date"})
_PARAM_SUFFIX = re.compile(r"^(?P<base>.+?)_(?P<params>[0-9][0-9_]*)$")


def compress_columns(columns: list[str]) -> list[str]:
    """列名清单 → 压缩分组行（确定性排序：基名 → 参数）。"""
    by_base: dict[str, set[str]] = {}
    plain: list[str] = []
    for col in sorted(columns):
        if col in _SKIP:
            continue
        m = _PARAM_SUFFIX.match(col)
        if m:
            by_base.setdefault(m.group("base"), set()).add(m.group("params"))
        else:
            plain.append(col)
    out = list(plain)
    for base in sorted(by_base):
        params = sorted(by_base[base])
        out.append(f"{base}@{{{'|'.join(params)}}}")
    return out


def render_catalog_text(tables_columns: dict[str, list[str]]) -> str:
    """factors 表列 → prompt 用紧凑目录文本（每表一行，含中文类目/价格源）。"""
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
        groups = compress_columns(tables_columns[table])
        lines.append(f"factors.{table}（{label}）：{'、'.join(groups)}")
    return "\n".join(lines) + "\n"


def generate_catalog(path: Path | None = None, db_url: str | None = None) -> Path:
    """从本地因子库生成快照文件（需 QRE_MARKET_DB_URL）。返回写入路径。"""
    from quant_research_engine.gui.factor_wizard import load_factor_tables_columns

    target = path or DEFAULT_CATALOG_PATH
    text = render_catalog_text(load_factor_tables_columns(db_url))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


_CATALOG_CACHE: dict[str, Any] = {}


def load_catalog_text(path: Path | None = None) -> str | None:
    """读快照（mtime 缓存）；文件不存在返回 None（调用方回退旧口径）。"""
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
