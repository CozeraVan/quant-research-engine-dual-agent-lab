from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from quant_research_engine.gui import admin
from quant_research_engine.gui.admin import (
    MAX_QUERY_LIMIT,
    _clamp_limit,
    health_status,
    overview_backtests,
    parse_systemctl_show,
    query_daily,
    query_factor,
    rows_to_csv,
    timer_status,
)


# --- fake DB store ---


class _FakeResult:
    def __init__(self, *, scalar=None, rows=None, mappings=None):
        self._scalar = scalar
        self._rows = rows or []
        self._mappings = mappings

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._mappings if self._mappings is not None else self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def mappings(self):
        return self

    @property
    def scalar_one_or_none(self):
        return self._scalar


class _FakeConn:
    """按 SQL 文本特征返回固定结果；记录所有查询。"""

    def __init__(self, store):
        self.store = store

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, clause, params=None):
        sql = str(clause)
        params = params or {}
        self.store.queries.append((sql, params))
        if "pg_class" in sql:
            return _FakeResult(rows=[(123456,)])
        if "COUNT(DISTINCT ts_code)" in sql:
            return _FakeResult(scalar=5547)
        if "COUNT(*)" in sql:
            return _FakeResult(scalar=3)
        if "MAX(trade_date)" in sql and "factors" in sql:
            for table, wm in self.store.factor_maxes.items():
                if f'"{table}"' in sql:
                    return _FakeResult(scalar=wm)
            return _FakeResult(scalar=None)
        if "MAX(trade_date)" in sql:
            return _FakeResult(scalar="2026-07-27")
        if "DISTINCT trade_date" in sql:
            return _FakeResult(rows=[("2026-07-27",), ("2026-07-24",)])
        if "information_schema.tables" in sql:
            return _FakeResult(rows=[("stock_daily_momentum_close",), ("stock_daily_overlap_close",)])
        # data rows
        mappings = [
            {"trade_date": "2026-07-27", "ts_code": params.get("ts_code"), "close": "10.5"},
            {"trade_date": "2026-07-24", "ts_code": params.get("ts_code"), "close": "10.3"},
        ]
        return _FakeResult(mappings=mappings)


class _FakeEngine:
    def __init__(self, store):
        self.store = store

    def begin(self):
        return _FakeConn(self.store)


class FakeStore:
    def __init__(self, columns=("ts_code", "trade_date", "rsi_14"), factor_maxes=None):
        self.queries: list[tuple[str, dict]] = []
        self.market_engine = _FakeEngine(self)
        self._columns = list(columns)
        self.factor_maxes = factor_maxes or {
            "stock_daily_momentum_close": "2026-07-24",
            "stock_daily_overlap_close": "2026-07-24",
        }

    def ping(self):
        return True

    def close(self):
        pass

    def table_exists(self, table_name, *, engine=None):
        return table_name == "factors.stock_daily_momentum_close"

    def get_table_columns(self, table_name, *, engine=None):
        return list(self._columns)


# --- query_daily / query_factor ---


def test_query_daily_basic():
    store = FakeStore()
    result = query_daily(ts_code="000001.SZ", start="2026-07-01", end="2026-07-27", store=store)
    assert result["total"] == 3
    assert result["limit"] == 200
    assert len(result["rows"]) == 2
    # 参数化：ts_code 不拼接进 SQL
    sql_text = " ".join(q for q, _ in store.queries)
    assert "000001.SZ" not in sql_text
    assert any(p.get("ts_code") == "000001.SZ" for _, p in store.queries)


def test_query_daily_empty_code():
    with pytest.raises(ValueError, match="股票代码不能为空"):
        query_daily(ts_code=" ", start="a", end="b", store=FakeStore())


def test_clamp_limit():
    assert _clamp_limit(10) == 10
    assert _clamp_limit(99999) == MAX_QUERY_LIMIT
    assert _clamp_limit(0) == 1
    assert _clamp_limit("abc") == 200


