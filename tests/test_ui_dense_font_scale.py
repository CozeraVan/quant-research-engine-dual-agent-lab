"""UI-ROUND3：全站字号统一 +2px（14 → 16px / 13.5px → 15.5px）。

覆盖（先 RED 后 GREEN）：
- base.html 内联样式：table 16px、label/.muted/details summary/.chart-empty/
  .bench-bar/.tag-tabs button/.btn-sm 15.5px；旧值 13px / 12.5px 不再出现。
- lab-theme.css：table.tbl 16px、.tbl th 16px、.detail-table(-th) 16px、
  .label-inline 15.5px、.chart-empty 15.5px、.btn-sm 15.5px（不被 base 压掉）。
- .opt 辅助小字本轮随全站同步 +2，但不得低于 14px（只在声明处断言）。
- 本轮不推进 line-height：本文件不对任何 line-height 作断言。

浏览器侧验收（三视口真实 Chromium、表格计算字号、无横溢、无裁切）在
.tmp/ui-round3/verify.py，不进 CI（依赖本地服务与 Playwright）。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "src/quant_research_engine/gui/saas/templates"
STATIC = ROOT / "src/quant_research_engine/gui/static"


def _base() -> str:
    return (TEMPLATES / "base.html").read_text(encoding="utf-8")


def _lab_css() -> str:
    return (STATIC / "lab-theme.css").read_text(encoding="utf-8")


def _rule_body(css: str, selector: str) -> str:
    """取某选择器第一处声明块的内容（正则不处理嵌套 at-rule，本文件规则均为平铺）。"""
    match = re.search(
        r"(?<![\w.\-#])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match, f"未找到规则 {selector}"
    return match.group(1)


def _all_rule_bodies(css: str, selector: str) -> list[str]:
    return re.findall(r"(?<![\w.\-#])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)


# ------------------------------------------------------------ base.html 内联字号
class TestBaseInlineScale:
    def test_table_font_is_16px(self):
        body = _rule_body(_base(), "table")
        assert "font-size:16px" in body.replace(" ", ""), body

    def test_th_did_not_override_below_16(self):
        base = _base()
        assert "th{font-size:13.5px" not in base.replace(" ", "")
        assert ".tbl th{font-size:13.5px" not in base.replace(" ", "")

    def test_helper_scale_is_15_5px(self):
        # 注意：任务书写的 "details summary" 在 base.html 里以裸 summary 规则落地（L112）
        base = _base()
        for selector in ("label", ".muted", "summary", ".chart-empty",
                         ".bench-bar", ".tag-tabs button", ".btn-sm"):
            body = _rule_body(base, selector).replace(" ", "")
            assert "font-size:15.5px" in body, f"{selector} 未放大到 15.5px: {body}"

    def test_old_13px_helper_scale_gone(self):
        base = _base()
        for selector in ("label", ".muted", "summary", ".chart-empty",
                         ".bench-bar", ".tag-tabs button", ".btn-sm"):
            body = _rule_body(base, selector).replace(" ", "")
            assert "font-size:13px" not in body, f"{selector} 仍是 13px: {body}"


# ------------------------------------------------------- lab-theme.css 覆盖规则
class TestLabThemeScale:
    def test_table_tbl_is_16px(self):
        body = _rule_body(_lab_css(), "table.tbl")
        assert "font-size:16px" in body.replace(" ", ""), body
        assert "font-size:16.5px" not in body.replace(" ", "")

    def test_tbl_th_is_16px(self):
        body = _rule_body(_lab_css(), ".tbl th")
        assert "font-size:16px" in body.replace(" ", ""), body

    def test_detail_table_is_16px(self):
        css = _lab_css()
        body = _rule_body(css, ".detail-table")
        assert "font-size:16px" in body.replace(" ", ""), body
        th_body = _rule_body(css, ".detail-table th")
        assert "font-size:16px" in th_body.replace(" ", ""), th_body

    def test_btn_sm_not_shrinking_base(self):
        body = _rule_body(_lab_css(), ".btn-sm")
        assert "font-size:15.5px" in body.replace(" ", ""), body

    def test_label_inline_is_15_5px(self):
        body = _rule_body(_lab_css(), ".label-inline")
        assert "font-size:15.5px" in body.replace(" ", ""), body
        assert "font-size:14.5px" not in body.replace(" ", "")

    def test_chart_empty_is_15_5px_in_both_places(self):
        # lab-theme.css L250（白天）与 L388（夜间）各一处 .chart-empty
        bodies = _all_rule_bodies(_lab_css(), ".chart-empty")
        assert len(bodies) == 2, bodies
        for body in bodies:
            assert "font-size:15.5px" in body.replace(" ", ""), body


# ------------------------------------------------------------------- .opt 下限
class TestOptFloor:
    def test_no_opt_declaration_below_14px(self):
        files = [*TEMPLATES.glob("*.html"), *STATIC.glob("*.css")]
        offenders = []
        for path in files:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(
                    r"\.opt[^{}]*\{[^}]*font-size:([0-9.]+)px", text):
                if float(match.group(1)) < 14:
                    offenders.append(f"{path.name}: {match.group(0)[:80]}")
        assert not offenders, offenders