"""R4-3（TV_ROUND4 §4）：模板内联 JS 语法守卫测试。

背景事故（R3-4 §3.6）：批量删除「T6 冻结注释 → `function renderKline(d){`」时，
那段注释其实夹在 `klineIndicatorDialog()` **函数体中间**，把该函数后半部分和闭合
花括号一起删了。结果 `node --check` 报 `Unexpected end of input`，而 pytest 报的是
「未找到 lwcDispose / klineDisposeEngines」——**离根因极远**，排错了半天。

本测试把「改完模板立刻 node --check」从人的纪律变成 CI 门禁：

1. 扫**所有**模板（不止 symbol/game）的内联 `<script>`；
2. Jinja 变量替换为 `null`、语句标签剔除后 `node --check`；
3. 断言零语法错误；
4. **非永真**：用「事故写法」注入一份坏模板，断言测试红（§7 回传第 3 项）。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TEMPLATE_DIRS = [
    REPO / "src/quant_research_engine/gui",
    REPO / "src/quant_research_engine/game",
]


def _templates() -> list[Path]:
    out: list[Path] = []
    for d in TEMPLATE_DIRS:
        out.extend(sorted(d.rglob("*.html")))
    return out


def _inline_scripts(html: str) -> list[str]:
    """内联 <script>（排除带 src 的外部脚本）。"""
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)


def _node_check(source: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if not node and Path("/home/van/codex-local/node-v22/bin/node").exists():
        node = "/home/van/codex-local/node-v22/bin/node"
    if not node:
        pytest.skip("node 不可用")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(source)
        path = fh.name
    try:
        return subprocess.run([node, "--check", path], capture_output=True, text=True)
    finally:
        Path(path).unlink(missing_ok=True)


def _render_jinja(block: str) -> str:
    """Jinja 变量 → null、语句标签 → 空（保行号，便于定位）。"""
    out = re.sub(r"\{\{.*?\}\}", "null", block)
    return re.sub(r"\{%.*?%\}", "", out)


class TestTemplateInlineJsSyntax:
    """所有模板的内联 JS 必须语法正确。"""

    def test_templates_found(self) -> None:
        tpls = _templates()
        assert len(tpls) >= 5, f"只找到 {len(tpls)} 个模板，扫描范围可能不对"

    @pytest.mark.parametrize("tpl", _templates(), ids=lambda p: p.name)
    def test_inline_js_syntax_ok(self, tpl: Path) -> None:
        html = tpl.read_text(encoding="utf-8")
        blocks = _inline_scripts(html)
        if not blocks:
            pytest.skip(f"{tpl.name} 无内联 script")
        for i, block in enumerate(blocks):
            src = _render_jinja(block)
            if not src.strip():
                continue
            r = _node_check(src)
            assert r.returncode == 0, (
                f"{tpl.name} 的内联 script #{i} 语法错误：\n{r.stderr[:600]}"
            )

    def test_every_template_covered(self) -> None:
        """防止新增模板落在扫描范围外（静默漏扫 = 守卫失效）。"""
        covered = {p.name for p in _templates()}
        # 已知的业务模板（含 lab 侧）
        must = {"symbol.html", "job.html", "base.html", "game.html", "lab_symbol.html",
                "lab_result.html", "admin.html", "console.html"}
        missing = must - covered
        assert not missing, f"这些模板没被扫描到（检查 TEMPLATE_DIRS）：{sorted(missing)}"


class TestAccidentReproduction:
    """§7 回传第 3 项：用 R3-4 事故写法注入坏模板，断言守卫红灯。"""

    ACCIDENT = """<!doctype html>
<html><head><script>
function klineIndicatorDialog(){
  const a = 1;
  // QRE-KLINE-LWC-FROZEN（T6）：这段注释原本夹在函数体中间
  // 删除时若从注释开始切，就会把下面的函数体后半部分一起删掉
function renderKline(d){
  return a;
}
</script></head><body></body></html>
"""

    def test_accident_writing_is_caught(self) -> None:
        """坏模板必须被 node --check 判红（证明守卫非永真）。"""
        blocks = _inline_scripts(self.ACCIDENT)
        assert blocks, "事故样本应含一个内联 script"
        r = _node_check(blocks[0])
        assert r.returncode != 0, (
            "守卫失效：事故写法（删注释删穿函数体）居然语法正确——"
            "说明 node --check 没真正执行或样本没复现事故形态"
        )
        assert "Unexpected end of input" in r.stderr or "SyntaxError" in r.stderr, (
            f"事故样本的报错形态与 R3-4 不一致：{r.stderr[:300]}"
        )

    def test_fixed_writing_passes(self) -> None:
        """对照：同样的代码把函数体补完整后必须通过（证明不是见函数名就红）。"""
        good = self.ACCIDENT.replace(
            "function renderKline(d){\n  return a;\n}",
            "  const b = 2;\n  return a + b;\n}\nfunction renderKline(d){\n  return 1;\n}",
        )
        blocks = _inline_scripts(good)
        r = _node_check(blocks[0])
        assert r.returncode == 0, f"补完整后应通过，实际报错：{r.stderr[:300]}"
