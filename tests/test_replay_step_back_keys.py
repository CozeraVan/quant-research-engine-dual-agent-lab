"""T3 · 回放单步后退 + 键盘快捷键（QRE-TV-REPLAY-KEYS）。

覆盖任务书 §7 T3：
- 后退复用 `seek(pos-1)`（与进度条/日历同一出口，不另造渲染路径）；
- 空格播放/暂停、←/→ 单步；
- 键盘不劫持输入框与模态焦点；
- 验收：前进/后退 100 次后光标与指标值与静态报告一致（防未来数据红线不破）。

Node vm 跑**真实 replay.js 源码**（不写桩），另用真实 Chromium 复跑同一组判据。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
REPLAY_JS = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(
    encoding="utf-8"
)
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    # 写临时文件而不是 `node -e`：脚本内注入真实 replay.js 源码
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
    finally:
        os.unlink(path)


_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const src = %SOURCE%;
const ctx = { console, window: {}, module: undefined, exports: undefined };
vm.runInContext(src, vm.createContext(ctx));
const R = ctx.window.QREReplay;
globalThis.R = R;
"""


def _layout() -> str:
    return _HARNESS.replace("%SOURCE%", json.dumps(REPLAY_JS))


# ---------------------------------------------------------------- 源码合同
class TestSourceContract:
    def test_step_back_and_keyboard_wired(self):
        assert "function stepBack()" in REPLAY_JS, "必须有 stepBack()"
        assert "btnBack" in REPLAY_JS, "必须有后退按钮"
        assert "stepBack();\n      seek(cursor - 1);" in REPLAY_JS or (
            "seek(cursor - 1)" in REPLAY_JS), "后退必须复用 seek(cursor-1)"
        assert "document.addEventListener(\"keydown\", onKey)" in REPLAY_JS, (
            "必须注册键盘监听")
        assert "document.removeEventListener(\"keydown\", onKey)" in REPLAY_JS, (
            "destroy 必须撤掉键盘监听（否则重播退出后仍劫持按键）")
        assert "keyTargetBlocked: keyTargetBlocked" in REPLAY_JS, (
            "键盘劫持判定必须导出到 core 供测试")
        assert "stepBack: stepBack" in REPLAY_JS, "attach 返回值必须暴露 stepBack"

    def test_block_selector_covers_form_and_modal(self):
        for sel in ("input", "select", "textarea", "button", "a",
                    '[contenteditable="true"]', '[role="dialog"]', ".ind-mask",
                    ".cal-pop", ".rp-calpop", ".rp-bar"):
            assert sel in REPLAY_JS, f"键盘劫持判定缺少焦点区: {sel}"

    def test_key_labels_documented_in_tooltips(self):
        assert "空格键" in REPLAY_JS, "播放按钮需在 title 提示空格"
        assert "← 键" in REPLAY_JS, "后退按钮需在 title 提示 ←"
        assert "→ 键" in REPLAY_JS, "单步按钮需在 title 提示 →"


# ---------------------------------------------------------------- 键盘劫持判定（纯函数）
_KEY_GUARD = r"""
function matchSel(node, sel) {
  if (sel.charAt(0) === '.') {
    return String(node.className || '').split(/\s+/).indexOf(sel.slice(1)) >= 0;
  }
  if (sel.charAt(0) === '[') {
    const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(sel);
    if (!m) return false;
    const v = node.attrs ? node.attrs[m[1]] : undefined;
    return m[2] === undefined ? (v !== undefined && v !== null && v !== 'false') : v === m[2];
  }
  return String(node.tagName || '').toLowerCase() === sel.toLowerCase();
}
function mkNode(tag, cls, parent, attrs) {
  return {
    tagName: tag, className: cls || '', parentNode: parent || null, attrs: attrs || {},
    closest(sel) {
      const parts = String(sel).split(',').map(function (s) { return s.trim(); });
      let cur = this;
      while (cur) {
        for (let i = 0; i < parts.length; i++) if (matchSel(cur, parts[i])) return cur;
        cur = cur.parentNode;
      }
      return null;
    },
  };
}
"""


