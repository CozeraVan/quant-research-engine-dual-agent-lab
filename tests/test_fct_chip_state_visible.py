"""QRE-FCT-CHIP-STATE-VISIBLE：因子 chip 呈现态必须肉眼可辨，且可一键复位。

背景（用户反复反馈「EMA 又跑到 K 线外面去了」）：
chip 三态（叠加K线 / 独立面板 / 隐藏）持久化在 localStorage 的
``qre_fct_<key>``。用户误点一次就把某因子永久切成独立面板，之后**每个**任务
打开都看到 EMA 落在 K 线之外；而 chip 只有配色差异、无任何文字说明，用户
完全无法自知，也无法恢复。

本测试锁死两件事：
1. chip 文案带态：``<label>·叠加`` / ``·独立`` / ``·隐藏``；
2. 有因子时末尾必有「重置布局」钮，点击即清掉本浏览器全部 ``qre_fct_*``
   并重渲染（回到默认呈现：均线类叠加 K 线）。

全部 Node vm + 内存 DOM 桩，不触外网、不跑回测。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SYMBOL_HTML = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
THEME_CSS = (
    REPO / "src/quant_research_engine/gui/static/lab-theme.css"
).read_text(encoding="utf-8")
NIGHT_CSS = (
    REPO / "src/quant_research_engine/gui/static/night-mode.css"
).read_text(encoding="utf-8")
# 真实因子分类源码：harness 里 plan() 必须跑生产规则，不能另写桩
FACTOR_LAYOUT_JS = (
    REPO / "src/quant_research_engine/gui/static/factor-layout.js"
).read_text(encoding="utf-8")

# 取出 chip 区块：从状态文案表到 renderFactorChips 结束（下一行是
# `let klineResizeBound = false`，是 chip 块之后的第一条语句）。
_BLOCK = SYMBOL_HTML.split("const FCT_STATE_LABEL", 1)[1].split(
    "let klineResizeBound = false", 1
)[0]
BLOCK = "const FCT_STATE_LABEL" + _BLOCK

assert "function renderFactorChips" in BLOCK, "chip 区块定位失败"
assert "function fctClearPersistedStates" in BLOCK, "重置函数定位失败"

_HARNESS = r"""
// ---- 内存 DOM 桩 ----
function mkEl(tag){
  return {
    tagName: tag, children: [], _handlers: {}, textContent: '', title: '',
    id: '', className: '', style: {},
    appendChild(c){ this.children.push(c); return c; },
    addEventListener(ev, fn){ (this._handlers[ev] = this._handlers[ev] || []).push(fn); },
    click(){ (this._handlers.click || []).forEach(fn => fn()); },
    get text(){ return this.children.map(c => c.textContent).join(''); },
  };
}
const slots = {};
function $(sel){ return slots[sel] || null; }
const document = { createElement: mkEl };
const localStorage = (() => {
  const store = {};
  return {
    get length(){ return Object.keys(store).length; },
    key(i){ return Object.keys(store)[i]; },
    getItem(k){ return Object.prototype.hasOwnProperty.call(store, k) ? store[k] : null; },
    setItem(k, v){ store[k] = String(v); },
    removeItem(k){ delete store[k]; },
    _store: store,
  };
})();

// ---- symbol.html 依赖的最小桩 ----
const FCT_LS_PREFIX = 'qre_fct_';
let kreplayCtl = null;
const klineData = null;
let dispatchCalls = 0;
// R3-4：引擎唯一，chip 点击/重置后直接重建 renderKline（renderKlineDispatch 已移除）
function renderKline(){ dispatchCalls++; }
function mountKlineReplay(){ return { destroy(){} }; }
function setChipState(key, st){ localStorage.setItem(FCT_LS_PREFIX + key, st); }

// 真实因子分类（window 桩：factor-layout.js 挂在 window.QREFactorLayout）
globalThis.window = globalThis;
%FACTOR_LAYOUT%

%BLOCK%

// ---- 用例 ----
// 因子集合用真实 payload 形态（与 job_78 生产产物一致：col=ema_5/ema_20/macd_*），
// plan 由真实 factor-layout.js 生成，避免桩与生产分类规则漂移。
const FACTORS = [
  {name: 'ema_5',  col: 'ema_5',  values: [1, 2, 3]},
  {name: 'ema_20', col: 'ema_20', values: [1, 2, 3]},
  {name: 'macd_dif',  col: 'macd_dif',  values: [1, 2, 3]},
  {name: 'macd_dea',  col: 'macd_dea',  values: [1, 2, 3]},
  {name: 'macd_hist', col: 'macd_hist', values: [1, 2, 3]},
];

