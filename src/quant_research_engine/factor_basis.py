"""QRE-FACTOR-BASIS-CONTRACT：因子复权口径硬契约（单一权威）。

## 为什么有这份契约

因子库存的是**后复权**尺度（`raw × adj_factor`），K 线是**前复权 @ K 线最后交易日**，
两者不同尺。价格型因子（EMA/MACD/BOLL…）必须除以 K 线最后交易日的 `adj_factor`
才能与 K 线并列；该换算只存在于实时生成路径。缺口径标记的历史快照会把 EMA 等按
hfq 尺度与 qfq K 线摆在一起——600330 实测 `ema_5=113.26` vs qfq 收盘 `21.97`
（差 5.16 倍）。**同一类问题已复发四次**（用户原话「每次都是治标不治本」），
根因是「有没有换算过」这件事没有任何地方强制记录。

## 契约三条（缺一即违约）

1. **生成侧**：任何写出 per-symbol 详情的代码路径都必须带 `factor_basis`，
   且值必须在 `KNOWN_BASES` 里。带不上就报错，**不许静默省略**。
2. **读取侧**：`factor_basis` 缺失或不在 `KNOWN_BASES` → 一律不当正确数据下发，
   **并打 WARNING 日志**（job_id / ts_code / 路径 / 原因），让复发可观测。
3. **运维侧**：`deploy/saas/scan-factor-basis.sh` 全量审计 live + 归档产物，
   发现缺标记/未知值即非零退出（可接 timer 或告警）。

## 新增口径怎么办

在 `KNOWN_BASES` 登记新值 + 在生成侧写上它 + 更新 `docs/agent/23_KLINE_IMPLEMENTATION.md`
的口径表。**不要**绕过白名单——读取侧会把未登记的值当「口径未知」拒发。
"""

from __future__ import annotations

# 现行口径：价格型因子已按 K 线前复权锚点（K 线最后交易日的 adj_factor）换算。
FACTOR_BASIS_QFQ_ANCHOR_V1 = "qfq_anchor_v1"

# 已知口径白名单。读取侧只认这里面的值；新口径必须先登记再用。
KNOWN_BASES: frozenset[str] = frozenset({FACTOR_BASIS_QFQ_ANCHOR_V1})


def is_known_basis(value: object) -> bool:
    """值是否是已登记的复权口径。"""
    return isinstance(value, str) and value in KNOWN_BASES


def basis_reason(value: object) -> str | None:
    """返回拒发原因；``None`` 表示口径合法、可以下发。

    读取侧用它做判定：原因非 None 就必须拒发并留痕（见模块 docstring 契约第 2 条）。
    """
    if value is None or value == "":
        return "missing"
    if not isinstance(value, str):
        return f"non-string:{type(value).__name__}"
    if value not in KNOWN_BASES:
        return f"unknown:{value}"
    return None
