"""QRE-SAAS-FIRST-SUCCESS-UX-001：wait-mask 状态文本 ARIA 与秒数降噪。

覆盖 static/wait-mask.js 与 lab-theme.css 的 .wm-* 族：
- 状态标题/说明 aria-live="polite"；
- 秒数（meta）仅视觉展示，不进 aria-live，避免每秒朗读；
- 既有语义不变：禁 ESC/禁背板关闭、按钮分流 keepMask、spinner 停转、
  reduced-motion 降级；移动端 768 断点样式仍在。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/quant_research_engine/gui/static"

_HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
function makeEl(tag){
  const e = {tag, children: [], attrs: {}, style: {}, _text: '', classes: new Set(), listeners: {},
    setAttribute(name, value){ this.attrs[name] = String(value); },
    getAttribute(name){ return this.attrs[name]; },
    appendChild(child){ this.children.push(child); return child; },
    addEventListener(type, fn){ (this.listeners[type] ||= []).push(fn); }};
  Object.defineProperty(e, 'textContent', {
    configurable: true,
    get(){ return e._text; }, set(v){ e._text = v; },
  });
  e.classList = {
    add(c){ e.classes.add(c); },
    remove(c){ e.classes.delete(c); },
    contains(c){ return e.classes.has(c); },
  };
  return e;
}
const body = makeEl('body');
const document = {createElement: tag => makeEl(tag), body};
// 浏览器里 window 即全局对象；vm 里把 sandbox 自指为 window，
// 组件内 window.LabUI 赋值与裸 LabUI 引用才能同时成立
const sandbox = {document, console};
sandbox.window = sandbox;
const context = vm.createContext(sandbox);
// 遮罩惰性创建：show() 之后才解析元素引用
function els(){
  const mask = body.children[0];
  const card = mask.children[0];
  const byClass = cls => card.children.find(c => c.className === cls);
  return {mask, card, byClass,
    title: byClass('wm-title'), sub: byClass('wm-sub'), meta: byClass('wm-meta')};
}
"""


def _run_wait_mask(scenario: str) -> None:
    source = (STATIC / "wait-mask.js").read_text(encoding="utf-8")
    node = shutil.which("node") or (
        "/home/van/codex-local/node-v22/bin/node"
        if Path("/home/van/codex-local/node-v22/bin/node").exists() else None
    )
    if not node:
        pytest.skip("node 不可用")
    script = (_HARNESS + "\nconst source = " + json.dumps(source)
              + ";\nvm.runInContext(source, context);\n"
              + "globalThis.LabUI = context.LabUI;\n" + scenario)
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def test_wait_mask_status_aria_live_and_seconds_not_announced():
    _run_wait_mask(r"""
(async () => {
  LabUI.waitMask.show({title: '冒烟校验中…', sub: '小范围验证策略可运行', meta: '已等待 5 秒'});
  const {mask, title, sub, meta} = els();
  assert.equal(title.getAttribute('aria-live'), 'polite', '状态标题必须 aria-live=polite');
  assert.equal(sub.getAttribute('aria-live'), 'polite', '状态说明必须 aria-live=polite');
  assert.ok(meta, '秒数必须有独立视觉元素');
  assert.equal(meta.textContent, '已等待 5 秒');
  assert.ok(!meta.getAttribute('aria-live'), '秒数不得进 aria-live，避免每秒朗读');
  assert.equal(meta.getAttribute('aria-hidden'), 'true', '秒数仅视觉展示');
  assert.equal(title.textContent, '冒烟校验中…');
  assert.equal(sub.textContent, '小范围验证策略可运行');
  assert.ok(mask.classList.contains('show'));
  assert.ok(body.classList.contains('wm-lock'));

  // 轮询刷新：只有 meta 变，标题/说明不变 → 不会反复朗读
  LabUI.waitMask.update({meta: '已等待 8 秒'});
  assert.equal(meta.textContent, '已等待 8 秒');
  assert.equal(title.textContent, '冒烟校验中…');
  assert.equal(sub.textContent, '小范围验证策略可运行');

  // 状态变化（排队 → 执行中）走 aria-live 正常播报
  LabUI.waitMask.update({title: '排队中，前面还有 3 个任务', sub: '任务在云端排队'});
  assert.equal(title.textContent, '排队中，前面还有 3 个任务');
  assert.equal(sub.textContent, '任务在云端排队');

  // 无 meta 时不渲染秒数行
  LabUI.waitMask.show({title: '提交任务中…', sub: ''});
  assert.equal(meta.textContent, '');
  assert.equal(sub.style.display, 'none');

  LabUI.waitMask.hide();
  assert.ok(!mask.classList.contains('show'));
  assert.ok(!body.classList.contains('wm-lock'));
  assert.equal(LabUI.waitMask.isOpen(), false);
})().catch(error => { console.error(error); process.exit(1); });
""")


