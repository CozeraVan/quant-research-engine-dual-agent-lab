"""QRE-SAAS-PUBLIC-BETA-OPS：关键公网路径真实 Chromium 验收（8099 staging）。

专用临时 staging（127.0.0.1:8099，库 qre_public_beta_audit，seed.py 播种，
LLM 由 run_audit.sh 以桩替换——不触真实 DeepSeek、不跑真实回测）。

场景（全部真实浏览器交互，桌面 1280；375 只验证不破版）：
1. 游客/登录：游客 /saas/ 与 /saas/new 渲染（游客条/三入口/NL 输入）；
   stub 登录后 /saas/ 记录页可用。
2. NL 编译 stub：new 页真实点击「生成策略」→ 等待遮罩 → 编译成功 +
   YAML 预览；同描述第二次 API 命中缓存 cache_hit=true。
3. 任务等待/失败恢复：登录用户提交任务 → 任务页排队中（worker 离线提示）→
   worker 协议 claim + fail(engine_error) → 任务页显示真实失败原因与
   「按原策略重新回测」恢复入口。
4. 结果只读与权限：本人已完成任务结果页完整渲染；匿名 → 统一无权卡；
   他人登录 → 统一无权卡（不泄露存在性）。
5. 反馈分类：登录用户 /saas/feedback 选「问题缺陷」提交 → 历史显示类型/状态。
6. 管理台运营指标：admin /saas/console「公测运营」tab 四窗口切换，指标卡
   与失败原因表渲染且无 NaN；「反馈」tab 按类型筛选 + 状态流转生效。
7. 全页面零 JS error、零横向溢出（含 375）。证据落盘 .tmp/public-beta-ops/。
"""

import gzip
import json
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[3]
BASE = "http://127.0.0.1:8099"
OUT = REPO / ".tmp" / "public-beta-ops"
SEED = json.loads((Path(__file__).resolve().parent / "seed.json").read_text(encoding="utf-8"))
DB = SEED["db"]
WORKER_TOKEN = SEED["worker_token"]
WORKER = {"X-Worker-Token": WORKER_TOKEN}
LOGIN_PHONE = SEED["login_phone"]
OTHER_PHONE = SEED["other_phone"]
ADMIN_PHONE = SEED["admin_phone"]
VALID_YAML = SEED["valid_yaml"]

results = []


def record(name, **kw):
    results.append({"case": name, **kw})


