"""risk.barometer_job 单测：分块边界、簇 <5 跳过、幂等 upsert、端到端小面板
（monkeypatch 取数 + fake engine，沿用 test_postgres_store 隔离模式，不触真库）。"""

from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd
import pytest

from quant_research_engine.risk import barometer_job as job


class TestChunkRanges:
    def test_year_chunks(self):
        dates = pd.bdate_range("2019-11-01", "2021-02-28").date.tolist()
        chunks = job.chunk_ranges(dates, chunk="year")
        assert chunks[0][0].year == 2019 and chunks[-1][1].year == 2021
        assert [c[0].year for c in chunks] == [2019, 2020, 2021]
        # 块间无重叠、首尾相接覆盖
        for (a0, a1), (b0, b1) in zip(chunks, chunks[1:]):
            assert a1 < b0
        assert chunks[0][0] == dates[0] and chunks[-1][1] == dates[-1]

    def test_month_chunks(self):
        dates = pd.bdate_range("2024-01-15", "2024-03-15").date.tolist()
        chunks = job.chunk_ranges(dates, chunk="month")
        assert len(chunks) == 3

    def test_all_single_chunk(self):
        dates = pd.bdate_range("2024-01-01", periods=10).date.tolist()
        assert job.chunk_ranges(dates, chunk="all") == [(dates[0], dates[-1])]

    def test_empty_and_bad_chunk(self):
        assert job.chunk_ranges([], chunk="year") == []
        with pytest.raises(ValueError):
            job.chunk_ranges([dt.date(2024, 1, 2)], chunk="week")


class FakeConnection:
    """记录执行语句与参数的最小 fake（engine.begin() 上下文）。"""

    def __init__(self):
        self.statements: list[tuple[str, object]] = []

    def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params))
        return None


class FakeEngine:
    def __init__(self):
        self.conn = FakeConnection()

    def begin(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, *args):
        return False


class TestStorage:
    def test_ensure_storage_ddl(self):
        eng = FakeEngine()
        job.ensure_storage(eng)
        stmts = [s for s, _ in eng.conn.statements]
        assert any("CREATE SCHEMA IF NOT EXISTS market_risk" in s for s in stmts)
        assert any("CREATE TABLE IF NOT EXISTS market_risk.daily" in s for s in stmts)
        assert any("PRIMARY KEY (trade_date, scope)" in s for s in stmts)

    def test_upsert_idempotent_on_conflict(self):
        eng = FakeEngine()
        row = {
            "trade_date": dt.date(2026, 8, 20),
            "scope": "market",
            "n_stocks": 5500,
            "indicators": {"median_sigma": 0.02, "var_breach_ratio": np.nan},
            "scores": {"total_score": np.float64(55.0)},
            "alert": {"alert": "green"},
        }
        assert job.upsert_daily(eng, [row]) == 1
        stmt, params = eng.conn.statements[0]
        assert "ON CONFLICT (trade_date, scope) DO UPDATE" in stmt
        payload = params[0]
        ind = json.loads(payload["indicators"])
        assert ind["median_sigma"] == 0.02
        assert ind["var_breach_ratio"] is None  # NaN → None（JSON 合法）
        assert json.loads(payload["scores"])["total_score"] == 55.0
        # 幂等：重放同一行不产生第二条语句结构差异（同一 UPSERT_SQL）
        job.upsert_daily(eng, [row])
        assert eng.conn.statements[1][0] == stmt

    def test_upsert_empty(self):
        assert job.upsert_daily(FakeEngine(), []) == 0


def _synthetic_panels(n_days: int = 300, n_stocks: int = 10, seed: int = 3):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-01-01", periods=n_days)
    cols = [f"s{i:03d}" for i in range(n_stocks)]
    ret = pd.DataFrame(rng.normal(0, 0.02, (n_days, n_stocks)), index=dates, columns=cols)
    w = pd.DataFrame(rng.uniform(1, 100, (n_days, n_stocks)), index=dates, columns=cols)
    return ret, w


