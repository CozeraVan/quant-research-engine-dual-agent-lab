# CR-2026-10-05 结果页显式入库 + 交易信号入口（策略库语义纠偏）

状态：已实施并部署（用户原话需求，设计决策已定稿，勿再确认）

## 用户原话需求

当前逻辑问题：用户测试 500 只股票得到不错超额收益后才需要持续跟踪和交易信号；
没超额收益的策略不该进策略库。改为：回测结果页面最后加两个按钮
「保存到我的策略库」「提示交易信号」（范围：本次测试范围 / 指定板块 / 全范围股票）。

## 设计决策（用户定稿）

- 开启交易信号隐含保存策略入库（watch 依赖策略持久化）；已保存则直接建 watch
- 「保存到我的策略库」：未保存时保存，已保存置灰显示已保存
- 游客：结果次日清空，不显示两个按钮（沿用现有游客引导条，低成本方案）
- 板块选择复用新建策略页同款二级菜单（/api/saas/universes）
- scope 三选项 = 现有 scope_type：last_run_universe / sector / all_a

## 数据模型

- `strategies.in_library BOOL NOT NULL DEFAULT false`（懒自愈；存量 backfill true，
  仅列不存在时执行一次——重复 apply 不得把未保存行翻回 true）
- jobs.strategy_id NOT NULL 约束不变：提交回测仍建行（FK + 记录展示），但默认
  in_library=false 不进策略库列表；策略库列表只显示 in_library=true
- 新端点 POST /api/saas/strategies/<id>/save（幂等）；POST watch 隐含置 true

## 结果

实现于 commit（见 git log：QRE-SAAS-RESULT-ACTIONS）；测试与验证见 04/05 同名条目。
