"""管理台「聚类动量因子研究」（QRE-GUI-POOL-MOM-031）：纯逻辑（排名/加速度/共振）、
数据层 fake store、路由、admin tab 存在性。"""

from __future__ import annotations

import datetime as dt

import pytest

from quant_research_engine.gui import admin, pool_momentum
from quant_research_engine.gui.pool_momentum import (
    compute_acceleration,
    pool_momentum_detail,
    pool_momentum_overview,
    rank_desc,
    resonance_flag,
    sort_by_acceleration,
)


def _clear_cache() -> None:
    admin._cache.clear()


@pytest.fixture(autouse=True)
def clear_cache():
    _clear_cache()
    yield
    _clear_cache()


# ---------------------------------------------------------------------------
# 纯逻辑
# ---------------------------------------------------------------------------


class TestRankDesc:
    def test_basic_desc(self):
        assert rank_desc([0.1, 0.3, 0.2]) == [3, 1, 2]

    def test_none_excluded(self):
        assert rank_desc([0.1, None, 0.3]) == [2, None, 1]

    def test_ties_share_rank(self):
        assert rank_desc([0.2, 0.3, 0.2, 0.1]) == [2, 1, 2, 4]

    def test_all_none(self):
        assert rank_desc([None, None]) == [None, None]


class TestAcceleration:
    def test_accel_positive_when_short_rank_better(self):
        rows = [
            {"fwd_ret_50": 0.30, "fwd_ret_3": 0.01},   # 速度 rank1，短窗 rank2 → accel -1
            {"fwd_ret_50": 0.10, "fwd_ret_3": 0.05},   # 速度 rank2，短窗 rank1 → accel +1
        ]
        out = compute_acceleration(rows)
        assert out[0]["speed_rank"] == 1 and out[0]["short_rank"] == 2
        assert out[0]["acceleration"] == -1
        assert out[1]["speed_rank"] == 2 and out[1]["short_rank"] == 1
        assert out[1]["acceleration"] == 1

    def test_missing_rank_gives_none(self):
        rows = [
            {"fwd_ret_50": None, "fwd_ret_3": 0.05},
            {"fwd_ret_50": 0.10, "fwd_ret_3": 0.01},
        ]
        out = compute_acceleration(rows)
        assert out[0]["acceleration"] is None
        assert out[0]["weak_long_strong_short"] is False
        assert out[1]["acceleration"] == -1  # speed 1 - short 2

    def test_weak_long_strong_short_flag(self):
        # 10 个池：速度排名后半区（>5）且短窗排名前 10%（<=1）
        rows = [
            {"fwd_ret_50": 0.50, "fwd_ret_3": 0.001},   # speed 1
            {"fwd_ret_50": 0.40, "fwd_ret_3": 0.001},   # speed 2
            {"fwd_ret_50": 0.30, "fwd_ret_3": 0.001},   # speed 3
            {"fwd_ret_50": 0.20, "fwd_ret_3": 0.001},   # speed 4
            {"fwd_ret_50": 0.10, "fwd_ret_3": 0.001},   # speed 5
            {"fwd_ret_50": 0.05, "fwd_ret_3": 0.001},   # speed 6 短窗 4 → 不高亮
            {"fwd_ret_50": -0.01, "fwd_ret_3": 0.001},
            {"fwd_ret_50": -0.02, "fwd_ret_3": 0.001},
            {"fwd_ret_50": -0.03, "fwd_ret_3": 0.001},
            {"fwd_ret_50": -0.10, "fwd_ret_3": 0.20},   # speed 10 短窗 1 → 长弱短升
        ]
        out = compute_acceleration(rows)
        assert out[9]["weak_long_strong_short"] is True
        assert out[9]["acceleration"] == 9
        assert out[5]["weak_long_strong_short"] is False  # 短窗不在前 10%
        assert out[0]["weak_long_strong_short"] is False  # 长窗不弱


class TestResonance:
    def _row(self, ret, vwap, vol):
        return {"fwd_ret_3": ret, "vwap_ret_3": vwap, "vol_chg_3": vol}

    def test_all_positive(self):
        assert resonance_flag(self._row(0.01, 0.02, 0.5), 3) is True

    def test_any_nonpositive_blocks(self):
        assert resonance_flag(self._row(0.01, -0.02, 0.5), 3) is False
        assert resonance_flag(self._row(0.01, 0.02, 0.0), 3) is False  # 严格 >0
        assert resonance_flag(self._row(-0.01, 0.02, 0.5), 3) is False

    def test_missing_value_blocks(self):
        assert resonance_flag(self._row(None, 0.02, 0.5), 3) is False

    def test_window_50_never_resonates(self):
        # vol_chg_50 构造上恒为 0 → 严格 >0 永不成立
        row = {"fwd_ret_50": 0.3, "vwap_ret_50": 0.3, "vol_chg_50": 0.0}
        assert resonance_flag(row, 50) is False


class TestSortByAcceleration:
    def test_desc_none_last(self):
        rows = [{"acceleration": 1}, {"acceleration": None}, {"acceleration": 5}]
        out = sort_by_acceleration(rows)
        assert [r["acceleration"] for r in out] == [5, 1, None]


# ---------------------------------------------------------------------------
# 数据层（fake store）
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, scalar=None, rows=None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


_KEEP = object()


