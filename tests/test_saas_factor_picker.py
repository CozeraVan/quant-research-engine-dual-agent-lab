"""QRE-SAAS-FACTOR-PICKER-MODAL 自选因子三栏弹窗选择器测试。

数据契约（本文件的守护对象）：
- `.wz-left` / `.wz-rfield` 仍是唯一值来源（readGroup / snapshotWzArea / usedFactors /
  YAML 预览 / 固定值切换 / 策略还原口径全部不变），原三级 select 降级为隐藏数据字段；
- 新增按钮只负责显示当前「大类 / 子类 / 因子」并打开弹窗，不承载任何策略状态；
- 弹窗复用 `FACTOR_OPTIONS` / `factorGroups()` / `factorSubs()`，不新增 API 或依赖。

Node VM 用例覆盖：打开 → 父子级联动 → 最终因子写回隐藏 select、按钮文本更新、
派发一次 change、关闭并归还焦点；连续开关不重复创建弹窗；Esc / 遮罩只关不改值；
搜索过滤 / 清空恢复 / 空态 / 搜索结果选中；向导既有回归（条件增删、AND/OR、
固定值、快照与还原）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW_HTML = ROOT / "src/quant_research_engine/gui/saas/templates/new.html"
LAB_CSS = ROOT / "src/quant_research_engine/gui/static/lab-theme.css"

# 待测脚本区间：从因子目录状态声明到兜底校验之前（含 catalog/Groups/Subs/
# syncFactorSelect/makeFactorSelect/setFactorSelectValue/向导 DOM/readGroup/
# snapshotWzArea/restoreWizardState/usedFactors/refreshWizard/prefill）。
_SRC_START = "let FACTOR_OPTIONS = []"
_SRC_END = "// ---------- 缺因子兜底校验"

# 与 new.html 弹窗结构一致的最小 DOM 底座（真机结构由静态断言单独守护）
_DOM_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function descendants(node, out){
  out = out || [];
  (node.children || []).forEach(c => { out.push(c); descendants(c, out); });
  return out;
}
function simpleMatch(el, part){
  if (part === '*') return true;
  if (part[0] === '#') return el.id === part.slice(1);
  if (part[0] === '.') return String(el.className || '').split(/\s+/).indexOf(part.slice(1)) >= 0;
  if (part[0] === '['){ const name = part.slice(1, -1).split('=')[0]; return el[name] != null && el[name] !== ''; }
  return el.tagName === part.toUpperCase();
}
function queryAll(root, selector){
  const parts = String(selector).trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return [];
  return descendants(root).filter(el => {
    if (!simpleMatch(el, parts[parts.length - 1])) return false;
    let node = el.parentElement, i = parts.length - 2;
    while (node && i >= 0){ if (simpleMatch(node, parts[i])) i--; node = node.parentElement; }
    return i < 0;
  });
}
function createDom(){
  const byId = {};
  const doc = {
    activeElement: null, _listeners: {}, children: [], childNodes: [], tagName: '#document',
    appendChild(n){ this.children.push(n); this.childNodes.push(n); n.parentElement = this; return n; },
    addEventListener(type, fn){ (this._listeners[type] ||= []).push(fn); },
    dispatchEvent(ev){ (this._listeners[ev.type] || []).slice().forEach(fn => fn(ev)); return true; },
    createElement(tag){ return mkEl(tag); },
    createTextNode(text){ const n = mkEl('#text'); n.textContent = String(text); return n; },
    getElementById(id){ return byId[id] || null; },
    querySelector(sel){ return queryAll(this, sel)[0] || null; },
    querySelectorAll(sel){ return queryAll(this, sel); },
  };
  function mkEl(tag){
    const el = {
      tagName: String(tag || 'div').toUpperCase(), id: '', className: '',
      textContent: '', value: '', title: '', type: '', hidden: false, disabled: false,
      checked: false, placeholder: '', style: {}, dataset: {}, children: [], childNodes: [],
      parentElement: null, _listeners: {},
      appendChild(n){ this.children.push(n); this.childNodes.push(n); n.parentElement = this; return n; },
      remove(){ if (this.parentElement){ const i = this.parentElement.children.indexOf(this); if (i >= 0) this.parentElement.children.splice(i, 1); this.parentElement = null; } },
      replaceChildren(...nodes){ this.children = []; this.childNodes = []; nodes.forEach(n => this.appendChild(n)); },
      addEventListener(type, fn){ (this._listeners[type] ||= []).push(fn); },
      removeEventListener(type, fn){ const l = this._listeners[type] || []; const i = l.indexOf(fn); if (i >= 0) l.splice(i, 1); },
      dispatchEvent(ev){ (this._listeners[ev.type] || []).slice().forEach(fn => fn.call(this, ev)); return true; },
      setAttribute(k, v){ if (k === 'class') this.className = String(v); else if (k === 'id') this.id = String(v); else this[k] = String(v); },
      getAttribute(k){ return this[k] === undefined ? null : this[k]; },
      focus(){ doc.activeElement = this; },
      blur(){ if (doc.activeElement === this) doc.activeElement = null; },
      querySelector(sel){ return queryAll(this, sel)[0] || null; },
      querySelectorAll(sel){ return queryAll(this, sel); },
      contains(n){ return descendants(this).indexOf(n) >= 0; },
      scrollIntoView(){},
    };
    let html = '';
    Object.defineProperty(el, 'innerHTML', {
      get(){ return html; },
      set(v){ html = String(v); if (html === ''){ el.children = []; el.childNodes = []; } },
    });
    const classes = () => String(el.className || '').split(/\s+/).filter(Boolean);
    el.classList = {
      add(...cs){ const s = new Set(classes()); cs.forEach(c => s.add(c)); el.className = [...s].join(' '); },
      remove(...cs){ const s = new Set(classes()); cs.forEach(c => s.delete(c)); el.className = [...s].join(' '); },
      toggle(c, force){ const s = new Set(classes()); const want = force === undefined ? !s.has(c) : !!force; if (want) s.add(c); else s.delete(c); el.className = [...s].join(' '); return want; },
      contains(c){ return classes().indexOf(c) >= 0; },
    };
    return el;
  }
  function reg(tag, id, cls, parent, hidden){
    const el = mkEl(tag);
    if (id) el.id = id;
    if (cls) el.className = cls;
    if (hidden) el.hidden = true;
    (parent || doc).appendChild(el);
    byId[id] = el;
    return el;
  }
  reg('p', 'wz-factor-status');
  reg('div', 'wz-entry', 'cond-groups');
  reg('div', 'wz-exit', 'cond-groups');
  reg('input', 'p-sname');
  const mask = reg('div', 'factor-picker-modal', 'modal-mask');
  const cols = reg('div', 'factor-picker-cols', 'fp-cols', mask);
  reg('div', 'fp-col-group', 'fp-col', cols);
  reg('div', 'fp-list-group', 'fp-list', cols.children[cols.children.length - 1]);
  reg('div', 'fp-col-sub', 'fp-col', cols);
  reg('div', 'fp-list-sub', 'fp-list', cols.children[cols.children.length - 1]);
  reg('div', 'fp-col-factor', 'fp-col', cols);
  reg('div', 'fp-list-factor', 'fp-list', cols.children[cols.children.length - 1]);
  reg('div', 'factor-picker-results', 'fp-results', mask, true);
  reg('p', 'factor-picker-empty', 'fp-empty', mask, true);
  reg('input', 'factor-picker-search', 'fp-search', mask);
  reg('button', 'factor-picker-close', 'fp-close', mask);
  return {doc, byId};
}
function createHarness(groups){
  const {doc, byId} = createDom();
  const calls = {yaml: [], refresh: 0, alerts: [], factors: 0};
  const context = vm.createContext({
    console, document: doc, window: {}, Event, URLSearchParams,
    alert(msg){ calls.alerts.push(String(msg)); },
    $: (s, r) => (r || doc).querySelector(s),
    $$: (s, r) => Array.prototype.slice.call((r || doc).querySelectorAll(s)),
    esc(s){ return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;'); },
    maybeAutoName(){ calls.refresh += 0; },
    setYaml(y){ calls.yaml.push(y); },
    apiFetch(url){
      calls.factors += 1;
      return Promise.resolve({status: 200, ok: true, json: async () => ({ok: true, groups})});
    },
  });
  return {context, calls, doc, byId};
}
"""

