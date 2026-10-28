"""QRE-SAAS-CARD-FX：全站卡片磨砂玻璃 + 光标跟随光斑 + 轻微 3D 倾斜（CR-2026-10-28）。

核验本次切片的源码合同与纯函数行为：
1. lab-theme.css：`.card`/`.chart-box`/`.panel`/`.big-link` 玻璃（backdrop-filter
   blur(28px) saturate(140%)、55% 透明底、1px 半透明白描边、顶部 inset 高光、
   24px 圆角、大而柔投影）；`body::before` 背景装饰层（fixed / pointer-events:none
   / z-index:-1 / 品牌紫径向渐变）；光斑 ::before（z-index:-1 压在文字之下）与
   边框提亮 ::after（mask-composite:exclude 只留 1px 环）；`--mx/--my/--rx/--ry`
   被使用；倾斜 clamp ±4；canvas 卡不挂 transform；reduced-motion 降级；
   `.topbar` z-index:40 未被破坏。
2. night-mode.css：暗色玻璃 token（--glass-bg/line/hi/shadow/spot/rim）与暗色
   背景装饰层，全部规则仍带 `:root[data-theme="dark"]` 作用域。
3. card-fx.js：单个 pointermove 委托监听 + rAF 节流；嵌套卡只驱动最外层；
   含 canvas 的卡片不倾斜；prefers-reduced-motion 直接跳过。
4. Node vm harness 校验纯函数：spot（中心 50/50、四角 0/100、越界钳制、零尺寸）、
   tilt（中心 0/0、四角 ±4 极值、任何输入都落在 ±4 内）、outermost、eligibleForTilt。
5. 既有约束不变：不新增 `.opt` 灰字、无外部依赖、`base.html` 只多一行脚本引入。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src/quant_research_engine/gui/static"
TEMPLATES = ROOT / "src/quant_research_engine/gui/saas/templates"
THEME_CSS = STATIC / "lab-theme.css"
NIGHT_CSS = STATIC / "night-mode.css"
CARD_FX_JS = STATIC / "card-fx.js"


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


def _card_fx_section() -> str:
    """lab-theme.css 中本次新增的卡片特效段（从段头注释到文件末尾）。"""
    css = _theme()
    return css[css.index("全站卡片：磨砂玻璃 + 光标跟随光斑 + 轻微 3D 倾斜"):]


def _theme() -> str:
    return THEME_CSS.read_text(encoding="utf-8")


def _night() -> str:
    return NIGHT_CSS.read_text(encoding="utf-8")


def _fx() -> str:
    return CARD_FX_JS.read_text(encoding="utf-8")


def _base() -> str:
    return (TEMPLATES / "base.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------- 玻璃卡本体


def test_card_glass_contract():
    css = _theme()
    assert "--card-radius:24px" in css
    card = css[css.index(".card,.chart-box,.panel,.big-link{"):]
    card = card[: card.index("}")]
    assert "backdrop-filter:blur(28px) saturate(140%)" in card
    assert "-webkit-backdrop-filter:blur(28px) saturate(140%)" in card
    assert "background-color:var(--glass-bg)" in card
    assert "border:1px solid var(--glass-line)" in card
    assert "box-shadow:inset 0 1px 0 var(--glass-hi),var(--glass-shadow)" in card
    assert "border-radius:var(--card-radius)" in card
    # 45%–60% 透明度：取 55%
    assert "--glass-bg:rgba(255,255,255,.48)" in css
    assert "--glass-line:rgba(255,255,255,.5)" in css
    assert "--glass-hi:rgba(255,255,255,.75)" in css
    # 大而柔的投影（两层：接触影 + 环境影）
    assert "--glass-shadow:0 1px 2px" in css and "46px" in css


def test_key_pages_card_classes_are_glass():
    """job.html / symbol.html 的主体卡是 .chart-box 与 .panel，必须同在玻璃卡族里。"""
    css = _theme()
    family = css[css.index(".card,.chart-box,.panel,.big-link{"):]
    family = family[: family.index("}")]
    for klass in (".card", ".chart-box", ".panel", ".big-link"):
        assert klass in family.split("{")[0], klass
    job = (TEMPLATES / "job.html").read_text(encoding="utf-8")
    symbol = (TEMPLATES / "symbol.html").read_text(encoding="utf-8")
    assert 'class="chart-box"' in job and 'class="panel"' in job
    assert 'class="chart-box"' in symbol


def test_small_tiles_keep_own_radius():
    """小卡（指标卡/入口卡）吃玻璃但不改圆角，避免 60px 高的小卡变成胶囊。"""
    css = _theme()
    block = css[css.index(".metric,.metric-card,.entry-card{"):]
    block = block[: block.index("}")]
    assert "backdrop-filter:blur(28px) saturate(140%)" in block
    assert "border-radius" not in block


# ---------------------------------------------------------------- 背景装饰层


def test_backdrop_layer_exists_and_never_blocks_input():
    css = _theme()
    assert "body::before{" in css
    layer = css[css.index("body::before{"):]
    layer = layer[: layer.index("}")]
    assert "position:fixed" in layer and "inset:0" in layer
    assert "pointer-events:none" in layer
    # 负 z-index：排在全部内容之下，无需给 .wrap/.container 提层级
    assert "z-index:-1" in layer
    # 低透明度品牌紫径向渐变（不引入新色相）
    for rgb in ("103,80,164", "139,127,190", "230,222,243"):
        assert rgb in layer, rgb
    assert layer.count("radial-gradient(") >= 3


def test_topbar_and_overlays_layering_untouched():
    css = _theme()
    assert ".topbar{position:sticky;top:0;z-index:40" in css
    assert ".modal-mask{position:fixed;inset:0;background:rgba(36,31,46,.42);z-index:80" in css
    assert ".wm-mask{position:fixed;inset:0;background:rgba(36,31,46,.48);z-index:95" in css
    # 侧边悬浮导航的 fixed/z-index 仍在（base.html 内联），装饰层 z-index:-1 不会盖住它
    assert ".sidenav{position:fixed;left:0;top:38%;transform:translateY(-50%);z-index:60" in _base()


# ---------------------------------------------------------------- 光斑与边框提亮


def test_spotlight_and_rim_pseudo_elements():
    css = _theme()
    spot = css[css.index(".card::before,.chart-box::before"):]
    spot = spot[: spot.index("}")]
    # 光斑落在卡片背景之上、文字之下 → 不影响文字对比度
    assert "z-index:-1" in spot
    assert "isolation:isolate" in css
    assert "radial-gradient(280px circle at var(--mx) var(--my),var(--glass-spot),transparent 65%)" in spot
    assert "opacity:0" in spot and "transition:opacity .35s var(--ease)" in spot
    rim = css[css.index(".card::after,.chart-box::after"):]
    rim = rim[: rim.index("}")]
    assert "padding:1px" in rim
    assert "radial-gradient(220px circle at var(--mx) var(--my),var(--glass-rim),transparent 70%)" in rim
    assert "mask-composite:exclude" in rim
    assert "-webkit-mask-composite:xor" in rim
    # 由 JS 加类点亮（不用 :hover，嵌套内层不会重复点亮）
    assert ".fx-on::before,.fx-on::after{opacity:1}" in css


def test_custom_properties_declared_and_used():
    css = _theme()
    assert "--mx:50%;--my:50%;--rx:0;--ry:0" in css
    assert "at var(--mx) var(--my)" in css
    assert "rotateX(calc(clamp(calc(-1 * var(--glass-tilt)),var(--ry),var(--glass-tilt)) * 1deg))" in css
    assert "rotateY(calc(clamp(calc(-1 * var(--glass-tilt)),var(--rx),var(--glass-tilt)) * 1deg))" in css


# ---------------------------------------------------------------- 倾斜


def test_tilt_rules_and_canvas_exclusion():
    css = _theme()
    assert ".fx-tilt{" in css
    tilt = css[css.index(".fx-tilt{"):]
    tilt = tilt[: tilt.index("}")]
    assert "perspective(1000px)" in tilt
    assert "transition:transform .38s var(--ease)" in tilt
    # 移动中关过渡 → 跟手；移出后移除 .fx-live 并归零 → 平滑复原
    assert ".fx-tilt.fx-live{transition:none}" in css
    # 倾斜只对并列小卡（CR-2026-10-28 用户反馈后收窄）
    assert ".metric-card.fx-tilt{" in css, "倾斜必须挂在并列小卡上"
    assert ".entry-card.fx-tilt{" in css, "新建策略三入口也必须挂倾斜"
    assert "translateY(-2px)" in css, "hover 微浮应合并进小卡倾斜的 transform"
    # 入口卡的 hover 抬起已换成 3D 晃动，不得再留 translateY(-4px)
    assert "translateY(-4px)" not in css, "入口卡 hover 抬起应被倾斜取代"
    # 小卡透视必须近（170x77 的卡在 1000px 透视下 4° 只有 0.4px 位移，看不见）
    mcard = css[css.index(".metric-card.fx-tilt{"):]
    mcard = mcard[: mcard.index("}")]
    assert "perspective(260px)" in mcard, f"小卡倾斜必须用近透视，实际 {mcard[:80]}"
    js0 = _fx()
    TILT_JS_SEL = js0.split('TILT_SEL = ')[1].split(';')[0].strip()
    assert TILT_JS_SEL == "'.metric-card,.entry-card'", f"JS TILT_SEL 应为小卡+三入口，实际 {TILT_JS_SEL}"
    # 使用说明侧边栏 sticky 必须赢过玻璃卡族的 position:relative
    assert ".help-side{position:sticky;top:76px}" in css, "侧边栏 sticky 被玻璃族覆盖"
    # 侧边栏 sticky 规则必须排在玻璃卡族之后（同特异性后声明胜出）；
    # 原规则在 620 行、玻璃族在 741 行，必须额外补一条后置规则
    assert css.rindex(".help-side{position:sticky") > css.rindex(".card,.chart-box,.panel,.big-link{"), (
        "必须在玻璃卡族之后补一条 .help-side{position:sticky}")
    # CSS 侧二次钳制 ±4 之外还有 JS 钳制
    assert "--glass-tilt:4" in css
    js = js0
    assert "var TILT_MAX = 4;" in js
    assert "querySelector('canvas')" in js
    assert "eligibleForTilt" in js
    # 图表卡（含 canvas）不挂 transform → 计算样式为 none
    assert "eligibleForTilt" in js
    # 光斑宿主与倾斜宿主必须解耦：倾斜只挂光标下的小卡，不向上爬到大卡
    assert "outermost(hit)" in js, "光斑仍走最外层"
    assert "hit.matches(TILT_SEL)" in js, "倾斜必须取光标下的小卡，不得向上爬"
    assert "state.tilt" in js and "state.card" in js, "光斑与倾斜宿主必须分开存"


def test_nested_cards_drive_outermost_only():
    js = _fx()
    assert "function outermost(card)" in js
    assert "cur.parentElement.closest(CARD_SEL)" in js
    # 倾斜只对并列小卡；大卡/图表卡不参与，避免 transform 叠加与画布发糊
    assert "TILT_SEL = '.metric-card,.entry-card'" in js


# ---------------------------------------------------------------- 降级与可访问性


def test_reduced_motion_degrades():
    section = _card_fx_section()
    start = section.index("@media (prefers-reduced-motion: reduce){")
    block = section[start:]
    block = block[: block.index("}\n/* 无 backdrop-filter")]
    assert ".card::before,.card::after" in block
    assert "display:none" in block
    assert ".fx-tilt{transition:none}" in block
    js = _fx()
    assert "prefers-reduced-motion: reduce" in js
    assert "prefersReduced()" in js


def test_no_backdrop_filter_fallback():
    section = _card_fx_section()
    fallback = section[section.index("@supports not ((backdrop-filter:blur(4px))"):]
    assert "background-color:var(--panel)" in fallback
    assert "body::before{opacity:.45}" in fallback


def test_focus_ring_not_covered():
    """焦点环是 outline（画在卡片外），不被 ::after 描边环遮挡。"""
    css = _theme()
    assert ":focus-visible{outline:2px solid var(--lav);outline-offset:2px" in css


# ---------------------------------------------------------------- 夜间模式


def test_night_glass_tokens_and_layer():
    css = _night()
    assert ":root[data-theme=\"dark\"]{\n  --glass-bg:rgba(46,35,108,.48)" in css
    for token in ("--glass-line", "--glass-hi", "--glass-shadow", "--glass-spot", "--glass-rim"):
        assert token in css, token
    block = css[css.index(":root[data-theme=\"dark\"] .card,\n:root[data-theme=\"dark\"] .chart-box"):]
    block = block[: block.index("}")]
    assert "background-color:var(--glass-bg)" in block
    assert "border-color:var(--glass-line)" in block
    assert "inset 0 1px 0 var(--glass-hi)" in block
    assert ':root[data-theme="dark"] body::before{' in css
    # 色相不漂移：暗色装饰层仍是品牌紫
    dark = css[css.index(':root[data-theme="dark"] body::before{'):]
    dark = dark[: dark.index("}")]
    assert "155,132,216" in dark and "126,96,191" in dark


def test_night_css_all_rules_still_scoped():
    import re

    css = re.sub(r"/\*.*?\*/", "", _night(), flags=re.S)
    allowed = (':root[data-theme="dark"]', ".tt-btn", "@media")
    for selector in re.findall(r"(?m)^([^@{}/][^{}]*)\{", css):
        assert selector.strip().startswith(allowed), selector


# ---------------------------------------------------------------- JS 接线与性能


def test_single_delegated_listener_with_raf():
    js = _fx()
    assert js.count("document.addEventListener('pointermove'") == 1
    assert "{ passive: true }" in js
    assert "requestAnimationFrame(flush)" in js
    assert "state.raf" in js
    # 没有逐卡监听
    assert "addEventListener('pointermove', handler)" not in js
    assert "forEach" not in js


def test_base_template_loads_card_fx_after_night_mode():
    base = _base()
    assert '<script src="/static/card-fx.js?v={{ asset_v }}"></script>' in base
    assert base.index("card-fx.js") > base.index("night-mode.js")
    assert base.index("card-fx.js") > base.index("lab-theme.css")
    # 无外部依赖
    for bad in ("http://", "https://", "unpkg", "jsdelivr", "cdn"):
        assert bad not in CARD_FX_JS.read_text(encoding="utf-8"), bad


def test_no_new_gray_small_notes():
    """R-UI-001：本次改动不新增任何形式的灰色小字备注（.opt 既有规则原样保留）。"""
    base = _base()
    assert 'class="opt"' not in base
    assert "card-fx-note" not in base
    section = _card_fx_section()
    assert ".opt" not in section
    assert "--faint" not in section
    # 存量 .opt 规则原样保留（3 条），没有借机新增灰字样式
    assert _theme().count(".opt{") == 3
    for path in (NIGHT_CSS, CARD_FX_JS):
        assert ".opt" not in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 纯函数 harness


def test_card_fx_pure_functions_via_node_vm():
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const context = vm.createContext({window: {}, console});
vm.runInContext(
  fs.readFileSync('src/quant_research_engine/gui/static/card-fx.js', 'utf8'), context);
const fx = context.window.QRECardFx;
assert.ok(fx, 'QRECardFx 未导出');
assert.equal(fx.TILT_MAX, 4, '倾斜上限必须是 4 度');

/* ---- spot：指针位置 → 光斑中心百分比 ---- */
const center = fx.spot(200, 100, 100, 50);
assert.equal(center.mx, 50);
assert.equal(center.my, 50);
const corner = fx.spot(200, 100, 0, 0);
assert.equal(corner.mx, 0);
assert.equal(corner.my, 0);
const far = fx.spot(200, 100, 200, 100);
assert.equal(far.mx, 100);
assert.equal(far.my, 100);
// 越界钳制在 0–100
assert.equal(fx.spot(200, 100, -80, 400).mx, 0);
assert.equal(fx.spot(200, 100, -80, 400).my, 100);
assert.equal(fx.spot(200, 100, 9999, -9999).mx, 100);
assert.equal(fx.spot(200, 100, 9999, -9999).my, 0);
// 零尺寸不产生 NaN，回退中心
const zero = fx.spot(0, 0, 10, 10);
assert.equal(zero.mx, 50);
assert.equal(zero.my, 50);
// 连续采样必须单调且落在 0–100
for (let i = 0; i <= 40; i++) {
  const s = fx.spot(320, 180, i * 8, i * 4.5);
  assert.ok(s.mx >= 0 && s.mx <= 100, 'mx 越界: ' + s.mx);
  assert.ok(s.my >= 0 && s.my <= 100, 'my 越界: ' + s.my);
}

/* ---- tilt：中心为 0、四角为极值、任何输入都落在 ±4 ---- */
const t0 = fx.tilt(200, 100, 100, 50);
assert.ok(Math.abs(t0.rx) === 0, '中心 rotateY 应为 0');
assert.ok(Math.abs(t0.ry) === 0, '中心 rotateX 应为 0');
// 四角：|rx| 与 |ry| 同时取到 ±4
const corners = [[0, 0], [200, 0], [0, 100], [200, 100]];
corners.forEach(function (c) {
  const t = fx.tilt(200, 100, c[0], c[1]);
  assert.ok(Math.abs(t.rx - 4) < 1e-9 || Math.abs(t.rx + 4) < 1e-9, 'rx 非极值: ' + t.rx);
  assert.ok(Math.abs(t.ry - 4) < 1e-9 || Math.abs(t.ry + 4) < 1e-9, 'ry 非极值: ' + t.ry);
});
// 符号：光标在右 → rotateY 正（右缘后退）；光标在下 → rotateX 负（下缘后退）
assert.ok(fx.tilt(200, 100, 200, 50).rx > 0, '右侧应给正 rotateY');
assert.ok(fx.tilt(200, 100, 0, 50).rx < 0, '左侧应给负 rotateY');
assert.ok(fx.tilt(200, 100, 100, 100).ry < 0, '下侧应给负 rotateX');
assert.ok(fx.tilt(200, 100, 100, 0).ry > 0, '上侧应给正 rotateX');
// 任何输入（含越界与零尺寸）都钳制在 ±4 内且为有限数
const samples = [[-1e6, -1e6], [1e6, 1e6], [-1, 999], [0, 0], [1e-9, 1e-9], [0, 0]];
samples.forEach(function (s) {
  const t = fx.tilt(200, 100, s[0], s[1]);
  assert.ok(Number.isFinite(t.rx) && Math.abs(t.rx) <= 4, 'rx 越界: ' + t.rx);
  assert.ok(Number.isFinite(t.ry) && Math.abs(t.ry) <= 4, 'ry 越界: ' + t.ry);
});
const z = fx.tilt(0, 0, 5, 5);
assert.ok(Math.abs(z.rx) === 0, '零尺寸 rotateY 应为 0');
assert.ok(Math.abs(z.ry) === 0, '零尺寸 rotateX 应为 0');

/* ---- 嵌套卡：只驱动最外层 ---- */
function fake(sel, parent, hasCanvas) {
  const node = {
    sel: sel, parentElement: parent || null, hasCanvas: !!hasCanvas,
    matches(s) { return s.split(',').some(x => x.trim() === node.sel); },
    closest(s) {
      let cur = node;
      while (cur) { if (cur.matches(s)) return cur; cur = cur.parentElement; }
      return null;
    },
    querySelector() { return node.hasCanvas ? {} : null; },
  };
  return node;
}
const outer = fake('.chart-box', null);
const inner = fake('.metric-card', outer);
assert.equal(fx.outermost(inner), outer, '嵌套卡必须向上爬到最外层');
assert.equal(fx.outermost(outer), outer, '最外层返回自身');
const plain = fake('.card', fake('.container', null));
assert.equal(fx.outermost(plain), plain, '无玻璃卡祖先时返回自身');

/* ---- 倾斜资格：含 canvas / 不在可倾斜卡族 → 不挂 transform ---- */
assert.equal(fx.eligibleForTilt(fake('.metric-card', null, false)), true, '并列小卡可倾斜');
assert.equal(fx.eligibleForTilt(fake('.metric-card', null, true)), false, '含 canvas 的小卡不倾斜');
assert.equal(fx.eligibleForTilt(fake('.card', null, false)), false, '大卡不倾斜（装小卡的容器）');
assert.equal(fx.eligibleForTilt(fake('.chart-box', null, false)), false, '图表大卡不倾斜');
assert.equal(fx.eligibleForTilt(fake('.panel', null, false)), false, '面板不倾斜');
assert.equal(fx.eligibleForTilt(fake('.big-link', null, false)), false, '入口卡不倾斜');
assert.equal(fx.eligibleForTilt(fake('.metric', null, false)), false, '.metric 不在倾斜族');
assert.equal(fx.eligibleForTilt(fake('.entry-card', null, false)), true, '新建策略三入口可倾斜');
"""
    _run(script)
