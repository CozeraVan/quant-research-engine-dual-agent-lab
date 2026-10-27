"""JSON 出口非有限浮点（NaN/±Inf）硬化契约。

线上故障（2026-10-28，job_58 个股详情）：因子库 warm-up 段在 PG 里存的是
``double precision NaN`` 而非 NULL，``_fetch_factor_panels`` 的
``r[1] is not None`` 过滤漏掉它，NaN 随因子序列进入产物；云端读取出口
``saas/app.py::_jsonable`` 又不做非有限过滤，Flask ``json.dumps`` 默认
``allow_nan=True`` 把裸 ``NaN`` token 写进响应体——这不是合法 JSON，
浏览器 ``resp.json()`` 抛 ``SyntaxError``，symbol.html 走 catch 显示
「加载失败，请稍后重试」。

worker 侧 ``_json_sanitize``（2026-10-12 修过同类问题）只覆盖「写产物」
一刻，历史产物与云端读取出口都在保护范围之外。本文件锁定所有出口都必须
产出严格 JSON：非有限浮点一律降级为 ``null``，由前端按既有缺口逻辑渲染。
"""

from __future__ import annotations

import json
import math

import pytest


def test_jsonable_drops_non_finite_floats():
    """SaaS 统一出口 _jsonable：NaN/±Inf → None，有限值与日期口径不变。"""
    from datetime import date, datetime

    from quant_research_engine.gui.saas.app import _jsonable

    payload = {
        "nan": float("nan"),
        "inf": float("inf"),
        "ninf": float("-inf"),
        "ok": 1.25,
        "zero": 0,
        "none": None,
        "list": [float("nan"), 2.0, [float("inf")]],
        "nested": {"deep": {"v": float("nan")}},
        "when": datetime(2026, 10, 28, 9, 30),
        "day": date(2026, 10, 28),
    }
    out = _jsonable(payload)
    assert out["nan"] is None and out["inf"] is None and out["ninf"] is None
    assert out["ok"] == 1.25 and out["zero"] == 0 and out["none"] is None
    assert out["list"] == [None, 2.0, [None]]
    assert out["nested"]["deep"]["v"] is None
    assert out["when"] == "2026-10-28T09:30:00" and out["day"] == "2026-10-28"


def test_fetch_factor_panels_skips_non_finite_db_values(monkeypatch, tmp_path):
    """因子查询遇 DB NaN 必须降级 None（与缺口同语义），不得把 NaN 传进产物。"""
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    run_dir = tmp_path / "runs" / "r1"
    run_dir.mkdir(parents=True)
    (run_dir / "strategy.yaml").write_text(
        "data:\n  factor_fields:\n"
        "    macd: factors.stock_daily_tech.macd_12_26_9\n"
        "signal:\n  entry: macd > 0\n  exit: macd < 0\n",
        encoding="utf-8",
    )

    import re as _re

    from quant_research_engine.gui.lab_result import _fetch_factor_panels

    class _FakeRes:
        def __init__(self, rows):
            self._rows = rows

        def fetchall(self):
            return self._rows

        def first(self):
            return self._rows[0] if self._rows else None

        def fetchone(self):
            return self._rows[0] if self._rows else None

    class _Conn:
        def execute(self, stmt, params=None):
            sql = str(stmt)
            if "information_schema.columns" in sql:
                return _FakeRes([])
            if "SELECT adj_factor FROM public.stock_daily" in sql:
                return _FakeRes([])
            col = _re.search(r'"(\w+)" FROM', sql).group(1)
            assert col == "macd_12_26_9"
            # 第 1 日 warm-up：库里是 NaN 而非 NULL（真实 301xxx.SZ 场景）
            return _FakeRes([("2024-01-02", float("nan")), ("2024-01-03", 1.5)])

    class _Begin:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *a):
            return False

    class _Engine:
        def begin(self):
            return _Begin()

    class _Store:
        market_engine = _Engine()

    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda *a, **k: _Store())

    panels, note = _fetch_factor_panels({"run_id": "r1"}, "000001.SZ", ["2024-01-02", "2024-01-03"])
    assert note is None
    assert len(panels) == 1
    values = panels[0]["values"]
    assert values[0] is None, "DB NaN 必须降级为 None，否则产物带非法 JSON token"
    assert values[1] == 1.5
    assert all(math.isfinite(v) for v in values if v is not None)