def test_query_factor_ok():
    store = FakeStore()
    result = query_factor(
        table="factors.stock_daily_momentum_close",
        column="rsi_14",
        ts_code="000001.SZ",
        start="2026-07-01",
        end="2026-07-27",
        store=store,
    )
    assert result["total"] == 3
    assert len(result["rows"]) == 2


def test_query_factor_rejects_bad_table():
    with pytest.raises(ValueError, match="非法因子表名"):
        query_factor(table="public.stock_daily; DROP TABLE x", column="rsi_14",
                     ts_code="000001.SZ", start="a", end="b", store=FakeStore())
    with pytest.raises(ValueError, match="因子表不存在"):
        query_factor(table="factors.stock_daily_momentum_typical_price", column="rsi_14",
                     ts_code="000001.SZ", start="a", end="b", store=FakeStore())


def test_query_factor_rejects_bad_column():
    store = FakeStore(columns=["ts_code", "trade_date", "rsi_14"])
    with pytest.raises(ValueError, match="非法因子列名"):
        query_factor(table="factors.stock_daily_momentum_close", column="rsi_14; DROP",
                     ts_code="000001.SZ", start="a", end="b", store=store)
    with pytest.raises(ValueError, match="非法因子列名"):
        query_factor(table="factors.stock_daily_momentum_close", column="ts_code",
                     ts_code="000001.SZ", start="a", end="b", store=store)


def test_rows_to_csv():
    csv_text = rows_to_csv([
        {"trade_date": "2026-07-27", "close": "10.5"},
        {"trade_date": "2026-07-24", "close": "10.3"},
    ])
    lines = csv_text.strip().splitlines()
    assert lines[0] == "trade_date,close"
    assert lines[1] == "2026-07-27,10.5"
    assert rows_to_csv([]) == ""


# --- systemctl 解析 ---


def test_parse_systemctl_show():
    output = "ActiveState=active\nResult=success\nNextElapseUSecRealtime=Mon 2026-07-28 16:30:00 CST\n"
    props = parse_systemctl_show(output)
    assert props["ActiveState"] == "active"
    assert props["Result"] == "success"


class _Proc:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


def _runner_factory(mapping):
    def runner(cmd, **kwargs):
        unit = cmd[2]
        return mapping.get(unit, _Proc("LoadState=not-found\n", 1))
    return runner


def test_timer_status_installed_and_not_installed():
    mapping = {
        "quant-ts-daily.timer": _Proc(
            "LoadState=loaded\nActiveState=active\nUnitFileState=enabled\nNextElapseUSecRealtime=Mon 2026-07-28 16:30\n"
        ),
        "quant-ts-daily.service": _Proc(
            "LoadState=loaded\nActiveEnterTimestamp=Mon 2026-07-27 16:30\nResult=success\nExecMainStatus=0\n"
        ),
    }
    units = [
        {"unit": "quant-ts-daily.timer", "label": "日线", "service": "quant-ts-daily.service"},
        {"unit": "qre-refresh.timer", "label": "QRE", "service": "qre-refresh.service"},
    ]
    results = timer_status(units, runner=_runner_factory(mapping))
    qt, qr = results
    assert qt["status"] == "installed"
    assert qt["active_state"] == "active"
    assert qt["next_elapse"] == "Mon 2026-07-28 16:30"
    assert qt["last_result"] == "success"
    assert qt["last_exit_status"] == "0"
    assert qr["status"] == "not_installed"
    assert "sudo cp deploy/qre-refresh" in qr["install_hint"]


# --- health ---


def test_health_green():
    h = health_status("2026-07-27", ["2026-07-27", "2026-07-27"])
    assert h["level"] == "green"


def test_health_yellow_small_lag():
    h = health_status("2026-07-27", ["2026-07-27", "2026-07-25"])
    assert h["level"] == "yellow"
    assert "滞后" in h["detail"]