_FACTOR_GROUPS = json.dumps([
    {"group": "trend", "label": "趋势", "items": [
        {"label": "5日均线", "column": "ema_5", "table": "factors.stock_daily_trend"},
        {"label": "10日均线", "column": "ema_10", "table": "factors.stock_daily_trend"},
        {"label": "200日均线", "column": "ema_200", "table": "factors.stock_daily_trend"},
    ]},
    {"group": "momentum", "label": "动量", "items": [
        {"label": "MACD", "column": "macd", "table": "factors.stock_daily_momentum"},
        {"label": "MACD信号线", "column": "macd_signal", "table": "factors.stock_daily_momentum"},
    ]},
])


def _node():
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        import pytest

        pytest.skip("node 不可用")
    return node


def _wizard_source(page: str) -> str:
    start = page.index(_SRC_START)
    end = page.index(_SRC_END)
    source = page[start:end]
    assert "function makeFactorSelect(" in source
    assert "function readGroup(" in source
    assert "function snapshotWzArea(" in source
    return source


def _run_picker_js(page: str, scenario: str) -> None:
    source = _wizard_source(page)
    script = (
        _DOM_HARNESS
        + "\nconst FACTOR_GROUPS = " + _FACTOR_GROUPS + ";\n"
        + "const source = " + json.dumps(source) + ";\n"
        + scenario
    )
    result = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