def _pool_row(pool_type, key, ret50, ret3, n=10, vwap3=None, vol3=None, fwd50=_KEEP, fwd3=_KEEP, event=None):
    """按 _SELECT_COLS 列序构造一行：
    (pool_type, pool_key, n_stocks, ret×4, fwd×4, vwap×4, vol×4, event×4)。
    fwd 缺省跟随 ret（等同旧口径测试），显式传 None 表示末日未补齐；
    event=(next_premium, survive_3, survive_5, win_rate_1)。
    """
    fwd3 = ret3 if fwd3 is _KEEP else fwd3
    fwd50 = ret50 if fwd50 is _KEEP else fwd50
    ev = event or (None, None, None, None)
    return (
        pool_type, key, n,
        ret3, ret3 * 1.5, ret3 * 2.0, ret50,
        fwd3, (fwd3 * 1.5 if fwd3 is not None else None), (fwd3 * 2.0 if fwd3 is not None else None), fwd50,
        vwap3, vwap3, vwap3, vwap3,
        vol3, vol3, vol3, 0.0,
        ev[0], ev[1], ev[2], ev[3],
    )


class _FakeConn:
    def __init__(self, latest=None, overview_rows=None, detail_rows=None, fwd_latest="same",
                 date_list=None, post_dates=None, post_rows=None):
        self._latest = latest
        # fwd_latest="same" 表示与 latest 同日（fwd 已补齐）；可传具体 date 或 None
        self._fwd_latest = latest if fwd_latest == "same" else fwd_latest
        self._overview_rows = overview_rows or []
        self._detail_rows = detail_rows or []
        self._date_list = date_list or []
        self._post_dates = post_dates or []
        self._post_rows = post_rows or []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        sql = str(clause)
        if "DISTINCT trade_date" in sql:
            if "trade_date > :d" in sql:
                return _FakeResult(rows=[(d,) for d in self._post_dates])
            return _FakeResult(rows=[(d,) for d in self._date_list])
        if "fwd_ret_3 IS NOT NULL" in sql:
            return _FakeResult(scalar=self._fwd_latest)
        if "max(trade_date)" in sql:
            return _FakeResult(scalar=self._latest)
        if "trade_date > :d" in sql:
            return _FakeResult(rows=self._post_rows)
        if "pool_type = :pt" in sql:
            return _FakeResult(rows=self._detail_rows)
        return _FakeResult(rows=self._overview_rows)


class _FakeStore:
    def __init__(self, conn):
        self.market_engine = type("E", (), {"begin": lambda _self: conn})()

    def close(self):
        pass


def _patch_store(monkeypatch, conn):
    monkeypatch.setattr(pool_momentum, "_store", lambda db_url=None: _FakeStore(conn))


class TestOverview:
    def test_happy_path_groups_and_ranks(self, monkeypatch):
        d = dt.date(2026, 9, 1)
        rows = [
            _pool_row("concept", "华为概念", 0.10, 0.05, vwap3=0.02, vol3=0.5),
            _pool_row("concept", "CPO概念", 0.20, 0.01, vwap3=-0.02, vol3=0.5),
            _pool_row("state", "强势", 0.30, 0.03, vwap3=0.01, vol3=0.2),
            _pool_row("state", "弱势", -0.10, -0.02, vwap3=-0.01, vol3=-0.1),
        ]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        out = pool_momentum_overview()
        assert out["ok"] is True and out["empty"] is False
        assert out["latest_date"] == "2026-09-01"
        assert [r["pool_key"] for r in out["concept"]] == ["华为概念", "CPO概念"]
        # concept 组内：华为 ret50 rank2 / ret3 rank1 → accel +1 排前
        assert out["concept"][0]["acceleration"] == 1
        assert out["concept"][0]["resonance"]["3"] is True
        assert out["concept"][1]["resonance"]["3"] is False  # vwap 负
        # state 组内独立排名
        assert out["state"][0]["pool_key"] == "强势"
        assert out["state"][0]["speed_rank"] == 1
        assert out["state"][1]["speed_rank"] == 2

    def test_empty_table(self, monkeypatch):
        _patch_store(monkeypatch, _FakeConn(latest=None))
        out = pool_momentum_overview()
        assert out["ok"] is True and out["empty"] is True
        assert "暂无数据" in out["note"]

    def test_db_error_degrades(self, monkeypatch):
        def _boom(db_url=None):
            raise RuntimeError("no db")

        monkeypatch.setattr(pool_momentum, "_store", _boom)
        out = pool_momentum_overview()
        assert out["ok"] is False and "数据库不可用" in out["error"]

    def test_query_error_degrades(self, monkeypatch):
        class _BadConn(_FakeConn):
            def execute(self, clause, params=None):
                raise RuntimeError("relation cluster.pool_momentum_daily does not exist")

        _patch_store(monkeypatch, _BadConn())
        out = pool_momentum_overview()
        assert out["ok"] is False and "查询失败" in out["error"]