// 1) 默认态：文案带态
slots['#kline-chips'] = mkEl('span');
renderFactorChips(QREFactorLayout.plan(FACTORS, {}, []), null);
const chips1 = slots['#kline-chips'].children;
const texts1 = chips1.map(c => c.textContent);
if (!texts1.includes('ema_5·叠加')) throw new Error('overlay chip 文案缺态: ' + JSON.stringify(texts1));
if (!texts1.includes('ema_20·叠加')) throw new Error('overlay chip 文案缺态: ' + JSON.stringify(texts1));
if (!texts1.includes('MACD·独立')) throw new Error('pane chip 文案缺态: ' + JSON.stringify(texts1));
if (texts1.filter(t => t === '重置布局').length !== 1) throw new Error('缺重置布局钮: ' + JSON.stringify(texts1));
if (chips1[chips1.length - 1].className.indexOf('fct-chip-reset') < 0)
  throw new Error('重置钮 class 不对: ' + chips1[chips1.length - 1].className);

// 2) 持久化态可见：用户曾把 ema_5 切成独立面板（localStorage qre_fct_ema_5=pane，
//    由 chipStates() 喂进 plan）→ 文案必须显示 ·独立，否则用户无从自知。
localStorage.setItem('qre_fct_ema_5', 'pane');
slots['#kline-chips'] = mkEl('span');
renderFactorChips(QREFactorLayout.plan(FACTORS, {ema_5: 'pane'}, []), null);
const texts2 = slots['#kline-chips'].children.map(c => c.textContent);
if (!texts2.includes('ema_5·独立')) throw new Error('持久化 pane 态不可见: ' + JSON.stringify(texts2));

// 3) 点击重置 → 清掉全部 qre_fct_*，并触发一次重渲染
const before = dispatchCalls;
const resetBtn = slots['#kline-chips'].children[slots['#kline-chips'].children.length - 1];
resetBtn.click();
if (localStorage.length !== 0) throw new Error('重置后仍有持久化态残留: ' + JSON.stringify(localStorage._store));
if (dispatchCalls !== before + 1) throw new Error('重置未触发重渲染');

// 4) 无因子时不放重置钮（纯行情页）
slots['#kline-chips'] = mkEl('span');
renderFactorChips({chips: [], overlays: [], panes: []}, null);
if (slots['#kline-chips'].children.length !== 0) throw new Error('无因子时不应渲染任何 chip');

console.log('OK');
"""


def _node(script: str) -> None:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(script)
        path = fh.name
    try:
        result = subprocess.run([node, path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "OK" in result.stdout, result.stdout
    finally:
        Path(path).unlink(missing_ok=True)


def test_chip_label_carries_state_and_reset_button() -> None:
    script = _HARNESS.replace("%BLOCK%", BLOCK).replace(
        "%FACTOR_LAYOUT%", FACTOR_LAYOUT_JS
    )
    _node(script)


def test_reset_button_styled_distinct_from_factor_chips() -> None:
    """重置钮必须与因子 chip 视觉可分（虚线 + 独立 class），否则又是一颗"因子"。"""
    assert re.search(r"\.fct-chip-reset\{[^}]*border-style:dashed", THEME_CSS), \
        "lab-theme.css 缺 .fct-chip-reset 虚线样式"
    assert re.search(r"\.fct-chip-reset\{[^}]*background:transparent", THEME_CSS), \
        "lab-theme.css 缺 .fct-chip-reset 透明底"
    # 12_UI_STYLE_GUIDE 的字号下限：弱化层级也不得小于 12px
    m = re.search(r"\.fct-chip-reset\{[^}]*font-size:([0-9.]+)px", THEME_CSS)
    assert m, "lab-theme.css 的 .fct-chip-reset 缺 font-size"
    assert float(m.group(1)) >= 12.0, \
        "重置钮字号不得小于 12px（UI 长期标准下限），实际 %s" % m.group(1)
    # 夜间模式：.fct-chip 的深色面板规则会连带命中重置钮，必须显式还原
    assert re.search(r'data-theme="dark"\]\s*\.fct-chip-reset\{[^}]*border-style:dashed',
                     NIGHT_CSS), "night-mode.css 缺夜间 .fct-chip-reset 还原规则"


def test_block_has_no_leftover_old_label() -> None:
    """chip 文案必须走「标签·态」，不允许回退成裸标签。"""
    assert "b.textContent = c.label + '·' +" in BLOCK
