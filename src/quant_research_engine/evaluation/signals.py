from __future__ import annotations

import ast
import operator
from typing import Callable

import pandas as pd


_COMPARE_OPS: dict[type[ast.cmpop], Callable[[object, object], object]] = {
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
}

_BIN_OPS: dict[type[ast.operator], Callable[[object, object], object]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}


def evaluate_expression_signal(frame: pd.DataFrame, expression: str) -> pd.Series:
    tree = ast.parse(expression, mode="eval")
    result = _eval_node(tree.body, frame)
    if not isinstance(result, pd.Series):
        raise ValueError("Signal expression must evaluate to a boolean series")
    return result.fillna(False).astype(bool)


def referenced_fields(expression: str | None) -> set[str]:
    """返回信号表达式引用的全部列名（ast.Name 节点）。

    供装配/准备层判断哪些列是信号输入、必须保留（如 vol/amount/metadata 列被
    信号引用时不能裁剪）。解析失败时返回空集（表达式合法性由求值阶段把关）。"""
    if not expression:
        return set()
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        return set()
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}


def _eval_node(node: ast.AST, frame: pd.DataFrame) -> object:
    if isinstance(node, ast.BoolOp):
        values = [_as_bool_series(_eval_node(value, frame)) for value in node.values]
        if isinstance(node.op, ast.And):
            result = values[0]
            for value in values[1:]:
                result = result & value
            return result
        if isinstance(node.op, ast.Or):
            result = values[0]
            for value in values[1:]:
                result = result | value
            return result
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    if isinstance(node, ast.BinOp):
        left = _eval_node(node.left, frame)
        right = _eval_node(node.right, frame)
        if isinstance(node.op, ast.BitAnd):
            return _as_bool_series(left) & _as_bool_series(right)
        if isinstance(node.op, ast.BitOr):
            return _as_bool_series(left) | _as_bool_series(right)
        op = _BIN_OPS.get(type(node.op))
        if op is not None:
            return op(left, right)
        raise ValueError(f"Unsupported expression: {ast.dump(node)}")

    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, frame)
        comparisons = []
        current_left = left
        for op_node, comparator in zip(node.ops, node.comparators, strict=True):
            op = _COMPARE_OPS.get(type(op_node))
            if op is None:
                raise ValueError(f"Unsupported expression: {ast.dump(node)}")
            right = _eval_node(comparator, frame)
            comparisons.append(_as_bool_series(op(current_left, right)))
            current_left = right
        result = comparisons[0]
        for comparison in comparisons[1:]:
            result = result & comparison
        return result

    if isinstance(node, ast.Call):
        # Only support method calls (e.g. close.shift(1)), not bare function calls
        if not isinstance(node.func, ast.Attribute):
            raise ValueError(f"Unsupported expression: {ast.dump(node)}")
        func = _eval_node(node.func, frame)
        args = [_eval_node(arg, frame) for arg in node.args]
        return func(*args)

    if isinstance(node, ast.Attribute):
        value = _eval_node(node.value, frame)
        return getattr(value, node.attr)

    if isinstance(node, ast.Name):
        if node.id not in frame.columns:
            raise ValueError(f"Unknown signal field: {node.id}")
        return frame[node.id]

    if isinstance(node, ast.Constant) and isinstance(node.value, int | float | bool):
        return node.value

    if isinstance(node, ast.UnaryOp):
        if isinstance(node.op, ast.USub):
            return -_eval_node(node.operand, frame)
        if isinstance(node.op, ast.UAdd):
            return _eval_node(node.operand, frame)
        if isinstance(node.op, ast.Not):
            # 布尔取反：支持向导「排除型」条件（如 A and B and not E）
            return ~_as_bool_series(_eval_node(node.operand, frame))

    raise ValueError(f"Unsupported expression: {ast.dump(node)}")


def _as_bool_series(value: object) -> pd.Series:
    if isinstance(value, pd.Series):
        return value.fillna(False).astype(bool)
    if isinstance(value, bool):
        return pd.Series([value])
    raise ValueError("Signal expression must evaluate to a boolean series")
