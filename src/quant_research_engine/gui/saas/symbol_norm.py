"""股票代码规范化与显示脱敏（QRE-SAAS-SYMBOL-UX）。

- 输入规范化：用户可只输 6 位数字（如 000001），按号段自动补交易所后缀
  （60/68→SH，00/30→SZ，4/8/920→BJ）；已带后缀的输入大小写归一；
  非法代码抛 ValueError（中文友好报错，路由层转 400）。
- 显示脱敏：公网页面不显示 .SZ/.SH/.BJ 后缀（不暴露数据源代码体系），
  内部存储/API 载荷保持带后缀原样，只在前端渲染层剥离。
"""

from __future__ import annotations

import re

SUFFIXES = ("SH", "SZ", "BJ")
_FULL_RE = re.compile(r"^(\d{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_DIGITS_RE = re.compile(r"^\d{6}$")
_SPLIT_RE = re.compile(r"[,，、;；\s]+")


def infer_exchange(digits: str) -> str:
    """6 位数字代码 → 交易所后缀。无法识别抛 ValueError（友好报错）。"""
    if not _DIGITS_RE.match(digits):
        raise ValueError(f"股票代码「{digits}」格式不正确：应为 6 位数字（如 000001）或带后缀（如 000001.SZ）")
    if digits.startswith(("60", "68")):
        return "SH"
    if digits.startswith(("00", "30")):
        return "SZ"
    if digits[0] in ("4", "8") or digits.startswith("920"):
        return "BJ"
    raise ValueError(
        f"无法识别股票代码「{digits}」所属的交易所（60/68 开头为沪市，00/30 为深市，4/8/920 为北交所）"
    )


def normalize_ts_code(raw: object) -> str:
    """单个代码规范化 → 带后缀大写形式。非法输入抛 ValueError。"""
    s = str(raw or "").strip().upper()
    if not s:
        raise ValueError("股票代码为空")
    m = _FULL_RE.match(s)
    if m:
        return f"{m.group(1)}.{m.group(2).upper()}"
    if _DIGITS_RE.match(s):
        return f"{s}.{infer_exchange(s)}"
    raise ValueError(f"股票代码「{s}」格式不正确：应为 6 位数字（如 000001）或带后缀（如 000001.SZ）")


def normalize_ts_codes(codes: object) -> list[str]:
    """批量规范化（list 或逗号/空白分隔字符串），去重保序。空列表原样返回。"""
    if codes is None:
        return []
    if isinstance(codes, str):
        items = [c for c in _SPLIT_RE.split(codes) if c]
    elif isinstance(codes, (list, tuple)):
        items = [str(c) for c in codes if str(c).strip()]
    else:
        raise ValueError("股票代码须为数组或逗号分隔字符串")
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        code = normalize_ts_code(item)
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def strip_ts_suffix(code: object) -> str:
    """显示层脱敏：000001.SZ → 000001（无后缀输入原样返回）。"""
    s = str(code or "").strip()
    m = _FULL_RE.match(s)
    return m.group(1) if m else s


def resolve_ts_code(raw: object, known_codes: list[str] | None = None) -> str:
    """把用户/URL 输入解析为内部带后缀代码：已带后缀直接归一；纯数字先按
    已知代码表（本任务实际交易的个股）精确匹配，匹配不到再按号段推断。"""
    s = str(raw or "").strip().upper()
    if _FULL_RE.match(s):
        return normalize_ts_code(s)
    if _DIGITS_RE.match(s):
        for known in known_codes or []:
            if strip_ts_suffix(known) == s:
                return str(known).upper()
        return f"{s}.{infer_exchange(s)}"
    raise ValueError(f"股票代码「{s}」格式不正确：应为 6 位数字（如 000001）或带后缀（如 000001.SZ）")
