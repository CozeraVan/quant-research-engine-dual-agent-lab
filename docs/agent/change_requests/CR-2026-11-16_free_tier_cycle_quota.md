# CR-2026-11-16 · 免费层周期额度落地

- 游客：每日1次、1只、1826天、3因子；登录用户：自然月10次、10只、3653天、3因子；现有 paid 不变。
- `USED_QUOTA_SQL`：member 从自然月起算，其余按日；`daily_full_limit` 字段保留为历史名称，member 行表达周期次数。
- 全入口服务端范围校验；smoke 不占周期次数且不被 full 的区间闸误伤。
- 个人中心改“本周期”，9090 策略表/用户计数同步。
- schema 只迁移已知旧默认行，保留自定义；生产迁移前 guest/member 各1行匹配，备份 `/tmp/tier-policies-pre-20261116.csv`。
- 232 项相关测试通过、14 skipped；ECS active，无新回测。
