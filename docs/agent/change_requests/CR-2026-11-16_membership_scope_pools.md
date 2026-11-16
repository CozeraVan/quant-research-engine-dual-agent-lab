# CR-2026-11-16 · 会员规模分池与 NL 绕过审计

- 用户批准全量/中小任务分池，SU 不再用于两者付费兑换；随机全局上限2000。
- `quota_pool`：显式全市场/板块、random≥2000、覆盖≥80%进入 large；其余 small。
- `validate_scope_policy` 对所有入口服务端生效；登录账号按 tier_policies 检查 codes/random/universe/max_days；游客原专属逻辑保留。
- NL 文本只是快照，不参与 params 生成；直接伪造 params 也不能绕过。重复股票代码规范化去重后计数。
- 9090 范围卡直接读取执行常量，展示2000/80%/分池。
- 子代理两次因 invalid_iam_token 未启动，主代理完成静态审计与真实临时库测试。
- 212 项相关测试通过、14 skipped；ECS active，无回测。
