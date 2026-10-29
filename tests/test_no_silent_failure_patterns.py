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


# ---------------------------------------------------------------- C 类消费方语义
class TestConditionalKeyConsumerSemantics:
    """C 类正式定义（TV_ROUND5 §1.2 裁定）：**该键的消费方是否不解引用就取属性**。

    炸例：`legend.selected` → ECharts `LegendModel.isSelected()` 无条件
    `selected.hasOwnProperty(name)`（R3-2 bug 1）。
    不炸例：series 级 `markLine: undefined` → ECharts 走无配置分支。

    配套两条：
    1. 判定用消费方语义，不用值语义——`markLine` 这类实测不炸的**不改**，
       避免无 bug 的 churn；
    2. 新代码默认风格仍是「缺就不写键」——判定标准宽了，写作标准不放宽。
    """

    def test_markline_undefined_key_is_left_alone(self) -> None:
        """`markLine: klineLastPriceMarkLine()` 不得被改成「缺就不写键」。

        它是 C 类里**实测不炸**的样本（probe 见 `.tmp/perf-browser/probe_markline_undef.py`）；
        按消费方语义应保留原样。这条测试同时是"防后来者来回改"的锚。
        """
        tpl = (REPO / "src/quant_research_engine/gui/saas/templates/symbol.html").read_text(
            encoding="utf-8"
        )
        assert "markLine: klineLastPriceMarkLine()" in tpl, (
            "markLine 直接赋值的写法被改掉了——按 C 类消费方语义它不炸，"
            "不应为'看起来统一'而改（见 probe_markline_undef.py）"
        )

    def test_markline_probe_landed(self) -> None:
        """R5-4：被回传引用的 probe 必须落盘存在（证据不许只活在引文里）。"""
        probe = REPO / ".tmp/perf-browser/probe_markline_undef.py"
        assert probe.is_file(), (
            "probe_markline_undef.py 缺失——TV_ROUND4 §1.4 引用过它，"
            "被引用的 scratch 就是证据，证据不许消失"
        )
        body = probe.read_text(encoding="utf-8")
        assert "C 类判定" in body, "probe 缺结论行"
        assert "消费方" in body, "probe 必须写清 C 类的消费方语义判定标准"

    def test_legend_selected_still_uses_write_only_when_present(self) -> None:
        """炸例那一侧必须保持「缺就不写键」（写作标准不放宽）。"""
        js = (REPO / "src/quant_research_engine/gui/static/replay.js").read_text(encoding="utf-8")
        assert "if (opts.legendSelected) legend.selected = opts.legendSelected;" in js


# ------------------------------------------------ 夜间模式整体暂停（QRE-SAAS-NIGHT-PAUSED）
class TestNightModePause:
    """2026-10-30 用户决定：aguhuice.com 暂停夜间模式，所有人一律浅色。

    四个入口都必须落到 light（probe：`.tmp/perf-browser/verify_night_pause.py`）：
      A 存量 localStorage `qre-theme=dark`
      B 系统 `prefers-color-scheme: dark`
      C 干净 context
      D 手动 toggle（按钮已隐藏，但脚本/控制台仍可能调到，必须夹成 light）
    """

    def test_master_switch_present_and_false(self) -> None:
        js = (REPO / "src/quant_research_engine/gui/static/night-mode.js").read_text(
            encoding="utf-8")
        assert "var NIGHT_MODE_ENABLED = false;" in js, (
            "night-mode.js 必须有 NIGHT_MODE_ENABLED 总开关且当前为 false"
        )

    def test_resolved_and_set_both_clamped(self) -> None:
        """只夹 resolvedTheme 不够——toggle→set('dark') 会绕过（实测过）。"""
        js = (REPO / "src/quant_research_engine/gui/static/night-mode.js").read_text(
            encoding="utf-8")
        assert "if (!NIGHT_MODE_ENABLED) return 'light';" in js, (
            "resolvedTheme() 必须在暂停期恒返回 light"
        )
        assert "if (!NIGHT_MODE_ENABLED) return apply('light');" in js, (
            "set() 必须在暂停期夹成 light 且不落 localStorage"
        )

    def test_fouc_guard_also_respects_pause(self) -> None:
        """base.html 的首屏防闪脚本必须同步，否则存量 dark 用户首屏会闪一下夜间。"""
        tpl = (REPO / "src/quant_research_engine/gui/saas/templates/base.html").read_text(
            encoding="utf-8")
        assert "QRE-SAAS-NIGHT-PAUSED" in tpl, "base.html 防闪脚本缺暂停开关"
        assert "var NIGHT_PAUSED=true;" in tpl, "防闪脚本的暂停开关必须为 true"

    def test_pause_probe_landed(self) -> None:
        """四入口 probe 必须落盘（被引用的 scratch 就是证据）。"""
        probe = REPO / ".tmp/perf-browser/verify_night_pause.py"
        assert probe.is_file(), "verify_night_pause.py 缺失"
        body = probe.read_text(encoding="utf-8")
        for needle in ("qre-theme", "prefers-color-scheme", "toggle"):
            assert needle in body, f"probe 未覆盖入口: {needle}"