class TestDetail:
    def _detail_rows(self):
        # 与真实 SQL 一致：ORDER BY trade_date DESC；13 列含 fwd_ret/fwd_ret_3/20/50
        return [
            (dt.date(2026, 9, 1), 52, 0.02, 0.06, 0.12, 0.02, 0.11, 0.4, 0.0,
             None, None, None, None),
            (dt.date(2026, 8, 31), 50, 0.01, 0.05, 0.10, 0.01, 0.09, 0.3, 0.0,
             0.005, 0.015, 0.04, 0.08),
        ]

    def test_happy_path_ascending(self, monkeypatch):
        _patch_store(monkeypatch, _FakeConn(detail_rows=self._detail_rows()))
        out = pool_momentum_detail("concept", "华为概念")
        assert out["ok"] is True and out["empty"] is False
        assert out["series"]["dates"] == ["2026-08-31", "2026-09-01"]
        assert out["series"]["ret_50"] == [0.10, 0.12]
        assert out["series"]["vol_chg_3"] == [0.3, 0.4]

    def test_empty_pool(self, monkeypatch):
        _patch_store(monkeypatch, _FakeConn())
        out = pool_momentum_detail("concept", "不存在的池")
        assert out["ok"] is True and out["empty"] is True

    def test_invalid_pool_type(self):
        out = pool_momentum_detail("bogus", "x")
        assert out["ok"] is False and "非法 pool_type" in out["error"]

    def test_missing_pool_key(self):
        out = pool_momentum_detail("concept", "")
        assert out["ok"] is False