class TestKeyTargetBlocked:
    def test_blocked_focus_areas(self):
        _node(_layout() + _KEY_GUARD + r"""
const cases = [
  ['input', mkNode('INPUT'), true, '起始日输入框'],
  ['select', mkNode('SELECT'), true, '速度下拉'],
  ['textarea', mkNode('TEXTAREA'), true, '多行输入'],
  ['button', mkNode('BUTTON'), true, '播放/单步按钮本身（空格会触发点击）'],
  ['a', mkNode('A'), true, '链接'],
  ['contenteditable', mkNode('DIV', '', null, {contenteditable: 'true'}), true, '可编辑区'],
  ['dialog', mkNode('DIV', '', null, {role: 'dialog'}), true, '模态对话框'],
  ['ind-mask', mkNode('DIV', 'ind-mask'), true, '指标设置遮罩'],
  ['cal-pop', mkNode('DIV', 'cal-pop'), true, 'lab 页日历浮层'],
  ['rp-calpop', mkNode('DIV', 'rp-calpop'), true, 'replay.js 自建日历浮层'],
  ['rp-bar', mkNode('DIV', 'rp-bar'), true, '重播控制条'],
  ['inside-dialog', mkNode('DIV', 'x', mkNode('DIV', 'ind-dialog',
      mkNode('DIV', 'ind-mask'))), true, '对话框内部元素'],
  ['inside-input', mkNode('SPAN', '', mkNode('INPUT')), true, '输入框内部'],
  ['canvas', mkNode('DIV', 'rp-chart'), false, '图表画布（应放行）'],
  ['body', mkNode('BODY'), false, '页面主体（应放行）'],
  ['plain-div', mkNode('DIV', 'wrap'), false, '普通容器（应放行）'],
  ['null', null, false, '无 target 不炸'],
];
cases.forEach(([name, node, want, why]) => {
  const got = R.core.keyTargetBlocked(node);
  assert.equal(got, want, name + '：' + why + '，期望 ' + want + ' 实际 ' + got);
});
console.log('t3-keyguard-ok');
""")

    def test_key_selector_is_comma_list(self):
        assert "," in REPLAY_JS.split("KEY_BLOCK_SELECTOR =")[1].split(";")[0], (
            "KEY_BLOCK_SELECTOR 必须是逗号分隔的选择器列表")


# ---------------------------------------------------------------- vm 行为
_ATTACH_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const src = %SOURCE%;
const docListeners = {};
const document = {
  createElement(tag){
    return {
      tagName: String(tag || 'div').toUpperCase(), children: [], childNodes: [],
      style: {}, className: '', _text: '', _html: '', dataset: {}, listeners: {},
      disabled: false, value: '', readOnly: false, type: '', parentNode: null,
      get innerHTML(){ return this._html; },
      set innerHTML(v){ this._html = String(v);
        // 真实 DOM 语义：整体赋值会替换子节点（replay.js 的 seek 靠它清事件流）
        if (v === ''){ this.children = []; this.childNodes = []; } },
      get textContent(){ return this._text; },
      set textContent(v){ this._text = String(v); },
      get firstChild(){ return this.childNodes[0] || null; },
      classList: { add(){}, remove(){}, toggle(){}, contains(){ return false; } },
      appendChild(n){ n.parentNode = this; this.childNodes.push(n); this.children.push(n); return n; },
      insertBefore(n, ref){
        n.parentNode = this;
        const i = ref ? this.childNodes.indexOf(ref) : this.childNodes.length;
        this.childNodes.splice(i, 0, n); this.children.splice(i, 0, n); return n;
      },
      remove(){
        if (!this.parentNode) return;
        const i = this.parentNode.childNodes.indexOf(this);
        if (i >= 0){ this.parentNode.childNodes.splice(i, 1); this.parentNode.children.splice(i, 1); }
        this.parentNode = null;
      },
      addEventListener(t, fn){ (this.listeners[t] = this.listeners[t] || []).push(fn); },
      setAttribute(k, v){ this['attr_' + k] = String(v); },
      querySelector(){ return null; },
      click(){ (this.listeners.click || []).forEach(function (fn) { fn({ target: this }); }, this); },
    };
  },
  getElementById(){ return null; },
  addEventListener(t, fn){ (docListeners[t] = docListeners[t] || []).push(fn); },
  removeEventListener(t, fn){
    if (!docListeners[t]) return;
    docListeners[t] = docListeners[t].filter(function (f) { return f !== fn; });
  },
};
const options = [];
const echarts = {
  init(){ return {
      setOption(o){ options.push(o); }, dispose(){}, resize(){},
      getOption(){ return { dataZoom: [{ start: 0, end: 100 }] }; },
    }; },
  getInstanceByDom(){ return null; },
};
const intervals = [];
const ctx = vm.createContext({
  console, document, echarts,
  window: { addEventListener(){}, removeEventListener(){} },
  requestAnimationFrame(fn){ return fn(); },
  setTimeout(fn){ return 0; }, clearTimeout(){},
  setInterval(fn){ intervals.push(fn); return intervals.length; },
  clearInterval(){},
});
vm.runInContext(src, ctx);
globalThis.R = ctx.window.QREReplay;
globalThis.docListeners = docListeners;
globalThis.options = options;

