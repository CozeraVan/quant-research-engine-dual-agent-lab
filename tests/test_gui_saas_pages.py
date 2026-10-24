"""QRE-SAAS-004 SaaS 前端页面测试。

页面路由 200 + 关键元素存在；/api/saas/nl/compile 与 /api/saas/factors
在 saas app 中可用（LLM 层 monkeypatch nl_compiler.call_llm 为固定 YAML，
与既有 test_gui_nl_compiler.py 的 stub 思路一致——不触真实 DeepSeek）。
"""

from __future__ import annotations

import subprocess
import uuid

import pytest

from quant_research_engine.gui.saas import create_saas_app

WORKER_TOKEN = "t"
VALID_YAML = (
    "experiment:\n  name: t\ndata:\n  market_fields: [close]\n"
    "signal:\n  entry: close > 0\n"
    "evaluation:\n  forward_return_horizons: [1, 3, 5]\n"
    "holding:\n  max_holding_days: 20\n"
)


def _psql(db: str, *args: str) -> None:
    subprocess.run(
        ["psql", f"postgresql:///{db}", "-v", "ON_ERROR_STOP=1", *args],
        check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def saas_db():
    db_name = f"qre_saas_pages_{uuid.uuid4().hex[:12]}"
    _psql("postgres", "-c", f"CREATE DATABASE {db_name}")
    _psql(db_name, "-f", "deploy/saas/cloud_schema.sql")
    yield db_name
    _psql("postgres", "-c", f"DROP DATABASE IF EXISTS {db_name}")


@pytest.fixture()
def client(saas_db):
    app = create_saas_app()
    app.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
    app.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
    app.config["SAAS_DEV_AUTH"] = "1"
    app.config["SAAS_AUTH_CHANNEL"] = "stub"
    from sqlalchemy import text

    from quant_research_engine.gui.saas.app import _get_engine

    with _get_engine(app).begin() as conn:
        conn.execute(text("TRUNCATE results, jobs, strategies, users, sessions, sms_codes RESTART IDENTITY CASCADE"))
    yield app.test_client()
    engine = app.extensions.get("saas_engine")
    if engine is not None:
        engine.dispose()


AUTH = {"X-User-Id": "1"}  # dev 后门


class TestPages:
    def test_login_page(self, client):
        resp = client.get("/saas/login")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="login-target"' in html and 'id="login-code"' in html
        # D1D2：邮箱+密码登录/注册（内测临时方案，验证码通道下线后 UI 替换）
        assert 'id="tab-login"' in html and 'id="tab-register"' in html
        assert 'type="password"' in html and 'id="btn-login"' in html
        assert 'name="viewport"' in html

    def test_login_page_preserves_safe_next(self, client):
        resp = client.get("/saas/login?next=/saas/jobs/78%3Fx%3D1%23risk")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'const LOGIN_NEXT = "/saas/jobs/78?x=1#risk";' in html
        assert "location.href = LOGIN_NEXT;" in html
        assert "location.href = '/saas/';" not in html
        assert 'href="/saas/login/authing?next=%2Fsaas%2Fjobs%2F78%3Fx%3D1%23risk"' in html

    def test_common_access_fallback_helpers(self, client):
        html = client.get("/saas/login").get_data(as_text=True)
        for marker in (
            "function saasLoginUrl()",
            "function showAccessFallback(root)",
            "function showLoadFailure(root, retryFn)",
            "opts.redirectOn401 !== false",
            "error.status = 401",
            "location.pathname + location.search + location.hash",
            "页面不存在或暂无访问权限",
            "登录/注册",
            "返回首页",
            "登录后可查看并管理自己的回测记录",
            "加载失败，请稍后重试",
            "root.replaceChildren(card)",
            "document.createElement",
            "retryFn",
        ):
            assert marker in html

    def test_dashboard_page(self, client):
        resp = client.get("/saas/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # QRE-SAAS-RECORDS-UI：与 8081 对齐的记录页结构
        assert 'id="jobs-tbody"' in html and 'class="page-head"' in html
        assert 'id="recs-filter"' in html and "筛选策略名" in html
        assert 'class="card"' in html and 'id="del-mask"' in html
        # 无重复头部 panel（历史结构 bug：曾渲染出两个「我的回测记录」头）
        assert html.count("我的回测记录") <= 2
        assert '排队中' in html or "STATUS_LABEL" in html

    def test_new_page(self, client):
        resp = client.get("/saas/new")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # C5：三入口卡 + 共用参数 + 预览栏 + 唯一流水线按钮（冻结版结构平移）
        assert 'id="entryGrid"' in html and 'data-entry="nl"' in html and 'data-entry="wizard"' in html and 'data-entry="yaml"' in html
        assert 'id="nl-text"' in html and 'id="wz-entry"' in html and 'id="yaml-editor"' in html
        assert 'id="btn-run-main"' in html  # 唯一「运行回测」（冒烟→全量流水线）
        assert 'id="pv-view"' in html       # 策略代码预览栏（行号+高亮）
        assert 'id="cal-pop"' in html       # 日历选区间
        assert 'id="p-random-n"' in html    # 随机股票 N（板块/概念降级说明在页面上）

    def test_job_page(self, client):
        resp = client.get("/saas/jobs/1")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="chart-main"' in html and 'id="bench-bar"' in html  # 净值 vs 基准可切换
        assert 'id="job-badge"' in html and '/static/echarts.min.js' in html
        assert 'id="chart-tags"' in html and 'id="tag-rank"' in html  # 归因区块
        assert 'id="metric-strip"' in html and 'id="meta-chips"' in html
        assert 'id="box-risk"' in html and 'id="box-fees"' in html   # C5：FRM + 交易磨损（无数据整块隐藏）
        assert 'id="big-symbols"' in html                            # 个股明细大入口
        # QRE-SAAS-RESULT-ACTIONS：结果页末尾操作卡（保存入库/提示交易信号；游客 JS 隐藏）
        assert 'id="box-actions"' in html and 'id="btn-save-lib"' in html
        assert 'id="btn-signal-open"' in html and 'id="signal-panel"' in html
        assert 'sig-scope' in html and 'last_run_universe' in html and 'all_a' in html
        # CR-2026-10-04 切片1：回测重播（共享组件 replay.js；接管模式：接管原收益曲线容器）
        assert '/static/replay.js' in html and 'id="btn-replay"' in html and 'id="btn-replay-exit"' in html
        assert 'id="replay-bar-slot"' in html and 'id="replay-metrics"' in html and 'id="replay-events"' in html
        # QRE-SAAS-DETAIL-UI：区间信息卡（8081 同款随滑块重算）+ meta chips 全字段
        assert 'id="range-strip"' in html and "updateRangeStrip" in html
        assert "区间策略收益" in html and "交易日数" in html
        assert "最大持仓" in html and "引擎" in html and "费率" in html

    def test_no_engineering_jargon(self, client):
        # 零术语原则：页面不得出现 沙箱/晋升/promote/试算 等内部词
        for page in ("/saas/", "/saas/new", "/saas/jobs/1"):
            html = client.get(page).get_data(as_text=True)
            for word in ("沙箱", "晋升", "promote", "试算"):
                assert word not in html, f"{page} 含术语 {word}"

    def test_static_echarts_served(self, client):
        resp = client.get("/static/echarts.min.js")
        assert resp.status_code == 200
        assert len(resp.data) > 100_000  # vendored echarts 复用，非占位


class TestSaasRandomSymbolRoute:
    def test_random_symbol_from_metadata(self, client):
        """QRE-SAAS-GUEST-RANDOM-SYMBOL：元数据 all_a_codes 口径，游客可用。"""
        resp = client.get("/api/saas/random-symbol")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and isinstance(data["ts_code"], str) and data["ts_code"]


class TestSaasNlCompileRoute:
    def test_guest_compile_allowed_but_rate_limited(self, client, monkeypatch, tmp_path):
        """游客开放 NL 编译（QRE-SAAS-GUEST-NL）：未配置 LLM 时 503；
        单 IP 每日限 GUEST_NL_DAILY_LIMIT 次，超限 403。"""
        monkeypatch.setenv("QRE_GUEST_NL_COUNTER", str(tmp_path / "nl-counter.json"))
        for var in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)
        # 游客（无 AUTH 头）不再 401：走到编译逻辑，LLM 未配置 → 503
        assert client.post("/api/saas/nl/compile", json={"description": "x"}).status_code == 503
        from quant_research_engine.gui.saas import app as saas_app

        for _ in range(saas_app.GUEST_NL_DAILY_LIMIT - 1):
            client.post("/api/saas/nl/compile", json={"description": "x"})
        resp = client.post("/api/saas/nl/compile", json={"description": "x"})
        assert resp.status_code == 403
        assert resp.get_json()["code"] == "guest_nl_limit"

    def test_empty_description_400(self, client):
        resp = client.post("/api/saas/nl/compile", json={"description": " "}, headers=AUTH)
        assert resp.status_code == 400

    def test_compile_success_with_stubbed_llm(self, client, monkeypatch):
        monkeypatch.setenv("QRE_NL_LLM_BASE_URL", "https://llm.test")
        monkeypatch.setenv("QRE_NL_LLM_API_KEY", "k")
        monkeypatch.setenv("QRE_NL_LLM_MODEL", "m")
        monkeypatch.setattr(
            "quant_research_engine.gui.nl_compiler.call_llm",
            lambda description, config, **kw: VALID_YAML,
        )
        monkeypatch.setattr(
            "quant_research_engine.gui.nl_compiler._default_column_lookup",
            lambda db_url=None: None,  # DB 不可用 → 跳过因子存在性检查
        )
        resp = client.post("/api/saas/nl/compile",
                           json={"description": "收盘价大于 0 买入"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and "entry" in data["yaml"]

    def test_not_configured_503(self, client, monkeypatch):
        for var in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)
        resp = client.post("/api/saas/nl/compile", json={"description": "x"}, headers=AUTH)
        assert resp.status_code == 503
        assert resp.get_json()["code"] == "not_configured"


class TestSaasFactorsRoute:
    def test_anonymous_allowed(self, client):
        # 因子目录为只读元数据，对游客开放（配额在提交环节收口）
        assert client.get("/api/saas/factors").status_code == 200

    def test_groups_shape(self, client, monkeypatch):
        monkeypatch.setattr(
            "quant_research_engine.gui.factor_wizard.load_factor_tables_columns",
            lambda db_url=None: {"stock_daily_momentum_close": ["rsi_14", "mom_10"]},
        )
        resp = client.get("/api/saas/factors", headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and data["groups"]
        assert data["groups"][0]["group"] == "market"  # 首组行情字段
        assert any(g["label"] for g in data["groups"])


class TestFactorRequests:
    def test_submit_list_dedup(self, client):
        resp = client.post("/api/saas/factor-requests",
                           json={"strategy_name": "s1", "factors": ["rsi_99", "foo_1"]}, headers=AUTH)
        assert resp.status_code == 200 and resp.get_json()["status"] == "pending"
        # 24h 内同因子集合去重（顺序无关）
        dup = client.post("/api/saas/factor-requests",
                          json={"factors": ["foo_1", "rsi_99"]}, headers=AUTH)
        assert dup.status_code == 409
        # 不同集合可提交
        other = client.post("/api/saas/factor-requests", json={"factors": ["bar_2"]}, headers=AUTH)
        assert other.status_code == 200

        lst = client.get("/api/saas/factor-requests", headers=AUTH).get_json()["requests"]
        assert len(lst) == 2
        assert lst[0]["factors"] == ["bar_2"]  # 倒序
        assert lst[1]["status"] == "pending"

    def test_isolated_by_user(self, client):
        client.post("/api/saas/factor-requests", json={"factors": ["x_1"]}, headers=AUTH)
        other = client.get("/api/saas/factor-requests", headers={"X-User-Id": "2"}).get_json()
        assert other["requests"] == []

    def test_unauthorized_401(self, client):
        assert client.post("/api/saas/factor-requests", json={"factors": ["x"]}).status_code == 401
        assert client.get("/api/saas/factor-requests").status_code == 401

    def test_bad_payload_400(self, client):
        assert client.post("/api/saas/factor-requests", json={"factors": []}, headers=AUTH).status_code == 400
        assert client.post("/api/saas/factor-requests", json={}, headers=AUTH).status_code == 400


class TestNoAdminLinks:
    """需求 2：SaaS 页面不得出现指向内网管理端/未实现功能的链接。"""

    @pytest.mark.parametrize("page", ["/saas/login", "/saas/", "/saas/new", "/saas/jobs/1"])
    def test_no_admin_or_internal_links(self, client, page):
        html = client.get(page).get_data(as_text=True)
        for banned in ("/admin", "factor-admin", "factor-create", "8080", "8081"):
            assert banned not in html, f"{page} 含禁链 {banned}"

    def test_new_page_has_factor_modal(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert 'id="factor-modal"' in html and '提交因子需求' in html and '换个策略' in html

    def test_new_page_big_universe_guard(self, client):
        """QRE-SAAS-LARGE-UNIVERSE-GUARD：大范围标的提交前耗时确认弹层（阈值口径同 lab 版 3000）。"""
        html = client.get("/saas/new").get_data(as_text=True)
        assert 'id="big-univ-modal"' in html
        assert 'id="big-univ-ok"' in html and 'id="big-univ-cancel"' in html
        assert 'class="modal-mask" id="big-univ-modal"' in html  # 规范弹层组件（非原生 confirm）
        assert 'LARGE_UNIVERSE_THRESHOLD = 3000' in html
        assert "大范围回测耗时提示" in html and "几分钟到十几分钟" in html
        assert "confirmBigUniverse" in html and "largeUniverseEstimate" in html
        assert "all_a_count" in html  # 全部 A 股计数来自 /api/saas/universes

    def test_dashboard_has_factor_request_section(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        assert 'id="factor-req-tbody"' in html and '我的因子申请' in html

    def test_profile_page(self, client):
        # QRE-SAAS-PROFILE：个人信息页 = 账号信息卡 + 复用记录区（_records_* partial）
        resp = client.get("/saas/profile")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert 'id="pf-account"' in html and 'id="pf-tier"' in html and 'id="pf-quota"' in html
        assert 'id="jobs-tbody"' in html and 'id="del-mask"' in html  # 回测记录内嵌
        assert "个人信息" in html
        # header 导航指向个人信息页
        assert 'href="/saas/profile"' in html and "个人信息</a>" in html

    def test_dashboard_and_profile_share_records_partials(self, client):
        # 两页共用 _records_body/_records_scripts，渲染出的记录区结构一致
        dash = client.get("/saas/").get_data(as_text=True)
        prof = client.get("/saas/profile").get_data(as_text=True)
        for marker in ('id="jobs-table"', 'id="strat-tbody"', 'id="factor-req-tbody"', "/api/results?sort="):
            assert marker in dash and marker in prof


class TestStubEcho:
    def test_echo_off_by_default(self, client):
        resp = client.post("/api/saas/auth/code", json={"target": "echo@example.com"})
        assert "dev_code" not in resp.get_json()

    def test_echo_on_returns_dev_code(self, saas_db, monkeypatch):
        app2 = create_saas_app()
        app2.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app2.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
        app2.config["SAAS_AUTH_CHANNEL"] = "stub"
        app2.config["SAAS_STUB_ECHO"] = "1"
        c2 = app2.test_client()
        resp = c2.post("/api/saas/auth/code", json={"target": "echo2@example.com"})
        data = resp.get_json()
        assert data["ok"] and len(data["dev_code"]) == 6
        # dev_code 可直接登录
        login = c2.post("/api/saas/auth/login",
                        json={"target": "echo2@example.com", "code": data["dev_code"]})
        assert login.status_code == 200 and login.get_json()["token"]
        engine = app2.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()


class TestAuthBypass:
    """SAAS_AUTH_BYPASS=1（staging 专用，生产严禁）：免登录直用核心功能。"""

    @pytest.fixture()
    def bypass_client(self, saas_db):
        app2 = create_saas_app()
        app2.config["SAAS_DB_URL"] = f"postgresql+psycopg:///{saas_db}"
        app2.config["SAAS_WORKER_TOKEN"] = WORKER_TOKEN
        app2.config["SAAS_AUTH_BYPASS"] = "1"
        yield app2.test_client()
        engine = app2.extensions.get("saas_engine")
        if engine is not None:
            engine.dispose()

    def test_login_page_redirects(self, bypass_client):
        resp = bypass_client.get("/saas/login")
        assert resp.status_code == 302 and "/saas/" in resp.headers["Location"]

    def test_core_apis_without_token(self, bypass_client):
        # 无 token 直接建任务、查列表、查 me（自动建 staging@local 用户）
        created = bypass_client.post("/api/saas/jobs", json={"yaml": "x", "kind": "smoke"})
        assert created.status_code == 200
        me = bypass_client.get("/api/saas/me").get_json()["user"]
        assert me["email"] == "staging@local"
        jobs = bypass_client.get("/api/saas/jobs").get_json()["jobs"]
        assert jobs[0]["user_id"] == me["id"]

    def test_bypass_off_keeps_401(self, client):
        # 默认关（client fixture 未开 bypass）：维持 401
        assert client.get("/api/saas/me").status_code == 401
        # D1D2：匿名提交走游客校验（无单股参数 → 403 而非 401）
        assert client.post("/api/saas/jobs", json={"yaml": "x"}).status_code == 403


class TestResultsDataSource:
    """B3：回测记录/结果详情页数据源切到 B1/B2 的 /api/results 系列。"""

    def test_dashboard_uses_results_api(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        assert "/api/results?sort=" in html                # 列表走 /api/results（排序/分页）
        assert "/api/saas/jobs')" not in html              # 不再走旧 jobs 列表
        assert "job.job_id" in html                        # 新字段名
        assert "strategy_name" in html

    def test_guest_ux_elements(self, client):
        """QRE-SAAS-GUEST-UX：统一顶栏/游客条/游客确认弹层/参数区 8081 对齐字段。"""
        html = client.get("/saas/new").get_data(as_text=True)
        # 统一顶栏（无指向 8080 管理台的链接由禁链断言另行保证）
        assert 'class="topbar"' in html and 'data-nav="new"' in html and 'data-nav="records"' in html
        assert 'id="guest-strip"' in html and "游客模式" in html
        # 游客确认弹层：两按钮 + 说明文案
        assert 'id="guest-modal"' in html and 'id="guest-continue"' in html and 'id="guest-register"' in html
        assert "每日 1 次" in html and "结果次日清空" in html
        # 参数区对齐：全期按钮 + 费率/滑点字段 + scope 三选项
        assert 'id="range-all"' in html and "全期(2010起)" in html
        assert 'id="p-comm"' in html and 'id="p-mincomm"' in html and 'id="p-stamp"' in html
        assert 'id="p-slipb"' in html and 'id="p-slips"' in html
        assert 'value="all"' in html and 'value="codes"' in html and 'value="random"' in html
        # 游客分流逻辑
        assert "isGuest()" in html and "openGuestModal" in html and "继续游客测试" in html
        # job 页游客结果提示
        job = client.get("/saas/jobs/1").get_data(as_text=True)
        assert 'id="guest-result-note"' in job and "次日清空" in job

    def test_symbols_pages_registered(self, client):
        html = client.get("/saas/jobs/1/symbols").get_data(as_text=True)
        assert 'id="sym-table"' in html and "/api/results/" in html and "/symbols" in html
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        assert 'id="sum-strip"' in html and 'id="chart-kline"' in html
        # CR-2026-10-04 切片2：K线级重播（复用切片1 replay.js；接管模式：接管原 K线容器）
        assert '/static/replay.js' in html and 'id="btn-kreplay"' in html and 'id="btn-kreplay-exit"' in html
        assert 'id="kreplay-bar-slot"' in html and 'id="kreplay-info"' in html and 'id="kreplay-events"' in html
        assert "/api/results/" in html and "/symbols/" in html

    def test_job_page_uses_results_detail_apis(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert "/api/results/' + JOB_ID + '/summary'" in html
        assert "/chart-data" in html and "/tag-analysis" in html
        assert "resp.status === 409" in html               # 未完成 → 进行状态轮询
        assert "/api/saas/jobs/' + JOB_ID" not in html     # 不再走旧 job 嵌套 result


class TestSecurityHardening:
    """N4 安全初步：响应头 + 模板转义（QRE-SAAS-SEC-HARDEN）。"""

    def test_security_headers(self, client):
        resp = client.get("/saas/")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "strict-origin" in (resp.headers.get("Referrer-Policy") or "")

    def test_records_template_escapes_user_strings(self, client):
        # 策略名/因子申请等用户输入进 innerHTML 前必须转义（防存储型 XSS）
        for page in ("/saas/", "/saas/profile"):
            html = client.get(page).get_data(as_text=True)
            assert "function escH(" in html
            assert "escH(job.strategy_name" in html and "escH(s.name)" in html
            assert "escH(r.note" in html