def test_wait_mask_skips_dom_write_when_text_unchanged():
    """aria-live 降噪回归：轮询刷新时 title/sub 文本没变就不得重写 DOM（避免重复播报）；
    meta（秒数）照常更新；文本变化时必须更新。API 不变。"""
    _run_wait_mask(r"""
(async () => {
  function countWrites(el){
    let n = 0;
    const desc = Object.getOwnPropertyDescriptor(el, 'textContent');
    Object.defineProperty(el, 'textContent', {
      get: desc.get,
      set(v){ n += 1; desc.set.call(el, v); },
    });
    return () => n;
  }
  LabUI.waitMask.show({title: '冒烟校验中…', sub: '小范围验证策略可运行', meta: '已等待 5 秒'});
  const {title, sub, meta} = els();
  const titleWrites = countWrites(title), subWrites = countWrites(sub);
  // 轮询刷新：只有 meta 变
  LabUI.waitMask.update({meta: '已等待 8 秒'});
  LabUI.waitMask.update({meta: '已等待 11 秒'});
  assert.equal(meta.textContent, '已等待 11 秒');
  assert.equal(titleWrites(), 0, '标题未变不得重写 DOM（重复播报）');
  assert.equal(subWrites(), 0, '说明未变不得重写 DOM（重复播报）');
  // 同文本再 update 一次也不得写
  LabUI.waitMask.update({title: '冒烟校验中…', sub: '小范围验证策略可运行'});
  assert.equal(titleWrites(), 0);
  assert.equal(subWrites(), 0);
  // 状态变化（排队 → 执行中）必须更新并被播报
  LabUI.waitMask.update({title: '排队中，前面还有 3 个任务', sub: '任务在云端排队'});
  assert.equal(titleWrites(), 1, '标题变化必须更新 DOM');
  assert.equal(subWrites(), 1, '说明变化必须更新 DOM');
  assert.equal(title.textContent, '排队中，前面还有 3 个任务');
  assert.equal(sub.textContent, '任务在云端排队');
  // 清空 sub 时也要落盘（display none）
  LabUI.waitMask.update({sub: ''});
  assert.equal(subWrites(), 2);
  assert.equal(sub.style.display, 'none');
})().catch(error => { console.error(error); process.exit(1); });
""")


def test_wait_mask_buttons_and_keepmask_unchanged():    _run_wait_mask(r"""
(async () => {
  let clicks = 0;
  LabUI.waitMask.show({title: '已提交，排队执行中', sub: '关闭页面不影响结果',
    buttons: [{label: '后台运行', onClick: () => { clicks += 1; }},
              {label: '继续等待', primary: true, keepMask: true, onClick: () => { clicks += 1; return true; }}]});
  const {mask, card, byClass} = els();
  const btnRow = card.children[card.children.length - 1];
  const btns = btnRow.children;
  assert.equal(btns.length, 2);
  assert.ok(btns[1].className.includes('primary'));
  // spinner 停转（等待语义交还用户）
  assert.equal(byClass('wm-spin').style.display, 'none');
  // keepMask 按钮：执行动作但保持遮罩
  btns[1].listeners.click.forEach(fn => fn());
  assert.equal(clicks, 1);
  assert.ok(mask.classList.contains('show'), 'keepMask 必须保持遮罩');
  // 非 keepMask 按钮：执行后自动隐藏
  btns[0].listeners.click.forEach(fn => fn());
  assert.equal(clicks, 2);
  assert.ok(!mask.classList.contains('show'));
  assert.equal(LabUI.waitMask.isOpen(), false);
})().catch(error => { console.error(error); process.exit(1); });
""")


def test_wait_mask_css_meta_and_mobile_rules():
    css = (STATIC / "lab-theme.css").read_text(encoding="utf-8")
    meta_rule = re.search(r"\.wm-meta\{[^}]*\}", css)
    assert meta_rule, "秒数行必须有样式（tabular-nums，不抖动）"
    assert "tabular-nums" in meta_rule.group(0)
    assert ".wm-btn:focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert ".wm-card{padding:22px 18px" in css, "移动端卡片自适应必须保留"
    assert ".wm-btns .wm-btn{width:100%;min-height:44px}" in css, "移动端按钮 44px 必须保留"
