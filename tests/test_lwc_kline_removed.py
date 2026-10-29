"""R3-4（TV_ROUND3 §5）：休眠 LWC 试点已整体移除的合同测试。

原 `tests/test_lwc_kline_adapter.py`（13 例）断言的是"LWC 资产**在**、代码**在**、
引擎开关**恒 echarts**"——那是 T6 冻结态。R3-4 按逆向侧"解冻从 git 历史找回比养着
400KB 死码便宜"的结论，把 LWC 分支、vendored 资产、DOM 图例/attribution 全部删除，
本文件改为断言它们**不再被引用/加载**。

删除范围（改动前 → 后）：
- `symbol.html` 2570 → 2294 行（-276 行死代码）
- vendored 资产：`chart-core/` 整个目录（js 197,922B + LICENSE 11,347B +
  两张品牌水印 PNG 450,465B）
- 模板 `<script>` 引用 2 个（立省约 199KB 传输）

回滚方式：`git log` 找回（见 `docs/agent/24_KLINE_LWC_FROZEN.md`）。
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SYMBOL_TPL = (
    REPO / "src/quant_research_engine/gui/saas/templates/symbol.html"
).read_text(encoding="utf-8")
CHART_CORE = REPO / "src/quant_research_engine/gui/static/chart-core"


class TestLwcAssetsRemoved:
    """vendored 资产与模板引用都必须消失。"""

    def test_vendor_directory_gone(self) -> None:
        assert not CHART_CORE.exists(), (
            "static/chart-core/ 必须整体删除（R3-4）；解冻从 git 历史找回"
        )

    def test_no_script_tag_loads_lwc(self) -> None:
        for m in re.finditer(r"<(?:script|link)\b[^>]*?(?:src|href)=\"([^\"]*)\"", SYMBOL_TPL):
            url = m.group(1)
            assert "chart-core" not in url, f"模板仍在加载 LWC 资产: {url}"
            assert "lightweight-charts" not in url, f"模板仍在加载 LWC 库: {url}"
            assert "kline-lwc" not in url, f"模板仍在加载 LWC 适配层: {url}"

    def test_no_lwc_identifier_in_template(self) -> None:
        # 允许的唯一例外：解释"为什么没有"的注释（不含可执行引用）
        code = re.sub(r"\{#.*?#\}", "", SYMBOL_TPL, flags=re.S)
        code = re.sub(r"//[^\n]*", "", code)
        code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
        for bad in ("LightweightCharts", "QRELwcAdapter", "lwcDispose",
                    "renderKlineLwc", "lwcRenderLegend", "lwcApplyTheme",
                    "lwcSyncAttrib", "lwcChart", "lwcMarkers", "lwcHover",
                    "lwcThresholds", "KLINE_ENGINE_LS_KEY", "klineEngine",
                    "setKlineEngine", "renderKlineDispatch"):
            assert bad not in code, f"symbol.html 仍引用已移除的 LWC 标识符: {bad}"

    def test_lwc_dom_removed(self) -> None:
        assert 'id="kline-legend"' not in SYMBOL_TPL, "LWC DOM 图例必须删除"
        assert 'id="kline-attrib"' not in SYMBOL_TPL, "attribution 行必须删除"
        assert "kline-attrib-mark" not in SYMBOL_TPL, "品牌水印 img 必须删除"
        assert "kline-attrib-link" not in SYMBOL_TPL, "TradingView 链接必须删除"

    def test_lwc_css_removed(self) -> None:
        for sel in (".kline-legend", ".kline-attrib"):
            assert sel not in SYMBOL_TPL, f"CSS 规则 {sel} 必须删除"


class TestSingleEngineRemains:
    """删完之后，剩下的必须是完整的单引擎路径。"""

    def test_render_kline_is_the_only_entry(self) -> None:
        assert re.search(r"\bfunction renderKline\(d\)\{", SYMBOL_TPL), (
            "renderKline 必须保留（唯一渲染入口）"
        )
        assert "function klineDisposeEngines(){" in SYMBOL_TPL, (
            "klineDisposeEngines 必须保留（单引擎清理）"
        )

    def test_dispose_only_touches_echarts(self) -> None:
        i = SYMBOL_TPL.find("function klineDisposeEngines(){")
        assert i >= 0
        block = SYMBOL_TPL[i:i + 700]
        assert "echarts.getInstanceByDom" in block, "必须仍清 ECharts 实例"
        assert "lwcDispose" not in block, "不得再调 lwcDispose"

    def test_all_rerender_paths_call_render_kline(self) -> None:
        """三处重渲染点（load / chip 点击 / 指标设置 / 重播退出）都必须直连 renderKline。"""
        assert "renderKlineDispatch" not in SYMBOL_TPL
        assert SYMBOL_TPL.count("renderKline(d);") >= 2, "重渲染调用点不足"
        assert "const rebuild = renderKline;" in SYMBOL_TPL
        assert "const rebuildKline = renderKline;" in SYMBOL_TPL

    def test_kline_grid_still_delegates_shared_layer(self) -> None:
        """R3-1 的收敛不能被这轮删除带坏。"""
        assert "QREFactorLayout.paneGrids(" in SYMBOL_TPL, (
            "klineGridSpec 必须仍委派共享层 paneGrids"
        )


class TestPageShrank:
    """死代码确实没了（防"删了引用、留着代码"的半成品）。"""

    def test_template_shrank_materially(self) -> None:
        # 改动前 2570 行；删除 LWC 分支后应 ≤ 2350 行
        lines = SYMBOL_TPL.count("\n")
        assert lines <= 2350, f"symbol.html 仍有 {lines} 行，疑似死代码未删净"

    def test_no_full_market_report_regression_marker(self) -> None:
        """冻结文档指向 git 历史，不得在代码里留"以后可能解冻"的分支。"""
        assert "休眠" not in SYMBOL_TPL, "symbol.html 不应再保留休眠态说明"