def test_health_red_large_lag_or_missing():
    assert health_status("2026-07-27", ["2026-07-01"])["level"] == "red"
    assert health_status("2026-07-27", [None, "2026-07-27"])["level"] == "red"
    assert health_status(None, ["2026-07-27"])["level"] == "red"


# --- overview_backtests ---


def test_overview_backtests(tmp_path):
    (tmp_path / "backtests" / "b1" / "strat_a").mkdir(parents=True)
    (tmp_path / "backtests" / "b1" / "strat_b").mkdir(parents=True)
    (tmp_path / "backtests" / "b2" / "strat_c").mkdir(parents=True)
    admin._cache.clear()
    with patch("quant_research_engine.gui.admin.subprocess.run") as mock_run:
        mock_run.return_value = _Proc(stdout=f"{5 * 1024**3}\t{tmp_path}\n")
        result = overview_backtests(tmp_path)
    assert result["batch_count"] == 2
    assert result["strategy_dir_count"] == 3
    assert result["size_bytes"] == 5 * 1024**3
    assert result["latest_batch"] == "b2"
    # 缓存命中：第二次不再调 du
    result2 = overview_backtests(tmp_path)
    assert result2["batch_count"] == 2
    assert mock_run.call_count == 1
    admin._cache.clear()


# --- overview_daily / overview_factors（fake store 注入） ---


def test_overview_daily_and_factors(monkeypatch):
    admin._cache.clear()
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    daily = admin.overview_daily()
    assert daily["estimated_rows"] == 123456
    assert daily["watermark"] == "2026-07-27"
    assert daily["symbol_count"] == 5547
    assert daily["recent_trade_dates"] == ["2026-07-27", "2026-07-24"]

    factors = admin.overview_factors()
    assert factors["daily_watermark"] == "2026-07-27"
    assert len(factors["tables"]) == 2
    assert factors["unmanaged_tables"] == []
    assert factors["lagging_tables"] == [
        "factors.stock_daily_momentum_close",
        "factors.stock_daily_overlap_close",
    ]
    admin._cache.clear()


# --- 纳管表清单（QRE-ADMIN-FACTOR-HEALTH-FIX-001） ---


def test_managed_factor_tables_from_config(tmp_path, monkeypatch):
    import quant_research_engine.gui.factor_admin as fa

    repo = tmp_path / "indicators"
    (repo / "config").mkdir(parents=True)
    (repo / "config" / "factors.yaml").write_text(
        "factors:\n"
        "  - name: sma\n    category: overlap\n    column: close\n    periods: [5]\n"
        "  - name: ema\n    category: overlap\n    column: typical_price\n    periods: [3]\n"
        "  - name: rsi\n    category: momentum\n    column: close\n    periods: [14]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: repo)
    tables = admin.managed_factor_tables()
    assert tables == {
        "stock_daily_overlap_close",
        "stock_daily_overlap_typical_price",
        "stock_daily_momentum_close",
    }


def test_managed_factor_tables_fallback(monkeypatch, tmp_path):
    import quant_research_engine.gui.factor_admin as fa

    monkeypatch.setattr(fa, "indicators_repo", lambda env=None: tmp_path / "nonexistent")
    tables = admin.managed_factor_tables()
    assert tables == set(admin.MANAGED_FACTOR_TABLES_FALLBACK)
    assert len(tables) == 10
    assert "stock_daily_vortex_close" not in tables


def test_overview_factors_orphan_goes_unmanaged(monkeypatch):
    """孤儿表（不在纳管清单）进未纳管段，不参与滞后判定。"""
    admin._cache.clear()
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    # 只纳管 momentum；overlap 视为孤儿表
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close"},
    )
    factors = admin.overview_factors()
    assert [t["table"] for t in factors["tables"]] == ["factors.stock_daily_momentum_close"]
    assert [t["table"] for t in factors["unmanaged_tables"]] == ["factors.stock_daily_overlap_close"]
    assert factors["lagging_tables"] == ["factors.stock_daily_momentum_close"]
    admin._cache.clear()


