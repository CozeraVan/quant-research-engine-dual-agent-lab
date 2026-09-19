# Implementation Brief

## Task ID

QRE-JOB-API（A2：Flask 侧 job API 按 17 号协议改造过渡版）——已完成，见 05_PROGRESS 2026-09-19 条目

## Created By

KIMI_CODE（2026-09-07；依据已落档 CR `docs/agent/change_requests/CR-0004-saas-mvp-launch.md`，
用户当日指令「将 8081 上线作为当前阶段主要任务，按最精简功能上线为基准步步推进」）

## Intended Implementer

KIMI_CODE

## Goal（M1 切片：云端/本地代码双侧改造，不部署）

1. **QRE-SAAS-003 本地 PG 只读账号** ✅（2026-09-07 已完成并验证）：
   角色 `qre_worker_ro`（LOGIN，仅 SELECT），覆盖 public/factors/reference/
   derivatives/cluster/market_risk 六 schema + default privileges；顺手修复
   PG 默认隐患 `REVOKE CREATE ON SCHEMA public FROM PUBLIC`（van 属
   pg_database_owner 不受影响，已实测建表正常）。验证：SELECT stock_daily/
   alpha191/pool_momentum_daily 正常；CREATE/DELETE 均 permission denied。
2. **QRE-SAAS-001 云小库 schema**：`deploy/saas/cloud_schema.sql`——
   users（手机号唯一）/ strategies（YAML+编译状态）/ jobs（任务状态机：
   queued→leased→running→done/failed，含心跳 lease_expires）/
   results（报告 JSON 元数据 + OSS key）。单机 PG/SQLite 均可跑的纯 SQL。
3. **QRE-SAAS-002 任务队列协议**：Worker 出站轮询 REST——
   `POST /api/worker/jobs/lease`（认领，带 lease 超时）→ 本地跑回测 →
   `POST /api/worker/jobs/<id>/result`（回传报告 JSON + 产物 OSS 直传后登记）；
   Worker 与云端之间用共享 token 鉴权；任务可重试（lease 过期自动回队）。
4. **QRE-SAAS-004 8081 四功能裁剪**：仅保留 新增策略（NL+向导）/ 提交回测
   （排队态 UI）/ 结果呈现 / 历史记录；移除回测管理/因子 tab 的管理面
   （8080 保持内网原样，不动）。

## 约束

- 8081 现冻结的页面观感基准不破坏（RSI 基准 run 结果页保持可比）；
- 引擎回测口径零改动；云端不落任何 K线/因子明细；
- 既有测试全绿（基线 1960+4 skipped）；新功能配测试；
- 不 git commit（等用户审批）；不动 8080 生产服务；
- docs/agent 同步：05_PROGRESS 记 SAAS-003 完成项 + 本切片进展。

## 验证路径

- schema：本地临时 PG 库 apply cloud_schema.sql 跑通；
- 队列协议：FastAPI/Flask test_client 模拟 Worker lease→result 全流程 +
  lease 过期重排用例；
- 只读账号：已完成实测（见上）。
