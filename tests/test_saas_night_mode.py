"""QRE-SAAS-NIGHT-MODE：SaaS 全站夜间模式（浅色外观与数据零改动）。

覆盖：
- static/night-mode.css：仅夜间作用域（:root[data-theme="dark"]）+ 主题按钮，
  8 个指定夜色齐全，无白卡/白按钮残留规则。
- static/night-mode.js：localStorage 键、系统偏好回退、首帧应用、按钮文案与
  aria、主题事件、ECharts 中性层与品牌紫/红绿映射（不重算数据）。
- base.html / login_callback.html：首帧 bootstrap 在首个样式表之前、夜间样式与
  脚本引入、带文字的主题切换按钮；meta theme-color 双色。
- 模板与 replay.js：8 处图表接入 themeChart（含 8080/8081 共用脚本的守卫）。
- 浅色零回归：lab-theme.css 与 base 的浅色 token / 品牌色原样保留。
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUI = ROOT / "src/quant_research_engine/gui"
TEMPLATES = GUI / "saas/templates"
STATIC = GUI / "static"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _css() -> str:
    return _text(STATIC / "night-mode.css")


def _js() -> str:
    return _text(STATIC / "night-mode.js")


def _base() -> str:
    return _text(TEMPLATES / "base.html")


DARK_TOKENS = {
    "--bg": "#17153B",
    "--card": "#2E236C",
    "--line": "#433D8B",
    "--text": "#F1EDF8",
    "--muted": "#C8ACD6",
    "--accent": "#7E60BF",
    "--accent-deep": "#C8ACD6",
    "--accent-soft": "#2E236C",
}


class TestNightModeCss:
    def test_dark_scope_and_tokens(self) -> None:
        css = _css()
        assert ':root[data-theme="dark"]' in css
        root_block = css[css.index(':root[data-theme="dark"]'):]
        root_block = root_block[: root_block.index("}")]
        for name, value in DARK_TOKENS.items():
            assert f"{name}:{value}" in root_block.replace(" ", ""), name

    def test_red_up_green_down_kept(self) -> None:
        css = _css().replace(" ", "")
        assert "--up:#FF7A7A" in css
        assert "--down:#4FD69A" in css

    def test_all_rules_scoped_or_button(self) -> None:
        css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
        allowed = (':root[data-theme="dark"]', ".tt-btn", "@media")
        for selector in re.findall(r"(?m)^([^@{}/][^{}]*)\{", css):
            sel = selector.strip()
            assert sel.startswith(allowed), sel

    def test_no_white_surfaces(self) -> None:
        css = _css().lower()
        for bad in ("background:#fff", "background: #fff", "background:white", "background: white"):
            assert bad not in css

    def test_button_float_and_narrow_screen(self) -> None:
        css = _css()
        assert ".tt-btn.tt-float" in css
        assert "max-width:960px" in css
        assert "position:fixed" in css

    def test_console_and_inline_fallbacks(self) -> None:
        css = _css()
        assert ":root[data-theme=\"dark\"] #guest-note" in css
        assert '[style*="#8B7FBE"]' in css
        assert '[style*="#6750A4"]' in css


class TestNightModeScript:
    def test_storage_and_system_fallback(self) -> None:
        js = _js()
        assert "'qre-theme'" in js
        assert "localStorage.setItem(THEME_KEY" in js
        assert "(prefers-color-scheme: dark)" in js
        # 无存储值时跟随系统且不写回
        assert "if (!storedTheme()) apply(systemTheme())" in js

    def test_apply_theme_and_meta(self) -> None:
        js = _js()
        for token in (
            "document.documentElement.dataset.theme = t",
            "meta[name=\"theme-color\"]",
            "META_LIGHT = '#4A3C78'",
            "META_DARK = '#17153B'",
            "qre:themechange",
        ):
            assert token in js, token

    def test_button_label_and_aria(self) -> None:
        js = _js()
        assert "日间模式" in js
        assert "夜间模式" in js
        assert "aria-pressed" in js
        assert "aria-label" in js
        assert "tt-btn tt-float" in js

    def test_echarts_neutral_and_series_colors(self) -> None:
        js = _js()
        for token in (
            "backgroundColor: 'transparent'",
            "tooltip",
            "#2E236C",
            "#433D8B",
            "#F1EDF8",
            "#C8ACD6",
            "addPair(['#6750a4'], '#9b84d8')",
            "addPair(['#d43030', '#c93a3a'], '#ff7a7a')",
            "addPair(['#1e8e5a', '#1a9e4b'], '#4fd69a')",
            "__qreOrigSetOption",
            "{ notMerge: true }",
        ):
            assert token in js, token

    def test_theme_chart_never_touches_data(self) -> None:
        js = _js()
        assert "if (k === 'data' || k === 'dataset') continue;" in js
        assert "window.QRETheme" in js

    def test_syntax(self) -> None:
        node = shutil.which("node")
        if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
            node = "/home/van/codex-local/node-v22/bin/node"
        if not node:
            pytest.skip("node 不可用")
        proc = subprocess.run(
            [node, "--check", str(STATIC / "night-mode.js")],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, proc.stderr


class TestBaseTemplate:
    def test_bootstrap_before_first_stylesheet(self) -> None:
        html = _base()
        boot = html.index("localStorage.getItem('qre-theme')")
        first_css = html.index('<link rel="stylesheet"')
        assert boot < first_css

    def test_assets_linked(self) -> None:
        html = _base()
        assert '/static/night-mode.css?v={{ asset_v }}' in html
        assert '/static/night-mode.js?v={{ asset_v }}' in html
        # 夜间样式在浅色主题之后、脚本在既有脚本之后
        assert html.index("night-mode.css") > html.index("lab-theme.css")
        assert html.index("night-mode.js") > html.index("wait-mask.js")

    def test_theme_color_meta_both(self) -> None:
        html = _base()
        assert '<meta name="theme-color" content="#4A3C78">' in html
        assert "'#17153B'" in html
        assert "'#4A3C78'" in html

    def test_toggle_button_in_nav(self) -> None:
        html = _base()
        m = re.search(r'<button[^>]*class="tt-btn"[^>]*>夜间模式</button>', html)
        assert m, "缺少主题切换按钮"
        button = m.group(0)
        assert 'aria-pressed="false"' in button
        assert 'aria-label="' in button
        nav = html.index('<nav class="mainnav">')
        assert nav < html.index(button) < html.index("</nav>")

    def test_light_tokens_unchanged(self) -> None:
        html = _base()
        assert ":root{--bg:#FAF9FC;--card:#fff;--line:#E4DFEE;--text:#241F2E;--muted:#9A93A6;--accent:#6750A4;--pos:#C93A3A;--neg:#1E8E5A}" in html
        assert '<meta name="theme-color" content="#4A3C78">' in html
        lab = _text(STATIC / "lab-theme.css")
        assert "data-theme" not in lab


class TestLoginCallback:
    def test_dark_tokens_and_assets(self) -> None:
        html = _text(TEMPLATES / "login_callback.html")
        assert ':root[data-theme="dark"]{--bg:#17153B;--card:#2E236C;--line:#433D8B' in html
        assert '/static/night-mode.css?v={{ asset_v }}' in html
        assert '/static/night-mode.js?v={{ asset_v }}' in html

    def test_bootstrap_early_and_button(self) -> None:
        html = _text(TEMPLATES / "login_callback.html")
        boot = html.index("localStorage.getItem('qre-theme')")
        assert boot < html.index(":root{--bg:#FAF9FC")
        assert 'class="tt-btn tt-float"' in html
        assert "夜间模式" in html

    def test_redirect_logic_untouched(self) -> None:
        html = _text(TEMPLATES / "login_callback.html")
        assert "localStorage.setItem('saas_token'" in html
        assert "const NEXT = {{ next | default('/saas/', true) | tojson }};" in html
        assert "location.replace(NEXT);" in html


class TestChartHooks:
    @pytest.mark.parametrize(
        ("rel", "expected"),
        [
            # QRE-VOL-REGIME-NO-BARCHART：job.html 删掉三等分柱状图后
            # 少一个 echarts.init + 一个 themeChart（5 → 4）
            ("saas/templates/job.html", 4),
            ("saas/templates/symbol.html", 2),
            ("static/replay.js", 1),
        ],
    )
    def test_theme_chart_calls(self, rel: str, expected: int) -> None:
        text = _text(GUI / rel)
        calls = re.findall(
            r"if \(window\.QRETheme && QRETheme\.themeChart\) QRETheme\.themeChart\((\w+)\);",
            text,
        )
        assert len(calls) == expected, rel
        inits = text.count("echarts.init(")
        assert inits == expected, f"{rel}: init={inits} calls={len(calls)}"


class TestForbiddenLinks:
    def test_no_private_entrypoints(self) -> None:
        for path in (
            STATIC / "night-mode.css",
            STATIC / "night-mode.js",
            TEMPLATES / "base.html",
            TEMPLATES / "login_callback.html",
        ):
            text = _text(path)
            for bad in ("/admin", "8080", "8081"):
                assert bad not in text, f"{path.name}: {bad}"