def test_overview_factors_orphan_does_not_affect_health(monkeypatch):
    """纳管表全部新鲜时健康灯为绿，即使存在滞后/空的孤儿表。"""
    admin._cache.clear()
    store = FakeStore(factor_maxes={
        "stock_daily_momentum_close": "2026-07-27",  # 纳管，新鲜
        "stock_daily_overlap_close": None,           # 孤儿，无数据
    })
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: store)
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close"},
    )
    factors = admin.overview_factors()
    assert factors["lagging_tables"] == []
    health = admin.health_status(
        factors["daily_watermark"], [t["watermark"] for t in factors["tables"]]
    )
    assert health["level"] == "green"
    # 孤儿表仍在未纳管段可见
    assert factors["unmanaged_tables"][0]["table"] == "factors.stock_daily_overlap_close"
    admin._cache.clear()


# --- 路由层 ---


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "quant_research_engine.gui.app.TEMPLATE_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "templates",
    )
    monkeypatch.setattr(
        "quant_research_engine.gui.app.STATIC_DIR",
        Path(__file__).resolve().parent.parent / "src" / "quant_research_engine" / "gui" / "static",
    )
    monkeypatch.setattr("quant_research_engine.gui.engine.TEMPLATES_DIR", tmp_path / "templates")
    monkeypatch.setattr("quant_research_engine.gui.engine.RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr("quant_research_engine.gui.engine.GUI_BASE_DIR", tmp_path)
    admin._cache.clear()

    from quant_research_engine.gui.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    admin._cache.clear()


def test_admin_page_200(app_client):
    resp = app_client.get("/admin")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8")
    assert "管理台" in html
    assert "总览" in html and "日更状态" in html and "数据查询" in html


def test_api_admin_overview_ok(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.managed_factor_tables",
        lambda repo=None: {"stock_daily_momentum_close", "stock_daily_overlap_close"},
    )
    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["daily"]["watermark"] == "2026-07-27"
    assert data["health"]["level"] in ("yellow", "red")  # fake 因子表滞后
    assert "backtests" in data


def test_api_admin_overview_db_down(app_client, monkeypatch):
    def boom(db_url=None):
        raise ConnectionError("refused")

    monkeypatch.setattr("quant_research_engine.gui.admin._store", boom)
    resp = app_client.get("/api/admin/overview")
    assert resp.status_code == 503
    assert "数据库不可用" in resp.get_json()["error"]


def test_api_admin_query_daily_ok(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    resp = app_client.get("/api/admin/query/daily?ts_code=000001.SZ&start=2026-07-01&end=2026-07-27")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["total"] == 3


def test_api_admin_query_daily_400(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    resp = app_client.get("/api/admin/query/daily?ts_code=&start=a&end=b")
    assert resp.status_code == 400


def test_api_admin_query_daily_csv(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    resp = app_client.get("/api/admin/query/daily?ts_code=000001.SZ&start=a&end=b&format=csv")
    assert resp.status_code == 200
    assert resp.mimetype == "text/csv"
    text = resp.data.decode("utf-8")
    assert "trade_date" in text.splitlines()[0]
    assert "attachment" in resp.headers.get("Content-Disposition", "")


def test_api_admin_query_factor_injection_rejected(app_client, monkeypatch):
    monkeypatch.setattr("quant_research_engine.gui.admin._store", lambda db_url=None: FakeStore())
    resp = app_client.get("/api/admin/query/factor?table=factors.stock_daily_momentum_close&column=rsi_14%3BDROP&ts_code=000001.SZ&start=a&end=b")
    assert resp.status_code == 400
    assert "非法因子列名" in resp.get_json()["error"]


def test_api_admin_timers(app_client, monkeypatch):
    monkeypatch.setattr(
        "quant_research_engine.gui.admin.timer_status",
        lambda units=None: [{"unit": "qre-refresh.timer", "status": "not_installed"}],
    )
    resp = app_client.get("/api/admin/timers")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert data["timers"][0]["status"] == "not_installed"
