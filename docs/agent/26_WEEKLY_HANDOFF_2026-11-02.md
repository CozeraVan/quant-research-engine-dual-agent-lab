# 26_WEEKLY_HANDOFF_2026-11-02.md — 主 Agent 交接文档（Kimi → 下一任主 Agent）

> 本文档是 2026-11-02 的主 Agent 交接权威记录。明天将切换主 Agent。
> **交接期间任务记录规则（用户 2026-11-02 明确要求）**：
> 从此刻起，凡是新布置的任务，**无论处于“准备进行”还是“已完成”，都必须记录到本文件**。
> 新主 Agent 每次推进任务前，先读本文件 §1 当前状态与 §7 任务记录表，然后在 §7 追加一行；
> 完成后更新同一行状态与验证证据。不要让任务只存在于对话里。

---

## 1. 当前状态（2026-11-02）

- 当前分支：`master`
- 最新提交：`f22326c fix(factors): 参数变体列去重并排除非数字参数列`
- 上一次全量测试：`uv run pytest -q -p no:randomly` → **3299 passed, 34 skipped**
- 文档检查：`bash scripts/check-progress-docs.sh` → 通过
- 主 Agent：Kimi Code（单 Agent 模式）；用户为最终验收人
- 当前无进行中的代码任务；最近一批 P0/P1/P2 工作已 commit/push，但存在**未部署/未重启**项，见 §5。

### 1.1 本交接覆盖的已完成工作（按提交时间）

| 提交 | 内容 | 状态 |
|---|---|---|
| `8f7c50a` | 删除被北交所三板残留污染的全期任务 58/66/74/78 | 已发布 |
| `e6785e9` | P0-4 宇宙侧设闸排除 `920%.BJ` 2021-11-15 前历史 | 已提交，worker 已重启 |
| `ade849d` | P0-5 阶段一：经典策略可复现定义 + 小样本验证 | 已提交 |
| `d7d2640` | P0-5：showcase 滚动器改由 `run_id` 解析基线，移除硬编码 `JOB_RUN_MAP` | 已提交 |
| `f247a32` | 同步经典策略滚动器解耦提交状态 | 已提交 |
| `7360444` | P0-6 统计口径全局生效复核 / P0-7 隐私隔离回归 / P0-8 结果端点 IDOR 普查 + P1-9 文案精简首段 | 已提交 |
| `461ba97` | P1-9 第二段动态内容灰字壳清理 | 已提交 |
| `8074aae` | P1-9 第三段反馈/因子申请/说明页灰字清理 | 已提交 |
| `afde319` | P1-9 第四段登录页与空态灰字清理 | 已提交 |
| `54c5620` | P1-10：全零波动率不得判成 high，regime 降级 error 节 | 已提交 |
| `030312e` | P1-10 threshold 绝对轴验证 + P2-15 后端可选波动率序列 | 已提交 |
| `ef12aa0` | P2-15 前端时序曲线 + P2-14 参数网格产物侧首版 | 已提交 |
| `f22326c` | P2-14 修复参数变体列重复/排除 `macd_cn_*`，补实测与浏览器验收 | 已提交 |

---

## 2. 当前 Todolist 快照

### 2.1 已完成
- P0-1 复权硬契约
- P0-2 年化爆表确认 + 全库极值扫描
- P0-3 删除被污染任务 58/66/74/78
- P0-4 股票池规则落地（宇宙排除 `920%.BJ` 2021-11-15 前历史）
- P0-6 统计口径全局生效复核
- P0-7 回测详情隐私隔离回归
- P0-8 结果端点 IDOR 普查 + 路由合同
- P1-9 文案精简化收尾 + UI 字号基线同步
- P1-10 FRM 波动率 threshold 绝对轴验证 + 分档分组核查
- P2-15 波动率时序曲线（后端可选序列 + 前端曲线 + 体积实测）
- P2-14 参数网格唤醒（产物侧实现 + 小样本/浏览器验收）

### 2.2 待推进
- P0-5 经典策略页重新填充：策略定义/小样本/滚动器解耦已完成；**全量全期重跑待用户手动布置**。
- P2-14：实现与验收完成；**待 worker 重启生效、全量预算批准**。
- P2-15：实现与体积实测完成；**待用户决定是否默认开启 `include_volatility_series`**。
- P1-11《我不是股神》重启：前置复权契约已 OK，待明确重启范围。
- P1-12 上云与数据迁移方案：用户暂缓。
- P2-16 回测产物 → 短视频重点提取：等视频产出后评估。
- D-21 `familyOf` 旧名分支退场：条件为连续 4 次周扫为 0，预计 2026-11-02/09/16/23 后。

---