class TestRoutes:
    def test_overview_route_200(self, monkeypatch):
        d = dt.date(2026, 9, 1)
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05)]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get("/api/admin/pool-momentum")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert data["concept"][0]["pool_key"] == "华为概念"

    def test_detail_route_200(self, monkeypatch):
        _patch_store(monkeypatch, _FakeConn(detail_rows=[
            (dt.date(2026, 9, 1), 50, 0.02, 0.06, 0.12, 0.02, 0.11, 0.4, 0.0,
             None, None, None, None),
        ]))
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get(
            "/api/admin/pool-momentum/detail?pool_type=concept&pool_key=华为概念"
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_detail_route_invalid_type(self):
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get(
            "/api/admin/pool-momentum/detail?pool_type=bogus&pool_key=x"
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is False


class TestAdminPage:
    def test_admin_tab_present(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        assert 'data-tab="mom"' in html
        assert "聚类动量" in html
        assert "/api/admin/pool-momentum" in html
        # 偏差声明
        assert "前视偏差" in html
        assert "point-in-time" in html
        # 速度/加速度口径说明
        assert "加速度" in html and "速度" in html


# ---------------------------------------------------------------------------
# v2：通用排序 / 热力色阶 / 成员指标
# ---------------------------------------------------------------------------

from quant_research_engine.gui.pool_momentum import (  # noqa: E402
    compute_heat,
    compute_member_metrics,
    pool_momentum_members,
    sort_rows,
)


class TestSortRows:
    def test_desc_none_last(self):
        rows = [{"v": 1.0}, {"v": None}, {"v": 3.0}]
        assert [r["v"] for r in sort_rows(rows, "v", desc=True)] == [3.0, 1.0, None]

    def test_asc_none_last(self):
        rows = [{"v": 1.0}, {"v": None}, {"v": 3.0}]
        assert [r["v"] for r in sort_rows(rows, "v", desc=False)] == [1.0, 3.0, None]

    def test_string_key(self):
        rows = [{"v": "b"}, {"v": None}, {"v": "a"}]
        assert [r["v"] for r in sort_rows(rows, "v", desc=False)] == ["a", "b", None]


class TestComputeHeat:
    def test_quantile_mapping(self):
        rows = [{"fwd_ret_3": 0.30}, {"fwd_ret_3": 0.10}, {"fwd_ret_3": -0.20}]
        out = compute_heat(rows, windows=(3,))
        heats = [r["heat"]["3"] for r in out]
        assert heats[0] == 1.0    # 最高 → +1（最红）
        assert heats[2] == -1.0   # 最低 → −1（最绿）
        assert heats[1] == 0.0    # 中位 → 0（近无色）

    def test_none_and_single(self):
        rows = [{"fwd_ret_3": None}, {"fwd_ret_3": 0.1}]
        out = compute_heat(rows, windows=(3,))
        assert out[0]["heat"]["3"] is None
        assert out[1]["heat"]["3"] is None  # 仅一个有效值无法分位

    def test_ties_share_heat(self):
        rows = [{"fwd_ret_3": 0.2}, {"fwd_ret_3": 0.2}, {"fwd_ret_3": 0.1}]
        out = compute_heat(rows, windows=(3,))
        assert out[0]["heat"]["3"] == out[1]["heat"]["3"] == 1.0

    def test_heat_independent_of_ret50(self):
        rows = [{"fwd_ret_3": 0.3, "fwd_ret_50": -0.1}, {"fwd_ret_3": 0.1, "fwd_ret_50": 0.2}]
        out = compute_heat(rows)
        assert out[0]["heat"]["3"] == 1.0 and out[0]["heat"]["50"] == -1.0


def _cal(n=51):
    return [f"D{i:03d}" for i in range(n)]  # 升序，末日 = D050


def _price_rows(code, cal, skip=()):
    rows = []
    for i, d in enumerate(cal):
        if d in skip:
            continue
        close = 100.0 * (1.01 ** i)
        rows.append((code, d, close, 1.0, close * 0.99, 100.0))
    return rows


class TestComputeMemberMetrics:
    def test_hand_computed(self):
        cal = _cal()
        out = compute_member_metrics(_price_rows("A", cal), cal)
        m = out["A"]
        assert m["close"] == 100.0 * 1.01 ** 50
        assert m["ret_3"] == pytest.approx(1.01 ** 3 - 1, rel=1e-9)
        assert m["ret_50"] == pytest.approx(1.01 ** 50 - 1, rel=1e-9)
        assert m["vwap_ret_3"] == pytest.approx(1.01 ** 3 - 1, rel=1e-9)
        assert m["vol_chg_3"] == pytest.approx(0.0, abs=1e-12)  # 量恒定

    def test_missing_today_gives_none(self):
        cal = _cal()
        out = compute_member_metrics(_price_rows("A", cal, skip={"D050"}), cal)
        m = out["A"]
        assert m["close"] is None
        assert m["ret_3"] is None  # 当日缺行 → 与管线宽表 shift 一致 None
        assert m["vol_chg_3"] is None

    def test_missing_prev_day_partial_none(self):
        cal = _cal()
        out = compute_member_metrics(_price_rows("A", cal, skip={"D047"}), cal)
        m = out["A"]
        assert m["ret_3"] is None    # t−3 = D047 缺行
        assert m["ret_5"] is not None
        assert m["vol_chg_3"] is None  # 近 3 日含 D047 缺行 → None（min_periods 口径）

    def test_short_calendar_vol_none(self):
        cal = _cal(10)  # 不足 51 日 → vol_chg 无法算
        out = compute_member_metrics(_price_rows("A", cal), cal)
        assert out["A"]["vol_chg_3"] is None
        assert out["A"]["ret_3"] is not None


class _FakeMembersConn:
    def __init__(self, latest, codes, calendar, price_rows, names):
        self._latest, self._codes = latest, codes
        self._calendar, self._price_rows, self._names = calendar, price_rows, names

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        sql = str(clause)
        if "max(trade_date)" in sql:
            return _FakeResult(scalar=self._latest)
        if "cluster.company_tags" in sql or "cluster.daily_tags" in sql:
            return _FakeResult(rows=[(c,) for c in self._codes])
        if "DISTINCT trade_date" in sql:
            return _FakeResult(rows=[(d,) for d in reversed(self._calendar)])
        if "close, adj_factor, vwap, vol" in sql:
            return _FakeResult(rows=self._price_rows)
        if "reference.stock_basic" in sql:
            return _FakeResult(rows=list(self._names.items()))
        return _FakeResult()


class TestMembers:
    def _conn(self, names=None):
        cal = _cal()
        prices = _price_rows("000001.SZ", cal) + _price_rows("000002.SZ", cal)
        return _FakeMembersConn(
            latest=dt.date(2026, 9, 1),
            codes=["000001.SZ", "000002.SZ"],
            calendar=cal,
            price_rows=prices,
            names=names if names is not None else {"000001.SZ": "平安银行"},
        )

    def test_happy_path(self, monkeypatch):
        _patch_store(monkeypatch, self._conn())
        out = pool_momentum_members("concept", "华为概念")
        assert out["ok"] is True and out["empty"] is False
        assert out["trade_date"] == "2026-09-01"
        assert len(out["members"]) == 2
        m0 = out["members"][0]
        assert m0["name"] == "平安银行" or out["members"][1]["name"] == "平安银行"
        m = next(x for x in out["members"] if x["ts_code"] == "000001.SZ")
        assert m["ret_3"] == pytest.approx(1.01 ** 3 - 1, rel=1e-9)
        assert m["ret_50"] is not None and m["vwap_ret_50"] is not None
        assert m["vol_chg_50"] == pytest.approx(0.0, abs=1e-12)

    def test_names_degrade(self, monkeypatch):
        class _NoNames(_FakeMembersConn):
            def execute(self, clause, params=None):
                if "reference.stock_basic" in str(clause):
                    raise RuntimeError("relation does not exist")
                return super().execute(clause, params)

        conn = self._conn()
        _patch_store(monkeypatch, _NoNames(conn._latest, conn._codes, conn._calendar, conn._price_rows, {}))
        out = pool_momentum_members("concept", "华为概念")
        assert out["ok"] is True
        assert all(m["name"] is None for m in out["members"])
        assert out["members"][0]["ret_3"] is not None

    def test_state_members_use_daily_tags(self, monkeypatch):
        _patch_store(monkeypatch, self._conn())
        out = pool_momentum_members("state", "量比:突增", trade_date="2026-09-01")
        assert out["ok"] is True and len(out["members"]) == 2

    def test_empty_members(self, monkeypatch):
        conn = self._conn()
        conn._codes = []
        _patch_store(monkeypatch, conn)
        out = pool_momentum_members("concept", "不存在的概念")
        assert out["ok"] is True and out["empty"] is True

    def test_no_price_rows(self, monkeypatch):
        conn = self._conn()
        conn._price_rows = []
        _patch_store(monkeypatch, conn)
        out = pool_momentum_members("concept", "华为概念")
        assert out["ok"] is True
        assert all(m["close"] is None and m["ret_3"] is None for m in out["members"])

    def test_invalid_pool_type(self):
        assert pool_momentum_members("bogus", "x")["ok"] is False

    def test_missing_pool_key(self):
        assert pool_momentum_members("concept", "")["ok"] is False

    def test_members_route_200(self, monkeypatch):
        _patch_store(monkeypatch, self._conn())
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get(
            "/api/admin/pool-momentum/members?pool_type=concept&pool_key=华为概念"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True and len(data["members"]) == 2

    def test_members_route_invalid(self):
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get(
            "/api/admin/pool-momentum/members?pool_type=bogus&pool_key=x"
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is False


class TestAdminPageV2:
    def test_heatmap_and_sort_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        assert "momHeatColor" in html          # 热力色映射
        assert "mom-sort" in html              # 可排序表头
        assert "mom-members" in html           # 成员明细容器
        assert "/api/admin/pool-momentum/members" in html
        assert "红涨绿跌" in html               # 热力口径声明


# ---------------------------------------------------------------------------
# v2（M7 前瞻口径切换）：fwd 排名/热力/共振、事件池、末日滞后
# ---------------------------------------------------------------------------


class TestV2ForwardBasis:
    def test_accel_uses_fwd_not_ret(self):
        # 回看与前瞻故意反向：回看 ret 口径下 A 速度更高，前瞻口径下 B 更高
        rows = [
            {"ret_50": 0.50, "ret_3": 0.01, "fwd_ret_50": 0.05, "fwd_ret_3": 0.01},
            {"ret_50": 0.10, "ret_3": 0.02, "fwd_ret_50": 0.30, "fwd_ret_3": 0.02},
        ]
        out = compute_acceleration(rows)
        assert out[1]["speed_rank"] == 1  # fwd_ret_50 0.30 最高
        assert out[0]["speed_rank"] == 2
        # 回看口径显式可选（metric="ret"）
        out_ret = compute_acceleration([dict(r) for r in rows], metric="ret")
        assert out_ret[0]["speed_rank"] == 1

    def test_heat_uses_fwd(self):
        rows = [
            {"ret_3": 0.50, "fwd_ret_3": -0.10},
            {"ret_3": 0.10, "fwd_ret_3": 0.20},
        ]
        out = compute_heat(rows, windows=(3,))
        assert out[1]["heat"]["3"] == 1.0   # fwd 最高
        assert out[0]["heat"]["3"] == -1.0
        out_ret = compute_heat([dict(r) for r in rows], windows=(3,), metric="ret")
        assert out_ret[0]["heat"]["3"] == 1.0

    def test_resonance_uses_fwd(self):
        row = {"fwd_ret_3": 0.01, "ret_3": -0.05, "vwap_ret_3": 0.02, "vol_chg_3": 0.5}
        assert resonance_flag(row, 3) is True   # 看 fwd 而非回看 ret
        row2 = {"fwd_ret_3": -0.01, "ret_3": 0.05, "vwap_ret_3": 0.02, "vol_chg_3": 0.5}
        assert resonance_flag(row2, 3) is False


class TestV2EventPools:
    def test_has_event_flag(self, monkeypatch):
        d = dt.date(2026, 8, 31)
        rows = [
            _pool_row("state", "连涨:3日", 0.30, 0.03, vwap3=0.01, vol3=0.2,
                      event=(0.005, 0.09, 0.05, 0.59)),
            _pool_row("state", "adx:强趋势", 0.10, 0.01, vwap3=0.01, vol3=0.2),
            _pool_row("concept", "华为概念", 0.10, 0.05, vwap3=0.02, vol3=0.5),
        ]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        out = pool_momentum_overview()
        by_key = {r["pool_key"]: r for r in out["state"]}
        assert by_key["连涨:3日"]["has_event"] is True
        assert by_key["连涨:3日"]["next_premium"] == 0.005
        assert by_key["连涨:3日"]["win_rate_1"] == 0.59
        assert by_key["adx:强趋势"]["has_event"] is False
        assert out["concept"][0]["has_event"] is False  # concept 恒无事件列


class TestV2FwdLag:
    def test_lag_shows_last_filled_date(self, monkeypatch):
        d_latest = dt.date(2026, 9, 1)
        d_fwd = dt.date(2026, 8, 31)
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05)]
        _patch_store(
            monkeypatch,
            _FakeConn(latest=d_latest, overview_rows=rows, fwd_latest=d_fwd),
        )
        out = pool_momentum_overview()
        assert out["latest_date"] == "2026-08-31"
        assert out["latest_date_overall"] == "2026-09-01"
        assert out["fwd_lag"] is True
        assert "T+1 收盘后补齐" in out["fwd_note"]

    def test_no_lag(self, monkeypatch):
        d = dt.date(2026, 8, 31)
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05)]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        out = pool_momentum_overview()
        assert out["fwd_lag"] is False
        assert out["latest_date"] == "2026-08-31"

    def test_no_fwd_at_all_falls_back_to_latest(self, monkeypatch):
        d = dt.date(2026, 9, 1)
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05, fwd3=None, fwd50=None)]
        _patch_store(
            monkeypatch,
            _FakeConn(latest=d, overview_rows=rows, fwd_latest=None),
        )
        out = pool_momentum_overview()
        assert out["latest_date"] == "2026-09-01"
        assert out["fwd_lag"] is False
        # fwd 全 None → 加速度/热力全 None 但不炸
        assert out["concept"][0]["acceleration"] is None
        assert out["concept"][0]["heat"]["3"] is None


