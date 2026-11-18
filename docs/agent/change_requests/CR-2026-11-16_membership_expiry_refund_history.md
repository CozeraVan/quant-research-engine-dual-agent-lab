# CR-2026-11-16 · 到期降级、权益历史与模拟退款

- `effective_tier`：仅 starter/advanced/diamond 到期回落 member；历史 paid 兼容。提交、个人中心、Agent owner policy、watch 均使用到期口径。
- `membership_entitlements` 在履约事务内记录订单/tier/生效/到期；订单唯一防重复。
- 模拟退款仅 fulfilled 可退：订单 refunded、权益 revoked、用户回落 member；重复退款 deduped，不重复事件。
- 9090 新增订单/履约/退款/有效权益真实计数。
- 247 项相关测试通过/14 skipped；生产 entitlements=0，无真实支付/回测。
- 订单超时/关闭/履约重试/续费顺延已于同日完成并部署，120项相关测试通过/14 skipped；下一项证书轮换与对账。
