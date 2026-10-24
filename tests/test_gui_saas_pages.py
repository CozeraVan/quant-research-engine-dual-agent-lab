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
    classList: {add(){}, remove(){}},
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(){},
  };
}
function response(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
  }};
}
function createHarness(fetchImpl){
  const root = el();
  root.childNodes = [el()];
  const elements = new Proxy({}, {get(obj, key){ return obj[key] || (obj[key] = el()); }});
  const calls = {access: 0, failure: 0, attribution: 0, requests: []};
  const timers = new Map();
  let nextTimer = 1;
  const document = {
    querySelector(selector){
      if (selector === '.container') return root;
      if (selector === '.container .card') return root.children[root.children.length - 1];
      return null;
    },
    getElementById(id){ return elements[id]; },
    createElement(){ return el(); },
  };
  const context = vm.createContext({
    console, document, JOB_ID: 1, STATUS_LABEL: {}, SAAS_BYPASS: false,
    saasToken(){ return 'token'; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(el()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(el()); },
    setTimeout(fn){ const id = nextTimer++; timers.set(id, fn); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderMeta(){}, renderStrategyInfo(){}, renderMetrics(){}, renderMain(){}, empty(){},
    initReplay(){}, initResultActions(){}, renderFees(){}, loadRisk(){}, renderRisk(){},
    renderAttribution(){ calls.attribution += 1; },
  });
  return {context, calls, timers, root, elements};
}
"""


def _run_job_js(html: str, source_pattern: str, scenario: str) -> None:
    match = re.search(source_pattern, html, re.S)
    assert match, "未找到待测模板脚本"
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    script = _JOB_JS_HARNESS + "\nconst source = " + json.dumps(match.group(1)) + ";\n" + scenario
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
function recordsResponse(status, data, jsonError){
  return {status, ok: status >= 200 && status < 300, json: async () => {
    if (jsonError) throw new Error('invalid json');
    return data;
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
    console, document, STATUS_LABEL: {}, SAAS_BYPASS: false,
    Date: {now(){ return now; }},
    location: {href: ''},
    requireLogin(){ calls.login += 1; },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(recordsEl()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(recordsEl()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
  });
  return {context, calls, timers, root, elements, setNow(value){ now = value; }};
}
"""


def _run_records_js(html: str, scenario: str) -> None:
    scripts = re.findall(r"<script>([\s\S]*?)</script>", html)
    source = next(script for script in scripts if "function loadFactorRequests()" in script)
    source = re.sub(r"\nload\(\);\s*$", "\nrecordsInitialLoad = load();", source)
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
  assert.equal(h.timers.size, 1);
  await vm.runInContext('load()', h.context);
  await vm.runInContext('load()', h.context);
  assert.equal(h.timers.size, 1, '重复 load 也只能保留一个 timer');
  h.setNow(1000 + 5 * 60 * 1000);
  await vm.runInContext('load()', h.context);
  assert.equal(h.timers.size, 0, '活跃刷新到期后必须暂停');
  assert.equal(vm.runInContext("document.querySelector('.wrap').children[0].children[0].textContent", h.context), '已暂停自动刷新');
  await h.elements['btn-reload'].listeners.click();
  assert.equal(h.timers.size, 1, '手动刷新必须恢复自动刷新');
  assert.equal(h.calls.failure, 0, '暂停不得伪报加载失败');
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
        assert "apiFetch('/api/saas/me', {redirectOn401:false})" in load_profile.group(0)
        assert "if (!resp.ok || !d.ok) return;" in load_profile.group(0)

    def test_new_login_url_and_poll_job_fail_fast(self, client):
        html = client.get("/saas/new").get_data(as_text=True)
        assert "$('#guest-register').addEventListener('click', () => { location.href = saasLoginUrl(); });" in html
        assert "for (let i = 0; i < 80; i++)" in html
        match = re.search(r"(async function pollJob\(jobId\)\{.*?\n\})(?=\nfunction isGuest)", html, re.S)
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
const context = vm.createContext({
  setTimeout(fn){ fn(); return 1; },
  apiFetch(url){ calls.push(url); return context.responses.shift(); },
  responses: [],
});
function response(status, data){
  return Promise.resolve({status, ok: status >= 200 && status < 300, json: async () => data});
}
"""
        scenario = r"""
(async () => {
  for (const responses of [
    [response(500, {ok: false, error: 'down'})],
    [response(200, {ok: true})],
    [response(200, {ok: false, job: {status: 'running'}})],
  ]){
    calls.length = 0;
    context.responses = responses;
    await assert.rejects(vm.runInContext('pollJob(7)', context));
    assert.equal(calls.length, 1, '非 2xx、!ok 或缺 job 必须立即 fail-fast');
  }
  calls.length = 0;
  context.responses = [response(200, {ok: true, job: {status: 'completed'}})];
  const job = await vm.runInContext('pollJob(7)', context);
  assert.equal(job.status, 'completed');
  assert.equal(calls.length, 1);
})().catch(error => { console.error(error); process.exit(1); });
"""
        script = harness + "\nconst source = " + json.dumps(match.group(1)) + ";\nvm.runInContext(source, context);\n" + scenario
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
    disabled: false, type: '', listeners: {},
    classList: {add(){}, remove(){}},
    appendChild(...nodes){ this.children.push(...nodes); this.childNodes.push(...nodes); },
    replaceChildren(...nodes){ this.children = [...nodes]; this.childNodes = [...nodes]; },
    addEventListener(type, fn){ this.listeners[type] = fn; },
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
  const calls = {access: 0, failure: 0, requests: [], summaries: [], replay: 0};
  const timers = new Map();
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
  const context = vm.createContext({
    console, document, JOB_ID: 1, TS_CODE: '000001.SZ', STATUS_LABEL: {}, AbortController,
    Date: {now(){ return now; }},
    $(selector){ return document.querySelector(selector); },
    apiFetch(url, options){ calls.requests.push({url, options}); return fetchImpl(url, options); },
    showAccessFallback(target){ calls.access += 1; target.replaceChildren(symbolEl()); },
    showLoadFailure(target, retry){ calls.failure += 1; calls.retry = retry; target.replaceChildren(symbolEl()); },
    setTimeout(fn, delay){ const id = nextTimer++; timers.set(id, {fn, at: now + delay}); return id; },
    clearTimeout(id){ timers.delete(id); },
    renderSummary(summary){ calls.summaries.push(summary); }, renderEquity(){}, renderWear(){}, renderRisk(){}, renderKline(){},
    initKlineReplay(){ calls.replay += 1; }, table(){}, pct(){ return ''; },
  });
  return {
    context, calls, timers, root, elements,
    setNow(value){ now = value; },
    async runNextTimer(){
      const entry = [...timers.entries()].sort((a, b) => a[1].at - b[1].at)[0];
      assert.ok(entry, '必须存在可执行的 timeout');
      timers.delete(entry[0]);
      now = Math.max(now, entry[1].at);
      return entry[1].fn();
    },
    generateButton(){
      return elements['sym-note'].children.find(node => node.id === 'btn-gen') || elements['btn-gen'];
    },
  };
}
"""


def _run_symbol_js(html: str, scenario: str) -> None:
    match = re.search(
        r"((?:const SYMBOL_POLL_INTERVAL_MS[\s\S]*?)?async function load\(\)\{.*\})(?=\n\n// FRM-SYMBOL)",
        html,
        re.S,
    )
    assert match, "未找到个股详情状态机脚本"
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    script = _SYMBOL_JS_HARNESS + "\nconst source = " + json.dumps(match.group(1)) + ";\n" + scenario
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


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
  vm.runInContext('symbolActiveSince = 1000', hardDeadline.context);
  hardDeadline.setNow(1000 + 5 * 60 * 1000 - 100);
  const last = vm.runInContext('pollGen()', hardDeadline.context);
  await hardDeadline.runNextTimer();
  await last;
  assert.equal(hardDeadline.calls.failure, 1, 'pending 也受包含网络等待的5分钟硬上限约束');
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
  await vm.runInContext('pollGen()', h.context);
  assert.equal(h.timers.size, 1);
  await vm.runInContext('retryGen()', h.context);
  await vm.runInContext('retryGen()', h.context);
  assert.equal(h.timers.size, 1, '重复重试仍只能有一个 timer');
  h.setNow(1000 + 5 * 60 * 1000);
  await vm.runInContext('pollGen()', h.context);
  assert.equal(h.timers.size, 0);
  assert.equal(h.calls.failure, 1, '总等待超时必须显示失败');
  assert.equal(typeof h.calls.retry, 'function');
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
            "apiFetch('/api/results/' + JOB_ID + '/summary', {redirectOn401:false})",
            "showAccessFallback(document.querySelector('.container'))",
            "showLoadFailure(document.querySelector('.container'), retryPoll)",
            "已暂停自动刷新",
            "clearPollTimer()",
            "pollInFlight",
            "if (jobData.readonly) return;",
            "tagResp.status === 404",
        ):
            assert marker in html

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
        _run_job_js(html, r"(async function loadRisk\(\)\{.*?\})(?=\nfunction renderRisk)", r"""
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
