# Implementation Brief

## Task ID

QRE-SAAS-R2 多租户弹性调度（并发闸门 + 内存护栏 + 任务分级）

## Created By

KIMI_CODE（2026-10-03；用户指令「回到服务器压力测试，基于当前 PC 配置限制并发防止挤爆服务器」，
AskUserQuestion 已对齐：三层全套方案；worker 内存预算 25.6G / 并发 4）

## Intended Implementer

KIMI_CODE

## 背景与依据（N3 实测基线，docs/agent/14_LAUNCH_ROADMAP.md §10）

- 回测机 14600KF（14C20T）+ 32G；单「全A×2年」任务峰值 5.79G / 110.8s；
  2 并发各 118.5s（劣化 7%）→ **内存是硬约束，CPU 余量充足**。
- 预算：32G × 80% = 25.6G；槽位设计：2 轻量槽（1.5G/个）+ 3 重量槽（6G/个）= 21G ≤ 25.6G。
- 现状：worker daemon 单并发轮询 claim（daemon.py），jobs 表天然排队，ECS 零压力——
  需要把 worker 端从「单并发」升级为「按预算领任务」，并防止轻任务被重任务堵死。

## Goal（四个切片）

### 切片 1：云端任务分级 + 分类认领（saas/app.py + cloud_schema.sql）

- `jobs.weight_class TEXT NOT NULL DEFAULT 'heavy'`（懒自愈 ALTER，进程级标记防重复，同 tier_policies 模式）。
- 分类器 `classify_job_weight(kind, params)`：
  - kind=smoke → light；
  - params.universe（板块/全市场）→ heavy；
  - 显式 codes ≤ 5 → light，否则 heavy。
  （v1 不按区间天数细分：内存 ≈ 标的数 × 天数，单股全历史仍轻量。）
- `POST /api/worker/jobs/claim` 接受 `classes` 参数：`"light"` 只领轻任务，`"any"`（默认，向后兼容）任意。
- job 详情对 queued 任务返回 `queue_position`（排在前面的同优先级队列长度），供前端显示「排队中，前面还有 N 个」。

### 切片 2：worker 槽位调度 + 内存闸门（worker/daemon.py + 新 worker/slots.py）

- 槽位：轻量槽线程 × `QRE_WORKER_LIGHT_SLOTS`（默认 2），重量槽线程 × `QRE_WORKER_HEAVY_SLOTS`（默认 3）。
- 内存闸门：领取前读 `/proc/meminfo` MemAvailable；轻量槽要求 ≥ `QRE_WORKER_LIGHT_MIN_AVAIL_MB`（默认 2000），
  重量槽 ≥ `QRE_WORKER_HEAVY_MIN_AVAIL_MB`（默认 6500）；不足则 sleep 重试（本机有其他负载时自动降速）。
- 轻量槽 claim(classes="light")；重量槽 claim(classes="any")。
- 每个 job 在 **fork 子进程**中执行（runner.execute_job 原样在子进程跑）：
  GIL 隔离（N3 并发口径即多进程）、内存隔离、可强杀；父进程维持心跳/取消/回传语义不变。
  子进程异常退出（含 OOM 被杀）→ 回传 failed（error_class=engine_error）。
- 保留 `WorkerDaemon.run_once` 单任务路径（既有测试不破）；`--slots` 模式为新主路径。
- 优雅退出语义不变：运行中任务等完成再退。

### 切片 3：本机 worker 的 systemd 托管（deploy/saas/qre-worker.service）

- WSL Ubuntu 用 systemd unit 托管 worker：`MemoryMax=26G`（cgroup 硬兜底，超了先杀 worker 不拖垮 PG/系统）、
  `Restart=always`、环境文件 `/home/van/.config/qre/worker.env`。
- 文档写明 enable/start 命令（16_ECS_DEPLOYMENT.md 或 14_LAUNCH_ROADMAP.md 运维速查节）。

### 切片 4：管理台队列可视化 + 文档

- console overview 增加轻/重队列深度（queued by weight_class）与槽位配置回显。
- 更新 05_PROGRESS.md、14_LAUNCH_ROADMAP.md §10（容量基线→调度参数落档）、11_AGENT_STATE.md。

## 约束

- 不改引擎回测口径；不改 17 协议既有字段语义（classes 为可选增量，旧 worker 不传 = any，行为不变）。
- 既有测试全绿（基线 saas 185 passed + 4 skipped）；新功能配测试：
  分类器单测、claim 分类过滤、queue_position、内存闸门纯函数、槽位线程（注入 fake client/runner）、
  子进程执行成功/异常/OOM 退出三态。
- UI 基准不动（本次无前台页面改动；console 仅加指标行）。

## 验证路径

1. `.venv/bin/pytest tests/ -q -k saas` 全绿 + worker/security 相关测试文件。
2. 本地 staging 闭环：提 1 轻 1 重任务 → 两槽并行领取；`stress -m` 占内存后重量槽自动停领。
3. ECS 部署后公网提交任务确认 weight_class 落库、queue_position 返回。