class TestV2DetailSeries:
    def test_fwd_series_present_and_lag_null(self, monkeypatch):
        from quant_research_engine.gui.pool_momentum import pool_momentum_detail as _detail

        class _Conn(_FakeConn):
            pass

        conn = _Conn(detail_rows=[
            (dt.date(2026, 9, 1), 52, 0.02, 0.06, 0.12, 0.02, 0.11, 0.4, 0.0,
             None, None, None, None),
            (dt.date(2026, 8, 31), 50, 0.01, 0.05, 0.10, 0.01, 0.09, 0.3, 0.0,
             0.005, 0.015, 0.04, 0.08),
        ])
        _patch_store(monkeypatch, conn)
        out = _detail("concept", "华为概念")
        s = out["series"]
        assert s["fwd_ret"] == [0.005, None]   # 末日 NULL（一日滞后）
        assert s["fwd_ret_50"] == [0.08, None]
        assert s["ret_50"] == [0.10, 0.12]     # 回看辅线保留


class TestAdminPageV3:
    def test_v2_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        assert "fwd_ret_w" in html
        assert "回看" in html
        assert "selection_artifact" in html
        assert "对标同花顺涨停复盘" in html
        assert "T+1 收盘后才可算" in html
        assert "次日溢价" in html and "存活" in html and "胜率" in html
        assert "成员回看指标" in html