def api_post(path, body, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def worker_post(path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", **WORKER})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def check_no_overflow(page, name, view=None):
    widths = page.evaluate("""({
        doc: document.documentElement.scrollWidth, view: innerWidth,
        offenders: [...document.querySelectorAll('body *')].filter(el => {
            const r = el.getBoundingClientRect();
            return r.right > innerWidth + 1 && r.width > 0;
        }).slice(0, 8).map(el => el.tagName + '.' + String(el.className || '').slice(0, 40)
            + '#' + el.id + '@' + Math.round(el.getBoundingClientRect().right)),
    })""")
    limit = view if view is not None else widths["view"]
    assert widths["doc"] <= limit + 1, f"{name}: 横向溢出 {widths} (limit {limit})"
    return widths


def do_login(page, phone):
    out = page.evaluate("""async (target) => {
        const r1 = await fetch('/api/saas/auth/code', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target})});
        const d1 = await r1.json();
        if (!d1.ok || !d1.dev_code) return {step: 'code', body: d1};
        const r2 = await fetch('/api/saas/auth/login', {method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({target, code: d1.dev_code})});
        const d2 = await r2.json();
        if (d2.token) localStorage.setItem('saas_token', d2.token);
        return {status: r2.status, ok: d2.ok};
    }""", phone)
    assert out.get("ok"), f"stub 登录失败: {out}"


def submit_job(page, name, codes=("000001.SZ",)):
    out = page.evaluate("""async ([name, codes]) => {
        const token = localStorage.getItem('saas_token') || '';
        const headers = {'Content-Type': 'application/json'};
        if (token) headers['Authorization'] = 'Bearer ' + token;
        const resp = await fetch('/api/jobs', {
            method: 'POST', headers,
            body: JSON.stringify({yaml: 'signal:\\n  entry: true\\n', kind: 'full', name,
                params: {codes, start: '2026-09-01', end: '2026-09-30'}})
        });
        const data = await resp.json();
        return {status: resp.status, job_id: data.job_id, error: data.error};
    }""", [name, list(codes)])
    assert out["status"] == 200, f"提交失败: {out}"
    return out["job_id"]


def access_fallback_visible(page):
    return page.evaluate(
        "() => document.body.innerText.includes('页面不存在或暂无访问权限')")


with sync_playwright() as p:
    # 等 staging 就绪（最多 30s）
    import time
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/saas/factors", timeout=2)
            break
        except Exception:
            time.sleep(0.5)
    else:
        raise SystemExit("staging 未就绪，见 .tmp/public-beta-ops/server.log")
    browser = p.chromium.launch(headless=True)
    all_errors: dict[str, list[str]] = {}

    def track(page, key):
        all_errors.setdefault(key, [])
        page.on("pageerror", lambda e: all_errors[key].append(str(e)))

    # ---------- 1) 游客/登录（桌面 1280 + 375 不破版） ----------
    ctx_g = browser.new_context(viewport={"width": 1280, "height": 900})
    page_g = ctx_g.new_page()
    track(page_g, "guest")
    page_g.goto(f"{BASE}/saas/", wait_until="networkidle")
    assert page_g.locator("#guest-strip").is_visible(), "游客条应可见"
    page_g.goto(f"{BASE}/saas/new", wait_until="networkidle")
    assert page_g.locator("#nl-text").is_visible()
    assert page_g.locator(".entry-card").count() >= 3, "新建页三入口"
    check_no_overflow(page_g, "guest-new-1280")
    page_g.screenshot(path=str(OUT / "guest-new-1280.png"))
    page_g.set_viewport_size({"width": 375, "height": 812})
    page_g.goto(f"{BASE}/saas/", wait_until="networkidle")
    check_no_overflow(page_g, "guest-home-375")
    page_g.goto(f"{BASE}/saas/new", wait_until="networkidle")
    check_no_overflow(page_g, "guest-new-375")
    page_g.screenshot(path=str(OUT / "guest-new-375.png"))
    record("guest-and-login", guest_strip=True, new_entries=3, m375_no_overflow=True)
    ctx_g.close()

    # ---------- 2) 登录用户：NL 编译 stub + 任务等待/失败恢复 + 结果权限 ----------
    ctx_a = browser.new_context(viewport={"width": 1280, "height": 900})
    page_a = ctx_a.new_page()
    track(page_a, "member")
    page_a.goto(f"{BASE}/saas/new", wait_until="networkidle")
    do_login(page_a, LOGIN_PHONE)
    page_a.goto(f"{BASE}/saas/", wait_until="networkidle")
    assert page_a.locator("#guest-strip").is_hidden(), "登录后游客条隐藏"
    record("login-dashboard", guest_strip_hidden=True)

    # 2a) NL 编译（真实 UI 交互 + stub LLM）
    page_a.goto(f"{BASE}/saas/new", wait_until="networkidle")
    page_a.fill("#nl-text", "MACD 金叉买入，死叉卖出")
    page_a.click("#nl-compile")
    page_a.wait_for_selector("#nl-result.ok", timeout=30000)
    assert "编译成功" in page_a.locator("#nl-status").text_content()
    yaml_preview = page_a.locator("#yaml-editor").input_value()
    assert "experiment" in yaml_preview and "entry" in yaml_preview, yaml_preview[:200]
    page_a.screenshot(path=str(OUT / "nl-compile-1280.png"))
    # 同描述第二次：API 层 cache_hit=true（命中不调用 LLM）
    token = page_a.evaluate("() => localStorage.getItem('saas_token')")
    _, c1 = api_post("/api/saas/nl/compile", {"description": "KDJ 低于 20 买入，高于 80 卖出"}, token)
    _, c2 = api_post("/api/saas/nl/compile", {"description": "KDJ  低于 20 买入，高于 80 卖出 "}, token)
    assert c1.get("ok") and c1.get("cache_hit") is False, c1
    assert c2.get("ok") and c2.get("cache_hit") is True, c2
    assert c1.get("yaml") == c2.get("yaml")
    record("nl-compile-stub", ui_compile_ok=True, api_first_cache_hit=False,
           api_second_cache_hit=True, yaml_identical=True)

    # 2b) 任务等待（queued + worker 离线提示）→ 失败恢复（真实失败原因 + 重跑入口）
    job_fail = submit_job(page_a, "失败恢复验收任务")
    page_a.goto(f"{BASE}/saas/jobs/{job_fail}", wait_until="networkidle")
    page_a.wait_for_selector("#job-badge", timeout=20000)
    note = page_a.locator("#job-status-note").text_content()
    assert "排队中" in note, note
    extra = page_a.locator("#job-status-extra").text_content()
    assert "已等待" in extra, extra
    page_a.screenshot(path=str(OUT / "job-queued-1280.png"))
    # worker 协议：claim → fail（engine_error，不可重试）。seed 里另有更旧的游客
    # queued 任务，claim 按最旧优先，故循环直到认领到本次任务。
    for _ in range(6):
        st, claim = worker_post("/api/worker/jobs/claim",
                                {"worker_id": "audit-w", "wait_seconds": 1})
        assert st == 200, claim
        if (claim.get("job") or {}).get("id") == job_fail:
            break
    else:
        raise SystemExit("未能认领到目标任务")
    st, fail_body = worker_post(f"/api/worker/jobs/{job_fail}/fail", {
        "worker_id": "audit-w", "error_class": "engine_error",
        "error_message": "回测引擎内部错误（验收模拟）", "retryable": False})
    assert st == 200 and fail_body.get("status") == "failed", fail_body
    page_a.reload(wait_until="networkidle")
    page_a.wait_for_selector("#job-badge", timeout=20000)
    failed_text = page_a.locator("#status-card").text_content()
    assert "回测引擎内部错误（验收模拟）" in failed_text, failed_text
    rerun = page_a.locator("#btn-rerun")
    assert rerun.is_visible() and "重新回测" in rerun.text_content(), rerun.text_content()
    assert "strategy=" in (rerun.get_attribute("href") or "")
    page_a.screenshot(path=str(OUT / "job-failed-1280.png"))
    record("job-wait-and-failure-recovery", queued_hint=True,
           failed_message_shown=True)

    # 2c) 结果只读与权限：本人完成 → 匿名 → 他人
    jobs = json.loads(subprocess.run(
        ["psql", f"postgresql:///{DB}", "-tAc",
         "SELECT j.id FROM jobs j JOIN strategies s ON s.id = j.strategy_id "
         "WHERE s.name = '本人策略' AND j.status = 'completed' ORDER BY j.id LIMIT 1"],
        check=True, capture_output=True, text=True).stdout.strip())
    page_a.goto(f"{BASE}/saas/jobs/{jobs}", wait_until="networkidle")
    page_a.wait_for_selector("#result-area:not(.hidden)", timeout=20000)
    assert page_a.locator("#metric-strip .metric-card").count() >= 5
    page_a.screenshot(path=str(OUT / "result-owner-1280.png"))
    ctx_anon = browser.new_context(viewport={"width": 1280, "height": 900})
    page_anon = ctx_anon.new_page()
    track(page_anon, "anon")
    page_anon.goto(f"{BASE}/saas/jobs/{jobs}", wait_until="networkidle")
    page_anon.wait_for_timeout(600)
    assert access_fallback_visible(page_anon), "匿名必须统一无权卡"
    ctx_anon.close()
    ctx_o = browser.new_context(viewport={"width": 1280, "height": 900})
    page_o = ctx_o.new_page()
    track(page_o, "other")
    page_o.goto(f"{BASE}/saas/new", wait_until="networkidle")
    do_login(page_o, OTHER_PHONE)
    page_o.goto(f"{BASE}/saas/jobs/{jobs}", wait_until="networkidle")
    page_o.wait_for_timeout(600)
    assert access_fallback_visible(page_o), "他人必须统一无权卡"
    ctx_o.close()
    record("result-readonly-and-permission", owner_rendered=True,
           anon_denied=True, other_user_denied=True)

    # ---------- 3) 反馈分类（登录用户） ----------
    page_a.goto(f"{BASE}/saas/feedback", wait_until="networkidle")
    page_a.select_option("#fb-category", "bug")
    page_a.fill("#fb-content", "浏览器验收：分类提交闭环")
    page_a.click("#fb-submit")
    page_a.wait_for_selector("#fb-history-card:not(.hidden)", timeout=10000)
    page_a.wait_for_function(
        "() => document.getElementById('fb-tbody').textContent.includes('浏览器验收：分类提交闭环')",
        timeout=10000)
    row = page_a.locator("#fb-tbody tr").first.text_content()
    assert "问题缺陷" in row and "待处理" in row, row
    page_a.screenshot(path=str(OUT / "feedback-submit-1280.png"))
    record("feedback-category", submitted_category="bug", row_shows_type_and_status=True)

    # ---------- 4) 管理台运营指标（admin） ----------
    ctx_adm = browser.new_context(viewport={"width": 1280, "height": 900})
    page_adm = ctx_adm.new_page()
    track(page_adm, "admin")
    page_adm.goto(f"{BASE}/saas/console", wait_until="networkidle")
    do_login(page_adm, ADMIN_PHONE)
    page_adm.goto(f"{BASE}/saas/console", wait_until="networkidle")
    page_adm.wait_for_selector("#console:not(.hidden)", timeout=20000)
    admin_token = page_adm.evaluate("() => localStorage.getItem('saas_token')")
    page_adm.click("button[data-tab='ops']")
    page_adm.wait_for_selector("#pane-ops:not(.hidden)", timeout=10000)
    page_adm.wait_for_function(
        "() => document.getElementById('ops-nl').textContent.includes('编译次数')",
        timeout=10000)
    for win in ("7d", "30d", "all", "today"):
        page_adm.click(f"#ops-window button[data-win='{win}']")
        page_adm.wait_for_timeout(400)
        text = page_adm.locator("#pane-ops").text_content()
        assert "NaN" not in text and "undefined" not in text, f"窗口 {win} 含异常值: {text[:200]}"
        assert "成功率" in text and "缓存命中率" in text and "平均排队" in text
    # 运营数值合理性：累计窗口应有编译次数与正式回测数
    page_adm.click("#ops-window button[data-win='all']")
    page_adm.wait_for_timeout(400)
    ops_text = page_adm.locator("#pane-ops").text_content()
    assert "编译次数" in ops_text
    page_adm.screenshot(path=str(OUT / "console-ops-1280.png"), full_page=True)
    # 失败原因表（NL 有 missing_factors 事件）
    assert "缺少因子" in ops_text, ops_text[:400]
    # Required Fix 1：不得出现伪转化率（未关联总量的比可 >100%）
    assert "注册 / 游客" not in ops_text, "不得展示未关联总量的比率卡"
    assert "转化率" in ops_text, "转化率卡应显示「—」"
    conv_block = page_adm.locator("#ops-conv").text_content()
    assert "%" not in conv_block, f"转化区不得有百分比: {conv_block}"
    record("console-ops", windows_ok=True, no_nan=True, nl_failure_reason_visible=True,
           no_fake_conversion_ratio=True)

    # 反馈 tab：类型筛选 + 状态流转
    page_adm.click("button[data-tab='feedback']")
    page_adm.wait_for_selector("#pane-feedback:not(.hidden)", timeout=10000)
    page_adm.wait_for_function(
        "() => document.getElementById('feedback-tbody').textContent.includes('登录后结果页打不开')",
        timeout=10000)
    page_adm.click("#feedback-filter button[data-cat='bug']")
    page_adm.wait_for_timeout(400)
    bug_rows = page_adm.locator("#feedback-tbody tr").count()
    assert bug_rows >= 1
    page_adm.click("#feedback-filter button[data-cat='experience']")
    page_adm.wait_for_timeout(400)
    exp_text = page_adm.locator("#feedback-tbody").text_content()
    assert "希望能记住上次的区间" in exp_text
    page_adm.click("#feedback-filter button[data-cat='']")
    page_adm.wait_for_timeout(400)
    # 状态流转：首条 bug（待处理）→ 处理中
    page_adm.click("#feedback-filter button[data-cat='bug']")
    page_adm.wait_for_timeout(400)
    page_adm.locator("#feedback-tbody button[data-fbst='doing']").first.click()
    # 以 API 为准校验状态流转（按钮文案含「处理中」，不能作为等待条件）
    import urllib.request as _u
    for _ in range(20):
        req = _u.Request(BASE + "/api/saas/console/feedback?category=bug",
                         headers={"Authorization": "Bearer " + admin_token})
        with _u.urlopen(req, timeout=10) as resp:
            rows = json.loads(resp.read())["feedback"]
        newest = rows[0]
        if newest["status"] == "doing":
            break
        page_adm.wait_for_timeout(300)
    assert newest["status"] == "doing", newest
    page_adm.wait_for_function(
        "() => document.querySelector('#feedback-tbody .badge').textContent.includes('处理中')",
        timeout=10000)
    page_adm.screenshot(path=str(OUT / "console-feedback-1280.png"))
    record("console-feedback-triage", category_filter_ok=True, status_flow_ok=True)
    ctx_adm.close()

    # ---------- 5) 375 不破版（console ops + feedback） ----------
    # 复用 admin session（同手机号 60s 内重复发码会被限流；session 本身有效）
    ctx_m = browser.new_context(viewport={"width": 375, "height": 812})
    page_m = ctx_m.new_page()
    track(page_m, "m375")
    page_m.goto(f"{BASE}/saas/login", wait_until="networkidle")
    page_m.evaluate("t => localStorage.setItem('saas_token', t)", admin_token)
    page_m.goto(f"{BASE}/saas/console", wait_until="networkidle")
    page_m.wait_for_selector("#console:not(.hidden)", timeout=20000)
    page_m.click("button[data-tab='ops']")
    page_m.wait_for_selector("#pane-ops:not(.hidden)", timeout=10000)
    check_no_overflow(page_m, "console-ops-375")
    page_m.screenshot(path=str(OUT / "console-ops-375.png"), full_page=True)
    page_m.click("button[data-tab='feedback']")
    page_m.wait_for_selector("#pane-feedback:not(.hidden)", timeout=10000)
    check_no_overflow(page_m, "console-feedback-375")
    page_m.screenshot(path=str(OUT / "console-feedback-375.png"), full_page=True)
    record("m375-no-overflow", console_ops=True, console_feedback=True)
    ctx_m.close()

    browser.close()

# ---------- 汇总断言：零 JS error ----------
for key, errs in all_errors.items():
    assert not errs, f"{key} 页面 JS error: {errs}"

(OUT / "browser-evidence.json").write_text(json.dumps({
    "base": BASE, "db": DB, "results": results, "js_errors": all_errors,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"passed": len(results), "js_errors": all_errors}, ensure_ascii=False))