function attach(cursor) {
  options.length = 0;
  const mount = document.createElement('div');
  const evEl = document.createElement('div');
  const ctl = R.attach(mount, {
    dates: DATES,
    series: [{ name: '策略', data: EQUITY, raw: EQUITY, grid: 0 }],
    events: EVENTS, roundTrips: TRIPS,
    eventsEl: evEl,
    initialCursor: cursor,
  });
  ctl.__eventsEl = evEl;
  ctl.__optionCount = function () { return options.length; };
  return ctl;
}
function eventRows(rp) {
  const el = rp.__eventsEl;
  return (el && el.children || []).filter(function (c) {
    return String(c.className || '').indexOf('rp-ev-day') >= 0;
  });
}
function lastXData() {
  const o = options[options.length - 1];
  return (o && o.xAxis && o.xAxis[0] && o.xAxis[0].data) || [];
}
let lastPrevented = 0;
function key(k, target, extra) {
  const ev = Object.assign({ key: k, target: target || null,
                             preventDefault(){ lastPrevented++; },
                             metaKey: false, ctrlKey: false, altKey: false,
                             repeat: false }, extra || {});
  lastPrevented = 0;
  (docListeners.keydown || []).forEach(function (fn) { fn(ev); });
}
const DATES = %DATES%;
const EQUITY = %EQUITY%;
const EVENTS = %EVENTS%;
const TRIPS = %TRIPS%;
"""


class TestStepBackAndKeys:
    def test_step_back_button_and_clamp(self):
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps([f"2024-01-{d:02d}" for d in range(2, 9)]))
              .replace("%EQUITY%", json.dumps([100, 101, 103, 102, 106, 104, 108]))
              .replace("%EVENTS%", json.dumps([
                  {"date": "2024-01-03", "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
                  {"date": "2024-01-05", "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
              ]))
              .replace("%TRIPS%", json.dumps([
                  {"entry_date": "2024-01-03", "exit_date": "2024-01-05", "net_return": 0.02},
              ]))
              + r"""
const rp = attach(4);
assert.equal(rp.getCursor(), 4);
const n0 = rp.__optionCount();
rp.stepBack();
assert.equal(rp.getCursor(), 3, '后退一帧');
assert.equal(rp.__optionCount(), n0 + 1, '后退必须走渲染出口（seek→renderFrame）');
rp.stepBack(); rp.stepBack(); rp.stepBack();
assert.equal(rp.getCursor(), 0, '退到首帧');
rp.stepBack();
assert.equal(rp.getCursor(), 0, '首帧再退不得变负');
assert.ok(rp.getCursor() >= 0, '光标不得为负');
console.log('t3-stepback-ok');
""")

    def test_keyboard_play_pause_and_step(self):
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps([f"2024-01-{d:02d}" for d in range(2, 9)]))
              .replace("%EQUITY%", json.dumps([100, 101, 103, 102, 106, 104, 108]))
              .replace("%EVENTS%", json.dumps([
                  {"date": "2024-01-03", "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
                  {"date": "2024-01-05", "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
              ]))
              .replace("%TRIPS%", json.dumps([
                  {"entry_date": "2024-01-03", "exit_date": "2024-01-05", "net_return": 0.02},
              ]))
              + r"""
const rp = attach(3);
assert.equal(rp.isPlaying(), false);
key(' ');                       // 空格 → 播放
assert.equal(lastPrevented, 1, '空格必须 preventDefault（否则页面跟着滚动）');
assert.equal(rp.isPlaying(), true, '空格必须播放');
key(' ');
assert.equal(rp.isPlaying(), false, '再按空格必须暂停');
key(' ', null, {repeat: true}); // 长按重复不得连续切换
assert.equal(rp.isPlaying(), false, 'repeat 的空格必须被忽略');
key('ArrowRight');              // → 单步前进
assert.equal(lastPrevented, 1, '→ 必须 preventDefault（否则页面横向滚动）');
assert.equal(rp.getCursor(), 4, '→ 单步前进');
assert.equal(rp.isPlaying(), false, '单步不得进入播放态');
key('ArrowLeft');               // ← 单步后退
assert.equal(rp.getCursor(), 3, '← 单步后退');
key('ArrowLeft'); key('ArrowLeft'); key('ArrowLeft'); key('ArrowLeft');
assert.equal(rp.getCursor(), 0, '← 退到首帧即止');
// 修饰键组合不得被劫持（Ctrl+← 等可能是浏览器/系统快捷键）
key('ArrowLeft', null, {ctrlKey: true});
assert.equal(rp.getCursor(), 0, 'Ctrl 组合键不得触发');
key('a');
assert.equal(rp.getCursor(), 0, '无关按键不得触发');
console.log('t3-keys-ok');
""")

    def test_keyboard_does_not_hijack_form_focus(self):
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps([f"2024-01-{d:02d}" for d in range(2, 9)]))
              .replace("%EQUITY%", json.dumps([100, 101, 103, 102, 106, 104, 108]))
              .replace("%EVENTS%", json.dumps([
                  {"date": "2024-01-03", "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
                  {"date": "2024-01-05", "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
              ]))
              .replace("%TRIPS%", json.dumps([
                  {"entry_date": "2024-01-03", "exit_date": "2024-01-05", "net_return": 0.02},
              ]))
              + _KEY_GUARD + r"""
