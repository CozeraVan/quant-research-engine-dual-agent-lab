"""QRE-SAAS-004 SaaS 前端页面测试。

页面路由 200 + 关键元素存在；/api/saas/nl/compile 与 /api/saas/factors
在 saas app 中可用（LLM 层 monkeypatch nl_compiler.call_llm 为固定 YAML，
与既有 test_gui_nl_compiler.py 的 stub 思路一致——不触真实 DeepSeek）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

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


_JOB_JS_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function el(){
  return {
    children: [], childNodes: [], style: {}, className: '', textContent: '', innerHTML: '',
    disabled: false, dataset: {}, listeners: {},
    classList: {add(){}, remove(){}, toggle(){}, contains(){ return false; }},
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){ (this.listeners[type] ||= []).push(fn); },
    setAttribute(name, value){ this[name] = String(value); },
    removeAttribute(name){ delete this[name]; },
    querySelectorAll(){ return []; },
  };
}
function response(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
  }};
}
function jobDeferred(){
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}
function jobPendingBody(status, onBody){
  return {status, ok: status >= 200 && status < 300, json(){
    if (onBody) onBody();
    return new Promise(() => {});
  }};
}
function jobPendingFetch(options){
  return new Promise(() => {});
}
function createHarness(fetchImpl){
  const root = el();
  root.childNodes = [el()];
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = el()); }});
  const calls = {access: 0, failure: 0, attribution: 0, requests: []};
  const timers = new Map();
  const windowListeners = {};
  let nextTimer = 1;
  let now = 1000;
  const document = {
    querySelector(selector){
      if (selector === '.container') return root;
      if (selector === '.container .card') return root.children[root.children.length - 1];
      if (selector.startsWith('input[name=sig-scope]:checked')) return Object.assign(el(), {value: 'last_run_universe'});
      return null;
    },
    querySelectorAll(){ return []; },
    getElementById(id){ return elements[id]; },
    createElement(){ return el(); },
  };
  const window = {
    addEventListener(type, fn){ (windowListeners[type] ||= []).push(fn); },
  };
  const context = vm.createContext({
    console, document, window, JOB_ID: 1, STATUS_LABEL: {}, SAAS_BYPASS: false, AbortController,
    MAX_ACTIVE_WAIT_MS: 300000,
    Date: {now(){ return now; }},
    location: {search: ''}, URLSearchParams,
    // P1 只读分享：URL 无 share token 时透传（token 传播由
    // test_saas_access_hardening 的专用 harness 覆盖）
    shareUrl(url){ return url; }, shareSuffix(){ return ''; }, initShareButton(){},
    requestAnimationFrame(fn){ return fn(); },
    saasToken(){ return 'token'; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(el()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(el()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderMeta(){}, renderStrategyInfo(){}, renderMetrics(){}, renderMain(){}, empty(){},
    renderContract(){},
    initReplay(){}, initResultActions(){}, renderFees(){}, loadRisk(){}, renderRisk(){},
    renderAttribution(){ calls.attribution += 1; },
    mountReplay(){ return {destroy(){}}; },
  });
  return {
    context, calls, timers, root, elements, windowListeners,
    setNow(value){ now = value; },
    listenerCount(id, type){ return (elements[id].listeners[type] || []).length; },
    async runNextTimer(){
      const entry = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(entry, '必须存在可执行的 timeout');
      timers.delete(entry[0]);
      now = Math.max(now, entry[1].at);
      return entry[1].fn();
    },
  };
}
"""


def _run_job_js(html: str, source_pattern: str, scenario: str, prefix_pattern: str | None = None) -> None:
    match = re.search(source_pattern, html, re.S)
    assert match, "未找到待测模板脚本"
    prefix = re.search(prefix_pattern, html, re.S) if prefix_pattern else None
    if prefix_pattern:
        assert prefix, "未找到待测模板前置脚本"
    source = (prefix.group(1) if prefix else "") + match.group(1)
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    script = _JOB_JS_HARNESS + "\nconst source = " + json.dumps(source) + ";\n" + scenario
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


