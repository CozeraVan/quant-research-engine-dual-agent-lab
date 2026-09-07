"""策略 YAML 严格校验器（QRE-SAAS-005）：公网 NL 入口的前置安全闸。

威胁模型结论（2026-09-07 调查）：
- NL 写策略产物是纯 YAML 声明式配置，无 Python 代码执行；
  但 ``signal.entry/exit`` 表达式会被 ``evaluation.signals.evaluate_expression_signal``
  用自定义 AST 求值器解释——该求值器对 ``ast.Attribute`` 做**无限制 getattr**、
  对 ``ast.Call`` 允许调用任意方法（如 ``close.to_csv(...)``），构成真实注入面。
  本模块在执行前用更严的 AST 白名单把表达式锁死（只许列名/数值/比较/逻辑/
  算术 + 白名单方法链）。
- 因子字段引用（data.factor_fields 的 "factors.table.column"）会被拼进 SQL
  标识符，需逐段标识符校验防注入。

本模块为纯函数，零 DB 零 IO。引擎既有行为不改——本校验器只在
公网入口（worker runner 执行云端任务前）强制调用。
"""

from __future__ import annotations

import ast
from typing import Any

import yaml

MAX_YAML_BYTES = 100_000
MAX_EXPRESSION_CHARS = 2_000

# 顶层节白名单（对齐 strategies/spec.py 读取的节）
_TOP_LEVEL_KEYS = frozenset({
    "experiment", "data", "signal", "evaluation", "holding", "risk", "portfolio", "universe",
})
_SECTION_KEYS: dict[str, frozenset[str]] = {
    "experiment": frozenset({"name", "market_profile", "frequency"}),
    "data": frozenset({"market_fields", "factor_fields"}),
    "signal": frozenset({"entry", "exit"}),
    "evaluation": frozenset({"forward_return_horizons", "quantiles"}),
    "holding": frozenset({"max_holding_days"}),
    "risk": frozenset({"stop_loss_pct", "take_profit_pct", "trailing_stop_pct"}),
    "portfolio": frozenset({"weight_model", "score_column", "volatility_column", "rebalance_interval_days"}),
    "universe": frozenset({"exclude_st", "exclude_suspended", "exclude_risk_warning",
                           "min_listing_days", "min_amount"}),
}

# 行情列名白名单（stock_daily 可暴露给表达式的列）
_MARKET_FIELDS = frozenset({"open", "high", "low", "close", "pre_close", "vol", "amount"})

# 表达式允许的方法调用（pandas 序列向量化方法；属性访问只允许出现在
# 方法调用的 func 链上，且属性名必须在此白名单内、不得下划线开头）
_SAFE_METHODS = frozenset({
    "shift", "rolling", "ewm", "expanding",
    "mean", "std", "var", "min", "max", "sum", "median", "quantile", "rank",
    "pct_change", "diff", "abs", "clip", "fillna", "ffill", "bfill",
    "where", "round", "pow", "log", "log10", "exp", "sqrt", "sign",
    "cumsum", "cummax", "cummin", "cumprod",
})

_ALLOWED_CMP = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
_ALLOWED_BINOP = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow, ast.Mod, ast.BitAnd, ast.BitOr)
_ALLOWED_BOOLOP = (ast.And, ast.Or)
_ALLOWED_UNARY = (ast.USub, ast.UAdd, ast.Not, ast.Invert)


