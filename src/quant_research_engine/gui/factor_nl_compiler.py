"""自然语言 → indicators_tushare 因子代码生成器（GUI 新因子创建闭环 P2）。

复用 ``nl_compiler.call_llm`` / ``nl_config``（OpenAI 兼容协议，DeepSeek 配置
走同一组 QRE_NL_LLM_* 环境变量），但使用独立的因子写作系统提示词
（约束提炼自 indicators_tushare/docs/FACTOR_AUTHORING.md）。

输出协议（两段式，测试里固定）：
  <<<CODE>>>
  <Python 源码，可带 ```python 围栏，解析时剥离>
  <<<META>>>
  <YAML 映射：name / category / column / periods 或 params>
超出模板能力范围时要求 LLM 输出 ``<<<ERROR>>>原因``。

静态安全检查（生成的代码将在 indicators 沙箱中执行，必须白名单把关）：
  - 只允许 import pandas_ta / pandas / numpy / typing / core.factor_base
    （含 as 别名、from 子句）；
  - 禁止 __import__ / open / eval / exec / compile / input / globals / locals；
  - 禁止危险 dunder 属性访问（__class__ / __globals__ / __subclasses__ 等逃逸通道；
    `__init__` 等常规魔术方法不在此列）；
  - ast 解析失败即拒绝。
安全闸：生成结果绝不自动执行/入库，只回填到编辑框由用户确认。
"""

from __future__ import annotations

import ast
import re
from typing import Any, Callable

import yaml

from quant_research_engine.gui.nl_compiler import NOT_CONFIGURED_ERROR, call_llm, nl_config

# ---------------------------------------------------------------------------
# 提示词
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
你是一名 A 股技术指标因子工程师。用户用中文描述一个技术指标需求，
你要为 indicators_tushare 项目生成一个因子类源码 + 配置建议。

【硬性约束（违反任何一条即废品）】
- 只输出一个继承 FactorBase 的因子类；文件顶部 import 固定为：
    import pandas as pd
    import pandas_ta as ta
    from core.factor_base import FactorBase
- __init__ 里调用 super().__init__(db_manager)，并设置
  self.indicator_name（小写指标名，须与 pandas_ta 函数名一致）和 self.category。
- category 只能是：overlap / momentum / volatility / trend / volume /
  statistics / candle / performance 之一。
- 只实现 calculate_logic(self, df, p=None)；不要重写 calculate。
  - p=None 必须可用（此时用 pandas_ta 默认参数）；p 为 int 时是单周期 length，
    p 为 list 时按位置展开为 pandas_ta 的关键字参数。
  - 取价格序列用 self.get_price_series(df)（单序列指标）；HLC 输入用
    df['high'] / df['low'] / df['close']；成交量用 df['volume']。
  - 单输出返回 pd.Series；多输出返回 pd.DataFrame（列名用 pandas_ta 原列名，
    基类会自动做列名归一化与参数后缀拼接，不要在列名里自己拼参数）。
- 只允许 import pandas / pandas_ta / numpy / typing / core.factor_base；
  禁止 import os/sys/subprocess/socket/requests，禁止 open()/eval()/exec()/__import__()。
- 只支持模板型指标：pandas_ta 已有函数、输入为单序列或 OHLCV、单/多输出。
  需要财务数据、分钟线、横截面排名、多股票计算或未来数据的需求，
  不要硬写，输出一行：<<<ERROR>>>该需求超出模板因子范围，请走人工通道（简述原因）

【输出格式（严格遵守，不要任何额外解释）】
<<<CODE>>>
<完整 Python 源码>
<<<META>>>
name: <indicator_name>
category: <类别>
column: <close|typical_price|average_price|median_price>
periods: [<整数周期列表>]
（多参数指标用 params: [[12, 26, 9]] 代替 periods；无参指标用 periods: [null]）

【示例 1：单序列、单周期参数】
用户：SMA 简单均线，周期 5/20
输出：
<<<CODE>>>
import pandas as pd
import pandas_ta as ta
from core.factor_base import FactorBase


class SMAFactor(FactorBase):
    \"\"\"Simple Moving Average (SMA)\"\"\"
    def __init__(self, db_manager):
        super().__init__(db_manager); self.indicator_name = "sma"; self.category = "overlap"
    def calculate_logic(self, df, p=None):
        series = self.get_price_series(df)
        return ta.sma(series, length=p) if p else ta.sma(series)
<<<META>>>
name: sma
category: overlap
column: close
periods: [5, 20]

【示例 2：HLC 多输入】
用户：ATR 真实波幅，周期 14
输出：
<<<CODE>>>
import pandas as pd
import pandas_ta as ta
from core.factor_base import FactorBase


class ATRFactor(FactorBase):
    \"\"\"Average True Range (ATR)\"\"\"
    def __init__(self, db_manager):
        super().__init__(db_manager); self.indicator_name = "atr"; self.category = "volatility"
    def calculate_logic(self, df, p=None):
        return ta.atr(df['high'], df['low'], df['close'], length=p) if p else ta.atr(df['high'], df['low'], df['close'])