# ---------------------------------------------------------------------------
# v3（历史回看）：post 窗口、验证摘要、日期参数
# ---------------------------------------------------------------------------

from quant_research_engine.gui.pool_momentum import (  # noqa: E402
    accel_top_summary,
    compute_post_returns,
)


def _v3_row(pool_type, key, fwd50, fwd3):
    """v3 测试用行：只需排名/事后相关字段。"""
    return {
        "_pool_type": pool_type, "pool_key": key,
        "fwd_ret_50": fwd50, "fwd_ret_3": fwd3,
    }


class TestComputePostReturns:
    def test_compound(self):
        rows = [_v3_row("concept", "A", 0.1, 0.01)]
        series = {("concept", "A"): [0.01, 0.02, -0.01, 0.03, 0.0, 0.01]}
        out = compute_post_returns(rows, series, windows=(3, 5, 20))
        assert out[0]["post_3"] == pytest.approx(1.01 * 1.02 * 0.99 - 1, rel=1e-12)
        assert out[0]["post_5"] == pytest.approx(1.01 * 1.02 * 0.99 * 1.03 * 1.0 - 1, rel=1e-12)
        assert out[0]["post_20"] is None  # 不足 20 日 → 未满窗口

    def test_none_inside_window_blocks(self):
        rows = [_v3_row("concept", "A", 0.1, 0.01)]
        series = {("concept", "A"): [0.01, None, -0.01]}
        out = compute_post_returns(rows, series, windows=(3,))
        assert out[0]["post_3"] is None

    def test_missing_pool_series(self):
        rows = [_v3_row("concept", "A", 0.1, 0.01)]
        out = compute_post_returns(rows, {}, windows=(3,))
        assert out[0]["post_3"] is None


class TestAccelTopSummary:
    def _rows(self):
        # 加速度由 fwd_ret_50/fwd_ret_3 推导：i 越大 accel 越大
        rows = []
        for i in range(12):
            rows.append({
                "_pool_type": "concept", "pool_key": f"P{i}",
                "fwd_ret_50": -0.01 * i, "fwd_ret_3": 0.001 * i,
                "post_5": 0.01 if i >= 10 else (-0.02 if i < 5 else 0.0),
            })
        return compute_acceleration(rows)

    def test_summary_vs_all(self):
        out = accel_top_summary(self._rows(), post_key="post_5", top_n=10)
        # accel_i = 2i−11，top10 = i=2..11：post_5 = -0.02×3 + 0.0×5 + 0.01×2
        assert out["n_top"] == 10
        assert out["top_mean"] == pytest.approx(-0.004, rel=1e-9)
        assert out["top_median"] == pytest.approx(0.0, abs=1e-12)
        assert out["top_win_rate"] == pytest.approx(0.2, rel=1e-9)
        # 全体 12：-0.02×5 + 0×5 + 0.01×2 = -0.08 → mean -0.006667
        assert out["all_mean"] == pytest.approx(-0.08 / 12, rel=1e-9)
        assert out["n_all"] == 12

    def test_missing_post_excluded(self):
        rows = self._rows()
        for r in rows:
            r["post_5"] = None
        out = accel_top_summary(rows)
        assert out["top_mean"] is None and out["all_mean"] is None

    def test_accel_none_rows_excluded_from_top(self):
        rows = self._rows()
        rows.append({"_pool_type": "concept", "pool_key": "PX",
                     "fwd_ret_50": None, "fwd_ret_3": None, "post_5": 0.99})
        out = accel_top_summary(rows, top_n=10)
        assert out["n_top"] == 10
        assert out["top_mean"] == pytest.approx(-0.004, rel=1e-9)  # PX 未混入 top
        assert out["n_all"] == 13  # 但计入全体对照