def validate_expression(expression: str, allowed_names: set[str] | None = None) -> list[str]:
    """信号表达式 AST 白名单校验；返回违规列表（空 = 通过）。

    允许：列名 Name（可选限定 allowed_names）、数值/布尔常量、比较（6 种）、
    逻辑 and/or、算术 +-*/**%、位与/或（布尔组合）、一元 -/+/not/~、
    白名单方法链调用（如 close.shift(1)、close.rolling(20).mean()）。
    禁止：字符串等其他常量、下划线开头标识符、非白名单方法、
    裸函数调用、属性读取（非调用链）、下标、lambda、推导式等一切其他节点。
    """
    issues: list[str] = []
    if not isinstance(expression, str) or not expression.strip():
        return ["表达式为空"]
    if len(expression) > MAX_EXPRESSION_CHARS:
        return [f"表达式超长（>{MAX_EXPRESSION_CHARS} 字符）"]
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        return [f"表达式语法错误: {exc}"]

    def visit(node: ast.AST, *, in_call_chain: bool = False) -> None:
        if isinstance(node, ast.Expression):
            visit(node.body)
        elif isinstance(node, ast.BoolOp):
            if not isinstance(node.op, _ALLOWED_BOOLOP):
                issues.append(f"禁止的逻辑运算符: {ast.dump(node.op)}")
            for v in node.values:
                visit(v)
        elif isinstance(node, ast.BinOp):
            if not isinstance(node.op, _ALLOWED_BINOP):
                issues.append(f"禁止的算术运算符: {ast.dump(node.op)}")
            visit(node.left)
            visit(node.right)
        elif isinstance(node, ast.UnaryOp):
            if not isinstance(node.op, _ALLOWED_UNARY):
                issues.append(f"禁止的一元运算符: {ast.dump(node.op)}")
            visit(node.operand)
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                if not isinstance(op, _ALLOWED_CMP):
                    issues.append(f"禁止的比较运算符: {ast.dump(op)}")
            visit(node.left)
            for c in node.comparators:
                visit(c)
        elif isinstance(node, ast.Call):
            # 只允许白名单方法调用（close.shift(1)），禁止裸函数调用
            if not isinstance(node.func, ast.Attribute):
                issues.append("禁止裸函数调用（只允许白名单方法链，如 close.shift(1)）")
                for a in node.args:
                    visit(a)
                return
            if node.func.attr.startswith("_"):
                issues.append(f"禁止访问下划线开头属性: {node.func.attr}")
            elif node.func.attr not in _SAFE_METHODS:
                issues.append(f"禁止的方法调用: {node.func.attr}()（不在白名单）")
            visit(node.func.value, in_call_chain=True)
            for a in node.args:
                visit(a)
            for kw in node.keywords:
                visit(kw.value)
        elif isinstance(node, ast.Attribute):
            # 属性只允许作为方法调用链的中间环节（由 Call 分支递归进入）
            if node.attr.startswith("_"):
                issues.append(f"禁止访问下划线开头属性: {node.attr}")
            elif not in_call_chain:
                issues.append(f"禁止裸属性访问: .{node.attr}（只允许白名单方法调用）")
            elif node.attr not in _SAFE_METHODS:
                issues.append(f"禁止的方法链属性: .{node.attr}")
            visit(node.value, in_call_chain=in_call_chain)
        elif isinstance(node, ast.Name):
            if node.id.startswith("_"):
                issues.append(f"禁止下划线开头标识符: {node.id}")
            elif allowed_names is not None and node.id not in allowed_names:
                issues.append(f"未知列名: {node.id}（策略未声明该字段）")
        elif isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float, bool)):
                issues.append(f"禁止的常量类型: {type(node.value).__name__}（只允许数字/布尔）")
        else:
            issues.append(f"禁止的语法节点: {type(node).__name__}")

    visit(tree)
    # 去重保持顺序
    seen: set[str] = set()
    unique: list[str] = []
    for v in issues:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def _is_ident(value: Any) -> bool:
    return (
        isinstance(value, str)
        and value.isidentifier()
        and not value.startswith("_")
    )


