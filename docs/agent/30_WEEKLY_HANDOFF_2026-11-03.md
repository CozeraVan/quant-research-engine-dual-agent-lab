# 30_WEEKLY_HANDOFF_2026-11-03.md — 主 Agent 交接文档（2026-11-03 切换前）

> 本文是 **2026-11-03 的主 Agent 交接权威记录**，覆盖 2026-11-02 夜~11-03 上午的全部工作。
> 用户即将切换主 Agent；**接手本项目必读本文 + `AGENTS.md` + `docs/agent/14_LAUNCH_ROADMAP.md` §11.8**。
> 任务级流水见 `26_WEEKLY_HANDOFF_2026-11-02.md` §7（每个切片的动工前计划 + 完成后对照）。

---

## 1. 当前状态（2026-11-03 09:40 CST）

| 项 | 值 |
|---|---|
| 分支 / HEAD | `master` / **`a4ea695`**（已 push，工作树干净） |
| 全量测试 | `uv run pytest -q -p no:randomly` → **3385 passed, 34 skipped**（基线 3299+34，零回归） |
| 文档门禁 | `bash scripts/check-progress-docs.sh` / `bash scripts/git-finalize-check.sh` 均 exit 0 |
| 本地 worker | `qre-saas-worker.service` **PID 430787**（11-03 09:08 重启，2 轻 + 3 重槽，轮询 aguhuice.com） |
| ECS SaaS | MainPID **609646**；`QRE_AGENT_API_ENABLED=1` **已打开**（11-03 09:33） |
| 生产开关回滚 | 删 `/etc/qre-saas.env` 里 `QRE_AGENT_API_ENABLED=1` 行 + `sudo -n systemctl restart qre-saas`；备份 `/etc/qre-saas.env.bak-20261102T013344Z` |
| 压测遗留（**未清理，用户要求保留**） | 临时 app(66791/66788)、`/tmp/qre-worker-job{6,7,8}-*`、`outputs/saas_uploads/job_6`、`job_8`、`qre_stress_2611` 库；清单见 `27_STRESS_TEST` §10。**job7/job8 是唯一完整产物副本，删前必须归档** |

---

## 2. 本轮完成的工作（按提交倒序，全部已 push）

| 提交 | 内容 |
|---|---|
| `a4ea695` | **M6 外部 agent 端到端验收通过 + 生产打开 `QRE_AGENT_API_ENABLED`**（26 项断言全绿，3/3 job 真实回测；可复跑脚本 `scripts/agent_api/m6_acceptance_client.py` + 证据 log） |
| `290a8c2` | 修 dev 后门用户不存在导致令牌签发 500（幂等补 `users` 行 + 回归用例） |
| `9071041` | 解除第四入口 6 例测试的墙上时钟依赖 + 修一处全量 flake（`test_gui_risk_report` 截止 10s→30s） |
| `a084d94` | **全期全量压测三项收官** + **P0-10 容量假设修正**（item3 峰值 13.97GB，推翻 6GB×4 并发模型） |
| `ebf825e` | **P0-9 A+C**：`MAX_FORM_PARTS=5000` + worker 回传失败落终态（4xx→`result_upload_http_<code>` 不可重试） |
| `10d0984` | 立项 P0-9（压测实测：413 丢结果 + `uploading` 无终态被重排重算） |
| `f46daad` | **M5** 结果与产物读取（`/result` 默认不含 chart_data、`/artifacts/<name>` 白名单双防穿越、TTL 清理纯函数） |
| `f69a0f2` | secret 扫描排除已知占位符（测试夹具不再误报） |
| `87d59c0` | **M4** 每分钟限流（429+`Retry-After`）+ 夜间窗口 `eligible_at` + 最小审计 + 每令牌限额 + 9090 清点 |
| `917920c` | **M3** `validate` + `sweeps`（screen/confirm 两阶段护栏、笛卡尔积串行展开、预算预检、幂等、aggregate 只回数字） |
| `ed261a0` | **M2** `research_runs` 研究会话容器（边界/清单/预算/结论原样存储，QRE 不解释） |
| `fb419b4` | **M1** `api_tokens` + `capabilities` 成本信封 + `openapi.json` + `schema/strategy` |
| `6f82567` | E 项 M0 设计定稿（设计文档 + CR，取代 10-25 brainstorm） |
| `cc1ae20` | §11.8 补 F 节扩展 backlog（32 项远期/挂起任务，解决「todolist 变短」） |

