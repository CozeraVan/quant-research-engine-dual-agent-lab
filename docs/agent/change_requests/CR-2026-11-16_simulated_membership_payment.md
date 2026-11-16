# CR-2026-11-16 · 会员模拟支付 HTTP 闭环

- 新增 payments.py：商品目录、服务端价格/天数、登录下单、本人订单查询、显式开关模拟支付。
- 新表 membership_orders/payment_events；支付+履约+用户 tier/到期在同一事务，重复支付返回 deduped，不顺延。
- 模拟开关 `SAAS_PAYMENT_SIMULATOR` 默认关；生产只验证商品200和订单表0行，无真实支付。
- 237 项相关测试通过/14 skipped，覆盖金额、跨账号404、开关、幂等和事件数。
- 下一步才接真实 Native 下单/验签回调/查单；模拟接口不能作为真实支付证据。
