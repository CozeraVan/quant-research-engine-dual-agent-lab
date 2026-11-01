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

---

## 8. 建议下一任主 Agent 的第一步行事

1. 读 `AGENTS.md` 与本文件。
2. 跑 `git log --oneline -20`、`git status --short`、`uv run pytest -q -p no:randomly` 确认基线。
3. 向用户确认三件事：
   - 是否重启 worker 激活 P2-14；
   - 是否部署 ECS；
   - 是否默认开启 P2-15。
4. 然后再从 P0-5 或用户新任务推进。