def validate_strategy_yaml(yaml_text: str) -> dict[str, Any]:
    """策略 YAML 严格校验 → {"ok": True, "names": set} 或 {"ok": False, "issues": [...]}。

    在 ``validate_yaml``（engine.py 的 StrategySpec 结构校验）之上叠加：
    节/键白名单、类型检查、因子引用逐段标识符校验、信号表达式 AST 白名单。
    """
    issues: list[str] = []
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return {"ok": False, "issues": ["YAML 为空"]}
    if len(yaml_text.encode("utf-8")) > MAX_YAML_BYTES:
        return {"ok": False, "issues": [f"YAML 超长（>{MAX_YAML_BYTES} 字节）"]}
    try:
        raw = yaml.safe_load(yaml_text)  # safe_load 本身拒绝 python 对象标签
    except yaml.YAMLError as exc:
        return {"ok": False, "issues": [f"YAML 解析失败: {exc}"]}
    if not isinstance(raw, dict):
        return {"ok": False, "issues": ["YAML 顶层必须是映射"]}

    for key in raw:
        if not isinstance(key, str) or key.startswith("_"):
            issues.append(f"非法顶层键: {key!r}")
        elif key not in _TOP_LEVEL_KEYS:
            issues.append(f"未知顶层节: {key}（只允许 {'/'.join(sorted(_TOP_LEVEL_KEYS))}）")
    for required in ("experiment", "data", "signal"):
        if required not in raw:
            issues.append(f"缺少必需节: {required}")

    names: set[str] = set()
    for section, body in raw.items():
        if section not in _SECTION_KEYS or not isinstance(body, dict):
            if not isinstance(body, dict) and section in _TOP_LEVEL_KEYS:
                issues.append(f"{section} 节必须是映射")
            continue
        for key in body:
            if not isinstance(key, str) or key.startswith("_") or key not in _SECTION_KEYS[section]:
                issues.append(f"{section} 节未知键: {key!r}")

    # experiment.name
    experiment = raw.get("experiment") or {}
    if isinstance(experiment, dict):
        for key in ("name", "market_profile", "frequency"):
            if key in experiment and not isinstance(experiment[key], str):
                issues.append(f"experiment.{key} 必须是字符串")

    # data.market_fields / factor_fields
    data = raw.get("data") or {}
    if isinstance(data, dict):
        market_fields = data.get("market_fields", [])
        if market_fields is not None:
            if not isinstance(market_fields, list) or not all(
                isinstance(f, str) and f in _MARKET_FIELDS for f in market_fields
            ):
                issues.append(f"data.market_fields 只允许已知行情列: {'/'.join(sorted(_MARKET_FIELDS))}")
            else:
                names.update(market_fields)
        factor_fields = data.get("factor_fields", {}) or {}
        if not isinstance(factor_fields, dict):
            issues.append("data.factor_fields 必须是映射（逻辑名 -> factors.table.column）")
        else:
            for logical, target in factor_fields.items():
                if not _is_ident(logical):
                    issues.append(f"因子逻辑名非法: {logical!r}（须为标识符且不下划线开头）")
                    continue
                parts = str(target).split(".")
                # 形如 factors.stock_daily_rsi.rsi_14 或 stock_daily.close
                if len(parts) < 2 or not all(_is_ident(p) for p in parts):
                    issues.append(f"因子引用非法: {target!r}（须为 <schema.>table.column 全标识符）")
                elif parts[0] not in ("factors", "public", "reference", "cluster"):
                    issues.append(f"因子引用 schema 非法: {parts[0]}（只允许 factors/public/reference/cluster）")
                else:
                    names.add(logical)

    # signal.entry / exit → AST 白名单
    signal = raw.get("signal") or {}
    if isinstance(signal, dict):
        entry = signal.get("entry")
        if not isinstance(entry, str) or not entry.strip():
            issues.append("signal.entry 缺失或非字符串")
        else:
            issues.extend(f"signal.entry: {v}" for v in validate_expression(entry, names))
        exit_ = signal.get("exit")
        if exit_ is not None:
            if not isinstance(exit_, str):
                issues.append("signal.exit 必须是字符串")
            else:
                issues.extend(f"signal.exit: {v}" for v in validate_expression(exit_, names))

    # evaluation / holding / risk / universe 类型检查
    evaluation = raw.get("evaluation") or {}
    if isinstance(evaluation, dict):
        horizons = evaluation.get("forward_return_horizons")
        if horizons is not None and (
            not isinstance(horizons, list)
            or not all(isinstance(h, int) and not isinstance(h, bool) and 1 <= h <= 250 for h in horizons)
        ):
            issues.append("evaluation.forward_return_horizons 必须是 1..250 的整数列表")
        quantiles = evaluation.get("quantiles")
        if quantiles is not None and (
            not isinstance(quantiles, int) or isinstance(quantiles, bool) or not 2 <= quantiles <= 100
        ):
            issues.append("evaluation.quantiles 必须是 2..100 的整数")
    holding = raw.get("holding") or {}
    if isinstance(holding, dict):
        mhd = holding.get("max_holding_days")
        if mhd is not None and (
            not isinstance(mhd, int) or isinstance(mhd, bool) or not 1 <= mhd <= 1000
        ):
            issues.append("holding.max_holding_days 必须是 1..1000 的整数")
    risk = raw.get("risk") or {}
    if isinstance(risk, dict):
        for key in ("stop_loss_pct", "take_profit_pct", "trailing_stop_pct"):
            val = risk.get(key)
            if val is not None and (
                isinstance(val, bool) or not isinstance(val, (int, float)) or not 0 < val < 1
            ):
                issues.append(f"risk.{key} 必须是 (0, 1) 的小数")
    universe = raw.get("universe") or {}
    if isinstance(universe, dict):
        for key in ("exclude_st", "exclude_suspended", "exclude_risk_warning"):
            if universe.get(key) is not None and not isinstance(universe.get(key), bool):
                issues.append(f"universe.{key} 必须是布尔")
        mld = universe.get("min_listing_days")
        if mld is not None and (not isinstance(mld, int) or isinstance(mld, bool) or mld < 0):
            issues.append("universe.min_listing_days 必须是非负整数")
        min_amount = universe.get("min_amount")
        if min_amount is not None and (
            isinstance(min_amount, bool) or not isinstance(min_amount, (int, float)) or min_amount < 0
        ):
            issues.append("universe.min_amount 必须是非负数值")

    return {"ok": not issues, "issues": issues, "names": sorted(names)}