<<<META>>>
name: atr
category: volatility
column: close
periods: [14]
"""

_CODE_MARK = "<<<CODE>>>"
_META_MARK = "<<<META>>>"
_ERROR_MARK = "<<<ERROR>>>"

# ---------------------------------------------------------------------------
# 静态安全检查（白名单思路，见模块 docstring）
# ---------------------------------------------------------------------------

ALLOWED_IMPORT_ROOTS = frozenset({"pandas", "pandas_ta", "numpy", "typing"})

# 因子基类的唯一合法项目内 import
_ALLOWED_FROM_IMPORTS = frozenset({"core.factor_base"})

_BANNED_CALLS = frozenset(
    {"__import__", "open", "eval", "exec", "compile", "input", "globals", "locals", "breakpoint"}
)

# 逃逸通道 dunder（常规魔术方法如 __init__ 允许）
_BANNED_DUNDER_ATTRS = frozenset(
    {
        "__class__",
        "__globals__",
        "__subclasses__",
        "__bases__",
        "__mro__",
        "__dict__",
        "__code__",
        "__builtins__",
        "__getattribute__",
        "__loader__",
        "__spec__",
        "__import__",
    }
)


def check_code_safety(code: str) -> list[str]:
    """对生成的因子源码做 AST 白名单检查；返回违规列表（空 = 通过）。"""
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [f"代码无法解析（语法错误）: {exc}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    violations.append(f"禁止的 import {alias.name}（只允许 pandas/pandas_ta/numpy/typing）")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if node.level != 0 or (
                root not in ALLOWED_IMPORT_ROOTS and node.module not in _ALLOWED_FROM_IMPORTS
            ):
                violations.append(
                    f"禁止的 from-import: {node.module}（只允许 pandas/pandas_ta/numpy/typing/core.factor_base）"
                )
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _BANNED_CALLS:
                violations.append(f"禁止调用: {func.id}()")
        elif isinstance(node, ast.Attribute):
            if node.attr in _BANNED_DUNDER_ATTRS:
                violations.append(f"禁止访问 dunder 属性: {node.attr}")
    # 去重保持顺序
    seen: set[str] = set()
    unique: list[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


# ---------------------------------------------------------------------------
# 输出解析
# ---------------------------------------------------------------------------


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def parse_llm_output(raw: str) -> dict[str, Any]:
    """解析两段式 LLM 输出 → {"code", "meta"} 或 {"error"}（raise ValueError）。"""
    text = (raw or "").strip()
    if _ERROR_MARK in text:
        reason = text.split(_ERROR_MARK, 1)[1].strip().splitlines()[0] if text.split(_ERROR_MARK, 1)[1].strip() else ""
        raise ValueError(reason or "该需求超出模板因子范围，请走人工通道")
    if _CODE_MARK in text:
        text = text.split(_CODE_MARK, 1)[1]
    if _META_MARK not in text:
        raise ValueError("LLM 输出缺少 <<<META>>> 配置块，无法解析（可重试或改手写）")
    code_part, meta_part = text.split(_META_MARK, 1)
    code = _strip_code_fence(code_part)
    if not code:
        raise ValueError("LLM 输出的代码块为空")
    try:
        meta = yaml.safe_load(_strip_code_fence(meta_part))
    except yaml.YAMLError as exc:
        raise ValueError(f"META 块 YAML 解析失败: {exc}") from exc
    if not isinstance(meta, dict) or not meta.get("name"):
        raise ValueError("META 块缺少 name 等必需字段")
    return {"code": code, "meta": meta}


def normalize_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """规范化 LLM 建议的 config 条目：name/category/column + periods 或 params。"""
    name = str(meta.get("name") or "").strip().lower()
    category = str(meta.get("category") or "").strip().lower()
    column = str(meta.get("column") or "close").strip().lower()
    result: dict[str, Any] = {"name": name, "category": category, "column": column}
    periods = meta.get("periods")
    params = meta.get("params")
    if params is not None:
        result["params"] = params
    elif periods is not None:
        result["periods"] = periods
    else:
        result["periods"] = [None]
    return result


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def generate_factor_code(
    description: str,
    *,
    http_post: Callable[..., Any] | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """NL → 因子代码草稿 + 建议 config 条目。只生成不执行（安全闸）。

    Returns:
      {"ok": True, "code": str, "meta": dict}
      {"ok": False, "code": "not_configured"|"llm_error"|"out_of_scope"|
       "parse_error"|"unsafe"|"empty", "error": 中文, "source": 可选草稿}
    """
    description = (description or "").strip()
    if not description:
        return {"ok": False, "code": "empty", "error": "请先用自然语言描述要创建的因子"}

    config = nl_config(env)
    if config is None:
        return {"ok": False, "code": "not_configured", "error": NOT_CONFIGURED_ERROR}

    try:
        raw = call_llm(description, config, http_post=http_post, system_prompt=_SYSTEM_PROMPT)
    except Exception as exc:
        return {"ok": False, "code": "llm_error", "error": f"LLM 调用失败：{exc}"}

    try:
        parsed = parse_llm_output(raw)
    except ValueError as exc:
        message = str(exc)
        code = "out_of_scope" if "人工通道" in message else "parse_error"
        return {"ok": False, "code": code, "error": message, "source": raw}

    violations = check_code_safety(parsed["code"])
    if violations:
        return {
            "ok": False,
            "code": "unsafe",
            "error": "生成的代码未通过安全检查：" + "；".join(violations),
            "source": parsed["code"],
        }

    meta = normalize_meta(parsed["meta"])
    if not re.fullmatch(r"[a-z][a-z0-9_]*", meta["name"]):
        return {
            "ok": False,
            "code": "parse_error",
            "error": f"LLM 建议的指标名非法: {meta['name']!r}（应为小写字母开头的 snake_case），请手动修正",
            "source": parsed["code"],
        }
    return {"ok": True, "code": parsed["code"], "meta": meta}
