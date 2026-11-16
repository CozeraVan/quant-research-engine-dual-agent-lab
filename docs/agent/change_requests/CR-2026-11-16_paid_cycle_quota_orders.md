# CR-2026-11-16 · 付费分池扣次与订单状态机

- 新 tier：starter/advanced/diamond，分别3/10/30次、5/8/20字段、全市场全期；users CHECK 同步扩展。
- jobs.quota_pool 记录 large/small；新付费档只有 large 占次数，按 member_since 滚动支付周期，到期日进下一周期。
- `_quota_user_row` 统一执行和个人中心用量；管理台可选新档，首次授予时 member_since 缺省为当前时间。
- orders.py 状态机：created→pending→paid→fulfilled→refunding→refunded，另支持 expired/closed；非法/重复迁移拒绝。
- 233 项权限/会员回归 + 3 订单测试通过；生产 schema/代码 active，无真实支付、无新回测。
- 下一部：订单表/模拟渠道 HTTP 闭环，再接 Native；目前订单状态机不对外提供支付接口。