class TestV3Overview:
    def test_trade_date_param_and_post_columns(self, monkeypatch):
        d = dt.date(2026, 8, 10)
        rows = [
            _pool_row("concept", "华为概念", 0.10, 0.05, vwap3=0.02, vol3=0.5),
            _pool_row("concept", "CPO概念", 0.20, 0.01, vwap3=-0.02, vol3=0.5),
        ]
        post_dates = [dt.date(2026, 8, 11) + dt.timedelta(days=i) for i in range(5)]
        post_rows = [
            ("concept", "华为概念", dd, 0.01) for dd in post_dates
        ] + [
            ("concept", "CPO概念", dd, -0.01) for dd in post_dates
        ]
        conn = _FakeConn(
            latest=dt.date(2026, 9, 1), overview_rows=rows,
            fwd_latest=dt.date(2026, 8, 31),
            date_list=[dt.date(2026, 8, 31), dt.date(2026, 8, 10)],
            post_dates=post_dates, post_rows=post_rows,
        )
        _patch_store(monkeypatch, conn)
        out = pool_momentum_overview(trade_date="2026-08-10")
        assert out["ok"] is True
        assert out["latest_date"] == "2026-08-10"
        assert out["dates"] == ["2026-08-31", "2026-08-10"]
        by_key = {r["pool_key"]: r for r in out["concept"]}
        assert by_key["华为概念"]["post_5"] == pytest.approx(1.01 ** 5 - 1, rel=1e-9)
        assert by_key["华为概念"]["post_3"] == pytest.approx(1.01 ** 3 - 1, rel=1e-9)
        assert by_key["华为概念"]["post_20"] is None  # 未满窗口
        assert by_key["CPO概念"]["post_5"] == pytest.approx(0.99 ** 5 - 1, rel=1e-9)
        s = out["summary"]["concept"]
        assert s["n_all"] == 2 and s["n_top"] == 2
        # 池数 < top_n 时 top==全体；胜率 0.5（一正一负）
        assert s["top_mean"] == pytest.approx(s["all_mean"], rel=1e-12)
        assert s["top_win_rate"] == pytest.approx(0.5, rel=1e-9)

    def test_no_post_dates_gives_null_columns(self, monkeypatch):
        d = dt.date(2026, 9, 1)
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05)]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        out = pool_momentum_overview()
        assert out["concept"][0]["post_3"] is None
        assert out["summary"]["concept"]["top_mean"] is None

    def test_detail_end_date_param(self, monkeypatch):
        captured = {}

        class _Conn(_FakeConn):
            def execute(self, clause, params=None):
                captured["sql"] = str(clause)
                captured["params"] = params
                return _FakeResult(rows=self._detail_rows)

        conn = _Conn(detail_rows=[
            (dt.date(2026, 8, 10), 50, 0.01, 0.05, 0.10, 0.01, 0.09, 0.3, 0.0,
             0.005, 0.015, 0.04, 0.08),
        ])
        _patch_store(monkeypatch, conn)
        out = pool_momentum_detail("concept", "华为概念", end_date="2026-08-10")
        assert out["ok"] is True
        assert "trade_date <= :end" in captured["sql"]
        assert captured["params"]["end"] == "2026-08-10"

    def test_overview_route_trade_date(self, monkeypatch):
        rows = [_pool_row("concept", "华为概念", 0.10, 0.05)]
        _patch_store(
            monkeypatch,
            _FakeConn(latest=dt.date(2026, 9, 1), overview_rows=rows,
                      fwd_latest=dt.date(2026, 8, 31)),
        )
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get("/api/admin/pool-momentum?trade_date=2026-08-10")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True and data["latest_date"] == "2026-08-10"


class TestAdminPageV4:
    def test_v3_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        assert 'id="mom-date"' in html        # 日期选择器
        assert 'id="mom-summary"' in html     # 验证摘要条
        assert "事后3日" in html or "post_3" in html
        assert "验证摘要" in html
        assert "未满窗口" in html


# ---------------------------------------------------------------------------
# v4（底部回避名单）：Bottom10 判定、回避汇总、API/页面标记
# ---------------------------------------------------------------------------

from quant_research_engine.gui.pool_momentum import (  # noqa: E402
    avoid_list,
    compute_bottom_avoid,
)


def _v4_rows(n, base=-0.01):
    return [
        {"pool_key": f"P{i}", "fwd_ret_3": base * i, "n_stocks": 20}
        for i in range(n)
    ]


class TestComputeBottomAvoid:
    def test_bottom_n_flagged(self):
        rows = _v4_rows(15)
        out = compute_bottom_avoid(rows)
        flagged = [r["pool_key"] for r in out if r["avoid"]]
        assert flagged == [f"P{i}" for i in range(5, 15)]  # fwd_ret_3 = -0.01*i，最低 10 个
        assert len(flagged) == 10

    def test_none_excluded(self):
        rows = _v4_rows(12)
        rows[11]["fwd_ret_3"] = None  # 最低值置 None → 不参与回避
        out = compute_bottom_avoid(rows)
        assert out[11]["avoid"] is False
        assert sum(1 for r in out if r["avoid"]) == 10
        assert out[10]["avoid"] is True

    def test_min_stocks_excluded(self):
        rows = _v4_rows(12)
        rows[11]["n_stocks"] = 5  # 成员过少 → 不参与判定
        out = compute_bottom_avoid(rows)
        assert out[11]["avoid"] is False
        assert sum(1 for r in out if r["avoid"]) == 10

    def test_fewer_eligible_than_n(self):
        rows = _v4_rows(3)
        out = compute_bottom_avoid(rows)
        assert all(r["avoid"] for r in out)  # 有效池不足 bottom_n 时全部回避

    def test_empty_and_all_none(self):
        assert compute_bottom_avoid([]) == []
        rows = [{"pool_key": "A", "fwd_ret_3": None, "n_stocks": 50}]
        out = compute_bottom_avoid(rows)
        assert out[0]["avoid"] is False

    def test_window_param(self):
        rows = [
            {"pool_key": "A", "fwd_ret_3": 0.1, "fwd_ret_5": -0.5, "n_stocks": 20},
            {"pool_key": "B", "fwd_ret_3": -0.1, "fwd_ret_5": 0.5, "n_stocks": 20},
        ]
        out = compute_bottom_avoid(rows, window=5, bottom_n=1)
        assert out[0]["avoid"] is True   # fwd_ret_5 最低
        assert out[1]["avoid"] is False


class TestAvoidList:
    def test_sorted_ascending(self):
        rows = compute_bottom_avoid(_v4_rows(12))
        out = avoid_list(rows)
        assert len(out) == 10
        vals = [x["fwd_ret_3"] for x in out]
        assert vals == sorted(vals)
        assert out[0]["pool_key"] == "P11"  # 最弱
        assert out[0]["n_stocks"] == 20