### 2.1 第四入口（E 项）最终形态

用户三条硬边界（不可协商）：① 个人开发，**不自建/不调任何模型**；② 可调用库内全部数据但**只做回测相关动作**；③ **不做投资建议**，只做数据结果聚合。

已上线能力：令牌签发/吊销 → 成本信封 → openapi/JSON Schema → validate → 研究会话（边界/清单/预算/结论）→ sweep 两阶段扫描 → 聚合排名 → 结果/曲线/受控产物下载。
四层容量闸门：**每分钟限流 + 夜间窗口（00:00–06:00 CST）+ 日提交上限 + 在飞上限 + 会话预算**。
9090「外部 Agent API」卡：开关/默认限额/令牌清点/限流计数/审计事件/夜间窗口状态。

### 2.2 压测实测基线（做容量判断前必读 `27_STRESS_TEST`）

全市场 5201 只 × 2009-01-05~2026-10-30，本地 WSL 单机：

| 项 | exec_s | 收益/回撤/超额 | RSS 峰 | 本地产物 | 回传 |
|---|---|---|---|---|---|
| item1 NL SMA5×SMA200 | 3854 | -21.37% / -69.44% / -33.67% | 6.38G | 1.01GiB | 333 文件 / 20MiB（截断） |
| item2 wizard RSI14 | 2571 | +24.20% / -41.96% / +11.91% | 6.30G | 0.85GiB | **0 文件（413）** |
| item3 NL MACD | 4312 | +16.47% / -46.67% / +4.17% | **13.97G** | 1.52GiB | 245 文件 / 20MiB（仅 1.0%） |

三项 `buy_hold_return` 折算均 ≈ +12.30%（同宇宙同区间、与策略无关）→ 口径自检通过。

---

## 3. 重大失误与必须复查点（诚实清单，下一任接手先看这节）

1. **我用管道吞掉过一次提交门禁的退出码**：`bash scripts/git-finalize-check.sh | tail` 使 secret 扫描的 exit 1 被 `tail` 的 0 覆盖，M4 提交在门禁红灯下仍然通过。已在 `f69a0f2` 提交信息中记录在案，并修正了扫描规则（占位符不算泄漏）。**纪律：门禁必须看真实退出码，禁止用管道接尾命令后直接 `&&` 提交。**
2. **压测采样被我自己污染**：03:14 在本机启动 pytest 全量套件，与 item1 争抢 CPU/IO，污染了 03:14 之后的采样。已主动终止并写入 `27_STRESS_TEST` §8.0。**纪律：压测期间不在本机跑任何重任务。**
3. **我自己写的测试时间依赖**：M4 默认 `nightly_only=true`，06:00 后跑全套件 6 例 202≠201 全红。已改为 monkeypatch 窗口配置。**教训：默认值受时间影响的特性，测试必须显式设定。**
4. **压测文档曾含一次性 upload_token**：被 secret 扫描正当拦下，已脱敏为 `<REDACTED_一次性凭证>`。**纪律：日志片段进文档前必须过 secret 扫描。**
5. **改过 DB 行情数据的历史教训仍在**（见 `25_WEEKLY_HANDOFF_2026-10-29.md`）：源数据只读，`stock_daily` 一行未改、也不许改。
6. **压测子代理两次耗尽 2 小时后台预算**：第一次在等 03:00 闸门时耗尽（三项未开始），第二次跑完 item1/item2 后耗尽。已 resume 续跑。**排期超长任务时要预留预算或分段。**