class TestPickerMarkup:
    """弹窗结构、按钮与隐藏数据字段的静态契约。"""

    def test_modal_markup_and_columns(self):
        page = NEW_HTML.read_text()
        assert 'id="factor-picker-modal"' in page
        assert 'id="factor-picker-search"' in page
        assert 'id="factor-picker-close"' in page
        assert 'id="fp-list-group"' in page
        assert 'id="fp-list-sub"' in page
        assert 'id="fp-list-factor"' in page
        assert 'id="factor-picker-results"' in page
        assert 'id="factor-picker-empty"' in page
        # 弹层复用既有 modal 组件与紫色主题，无新色相/新依赖
        assert 'class="modal-mask" id="factor-picker-modal"' in page
        assert 'role="dialog"' in page and 'aria-modal="true"' in page
        assert 'aria-label="选择因子"' in page
        assert "setAttribute('aria-haspopup', 'dialog')" in page

    def test_hidden_selects_keep_value_contract(self):
        page = NEW_HTML.read_text()
        # 隐藏数据字段 + 按钮：select 保留 .wz-left/.wz-rfield 类名与 change 监听
        assert "wrap.className = 'wz-factsel factor-picker-field'" in page
        assert "const sel = document.createElement('select'); sel.className = cls;" in page
        assert "sel.addEventListener('change', refreshWizard);" in page
        assert "btn.className = 'factor-select-btn'" in page
        assert ".wz-left" in page and ".wz-rfield" in page
        css = LAB_CSS.read_text()
        assert ".factor-picker-field select{display:none}" in css

    def test_picker_functions_exist(self):
        page = NEW_HTML.read_text()
        for fn in ("function openFactorPicker(wrap)", "function closeFactorPicker()",
                   "function syncFactorPickerButton(wrap)", "function fpRender()"):
            assert fn in page, fn
        # Esc / 遮罩 / 关闭按钮 / 焦点归还
        assert "key === 'Escape'" in page
        assert "e.target === this) closeFactorPicker()" in page
        assert "fpLastFocus.focus()" in page
        assert "search.focus()" in page

    def test_no_new_dependency_or_api(self):
        page = NEW_HTML.read_text()
        for banned in ("cdn", "unpkg", "jsdelivr", "axios"):
            assert banned not in page.lower(), banned
        # 不得新增裸 fetch（既有 apiFetch 封装除外）
        assert re.search(r"(?<!api)(?<![A-Za-z])fetch\(", page) is None
        # 弹窗不新增接口调用（只复用既有 /api/saas/factors 目录加载结果）
        start = page.index("<!-- 自选因子三栏弹窗选择器")
        end = page.index("{% endblock %}\n{% block scripts %}")
        picker = page[start:end]
        assert "apiFetch" not in picker
        assert "fetch(" not in picker


