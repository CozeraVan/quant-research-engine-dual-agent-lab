"""标的范围（universe）归类查询层（QRE-SAAS-012，8081 新增策略页用）。

数据源（全部只读，本地 tushare_data 大库）：
- cluster.company_tags：layer A = 申万行业（tag 前缀 申万L1:/L2:/L3:）、
  layer B = 概念（source=em_concept 东财 / ths_concept 同花顺）、
  layer C source=local_features = 本地聚类状态池；
- reference.stock_basic.industry：通用行业（申万未覆盖北交所的兜底口径）。

API 形态：GET /api/lab/universes 返回 [{group, label, items: [{key, count}]}]；
GET /api/lab/universes/members?group=&key= 返回 {codes: [...]}。
引擎不改：前端在选择后把 group+key 解析成 codes 数组传既有 /api/run。

结果经 admin._cached TTL 缓存；DB 不可用时抛异常由路由层转 503 降级。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

# group key → 定义。company_tags 三组用 (layer, tag 前缀/source) 定位。
_GROUPS: list[dict[str, Any]] = [
    {"group": "sw1", "label": "申万一级行业", "layer": "A", "tag_prefix": "申万L1:"},
    {"group": "sw2", "label": "申万二级行业", "layer": "A", "tag_prefix": "申万L2:"},
    {"group": "sw3", "label": "申万三级行业", "layer": "A", "tag_prefix": "申万L3:"},
    {"group": "em", "label": "东财概念", "layer": "B", "source": "em_concept"},
    {"group": "ths", "label": "同花顺概念", "layer": "B", "source": "ths_concept"},
    {"group": "cluster", "label": "聚类状态池", "layer": "C", "source": "local_features"},
    {"group": "industry", "label": "通用行业（含北交所）", "source": "stock_basic"},
]

GROUP_KEYS = {g["group"] for g in _GROUPS}

#: 前端护栏阈值：成员超过该数量的范围提交前需确认（全市场量级耗时提示）
LARGE_UNIVERSE_THRESHOLD = 3000


def all_a_count(db_url: str | None = None) -> int:
    """全部 A 股标的数（reference.stock_basic 行数；stock_basic 已无 list_status 列，
    与 universe「通用行业」组同口径，含北交所）。供元数据导出与耗时护栏估算。"""
    engine = _engine(db_url)
    with engine.connect() as conn:
        return int(
            conn.execute(text("SELECT count(*) FROM reference.stock_basic")).scalar_one()
        )


def all_a_codes(db_url: str | None = None) -> list[str]:
    """全部 A 股 ts_code 列表（约 5.5k 条，~60KB）。供 SaaS 元数据导出与随机抽股。"""
    engine = _engine(db_url)
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT ts_code FROM reference.stock_basic ORDER BY ts_code")).fetchall()
    return [str(r[0]) for r in rows]


def random_symbol(db_url: str | None = None) -> str | None:
    """随机抽 1 只 A 股 ts_code（本地 DB 口径；SaaS 端优先走元数据 all_a_codes）。"""
    import random

    engine = _engine(db_url)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT ts_code FROM reference.stock_basic ORDER BY random() LIMIT 1")
        ).fetchone()
    return str(row[0]) if row else None


def _engine(db_url: str | None = None):
    from quant_research_engine.gui.admin import _store

    if db_url:
        return _store(db_url).market_engine
    try:
        return _store().market_engine
    except Exception:
        from quant_research_engine.risk.barometer_job import DEFAULT_DB_URL

        return _store(DEFAULT_DB_URL).market_engine


def list_universes(db_url: str | None = None) -> dict[str, Any]:
    """全部分组及每项成员数（按成员数降序）。"""
    engine = _engine(db_url)
    groups: list[dict[str, Any]] = []
    with engine.connect() as conn:
        for g in _GROUPS:
            if g.get("source") == "stock_basic":
                rows = conn.execute(
                    text(
                        "SELECT industry, count(*) FROM reference.stock_basic "
                        "WHERE industry IS NOT NULL AND industry <> '' "
                        "GROUP BY industry ORDER BY count(*) DESC"
                    )
                ).fetchall()
                items = [{"key": str(r[0]), "count": int(r[1])} for r in rows]
            else:
                cond = "layer = :layer"
                params: dict[str, Any] = {"layer": g["layer"]}
                if g.get("tag_prefix"):
                    cond += " AND tag LIKE :prefix"
                    params["prefix"] = g["tag_prefix"] + "%"
                else:
                    cond += " AND source = :source"
                    params["source"] = g["source"]
                rows = conn.execute(
                    text(
                        f"SELECT tag, count(DISTINCT ts_code) FROM cluster.company_tags "
                        f"WHERE {cond} GROUP BY tag ORDER BY count(DISTINCT ts_code) DESC"
                    ),
                    params,
                ).fetchall()
                items = [
                    {"key": str(r[0]).removeprefix(g.get("tag_prefix") or ""), "count": int(r[1])}
                    for r in rows
                ]
            groups.append({"group": g["group"], "label": g["label"], "items": items})
    return {"ok": True, "groups": groups}


def universe_members(group: str, key: str, db_url: str | None = None) -> list[str]:
    """group+key → 成员 ts_code 列表（未知组抛 KeyError）。"""
    spec = next((g for g in _GROUPS if g["group"] == group), None)
    if spec is None:
        raise KeyError(f"未知归类体系: {group}")
    engine = _engine(db_url)
    with engine.connect() as conn:
        if spec.get("source") == "stock_basic":
            rows = conn.execute(
                text("SELECT ts_code FROM reference.stock_basic WHERE industry = :key ORDER BY ts_code"),
                {"key": key},
            ).fetchall()
        else:
            tag = (spec.get("tag_prefix") or "") + key
            cond = "layer = :layer AND tag = :tag"
            params: dict[str, Any] = {"layer": spec["layer"], "tag": tag}
            if not spec.get("tag_prefix"):
                cond += " AND source = :source"
                params["source"] = spec["source"]
            rows = conn.execute(
                text(f"SELECT DISTINCT ts_code FROM cluster.company_tags WHERE {cond} ORDER BY ts_code"),
                params,
            ).fetchall()
    return [str(r[0]) for r in rows]
