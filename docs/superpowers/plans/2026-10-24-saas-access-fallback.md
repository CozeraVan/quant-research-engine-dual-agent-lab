# SaaS 统一无权页与加载兜底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 私有任务、不存在任务和无权访问不再停留“加载中”，统一展示无权页；登录后回跳原链接；所有轮询都有终止与恢复路径。

**Architecture:** 后端保留现有匿名 401、登录 404、本人 409 契约。`base.html` 提供统一鉴权错误、无权卡和加载失败卡；job/symbol/records 三处只改展示层状态机。登录 `next` 仅允许本站 `/saas/...` 相对路径，并在 Authing 服务端 session 中暂存。

**Tech Stack:** Flask/Jinja、原生 JavaScript、PostgreSQL、pytest、Node `new Function()` 脚本检查。

## Global Constraints

- 统一文案必须是「页面不存在或暂无访问权限」，不得区分“他人任务”和“任务不存在”。
- 按钮为「登录/注册」「返回首页」；首页去 `/saas/new`；游客附「登录后可查看并管理自己的回测记录」。
- 经典策略 showcase 的匿名/非所有者 GET 只读链路保持可用；`can_generate` 的个股 404 不是无权。
- 500、网络错误、非 JSON 显示「加载失败」+「重试」，不能伪装成无权或空记录。
- queued/leased/running/uploading 连续刷新；failed/expired/canceled/cancelled 立即停止；长任务等待上限只暂停自动刷新，不伪报失败。
- 遵守 `docs/agent/12_UI_STYLE_GUIDE.md`，复用 `.card/.btn-primary/.btn-ghost/.opt`，零新色相零新字体。
- 每次 commit 同步更新 `docs/agent/05_PROGRESS.md`；不重跑任何全量回测。

---

### Task 1: 公共无权卡与安全登录回跳

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/base.html:207-268`
- Modify: `src/quant_research_engine/gui/saas/templates/login.html:8,59-74`
- Modify: `src/quant_research_engine/gui/saas/templates/login_callback.html:29-33`
- Modify: `src/quant_research_engine/gui/saas/app.py`（登录路由与 next 校验）
- Test: `tests/test_gui_saas_pages.py`
- Test: `tests/test_saas_authing.py`

**Interfaces:**
- Produces: `saasLoginUrl(): string`
- Produces: `showAccessFallback(root): void`
- Produces: `showLoadFailure(root, retryFn): void`
- Produces: `apiFetch(url, {redirectOn401:false})`，401 Error 带 `status=401`
- Produces: `_safe_saas_next(value) -> str`，仅返回安全 `/saas/...` 或 `/saas/`

- [ ] **Step 1: 写失败测试**

在页面测试断言公共 helper 和登录 next 存在；在 Authing 测试加入：

```python
@pytest.mark.parametrize("raw,expected", [
    ("/saas/jobs/78?x=1#risk", "/saas/jobs/78?x=1#risk"),
    ("https://evil.example/saas/jobs/78", "/saas/"),
    ("//evil.example/saas/jobs/78", "/saas/"),
    ("/%5c%5cevil.example", "/saas/"),
    ("/other", "/saas/"),
])
def test_safe_next(raw, expected):
    assert _safe_saas_next(raw) == expected
```

另测 `/saas/login?next=/saas/jobs/78%3Fx%3D1%23risk` 的登录页包含 next，邮箱登录 JS 不再写死 `/saas/`；Authing 授权和 callback 使用服务端暂存的 next。

- [ ] **Step 2: 运行测试确认 RED**

Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas_pages.py tests/test_saas_authing.py -q`
Expected: 因 `_safe_saas_next`、公共 helper 或 next 传递尚不存在而失败。

- [ ] **Step 3: 实现 next 校验**

```python
def _safe_saas_next(value: Any) -> str:
    from urllib.parse import urlsplit
    raw = str(value or "").strip()
    if not raw or "\\" in raw or raw.startswith("//"):
        return "/saas/"
    parsed = urlsplit(raw)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/saas/"):
        return "/saas/"
    return raw
```

`/saas/login` 将 `_safe_saas_next(request.args.get("next"))` 传给模板；`/saas/login/authing` 将其写入 `session["authing_next"]`；callback `session.pop("authing_next", "/saas/")` 后再次校验并传给 `login_callback.html`。