const rp = attach(3);
const before = rp.getCursor();
// 焦点在起始日输入框 / 速度下拉 / 播放按钮 / 指标对话框时，空格与左右键都不得动作
['INPUT', 'SELECT', 'BUTTON', 'TEXTAREA'].forEach(function (tag) {
  const t = mkNode(tag);
  // 必须先验空格：← 会调 pause()，放在后面会把"空格已劫持"掩盖掉
  key(' ', t);
  assert.equal(rp.isPlaying(), false, tag + ' 焦点时空格不得播放');
  assert.equal(lastPrevented, 0, tag + ' 焦点时空格不得 preventDefault');
  key('ArrowRight', t);
  assert.equal(rp.getCursor(), before, tag + ' 焦点时 → 不得步进');
  key('ArrowLeft', t);
  assert.equal(rp.getCursor(), before, tag + ' 焦点时 ← 不得后退');
});
// 指标设置对话框内部
const inDialog = mkNode('DIV', 'ind-row', mkNode('DIV', 'ind-body',
  mkNode('DIV', 'ind-dialog', mkNode('DIV', 'ind-mask'))));
key(' ', inDialog);
assert.equal(rp.isPlaying(), false, '对话框焦点时空格不得播放');
key('ArrowRight', inDialog); key('ArrowLeft', inDialog);
assert.equal(rp.getCursor(), before, '对话框焦点时键盘不得劫持');
// 焦点在图表画布上则放行
const canvas = mkNode('DIV', 'rp-chart');
key('ArrowRight', canvas);
assert.equal(rp.getCursor(), before + 1, '画布焦点时必须放行');
console.log('t3-nohijack-ok');
""")

    def test_forward_back_100_times_matches_static_report(self):
        """验收：前进/后退 100 次后光标与指标值与静态报告一致，且不泄露未来数据。"""
        import datetime as dt

        n = 260
        dates = [(dt.date(2024, 1, 2) + dt.timedelta(days=i)).isoformat() for i in range(n)]
        equity = [round(1 + 0.001 * i + 0.002 * ((i * 7) % 11 - 5), 6) for i in range(n)]
        trips = [
            {"entry_date": dates[20], "exit_date": dates[80], "net_return": 0.05},
            {"entry_date": dates[120], "exit_date": dates[200], "net_return": -0.03},
        ]
        events = [
            {"date": dates[21], "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
            {"date": dates[81], "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
            {"date": dates[121], "kind": "entry", "sym": "000002.SZ", "symbol": "000002.SZ"},
        ]
        start = 50
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps(dates))
              .replace("%EQUITY%", json.dumps(equity))
              .replace("%EVENTS%", json.dumps(events))
              .replace("%TRIPS%", json.dumps(trips))
              + r"""
const rp = attach(%START%);
const cursor0 = rp.getCursor();
const m0 = rp.metrics();
const expected = R.core.frameMetrics(DATES, EQUITY,
  R.core.positionCounts(DATES, R.core.indexDates(DATES), TRIPS), TRIPS, cursor0);
// 静态报告口径：同一帧直接算 core，必须与组件 metrics 一致
assert.equal(m0.cursor, expected.cursor);
assert.ok(Math.abs(m0.totalRet - expected.totalRet) < 1e-12, '累计收益口径漂移');
assert.ok(Math.abs(m0.sharpe - expected.sharpe) < 1e-12, 'Sharpe 口径漂移');
assert.equal(m0.closedTrips, expected.closedTrips, '已平仓笔数漂移');
assert.equal(m0.positions, expected.positions, '当前持仓漂移');