## 3. 最近详细成果（新主 Agent 必读）

### 3.1 P2-15 波动率时序曲线
- 后端：`risk/report.py` 新增可选 `volatility.series`，默认关；`include_volatility_series` 开启后按 `volatility_series_max_points`（默认 500）抽稀 EWMA/GARCH 年化序列，末值必含。
- 前端：`gui/static/vol-regime.js` 新增 `seriesModel()` / `seriesChartOption()`；`job.html` / `lab_result.html` 有序列时画 EWMA/GARCH 年化波动曲线 + 低/高阈值 markLine，无序列降级为阈值标尺。
- 体积实测：4000 收益点、500 抽稀，`risk_report.json` 9,244 → 19,405 bytes，ratio 2.10。
- 测试：`tests/test_vol_regime.py` 覆盖 seriesModel/seriesChartOption；`tests/test_saas_night_mode.py` 图表计数同步更新。

### 3.2 P2-14 参数网格产物侧
- 语义 CR：`docs/agent/change_requests/CR-2026-11-01_param_grid_wake_semantics.md`
  - 先截断个股，后插变体；超预算先砍变体再砍个股；manifest 计数。
- 实现：
  - `gui/lab_result.py`：`_param_family_params()` / `_select_param_variant_columns()`；`_fetch_factor_panels()` / `build_lab_symbol_detail()` 支持 `include_param_variants`，默认 False；变体列按 `(table,column)` 去重，排除 `macd_cn_*` 等非数字参数列。
  - `worker/runner.py`：`SYMBOL_DETAIL_PARAM_VARIANT_TOP_N=20`，只对截断序头部注入变体；manifest 增加 `param_variants_included` / `param_variants_truncated` / `param_variant_top_n`。
- 实测：
  - 小样本 3 只实际交易股：294,684 → 509,809 bytes，ratio 1.73，约 +71.7KB/股。
  - 真实浏览器参数切换：`macd` 4 组，切到 `6_13_5` 后因子 12→3，零 pageerror。
- 测试：`tests/test_param_variants.py` 4 例；`tests/test_saas_symbol_ux.py` 2 例。

### 3.3 P1-10 / P0-6 / P0-7 / P0-8 摘要
- P1-10：全零波动率不再误判 high；`thresholds_annual` 绝对轴真实浏览器验证通过。
- P0-6：两个 worker 结果回传路径均注入 `result_contract`；batch 总收益口径 `Σfinal/Σinitial−1`；生产仅 job 82 带新合同，旧结果未验证。
- P0-7：生产匿名抽查 job76/job82 均 401；`share_links=0`。
- P0-8：12 条 `job_id` GET 路由清点并冻结；结果 GET 走 `_require_completed_result`。

---

## 4. 已验证命令（新主 Agent 可直接复跑）

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
git log --oneline -20
git status --short

uv run pytest -q -p no:randomly
bash scripts/check-progress-docs.sh
bash scripts/git-finalize-check.sh