# ------------------------------------- MACD 旧系退场证据链持久化（TV R6-1）
class TestLegacyScanEvidenceLogPersistent:
    """R6-1：退场条件①「连续 4 次周扫计数为 0」的唯一证据链必须持久化。

    隐患（逆向侧 ROUND6 复核发现）：周扫日志原先写在 `.tmp/`，
    而 `.tmp/` 是 scratch、会被清——一旦被清，「连续 4 次」从此无法判定，
    `familyOf` 旧名分支的退场机制**静默失效**，且无人会察觉。
    保留期缩到 15 天（用户 2026-10-30）后条件② 约 2026-11-08 即满足，
    条件① 的连续计数从此是退场的唯一关键路径，日志丢了就永远退不了场。
    """

    LOG = "deploy/saas/macd-legacy-scan.log"

    def test_evidence_log_lands_in_repo_and_is_tracked(self) -> None:
        log = REPO / self.LOG
        assert log.is_file(), f"周扫证据日志缺失（{self.LOG}）——R6-1 要求仓库内持久路径"
        body = log.read_text(encoding="utf-8")
        assert body.count("=== ") >= 1, (
            "证据日志必须含至少一条历史记录（空文件等于证据已丢失）"
        )
        # `*.log` 会忽略它，必须有显式 negation，否则新 clone 里没有这份证据
        gi = (REPO / ".gitignore").read_text(encoding="utf-8")
        assert f"!{self.LOG}" in gi, (
            f".gitignore 缺 `!{self.LOG}` negation——*.log 会把证据链挡在库外"
        )

    def test_script_writes_to_persistent_log(self) -> None:
        script = (REPO / "deploy/saas/scan-macd-legacy-names.sh").read_text(
            encoding="utf-8")
        log_line = next(
            (ln for ln in script.splitlines() if ln.startswith("LOG=")), ""
        )
        assert log_line, "scan 脚本缺 LOG= 赋值行"
        assert self.LOG in log_line, f"LOG= 必须指向仓库内持久路径 {self.LOG}"
        assert ".tmp" not in log_line, "LOG= 不许再指向 .tmp（scratch 会被清）"

    def test_unit_stdout_not_in_scratch(self) -> None:
        """timer 的 stdout 也不该活在 scratch；走 journal 与证据日志形成双保险。"""
        unit = (REPO / "deploy/systemd/qre-macd-legacy-scan.service").read_text(
            encoding="utf-8")
        assert "StandardOutput=journal" in unit, "unit 的 StandardOutput 应为 journal"
        assert ".tmp/" not in unit, "unit 里不许再出现 .tmp 路径（运行痕迹也该持久）"