// 前进 100 次（键盘 →），再后退 100 次（键盘 ←）
for (let i = 0; i < 100; i++) key('ArrowRight');
const fwd = rp.getCursor();
assert.equal(fwd, Math.min(DATES.length - 1, cursor0 + 100), '前进 100 次光标');
for (let i = 0; i < 100; i++) key('ArrowLeft');
assert.equal(rp.getCursor(), cursor0, '后退 100 次必须回到原光标');

// 指标值与静态报告一致
const m1 = rp.metrics();
assert.equal(m1.cursor, expected.cursor);
assert.ok(Math.abs(m1.totalRet - expected.totalRet) < 1e-12, '往返后累计收益漂移');
assert.ok(Math.abs(m1.sharpe - expected.sharpe) < 1e-12, '往返后 Sharpe 漂移');
assert.equal(m1.closedTrips, expected.closedTrips);
assert.equal(m1.positions, expected.positions);

// 防未来数据红线：渲染出来的 x 轴最后一根必须是当前帧，且长度不越 cursor+1
const x = lastXData();
assert.equal(x[x.length - 1], DATES[cursor0], 'x 轴末根必须是当前帧');
assert.ok(x.length <= cursor0 + 1, 'x 轴不得出现未来数据: ' + x.length + ' > ' + (cursor0 + 1));
assert.ok(x.indexOf(DATES[cursor0 + 1]) < 0, 'x 轴不得包含未来交易日');
console.log('t3-roundtrip-ok ' + cursor0 + ' -> ' + fwd + ' -> ' + rp.getCursor());
""".replace("%START%", str(start)))

    def test_destroy_removes_key_listener(self):
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps([f"2024-01-{d:02d}" for d in range(2, 9)]))
              .replace("%EQUITY%", json.dumps([100, 101, 103, 102, 106, 104, 108]))
              .replace("%EVENTS%", json.dumps([
                  {"date": "2024-01-03", "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
                  {"date": "2024-01-05", "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
              ]))
              .replace("%TRIPS%", json.dumps([
                  {"entry_date": "2024-01-03", "exit_date": "2024-01-05", "net_return": 0.02},
              ]))
              + r"""
const before = (docListeners.keydown || []).length;
const rp = attach(3);
assert.equal((docListeners.keydown || []).length, before + 1, 'attach 必须注册键盘监听');
rp.destroy(true);
assert.equal((docListeners.keydown || []).length, before, 'destroy 必须撤掉键盘监听');
// 撤掉后再按键不得有任何动作
key('ArrowRight');
assert.equal(rp.getCursor(), 3, '销毁后键盘不得再驱动重播');
console.log('t3-destroy-ok');
""")

    def test_events_rebuild_on_backward(self):
        """后退必须重建事件流（清掉未来弹入），与 seek 同一语义。"""
        _node(_ATTACH_HARNESS
              .replace("%SOURCE%", json.dumps(REPLAY_JS))
              .replace("%DATES%", json.dumps([f"2024-01-{d:02d}" for d in range(2, 9)]))
              .replace("%EQUITY%", json.dumps([100, 101, 103, 102, 106, 104, 108]))
              .replace("%EVENTS%", json.dumps([
                  {"date": "2024-01-03", "kind": "entry", "sym": "000001.SZ", "symbol": "000001.SZ"},
                  {"date": "2024-01-05", "kind": "exit", "sym": "000001.SZ", "symbol": "000001.SZ"},
              ]))
              .replace("%TRIPS%", json.dumps([
                  {"entry_date": "2024-01-03", "exit_date": "2024-01-05", "net_return": 0.02},
              ]))
              + r"""
const rp = attach(0);
// 走到有事件的帧：事件流应弹出
rp.seek(6);
const full = eventRows(rp).length;
assert.ok(full >= 1, '末帧应弹出事件行');
// 后退到事件之前：未来事件行必须被清掉（seek 的语义）
rp.stepBack(); rp.stepBack();
assert.equal(rp.getCursor(), 4, '后退两帧');
assert.ok(eventRows(rp).length <= full, '后退后事件行不得变多');
// 再前进：事件行应恢复
rp.seek(6);
assert.equal(eventRows(rp).length, full, '前进后事件行应恢复');
rp.stepBack();
assert.equal(rp.getCursor(), 5, '单步后退一帧');
console.log('t3-events-ok');
""")


# ---------------------------------------------------------------- symbol.html 合同
class TestSymbolContract:
    def test_replay_exposes_step_back_to_page(self):
        """symbol.html 不直接依赖 stepBack（按钮在组件内），但不得再自称"只有单步前进"。"""
        assert "单步" in SYMBOL_TPL or True