---

## 4. 遗留与待办（按优先级，全部已登记在 §11.8）

### P0（建议最优先）
- **P0-9 剩余**（`CR-2026-11-03_result_upload_413_and_uploading_terminal.md`）：B 分片上传（根治）、§8.5 20MiB 静默截断**无任何 `truncated` 标记**（item1/item3 均只落 ~1%）、§8.7 `/tmp/qre-worker-job*` 不清理、§8.11 batch 全量 `progress` 恒 0、§8.15 reaper 侧加固（worker 被 kill 在回传中途仍会走重排）。
- **P0-10 容量模型重建**：§10「安全并发 4（6G×N≤25.6G）」与 R2 heavy 闸门 6500MB 在 item3 级策略（50.4 万笔 → 13.97GB）下**不成立**，需按交易笔数/聚合规模重建模。

### P1
- **M7**：`validate` 增加**因子存在性预检**（M6 暴露：表名写错要等 worker 执行才报 `data_missing`，外部 agent 无法在提交前发现；设计文档 §4.2 原就要求）。
- **NL 穿越语义修复**（`CR-2026-11-02_nl_cross_semantics.md`）：`_DSL_DOC` + few-shot 教模型用 `.shift(1)` 表达上穿/下穿，bump `NL_COMPILER_CACHE_VERSION`，先补测试再改。
- **P0-5 经典策略页重新填充**：策略定义/小样本/滚动器解耦已完成；**全量全期重跑待用户手动布置**（先小样本验证效率与正确性）。

### P2 / 挂起
- P2-14 参数网格：实现与验收完成，**worker 已重启即生效**，全量预算待用户批准。
- P1-11《我不是股神》重启（前置复权契约已 OK，待明确范围）；P2-16 短视频提取（等视频产出）。
- D-21 `familyOf` 旧名分支退场：11-23 后、连续 4 次周扫为 0 才可删。
- 会员分层/付费、移动端/App、硬件扩容、分时因子：挂起。
- §11.8 **F 节 32 项扩展 backlog**（远期研究/引擎/数据运维/游戏/变现）。

---

## 5. 建议下一任主 Agent 的第一步行事

```bash
cd /home/van/quant-workspace/quant-research-engine-dual-agent-lab
git log --oneline -20 && git status --short          # 确认 HEAD=a4ea695、树干净
uv run pytest -q -p no:randomly                        # 确认 3385 passed, 34 skipped
bash scripts/check-progress-docs.sh                    # 文档门禁
systemctl status qre-saas-worker.service --no-pager | head -8   # 确认 PID 430787 active
```

然后按 §4 优先级推进；**任何新任务先登记到 `26_WEEKLY_HANDOFF_2026-11-02.md` §7**（用户明确要求：任务不论准备或完成都要记录）。

## 6. 长期纪律（不要违反）

- `docs/agent/` 是唯一权威长期记忆；对话不是真相来源。
- 代码/UI 改动：先部署 ECS 再提交；未通过验收立即回滚；**门禁必须看真实退出码**。
- 新 UI 不得新增灰色小字备注；解释统一 `tip-trigger + data-tip + LabUI.helpTips`。
- 权限/配额改动必须同步 9090 管理台（R-ADMIN-001），展示与执行同源。
- 生产表 UPDATE/DELETE 前必须跑同 `WHERE` 的 `COUNT(*)` 对账；数据修复先影子表。
- 源数据只读：`stock_daily` 一行未改，也不许改。
- 测试/并行任务必须隔离 `SAAS_UPLOAD_DIR`（如 `.tmp/test-uploads-isolated`）。
- 压测/性能测量期间不在本机跑其他重任务。
- 日志片段进文档前必须过 secret 扫描（`git-finalize-check.sh`）。
