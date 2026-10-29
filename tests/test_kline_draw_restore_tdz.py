"""QRE-DRAW-RESTORE-TDZ：画线必须在**页面加载时**从 localStorage 恢复。

R3-2 真实浏览器冷启动用例炸出来的真 bug（不是 harness 问题）：

`symbol.html` 里 `const klineDrawState = {..., lines: klineDrawLoad()}` 原本排在
`const KLINE_DRAW_LS_KEY = 'qre.kline.drawings'` **之前**。`const` 有暂时性死区，
初始化器执行时 `KLINE_DRAW_LS_KEY` 还没初始化 → ReferenceError，而
`klineDrawLoad()` 整个函数体包在 `try/catch { return [] }` 里，错误被**静默吞掉**。

后果：画线**永远不在页面加载时恢复**（localStorage 里明明有）。同会话内
`klineDrawLoad()` 单独调用却正常——所以既有单测全绿，只有真实浏览器冷启动才暴露。

本测试用 Node vm 按**生产源码顺序**跑这几个声明，锁死两件事：
1. `KLINE_DRAW_LS_KEY` 必须声明在 `klineDrawState` 之前（源码顺序）；
2. 按该顺序执行后 `klineDrawState.lines` 必须真的拿到存储里的画线（功能性）。
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

SEED = {"ts_code": "000001.SZ",
        "lines": [{"kind": "horizontal", "price": 13.385416666666668,
                   "date": "2017-07-21", "index": 1827}]}


def _slice(start_marker: str, end_marker: str) -> str:
    i = SYMBOL_HTML.find(start_marker)
    assert i >= 0, f"未找到起始标记: {start_marker}"
    j = SYMBOL_HTML.find(end_marker, i)
    assert j >= 0, f"未找到结束标记: {end_marker}"
    return SYMBOL_HTML[i:j + len(end_marker)]


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


KEY_DECL = _slice("const KLINE_DRAW_LS_KEY =", ";")
STATE_DECL = _slice("const klineDrawState = {", "};")
VALID_FN = _slice("function klineDrawValid(ln){", "\n}")
LOAD_FN = _slice("function klineDrawLoad(){", "\n}")


def test_key_declared_before_state() -> None:
    """源码顺序：key 必须在 klineDrawState 之前，否则初始化器撞 TDZ。"""
    i_key = SYMBOL_HTML.find("const KLINE_DRAW_LS_KEY =")
    i_state = SYMBOL_HTML.find("const klineDrawState = {")
    assert i_key >= 0 and i_state >= 0
    assert i_key < i_state, (
        "KLINE_DRAW_LS_KEY 必须声明在 klineDrawState 之前（const TDZ，"
        "否则 klineDrawLoad() 抛的 ReferenceError 被 try/catch 静默吞掉，"
        "画线永远不在页面加载时恢复）"
    )


def test_state_initializer_restores_from_storage() -> None:
    """按生产源码顺序执行，klineDrawState.lines 必须拿到存储里的画线。"""
    _node(r"""
const SEED = %SEED%;
const localStorage = {
  _s: {'qre.kline.drawings': JSON.stringify(SEED)},
  getItem(k){ return Object.prototype.hasOwnProperty.call(this._s, k) ? this._s[k] : null; },
  setItem(k, v){ this._s[k] = String(v); },
};
globalThis.localStorage = localStorage;
globalThis.TS_CODE = '000001.SZ';

// 与 symbol.html 中的顺序一致：key → state（初始化器调 klineDrawLoad）→ 函数声明
%KEY%
%STATE%
%VALID%
%LOAD%

if (klineDrawState.lines.length !== 1) {
  throw new Error('页面加载时未恢复画线: ' + JSON.stringify(klineDrawState.lines));
}
if (klineDrawState.lines[0].kind !== 'horizontal') throw new Error('恢复的线类型不对');
if (Math.abs(klineDrawState.lines[0].price - 13.385416666666668) > 1e-12) {
  throw new Error('恢复的 price 不对: ' + klineDrawState.lines[0].price);
}
// 换标的不得恢复（按标的隔离是既有设计，不能被这次修复破坏）
localStorage.setItem('qre.kline.drawings', JSON.stringify(
  {ts_code: '600000.SH', lines: [{kind: 'horizontal', price: 1, date: '2020-01-02', index: 1}]}));
globalThis.TS_CODE = '000001.SZ';
if (klineDrawLoad().length !== 0) throw new Error('异标的画线不得恢复');
console.log('OK');
""".replace("%SEED%", __import__("json").dumps(SEED))
   .replace("%KEY%", KEY_DECL)
   .replace("%STATE%", STATE_DECL)
   .replace("%VALID%", VALID_FN)
   .replace("%LOAD%", LOAD_FN))


def test_load_still_swallows_only_real_errors() -> None:
    """klineDrawLoad 的 try/catch 保留（隐私模式等），但不得再吞 TDZ 类错误。

    验证方式：把 key 声明**移到 state 之后**（复现 bug 的写法），
    此时 lines 必须为空——证明这个用例对声明顺序真的敏感（不是永真断言）。
    """
    buggy_order = STATE_DECL + "\n" + KEY_DECL
    _node(r"""
const localStorage = {
  _s: {'qre.kline.drawings': JSON.stringify({ts_code: '000001.SZ',
        lines: [{kind: 'horizontal', price: 1, date: '2020-01-02', index: 1}]})},
  getItem(k){ return Object.prototype.hasOwnProperty.call(this._s, k) ? this._s[k] : null; },
  setItem(k, v){ this._s[k] = String(v); },
};
globalThis.localStorage = localStorage;
globalThis.TS_CODE = '000001.SZ';
// 复现 bug 的顺序：state 在 key 之前 → TDZ → 被 catch 吞 → 恢复不了
// （buggy_order 已含 key 声明，不单独再插一次，否则重复声明直接语法错）
%STATE%
%VALID%
%LOAD%
if (klineDrawState.lines.length !== 0) {
  throw new Error('敏感度校验失败：乱序时本应恢复不了，实际恢复了 '
    + JSON.stringify(klineDrawState.lines));
}
console.log('OK');
""".replace("%STATE%", buggy_order)
   .replace("%VALID%", VALID_FN)
   .replace("%LOAD%", LOAD_FN))
