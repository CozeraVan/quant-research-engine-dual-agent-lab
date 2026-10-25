from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _node():
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    return node


def test_help_tip_repeated_hover_dynamic_nodes_and_touch():
    script = r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const listeners = {};
const body = {children: [], appendChild(el){ this.children.push(el); el.parentNode = this; }};
const document = {
  body,
  addEventListener(type, fn){ (listeners[type] ||= []).push(fn); },
  createElement(){ return {style: {}, classList: {add(){}, remove(){}}, setAttribute(){}}; },
  dispatch(type, event){
    event.target ||= null; event.relatedTarget ||= null;
    for (const fn of listeners[type] || []) fn(event);
  }
};
const window = {innerWidth: 1280, innerHeight: 800, pageXOffset: 0, pageYOffset: 0};
const context = vm.createContext({window, document, console});
const source = fs.readFileSync('src/quant_research_engine/gui/static/lab-ui.js', 'utf8');
vm.runInContext(source, context);
assert.equal(typeof window.LabUI.helpTips, 'function');
window.LabUI.helpTips();
function target(text){
  return {
    text,
    closest(selector){ return selector === '[data-tip]' ? this : null; },
    getAttribute(name){ return name === 'data-tip' ? this.text : null; },
    getBoundingClientRect(){ return {left: 100, top: 100, bottom: 124, width: 160}; },
    setAttribute(){}, removeAttribute(){}, classList: {add(){}, remove(){}}
  };
}
const first = target('完整模块说明');
const pop = () => body.children[0];
for (let i = 0; i < 3; i++) {
  document.dispatch('mouseover', {target: first});
  assert.equal(pop().style.display, 'block');
  assert.equal(pop().textContent, '完整模块说明');
  document.dispatch('mouseout', {target: first, relatedTarget: null});
  assert.equal(pop().style.display, 'none');
}
const metric = target('夏普比率口径');
document.dispatch('mouseover', {target: metric});
assert.equal(pop().textContent, '夏普比率口径');
document.dispatch('mouseout', {target: metric});
document.dispatch('focusin', {target: metric});
document.dispatch('pointerup', {target: metric, pointerType: 'touch'});
assert.equal(pop().style.display, 'block');
document.dispatch('mouseout', {target: metric, relatedTarget: null});
assert.equal(pop().style.display, 'block');
document.dispatch('scroll', {target: metric});
assert.equal(pop().style.display, 'block');
document.dispatch('pointerup', {target: metric, pointerType: 'touch'});
assert.equal(pop().style.display, 'none');
document.dispatch('focusin', {target: first});
assert.equal(pop().style.display, 'block');
document.dispatch('keydown', {key: 'Escape'});
assert.equal(pop().style.display, 'none');
'''
    result = subprocess.run([_node(), "-e", script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr or result.stdout


def _template(name: str) -> str:
    return (ROOT / "src/quant_research_engine/gui/saas/templates" / name).read_text()


def test_base_initializes_delegated_tips():
    base = _template("base.html")
    css = (ROOT / "src/quant_research_engine/gui/static/lab-theme.css").read_text()
    assert "LabUI.helpTips()" in base
    assert ".tip-pop" in css
    assert "pointer-events:none" in css


def test_new_page_removes_static_gray_notes():
    page = _template("new.html")
    for removed in ["更复杂的逻辑组合", "编辑器在页面底部", "由系统自动生成，仅供预览", "仅允许字母、数字、下划线、连字符</span>", "从全 A 股池随机抽 N 只"]:
        assert removed not in page
    assert page.count('class="tip-trigger"') >= 4
    assert "没有你要的因子？点此申请新因子" in page
    assert "仅允许字母、数字、下划线、连字符" in page  # 移入说明，而非丢失约束
    assert "textContent = '条件行选因子" not in page
    assert 'data-tip="条件行选因子' in page


def test_result_pages_move_module_and_metric_notes_to_tips():
    job = _template("job.html")
    symbol = _template("symbol.html")
    for page in [job, symbol]:
        assert 'class="tip-trigger"' in page
        assert "data-tip=" in page
    for removed in ["（累计收益率，全期起点", "（佣金 / 印花税 / 过户费等集中呈现", "（矩块面积 = 盈亏规模", "全部触发交易的个股列表：代码"]:
        assert removed not in job
    for label in ["总收益率", "夏普比率", "最大回撤", "胜率", "区间策略收益", "VaR "]:
        assert label in job
    assert "单笔净收益的算术平均" in symbol
    assert "历史模拟法" in symbol
    assert "round_trips 全量真实费用列" in job
    assert "不构成投资建议" in job
    assert "不构成投资建议" in symbol