class TestComputeChunk:
    def test_scopes_and_group_filters(self):
        ret, w = _synthetic_panels()
        cols = list(ret.columns)
        industry = {"big": cols[:8], "tiny": cols[:3]}  # tiny <5 跳过
        cday = ret.index[-1]
        cluster = {cday: {"tagx": cols[:6], "tagy": cols[6:9]}}  # tagy <5 跳过
        write_dates = list(ret.index[-3:])
        rows = job.compute_chunk(ret, w, industry, cluster, write_dates)
        scopes = {r["scope"] for r in rows}
        assert scopes == {"market", "industry:big", "cluster:tagx"}
        # 每个 scope 每天一行
        from collections import Counter

        counts = Counter(r["scope"] for r in rows)
        assert counts == {"market": 3, "industry:big": 3, "cluster:tagx": 1}
        # 簇行：scores=None + 披露 note
        crow = next(r for r in rows if r["scope"] == "cluster:tagx")
        assert crow["scores"] is None
        assert crow["n_stocks"] == 6
        # 市场行：分数 warmup=False（300 日 > 252），总分 0-100
        mrow = next(r for r in rows if r["scope"] == "market")
        assert mrow["scores"]["warmup"] is False
        assert 0.0 <= mrow["scores"]["total_score"] <= 100.0
        assert mrow["alert"]["alert"] in {"green", "amber", "red"}
        # 行可 JSON 序列化（NaN → None）
        json.dumps(job._jsonable(rows))


class TestRunRangeEndToEnd:
    def test_monkeypatched_pipeline(self, monkeypatch, tmp_path):
        """取数全 monkeypatch + fake engine：幂等、分块边界、JSON 产物。"""
        ret, w = _synthetic_panels(n_days=320, n_stocks=8)
        trade_dates = [d.date() for d in ret.index]
        cols = list(ret.columns)
        industry = {"big": cols[:6]}
        cluster_map = {ret.index[-1]: {"tagx": cols[:5]}}
        eng = FakeEngine()

        monkeypatch.setattr(job, "fetch_trade_dates", lambda e, d0, d1: [d for d in trade_dates if d0 <= d <= d1])
        monkeypatch.setattr(job, "fetch_returns_panel", lambda e, d0, d1: ret)
        monkeypatch.setattr(job, "fetch_market_cap_panel", lambda e, d0, d1: w)
        monkeypatch.setattr(job, "fetch_industry_groups", lambda e: industry)
        monkeypatch.setattr(
            job,
            "fetch_cluster_groups",
            lambda e, d: cluster_map.get(pd.Timestamp(d), {}),
        )
        monkeypatch.setattr(job, "buffer_start", lambda e, d0, buffer_days=312: trade_dates[0])
        monkeypatch.setattr(job, "output_dir", lambda: str(tmp_path))

        d0, d1 = trade_dates[-40], trade_dates[-1]
        summary = job.run_range(eng, d0, d1, chunk="month")
        assert summary["rows_written"] > 0
        # upsert 语句均为 ON CONFLICT 幂等
        upserts = [s for s, _ in eng.conn.statements if "INSERT INTO market_risk.daily" in s]
        assert upserts and all("ON CONFLICT" in s for s in upserts)
        # JSON 产物按日写盘
        products = sorted(tmp_path.glob("*.json"))
        assert len(products) == 40  # 写入区间 40 个交易日
        payload = json.loads(products[-1].read_text())
        assert payload["trade_date"] == trade_dates[-1].isoformat()
        scopes = {r["scope"] for r in payload["rows"]}
        assert "market" in scopes and "industry:big" in scopes
        assert "cluster:tagx" in scopes  # 末日有簇分组

    def test_no_trade_dates_raises(self, monkeypatch):
        eng = FakeEngine()
        monkeypatch.setattr(job, "ensure_storage", lambda e: None)
        monkeypatch.setattr(job, "fetch_trade_dates", lambda e, d0, d1: [])
        with pytest.raises(ValueError, match="no trade dates"):
            job.run_range(eng, dt.date(2026, 8, 20), dt.date(2026, 8, 20))