class TestV4Overview:
    def test_avoid_flags_and_payload(self, monkeypatch):
        d = dt.date(2026, 8, 31)
        # concept 12 池 fwd_ret_3 递增；state 2 池（fwd 最低者回避，但组内独立）
        rows = [
            _pool_row("concept", f"C{i}", 0.10, 0.001 * i, n=20)
            for i in range(12)
        ] + [
            _pool_row("state", "弱势", -0.10, -0.02, n=30),
            _pool_row("state", "强势", 0.30, 0.03, n=30),
        ]
        _patch_store(monkeypatch, _FakeConn(latest=d, overview_rows=rows))
        out = pool_momentum_overview()
        by_key = {r["pool_key"]: r for r in out["concept"]}
        assert sum(1 for r in out["concept"] if r["avoid"]) == 10
        assert by_key["C0"]["avoid"] is True    # fwd_ret_3 最低
        assert by_key["C11"]["avoid"] is False  # 最高
        # state 组内独立：有效池 2 < 10 → 全部回避
        assert all(r["avoid"] for r in out["state"])
        av = out["avoid"]
        assert [x["pool_key"] for x in av["concept"]][:2] == ["C0", "C1"]
        assert av["concept"][0]["fwd_ret_3"] == pytest.approx(0.0, abs=1e-12)
        assert out["avoid_bottom_n"] == 10 and out["avoid_min_stocks"] == 10

    def test_avoid_point_in_time(self, monkeypatch):
        # 历史回看模式：回避按选中日截面计算（trade_date 传参链路复用）
        rows = [_pool_row("concept", f"C{i}", 0.10, 0.001 * i, n=20) for i in range(12)]
        _patch_store(
            monkeypatch,
            _FakeConn(latest=dt.date(2026, 9, 1), overview_rows=rows,
                      fwd_latest=dt.date(2026, 8, 31)),
        )
        out = pool_momentum_overview(trade_date="2026-08-10")
        assert out["latest_date"] == "2026-08-10"
        assert sum(1 for r in out["concept"] if r["avoid"]) == 10

    def test_avoid_route_field(self, monkeypatch):
        rows = [_pool_row("concept", f"C{i}", 0.10, 0.001 * i, n=20) for i in range(12)]
        _patch_store(monkeypatch, _FakeConn(latest=dt.date(2026, 8, 31), overview_rows=rows))
        from quant_research_engine.gui.app import create_app

        resp = create_app().test_client().get("/api/admin/pool-momentum")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "avoid" in data
        assert data["concept"][0]["avoid"] in (True, False)
        assert len(data["avoid"]["concept"]) == 10


class TestAdminPageV5:
    def test_v4_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        assert 'id="mom-avoid"' in html       # 回避汇总卡容器
        assert "mom-avoid" in html            # 徽章样式类
        assert "⚠ 回避" in html
        assert "短窗最弱十分位" in html        # tooltip/卡片依据
        assert "无选股价值" in html            # 声明卡补句
        assert "NW t=−3.86" in html


# ---------------------------------------------------------------------------
# v5（榜单可读性）：横向滚动 + 首列 sticky + 精简列开关 + 详情面板上移
# ---------------------------------------------------------------------------


class TestAdminPageV6:
    def test_v5_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        # 详情面板：榜单上方（汇总卡之下）、带关闭按钮
        assert 'id="mom-detail-panel"' in html
        assert 'id="mom-detail-close"' in html
        assert 'id="mom-detail-title"' in html
        assert 'id="mom-detail"' in html and 'id="mom-members"' in html
        assert html.index('id="mom-summary"') < html.index('id="mom-detail-panel"') \
            < html.index('id="mom-concept"')
        # 底部旧详情区已移除
        assert 'data-section="mom-detail"' not in html
        # 精简列开关 + 列标记 + 横向滚动/限高容器
        assert 'id="btn-mom-cols"' in html
        assert "展开更多列" in html
        assert "mom-col-x" in html
        assert "mom-scroll" in html and "mom-members-scroll" in html

    def test_v7_render_perf_markup(self):
        from quant_research_engine.gui.app import create_app

        html = create_app().test_client().get("/admin").get_data(as_text=True)
        # v7 渲染性能：默认 Top/Bottom 50 截断 + 「显示全部」/「收起」切换
        assert "MOM_EDGE_N = 50" in html
        assert "momShowAll" in html
        assert "mom-expand" in html and "显示全部" in html
        assert "mom-collapse" in html and "mom-gap" in html
        # 精简模式不输出隐藏单元格（display:none 规则已删，JS 侧按 momFull 决定是否生成）
        assert "mom-compact" not in html
        # 首列 sticky 仅展开更多列时启用
        assert "mom-sticky" in html
        # 分区局部重渲
        assert "renderMomentumTable" in html

    def test_v5_css(self):
        from pathlib import Path

        css = Path(
            __import__("quant_research_engine.gui", fromlist=["x"]).__path__[0]
        ).joinpath("static", "style.css").read_text(encoding="utf-8")
        assert ".mom-scroll" in css and "overflow-x: auto" in css
        assert "position: sticky; left: 0" in css          # 首列池名 sticky（仅 .mom-sticky 展开模式）
        assert ".mom-scroll.mom-sticky" in css
        assert ".mom-compact" not in css                   # v7：精简列不再先渲染后隐藏
        assert "content-visibility: auto" in css           # 行级渲染跳过
        assert ".mom-gap" in css
        assert ".mom-members-scroll" in css and "max-height: 420px" in css