- [ ] **Step 4: 实现公共前端 helper**

```javascript
function saasLoginUrl(){
  const next = location.pathname + location.search + location.hash;
  return '/saas/login?next=' + encodeURIComponent(next);
}
async function apiFetch(url, opts){
  opts = opts || {};
  const redirectOn401 = opts.redirectOn401 !== false;
  delete opts.redirectOn401;
  opts.headers = Object.assign({}, opts.headers, {'Authorization': 'Bearer ' + saasToken()});
  if (opts.json !== undefined){ opts.method = opts.method || 'POST'; opts.headers['Content-Type']='application/json'; opts.body = JSON.stringify(opts.json); delete opts.json; }
  const resp = await fetch(url, opts);
  if (resp.status === 401){
    if (saasToken()){
      localStorage.removeItem(SAAS_TOKEN_KEY);
      if (redirectOn401) location.href = saasLoginUrl();
    }
    const error = new Error('unauthorized'); error.status = 401; throw error;
  }
  return resp;
}
function requireLogin(){ if (!SAAS_BYPASS && !saasToken()) location.href = saasLoginUrl(); }
```

`showAccessFallback(root)` 用 DOM 创建 `.card`，标题为统一文案，按钮链接分别为 `saasLoginUrl()` 和 `/saas/new`；`showLoadFailure(root, retryFn)` 显示「加载失败，请稍后重试」和重试按钮。两者清空目标 root 的加载态。

- [ ] **Step 5: 登录模板接入并验证**

`login.html` 注入 `LOGIN_NEXT`，邮箱登录成功 `location.href = LOGIN_NEXT`；Authing 链接携带安全 next；callback 用 `location.replace(NEXT)`。运行 Step 2 命令并 node 检查模板 script，Expected: 全绿。

---

### Task 2: job 详情状态机与 showcase 严格只读

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/job.html:733-798,859-867`
- Modify: `src/quant_research_engine/gui/saas/app.py:3319-3326`（showcase 写操作守护）
- Test: `tests/test_gui_saas_pages.py`
- Test: `tests/test_gui_saas.py`

**Interfaces:**
- Consumes: Task 1 的 `apiFetch`、`showAccessFallback`、`showLoadFailure`
- Produces: 单一 job 轮询控制器，401/404 统一无权、终态停止、异常可重试

- [ ] **Step 1: 写失败测试**

页面测试断言 `redirectOn401:false`、统一兜底、失败/取消/超时终态集合、轮询上限、`if (jobData.readonly) return`。后端测试新增：匿名 showcase 可 GET 个股详情，但 POST `symbols/<code>/generate` 返回 403 且不创建任务。

- [ ] **Step 2: 运行测试确认 RED**

Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas_pages.py tests/test_gui_saas.py -q`
Expected: 新增断言失败。

- [ ] **Step 3: 重构 poll 的异常与终态**

主资源请求使用 `{redirectOn401:false}`。401/404 调 `showAccessFallback(document.querySelector('.container'))`，只替换页面主内容，不销毁公共导航与脚本；其他 HTTP/JSON/网络错误显示失败卡并允许重试。状态集合必须为：

```javascript
const ACTIVE = new Set(['queued','leased','running','uploading']);
const TERMINAL = new Set(['failed','expired','canceled','cancelled']);
```

ACTIVE 每 5 秒刷新，连续异常最多 3 次，活跃等待最多 5 分钟；到期显示「已暂停自动刷新」+「重试」，重试创建新 timer 前清除旧 timer。`tag-analysis` 404 继续按无归因处理。

- [ ] **Step 4: 修复 showcase 写边界**

`initResultActions` 首行后增加：

```javascript
if (jobData.readonly) return;
```

`api_symbol_detail_generate` 在 `_require_completed_result` 成功后增加：

```python
if getattr(g, "showcase_readonly", False):
    return jsonify({"ok": False, "error": "经典策略为只读展示"}), 403
```

- [ ] **Step 5: 验证**

Run Step 2 命令与 Node 模板脚本解析。Expected: 全绿；公开 showcase GET 行为不变。

---

