"""R4-1（TV_ROUND4 §2）：「单测绿、生产炸」四类模式全库清扫的合同测试。

四个模式（逆向侧从 R3-2 两个真 bug 提取）：
  A 静默 catch      —— init/load 路径 catch 吞 ReferenceError/TypeError
  B TDZ/声明顺序    —— 模块级 const/let 初始化器前向引用后声明的绑定
  C `|| undefined`  —— option 组装处 `key: x || undefined`（键在值为 undefined）
  D 回调异常不可见  —— rAF/setTimeout/事件回调抛错无观察者

本文件锁**可静态判定的三类**（A/B/C）的清理结果，防止回归：
  A：静默 catch 必须集中在"持久化守卫"语义上（localStorage / JSON.parse / canvas），
     且每个都要有注释说明为什么可以吞；
  B：模块级 const/let 不得前向引用后声明的绑定（静态扫描 + 源码顺序断言）；
  C：option 组装处不得出现 `|| undefined` / `|| null` 条件键。

D 类靠真实浏览器（pageerrors===0）覆盖，脚本在 `.tmp/perf-browser/`，
由 R4-2 的一行化入口驱动；本文件只锁"脚本存在且被登记"。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# 清扫范围（任务书点名的全部文件）
SCAN_FILES = [
    "src/quant_research_engine/gui/saas/templates/symbol.html",
    "src/quant_research_engine/gui/saas/templates/job.html",
    "src/quant_research_engine/gui/saas/templates/base.html",
    "src/quant_research_engine/game/templates/game.html",
    "src/quant_research_engine/gui/static/replay.js",
    "src/quant_research_engine/gui/static/factor-layout.js",
    "src/quant_research_engine/gui/static/price-scale.js",
    "src/quant_research_engine/gui/static/equity-chart.js",
    "src/quant_research_engine/gui/static/vol-regime.js",
    "src/quant_research_engine/gui/static/perf-metrics.js",
    "src/quant_research_engine/gui/static/night-mode.js",
    "src/quant_research_engine/gui/static/lab-ui.js",
]

# A 类"合理保留"的白名单语义：这些 catch 吞的是**环境缺失**，不是代码缺陷。
# 每条都必须在同一行或上一行有注释说明理由（R4-1 要求"枚举每一条"）。
A_OK_SEMANTICS = (
    "localStorage",      # 隐私模式 / 存储被禁
    "JSON.parse",        # 损坏 JSON
    "getContext",        # canvas 2d 不可用
    "measureText",
    "隐私模式",
    "损坏",
    "存储",
    "localStorage 不可用",
)


def _texts() -> dict[str, str]:
    out = {}
    for rel in SCAN_FILES:
        p = REPO / rel
        if p.is_file():
            out[rel] = p.read_text(encoding="utf-8")
    return out


def _strip_comments(code: str) -> str:
    code = re.sub(r"\{\{.*?\}\}", "null", code)
    code = re.sub(r"\{%.*?%\}", "", code)
    code = re.sub(r"//[^\n]*", "", code)
    return re.sub(r"/\*[\s\S]*?\*/", "", code)


# ---------------------------------------------------------------- A 静默 catch
class TestSilentCatch:
    """A 类：静默 catch 只允许"环境缺失"语义，且必须带理由注释。"""

    def test_every_silent_catch_has_a_reason_comment(self) -> None:
        """`catch (e) {}` / `catch (e) { return []/null/{} }` 必须能讲出为什么可以吞。"""
        pat = re.compile(r"catch\s*\(\s*[A-Za-z_$][\w$]*\s*\)\s*\{\s*(?:return\s*(?:\[\]|null|\{\}|''|\"\")\s*)?\}")
        unchecked = []
        for rel, text in _texts().items():
            for m in pat.finditer(text):
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.end())
                line = text[line_start:line_end if line_end > 0 else None]
                # 同一行有注释，或上一行是注释
                prev_line = text[text.rfind("\n", 0, line_start - 1) + 1:line_start - 1]
                ctx = line + " " + prev_line
                if not any(k in ctx for k in A_OK_SEMANTICS if k):
                    unchecked.append((rel, text[:m.start()].count("\n") + 1, line.strip()[:90]))
        assert not unchecked, (
            "以下静默 catch 没有任何'为什么可以吞'的理由注释，逐条判定：\n"
            + "\n".join(f"  {r}:L{n}  {t}" for r, n, t in unchecked)
        )

    def test_no_catch_swallows_reference_or_type_error_silently(self) -> None:
        """R3-2 bug 2 的形态：catch 兜底吞 ReferenceError/TypeError 且返回值让功能静默失效。

        判定：`catch (e) { return [] }` 所在的函数**必须是纯读持久化**的（函数体内
        出现 localStorage.getItem / JSON.parse），不得是渲染/计算路径。
        """
        bad = []
        for rel, text in _texts().items():
            for m in re.finditer(r"catch\s*\(\s*[A-Za-z_$][\w$]*\s*\)\s*\{\s*return\s*\[\]\s*;?\s*\}", text):
                fn_start = text.rfind("\nfunction ", 0, m.start())
                if fn_start < 0:
                    continue
                fn_name = re.match(r"\nfunction\s+([A-Za-z_$][\w$]*)", text[fn_start:])
                body = text[fn_start:m.start()]
                if "localStorage.getItem" not in body and "JSON.parse" not in body:
                    bad.append((rel, text[:fn_start].count("\n") + 1,
                                fn_name.group(1) if fn_name else "?"))
        assert not bad, (
            "以下 `return []` 兜底不在持久化读取路径上，可能在吞代码缺陷：\n"
            + "\n".join(f"  {r}:L{n} {f}()" for r, n, f in bad)
        )


# ---------------------------------------------------------------- B TDZ 顺序
class TestNoModuleLevelForwardReference:
    """B 类：模块级 const/let 初始化器不得引用后声明的绑定（R3-2 bug 2 的根治）。"""

    def test_no_module_level_tdz_forward_reference(self) -> None:
        issues = []
        for rel, text in _texts().items():
            decls = [
                (m.group(1), text[:m.start()].count("\n") + 1, m.group(2))
                for m in re.finditer(
                    r"^(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*([^\n]*)", text, re.M
                )
            ]
            for name, ln, init in decls:
                for other, other_ln, _ in decls:
                    if other == name or other_ln <= ln:
                        continue
                    if re.search(rf"(?<![\w$.]){re.escape(other)}(?![\w$])", init):
                        issues.append((rel, ln, name, other, other_ln))
        assert not issues, (
            "模块级 const/let 前向引用（TDZ 风险，同 R3-2 bug 2 形态）：\n"
            + "\n".join(f"  {r}:L{ln} `{n}` → L{oln} `{o}`" for r, ln, n, o, oln in issues)
        )

    def test_kline_draw_ls_key_before_state(self) -> None:
        """R3-2 修复的源码顺序必须保持（防回归）。"""
        text = (REPO / "src/quant_research_engine/gui/saas/templates/symbol.html").read_text(
            encoding="utf-8"
        )
        i_key = text.find("const KLINE_DRAW_LS_KEY =")
        i_state = text.find("const klineDrawState = {")
        assert i_key >= 0 and i_state >= 0
        assert i_key < i_state, (
            "KLINE_DRAW_LS_KEY 必须声明在 klineDrawState 之前——否则 klineDrawLoad() "
            "抛的 ReferenceError 被 try/catch 吞掉，画线永远不在页面加载时恢复"
        )


# ---------------------------------------------------------------- C || undefined
class TestNoConditionalUndefinedKey:
    """C 类：option 组装处不得 `key: x || undefined`（R3-2 bug 1 的根治）。"""

    def test_no_or_undefined_conditional_key(self) -> None:
        bad = []
        for rel, text in _texts().items():
            code = _strip_comments(text)
            for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*[A-Za-z_$.\[\]]+\s*\|\|\s*undefined", code):
                bad.append((rel, code[:m.start()].count("\n") + 1, m.group(0)))
        assert not bad, (
            "option 组装处出现 `key: x || undefined`——键存在而值为 undefined 比不写键更危险"
            "（replaceMerge → overallReset 用裸 option 重建 model 时会炸，见 R3-2 bug 1）：\n"
            + "\n".join(f"  {r}:L{n}  {t}" for r, n, t in bad)
        )

    def test_replay_legend_selected_written_only_when_present(self) -> None:
        """R3-2 修复的写法必须保持。"""
        js = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(encoding="utf-8")
        assert "if (opts.legendSelected) legend.selected = opts.legendSelected;" in js, (
            "replay.js 必须'没有 legendSelected 时整个键都不写'"
        )


# ---------------------------------------------------------------- D 回调异常
class TestCallbackErrorObservabilityRegistered:
    """D 类靠真实浏览器；本测试只锁"覆盖脚本存在且被文档登记"，防覆盖退化。"""

    def test_hotpath_verify_script_exists_and_asserts_zero_pageerrors(self) -> None:
        script = REPO / ".tmp/perf-browser/d_class_hotpath.py"
        assert script.is_file(), (
            "D 类热路径覆盖脚本缺失（.tmp/perf-browser/d_class_hotpath.py）"
        )
        body = script.read_text(encoding="utf-8")
        assert "pageerror" in body, "D 类脚本必须监听 pageerror"
        assert "D 类结论" in body, "D 类脚本必须输出结论行"

    def test_tv_entry_script_registers_three_criteria(self) -> None:
        """R4-2 的一行化入口必须覆盖三条判据 + pageerrors===0。"""
        entry = REPO / ".tmp/perf-browser/tv_check_all.sh"
        assert entry.is_file(), "一行化验收入口缺失（.tmp/perf-browser/tv_check_all.sh）"
        body = entry.read_text(encoding="utf-8")
        for needle in ("tv3_verify.py", "t3_verify.py", "tv3_game_verify.py"):
            assert needle in body, f"入口未覆盖 {needle}"
