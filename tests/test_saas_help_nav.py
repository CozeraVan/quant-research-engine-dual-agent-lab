"""QRE-SAAS-HELP-NAV：使用说明页侧边栏玻璃胶囊指示器（CR-2026-10-28，V2 竞稿）。

核验本次切片的源码合同与纯函数行为：
1. help.html 只新增单个 `.help-pill`（`aria-hidden`），导航仍为七个锚点，脚本经
   `{% block scripts %}` 引入，不新增 `.opt` 灰字备注。
2. lab-theme.css 提供 `.help-jump{position:relative}`、五层玻璃（底色 + 受光渐变 +
   mask 渐变描边环 + 1px 高光 + 环境影）、`backdrop-filter`、`@supports not` 降级、
   `aria-current` 与 `focus-visible`、reduced-motion 关过渡；
   night-mode.css 提供暗色 token（亮度提升、色相不变）。
3. help-nav.js 走 IntersectionObserver + `aria-current` + offset 定位 + 平滑滚动，
   位移用弹簧积分、形变由速度投影与闭式阻尼振荡导出。
4. Node vm harness 校验弹簧步进、闭式振荡/阶跃响应、形变量、主轴与 transform。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HELP_TPL = ROOT / "src/quant_research_engine/gui/saas/templates/help.html"
THEME_CSS = ROOT / "src/quant_research_engine/gui/static/lab-theme.css"
NIGHT_CSS = ROOT / "src/quant_research_engine/gui/static/night-mode.css"
HELP_JS = ROOT / "src/quant_research_engine/gui/static/help-nav.js"


def _node() -> str:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    return node


def _run(script: str) -> None:
    result = subprocess.run(
        [_node(), "-e", script], cwd=ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _help_page() -> str:
    return HELP_TPL.read_text(encoding="utf-8")


def test_help_page_hosts_single_pill_and_loads_script():
    page = _help_page()
    assert page.count('class="help-pill"') == 1
    assert 'class="help-pill" aria-hidden="true"' in page
    assert 'src="/static/help-nav.js?v={{ asset_v }}"' in page
    assert page.count('href="#contract"') == 1
    nav = page[page.index('class="help-jump"'): page.index("</nav>")]
    assert nav.count("<a href=\"#") == 7
    assert 'class="opt"' not in nav


def test_help_page_keeps_no_new_gray_notes():
    page = _help_page()
    assert page.count('class="opt"') <= 3
    assert "help-nav-note" not in page


def test_theme_css_pill_contract():
    css = THEME_CSS.read_text(encoding="utf-8")
    assert ".help-jump{position:relative}" in css
    assert ".help-pill{" in css
    # 五层玻璃：受光渐变 + 半透明底 + mask 渐变描边环 + 1px 高光 + 环境影
    assert "--pill-sheen:linear-gradient(180deg" in css
    assert "background:var(--pill-sheen),var(--pill-bg)" in css
    assert "mask-composite:exclude" in css
    assert "-webkit-mask-composite:xor" in css
    assert "--pill-rim-top" in css
    assert "inset 0 1px 0 var(--pill-glow)" in css
    assert "backdrop-filter:blur(7px) saturate(1.35)" in css
    assert "@supports not ((backdrop-filter:blur(4px))" in css
    fallback = css[css.index("@supports not ((backdrop-filter:blur(4px))"):]
    fallback = fallback[: fallback.index("}", fallback.index(".help-pill{"))]
    assert "--pill-bg:var(--tint)" in fallback
    # 当前项与辅助视觉
    assert '.help-jump a[aria-current="true"]' in css
    assert ".help-jump a:focus-visible" in css
    assert ".help-jump a:hover{" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert ".help-pill{transition:none!important}" in css


def test_theme_css_keeps_locked_layout_rules():
    css = THEME_CSS.read_text(encoding="utf-8")
    assert ".help-jump{display:flex;flex-direction:column" in css
    assert ".help-side{position:sticky" in css
    assert ".help-content .card h2{font-size:22px" in css
    assert ".help-jump{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))" in css


def test_night_mode_pill_tokens():
    css = NIGHT_CSS.read_text(encoding="utf-8")
    assert ':root[data-theme="dark"] .help-pill{' in css
    block = css[css.index(':root[data-theme="dark"] .help-pill{'):]
    block = block[: block.index("}")]
    for token in ("--pill-glow", "--pill-rim-top", "--pill-sheen", "--pill-shadow"):
        assert token in block, token
    assert "155,132,216" in block  # 暗色 lav 色相，不漂移
    assert ':root[data-theme="dark"] .help-jump a[aria-current="true"]' in css


def test_help_nav_js_wiring():
    js = HELP_JS.read_text(encoding="utf-8")
    for token in (
        "IntersectionObserver",
        "aria-current",
        "offsetTop",
        "offsetLeft",
        "offsetWidth",
        "offsetHeight",
        "scrollIntoView",
        "(prefers-reduced-motion: reduce)",
        "requestAnimationFrame",
        "springStep",
        "oscillate",
        "stepResponse",
        "scaleFor",
        "axisFor",
        "crossedTarget",
        "replaceState",
        "document.fonts.ready",
    ):
        assert token in js, token


def test_help_nav_pure_functions_via_node_vm():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}, console});
const source = fs.readFileSync(
  'src/quant_research_engine/gui/static/help-nav.js', 'utf8');
vm.runInContext(source, context);
const nav = context.window.QREHelpNav;
assert.ok(nav, 'QREHelpNav 未导出');

/* ---- 位移弹簧：角速度恒定、阻尼比随距离自适应 ---- */
const near = nav.moveParams(0);
const far = nav.moveParams(400);
assert.equal(near.stiffness, far.stiffness, '角速度必须恒定');
assert.ok(far.damping > near.damping, '长距离应更阻尼');
assert.ok(nav.moveParams(1).damping > near.damping, '阻尼比应随距离上升');
assert.equal(nav.moveParams(1e6).damping, far.damping, '超大位移取远端阻尼');

/* ---- 弹簧步进：收敛、有过冲、大 dt 下稳定 ---- */
let x = 0, v = 0;
const params = nav.moveParams(138);
for (let i = 0; i < 60; i++) {
  const r = nav.springStep(x, v, 138, params, 1 / 60);
  x = r.value; v = r.velocity;
}
assert.ok(Math.abs(x - 138) < 0.5, '应收敛到目标，实际 ' + x);
let peak = 0;
x = 0; v = 0;
for (let i = 0; i < 40; i++) {
  const r = nav.springStep(x, v, 138, params, 1 / 60);
  x = r.value; v = r.velocity;
  peak = Math.max(peak, x);
}
assert.ok(peak > 138, '欠阻尼应有越过目标的一冲，峰值 ' + peak);
assert.ok(peak - 138 < 12, '过冲不得超过 12px，实际 ' + (peak - 138));
const big = nav.springStep(0, 0, 100, params, 0.5);
assert.ok(Number.isFinite(big.value) && Number.isFinite(big.velocity),
  '大 dt 不能溢出');

/* ---- 到位压扁振荡：从 0 起振、先负后正、衰减 ----
   2026-10-28 IMPACT_MAX 0.10→0.16：42px 胶囊压扁从 4.2px 提到 6.7px，
   与加强后的拉长（28%）匹配，回弹才看得见。 */
const bounce = nav.impactScale(138);
assert.ok(bounce < 0, '压扁量应为负');
assert.ok(bounce >= -0.16 - 1e-9, '压扁不得超过 16%');
// 138px < IMPACT_RANGE(160)，按比例给；≥160 才拉满
assert.ok(Math.abs(bounce - (-0.16 * 138 / 160)) < 1e-9, '按距离比例给压扁: ' + bounce);
assert.ok(Math.abs(nav.impactScale(200) + 0.16) < 1e-9, '≥160px 拉满 16%');
// IMPACT_MIN=0.5 是下限：位移 ≤ IMPACT_RANGE/2 (=80px) 时都吃保底
assert.equal(nav.impactScale(0), nav.impactScale(80), '0 位移也保底给一半幅度');
assert.ok(nav.impactScale(0) < 0, '保底压扁仍应为负');
assert.ok(nav.impactScale(400) < nav.impactScale(40), '长距离压得更狠');
assert.equal(nav.impactScale(1e6), nav.impactScale(400), '压扁量必须设上限');
assert.equal(nav.oscillate(0, bounce, {stiffness: 1600, damping: 25.6, mass: 1}), 0,
  't=0 应为 0（sin 起步，不跳变）');
assert.equal(nav.oscillate(-1, bounce, {stiffness: 1600, damping: 25.6, mass: 1}), 0,
  't<0 应为 0');
const BOUNCE = {stiffness: 1600, damping: 25.6, mass: 1};
let lo = 0, hi = 0;
for (let t = 0; t < 0.4; t += 0.002) {
  const b = nav.oscillate(t, bounce, BOUNCE);
  lo = Math.min(lo, b); hi = Math.max(hi, b);
}
assert.ok(lo < -0.02, '应有可见压扁，实际 ' + lo);
assert.ok(hi > 0.005, '压扁后应回冲，实际 ' + hi);
assert.ok(Math.abs(nav.oscillate(1, bounce, BOUNCE)) < 0.002, '应衰减到 0');

/* ---- 出场阶跃响应：从 1 收敛到 0 且过冲 ---- */
const ENTRANCE = {stiffness: 1156, damping: 34, mass: 1};
assert.equal(nav.stepResponse(0, ENTRANCE), 1, 't=0 应为 1');
assert.ok(Math.abs(nav.stepResponse(1, ENTRANCE)) < 0.01, '应收敛到 0');
let over = 0;
for (let t = 0; t < 0.5; t += 0.002) over = Math.min(over, nav.stepResponse(t, ENTRANCE));
assert.ok(over < 0, '欠阻尼应过冲到 0 以下（缩放越过 1）');

/* ---- 形变量：符号、截断、体积补偿 ----
   2026-10-28 用户反馈「没看见拉长特效」后加强：VEL_REF 1500→600、DEFORM_MAX
   0.12→0.28。原参数下实测峰值速度约 1000px/s 只能吃到 8% 形变（42px 胶囊约
   3.4px），肉眼不可见；现按典型速度饱和给足 28%（约 11.8px）。 */
assert.equal(nav.stretchScale(0), 0);
assert.ok(nav.stretchScale(600) >= 0.28 - 1e-9, '达到参考速度应拉满');
assert.ok(nav.stretchScale(1e6) <= 0.28 + 1e-9, '形变必须设上限');
assert.equal(nav.stretchScale(-600), nav.stretchScale(600), '与方向无关');
assert.ok(nav.deformScale(-600) < 0, '反向投影应得负形变（压扁）');
// 关键：真实速度区间（相邻项 ~600px/s、跨项 ~1000px/s）必须给出肉眼可见的拉长
[600, 800, 1000, 1200].forEach(function (v) {
  assert.ok(nav.stretchScale(v) >= 0.20, '速度 ' + v + ' 的拉长必须可见，实际 ' + nav.stretchScale(v));
});
assert.ok(nav.stretchScale(300) > 0.05, '慢速短距也要有可感拉长，实际 ' + nav.stretchScale(300));

/* ---- 主轴 ---- */
assert.equal(nav.axisFor(0, 100), 'y');
assert.equal(nav.axisFor(100, 0), 'x');
assert.equal(nav.axisFor(0, 0), 'y');

/* ---- 缩放对：主轴形变、垂直轴反向收窄 ---- */
const down = nav.scaleFor('y', 1500);
assert.ok(down.sy > 1, '竖向移动应拉长 scaleY');
assert.ok(down.sx < 1, '垂直轴应体积补偿收窄');
assert.ok(down.sx > 0.9, '收窄不得过头');
const right = nav.scaleFor('x', 1500);
assert.ok(right.sx > 1, '横向移动应拉长 scaleX');
assert.ok(right.sy < 1, '垂直轴应体积补偿收窄');
assert.equal(nav.scaleFor('y', 0).sy, 1, '静止时 scaleY 为 1');
assert.equal(nav.scaleFor('y', 0).sx, 1, '静止时 scaleX 为 1');
const squashed = nav.scaleFor('y', 0, -0.05);
assert.ok(squashed.sy < 1, '到位压扁应作用在主轴');
assert.ok(squashed.sx > 1, '压扁时垂直轴应反向放宽');

/* ---- 穿过判定 ---- */
assert.equal(nav.crossedTarget(0, 5, 3), true);
assert.equal(nav.crossedTarget(5, 0, 3), true);
assert.equal(nav.crossedTarget(0, 2, 3), false);
assert.equal(nav.crossedTarget(4, 5, 3), false);
assert.equal(nav.crossedTarget(3, 3, 3), false);

/* ---- transform ---- */
assert.equal(nav.transformFor({x: 3, y: 8}), 'translate3d(3px,8px,0)');
assert.equal(nav.transformFor({x: 1.234, y: 2.345}), 'translate3d(1.23px,2.35px,0)');
"""
    _run(script)