### Task 3: 个股详情及按需生成轮询兜底

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/symbol.html:87-154`
- Test: `tests/test_gui_saas_pages.py`

**Interfaces:**
- Consumes: Task 1 公共 helper；保留 `can_generate` 响应契约
- Produces: 主详情与生成状态共用有限轮询，无永久“生成中”

- [ ] **Step 1: 写失败测试**

断言主详情和 gen-status 均使用 `redirectOn401:false`；`can_generate` 分支在通用 404 无权分支之前；ready/failed/none/401/404 都停止；生成失败恢复按钮。

- [ ] **Step 2: 运行测试确认 RED**

Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas_pages.py -q`
Expected: 新断言失败。

- [ ] **Step 3: 实现详情与生成状态机**

主请求捕获 401/404 后显示无权卡；只有 `resp.status===404 && data.can_generate` 进入生成按钮分支。生成请求失败恢复按钮与文案。gen-status 仅 ready 继续 `load()`；failed/none/unknown 显示失败；401/404 显示无权；网络错误最多连续 3 次，总等待最多 5 分钟，并提供重试。

- [ ] **Step 4: 验证**

Run Step 2 命令和 Node 模板解析。Expected: 全绿；正常 `can_generate` 流程不回归。

---

### Task 4: 回测记录页无权/空态/轮询收口

**Files:**
- Modify: `src/quant_research_engine/gui/saas/templates/_records_scripts.html:1-200`
- Modify: `src/quant_research_engine/gui/saas/templates/profile.html:37-60`
- Modify: `src/quant_research_engine/gui/saas/templates/new.html:835-863`（仅非 2xx fail-fast 与登录 URL）
- Test: `tests/test_gui_saas_pages.py`

**Interfaces:**
- Consumes: Task 1 公共 helper
- Produces: 记录页首次鉴权成功后加载其他模块；200+ok+空数组才是空记录

- [ ] **Step 1: 写失败测试**

断言记录脚本不再顶层 `requireLogin()`，401 显示统一无权卡，500 不进入空记录，只有单一刷新 timer；`new.html` 注册链接使用 `saasLoginUrl()`，pollJob 检查 `resp.ok && d.ok && d.job`。

- [ ] **Step 2: 运行测试确认 RED**

Run: `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas_pages.py -q`
Expected: 新断言失败。

- [ ] **Step 3: 实现记录页状态收口**

移除顶层 `requireLogin()`；`/api/results` 用 `redirectOn401:false`。401/404 显示无权；其他失败显示加载失败；仅成功且 `items=[]` 显示「还没有回测记录」。首次成功后再加载策略库/因子申请。每次 `load()` 清旧 timer，活跃列表刷新到期暂停，点击手动刷新可恢复。`profile.html` 的 `/api/saas/me` 失败不得先触发旧跳登录逻辑。

- [ ] **Step 4: 新建页小修与验证**

注册按钮改 `saasLoginUrl()`；`pollJob` 对非 2xx 或缺 `job` 立即报错，不重写既有 80 次上限。运行测试和 Node 解析，Expected: 全绿。

---

### Task 5: 全量回归、长期文档、提交部署

**Files:**
- Modify: `docs/agent/04_TASK_HANDOFF.md`
- Modify: `docs/agent/05_PROGRESS.md`
- Modify: `docs/agent/09_CODING_HANDOFF.md`
- Modify: `docs/agent/10_REVIEW_REPORT.md`
- Modify: `docs/agent/11_AGENT_STATE.md`

- [ ] **Step 1: 全量相关回归**

Run:

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py -q
```

Expected: 全绿，既有匿名 401/登录 404/本人 409 测试不变。

- [ ] **Step 2: 实机验证清单**

用游客和登录用户分别检查不存在任务、他人任务、对应个股和记录页；邮箱与 Authing 回跳；showcase 公开只读；`can_generate`；任务终态与重试。任何场景不得无限转圈。

- [ ] **Step 3: 文档与最终检查**

记录实现、验证、遗留项，执行：

```bash
bash scripts/check-progress-docs.sh
bash scripts/git-finalize-check.sh
git diff --check
```

- [ ] **Step 4: 提交与部署**

```bash
git add -A
git commit -m "fix(saas): 统一无权页、登录回跳与轮询加载兜底"
git push
ssh -i ~/.ssh/aguhuice_ed25519 root@47.119.127.40 \
  "cd /srv/aguhuice/qre && git pull --ff-only && systemctl restart qre-saas"
```

确认 ECS HEAD、服务 active，线上 401/404 页面最终显示统一无权卡。