# P2-14 小样本实测（需要本地 PG 大库环境变量，已在历史命令中 source /etc/qre-saas-worker.env）
# P2-15 序列/体积实测可用 .venv/bin/python 直接 build_risk_report 复现
```

---

## 5. 未完成 / 必须注意的事项（高优先级）

1. **P2-14 worker 未重启**  
   `worker/runner.py` 已改并提交，但本地 `qre-saas-worker.service` 自 P0-4 后未重启。新代码不会生效。  
   重启命令：
   ```bash
   sudo -n systemctl restart qre-saas-worker.service
   systemctl status qre-saas-worker.service --no-pager | head -12
   ```
   重启后新的非 smoke 回测会默认对 TOP-N 保留股注入参数变体；因 15MiB 预算已紧，超额会先砍变体。

2. **ECS SaaS 部署待确认**  
   本轮有多個 SaaS 前端/后端文件已提交但未必部署到 ECS：`job.html`、`lab_result.html`、`vol-regime.js`、`lab_result.py`、`risk/report.py`、`risk/volatility.py` 等。  
   按 R-DEPLOY-001，代码/UI 改动后应备份并部署 ECS；本次交接时**未部署**。新主 Agent 需按用户指令决定是否部署。

3. **`deploy/saas/public-beta-audit/seed.json` 未跟踪**  
   该文件与本轮任务无关，尚未提交。不要随意纳入提交。

4. **P2-15 生产默认仍关**  
   `include_volatility_series` 默认 False。开启前需用户确认；体积增量小（ratio 2.10）但会增加 GARCH 拟合一次。

5. **P0-5 全量重跑未做**  
   经典策略页仍空；全量全期重跑需用户手动布置，且必须先小样本验证效率与正确性。

---

## 6. 长期纪律提醒（不要违反）

- `docs/agent/` 是唯一权威长期记忆；对话不是真相来源。
- 任何 AI 代码/UI 改动：先部署 ECS 再提交；未通过验收立即回滚。
- 新 UI 不得新增灰色小字备注；解释统一 `tip-trigger + data-tip + LabUI.helpTips`。
- 权限/配额改动必须同步 9090 管理台。
- 生产表 UPDATE/DELETE 前必须跑同 `WHERE` 的 `COUNT(*)` 对账；数据修复先影子表。
- 静默 catch 必须带理由注释；条件键缺就不写键；模块级 const 不得前向引用。
- 源数据只读：`stock_daily` 一行未改，也不许改。

---

## 7. 任务记录表（交接期间强制维护）

> 新主 Agent 每次接到新任务，先在这里加一行；状态变化及时更新。
> 状态建议：`planned` / `in_progress` / `blocked` / `done` / `rejected`。

| 日期 | 任务 | 状态 | 负责 Agent | 验证证据 / 备注 |
|---|---|---|---|---|
| 2026-11-02 | 写入主 Agent 交接 MD 并同步 AGENTS/状态文档 | in_progress | Kimi | 本文件创建；`check-progress-docs.sh` 待跑 |
| 2026-11-02 | P2-14 worker 重启使参数变体生效 | planned | 待定 | 需用户确认；重启命令见 §5.1 |
| 2026-11-02 | ECS SaaS 部署本轮已提交前端/后端改动 | planned | 待定 | 需用户确认；涉及 §5.2 文件 |
| 2026-11-02 | P0-5 全量重跑 | planned | 待定 | 用户手动布置；先小样本 |
| 2026-11-02 | P2-15 生产默认开启决策 | done | Kimi | 用户批准默认开启；`gui/risk_report.py` 已传入 `include_volatility_series=True` |
| 2026-11-02 | P1-12 数据库上云与云端 worker/DB 传输完全准备（不实际迁移） | in_progress | Kimi | 已建 `28_CLOUD_MIGRATION_RUNBOOK_2026-11-02.md` + `deploy/cloud/` 脚本；dry-run 通过；未真迁移 |
| 2026-11-02 | 全期全量压力测试（3项，03:00 后顺序执行） | in_progress | 测试子代理 agent-208 | 目标记录 `docs/agent/27_STRESS_TEST_2026-11-02.md`；未完成 |
| 2026-11-02 | NL 穿越语义丢失问题立项 | done | Kimi | `change_requests/CR-2026-11-02_nl_cross_semantics.md`；3 点压测前不改业务代码 |
| 2026-11-02 | ECS 部署清单 + seed.json 处置 + P2-14/P2-15 决策单 | done | Kimi | `29_PENDING_DEPLOY_AND_DECISIONS_2026-11-02.md`；`seed.json` 已 gitignore；ECS 已于 2026-11-02 部署（MainPID 602680），worker 待用户批准重启 |
| 2026-11-02 | E 项第四入口外部 AI Agent API —— M0 设计（读档 + 颗粒度对齐 + brainstorm + 设计文档/CR；**只设计不写码不上线**） | in_progress | Kimi | 已读 10-25 brainstorm、`17_JOB_PROTOCOL.md`、`app.py` 路由/quota/tier_policies；产出 `docs/superpowers/specs/2026-11-02-external-agent-api-design.md` + `change_requests/CR-2026-11-02_external_agent_api.md`；10-25 brainstorm 已标记被取代；§11.8 E 项已更新；待用户批准 D1–D6 与 commit |
| 2026-11-02 | §11.8 补 F 节扩展 backlog（32 项远期/挂起任务汇总） | done | Kimi | `cc1ae20` 已 commit/push；`check-progress-docs.sh` 通过 |
| 2026-11-02 | E 项第四入口 M0 设计（读档 + 对齐 + brainstorm + 设计文档/CR） | done | Kimi | `6f82567` 已 commit/push；设计文档 + CR + 10-25 brainstorm 取代标记 |
| 2026-11-02 | 压测文档追加「每个全期 job 耗时分布」监视要求（用户追加） | in_progress | Kimi | 已写入 `27_STRESS_TEST_2026-11-02.md` §2（min/median/p95/max + 排队时长 + 最慢 5 个 job）；待子代理在 item1–item3 小节落地数值 |
| 2026-11-02 | E 项 M1：api_tokens + capabilities + openapi + schema/strategy（特性开关默认关） | done | Kimi | `fb419b4` 已 commit/push 并部署 ECS（MainPID 603714，回滚 `/tmp/qre-deploy-20261101T182548Z.bak`）；新测试 23 例、全量 3322 passed + 34 skipped；生产 flag 关时全路由 404 |
| 2026-11-03 | **E 项 M3：validate + sweeps（参数扫描）** | done | Kimi | `POST /validate`（不执行不计配额 + 成本估计）+ `POST /sweeps`（screen/confirm 两阶段护栏、笛卡尔积串行展开、令牌级上限与会话预算预检、幂等）+ `GET /sweeps`·`/<id>`·`/aggregate`（只回数字）；agent job 不占会员日配额；app 级前缀闸修复 405 泄露；新测试 20 例、全量 **3354 passed + 34 skipped**；ECS 已部署（MainPID 605487，回滚 `/tmp/qre-deploy-20261101T184839Z.bak`），全方法 404 验证 |
| 2026-11-03 | **E 项 M4：令牌限流 + 夜间窗口 + 审计 + 9090 同源** | done | Kimi | `agent_rate_limits` 每分钟原子计数（超限 429 + Retry-After，2 小时前机会式清理）+ `jobs.eligible_at` 夜间窗口（claim SQL 只加一个条件）+ `agent_api_events` 最小审计（只记 token/端点/成败/错误分类）+ 每令牌限额可配（越界收敛）+ 9090 限流/审计/夜间窗口清点；新测试 10 例、全量 **3364 passed + 34 skipped**；ECS 已部署（MainPID 606088，回滚 `/tmp/qre-deploy-20261101T190011Z.bak`） |
| 2026-11-03 | 全期全量压测子代理第一次运行 | done（超时中止） | agent-208 | 2 小时后台预算在等 03:00 闸门期间耗尽，三项实测未开始；harness 已验证（3 只 smoke 7s/43s 端到端），三份 YAML 已生成并存 `.tmp/stress-2026-11-02/`；用户追加的「逐 job 耗时分布」条款已写入 §2 |
| 2026-11-03 | **E 项 M5：结果与产物读取** | done | Kimi | `/jobs/<id>/result`（默认不含 chart_data）+ `/result/chart-data` 按需 + `/artifacts/<name>` 白名单双防穿越 + `purge_expired_agent_artifacts()` 纯函数（不接请求路径）+ openapi 三条路由转已实现；门禁两次拦下本轮改动并已修正；新测试 8 例，定向子集 269 passed；ECS 已部署（MainPID 606687，回滚 `/tmp/qre-deploy-20261101T191846Z.bak`），GET/POST × 4 路由全 404 |
| 2026-11-03 | M5 提交前全量回归 | deferred | Kimi | 全量套件与 03:00 压测争抢 CPU/IO 会污染采样，已主动中止并记入 `27_STRESS_TEST` §8.0；改为跑定向子集（agent_api + git_finalize + 路由冻结 + gui_saas/console/pages）269 passed；**压测结束后必须补跑全量** |
| 2026-11-03 | 全期全量压测子代理恢复执行 | in_progress | agent-208 | 03:00 闸门已过，已 resume 同一 agent（task agent-vn63q4w8）串行跑 item1→item2→item3；目标 §5/§6/§7 |

**M2 计划（2026-11-03 动工前登记，用户要求「任何任务前后都写入长期文件」）**

范围：把「研究会话」做成一等公民，作为外部 agent 定边界、列清单、记账、提交结论的唯一落点。

1. DDL（`deploy/saas/cloud_schema.sql`，幂等）：`research_runs` 表
   （id / user_id / token_id / title / boundary_text / todo JSONB / budget JSONB /
   status / conclusion_text / conclusion_table JSONB / created_at / updated_at / concluded_at）。
   - 状态机：`planned → running → aggregated → concluded`，`archived` 为 TTL 终态；
     QRE 只校验归属与迁移合法性，不替 agent 决定下一步。
   - `boundary_text` / `todo` / `conclusion_text` 一律原样存储，QRE 不生成、不改写、不解释。
2. 端点（agent 令牌鉴权，全部归属校验，他人资源 404 与不存在同体）：
   - `POST /api/agent/v1/research-runs`（scope `jobs:submit`）：建会话；
     budget 只接受白名单键，且**不得超过 `AGENT_DEFAULTS` 的会话级上限**
     （max_jobs=200 / max_artifact_bytes=20GB / max_wall_clock_hours=12），超限 400。
   - `GET /api/agent/v1/research-runs`、`GET .../<id>`（scope `jobs:read`）：列表/详情，
     详情带预算用量（jobs_total / jobs_completed / artifact_bytes / wall_clock_seconds）。
   - `POST .../<id>/status`（`jobs:submit`）：状态迁移，非法迁移 409。
   - `POST .../<id>/conclusion`（`jobs:submit`）：存结论文本与表格，落 `concluded` + `concluded_at`。
3. 预算记账：`research_run_usage()` 从 `jobs.research_run_id` 汇总任务数、
   从 `results.artifacts` 汇总产物体积、从 `started_at/finished_at` 汇总墙上时间；
   会话级上限在 M3 sweep 展开前预检（本切片先把账算出来并暴露给 agent）。
4. 管理台（R-ADMIN-001）：9090「外部 Agent API」卡增加研究会话计数与最近会话列表
   （标题/状态/预算用量/结论是否存在），不回结论文本以外的敏感内容。
5. 测试：新建/归属隔离/非法迁移/budget 超上限收敛/用量记账/结论只存不解释/
   他人会话 404/管理台计数；全量回归不许变红。
6. 部署纪律：ECS 先 apply schema 再发文件、只重启 qre-saas、flag 仍默认关；
   验收通过后 commit/push。

完成度目标：M2 结束时应能在 flag 打开后，由外部 agent 完成
「建会话 → 记账 → 提交结论」全链路；sweep 展开（M3）尚未接入。

**M2 完成情况（2026-11-03）**：全部六项计划落地。
- DDL：`research_runs` 表（含 `boundary_text`/`todo`/`conclusion_text`/`conclusion_table`，
  状态机 `planned→running→aggregated→concluded`，`archived` 为 TTL 终态）。
- 端点：`POST /research-runs`（scope `jobs:submit`）、`GET /research-runs`、
  `GET /research-runs/<id>`、`POST .../status`、`POST .../conclusion`；
  他人/不存在一律 404 同体。
- 预算：白名单四键（`max_jobs`/`max_artifact_bytes`/`max_wall_clock_hours`/`allow_full_market`），
  超 `AGENT_DEFAULTS` 会话级上限自动收敛、负值/未知键/错类型 400；
  详情返回 `usage` + `budget_exceeded` + `budget_remaining`。
- 记账：`research_run_usage()` 从 `jobs.research_run_id` 汇总任务/完成/在飞，
  从 `results.artifacts` 的 `size` 汇总产物体积，从 `finished_at-started_at` 汇总墙上时间。
- 管理台：9090「外部 Agent API」卡新增研究会话区（总数/未完结/已结论 + 最近 20 条标题状态预算）。
- 测试：新 13 例；全量 **3335 passed + 34 skipped**（零回归）。
- 部署：ECS MainPID **604411**，回滚副本 `/tmp/qre-deploy-20261101T183600Z.bak`；
  生产验证 `research_runs` 表与授权就绪、flag 关时 `capabilities`/`research-runs`/`tokens` 全 404、
  既有三页 200。未重启 worker、未跑真实回测。
- **下一步 M3（validate + sweeps）**：`POST /validate` 复用 `validate_yaml`+`check_factor_limits`+
  universe 解析（不执行、不计配额）；`POST /sweeps` 笛卡尔积展开为串行子 job，screen 阶段强制
  抽样 universe 与短区间、confirm 阶段需 `allow_full_market` 且配置数 ≤5，展开前预检会话预算，
  `GET /sweeps/<id>/aggregate` 只回排名数字不回解读。

**M3 计划（2026-11-03 动工前登记）**

1. `POST /api/agent/v1/validate`（scope `factors:read`，不执行、不建 job、不计配额）：
   复用 `gui/engine.py::validate_yaml` + `security/yaml_guard.check_factor_limits` +
   `symbol_norm.normalize_ts_codes` + universe 解析；返回 `valid` / `issues` /
   `normalized_params` / `factor_usage` / `cost_estimate`（按 universe 规模匹配 scale_profiles）。
2. `POST /api/agent/v1/sweeps`（scope `jobs:submit`，强制 `research_run_id`）：
   - `stage=screen`（默认）：**强制**抽样股票池（`random_n`，缺省 300）与较短区间（≤5 年），
     拒绝 `all_market`/`universe`/超过上限的 `codes`；
   - `stage=confirm`：需会话 `budget.allow_full_market=true` 且配置数 ≤5，允许全市场；
   - grid 笛卡尔积展开为 **串行** 子 job（V1 不做并发调度），每个 job 落
     `token_id` / `research_run_id` / `labels`；
   - 展开前预检：令牌日提交上限、在飞上限、会话预算（`max_jobs`/`max_artifact_bytes`/
     `max_wall_clock_hours`）——超限返回 `budget_exhausted` 且**不展开**；
   - 幂等：强制 `Idempotency-Key`，同键返回既有 sweep（不重复展开）；
   - **重要决策：agent job 不占用户人工会员日配额**（否则 50 配置扫描立刻被 3 次/日挡死），
     改由令牌级上限与会话预算约束；worker 容量仍由夜间窗口（M4）保护。
3. `GET /api/agent/v1/sweeps`、`GET /api/agent/v1/sweeps/<id>`：列表/详情（含子 job 状态）。
4. `GET /api/agent/v1/sweeps/<id>/aggregate`：只回**数字**不回解读——每配置一行
   `total_return`/`annual_return`/`sharpe`/`max_drawdown`/`win_rate`/`trades`/
   `avg_holding_days`/`excess_return`/`buy_hold_return`/`n_symbols`，缺字段 null 不编造；
   `sort_by` 白名单，响应带 `note` 与 `disclaimer`。
5. 测试：validate 合同（合法/非法 YAML、因子超限、成本估计匹配）、两阶段护栏
   （screen 要全量被拒、confirm 无 allow_full_market 被拒、confirm 超配置数被拒）、
   预算预检（max_jobs 用尽即拒）、幂等、labels/归属落库、aggregate 口径与 null 处理、他人 sweep 404。
6. 部署纪律：ECS 先 apply schema（若无新增则跳过）再发文件、只重启 qre-saas、flag 仍默认关；
   验收通过后 commit/push。

完成度目标：M3 结束后，外部 agent 在 flag 打开时可完成
「validate → 建会话 → screen 扫描 → confirm 短名单 → aggregate 排名」全链路；
结果读取与受控下载仍在 M5。

**M3 完成情况（2026-11-03）**：六项计划全部落地，另修复一个自身缺陷。
- `POST /validate`：复用 `validate_yaml` + `check_factor_limits`（按属主 tier 策略）+
  `normalize_ts_codes`；返回 valid/issues/normalized_params/factor_limits/cost_estimate，
  显式 `executed:false` / `quota_charged:false`。
- `POST /sweeps`：screen 阶段强制抽样（`random_n` 默认 300、≤500 只、≤5 年，拒 all_market/板块）；
  confirm 需 `budget.allow_full_market=true` 且配置 ≤5；grid 笛卡尔积**串行**展开为子 job，
  落 `token_id`/`research_run_id`/`sweep_id`/`labels`；强制 `Idempotency-Key`（同键返回既有 sweep）。
- 预检：令牌日提交上限（默认 50）、在飞上限（默认 5）、会话 `max_jobs` 与 `max_wall_clock_hours`
  （按成本估计折算），超限一律不展开。
- `GET /sweeps`、`/sweeps/<id>`（含子 job 状态）、`/sweeps/<id>/aggregate`：
  `sort_by` 白名单 8 键，只回数字、缺字段 null、响应带「不含任何投资建议」。
- **关键决策落地**：agent job **不占用户会员日配额**（否则 50 配置扫描立刻被 3 次/日挡死），
  容量改由令牌级上限 + 会话预算约束；已有专项测试锁定该行为。
- **自身缺陷修复**：关闭开关时，对 POST-only 路由发 GET 会在 Flask 路由阶段抛 405，
  蓝图级 before_request 不执行 → 泄露「路由存在」。已补 app 级前缀闸（同 Flag），
  生产复测 GET/POST × 5 路由全 404。
- 测试：新 20 例；全量 **3354 passed + 34 skipped**（零回归）。
- 部署：ECS MainPID **605487**，回滚副本 `/tmp/qre-deploy-20261101T184839Z.bak`；
  `agent_sweeps` 表 + `jobs.sweep_id` 已 apply。未重启 worker、未跑真实回测。

**下一步 M4**：令牌级限流（每分钟，429 + Retry-After）、夜间窗口认领（`nightly_only`）、
`nl_compile_events` 式最小审计（不存策略文本/令牌明文/IP）、9090 展示与执行同源复核。
**M5**：结果端点放行 token 归属 + 受控 artifacts 下载 + 产物 TTL 归档。

---

**M4 计划（2026-11-03 动工前登记）**

1. 限流（PG 原子计数，新增 `agent_rate_limits` 表，键 `(scope, subject_hash, window_start)`）：
   - scope=`agent_minute`，subject=`sha256("agent:tid:"+tid+salt)` 截断（不落原始 token）；
   - window_start=`date_trunc('minute', now())`；单条 `INSERT … ON CONFLICT DO UPDATE …
     WHERE hits < limit RETURNING` 原子计数，多 worker/并发不突破；
   - 在 `authenticate_agent` 内统一执行，覆盖全部 agent 端点；超限 429 + `Retry-After`。
2. 夜间窗口（保护家里 worker 不被 agent 挤占真人时段）：
   - `jobs` 新增 `eligible_at TIMESTAMPTZ`（可空，NULL=立即可认领，旧行不受影响）；
   - `nightly_only=true` 的令牌提交的 job 落在窗口外时置 `eligible_at`=下一个窗口起点，
     响应带 `eligible_at`（HTTP 202 语义已在错误码表）；
   - claim SQL 增加 `AND (eligible_at IS NULL OR eligible_at <= now())`——**只加一个条件，
     不改租约/心跳/回传语义**；`_reap_expired` 与回队路径不动。
3. 审计（新增 `agent_api_events` 表，最小口径）：只记 `token_id` / `endpoint` / `ok` /
   `error_class` / `created_at`；**不记策略文本、不记令牌明文、不记原始 IP**（同
   `nl_compile_events` 纪律）；在 validate / sweeps / research-runs 结论四个写入口记录。
4. 9090（R-ADMIN-001）：「外部 Agent API」卡新增限流计数（行数/命中）、事件计数与失败分类 Top、
   夜间窗口当前是否开放、各令牌 `eligible_at` 待认领 job 数；全部读真实表，不写第二套口径。
5. 测试：限流超限 429 + `Retry-After` + 恢复；`eligible_at` 落在窗口内/外的两种落库；
   claim 不认领未到点 job 且到点后可认领；事件表不落敏感字段（用 SQL 断言列集合）；
   9090 计数与表一致；回归全量不许变红。
6. 部署纪律：ECS 先 apply schema 再发文件、只重启 qre-saas、flag 仍默认关；验收后 commit/push。

完成度目标：M4 结束后，即使 flag 打开，agent 也被「每分钟限流 + 夜间窗口 + 日/在飞上限 +
会话预算」四层闸门约束，且全部行为可在 9090 观测。

**M4 完成情况（2026-11-03）**：六项计划全部落地。
- 限流：`agent_rate_limits`（scope=`agent_minute`，subject=`sha256("agent:tid:"+tid+salt)` 截断，
  window_start=当前分钟），单条 `INSERT … ON CONFLICT DO UPDATE … WHERE hits < limit RETURNING`
  原子计数；超限 429 + `Retry-After`（秒数按分钟剩余算）；2 小时前的行机会式清理。
- 夜间窗口：`jobs.eligible_at`（可空，NULL=立即可认领）+ claim SQL 只加
  `AND (eligible_at IS NULL OR eligible_at <= now())`，租约/心跳/回传语义零改动；
  窗口外提交返回 **202** + `eligible_at`；窗口配置解析失败按「不拦」处理（宁可不拦，不可误拦）。
- 审计：`agent_api_events` 只记 `token_id`/`endpoint`/`ok`/`error_class`/`created_at`，
  在 validate / sweeps / conclusion 三个写入口记录；**不落策略文本、令牌明文、原始 IP**。
- 每令牌限额可在签发时设置（`daily_submit_limit`/`in_flight_limit`/`rate_per_minute`/`nightly_only`），
  非整数/负数 400，越界收敛到上限，0=不限（仅 rate_per_minute）；列举接口同样回显。
- 9090：新增限流计数（行/命中）、审计事件（总数/失败 + 最近 10 条）、夜间窗口是否开放、
  待认领（夜间）job 数，全部读真实表。
- 测试：新 10 例（限流 429/Retry-After/按令牌隔离/0=不限/清理、eligible_at 窗口判定与解析失败降级、
  claim 不认领未到点且到点后可认领、审计列集合不含敏感字段、控制台计数）；
  **全量 3364 passed + 34 skipped**（零回归）。
- 部署：ECS MainPID **606088**，回滚副本 `/tmp/qre-deploy-20261101T190011Z.bak`；
  两表 + `jobs.eligible_at` 已 apply；生产 GET/POST × 3 路由全 404、`/saas/` 200。未重启 worker。

**下一步 M5**：结果端点放行 token 归属（复用 P0-8 `_require_completed_result`）+ 受控 artifacts
下载（文件名白名单 + 限速 + TTL）+ 产物 TTL 归档（15 天，复用 D-21 归档机制）。

---

**M5 计划（2026-11-03 动工前登记）**

1. `GET /api/agent/v1/jobs/<id>/result`（scope `results:read`）：返回 `summary` /
   `data_until` / `result_contract` / `artifacts` 清单 / `symbol_details` 元信息；
   **不默认返回 `chart_data`**（全市场产物可达数百 MB，避免一次响应打爆 agent）。
2. `GET /api/agent/v1/jobs/<id>/result/chart-data`：按需取净值曲线等绘图数据。
3. `GET /api/agent/v1/jobs/<id>/artifacts/<name>`：受控下载——文件名白名单
   （`^[A-Za-z0-9._-]+$`，禁路径分隔符）+ 解析路径必须落在 `SAAS_UPLOAD_DIR/job_<id>/` 内
   （双重防穿越）+ 文件必须真实存在；限速复用 M4 每分钟闸。
4. 归属：允许读「本令牌创建的 job」与「同属主的人工 job」（令牌代表用户行事）；
   他人/不存在一律 404 同体，不泄露存在性。
5. **产物 TTL 明确推迟**：删除文件绝不挂在请求路径上（一次 GET 触发批量删文件不可接受）；
   改为先提供 `purge_expired_agent_artifacts()` 纯函数 + 文档登记，待接入既有周扫 timer
   （D-21 归档机制）后再启用。本轮不做静默删除。
6. 测试：归属隔离（他人 404）、chart-data 按需、artifacts 白名单与穿越防护
   （`../`、绝对路径、不存在的文件）、TTL 纯函数对过期/未过期/缺失目录的行为；
   回归全量不许变红。
7. 部署纪律：ECS 只发代码（无 schema 变更则跳过 apply）、只重启 qre-saas、flag 仍默认关；
   验收后 commit/push。

完成度目标：M5 结束后外部 agent 可闭环「提交 → 等完成 → 读指标 → 下钻曲线 → 取产物文件」。

---

**M5 完成情况（2026-11-03）**：七项计划中六项落地，产物 TTL 按计划**只做纯函数不接请求路径**。
- `GET /jobs/<id>/result`：返回 `summary`/`data_until`/`result_contract`/`artifacts`/
  `research_run_id`/`sweep_id`/`chart_data_url`；**默认不含 `chart_data`**（全市场产物可达
  数百 MB，避免一次响应打爆外部 agent）。
- `GET /jobs/<id>/result/chart-data`：按需取绘图数据。
- `GET /jobs/<id>/artifacts/<name>`：受控下载——文件名白名单 `^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$`、
  解析后真实路径必须落在 `SAAS_UPLOAD_DIR/job_<id>/` 内（双防穿越）、文件必须存在；
  限速复用 M4 每分钟闸。
- 归属：本令牌创建的 job + 同属主人工 job（令牌代表用户行事）；他人/不存在一律 404 同体。
- TTL：`purge_expired_agent_artifacts(engine, upload_root=None, ttl_days=15)` 纯函数——
  只删「令牌创建的 job 且终态且 finished_at 早于 TTL」的 `job_<id>/` 目录，人工产物一律不碰；
  目录来源刻意不读 Flask app config（周扫 timer 在应用上下文外调用，`current_app` 会抛异常），
  改为 显式参数 > 环境变量 > 仓库默认。**未挂到任何请求路径，也未接入周扫**（见下）。
- openapi：`/jobs/{id}/result`、`/result/chart-data`、`/artifacts/{name}` 改为已实现；
  单配置 `POST /jobs` 仍标 `x-status: planned`——外部 agent 统一走 `/sweeps`（哪怕只有一个配置），
  避免两套提交路径漂移。
- **门禁两次拦住我自己的改动，都已修正**：
  ① `test_git_finalize_check.py` 的合成泄漏值含 "example" 被占位符过滤吞掉 → 改用随机形态值，
    并新增「占位符不放行」反向用例；
  ② `test_saas_job_endpoint_audit.py` 的 P0-8 冻结路由清单不认识三条新 agent 路由 →
    已在冻结清单中显式登记（含归属校验说明）。这正是冻结清单的设计目的。
- 测试：新 8 例（默认不含 chart_data / 按需取 / 409 未完成 / 他人 404 / scope 403 /
  穿越与缺失 404 / TTL 清 agent 不碰人工 / TTL 保留未过期）。
- **遗留（明确记录，不静默）**：agent 产物 TTL 尚未接入周扫 timer；在接入前，
  `purge_expired_agent_artifacts()` 只是可用函数。接入属运维项，需与 D-21 归档机制统一排期，
  且**任何删除都不得挂在请求路径上**。

**下一步 M6**：用一个真实外部 agent 走通「发现 → validate → 建会话 → screen 扫描 →
confirm 短名单 → aggregate → 读结果 → 提交结论」全链路；在此之前需用户决定是否打开
`QRE_AGENT_API_ENABLED`（当前生产默认关）。


---

## 8. 建议下一任主 Agent 的第一步行事

1. 读 `AGENTS.md` 与本文件。
2. 跑 `git log --oneline -20`、`git status --short`、`uv run pytest -q -p no:randomly` 确认基线。
3. 向用户确认三件事：
   - 是否重启 worker 激活 P2-14；
   - 是否部署 ECS；
   - 是否默认开启 P2-15。
4. 然后再从 P0-5 或用户新任务推进。
