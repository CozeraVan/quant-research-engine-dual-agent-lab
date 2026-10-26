"""QRE-SAAS-NL-A2A3：持久限频（nl_rate_limits）与版本化编译缓存（nl_compile_cache）。

真实本地 PG 临时库（deploy/saas/cloud_schema.sql），LLM 层 monkeypatch
nl_compiler.call_llm（不触真实 DeepSeek、不跑真实回测）。覆盖批准计划
mister-terrific-echo-vision.md §4：
1. 同输入第二次 cache_hit=true 且 call_llm 只调用一次；空白归一化命中；不同描述 miss。
2. model/base_url/prompt/cache_version 任一变化均 miss；缓存结果保留
   yaml/warnings/corrections/fix_attempts，无 API key。
3. 失败结果不缓存；not_configured 不缓存；命中后返回与首次一致的成功 YAML。
4. 同 key 并发只调用一次 LLM；不同 key 不互相阻塞。
5. 游客第 11 次仍为 403/code=guest_nl_limit，计数跨 app 实例和重启不丢失。
6. 会员第 7 次/分钟为 429，下一分钟窗口恢复；admin 不限；缓存命中不占额度，
   miss 失败也只计一次。
7. 并发请求不超过限额；两表 GRANT 与 schema 幂等 apply。
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "test-worker-token"

VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5, 10, 20]\n  quantiles: 5\n"
    "holding:\n  max_holding_days: 20\n"
)
# 含一处可归一化纠正的因子名（rsi14 → rsi_14）的 YAML
CORRECTABLE_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "  factor_fields:\n    rsi14: factors.stock_daily_overlap_close.rsi14\n"
    "signal:\n  entry: rsi14 < 30\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5, 10, 20]\n  quantiles: 5\n"
    "holding:\n  max_holding_days: 20\n"
)
LLM_ENV = {
    "QRE_NL_LLM_BASE_URL": "https://llm.test",
    "QRE_NL_LLM_API_KEY": "k",
    "QRE_NL_LLM_MODEL": "m",
}


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_nl_cache_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE)")


def _make_app(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    return app


@pytest.fixture()
def app(saas_db):
    app = _make_app(saas_db)
    yield app
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def _clean(app, saas_db):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes, "
                          "share_links, nl_rate_limits, nl_compile_cache "
                          "RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def llm(monkeypatch):
    """桩 LLM：记录调用次数，可注入异常；因子库 lookup=None 跳过存在性检查。"""
    from quant_research_engine.gui import nl_compiler

    for key, value in LLM_ENV.items():
        monkeypatch.setenv(key, value)

    class _Stub:
        def __init__(self):
            self.calls: list[str] = []
            self.exc: Exception | None = None
            self.yaml_text = VALID_YAML

        def __call__(self, description, config, **kw):
            self.calls.append(description)
            if self.exc is not None:
                raise self.exc
            return self.yaml_text

    stub = _Stub()
    monkeypatch.setattr(nl_compiler, "call_llm", stub)
    monkeypatch.setattr(nl_compiler, "_default_column_lookup", lambda db_url=None: None)
    return stub


def _member(app, uid=1, role="user"):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(text("INSERT INTO users (id, email, tier, role) "
                          "VALUES (:i, :e, 'member', :r)"),
                     {"i": uid, "e": f"u{uid}@example.com", "r": role})


MEMBER = {"X-User-Id": "1"}
ADMIN = {"X-User-Id": "2"}


def _compile(client, description, headers=None):
    return client.post("/api/saas/nl/compile",
                       json={"description": description}, headers=headers or {})


def _rate_rows(app, scope=None):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    sql = "SELECT scope, subject_hash, window_start, hits FROM nl_rate_limits"
    if scope:
        sql += " WHERE scope = :s"
    with _get_engine(app).connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), {"s": scope}).mappings().all()]


def _cache_rows(app):
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).connect() as conn:
        return [dict(r) for r in conn.execute(
            text("SELECT * FROM nl_compile_cache")).mappings().all()]


# --- 缓存命中 / 归一化 / miss ---

class TestCacheHit:
    def test_second_call_hit_no_llm(self, client, app, llm):
        _member(app)
        first = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert first.status_code == 200
        assert first.get_json()["cache_hit"] is False
        second = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert second.status_code == 200
        body = second.get_json()
        assert body["cache_hit"] is True
        assert body["yaml"] == first.get_json()["yaml"]
        assert len(llm.calls) == 1
        rows = _cache_rows(app)
        assert len(rows) == 1 and rows[0]["hit_count"] == 1

    def test_whitespace_normalization_hit(self, client, app, llm):
        _member(app)
        _compile(client, "MACD   金叉买入\n死叉卖出", MEMBER)
        resp = _compile(client, "  MACD 金叉买入 死叉卖出  ", MEMBER)
        assert resp.get_json()["cache_hit"] is True
        assert len(llm.calls) == 1

    def test_different_description_miss(self, client, app, llm):
        _member(app)
        _compile(client, "MACD 金叉买入", MEMBER)
        resp = _compile(client, "RSI 低于 30 买入", MEMBER)
        assert resp.get_json()["cache_hit"] is False
        assert len(llm.calls) == 2
        assert len(_cache_rows(app)) == 2


class TestCacheKeyInputs:
    def _prime(self, client, app, llm, monkeypatch=None):
        _member(app)
        return _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)

    def test_model_change_miss(self, client, app, llm, monkeypatch):
        self._prime(client, app, llm)
        monkeypatch.setenv("QRE_NL_LLM_MODEL", "m2")
        resp = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert resp.get_json()["cache_hit"] is False
        assert len(llm.calls) == 2

    def test_base_url_change_miss(self, client, app, llm, monkeypatch):
        self._prime(client, app, llm)
        monkeypatch.setenv("QRE_NL_LLM_BASE_URL", "https://llm2.test")
        resp = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert resp.get_json()["cache_hit"] is False
        assert len(llm.calls) == 2

    def test_prompt_change_miss(self, client, app, llm, monkeypatch):
        from quant_research_engine.gui import nl_compiler

        self._prime(client, app, llm)
        original_prompt = nl_compiler.build_system_prompt
        monkeypatch.setattr(nl_compiler, "build_system_prompt",
                            lambda: original_prompt() + "\nEXTRA")
        resp = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert resp.get_json()["cache_hit"] is False
        assert len(llm.calls) == 2

    def test_cache_version_change_miss(self, client, app, llm, monkeypatch):
        from quant_research_engine.gui.saas import nl_compile_support

        self._prime(client, app, llm)
        monkeypatch.setattr(nl_compile_support, "NL_COMPILER_CACHE_VERSION", "2099-01-01.1")
        resp = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
        assert resp.get_json()["cache_hit"] is False
        assert len(llm.calls) == 2


class TestResultFidelity:
    def test_full_result_preserved_no_api_key(self, client, app, llm, monkeypatch):
        from quant_research_engine.gui import nl_compiler

        _member(app)
        llm.yaml_text = CORRECTABLE_YAML
        monkeypatch.setattr(
            nl_compiler, "_default_column_lookup",
            lambda db_url=None: (lambda table: {"rsi_14"}
                                 if table == "factors.stock_daily_overlap_close" else set()),
        )
        first = _compile(client, "RSI14 低于 30 买入", MEMBER)
        assert first.status_code == 200
        body = first.get_json()
        assert body["ok"] and body["yaml"]
        assert body.get("corrections"), "应保留自动纠正记录"
        assert body.get("warnings"), "应保留 warnings"
        second = _compile(client, "RSI14 低于 30 买入", MEMBER)
        assert second.get_json()["cache_hit"] is True
        for key in ("yaml", "warnings", "corrections"):
            assert second.get_json()[key] == body[key]
        row = _cache_rows(app)[0]
        dumped = json.dumps(row["result"], ensure_ascii=False)
        assert "api_key" not in dumped and "k" != dumped
        assert row["model"] == "m" and row["cache_version"]
        assert row["prompt_hash"] and len(row["prompt_hash"]) == 64

    def test_fix_attempts_preserved(self, client, app, llm, monkeypatch):
        from quant_research_engine.gui import nl_compiler

        _member(app)
        monkeypatch.setattr(nl_compiler, "compile_nl",
                            lambda description, **kw: {
                                "ok": True, "yaml": VALID_YAML,
                                "warnings": ["w"], "corrections": [{"alias": "a"}],
                                "fix_attempts": 2,
                            })
        first = _compile(client, "MACD 金叉买入", MEMBER)
        body = first.get_json()
        assert body["cache_hit"] is False and body["fix_attempts"] == 2
        second = _compile(client, "MACD 金叉买入", MEMBER)
        hit = second.get_json()
        assert hit["cache_hit"] is True
        assert hit["fix_attempts"] == 2 and hit["corrections"] == [{"alias": "a"}]
        assert "cache_hit" not in _cache_rows(app)[0]["result"]


class TestFailureNotCached:
    def test_llm_error_not_cached_and_counts_each_miss(self, client, app, llm):
        _member(app)
        llm.exc = RuntimeError("boom")
        first = _compile(client, "MACD 金叉买入", MEMBER)
        assert first.status_code == 200  # 业务体错误，HTTP 仍 200（既有语义）
        assert first.get_json()["code"] == "llm_error"
        assert _cache_rows(app) == []
        second = _compile(client, "MACD 金叉买入", MEMBER)
        assert second.get_json()["code"] == "llm_error"
        assert len(llm.calls) == 2
        rows = _rate_rows(app, "member_minute")
        assert len(rows) == 1 and rows[0]["hits"] == 2

    def test_not_configured_not_cached(self, client, app, llm, monkeypatch):
        _member(app)
        for var in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)
        resp = _compile(client, "MACD 金叉买入", MEMBER)
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "not_configured"
        assert _cache_rows(app) == []
        rows = _rate_rows(app, "member_minute")
        assert len(rows) == 1 and rows[0]["hits"] == 1


class TestConcurrency:
    def test_same_key_single_llm_call(self, client, app, llm):
        """同 key 并发：咨询锁保证只调用一次 LLM，其余请求拿到缓存命中。"""
        _member(app)
        results: list = []
        lock = threading.Lock()

        def worker():
            resp = _compile(client, "MACD 金叉买入，死叉卖出", MEMBER)
            with lock:
                results.append(resp.get_json())

        threads = [threading.Thread(target=worker) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert len(results) == 3
        assert len(llm.calls) == 1
        hits = sorted(r["cache_hit"] for r in results)
        assert hits == [False, True, True]
        assert len(_cache_rows(app)) == 1
        # 同 key 并发只消耗一次配额（其余为缓存命中）
        rows = _rate_rows(app, "member_minute")
        assert len(rows) == 1 and rows[0]["hits"] == 1

    def test_different_keys_not_serialized(self, client, app, llm):
        """不同 key 不得互相阻塞：两个 LLM 调用必须能同时处于进行中。

        用两个不同会员：配额行锁按 (scope, subject, window) 生效，同会员同分钟
        本就会话级串行（原子计数的固有属性）；不同会员 + 不同描述时缓存咨询锁
        与配额行均不冲突，必须并行。
        """
        _member(app, uid=1)
        _member(app, uid=2)
        entered = threading.Barrier(2, timeout=15)
        release = threading.Event()

        def slow(description, config, **kw):
            llm.calls.append(description)
            entered.wait(timeout=15)
            release.wait(timeout=15)
            return VALID_YAML

        import quant_research_engine.gui.nl_compiler as nc
        nc.call_llm = slow
        done: list[str] = []

        def worker(desc, uid):
            resp = _compile(client, desc, {"X-User-Id": str(uid)})
            done.append(desc)
            release.set()

        t1 = threading.Thread(target=worker, args=("MACD 金叉买入", 1))
        t2 = threading.Thread(target=worker, args=("RSI 低于 30 买入", 2))
        t1.start()
        t2.start()
        entered.wait(timeout=15)
        t1.join(timeout=30)
        t2.join(timeout=30)
        assert len(done) == 2 and len(llm.calls) == 2


# --- 限频 ---

class TestGuestLimit:
    def test_11th_request_403_code_unchanged(self, client, app, llm):
        for i in range(10):
            resp = _compile(client, f"策略描述 {i}", )
            assert resp.status_code == 200, i
        resp = _compile(client, "策略描述 10")
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "guest_nl_limit"
        rows = _rate_rows(app, "guest_daily")
        assert len(rows) == 1 and rows[0]["hits"] == 10

    def test_count_survives_new_app_instance(self, client, app, saas_db, llm):
        for i in range(10):
            assert _compile(client, f"游客策略 {i}").status_code == 200
        engine = app.extensions.get("saas_engine")
        engine.dispose()
        app2 = _make_app(saas_db)  # 模拟重启：新 app + 新 engine
        try:
            resp = _compile(app2.test_client(), "游客策略 10")
            assert resp.status_code == 403
            assert resp.get_json()["code"] == "guest_nl_limit"
        finally:
            engine2 = app2.extensions.get("saas_engine")
            if engine2 is not None:
                engine2.dispose()

    def test_atomic_under_concurrency(self, client, app, llm):
        codes: list[int] = []
        lock = threading.Lock()

        def worker(i):
            resp = _compile(client, f"并发游客策略 {i}")
            with lock:
                codes.append(resp.status_code)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert codes.count(200) == 10
        assert codes.count(403) == 6
        rows = _rate_rows(app, "guest_daily")
        assert len(rows) == 1 and rows[0]["hits"] == 10

    def test_cache_hit_does_not_consume_guest_quota(self, client, app, llm):
        for _ in range(15):
            resp = _compile(client, "MACD 金叉买入，死叉卖出")
            assert resp.status_code == 200
        rows = _rate_rows(app, "guest_daily")
        assert len(rows) == 1 and rows[0]["hits"] == 1


class TestMemberLimit:
    def test_7th_per_minute_429_and_next_minute(self, client, app, llm):
        _member(app)
        for i in range(6):
            resp = _compile(client, f"会员策略 {i}", MEMBER)
            assert resp.status_code == 200, i
        resp = _compile(client, "会员策略 6", MEMBER)
        assert resp.status_code == 429
        body = resp.get_json()
        assert body["code"] == "nl_rate_limited"
        assert body["scope"] == "member_minute"
        assert 1 <= body["reset_seconds"] <= 60
        # 下一分钟窗口恢复（把窗口起点拨回一分钟前）
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        with _get_engine(app).begin() as conn:
            conn.execute(text("UPDATE nl_rate_limits SET window_start = "
                              "window_start - interval '1 minute' "
                              "WHERE scope = 'member_minute'"))
        resp = _compile(client, "会员策略 7", MEMBER)
        assert resp.status_code == 200

    def test_daily_unlimited_across_minutes(self, client, app, llm):
        """每日次数不限：同一会员跨分钟窗口可连续编译（模拟窗口滚动）。"""
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        _member(app)
        for i in range(6):
            assert _compile(client, f"跨分钟策略 {i}", MEMBER).status_code == 200
        # 手动把窗口滚动到上一分钟，模拟时间流逝（不 sleep）
        with _get_engine(app).begin() as conn:
            conn.execute(text("UPDATE nl_rate_limits SET window_start = "
                              "window_start - interval '1 minute' "
                              "WHERE scope = 'member_minute'"))
        for i in range(6, 12):
            assert _compile(client, f"跨分钟策略 {i}", MEMBER).status_code == 200
        rows = _rate_rows(app, "member_minute")
        assert len(rows) == 2 and all(r["hits"] <= 6 for r in rows)

    def test_cache_hit_does_not_consume_member_quota(self, client, app, llm):
        _member(app)
        for _ in range(8):
            assert _compile(client, "MACD 金叉买入，死叉卖出", MEMBER).status_code == 200
        rows = _rate_rows(app, "member_minute")
        assert len(rows) == 1 and rows[0]["hits"] == 1

    def test_admin_unlimited(self, client, app, llm):
        _member(app, uid=2, role="admin")
        for i in range(15):
            resp = _compile(client, f"管理员策略 {i}", ADMIN)
            assert resp.status_code == 200, i
        assert _rate_rows(app) == []


class TestSchemaAndGrants:
    def test_tables_and_columns(self, app):
        from sqlalchemy import text

        from quant_research_engine.gui.saas.app import _get_engine

        with _get_engine(app).connect() as conn:
            rate_cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'nl_rate_limits'"))}
            cache_cols = {r[0] for r in conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'nl_compile_cache'"))}
        assert {"scope", "subject_hash", "window_start", "hits", "updated_at"} <= rate_cols
        assert {"cache_key", "description", "result", "model", "prompt_hash",
                "cache_version", "created_at", "last_hit_at", "hit_count"} <= cache_cols

    def test_schema_idempotent_reapply(self, saas_db):
        _psql(saas_db, "-f", "deploy/saas/cloud_schema.sql")

    def test_grants_when_role_exists(self, saas_db):
        """aguhuice 角色存在时两表 CRUD 已授予；本地无角色则跳过。"""
        role_exists = subprocess.run(
            ["psql", "postgresql:///postgres", "-tAc",
             "SELECT 1 FROM pg_roles WHERE rolname = 'aguhuice'"],
            capture_output=True, text=True).stdout.strip()
        if role_exists != "1":
            pytest.skip("本地无 aguhuice 角色")
        out = subprocess.run(
            ["psql", f"postgresql:///{saas_db}", "-tAc",
             "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
             "WHERE grantee = 'aguhuice' AND table_name IN "
             "('nl_rate_limits', 'nl_compile_cache') ORDER BY 1, 2"],
            capture_output=True, text=True, check=True).stdout
        granted = {(line.split("|")[0], line.split("|")[1])
                   for line in out.strip().splitlines() if line.strip()}
        for table in ("nl_rate_limits", "nl_compile_cache"):
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                assert (table, priv) in granted, f"{table} 缺 {priv}"