_RECORDS_JS_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function recordsEl(){
  return {
    children: [], childNodes: [], style: {}, className: '', textContent: '', innerHTML: '',
    disabled: false, dataset: {}, listeners: {},
    classList: {add(){}, remove(){}, toggle(){}},
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){ this.listeners[type] = fn; },
    querySelectorAll(){ return []; },
  };
}
function recordsText(node){
  return String(node.innerHTML || '') + String(node.textContent || '') + (node.children || []).map(recordsText).join('');
}
function recordsResponse(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
  }};
}
function recordsDeferred(){
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}
function recordsPendingBody(status, onBody){
  return {status, ok: status >= 200 && status < 300, json(){
    if (onBody) onBody();
    return new Promise(() => {});
  }};
}
function createRecordsHarness(fetchImpl){
  const root = recordsEl();
  root.childNodes = [recordsEl()];
  root.children = [...root.childNodes];
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = recordsEl()); }});
  const calls = {access: 0, failure: 0, login: 0, requests: []};
  const timers = new Map();
  let nextTimer = 1;
  let now = 1000;
  const document = {
    querySelector(selector){ return selector === '.wrap' ? root : null; },
    querySelectorAll(){ return []; },
    getElementById(id){ return elements[id]; },
    createElement(){ return recordsEl(); },
  };
  const context = vm.createContext({
    console, document, STATUS_LABEL: {}, SAAS_BYPASS: false, AbortController,
    Date: {now(){ return now; }},
    location: {href: ''},
    requireLogin(){ calls.login += 1; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(recordsEl()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(recordsEl()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
  });
  return {
    context, calls, timers, root, elements,
    setNow(value){ now = value; },
    pollTimerCount(){ return [...timers.values()].filter(timer => timer.at - now === 5000).length; },
    async runNextTimer(){
      const entry = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(entry, '必须存在可执行的 timeout');
      timers.delete(entry[0]);
      now = Math.max(now, entry[1].at);
      return entry[1].fn();
    },
  };
}
"""


def _run_records_js(html: str, scenario: str) -> None:
    scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
    source = next(script for script in scripts if "function loadFactorRequests()" in script)
    source = source.replace("\nload();", "\nrecordsInitialLoad = load();", 1)
    source = source.replace("\nloadProfile();", "\nprofileInitialLoad = loadProfile();", 1)
    assert "recordsInitialLoad = load();" in source
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    script = _RECORDS_JS_HARNESS + "\nconst source = " + json.dumps(source) + ";\n" + scenario
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


class TestRecordsAccessStateMachine:
    def test_records_http_json_and_empty_states(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        records_script = next(
            script for script in re.findall(r"<script>([\s\S]*?)</script>", html)
            if "function loadFactorRequests()" in script
        )
        assert not re.search(r"^requireLogin\(\);", records_script, re.M)
        _run_records_js(html, r"""
function recordsFetch(listResponse){
  return async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    return listResponse;
  };
}
async function settle(h){
  await vm.runInContext('recordsInitialLoad.catch(() => {})', h.context);
}
(async () => {
  for (const status of [401, 404]){
    const h = createRecordsHarness(recordsFetch(recordsResponse(status, {ok: false})));
    vm.runInContext(source, h.context);
    await settle(h);
    assert.equal(h.calls.access, 1, status + ' 必须显示统一无权卡');
    assert.equal(h.calls.failure, 0);
    assert.equal(h.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), false);
    assert.equal(h.calls.requests.filter(r => r.url.startsWith('/api/results?')).length, 1);
    assert.equal(h.calls.requests.filter(r => r.url.startsWith('/api/results?'))[0].options.redirectOn401, false);
  }
  for (const listResponse of [
    recordsResponse(500, {ok: false}),
    recordsResponse(200, {ok: false, items: []}),
    recordsResponse(200, {ok: true}),
    recordsResponse(201, {ok: true, items: []}),
    recordsResponse(200, null, true),
  ]){
    const h = createRecordsHarness(recordsFetch(listResponse));
    vm.runInContext(source, h.context);
    await settle(h);
    assert.equal(h.calls.access, 0);
    assert.equal(h.calls.failure, 1, '非 200+ok+items 响应必须显示加载失败');
    assert.equal(h.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), false, '失败不得冒充空记录');
    assert.equal(h.calls.requests.some(r => r.url === '/api/saas/strategies'), false);
    assert.equal(h.calls.requests.some(r => r.url === '/api/saas/factor-requests'), false);
  }
  const empty = createRecordsHarness(recordsFetch(recordsResponse(200, {ok: true, items: [], total: 0})));
  vm.runInContext(source, empty.context);
  await settle(empty);
  assert.equal(empty.calls.access, 0);
  assert.equal(empty.calls.failure, 0);
  assert.equal(empty.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), true);
  assert.deepEqual(empty.calls.requests.slice(0, 2).map(r => r.url.startsWith('/api/results?') ? 'results' : r.url), ['/api/saas/me', 'results']);
  assert.equal(empty.calls.requests.filter(r => r.url === '/api/saas/strategies').length, 1, '首次成功后才加载策略库');
  assert.equal(empty.calls.requests.filter(r => r.url === '/api/saas/factor-requests').length, 1, '首次成功后才加载因子申请');
  await vm.runInContext('load()', empty.context);
  assert.equal(empty.calls.requests.filter(r => r.url === '/api/saas/strategies').length, 1, '后续刷新不得重复初始化策略库');
  assert.equal(empty.calls.requests.filter(r => r.url === '/api/saas/factor-requests').length, 1);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_rows_hide_contract_label(self, client):
        """结果合同仍可由 API 返回，但个人记录行只显示任务状态。"""
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
(async () => {
  const items = [
    {job_id: 11, status: 'completed', strategy_name: '新结果', excess_return: 0.1,
     result_contract: {verified: true, label: '已验证口径', version: '2026-10-25.1',
                       tip: '收益曲线 = 日收益累乘；总收益率 = 初始资金加权总收益'}},
    {job_id: 74, status: 'completed', strategy_name: '旧结果', excess_return: null,
     result_contract: {verified: false, label: '旧口径·未验证', version: 'legacy',
                       tip: '收益曲线 = 日收益累乘；总收益率 = 初始资金加权总收益'}},
    {job_id: 12, status: 'running', strategy_name: '在跑'},
  ];
  const h = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    return recordsResponse(200, {ok: true, total: items.length, items});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('recordsInitialLoad.catch(() => {})', h.context);
  const body = recordsText(h.elements['jobs-tbody']);
  assert.ok(!body.includes('已验证口径'), '记录行不得显示合同验证标签');
  assert.ok(!body.includes('旧口径·未验证'), '记录行不得显示新旧口径标签');
  assert.ok(body.includes('badge ok') && body.includes('completed'), '任务状态徽章仍需保留');
  assert.equal(h.calls.access, 0);
  assert.equal(h.calls.failure, 0);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_single_timer_pause_and_manual_resume(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
(async () => {
  const h = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    return recordsResponse(200, {ok: true, total: 1, items: [{job_id: 1, status: 'running'}]});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('recordsInitialLoad', h.context);
  assert.equal(h.pollTimerCount(), 1);
  await vm.runInContext('load()', h.context);
  await vm.runInContext('load()', h.context);
  assert.equal(h.pollTimerCount(), 1, '重复 load 也只能保留一个 timer');
  h.setNow(1000 + 5 * 60 * 1000);
  await vm.runInContext('load()', h.context);
  assert.equal(h.pollTimerCount(), 0, '活跃刷新到期后必须暂停');
  assert.equal(vm.runInContext("document.querySelector('.wrap').children[0].children[0].textContent", h.context), '已暂停自动刷新');
  await h.elements['btn-reload'].listeners.click();
  assert.equal(h.pollTimerCount(), 1, '手动刷新必须恢复自动刷新');
  assert.equal(h.calls.failure, 0, '暂停不得伪报加载失败');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_filter_empty_is_distinct_from_no_records(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
(async () => {
  const h = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    return recordsResponse(200, {ok: true, total: 1, items: [{job_id: 1, status: 'completed', strategy_name: 'alpha'}]});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('recordsInitialLoad', h.context);
  h.elements['recs-filter'].value = 'missing';
  await h.elements['recs-filter'].listeners.input.call(h.elements['recs-filter']);
  assert.equal(h.elements['jobs-tbody'].innerHTML.includes('当前筛选无匹配结果'), true);
  assert.equal(h.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), false);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_main_body_pending_times_out_and_retries(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
(async () => {
  const started = recordsDeferred();
  let blocked = true;
  const h = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    if (blocked) return recordsPendingBody(200, started.resolve);
    return recordsResponse(200, {ok: true, items: [], total: 0});
  });
  vm.runInContext(source, h.context);
  const pending = vm.runInContext('recordsInitialLoad', h.context);
  await started.promise;
  await h.runNextTimer();
  await pending;
  assert.equal(h.calls.failure, 1, '主列表 body pending 必须超时显示失败');
  assert.equal(typeof h.calls.retry, 'function');
  blocked = false;
  await h.calls.retry();
  assert.equal(h.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), true);
  assert.equal(h.calls.requests.filter(r => r.url.startsWith('/api/results?')).length, 2);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_latest_load_epoch_controls_render_failure_and_timer(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
function success(items){ return recordsResponse(200, {ok: true, items, total: items.length}); }
function running(){ return [{job_id: 1, status: 'running', strategy_name: 'old'}]; }
(async () => {
  const first = recordsDeferred(), second = recordsDeferred();
  let notifyFirst;
  const firstStarted = new Promise(resolve => { notifyFirst = resolve; });
  let round = 0;
  const latest = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    round += 1;
    if (round === 1){ notifyFirst(); return first.promise; }
    return second.promise;
  });
  vm.runInContext(source, latest.context);
  const oldLoad = vm.runInContext('recordsInitialLoad', latest.context);
  await firstStarted;
  const newLoad = vm.runInContext('load()', latest.context);
  second.resolve(success([]));
  await newLoad;
  first.resolve(success(running()));
  await oldLoad;
  for (let i = 0; i < 12; i += 1) await Promise.resolve();
  assert.equal(latest.elements['jobs-tbody'].innerHTML.includes('还没有回测记录'), true, '旧响应不能覆盖新空态');
  assert.equal(latest.timers.size, 0, '旧活跃响应不能在新终态后调度');

  const slow = recordsDeferred();
  let notifySlow;
  const slowStarted = new Promise(resolve => { notifySlow = resolve; });
  let calls = 0;
  const failure = createRecordsHarness(async url => {
    if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
    if (url === '/api/saas/strategies') return recordsResponse(200, {ok: true, strategies: []});
    if (url === '/api/saas/factor-requests') return recordsResponse(200, {ok: true, requests: []});
    calls += 1;
    if (calls === 1){ notifySlow(); return slow.promise; }
    return recordsResponse(500, {ok: false});
  });
  vm.runInContext(source, failure.context);
  const stale = vm.runInContext('recordsInitialLoad', failure.context);
  await slowStarted;
  await vm.runInContext('load()', failure.context);
  assert.equal(failure.calls.failure, 1);
  slow.resolve(success(running()));
  await stale;
  assert.equal(failure.calls.failure, 1, '旧响应不能清除新失败');
  assert.equal(failure.timers.size, 0, '旧响应不能在失败后重启 timer');
  assert.equal(failure.calls.requests.some(r => r.url === '/api/saas/strategies'), false, '作废旧成功不能初始化附属模块');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_records_auxiliary_http_failures_and_retry(self, client):
        html = client.get("/saas/").get_data(as_text=True)
        _run_records_js(html, r"""
async function flushAux(){ for (let i = 0; i < 12; i += 1) await Promise.resolve(); }
(async () => {
  for (const status of [401, 404]){
    for (const target of ['/api/saas/strategies', '/api/saas/factor-requests']){
      let attempts = 0;
      const h = createRecordsHarness(async url => {
        if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
        if (url.startsWith('/api/results?')) return recordsResponse(200, {ok: true, total: 1, items: [{job_id: 1, status: 'running'}]});
        if (url === target){
          attempts += 1;
          if (attempts === 1) return recordsResponse(status, {ok: false});
        }
        return recordsResponse(200, {ok: true, strategies: [], requests: []});
      });
      vm.runInContext(source, h.context);
      await vm.runInContext('recordsInitialLoad', h.context);
      const mainChildren = [...h.root.children];
      const mainEpoch = vm.runInContext('recordsLoadEpoch', h.context);
      const mainRequest = h.calls.requests.find(r => r.url.startsWith('/api/results?'));
      await flushAux();
      const bodyId = target.endsWith('strategies') ? 'strat-tbody' : 'factor-req-tbody';
      assert.equal(h.calls.access, 0, target + ' 不得调用整页无权 helper');
      assert.ok(h.root.children.every((node, index) => node === mainChildren[index]), '附属无权必须保留主列表 DOM');
      assert.equal(vm.runInContext('recordsLoadEpoch', h.context), mainEpoch, '附属无权不得改变主 epoch');
      assert.equal(mainRequest.options.signal.aborted, false, '附属无权不得 abort 主请求');
      assert.equal(h.pollTimerCount(), 1, '附属无权不得停止主轮询');
      assert.equal(recordsText(h.elements[bodyId]).includes('页面不存在或暂无访问权限'), true, '附属无权必须模块内提示');
      const retry = h.elements[bodyId].children[0].children[0].children[1];
      await retry.listeners.click();
      assert.equal(attempts, 2, '模块内重试必须重新请求');
      assert.equal(recordsText(h.elements[bodyId]).includes('暂无'), true, '模块重试成功必须恢复内容');
      assert.equal(h.pollTimerCount(), 1, '模块重试不得影响主轮询');
    }
  }
  for (const target of ['/api/saas/strategies', '/api/saas/factor-requests']){
    let attempts = 0;
    const h = createRecordsHarness(async url => {
      if (url === '/api/saas/me') return recordsResponse(200, {ok: true, user: {}});
      if (url.startsWith('/api/results?')) return recordsResponse(200, {ok: true, items: [], total: 0});
      if (url === target){
        attempts += 1;
        if (attempts === 1) return recordsResponse(500, {ok: false});
      }
      return recordsResponse(200, {ok: true, strategies: [], requests: []});
    });
    vm.runInContext(source, h.context);
    await vm.runInContext('recordsInitialLoad', h.context);
    await flushAux();
    const bodyId = target.endsWith('strategies') ? 'strat-tbody' : 'factor-req-tbody';
    assert.equal(recordsText(h.elements[bodyId]).includes('加载失败'), true, target + ' 500 必须显示本模块失败');
    assert.equal(recordsText(h.elements[bodyId]).includes('暂无'), false, '失败不得冒充空模块');
    await vm.runInContext('load()', h.context);
    await flushAux();
    assert.equal(attempts, 2, '失败的附属模块必须在后续主列表成功时重试');
    assert.equal(h.elements[bodyId].innerHTML.includes('暂无'), true);
  }
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_profile_body_pending_times_out_and_retries(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        _run_records_js(html, r"""
(async () => {
  const started = recordsDeferred();
  let blocked = true;
  let meCalls = 0;
  const h = createRecordsHarness(async url => {
    if (url === '/api/saas/me'){
      meCalls += 1;
      if (meCalls === 2 && blocked) return recordsPendingBody(200, started.resolve);
      return recordsResponse(200, {ok: true, user: {email: 'recovered@example.com'}});
    }
    if (url.startsWith('/api/results?')) return recordsResponse(200, {ok: true, items: [], total: 0});
    return recordsResponse(200, {ok: true, strategies: [], requests: []});
  });
  vm.runInContext(source, h.context);
  const pending = vm.runInContext('profileInitialLoad', h.context);
  await started.promise;
  await h.runNextTimer();
  await pending;
  assert.equal(h.calls.failure, 1, 'profile body pending 必须超时显示失败');
  assert.equal(typeof h.calls.retry, 'function');
  blocked = false;
  await h.calls.retry();
  assert.equal(h.elements['pf-account'].textContent, 'recovered@example.com');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_profile_me_disables_legacy_redirect(self, client):
        html = client.get("/saas/profile").get_data(as_text=True)
        profile_script = next(
            script for script in re.findall(r"<script>([\s\S]*?)</script>", html)
            if "async function loadProfile()" in script
        )
        load_profile = re.search(r"async function loadProfile\(\)\{.*?\n\}", profile_script, re.S)
        assert load_profile
        assert "recordsRequestWithTimeout('/api/saas/me'" in load_profile.group(0)
        assert "redirectOn401:false" in load_profile.group(0)
        assert "showLoadFailure(document.getElementById('profile-card'), retryProfile)" in load_profile.group(0)

    def test_new_login_url_and_poll_job_fail_fast(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert "$('#guest-register').addEventListener('click', () => { location.href = saasLoginUrl(); });" in html
        assert "for (let i = 0; i < 80; i++)" in html
        match = re.search(r"(const NEW_REQUEST_TIMEOUT_MS[\s\S]*?async function pollJob\(jobId\)\{.*?\n\})(?=\nfunction isGuest)", html, re.S)
        assert match
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const calls = [];
const timers = new Map();
let nextTimer = 1;
const context = vm.createContext({
  AbortController,
  setTimeout(fn, delay){
    const id = nextTimer++;
    if (delay === 3000){ fn(); return id; }
    timers.set(id, fn);
    return id;
  },
  clearTimeout(id){ timers.delete(id); },
  async runNextTimer(){
    const entry = timers.entries().next().value;
    assert.ok(entry, '请求必须存在 timeout');
    timers.delete(entry[0]);
    return entry[1]();
  },
  apiFetch(url){ calls.push(url); return context.responses.shift(); },
  responses: [],
  LabUI: {waitMask: {show(){}, update(){}, hide(){}}},
});
function response(status, data){
  return Promise.resolve({status, ok: status >= 200 && status < 300, json: async () => data});
}
"""
        scenario = r"""
(async () => {
  for (const responses of [
    [Promise.resolve({status: 500, ok: false, json: async () => { throw new Error('非 2xx 不得解析 JSON'); }})],
    [response(500, {ok: false, error: 'down'})],
    [response(200, {ok: true})],
    [response(200, {ok: false, job: {status: 'running'}})],
  ]){
    calls.length = 0;
    context.responses = responses;
    await assert.rejects(vm.runInContext('pollJob(7)', context), /HTTP 500|任务状态加载失败/);
    assert.equal(calls.length, 1, '非 2xx、!ok 或缺 job 必须立即 fail-fast');
  }
  calls.length = 0;
  context.responses = [response(200, {ok: true, job: {status: 'expired', error: '租约过期'}})];
  await assert.rejects(vm.runInContext('pollJob(7)', context), /租约过期/);
  assert.equal(calls.length, 1, 'expired 必须立即终态，不得继续轮询');

  calls.length = 0;
  context.responses = [response(200, {ok: true, job: {status: 'completed'}})];
  const job = await vm.runInContext('pollJob(7)', context);
  assert.equal(job.status, 'completed');
  assert.equal(calls.length, 1);

  calls.length = 0;
  context.responses = [
    Promise.resolve({status: 200, ok: true, json(){ return new Promise(() => {}); }}),
    response(200, {ok: true, job: {status: 'running'}}),
    response(200, {ok: true, job: {status: 'completed'}}),
  ];
  const pending = vm.runInContext('pollJob(7)', context);
  await Promise.resolve();
  assert.equal(calls.length, 1, 'body pending 场景必须先发出请求');
  assert.equal(timers.size, 1, 'body pending 时必须保留请求 timeout');
  await context.runNextTimer();
  // 单次 15 秒 AbortError 归为临时状态刷新超时：继续轮询，不判策略失败
  const retriedJob = await pending;
  assert.equal(retriedJob.status, 'completed');
  assert.equal(calls.length, 3, '临时超时后必须继续轮询直到终态');
})().catch(error => { console.error(error); process.exit(1); });
"""
        script = harness + "\nconst source = " + json.dumps(match.group(1)) + ";\nvm.runInContext(source, context);\n" + scenario
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout


_NEW_WAIT_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function response(status, data){
  return Promise.resolve({status, ok: status >= 200 && status < 300, json: async () => data});
}
function createNewWaitHarness(fetchImpl){
  const calls = [];
  const timers = new Map();
  const maskCalls = [];
  let nextTimer = 1;
  const context = vm.createContext({
    AbortController,
    setTimeout(fn, delay){
      const id = nextTimer++;
      if (delay === 3000){ fn(); return id; }
      timers.set(id, fn);
      return id;
    },
    clearTimeout(id){ timers.delete(id); },
    async runNextTimer(){
      const entry = timers.entries().next().value;
      assert.ok(entry, '请求必须存在 timeout');
      timers.delete(entry[0]);
      return entry[1]();
    },
    apiFetch(url, options){ calls.push({url, options}); return fetchImpl(url, options); },
    LabUI: {waitMask: {
      show(opts){ maskCalls.push({op: 'show', opts}); },
      update(opts){ maskCalls.push({op: 'update', opts}); },
      hide(){ maskCalls.push({op: 'hide'}); },
    }},
  });
  return {context, calls, timers, maskCalls};
}
"""


class TestNewPageWaitStates:
    """QRE-SAAS-FIRST-SUCCESS-UX-001：new.html 等待态准确表达排队/离线/超时。"""

    def _run(self, html, scenario):
        match = re.search(
            r"(const NEW_REQUEST_TIMEOUT_MS[\s\S]*?async function pollJob\(jobId[\s\S]*?\n\})"
            r"(?=\nfunction isGuest)", html, re.S)
        assert match, "未找到 new.html 轮询脚本"
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        script = (_NEW_WAIT_HARNESS + "\nconst source = " + json.dumps(match.group(1))
                  + ";\n" + scenario)
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout

    def test_wait_copy_markers_present(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert "排队中，前面还有 " in html
        assert "排队中，等待计算节点领取" in html
        assert "计算节点暂时离线" in html
        assert "任务已保留，恢复后会继续；无需重复提交" in html
        assert "PollTimeoutError" in html
        assert "任务仍在后台执行，请前往任务页查看" in html
        # 真实失败仍写「没跑通」；前台等待超时不得冒充策略失败
        assert "策略在小样本上没跑通" in html

    def test_transient_abort_continues_polling(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const pending = Promise.resolve({status: 200, ok: true, json(){ return new Promise(() => {}); }});
  const queue = [pending, response(200, {ok: true, job: {status: 'running'}}),
                 response(200, {ok: true, job: {status: 'completed'}})];
  const hh = createNewWaitHarness(async () => queue.shift());
  vm.runInContext(source, hh.context);
  const done = vm.runInContext('pollJob(7)', hh.context);
  await Promise.resolve();
  assert.equal(hh.calls.length, 1, 'body pending 场景必须先发出请求');
  await hh.context.runNextTimer();  // 15s 刷新超时 → AbortError
  const job = await done;
  assert.equal(job.status, 'completed');
  assert.equal(hh.calls.length, 3, '单次 AbortError 后必须继续轮询');
  assert.ok(hh.maskCalls.filter(c => c.op === 'update').length >= 2,
    '每次成功轮询都要渲染等待态');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_http_500_and_terminal_fail_fast(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  for (const bad of [response(500, {ok: false}), response(200, {ok: false, job: {}})]) {
    const h = createNewWaitHarness(async () => bad);
    vm.runInContext(source, h.context);
    await assert.rejects(vm.runInContext('pollJob(7)', h.context), /HTTP 500|任务状态加载失败/);
    assert.equal(h.calls.length, 1, 'HTTP 500 / 缺 job 必须 fail-fast');
  }
  // 终态必须带出后端真实 error_message（_job_view 字段），不是固定「任务失败」
  const terminal = createNewWaitHarness(async () =>
    response(200, {ok: true, job: {status: 'failed',
                                   error_message: '策略第 3 行 entry 表达式不合法'}}));
  vm.runInContext(source, terminal.context);
  await assert.rejects(vm.runInContext('pollJob(7)', terminal.context),
                       /策略第 3 行 entry 表达式不合法/);
  assert.equal(terminal.calls.length, 1, '终态必须立即失败');
  // 旧数据无 error_message 时回退通用文案
  const legacy = createNewWaitHarness(async () =>
    response(200, {ok: true, job: {status: 'expired'}}));
  vm.runInContext(source, legacy.context);
  await assert.rejects(vm.runInContext('pollJob(7)', legacy.context), /任务失败/);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_poll_timeout_is_distinct_error_not_strategy_failure(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createNewWaitHarness(async () =>
    response(200, {ok: true, job: {status: 'running', queue_position: 1, worker_online: true}}));
  vm.runInContext(source, h.context);
  let err = null;
  try { await vm.runInContext('pollJob(7)', h.context); } catch (e) { err = e; }
  assert.ok(err, '80 轮后必须抛出独立超时错误');
  assert.equal(err.name, 'PollTimeoutError', '前台等待上限必须是独立错误类型');
  assert.ok(/任务仍在后台执行，请前往任务页查看/.test(err.message), err.message);
  assert.equal(h.calls.length, 80, '必须保留 80 次轮询上限');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_queue_and_offline_copy_rendering(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createNewWaitHarness(async () => undefined);
  vm.runInContext(source, h.context);
  const queued = vm.runInContext(
    "jobWaitStatus({status: 'queued', queue_position: 3, worker_online: true}, 42000)", h.context);
  assert.ok(queued.title.includes('排队中，前面还有 3 个任务'), queued.title);
  assert.ok(queued.meta.includes('42'), queued.meta);
  const zero = vm.runInContext(
    "jobWaitStatus({status: 'queued', queue_position: 0, worker_online: true}, 5000)", h.context);
  assert.ok(zero.title.includes('排队中，等待计算节点领取'), zero.title);
  const offline = vm.runInContext(
    "jobWaitStatus({status: 'queued', queue_position: 0, worker_online: false}, 5000)", h.context);
  assert.ok(offline.title.includes('计算节点暂时离线'), offline.title);
  assert.ok(offline.sub.includes('任务已保留，恢复后会继续'), offline.sub);
  assert.ok(offline.sub.includes('无需重复提交'), offline.sub);
  // 离线提示覆盖全部活跃态（queued/leased/running/uploading），不止 queued/running
  for (const st of ['queued', 'leased', 'running', 'uploading']){
    const s = vm.runInContext(
      "jobWaitStatus({status: '" + st + "', queue_position: 0, worker_online: false}, 5000)",
      h.context);
    assert.ok(s.title.includes('计算节点暂时离线'), st + ' 离线提示缺失: ' + s.title);
    assert.ok(s.sub.includes('无需重复提交'), st);
  }
  // 终态（failed）不读离线提示
  const terminal = vm.runInContext(
    "jobWaitStatus({status: 'failed', worker_online: false}, 5000)", h.context);
  assert.ok(!terminal.title.includes('计算节点暂时离线'), terminal.title);
  const running = vm.runInContext(
    "jobWaitStatus({status: 'running', worker_online: true}, 65000)", h.context);
  assert.ok(running.meta.includes('1 分'), running.meta);
  assert.ok(!JSON.stringify(running).includes('%'), '不得虚构百分比');
  assert.ok(!JSON.stringify(running).includes('预计'), '不得虚构预计完成时间');
  // 渲染入口：一次成功轮询把状态与秒数写进遮罩（meta 独立于 aria-live 文案）
  vm.runInContext(
    "renderJobWait({status: 'queued', queue_position: 2, worker_online: false}, 9000)", h.context);
  const last = h.maskCalls[h.maskCalls.length - 1].opts;
  assert.ok(last.title.includes('计算节点暂时离线'), JSON.stringify(last));
  assert.ok(last.sub.includes('无需重复提交'), JSON.stringify(last));
  assert.ok(last.meta.includes('9'), last.meta);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_pipe_stop_at_is_neutral_not_failure(self, client):
        """前台等待超时（PollTimeoutError）是中性「后台等待中」，不得显示失败红态。"""
        html = client.get("/saas/new").get_data(as_text=True)
        fail_src = re.search(r"(function pipeFailAt\(i, msg\)\{[\s\S]*?\n\})", html, re.S)
        stop_src = re.search(
            r"(function pipeStopAt\(i, msg, linkHref, linkText\)\{[\s\S]*?\n\})", html, re.S)
        assert fail_src and stop_src, "未找到 pipeFailAt/pipeStopAt"
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function makeEl(){
  const e = {children: [], style: {}, classes: new Set(), _text: '', innerHTML: '',
    classList: {add(c){ e.classes.add(c); }, remove(c){ e.classes.delete(c); },
                contains(c){ return e.classes.has(c); }},
    querySelector(){ return e._st || (e._st = makeEl()); }};
  Object.defineProperty(e, 'textContent', {get(){ return e._text; }, set(v){ e._text = v; }});
  return e;
}
const step = makeEl();
const err = makeEl();
const context = vm.createContext({
  $(sel){ return sel.indexOf('pipe-err') >= 0 ? err : step; },
  esc(s){ return String(s == null ? '' : s); },
});
"""
        scenario = r"""
(async () => {
  vm.runInContext(source, context);
  // 对照：真实失败仍走 fail 红态
  vm.runInContext('pipeFailAt(2, "策略在小样本上没跑通：boom")', context);
  assert.ok(step.classes.has('fail'), '真实失败必须保留 fail 态');
  step.classes.delete('fail');
  step.classes.add('doing');
  // 前台等待超时：中性后台等待中——不加 fail、无新色相
  vm.runInContext(
    "pipeStopAt(2, '任务仍在后台执行，请前往任务页查看', '/saas/jobs/9?guest=1', '前往任务页查看进度')",
    context);
  assert.ok(!step.classes.has('fail'), '前台等待超时不得显示失败态');
  assert.ok(!step.classes.has('doing'), '后台等待中不得残留 doing 态');
  assert.equal(step.querySelector('.pipe-st').textContent, '后台等待中');
  assert.equal(err.style.display, 'block');
  assert.ok(err.innerHTML.indexOf('等待超时') >= 0, err.innerHTML);
  assert.ok(err.innerHTML.indexOf('/saas/jobs/9?guest=1') >= 0, '必须提供任务页入口');
  assert.ok(err.innerHTML.indexOf('未提交全量回测') >= 0, '不得自动提交全量');
  assert.ok(err.innerHTML.indexOf('失败') < 0, '超时提示不得写「失败」');
})().catch(error => { console.error(error); process.exit(1); });
"""
        script = (harness + "\nconst source = "
                  + json.dumps(fail_src.group(1) + "\n" + stop_src.group(1)) + ";\n" + scenario)
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout

    def test_create_job_submit_timeout_message(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        match = re.search(r"(async function createJob\(kind\)\{[\s\S]*?\n\})(?=\nfunction isGuest)",
                          html, re.S)
        assert match, "未找到 createJob"
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        harness = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const calls = [];
const timers = new Map();
let nextTimer = 1;
const context = vm.createContext({
  AbortController,
  setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, fn); return id; },
  clearTimeout(id){ timers.delete(id); },
  async runNextTimer(){
    const entry = timers.entries().next().value;
    assert.ok(entry, '提交必须存在 timeout');
    timers.delete(entry[0]);
    return entry[1]();
  },
  apiFetch(url, options){ calls.push({url, options}); return new Promise(() => {}); },
  curEntry(){ return 'yaml'; },
  strategyYaml: 'yaml',
  applyName(s){ return s; },
  collectWizardState(){ return null; },
  buildParams(){ return {}; },
  $(sel){ return {value: ''}; },
});
"""
        scenario = r"""
(async () => {
  vm.runInContext(source, context);
  const pending = vm.runInContext('createJob("smoke")', context);
  await Promise.resolve();
  assert.equal(calls.length, 1, '提交必须先发出请求');
  assert.equal(timers.size, 1, '提交必须带 15 秒超时');
  await context.runNextTimer();
  let err = null;
  try { await pending; } catch (e) { err = e; }
  assert.ok(err, '提交超时必须抛出可读错误');
  assert.ok(/超时/.test(err.message), err.message);
  assert.ok(/重复提交/.test(err.message), err.message);
  assert.equal(calls.length, 1, '超时后不得自动重试提交');
})().catch(error => { console.error(error); process.exit(1); });
"""
        script = harness + "\nconst source = " + json.dumps(match.group(1)) + ";\n" + scenario
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout


_SYMBOL_JS_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function symbolEl(){
  return {
    id: '', children: [], childNodes: [], style: {}, className: '', _textContent: '', innerHTML: '',
    get textContent(){ return this._textContent; },
    set textContent(value){ this._textContent = value; this.children = []; this.childNodes = []; },
    disabled: false, type: '', listeners: {}, listenerCounts: {}, dataset: {},
    classList: {add(){}, remove(){}, contains(){ return false; }},
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){
      this.listeners[type] = fn;
      this.listenerCounts[type] = (this.listenerCounts[type] || 0) + 1;
    },
    insertAdjacentHTML(){},
    remove(){},
  };
}
function response(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
  }};
}
function bodyBarrier(){
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}
function pendingBodyResponse(status, onBody){
  return {status, ok: status >= 200 && status < 300, json(){
    onBody();
    return new Promise(() => {});
  }};
}
function createSymbolHarness(fetchImpl){
  const root = symbolEl();
  root.childNodes = [symbolEl()];
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = symbolEl()); }});
  const calls = {access: 0, failure: 0, requests: [], summaries: [], replay: 0, pause: []};
  const timers = new Map();
  const windowListeners = {};
  let nextTimer = 1;
  let now = 1000;
  const document = {
    querySelector(selector){
      if (selector === '.wrap') return root;
      if (selector === '.wrap .card') return root.children[root.children.length - 1];
      if (selector.startsWith('#')) return elements[selector.slice(1)];
      return null;
    },
    getElementById(id){ return elements[id]; },
    createElement(){ return symbolEl(); },
  };
  const window = {addEventListener(type, fn){ (windowListeners[type] ||= []).push(fn); }};
  const context = vm.createContext({
    console, document, window, JOB_ID: 1, TS_CODE: '000001.SZ', STATUS_LABEL: {}, AbortController,
    Date: {now(){ return now; }},
    $(selector){ return document.querySelector(selector); },
    // P1 只读分享：URL 无 share token 时透传（token 传播由
    // test_saas_access_hardening 的专用 harness 覆盖）
    shareUrl(url){ return url; }, shareSuffix(){ return ''; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(symbolEl()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(symbolEl()); },
    pauseSymbolActivePolling(){ calls.pause.push({}); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderSummary(summary){ calls.summaries.push(summary); }, renderEquity(){}, renderWear(){}, renderRisk(){}, renderKline(){},
    initKlineReplay(){ calls.replay += 1; }, table(){}, pct(){ return ''; },
    esc(s){ return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); },
  });
  return {
    context, calls, timers, root, elements, windowListeners,
    setNow(value){ now = value; },
    async runNextTimer(){
      const entry = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(entry, '必须存在可执行的 timeout');
      timers.delete(entry[0]);
      now = Math.max(now, entry[1].at);
      return entry[1].fn();
    },
    generateButton(){
      return elements['sym-note'].children.find(node => node.id === 'btn-gen') || null;
    },
  };
}
"""


def _run_symbol_script_js(html: str, source_pattern: str, scenario: str) -> None:
    match = re.search(source_pattern, html, re.S)
    assert match, "未找到个股详情脚本"
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    script = _SYMBOL_JS_HARNESS + "\nconst source = " + json.dumps(match.group(1)) + ";\n" + scenario
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _run_symbol_js(html: str, scenario: str) -> None:
    _run_symbol_script_js(
        html,
        r"((?:const SYMBOL_POLL_INTERVAL_MS[\s\S]*?)?async function load\(\)\{.*\})(?=\n\n// FRM-SYMBOL)",
        scenario,
    )


class TestPages:
    def test_symbol_detail_http_json_and_generate_guards(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const canGenerate = createSymbolHarness(async () => response(404, {ok: false, can_generate: true}));
  vm.runInContext(source, canGenerate.context);
  await vm.runInContext('load()', canGenerate.context);
  assert.equal(canGenerate.calls.access, 0, 'can_generate 的业务 404 不是无权');
  assert.equal(canGenerate.calls.failure, 0);
  assert.equal(canGenerate.calls.requests[0].options.redirectOn401, false);
  assert.equal(canGenerate.generateButton().disabled, false);

  const readonly = createSymbolHarness(async () => response(404, {ok: false, can_generate: true, readonly: true}));
  vm.runInContext(source, readonly.context);
  await vm.runInContext('load()', readonly.context);
  assert.equal(readonly.calls.access, 0, 'showcase 只读缺产物不应误报整页无权');
  assert.equal(readonly.calls.failure, 0);
  assert.ok(!readonly.generateButton(), 'showcase 只读不显示注定403的生成按钮：' + JSON.stringify(readonly.elements['sym-note']));
  assert.match(readonly.elements['sym-note'].textContent, /公开经典策略/);

  const plain404 = createSymbolHarness(async () => response(404, {ok: false}));
  vm.runInContext(source, plain404.context);
  await vm.runInContext('load()', plain404.context);
  assert.equal(plain404.calls.access, 1);
  assert.equal(plain404.timers.size, 0);

  const unauthorized = new Error('unauthorized'); unauthorized.status = 401;
  const auth = createSymbolHarness(async () => { throw unauthorized; });
  vm.runInContext(source, auth.context);
  await vm.runInContext('load()', auth.context);
  assert.equal(auth.calls.access, 1);
  assert.equal(auth.calls.failure, 0);

  for (const fetchImpl of [
    async () => response(500, {ok: false}),
    async () => response(200, null, true),
    async () => { throw new Error('offline'); },
  ]){
    const h = createSymbolHarness(fetchImpl);
    vm.runInContext(source, h.context);
    await vm.runInContext('load()', h.context);
    assert.equal(h.calls.access, 0);
    assert.equal(h.calls.failure, 1);
    assert.equal(typeof h.calls.retry, 'function');
  }
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_http_status_precedes_json_for_all_requests(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  for (const status of [401, 404]){
    const main = createSymbolHarness(async () => response(status, null, true));
    vm.runInContext(source, main.context);
    await vm.runInContext('load()', main.context);
    assert.equal(main.calls.access, 1, '主详情非JSON ' + status + ' 必须显示无权卡');
    assert.equal(main.calls.failure, 0);

    const polling = createSymbolHarness(async () => response(status, null, true));
    vm.runInContext(source, polling.context);
    await vm.runInContext('pollGen()', polling.context);
    assert.equal(polling.calls.access, 1, 'gen-status 非JSON ' + status + ' 必须显示无权卡');
    assert.equal(polling.calls.failure, 0);
    assert.equal(polling.timers.size, 0);

    const generating = createSymbolHarness(async () => response(status, null, true));
    vm.runInContext(source, generating.context);
    await vm.runInContext('showGenerate()', generating.context);
    await generating.generateButton().listeners.click();
    assert.equal(generating.calls.access, 1, '生成 POST 非JSON ' + status + ' 必须显示无权卡');
  }
  for (const command of ['load()', 'pollGen()']){
    const h = createSymbolHarness(async () => response(500, null, true));
    vm.runInContext(source, h.context);
    await vm.runInContext(command, h.context);
    assert.equal(h.calls.access, 0);
    assert.equal(h.calls.failure, 1, command + ' 的非JSON 500 必须显示加载失败');
  }
  const generating = createSymbolHarness(async () => response(500, null, true));
  vm.runInContext(source, generating.context);
  await vm.runInContext('showGenerate()', generating.context);
  await generating.generateButton().listeners.click();
  assert.equal(generating.calls.access, 0);
  assert.equal(generating.generateButton().disabled, false, '生成 POST 非JSON 500 必须恢复重试按钮');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_generate_failure_restores_button(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  for (const fetchImpl of [
    async () => response(500, {ok: false, error: '生成不可用'}),
    async () => response(200, null, true),
    async () => { throw new Error('offline'); },
  ]){
    const h = createSymbolHarness(fetchImpl);
    vm.runInContext(source, h.context);
    await vm.runInContext('showGenerate()', h.context);
    await h.generateButton().listeners.click();
    const restored = h.generateButton();
    assert.equal(restored.disabled, false, '生成请求失败后必须恢复可用按钮');
    assert.equal(restored.textContent, '生成该股详情');
    assert.equal(h.timers.size, 0);
    assert.equal(h.calls.requests[0].options.redirectOn401, false);
  }
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_gen_status_terminal_states_stop(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  for (const status of ['failed', 'none', 'unknown']){
    const h = createSymbolHarness(async () => response(200, {ok: true, status, error: 'worker error'}));
    vm.runInContext(source, h.context);
    await vm.runInContext('pollGen()', h.context);
    assert.equal(h.timers.size, 0, status + ' 必须停止轮询');
    assert.equal(h.generateButton().disabled, false);
    assert.equal(h.calls.access, 0);
  }
  for (const status of [401, 404]){
    const h = createSymbolHarness(async () => {
      if (status === 401){ const error = new Error('unauthorized'); error.status = 401; throw error; }
      return response(404, {ok: false});
    });
    vm.runInContext(source, h.context);
    await vm.runInContext('pollGen()', h.context);
    assert.equal(h.calls.access, 1, status + ' 必须显示统一无权卡');
    assert.equal(h.timers.size, 0);
  }
  const ready = createSymbolHarness(async url => {
    if (url.endsWith('/gen-status')) return response(200, {ok: true, status: 'ready'});
    return response(200, {ok: true, summary: {}, trades: [], orders: [], failed_orders: []});
  });
  vm.runInContext(source, ready.context);
  await vm.runInContext('pollGen()', ready.context);
  assert.equal(ready.calls.requests.length, 2, 'ready 只能继续 load 主详情');
  assert.equal(ready.timers.size, 0);
  assert.equal(ready.calls.requests[0].options.redirectOn401, false);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_load_latest_epoch_wins_without_duplicate_replay(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
function deferred(){
  let resolve;
  const promise = new Promise(r => { resolve = r; });
  return {promise, resolve};
}
function detail(name){
  return response(200, {ok: true, summary: {name}, trades: [], orders: [], failed_orders: []});
}
(async () => {
  const mains = [];
  let notifyMain;
  const mainStarted = new Promise(resolve => { notifyMain = resolve; });
  const h = createSymbolHarness((url, options) => {
    if (url.endsWith('/gen-status')) return Promise.resolve(response(200, {ok: true, status: 'ready'}));
    const pending = deferred();
    mains.push({pending, options});
    notifyMain();
    return pending.promise;
  });
  vm.runInContext(source, h.context);
  const readyLoad = vm.runInContext('pollGen()', h.context);
  await mainStarted;
  assert.equal(mains.length, 1);
  const manualLoad = vm.runInContext('retryLoad()', h.context);
  assert.equal(mains.length, 2);
  mains[1].pending.resolve(detail('new'));
  await manualLoad;
  assert.deepEqual(h.calls.summaries.map(s => s.name), ['new']);
  assert.equal(h.calls.replay, 1);
  mains[0].pending.resolve(detail('old'));
  await readyLoad;
  assert.deepEqual(h.calls.summaries.map(s => s.name), ['new'], '旧 load 响应不能覆盖手动重试的新响应');
  assert.equal(h.calls.replay, 1, '成功重入不能重复初始化重播监听');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_gen_status_errors_stop_after_three_with_single_timer_retry(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  for (const fetchImpl of [
    async () => { throw new Error('offline'); },
    async () => response(500, {ok: false}),
    async () => response(200, null, true),
  ]){
    const h = createSymbolHarness(fetchImpl);
    vm.runInContext(source, h.context);
    for (let attempt = 1; attempt <= 3; attempt += 1){
      await vm.runInContext('pollGen()', h.context);
      assert.equal(h.calls.failure, attempt);
      assert.equal(h.timers.size, attempt < 3 ? 1 : 0);
    }
    assert.equal(vm.runInContext('symbolConsecutiveErrors', h.context), 3);
    assert.equal(h.calls.access, 0);
    assert.equal(typeof h.calls.retry, 'function');
    await vm.runInContext('retryGen()', h.context);
    await vm.runInContext('retryGen()', h.context);
    assert.equal(vm.runInContext('symbolConsecutiveErrors', h.context), 1);
    assert.equal(h.timers.size, 1, '手动重试不能留下重复 timer');
  }
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_pending_requests_timeout_and_recover(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
function pendingResponse(options){
  return new Promise((resolve, reject) => {
    if (options.signal) options.signal.addEventListener('abort', () => {
      const error = new Error('aborted'); error.name = 'AbortError'; reject(error);
    });
  });
}
(async () => {
  let blocked = true;
  const polling = createSymbolHarness(async (url, options) => {
    if (blocked) return pendingResponse(options);
    return response(200, {ok: true, status: 'queued'});
  });
  vm.runInContext(source, polling.context);
  const first = vm.runInContext('pollGen()', polling.context);
  assert.ok(polling.calls.requests[0].options.signal, 'gen-status 必须传 AbortSignal');
  await polling.runNextTimer();
  await first;
  assert.equal(polling.calls.failure, 1, '永久 pending 必须在请求超时后显示失败');
  assert.equal(typeof polling.calls.retry, 'function');
  blocked = false;
  await vm.runInContext('retryGen()', polling.context);
  assert.equal(polling.calls.requests.length, 2, '超时后可以重新发起请求');
  assert.equal(polling.timers.size, 1);

  const generating = createSymbolHarness(async (url, options) => pendingResponse(options));
  vm.runInContext(source, generating.context);
  await vm.runInContext('showGenerate()', generating.context);
  const click = generating.generateButton().listeners.click();
  assert.ok(generating.calls.requests[0].options.signal, '生成 POST 必须传 AbortSignal');
  await generating.runNextTimer();
  await click;
  assert.equal(generating.generateButton().disabled, false, '生成 POST 超时后必须恢复按钮');
  assert.equal(generating.generateButton().textContent, '生成该股详情');

  const hardDeadline = createSymbolHarness(async (url, options) => pendingResponse(options));
  vm.runInContext(source, hardDeadline.context);
  hardDeadline.context.pauseSymbolActivePolling = () => hardDeadline.calls.pause.push({});
  vm.runInContext('symbolActiveSince = 1000', hardDeadline.context);
  hardDeadline.setNow(1000 + 5 * 60 * 1000 - 100);
  const last = vm.runInContext('pollGen()', hardDeadline.context);
  await hardDeadline.runNextTimer();
  await last;
  assert.equal(hardDeadline.calls.failure, 0, '5分钟硬上限不得显示加载失败');
  assert.equal(hardDeadline.calls.pause.length, 1, 'pending 也受包含网络等待的5分钟暂停约束');
  assert.equal(hardDeadline.timers.size, 0);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_main_body_pending_times_out_and_retries(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const started = bodyBarrier();
  let blocked = true;
  const h = createSymbolHarness(async () => {
    if (blocked) return pendingBodyResponse(200, started.resolve);
    return response(200, {ok: true, summary: {name: 'recovered'}, trades: [], orders: [], failed_orders: []});
  });
  vm.runInContext(source, h.context);
  const pending = vm.runInContext('load()', h.context);
  await started.promise;
  await h.runNextTimer();
  await pending;
  assert.equal(h.calls.failure, 1, '主详情 body pending 必须超时显示失败');
  assert.equal(typeof h.calls.retry, 'function');
  blocked = false;
  await vm.runInContext('retryLoad()', h.context);
  assert.equal(h.calls.requests.length, 2);
  assert.deepEqual(h.calls.summaries.map(s => s.name), ['recovered']);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_generate_body_pending_times_out_and_retries(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const started = bodyBarrier();
  let blocked = true;
  const h = createSymbolHarness(async () => {
    if (blocked) return pendingBodyResponse(200, started.resolve);
    return response(500, {ok: false, error: '生成不可用'});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('showGenerate()', h.context);
  const pending = h.generateButton().listeners.click();
  await started.promise;
  await h.runNextTimer();
  await pending;
  assert.equal(h.generateButton().disabled, false, '生成 POST body pending 超时后必须恢复按钮');
  blocked = false;
  await h.generateButton().listeners.click();
  assert.equal(h.calls.requests.length, 2);
  assert.equal(h.generateButton().disabled, false);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_gen_status_body_pending_times_out_and_retries(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const started = bodyBarrier();
  let blocked = true;
  const h = createSymbolHarness(async () => {
    if (blocked) return pendingBodyResponse(200, started.resolve);
    return response(200, {ok: true, status: 'none'});
  });
  vm.runInContext(source, h.context);
  const pending = vm.runInContext('pollGen()', h.context);
  await started.promise;
  await h.runNextTimer();
  await pending;
  assert.equal(h.calls.failure, 1, 'gen-status body pending 必须超时显示失败');
  assert.equal(typeof h.calls.retry, 'function');
  blocked = false;
  await vm.runInContext('retryGen()', h.context);
  assert.equal(h.calls.requests.length, 2);
  assert.equal(h.generateButton().disabled, false);
  assert.equal(h.timers.size, 0);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_retry_aborts_pending_without_duplicate_requests(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const h = createSymbolHarness(async (url, options) => new Promise((resolve, reject) => {
    if (options.signal) options.signal.addEventListener('abort', () => {
      const error = new Error('aborted'); error.name = 'AbortError'; reject(error);
    });
  }));
  vm.runInContext(source, h.context);
  const first = vm.runInContext('pollGen()', h.context);
  const second = vm.runInContext('retryGen()', h.context);
  const third = vm.runInContext('retryGen()', h.context);
  assert.equal(h.calls.requests.length, 3, '每次手动重试都必须 abort 旧请求并发起新请求');
  assert.equal(h.calls.requests[0].options.signal.aborted, true);
  assert.equal(h.calls.requests[1].options.signal.aborted, true);
  assert.equal(h.calls.requests[2].options.signal.aborted, false);
  await h.runNextTimer();
  await Promise.all([first, second, third]);
  assert.equal(h.calls.requests.length, 3, '旧 Promise 收口不能触发额外请求');
  assert.equal(h.calls.failure, 1, '被新轮次 abort 的旧请求不能累计失败');
  assert.equal(h.timers.size, 0);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_gen_status_wait_limit_stops_with_retry(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const h = createSymbolHarness(async () => response(200, {ok: true, status: 'queued'}));
  vm.runInContext(source, h.context);
  h.context.pauseSymbolActivePolling = () => h.calls.pause.push({});
  await vm.runInContext('pollGen()', h.context);
  assert.equal(h.timers.size, 1);
  await vm.runInContext('retryGen()', h.context);
  await vm.runInContext('retryGen()', h.context);
  assert.equal(h.timers.size, 1, '重复重试仍只能有一个 timer');
  h.setNow(1000 + 5 * 60 * 1000);
  await vm.runInContext('pollGen()', h.context);
  assert.equal(h.timers.size, 0);
  assert.equal(h.calls.failure, 0, '活跃等待到期不得显示加载失败');
  assert.equal(h.calls.pause.length, 1, '活跃等待到期必须暂停自动刷新');
  assert.equal(typeof vm.runInContext('retryGen', h.context), 'function');
})().catch(error => { console.error(error); process.exit(1); });
""")
        assert "已暂停自动刷新" in html
        assert "任务可能仍在运行" in html

    def test_symbol_note_shows_data_until_without_contract_link(self, client):
        """头部 sym-note 只显示数据截止，不再重复提供口径说明深链。"""
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_js(html, r"""
(async () => {
  const withUntil = createSymbolHarness(async () => response(200, {ok: true,
    summary: {}, trades: [], orders: [], failed_orders: [],
    data_until: '2026-02-27', kline: {dates: ['2026-01-05', '2026-01-06']}}));
  vm.runInContext(source, withUntil.context);
  await vm.runInContext('load()', withUntil.context);
  const note = withUntil.elements['sym-note'].innerHTML;
  assert.ok(note.includes('数据截止 2026-02-27'), note);
  assert.ok(!note.includes('/saas/help#'), note);
  assert.ok(note.includes('全量 2 个交易日'), '既有交易日文案不得丢失：' + note);

  const missing = createSymbolHarness(async () => response(200, {ok: true,
    summary: {}, trades: [], orders: [], failed_orders: [], kline: null}));
  vm.runInContext(source, missing.context);
  await vm.runInContext('load()', missing.context);
  const note2 = missing.elements['sym-note'].innerHTML;
  assert.ok(note2.includes('数据截止 未声明'), '缺字段不编日期：' + note2);
  assert.ok(!note2.includes('/saas/help#'), note2);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_repeated_replay_initialization_binds_once(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_script_js(html, r"(let kreplayCtl[\s\S]*?function initKlineReplay[\s\S]*?\n\})(?=\nfunction mountKlineReplay)", r"""
(async () => {
  const h = createSymbolHarness(async () => response(200, {ok: true}));
  h.context.mountKlineReplay = () => ({destroy(){}});
  vm.runInContext(source, h.context);
  vm.runInContext('initKlineReplay({kline: null})', h.context);
  const data = {kline: {dates: ['2026-01-01'], ohlc: [[1, 1, 1, 1]], vols: [1]}, trades: [], orders: []};
  for (let i = 0; i < 2; i += 1) vm.runInContext('initKlineReplay(' + JSON.stringify(data) + ')', h.context);
  assert.equal(h.elements['btn-kreplay'].listenerCounts.click, 1, '失败后重试与连续初始化只能绑定一次重播');
  assert.equal(h.elements['btn-kreplay-exit'].listenerCounts.click, 1);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_symbol_equity_and_kline_resize_listeners_do_not_accumulate(self, client):
        html = client.get("/saas/jobs/1/symbols/000001.SZ").get_data(as_text=True)
        _run_symbol_script_js(html, r"(let equityResizeBound[\s\S]*?)(?=\nfunction renderWear)", r"""
(async () => {
  const h = createSymbolHarness(async () => response(200, {ok: true}));
  h.context.echarts = {init(){ return {
    setOption(){}, on(){}, resize(){},
    getOption(){ return {dataZoom: [{start: 0, end: 100}]}; },
  }; }};
  h.context.card = () => ''; h.context.pct = () => ''; h.context.cls = () => '';
  vm.runInContext(source, h.context);
  const data = {equity: {dates: ['2026-01-01'], values: [1]}, trades: []};
  vm.runInContext('renderEquity(' + JSON.stringify(data) + ')', h.context);
  vm.runInContext('renderEquity(' + JSON.stringify(data) + ')', h.context);
  assert.equal((h.windowListeners.resize || []).length, 1, '收益图重复渲染不得累积 resize');
})().catch(error => { console.error(error); process.exit(1); });
""")
        _run_symbol_script_js(html, r"(let klineResizeBound[\s\S]*?)(?=\n// --- K线级重播)", r"""
(async () => {
  const h = createSymbolHarness(async () => response(200, {ok: true}));
  h.context.echarts = {
    init(){ return {setOption(){}, resize(){}}; },
    getInstanceByDom(){ return null; },
  };
  h.context.QREFactorLayout = {plan(){ return {chips: [], panes: [], overlays: []}; }};
  h.context.chipStates = () => ({});
  h.context.renderFactorChips = () => {};
  vm.runInContext(source, h.context);
  const data = {kline: {dates: ['2026-01-01'], ohlc: [[1, 1, 1, 1]], vols: [1]}, factors: [], orders: []};
  vm.runInContext('renderKline(' + JSON.stringify(data) + ')', h.context);
  vm.runInContext('renderKline(' + JSON.stringify(data) + ')', h.context);
  assert.equal((h.windowListeners.resize || []).length, 1, 'K线重复渲染不得累积 resize');
})().catch(error => { console.error(error); process.exit(1); });
""")

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

    def test_job_polling_access_and_readonly_guards(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        for marker in (
            "const ACTIVE = new Set(['queued','leased','running','uploading']);",
            "const TERMINAL = new Set(['failed','expired','canceled','cancelled']);",
            "const POLL_INTERVAL_MS = 5000;",
            "const MAX_CONSECUTIVE_ERRORS = 3;",
            "const MAX_ACTIVE_WAIT_MS = 5 * 60 * 1000;",
            "jobRequestJsonWithTimeout(shareUrl('/api/results/' + JOB_ID + '/summary'), {redirectOn401:false}",
            "showAccessFallback(document.querySelector('.container'))",
            "showLoadFailure(document.querySelector('.container'), retryPoll)",
            "已暂停自动刷新",
            "clearPollTimer()",
            "pollInFlight",
            "if (jobData.readonly){ syncResultActionCard(); return; }",
            "tagResp.status === 404",
        ):
            assert marker in html


_JOB_RUNTIME_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function jobEl(){
  const e = {
    children: [], childNodes: [], style: {}, className: '', _textContent: '', innerHTML: '',
    disabled: false, dataset: {}, listeners: {}, classes: new Set(),
    setAttribute(name, value){ this[name] = String(value); },
    removeAttribute(name){ delete this[name]; },
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){ (this.listeners[type] ||= []).push(fn); },
    querySelectorAll(){ return []; },
  };
  Object.defineProperty(e, 'textContent', {
    get(){ return e._textContent; }, set(v){ e._textContent = v; },
  });
  e.classList = {
    add(c){ e.classes.add(c); },
    remove(c){ e.classes.delete(c); },
    toggle(c, force){ if (force === undefined ? !e.classes.has(c) : force) e.classes.add(c); else e.classes.delete(c); },
    contains(c){ return e.classes.has(c); },
  };
  return e;
}
function response(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
  }};
}
function createJobRuntimeHarness(fetchImpl, opts){
  opts = opts || {};
  const root = jobEl();
  root.childNodes = [jobEl()];
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = jobEl()); }});
  const calls = {access: 0, failure: 0, attribution: 0, requests: []};
  const timers = new Map();
  let nextTimer = 1;
  let now = 1000;
  const document = {
    querySelector(selector){
      if (selector === '.container') return root;
      if (selector === '.container .card') return root.children[root.children.length - 1];
      return null;
    },
    querySelectorAll(){ return []; },
    getElementById(id){ return elements[id]; },
    createElement(){ return jobEl(); },
  };
  const context = vm.createContext({
    console, document, window: {addEventListener(){}}, JOB_ID: 1, STATUS_LABEL: {},
    SAAS_BYPASS: !!opts.bypass, AbortController,
    MAX_ACTIVE_WAIT_MS: 300000,
    Date: {now(){ return now; }},
    location: {search: ''}, URLSearchParams,
    // P1 只读分享：URL 无 share token 时透传（token 传播由
    // test_saas_access_hardening 的专用 harness 覆盖）
    shareUrl(url){ return url; }, shareSuffix(){ return ''; }, initShareButton(){},
    requestAnimationFrame(fn){ return fn(); },
    saasToken(){ return opts.token === undefined ? 'token' : opts.token; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(jobEl()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(jobEl()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderMeta(){}, renderStrategyInfo(){}, renderMetrics(){}, renderMain(){}, empty(){},
    renderContract(){},
    initReplay(){}, initResultActions(){}, renderFees(){}, loadRisk(){}, renderRisk(){},
    renderAttribution(){ calls.attribution += 1; },
    mountReplay(){ return {destroy(){}}; },
  });
  return {
    context, calls, timers, root, elements,
    setNow(value){ now = value; },
    click(id){ (elements[id].listeners.click || []).forEach(fn => fn({target: elements[id]})); },
    async runNextTimer(){
      const entry = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(entry, '必须存在可执行的 timeout');
      timers.delete(entry[0]);
      now = Math.max(now, entry[1].at);
      return entry[1].fn();
    },
  };
}
"""


class TestJobPageRuntimeAndCancel:
    """QRE-SAAS-FIRST-SUCCESS-UX-001：job.html 队列/离线/取消/失败恢复。"""

    def _run(self, html, scenario):
        match = re.search(r"(const ACTIVE =.*?)(?=// --- 回测重播)", html, re.S)
        assert match, "未找到 job.html 轮询脚本"
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        script = (_JOB_RUNTIME_HARNESS + "\nconst source = " + json.dumps(match.group(1))
                  + ";\n" + scenario)
        result = subprocess.run([node, "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout

    def test_runtime_markers_present(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        for marker in (
            'id="btn-cancel-job"',
            'id="cancel-modal"',
            'id="recover-actions"',
            'id="job-status-extra"',
            "排队中，前面还有 ",
            "排队中，等待计算节点领取",
            "计算节点暂时离线，任务已保留，恢复后会继续；无需重复提交",
            "按原策略重新回测",
            "/api/saas/jobs/' + JOB_ID + '/cancel'",
        ):
            assert marker in html, marker

    def test_queued_409_renders_queue_offline_and_cancel(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createJobRuntimeHarness(async url => {
    if (url.includes('/summary')) return response(409, {ok: false, status: 'queued',
      queue_position: 3, worker_online: false, cancel_requested: false, strategy_id: 42,
      error_class: null, error_message: null});
    return response(200, {ok: true});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('poll()', h.context);
  const note = h.elements['job-status-note'].textContent;
  assert.ok(note.includes('排队中，前面还有 3 个任务'), note);
  const extra = h.elements['job-status-extra'].textContent;
  assert.ok(extra.includes('计算节点暂时离线'), extra);
  assert.ok(extra.includes('无需重复提交'), extra);
  assert.ok(extra.includes('已等待'), extra);
  assert.equal(h.elements['job-badge'].className, 'badge queued');
  assert.ok(!h.elements['status-actions'].classes.has('hidden'), '活跃任务必须出现取消入口');
  assert.equal(h.elements['btn-cancel-job'].disabled, false);
  assert.equal(h.timers.size, 1, '活跃态必须继续轮询');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_queued_zero_and_running_cancel_requested(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const zero = createJobRuntimeHarness(async () =>
    response(409, {ok: false, status: 'queued', queue_position: 0, worker_online: true}));
  vm.runInContext(source, zero.context);
  await vm.runInContext('poll()', zero.context);
  assert.ok(zero.elements['job-status-note'].textContent.includes('排队中，等待计算节点领取'));

  const running = createJobRuntimeHarness(async () =>
    response(409, {ok: false, status: 'running', worker_online: true, cancel_requested: true}));
  vm.runInContext(source, running.context);
  await vm.runInContext('poll()', running.context);
  const note = running.elements['job-status-note'].textContent;
  assert.ok(note.includes('正在取消'), note);
  assert.equal(running.elements['btn-cancel-job'].disabled, true, '取消请求已发送必须禁用重复取消');
  assert.ok(running.elements['cancel-status'].textContent.includes('正在取消'));
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_cancel_modal_confirms_and_cancels_queued(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createJobRuntimeHarness(async url => {
    if (url.includes('/summary')) return response(409, {ok: false, status: 'queued',
      queue_position: 1, worker_online: true});
    if (url.includes('/cancel')) return response(200, {ok: true, status: 'canceled'});
    return response(200, {ok: true});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('poll()', h.context);
  // 第一次点击只开二次确认模态，不得直接取消
  h.click('btn-cancel-job');
  assert.ok(h.elements['cancel-modal'].classes.has('show'), '取消必须走自定义模态二次确认');
  assert.equal(h.calls.requests.filter(r => r.url.includes('/cancel')).length, 0);
  // 取消按钮（模态内）不关模态
  h.click('cancel-modal-no');
  assert.ok(!h.elements['cancel-modal'].classes.has('show'));
  assert.equal(h.calls.requests.filter(r => r.url.includes('/cancel')).length, 0);
  // 确认取消 → POST 取消端点，queued 直接 canceled 后停止轮询
  h.click('btn-cancel-job');
  h.click('cancel-modal-yes');
  await new Promise(r => setTimeout(r, 0));
  const cancels = h.calls.requests.filter(r => r.url.includes('/cancel'));
  assert.equal(cancels.length, 1, '确认后必须调用既有取消 API');
  assert.equal(cancels[0].options.method, 'POST');
  assert.equal(h.timers.size, 0, 'queued 取消成功后必须停止轮询');
  assert.equal(h.elements['job-badge'].className, 'badge failed');
  assert.ok(h.elements['job-status-note'].textContent.includes('已取消'));
  assert.ok(h.elements['status-actions'].classes.has('hidden'));
  // 重复点击不得产生第二次取消请求
  h.click('cancel-modal-yes');
  await new Promise(r => setTimeout(r, 0));
  assert.equal(h.calls.requests.filter(r => r.url.includes('/cancel')).length, 1);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_cancel_running_marks_request_sent(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createJobRuntimeHarness(async url => {
    if (url.includes('/summary')) return response(409, {ok: false, status: 'running',
      worker_online: true});
    if (url.includes('/cancel')) return response(200, {ok: true, status: 'running',
      cancel_requested: true});
    return response(200, {ok: true});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('poll()', h.context);
  h.click('btn-cancel-job');
  h.click('cancel-modal-yes');
  await new Promise(r => setTimeout(r, 0));
  const status = h.elements['cancel-status'].textContent;
  assert.ok(status.includes('取消请求已发送'), status);
  assert.ok(status.includes('最终状态以服务端为准'), status);
  assert.equal(h.elements['btn-cancel-job'].disabled, true);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_failed_recovery_links_for_login_and_guest(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const failed = {ok: false, status: 'failed', strategy_id: 42,
                  error_class: 'strategy_compile_error',
                  error_message: '策略第 3 行 entry 表达式不合法'};
  const login = createJobRuntimeHarness(async () => response(409, failed), {token: 'token'});
  vm.runInContext(source, login.context);
  await vm.runInContext('poll()', login.context);
  const err = login.elements['recover-error'].textContent;
  assert.ok(err.includes('策略第 3 行 entry 表达式不合法'), err);
  const link = login.elements['btn-rerun'];
  assert.equal(link.textContent, '按原策略重新回测');
  assert.equal(link.href, '/saas/new?strategy=42');
  assert.ok(!login.elements['recover-actions'].classes.has('hidden'));
  assert.equal(login.timers.size, 0, '终态必须停止轮询');

  const guest = createJobRuntimeHarness(async () => response(409, failed), {token: ''});
  vm.runInContext(source, guest.context);
  await vm.runInContext('poll()', guest.context);
  assert.equal(guest.elements['btn-rerun'].textContent, '返回新建页');
  assert.equal(guest.elements['btn-rerun'].href, '/saas/new');
  assert.ok(guest.elements['recover-error'].textContent.includes('策略第 3 行 entry 表达式不合法'));
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_readonly_completed_never_shows_cancel(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        self._run(html, r"""
(async () => {
  const h = createJobRuntimeHarness(async url => {
    if (url.includes('/summary')) return response(200, {ok: true, readonly: true,
      strategy_id: 1, strategy_name: '经典', summary: {}, result_contract: null});
    return response(200, {ok: true});
  });
  vm.runInContext(source, h.context);
  await vm.runInContext('poll()', h.context);
  assert.ok(h.elements['status-card'].classes.has('hidden'), '完成后状态卡隐藏');
  assert.ok(h.elements['status-actions'].classes.has('hidden'), 'showcase 只读不得出现取消入口');
  assert.ok(h.elements['recover-actions'].classes.has('hidden'), '只读不得出现重跑入口');
  h.click('btn-cancel-job');
  assert.equal(h.calls.requests.filter(r => r.url.includes('/cancel')).length, 0);
  assert.ok(!h.elements['cancel-modal'].classes.has('show'));
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_job_contract_badge_is_not_rendered(self, client):
        """结果合同留在系统内，页面只保留两种收益口径的悬停提示。"""
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        assert 'id="box-contract"' not in html
        assert 'id="contract-badge"' not in html
        assert 'id="contract-note"' not in html
        assert "日收益累乘" in html and "初始资金加权" in html
        assert "function renderContract(c)" in html

    def test_job_completed_resource_failures_pause_after_three_rounds(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =.*?)(?=// --- 回测重播)", r"""
const h = createHarness(async url => {
  if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
  if (url.includes('/chart-data')) return response(500, {ok: false});
  return response(404, {ok: false});
});
vm.runInContext(source, h.context);
(async () => {
  for (let round = 0; round < 3; round += 1) await vm.runInContext('poll()', h.context);
  assert.equal(vm.runInContext('consecutiveErrors', h.context), 3);
  assert.equal(h.calls.failure, 3);
  assert.equal(h.calls.access, 0);
  assert.equal(h.timers.size, 0, '连续 chart 失败后必须暂停，不能继续无限轮询');
  assert.equal(typeof h.calls.retry, 'function', '暂停后必须保留重试入口');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_job_resource_404_does_not_trigger_access_fallback(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =.*?)(?=// --- 回测重播)", r"""
(async () => {
  const chart404 = createHarness(async url => {
    if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
    if (url.includes('/chart-data')) return response(404, {ok: false});
    return response(404, {ok: false});
  });
  vm.runInContext(source, chart404.context);
  await vm.runInContext('poll()', chart404.context);
  assert.equal(chart404.calls.access, 0, 'chart-data 404 不是任务无权');
  assert.equal(chart404.calls.failure, 1);

  const summary404 = createHarness(async () => response(404, {ok: false}));
  vm.runInContext(source, summary404.context);
  await vm.runInContext('poll()', summary404.context);
  assert.equal(summary404.calls.access, 1);
  assert.equal(summary404.calls.failure, 0);

  const tag404 = createHarness(async url => {
    if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
    if (url.includes('/chart-data')) return response(200, {ok: true});
    return response(404, {ok: false});
  });
  vm.runInContext(source, tag404.context);
  await vm.runInContext('poll()', tag404.context);
  assert.equal(tag404.calls.access, 0);
  assert.equal(tag404.calls.failure, 0);
  assert.equal(tag404.calls.attribution, 1, 'tag-analysis 404 仍按无归因完成整轮');
  assert.equal(vm.runInContext('consecutiveErrors', tag404.context), 0);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_load_risk_errors_are_local_and_never_redirect(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(let riskEpoch[\s\S]*?async function loadRisk\(\)\{.*?\})(?=\nfunction renderRisk)", r"""
(async () => {
  const unauthorized = new Error('unauthorized');
  unauthorized.status = 401;
  const scenarios = [
    async () => { throw new Error('offline'); },
    async () => { throw unauthorized; },
    async () => response(500, {ok: false}),
    async () => response(200, null, true),
  ];
  for (const apiFetch of scenarios){
    const h = createHarness(apiFetch);
    vm.runInContext(source, h.context);
    await vm.runInContext('loadRisk()', h.context);
    assert.equal(h.elements['box-risk'].style.display, '');
    assert.equal(h.elements['risk-body'].children[0].textContent, '风险分析加载失败');
    assert.equal(h.calls.access, 0, '风险区异常不能触发整页无权');
    assert.equal(h.calls.requests.at(-1).options.redirectOn401, false);
  }
})().catch(error => { console.error(error); process.exit(1); });
""", r"(const JOB_REQUEST_TIMEOUT_MS[\s\S]*?)(?=function abortPoll)")

    def test_job_all_resource_fetch_and_body_pending_time_out(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =.*?)(?=// --- 回测重播)", r"""
(async () => {
  for (const resource of ['summary', 'chart-data', 'tag-analysis']){
    for (const kind of ['fetch', 'body']){
      const started = jobDeferred();
      const h = createHarness(async (url, options) => {
        const pending = kind === 'fetch' ? jobPendingFetch(options) : jobPendingBody(200, started.resolve);
        if (url.includes('/' + resource)) return pending;
        if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
        if (url.includes('/chart-data')) return response(200, {ok: true});
        return response(404, {ok: false});
      });
      vm.runInContext(source, h.context);
      const pending = vm.runInContext('poll()', h.context);
      if (kind === 'body') await started.promise;
      assert.ok(h.calls.requests.some(r => r.options.signal), resource + ' ' + kind + ' 必须传 AbortSignal');
      await h.runNextTimer();
      await pending;
      assert.equal(h.calls.failure, 1, resource + ' ' + kind + ' pending 必须超时失败');
      assert.equal(h.calls.access, 0);
      assert.ok(h.timers.size <= 1, resource + ' ' + kind + ' 收口后最多保留一个重试 timer');
    }
  }
})().catch(error => { console.error(error); process.exit(1); });
""")
        _run_job_js(html, r"(let riskEpoch[\s\S]*?async function loadRisk\(\)\{.*?\})(?=\nfunction renderRisk)", r"""
(async () => {
  for (const kind of ['fetch', 'body']){
    const started = jobDeferred();
    const h = createHarness(async (url, options) => kind === 'fetch' ? jobPendingFetch(options) : jobPendingBody(200, started.resolve));
    vm.runInContext(source, h.context);
    const pending = vm.runInContext('loadRisk()', h.context);
    if (kind === 'body') await started.promise;
    await h.runNextTimer();
    await pending;
    assert.equal(h.elements['risk-body'].children[0].textContent, '风险分析加载失败', kind + ' pending 必须局部收口');
    assert.equal(h.calls.access, 0);
    assert.equal(h.timers.size, 0);
  }
})().catch(error => { console.error(error); process.exit(1); });
""", r"(const JOB_REQUEST_TIMEOUT_MS[\s\S]*?)(?=function abortPoll)")

    def test_job_retry_supersedes_pending_round_without_duplicate_timers(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =.*?)(?=// --- 回测重播)", r"""
(async () => {
  let first = true;
  const h = createHarness(async (url, options) => {
    if (url.includes('/summary') && first) return jobPendingFetch(options);
    if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
    if (url.includes('/chart-data')) return response(200, {ok: true});
    return response(404, {ok: false});
  });
  vm.runInContext(source, h.context);
  const oldRound = vm.runInContext('poll()', h.context);
  first = false;
  await vm.runInContext('retryPoll()', h.context);
  assert.equal(h.calls.requests[0].options.signal.aborted, true, '手动重试必须 abort 旧请求');
  assert.equal(h.timers.size, 0, '完成后不得遗留重复 timer');
  await oldRound;
  assert.equal(h.calls.failure, 0, '旧请求取消不得污染新成功轮次');
  assert.equal(h.calls.attribution, 1);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_job_chart_and_tag_401_use_access_fallback(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =.*?)(?=// --- 回测重播)", r"""
(async () => {
  for (const resource of ['chart-data', 'tag-analysis']){
    const h = createHarness(async url => {
      if (url.includes('/summary')) return response(200, {ok: true, summary: {}});
      if (url.includes('/' + resource)) return response(401, {ok: false});
      return response(200, {ok: true});
    });
    vm.runInContext(source, h.context);
    await vm.runInContext('poll()', h.context);
    assert.equal(h.calls.access, 1, resource + ' 401 必须统一无权');
    assert.equal(h.calls.failure, 0);
    assert.equal(h.timers.size, 0);
  }
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_job_repeated_success_and_retry_bind_listeners_once(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(const ACTIVE =[\s\S]*?async function initResultActions[\s\S]*?\n\})(?=\n\nif \(new URLSearchParams)", r"""
function successFetch(url){
  if (url.includes('/summary')) return response(200, {ok: true, strategy_id: 7, summary: {}});
  if (url.includes('/chart-data')) return response(200, {ok: true, dates: ['2026-01-01'], equity: [1]});
  if (url.includes('/tag-analysis')) return response(404, {ok: false});
  if (url.endsWith('/api/saas/strategies/7')) return response(200, {ok: true, strategy: {in_library: false}});
  if (url.endsWith('/api/saas/universes')) return response(200, {ok: true, groups: []});
  return response(200, {ok: true});
}
async function assertSinglePost(h){
  await h.elements['btn-save-lib'].listeners.click[0]();
  assert.equal(h.calls.requests.filter(r => r.url.endsWith('/save')).length, 1, '一次保存点击只能发一次 POST');
  await h.elements['btn-signal-open'].listeners.click[0]();
  await h.elements['btn-signal-confirm'].listeners.click[0]();
  assert.equal(h.calls.requests.filter(r => r.url.endsWith('/watch')).length, 1, '一次监控点击只能发一次 POST');
}
(async () => {
  const twice = createHarness(async url => successFetch(url));
  vm.runInContext(source, twice.context);
  await vm.runInContext('poll()', twice.context);
  await vm.runInContext('poll()', twice.context);
  for (const id of ['btn-replay', 'btn-replay-exit', 'btn-save-lib', 'btn-signal-open', 'btn-signal-confirm'])
    assert.equal(twice.listenerCount(id, 'click'), 1, id + ' 连续初始化不得重复绑定');
  await assertSinglePost(twice);

  let failed = true;
  const retry = createHarness(async url => {
    if (failed && url.includes('/chart-data')) return response(500, {ok: false});
    return successFetch(url);
  });
  vm.runInContext(source, retry.context);
  await vm.runInContext('poll()', retry.context);
  failed = false;
  await retry.calls.retry();
  for (const id of ['btn-replay', 'btn-replay-exit', 'btn-save-lib', 'btn-signal-open', 'btn-signal-confirm'])
    assert.equal(retry.listenerCount(id, 'click'), 1, id + ' 失败后重试不得重复绑定');
  await assertSinglePost(retry);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_job_main_and_risk_resize_listeners_do_not_accumulate(self, client):
        html = client.get("/saas/jobs/1").get_data(as_text=True)
        _run_job_js(html, r"(let mainChart[\s\S]*?function renderMain[\s\S]*?\n\})(?=\nfunction applyBench)", r"""
(async () => {
  const h = createHarness(async () => response(200, {ok: true}));
  h.context.echarts = {init(){ return {
    setOption(){}, on(){}, resize(){}, dispatchAction(){},
    getOption(){ return {dataZoom: [{start: 0, end: 100}]}; },
  }; }};
  h.context.pct = () => ''; h.context.cls = () => ''; h.context.stratRet = () => [];
  h.context.card = () => '';
  vm.runInContext(source, h.context);
  const data = {dates: ['2026-01-01'], equity: [1], drawdown_pct: [], trades: {points: []}};
  vm.runInContext('renderMain(' + JSON.stringify(data) + ')', h.context);
  vm.runInContext('renderMain(' + JSON.stringify(data) + ')', h.context);
  assert.equal((h.windowListeners.resize || []).length, 1, '主图重复渲染不得累积 resize');
})().catch(error => { console.error(error); process.exit(1); });
""")
        _run_job_js(html, r"(let riskCharts[\s\S]*?function renderRisk\(d\) \{[\s\S]*?\n  \})(?=\nfunction renderRiskDist)", r"""
(async () => {
  const h = createHarness(async () => response(200, {ok: true}));
  h.context.renderRiskDist = () => {}; h.context.renderRiskVol = () => {}; h.context.renderRiskStress = () => {};
  h.context.card = () => ''; h.context.escH = value => String(value);
  vm.runInContext(source, h.context);
  vm.runInContext('renderRisk({})', h.context);
  vm.runInContext('renderRisk({})', h.context);
  assert.equal((h.windowListeners.resize || []).length, 1, '风险图重复渲染不得累积 resize');
})().catch(error => { console.error(error); process.exit(1); });
""")

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
        # QRE-SAAS-NL-A1：输入须先过前置校验，"x" 属过短（422），改用经典合法描述
        assert client.post("/api/saas/nl/compile",
                           json={"description": "MACD 金叉买入，死叉卖出"}).status_code == 503
        from quant_research_engine.gui.saas import app as saas_app

        for _ in range(saas_app.GUEST_NL_DAILY_LIMIT - 1):
            client.post("/api/saas/nl/compile",
                        json={"description": "MACD 金叉买入，死叉卖出"})
        resp = client.post("/api/saas/nl/compile",
                           json={"description": "MACD 金叉买入，死叉卖出"})
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
                           json={"description": "收盘价大于 0 买入，小于 0 卖出"}, headers=AUTH)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] and "entry" in data["yaml"]

    def test_not_configured_503(self, client, monkeypatch):
        for var in ("QRE_NL_LLM_BASE_URL", "QRE_NL_LLM_API_KEY", "QRE_NL_LLM_MODEL"):
            monkeypatch.delenv(var, raising=False)
        resp = client.post("/api/saas/nl/compile",
                           json={"description": "MACD 金叉买入，死叉卖出"}, headers=AUTH)
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

    def test_items_carry_registry_display_fields(self, client, monkeypatch):
        """因子语义注册表增量字段：zh / canonical / price_basis / aliases。"""
        monkeypatch.setattr(
            "quant_research_engine.gui.factor_wizard.load_factor_tables_columns",
            lambda db_url=None: {"stock_daily_momentum_close": ["rsi_14"]},
        )
        data = client.get("/api/saas/factors", headers=AUTH).get_json()
        items = [i for g in data["groups"] for i in g["items"]]
        assert items
        for item in items:
            for key in ("label", "zh", "canonical", "price_basis", "aliases"):
                assert key in item, (key, item)
        rsi = next(i for i in items if i["column"] == "rsi_14")
        assert rsi["canonical"] == "factors.stock_daily_momentum_close.rsi_14"
        assert rsi["price_basis"] == "close"
        assert "相对强弱指标" in rsi["zh"]
        assert "rsi" in rsi["aliases"]
        market = next(i for i in items if i["column"] == "close")
        assert market["zh"] == "收盘价"
        assert market["canonical"] == "public.stock_daily.close"


class TestFactorPickerModal:
    """QRE-SAAS-FACTOR-PICKER-MODAL：渲染后的 new.html 必须带三栏弹窗与隐藏数据字段契约。"""

    def test_new_page_renders_picker_modal(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        # 弹窗结构（复用既有 modal-mask/.modal 组件）
        assert 'class="modal-mask" id="factor-picker-modal"' in html
        assert 'id="factor-picker-search"' in html
        assert 'id="factor-picker-close"' in html
        assert 'id="fp-list-group"' in html and 'id="fp-list-sub"' in html and 'id="fp-list-factor"' in html
        assert 'id="factor-picker-results"' in html and 'id="factor-picker-empty"' in html
        assert 'role="dialog"' in html and 'aria-modal="true"' in html
        # 数据契约：按钮只呈现，.wz-left/.wz-rfield 仍是唯一值来源
        assert "wrap.className = 'wz-factsel factor-picker-field'" in html
        assert "sel.addEventListener('change', refreshWizard);" in html
        assert "function openFactorPicker(wrap)" in html
        assert "function closeFactorPicker()" in html
        assert "function syncFactorPickerButton(wrap)" in html
        assert "snapshotWzArea" in html and "setFactorSelectValue" in html

    def test_picker_css_hides_data_selects(self):
        css = (Path(__file__).resolve().parents[1]
               / "src/quant_research_engine/gui/static/lab-theme.css").read_text()
        assert ".factor-picker-field select{display:none}" in css
        assert ".factor-select-btn" in css
        assert "#factor-picker-modal .modal.factor-picker" in css
        # 移动端：接近全宽 + 视口限高 + 三栏降单列，禁页面横滚
        assert "calc(100vw - 24px)" in css and "calc(100vh - 40px)" in css
        assert "grid-template-columns:1fr" in css


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
        assert "/api/saas/jobs/' + JOB_ID + '/result" not in html  # 不再走旧 job 嵌套 result
        # QRE-SAAS-FIRST-SUCCESS-UX-001：取消走既有 cancel API（POST）
        assert "/api/saas/jobs/' + JOB_ID + '/cancel" in html


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
