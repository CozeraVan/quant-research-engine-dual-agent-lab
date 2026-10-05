# Implementation Brief

## Task ID

QRE-SAAS-RESULT-ACTIONS（结果页「保存到策略库 / 提示交易信号」+ 策略库入库语义改为显式保存）

## Created By

KIMI_CODE（2026-10-05；用户原话需求已定稿，勿再确认）

## 背景与关键现状

- 现状：api_create_job 提交时按 (user_id,name) upsert strategies 且策略库列表全量显示
  ——所有测试过的策略都「入库」。用户要求：没超额收益的策略不该进库，入库改为结果页
  显式按钮触发。
- 约束：jobs.strategy_id NOT NULL REFERENCES strategies(id)——提交时仍必须建行
  （FK + 回测记录展示），不能跳过建行。
- 既有可复用：watch CRUD（POST/DELETE /api/saas/strategies/<id>/watch，默认
  last_run_universe 快照）、signal_scan、/saas/signals、new.html 板块二级菜单数据源
  /api/saas/universes、strategies 懒自愈列模式。

## Goal（设计决策按用户定稿）

1. strategies 加 `in_library BOOL NOT NULL DEFAULT false`（懒自愈扩展现有
   _ensure_strategy_asset_columns；存量行 backfill true——它们本就在库里）；
   提交 upsert 不动该旗标（默认 false）；显式保存（POST /api/saas/strategies、
   结果页保存按钮、创建 watch 隐含保存）才置 true。
2. 策略库列表 API 只返回 in_library=true；详情/回填 API 不受限（job 关联行可读）。
3. 新端点 POST /api/saas/strategies/<id>/save（幂等，返回 already 状态）。
4. job.html 结果页末尾操作卡：「保存到我的策略库」（已保存置灰）+
   「提示交易信号」（三选一：本次测试范围 last_run_universe / 指定板块 sector 二级菜单
   / 全范围 all_a）→ POST watch；游客不显示（现有游客引导条已存在，低成本方案）。
5. 验证：单测 + staging Playwright 截图。

## Validation

- `.venv/bin/pytest tests/ -q -k saas` 全绿（基线 235）
- 新增：提交不入库/保存后入库/幂等/watch 隐含入库/列表过滤/详情不受限；
  job 页按钮三态（游客隐藏/未保存可点/已保存置灰）模板断言
- Playwright staging：桌面+375 截图（未保存态→保存→已保存→信号面板三 scope）