class TestPickerInteraction:
    """Node VM：弹窗三级联动、写回契约、Esc/遮罩/焦点与搜索。"""

    def test_open_pick_write_back_and_focus_return(self):
        _run_picker_js(NEW_HTML.read_text(), r"""
(async () => {
  const h = createHarness(FACTOR_GROUPS);
  vm.runInContext(source, h.context);
  await vm.runInContext('loadFactorCatalog()', h.context);
  const doc = h.doc;

  const wrap = doc.querySelector('#wz-entry .cond-group .wz-cond .wz-factsel');
  assert.ok(wrap, '默认条件行应包含因子字段');
  doc.querySelector('#wz-entry .wz-op').value = '>';  // 用朴素比较，断言聚焦因子选择
  const sel = wrap.querySelectorAll('select')[2];
  const btn = wrap.querySelector('.factor-select-btn');
  assert.equal(sel.className, 'wz-left', '隐藏数据字段必须保留 .wz-left');
  assert.equal(sel.value, 'ema_5');
  assert.equal(btn.textContent, '趋势 / trend / 5日均线', '按钮显示大类/子类/因子');
  let changes = 0;
  sel.addEventListener('change', () => { changes += 1; });

  // 打开弹窗：焦点进搜索、三栏渲染、连续打开不重复创建
  btn.dispatchEvent({type: 'click'});
  const mask = doc.getElementById('factor-picker-modal');
  assert.ok(mask.classList.contains('show'), '点击按钮应打开弹窗');
  assert.equal(doc.activeElement, doc.getElementById('factor-picker-search'), '焦点应进入搜索框');
  assert.equal(doc.getElementById('factor-picker-cols').hidden, false);
  assert.equal(doc.getElementById('factor-picker-results').hidden, true);
  const groupItems = doc.getElementById('fp-list-group').children.map(b => b.textContent);
  assert.deepEqual(groupItems, ['趋势', '动量']);
  const subItems = doc.getElementById('fp-list-sub').children.map(b => b.textContent);
  assert.deepEqual(subItems, ['trend']);
  const factorItems = doc.getElementById('fp-list-factor').children.map(b => b.textContent);
  assert.deepEqual(factorItems, ['5日均线', '10日均线', '200日均线']);
  assert.equal(doc.getElementById('fp-list-factor').children[0].className, 'fp-item sel', '当前值应有选中态');

  btn.dispatchEvent({type: 'click'});
  const fpItemCount = () => doc.querySelectorAll('#factor-picker-modal .fp-item').length;
  const opened = fpItemCount();
  assert.ok(opened > 0, '弹窗应渲染因子项');
  btn.dispatchEvent({type: 'click'});
  assert.equal(fpItemCount(), opened, '连续打开不得重复创建弹窗节点');
  assert.equal(doc.getElementById('fp-list-group').children.length, 2);
  // 父子级联动：点大类 → 子类/因子栏刷新
  doc.getElementById('fp-list-group').children[1].dispatchEvent({type: 'click'});
  assert.ok(mask.classList.contains('show'), '点父级只更新下级，不关闭');
  assert.deepEqual(doc.getElementById('fp-list-sub').children.map(b => b.textContent), ['momentum']);
  assert.deepEqual(doc.getElementById('fp-list-factor').children.map(b => b.textContent), ['MACD', 'MACD信号线']);
  assert.equal(sel.value, 'ema_5', '点父级不得改值');
  assert.equal(changes, 0, '点父级不得派发 change');

  // 最终因子：写回隐藏 select、按钮更新、派发一次 change、关闭并归还焦点
  doc.getElementById('fp-list-factor').children[0].dispatchEvent({type: 'click'});
  assert.equal(sel.value, 'macd');
  assert.equal(btn.textContent, '动量 / momentum / MACD');
  assert.equal(changes, 1, '最终选择必须且只能派发一次 change');
  assert.equal(mask.classList.contains('show'), false, '选完因子后弹窗关闭');
  assert.equal(doc.activeElement, btn, '关闭后焦点回到原按钮');
  // 数据契约：readGroup / 快照 / YAML 口径不变
  const snap = vm.runInContext("snapshotWzArea('entry')", h.context);
  assert.equal(snap.groups[0].conds[0].left, 'macd');
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(macd > ema_200)');
  const yaml = h.calls.yaml[h.calls.yaml.length - 1];
  assert.match(yaml, /entry: "\(macd > ema_200\)"/);
  assert.match(yaml, /macd: factors\.stock_daily_momentum\.macd/);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_esc_and_mask_close_without_value_change(self):
        _run_picker_js(NEW_HTML.read_text(), r"""
(async () => {
  const h = createHarness(FACTOR_GROUPS);
  vm.runInContext(source, h.context);
  await vm.runInContext('loadFactorCatalog()', h.context);
  const doc = h.doc;
  const wrap = doc.querySelector('#wz-entry .cond-group .wz-cond .wz-factsel');
  const sel = wrap.querySelectorAll('select')[2];
  const btn = wrap.querySelector('.factor-select-btn');
  let changes = 0;
  sel.addEventListener('change', () => { changes += 1; });
  const mask = doc.getElementById('factor-picker-modal');

  btn.dispatchEvent({type: 'click'});
  doc.dispatchEvent({type: 'keydown', key: 'Escape'});
  assert.equal(mask.classList.contains('show'), false, 'Esc 必须关闭弹窗');
  assert.equal(sel.value, 'ema_5', 'Esc 只关不改值');
  assert.equal(changes, 0);
  assert.equal(doc.activeElement, btn, 'Esc 关闭后焦点回到按钮');

  btn.dispatchEvent({type: 'click'});
  mask.dispatchEvent({type: 'click', target: mask});
  assert.equal(mask.classList.contains('show'), false, '点遮罩必须关闭');
  assert.equal(sel.value, 'ema_5');
  assert.equal(changes, 0);
  assert.equal(doc.activeElement, btn, '遮罩关闭后焦点回到按钮');

  btn.dispatchEvent({type: 'click'});
  doc.getElementById('factor-picker-close').dispatchEvent({type: 'click'});
  assert.equal(mask.classList.contains('show'), false, '关闭按钮必须关闭');
  assert.equal(changes, 0);

  // 弹窗关闭时按键不得影响值
  doc.dispatchEvent({type: 'keydown', key: 'Escape'});
  assert.equal(sel.value, 'ema_5');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_catalog_not_ready_keeps_existing_error_prompt(self):
        _run_picker_js(NEW_HTML.read_text(), r"""
(async () => {
  const h = createHarness([]);
  vm.runInContext(source, h.context);
  // 目录加载失败：不打开弹窗，沿用既有错误提示
  h.context.apiFetch = () => Promise.resolve({status: 200, ok: true, json: async () => ({ok: false})});
  await vm.runInContext('loadFactorCatalog()', h.context);
  assert.equal(h.byId['factor-picker-modal'].classList.contains('show'), false);
  assert.match(h.byId['wz-factor-status'].innerHTML, /因子库不可用/);
  vm.runInContext("wzAddGroup('entry')", h.context);
  const wrap = h.doc.querySelector('#wz-entry .cond-group .wz-cond .wz-factsel');
  const btn = wrap.querySelector('.factor-select-btn');
  assert.equal(btn.textContent, '选择因子', '无当前值时按钮显示占位文案');
  btn.dispatchEvent({type: 'click'});
  assert.equal(h.byId['factor-picker-modal'].classList.contains('show'), false, '目录未就绪不得打开弹窗');
  assert.match(h.byId['wz-factor-status'].innerHTML, /因子目录未就绪/);
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_search_filters_and_restores_columns(self):
        _run_picker_js(NEW_HTML.read_text(), r"""
(async () => {
  const h = createHarness(FACTOR_GROUPS);
  vm.runInContext(source, h.context);
  await vm.runInContext('loadFactorCatalog()', h.context);
  const doc = h.doc;
  const wrap = doc.querySelector('#wz-entry .cond-group .wz-cond .wz-factsel');
  const sel = wrap.querySelectorAll('select')[2];
  const btn = wrap.querySelector('.factor-select-btn');
  btn.dispatchEvent({type: 'click'});
  const search = doc.getElementById('factor-picker-search');
  const cols = doc.getElementById('factor-picker-cols');
  const results = doc.getElementById('factor-picker-results');
  const empty = doc.getElementById('factor-picker-empty');

  // 按字段名搜索（label / value / group / sub 均可命中）
  search.value = 'ema_10';
  search.dispatchEvent({type: 'input'});
  assert.equal(cols.hidden, true, '搜索时隐藏三栏');
  assert.equal(results.hidden, false);
  assert.deepEqual(results.children.map(b => b.textContent), ['趋势 / trend / 10日均线']);
  assert.equal(empty.hidden, true);

  // 中文标签 + 大类名搜索
  search.value = 'MACD';
  search.dispatchEvent({type: 'input'});
  assert.deepEqual(results.children.map(b => b.textContent), ['动量 / momentum / MACD', '动量 / momentum / MACD信号线']);

  // 空态
  search.value = '不存在的因子';
  search.dispatchEvent({type: 'input'});
  assert.equal(empty.hidden, false, '无结果须显示空态');
  assert.equal(results.children.length, 0);

  // 清空恢复三栏
  search.value = '';
  search.dispatchEvent({type: 'input'});
  assert.equal(cols.hidden, false);
  assert.equal(results.hidden, true);
  assert.equal(results.children.length, 0, '切回三栏必须清空搜索结果，避免隐藏节点残留焦点链');
  assert.equal(doc.getElementById('fp-list-group').children.length, 2);

  // 搜索结果选中：写回并关闭，三栏与按钮一致
  search.value = 'macd';
  search.dispatchEvent({type: 'input'});
  results.children[1].dispatchEvent({type: 'click'});
  assert.equal(sel.value, 'macd_signal');
  assert.equal(btn.textContent, '动量 / momentum / MACD信号线');
  assert.equal(h.byId['factor-picker-modal'].classList.contains('show'), false);
  // 再次打开：三栏定位到新值
  btn.dispatchEvent({type: 'click'});
  search.value = '';
  search.dispatchEvent({type: 'input'});
  assert.deepEqual(doc.getElementById('fp-list-sub').children.map(b => b.textContent), ['momentum']);
  assert.equal(doc.getElementById('fp-list-factor').children[1].className, 'fp-item sel');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_wizard_regressions_fixed_value_groups_and_restore(self):
        _run_picker_js(NEW_HTML.read_text(), r"""
(async () => {
  const h = createHarness(FACTOR_GROUPS);
  vm.runInContext(source, h.context);
  await vm.runInContext('loadFactorCatalog()', h.context);
  const doc = h.doc;

  // 固定值切换：右因子字段隐藏、readGroup 取数值
  const row = doc.querySelector('#wz-entry .wz-cond');
  row.querySelector('.wz-op').value = '>';
  const isfixed = row.querySelector('.wz-isfixed');
  isfixed.checked = true;
  isfixed.dispatchEvent({type: 'change'});
  row.querySelector('.wz-rnum').value = '30';
  row.querySelector('.wz-rnum').dispatchEvent({type: 'input'});
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(ema_5 > 30)');
  assert.equal(vm.runInContext("snapshotWzArea('entry').groups[0].conds[0].fixed", h.context), '30');
  isfixed.checked = false;
  isfixed.dispatchEvent({type: 'change'});
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(ema_5 > ema_200)');

  // 右因子也能通过弹窗选择（数据契约 .wz-rfield 不变）
  const rightWrap = row.querySelectorAll('.wz-factsel')[1];
  assert.equal(rightWrap.querySelectorAll('select')[2].className, 'wz-rfield');
  rightWrap.querySelector('.factor-select-btn').dispatchEvent({type: 'click'});
  doc.getElementById('fp-list-group').children[1].dispatchEvent({type: 'click'});
  doc.getElementById('fp-list-factor').children[1].dispatchEvent({type: 'click'});
  assert.equal(rightWrap.querySelectorAll('select')[2].value, 'macd_signal');
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(ema_5 > macd_signal)');

  // 条件增删 + AND/OR
  vm.runInContext("wzAddCondition('entry', document.getElementById('wz-entry').querySelector('.cond-group'))", h.context);
  const rows = doc.querySelectorAll('#wz-entry .wz-cond');
  assert.equal(rows.length, 2);
  rows[1].querySelector('.wz-left').value = 'ema_10';
  rows[1].querySelector('.wz-op').value = '>';
  rows[1].querySelector('.wz-rfield').value = 'ema_200';
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context),
    '(ema_5 > macd_signal) and (ema_10 > ema_200)');
  const comb = doc.querySelector('#wz-entry .cond-group .comb-toggle');
  comb.dataset.comb = 'or';
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context),
    '(ema_5 > macd_signal) or (ema_10 > ema_200)');
  rows[1].remove();
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(ema_5 > macd_signal)');

  // 快照 → 还原：值不变
  const snap = vm.runInContext("collectWizardState()", h.context);
  vm.runInContext("restoreWizardState(" + JSON.stringify(snap) + ")", h.context);
  const restored = vm.runInContext("collectWizardState()", h.context);
  assert.deepEqual(restored, snap);
  assert.equal(vm.runInContext("readGroup('entry').expression", h.context), '(ema_5 > macd_signal)');
  const restoredBtn = doc.querySelector('#wz-entry .cond-group .wz-cond .factor-select-btn');
  assert.equal(restoredBtn.textContent, '趋势 / trend / 5日均线');
})().catch(error => { console.error(error); process.exit(1); });
""")

    def test_render_new_page_inline_script_parses(self):
        """渲染后的 new.html 内联脚本必须可被 Node 解析（语法回归防线）。"""
        page = NEW_HTML.read_text()
        scripts = re.findall(r"<script>([\s\S]*?)</script>", page)
        target = next(s for s in scripts if _SRC_START in s)
        script = (
            "const fs = require('node:fs');\n"
            "const vm = require('node:vm');\n"
            "const src = " + json.dumps(target) + ";\n"
            "new vm.Script(src, {filename: 'new.html'});\n"
            "console.log('parse ok');\n"
        )
        result = subprocess.run([_node(), "-e", script], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "parse ok" in result.stdout
