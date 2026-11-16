"""会员订单状态机；首版仅供模拟渠道，不连接真实支付。"""

from __future__ import annotations

ORDER_TRANSITIONS = {
    "created": {"pending", "expired", "closed"},
    "pending": {"paid", "expired", "closed"},
    "paid": {"fulfilled", "refunding"},
    "fulfilled": {"refunding"},
    "refunding": {"refunded"},
    "expired": set(),
    "closed": set(),
    "refunded": set(),
}


def transition_order(status: str, event: str) -> str:
    """按事件推进订单；非法/重复状态明确报错，由调用方做幂等处理。"""
    target = {
        "submit": "pending", "pay": "paid", "fulfill": "fulfilled",
        "expire": "expired", "close": "closed", "refund": "refunding",
        "refund_complete": "refunded",
    }.get(event)
    if target is None:
        raise ValueError(f"未知订单事件：{event}")
    if target not in ORDER_TRANSITIONS.get(status, set()):
        raise ValueError(f"订单状态 {status} 不允许事件 {event}")
    return target


def simulate_order(events: list[str]) -> str:
    """模拟渠道验收辅助：从 created 开始依序执行事件。"""
    status = "created"
    for event in events:
        status = transition_order(status, event)
    return status
