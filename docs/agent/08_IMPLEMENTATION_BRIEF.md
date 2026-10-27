# Implementation Brief

## Task ID

QRE-SAAS-FRM-HISTOGRAM-CUMRET（经典策略 FRM 日收益分布无数据修复）

## Created By

KIMI_CODE（2026-10-27；用户要求检查经典策略 FRM 结构并修复日收益分析无数据）

## 目标与边界

1. 只修 SaaS `/api/results/<job_id>/risk-analysis` 的“日收益分布/直方图”数据缺失，不改 FRM 指标计算、风险报告、收益曲线口径或页面结构。
2. 直方图数据源必须与 risk_report 的日收益口径一致：使用 `result_chart_data.cumret` 差分还原日收益；禁止使用 `total_equity.pct_change`（会引入新股注资跳变），禁止把 per-symbol `equity_curve.csv` 误当组合级曲线。
3. 无 risk_report、无 cumret、cumret 过短或 mean/std 缺失时，`histogram` 保持 `None`，前端继续显示“暂无分布数据”，不造数据。
4. 不跑回测、不改数据库/worker/引擎/游戏；按 R-DEPLOY-001 先部署 ECS 并验证，再等待用户验收；未 commit/push。

## 验证

```bash
uv run pytest tests/test_gui_lab_result.py tests/test_gui_saas.py tests/test_saas_access_hardening.py -q
uv run pytest tests/ -q
./deploy/saas/deploy-ecs.sh src/quant_research_engine/gui/lab_result.py src/quant_research_engine/gui/saas/app.py
# 生产只读验证：/api/results/58|66/risk-analysis 的 histogram 40 箱、点数 = n_obs
```

## Task ID

QRE-WEEK-TESTDEBT-ML-SENSITIVITY（工程收口 + M10.4 参数敏感性工具化）

## Created By

KIMI_CODE 统筹（2026-10-27）；DeepSeek 实施，Kimi 复核。用户 2026-10-27 选择本周主线：工程收口 + ML 工具化。

## 目标与边界

1. **工程收口**：修掉全仓唯一红灯 `tests/test_showcase_roller.py::TestParams::test_build_roll_params_holding_override`。根因是该测试硬编码读取已按用户批准删除的外部产物 `/home/van/qre-outputs/gui-console/runs/20261011T135434249768/strategy.yaml`。必须改为自包含 YAML/夹具，禁止恢复已删除数据，禁止放宽原断言语义。
2. **M10.4 参数敏感性工具化**：在现有只读 ML 报告基础上增加确定性 sensitivity 能力，回答默认 `eps=1.0` 的“无成簇”是否对参数敏感。默认行为与既有产物合同不变；不新增公网 UI、不新增主环境依赖、不重算统计、不跑任何回测。
3. **游戏边界**：不碰 `src/quant_research_engine/game/`、游戏测试、`docs/agent/22_TRADING_GAME.md` 与游戏 CR；这些保持本地未提交，等用户试玩反馈。
4. **流程边界**：DeepSeek 不改共享进度文档（04/05/09/10/11/14 等），由主 Agent 统一回写；不部署 ECS、不 commit/push；不得修复无关架构或恢复旧数据。

## 实施要求

### A. 测试债务修复

- 用 `tmp_path` 或模块内最小 YAML 复现 job#58 的 holding 语义：YAML `holding.max_holding_days=20`；`params.max_holding_days=None` → 20；显式 `0` → 0；`mode=shared` 仍按现有逻辑报错。
- 顺带搜索非 slow 测试中其它硬编码 `qre-outputs/gui-console/runs/...` 路径；凡因本轮清理失效的，改为自包含或明确 skip，不静默删除覆盖。
- 验证：`uv run pytest tests/test_showcase_roller.py -q` 与全量 `uv run pytest tests/ -q` 必须记录真实结果。

### B. M10.4 sensitivity

- CLI 增加可选的参数网格（建议 `--eps-grid`，默认关闭；默认输出与当前完全一致），对同一 fit 产物逐组合运行并输出 sensitivity 摘要：策略状态计数、成簇策略数、noise 股票数、参数组合。
- 输出物必须确定、可审计；不得覆盖默认 `ml_cluster_*` 主产物。manifest 或 sensitivity 文件需记录参数、随机种子、输入目录和 scikit-learn 版本。
- 测试覆盖：默认不开启时行为不变；网格输出确定；空/不足样本安全；主环境无 sklearn 降级不变。
- 真实数据只读验证使用既有 `outputs/strategy_fit/f365c8a07b33`；证据可放 `.tmp/`，不跑回测。

## 验证命令（最低要求）

```bash
uv run pytest tests/test_showcase_roller.py -q
uv run pytest tests/ -q
PYTHONPATH=.venv-ml/lib/python3.13/site-packages uv run pytest tests/test_strategy_fit_ml.py tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py -q
.venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33 --eps-grid 1.0,1.5,2.0
```

## 完成定义

- 全仓测试不再存在本轮已知外部产物失败；如有其它失败必须如实报告，不得伪报全绿。
- M10.4 默认合同不变，sensitivity 输出可复现；真实 fit 的默认/敏感性差异被明确记录。
- 共享文档由主 Agent 在复核后统一更新。

## Task ID

QRE-PARALLEL-GAME-TERMINAL-AND-M10-4（DeepSeek 游戏修复 + Step 5 ML 聚类首片）

## Created By

KIMI_CODE 统筹（2026-10-27）

## 目标与边界

1. DeepSeek 按 `change_requests/CR-2026-10-27_game_terminal_repair.md` 在当前游戏版本上先复现并修复 OHLC 与 EMA/BOLL 口径错位，再完成紧凑交易终端布局和真实浏览器验收；仅 WSL，不改主线。
2. Step 5 按 `change_requests/CR-2026-10-27_m10_4_ml_cluster.md` 实现 M10.4 首个分析切片：复用 M10.1、保留 90/99/99.9 层级、输出聚类/noise 与可解释摘要；只读已有产物，禁止新全量回测。
3. 两项均不 commit/push；共享长期文档由主 Agent 回收后统一更新。游戏不部署 ECS；M10.4 本片为本地分析能力，不新增公网 UI。

## 历史任务：QRE-DATA-CLEANUP-EXECUTION

四库与指定旧产物已删除，`qre-outputs` 27G→536M，磁盘可用 386G→418G。备份与清单在 `/home/van/quant-workspace/backups/local-cleanup-20261027/`；akshare 仅保留结构+行数，本体不可恢复。三份 CSV（20261019/20/21）与入库格式匹配，均为 pending，timer enabled/active，下一触发 2026-10-27 17:20 CST。8080/8092 HTTP 200；8081 staging 引用已删除的 aguhuice_local，重用前需重建/换库。未 commit/push。

### 历史盘点（2026-10-27 早些时候，只读）

## 盘点结果（2026-10-27，只读；未删除任何文件/表/库）

**三项高风险（需用户决定，均未动手）**：
1. **`public.stock_daily_qfq_legacy` 已不存在**（全 schema 搜 `%legacy%`/`%qfq%` 为 0 条），本地亦无 `tushare_data` dump ⇒ 2026-10-12 方案A（qfq→原始价+adj_factor）的**回滚能力已永久失去**。新口径自 10-12 起生产生效且因子已全历史重算，但该选项不再存在。
2. **分钟线压缩缺口 140GB**：922 chunk 中 708 已压缩仅 396MB，214 未压缩 140GB；其中 **213 个 `range_end` 早于 T-7 仍未压缩**（2022-09-01 → 2026-10-08），违反 20 §3.4 规则。`minute_compress.log` 声称 10-11 已压缩 707 个，但未压缩 chunk 内部 ID 更高，说明是那次之后新建、再未压缩。重跑 `compress_minute_chunks.sh`（幂等，已有一次成功记录）预计回收 ~139GB。
3. **分钟线数据落后日线 10 天**：`stock_minute_1m` 最新 2026-10-16 vs `stock_daily` 2026-10-26。分钟线只入用户拷入 `mindata` 的 CSV，10-16 后无新文件；`minute-csv-ingest.timer` 每天「扫描到 CSV 0 个」。需确认是暂停还是漏拷。

**「已入库」≠「可安全删除」的核查结论**：`/home/van/mindata` **已是空的**（0 文件，24KB，仅剩两个空目录 inode）。日志证明只有 5 个 CSV（20261012–1016）走过「先校验 rows_csv==rows_db 再删除」；`import_minute_csv.py` 无任何删除代码，4308 个历史 CSV 属**无日志的脚本外删除**（`mindata/` mtime 2026-10-11 23:19 晚于审计最后写入 20:10，顺序正确但无轨迹）。数据侧已验证完整：审计 4318 条全部 `rows_csv==rows_db`、审计日期与表日期双向差集 0、抽查 8 个日期（含磁盘打满失败的 2022-08-22/25/29）审计 `rows_db` 与实时行数 8/8 MATCH。**但源 CSV 不可恢复，今后发现缺口只能回原始数据商重新下载。**

**可删候选（待确认，未动）**：空壳库 `aguhuice_test`(7.5MB,0 表)、`quant_hub`(10MB,0 public 表)；陈旧 `aguhuice_local`(8.9MB,3 users/15 jobs,9-27→10-05)；`qre-outputs` 陈旧产物 `refresh/incremental` 17G(8-02)、`gui-console/runs` 5.4G(8-20)、`backtests` 4.3G(8-18)、`gui-run` 442M(9-13) 及约 20 个 7 月 `*_check` 目录。任务书提到的 `qre_saas`/`dbg` **均不存在**。

**需保留/勿动**：`refresh/registry.json`/`state.json`/`delta/`（KB 级活配置，被 `gui/refresh_registry.py` 引用，绝不能随 17G 一起删）；`saas_uploads`（今天仍在写）、`market_risk`(10-26)、`video_packages`(10-24)；`.tmp/ms-playwright` 681M + `.tmp/browser-venv` 142M（浏览器审计工具链）；两个上一任务 staging 库 `qre_factor_display`/`qre_readonly_share_browser`（各自任务验收后再删）。

**高风险单项**：`akshare_data` 5.8GB——`stock_ticks` 36,147,932 行、2026-04-07→04-24、10 分区；`AK_DB_URL` 仅在 `quant_ts/config.py` 定义、全仓无消费者，属 4 月 tick 实验遗留。

**验证 SQL/命令（只读，已实跑）**：
```sql
-- 审计一致性
select trade_date, rows_csv, rows_db from public.stock_minute_1m_audit where rows_csv is distinct from rows_db;  -- 0 行
-- 审计 vs 实际表双向差集
select trade_date from public.stock_minute_1m_audit except select distinct trade_date from public.stock_minute_1m;  -- 0 行
select distinct trade_date from public.stock_minute_1m except select trade_date from public.stock_minute_1m_audit;  -- 0 行
-- 单日实时行数比对
select count(*) from public.stock_minute_1m where trade_date='2022-08-25';  -- 1180224 = 审计 rows_db
-- 压缩缺口
select count(*), pg_size_pretty(sum(pg_relation_size(format('%I.%I',chunk_schema,chunk_name))::bigint))
from timescaledb_information.chunks
where hypertable_name='stock_minute_1m' and not is_compressed and range_end < (now()-interval '7 days');  -- 213 | 140 GB
-- 遗留表/库搜索
select table_schema||'.'||table_name from information_schema.tables where table_name ilike '%legacy%' or table_name ilike '%qfq%';  -- 0 行
```
磁盘：1007G 总 / 570G 已用 / 386G 可用（60%），无告急。

**未做**：未删除任何文件/表/数据库、未修改生产或 WSL 数据、未跑真实回测、未碰游戏；未 commit/push。清理动作全部等用户逐项确认后再立项。

## Task ID

QRE-ECS-SSH-HARDENING（root SSH 与部署发布纪律加固）

## Created By

KIMI_CODE 规划并实施完成（2026-10-27；已生效待人工验收）

## 目标与边界

1. 先审计并证明 `deploy` 用户密钥登录与 `sudo -n` 可用，再考虑禁用 root 直连；不得在未验证备用路径时锁死 SSH。保留 9090 管理台所需 TCP 转发，禁 root 密码登录、禁密码交互、仅密钥。
2. 使用独立 `sshd_config.d/99-qre-hardening.conf`，不改其他系统配置；变更前备份，`sshd -t` 通过后 reload，不强制断开当前会话。验证 deploy 新连接、sudo、qre-saas 状态与 9090 隧道，root 直连按预期拒绝。
3. 同步部署纪律：生产只接受密钥、禁止 root 直接操作业务文件、使用 deploy+sudo 与既有备份流程；记录回滚路径与云控制台救援方式，不跑真实回测，不推进游戏或其他任务。
4. 更新 04/05/08/09/10/11/14/16 与 deploy 运维配置/脚本；不 commit/push，待用户人工验收。不得修改 WSL 数据库、worker、因子或 UI。

## 实施结果（2026-10-27，已生效待人工验收，未 commit/push）

- **审计先行，且审计就抓出锁死风险**：`deploy` 在 `sudo` 组但密码锁定（`L`），`/etc/sudoers.d/deploy` 仅放通 `systemctl`/`docker`——`sudo -n` 当时**不可用**。若直接禁 root，将无法安装文件、无法 PG 备份恢复、无法动证书/防火墙。已补 `/etc/sudoers.d/90-qre-deploy`（`deploy ALL=(ALL:ALL) NOPASSWD: ALL`，0440）并修掉 `sudoers.d/deploy` 的 0644 权限隐患，`visudo -c` 全绿后才动 sshd。
- **deploy 路径五项实证**（改 SSH 前）：密钥登录 uid=1000；`sudo -n` → uid=0；业务文件可读；`/tmp → sudo install → sudo rm` 部署链干跑成功；deploy 自建隧道 9091 应用层 200 且 `/api/saas/factors` 902/902 带 zh。
- **sshd**：新增 `99-qre-hardening.conf`（`PermitRootLogin no`/`PasswordAuthentication no`/`KbdInteractiveAuthentication no`/`PubkeyAuthentication yes`/`AllowTcpForwarding yes`）；因 sshd **同关键字取先出现者**且 drop-in 按字典序展开，`99-aguhuice-hardening.conf`（排在前）的 `PermitRootLogin prohibit-password` 必须改为 `no`，否则新文件被完全遮蔽（已实测证明：只留新文件时 `no` 生效，并存时回退 `without-password`）。该文件另两行原样未动。`sshd -t` 通过 → `systemctl reload ssh`（不断会话）。生效值 `sshd -T` 复核如上。
- **验证**：root 新连接 `Permission denied (publickey)`；既有 root 隧道 reload 后仍 200；deploy 新连接/`sudo -n`/`qre-saas active`/`nginx`/`ssh` 全过；deploy 隧道 9092 与 `admin-tunnel.sh`（deploy@）起的 9090 均 `/saas/new` 200、`/saas/console` 200；`fail2ban-client status sshd` 经 `sudo -n` 正常。陈旧 root 隧道已换成 deploy 所有，现网无 root 会话。
- **脚本**：新增 `deploy/saas/deploy-ecs.sh`（deploy+sudo 唯一部署入口，`--dry-run`，自带 `/tmp` 回滚副本，只重启 qre-saas）；`admin-tunnel.sh`/`pull-ecs-backup.sh` 默认 `deploy@`；`scripts/sync_saas_metadata.py` 用法注释同步。**该脚本已真实端到端跑通**（用与生产 SHA256 相同的 metadata.json，四步全过、生产字节未变），并修掉两个真 bug（scp 不自建远程嵌套目录；内联 `bash -c` 二次转义 → 改远程脚本文件）。
- **测试**：无 `src/` 改动、无测试引用这三个脚本；**全量 2890 passed + 6 skipped**（基线一致，零回归）；`bash -n` 三个脚本全过。
- **备份/回滚/救援**：`/tmp/qre-ssh-hardening-pre-20261027/`；回滚两步（删 99-qre-hardening.conf + 改回 prohibit-password → reload ssh；删 90-qre-deploy）均不断业务；阿里云控制台 VNC 救援路径写入 `16_ECS_DEPLOYMENT.md` §6。
- **未 commit/push、未跑真实回测、未碰 WSL 数据库/worker/因子/UI/游戏。** 建议提交 `chore(ecs): 禁 root 直连并落地 deploy+sudo 部署纪律`。

## Task ID

QRE-FACTOR-ZH-COVERAGE（剩余 341 列中文显示名维护）

## Created By

KIMI_CODE 规划并实施完成（2026-10-27；已部署待人工验收）

## 目标与边界

1. 在 `QRE-FACTOR-DISPLAY-CONTRACT` 基础上维护剩余 341 列中文显示名，覆盖 Alpha191 191、Alpha101 31、quality/growth `_rank` 族与少量财务报告期/现金流字段。canonical、display 图表合同、别名解析、common/core 不变。
2. 中文名必须来自实际公式/官方定义或明确字段语义，不能凭列名猜译、不能伪造；无法确认的条目保留 `zh=null` 并在覆盖报告列出。优先保证常用与可解释条目的准确性，不为追求 100% 而乱译。
3. `scripts/gen_factor_registry.py` 的 FAMILY_RULES/MANUAL_ENTRIES 可复现输出；重新生成 registry 与 deploy/saas/metadata.json，校验所有 canonical、别名和 display 合法。不得修改数据库、worker 或游戏文件。
4. 运行注册表/呈现/相关与全量测试，检查自选因子目录中文展示和搜索；按 R-DEPLOY-001 备份后直接部署 ECS 待验收，未 commit/push。保护 replay/Night Mode 在途改动，不跑真实回测。

## 实施结果（2026-10-27，已部署待人工验收，未 commit/push）

- **覆盖 341/341，遗留 0 列**：`ALPHA191_ZH` 191 + `ALPHA101_ZH` 31 + `FINANCIAL_ZH` 119（quality 87 / growth 16 / `_pit_financial_panel` 14 / candle 1 / value 1）。中文名覆盖 554 → **895/895（100%）**，metadata 902/902 项带 zh。无一条需要保留 null，因此覆盖报告中「未维护条目」为空。
- **命名溯源**：alpha191 逐条对照 `indicators_tushare/alpha191/formulas.py` docstring（含 DolphinDB 口径与 errata 注释）；alpha101 逐条对照官方 486 文档表达式表（`change_requests/factor_specs_p4p5p7.md` §三）；quality/growth 逐条对照 `panel_factors/quality.py::compute_all` / `panel_factors/growth.py` results 与 `change_requests/factor_specs_p1p3.md` §三/§四表达式表；`_pit_financial_panel` 按 `panel_factors/pit_panel.py` FAMILIES 与 Tushare 标准字段语义。
- **三处需要口径注记的命名**（已在 04/21 号文档写明，避免后续误读）：`gpm_q` 实现与 `gpm_ttm` 同为 TTM 口径 → 「毛利率(TTM口径)」；`ar_ap_to_revenue` 含 contract_liab 兜底并扣预付款项 → 「预收预付净额/营业收入(TTM)」；`npm_tsh` 按官方语义（非笔误文本）→ 「归母净利润/平均总股本」。`_rank` 列统一「·排名」后缀。
- **实现**：`scripts/gen_factor_registry.py` 新增三个模块级字典 + `_coverage_zh(table, column)`，在 `build_registry()` 的 `if manual.get("zh")` 后以 `elif not entry["zh"]` 挂载；只补空不改名，不改 FAMILY_RULES/MANUAL_ENTRIES/别名/common/core/display。
- **零漂移**：重新生成前后逐字段比对，除 zh 外 0 差异；341 条 null→中文名，0 条覆盖既有条目。与生产旧版比对同样只有 341 处 zh 差异。
- **验证**：注册表/呈现/相关 10 文件 321 passed；全量 **2890 passed + 6 skipped**（基线一致）。两处测试随覆盖状态更新（契约未放宽）：`test_no_fabricated_zh` 改为「不得空串/不得英文列名冒充 + 覆盖须 100%」；`test_build_factor_groups_zh_falls_back_to_none_for_unregistered` 改用未注册列验回退并补 `alpha001` 中文名断言。
- **真实浏览器**：本地 staging 8099 与生产（SSH 隧道 9090）各跑一遍——902/902 带 zh、三栏弹窗 Alpha191 因子列全中文、中文搜索命中（毛利率 13 / 十字星 1 / 五年盈利价格比 2 / 产权比率年度变化 2）、英文列名搜索仍可用、空态正常、零 JS error。证据 `.tmp/factor-zh-coverage/`。
- **发布（R-DEPLOY-001）**：备份 `/tmp/qre-factor-zh-pre-20261027/` → scp `configs/factor_registry.json` + `deploy/saas/metadata.json` → 仅重启 qre-saas（MainPID 491196），worker inactive 未触碰；两文件生产 SHA256 与本地相等。未跑真实回测、未 commit/push。建议提交 `feat(factors): 维护剩余 341 列中文显示名`。

## Task ID

QRE-FACTOR-DISPLAY-CONTRACT（因子别名与呈现属性统一协议）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-27；用户明确要求删除全量策略库批次任务，游戏明日再做）

## 目标与边界

1. **把呈现属性变成因子数据成员**：在现有 `configs/factor_registry.json` 与 `gui/factor_registry.py` 的单一语义来源上，为每个 canonical 固化 `chart_type=overlay|pane`、`panel_id`、`role`、`series_type=line|bar`、`axis`、`precision`、`color`、`price_basis`、`render_order` 与中文/英文显示名、别名。canonical 仍是数据库/YAML/回测唯一标识。
2. **禁止页面各自猜指标**：SaaS 因子弹窗、job/symbol 静态图、replay、NL 元数据全部读取同一 display 合同。`factor-layout.js` 只消费属性；启发式只能作为旧数据回退，不得覆盖显式注册属性。不得通过前端改列名解决展示问题。
3. **默认约束**：overlap 表与 EMA/BOLL/轨道系必须 overlay K 线；MACD/PPO/PVO 同参数 DIF+DEA+HIST 同副图；KDJ/STOCH 等家族同副图；RSI、风险、流动性、Alpha 默认独立副图。`panel_id` 含价格口径，避免同列不同口径互相覆盖。
4. **注册表生成与校验**：`scripts/gen_factor_registry.py` 生成完整 display 属性，所有真实列都有安全默认值；特殊族进入显式规则。校验 canonical/role/panel_id/series_type 合法、无冲突、无失效引用、所有列覆盖，不能伪造中文翻译。现有别名解析、common/core 和 341 列后续维护不受影响。
5. **验证**：EMA 永不落入独立 DIV，MACD 同面板、不同口径不串键；Node 布局回归 + 注册表全套 + 相关/全量测试 + 真实 Chromium 验证静态与重播。按 R-DEPLOY-001 备份后直接部署 ECS，仅重启 qre-saas；用户验收后才 commit/push。不跑真实回测，不推进游戏或其他任务。
6. **保护在途改动**：保留 Step 5 replay 与 DeepSeek Night Mode 的产品改动，不覆盖、不格式化、不提交它们；`game/` 和 `docs/agent/22_TRADING_GAME.md` 一律不碰。

## 实施结果（2026-10-27，Step 5 实现，Kimi 复核与部署收尾，待人工验收）

- **注册表**：`configs/factor_registry.json` 为每个 canonical 增加完整 display；`gui/factor_registry.py` 加载并校验合法枚举、panel_id 冲突、失效引用与全列覆盖；`gen_factor_registry.py` 可重现同一输出。
- **消费端**：`factor-layout.js` 优先显式 display，旧数据才启发式；`factor_wizard.py` 与 `deploy/saas/metadata.json` 携带合同；`lab_result._panel_display` 给 symbol 面板挂载；job/symbol/replay 与 Night Mode 保留既有语义。
- **验证**：专项与注册表 59 passed；全量 2890 passed + 6 skipped。真实 Chromium 以生产目录驱动 replay，EMA 主图、MACD 同副图、夜间切换、375 无横溢，证据 `.tmp/factor-display-contract/`。
- **发布**：Step 5 两次 2 小时超时后由 Kimi 完成验证部署；ECS 备份 `/tmp/qre-factor-display-pre-20261027/`，仅同步运行文件并重启 qre-saas；未跑真实回测、未 commit/push。建议提交 `feat(factors): 统一因子呈现属性与图表合同`。

## Task ID

QRE-SAAS-NIGHT-MODE（保留原色板，仅新增夜间模式）

## Created By

KIMI_CODE 规划，DeepSeek 实施（2026-10-27；用户否决全部浅色重装修候选，Kimi 复核）

## 目标与边界

1. **只新增夜间模式**：不得修改字体、字号、排版、间距、布局、组件形状、动效、文案或数据。唯一新增交互是主题切换按钮；盈亏继续红涨绿跌。
2. **浅色保持原样**：禁止全站色板重装修，现有浅色 token 与视觉完全保留；三个候选版全部作废，不进入生产。
3. **夜间定稿**：bg `#17153B`，card `#2E236C`，line `#433D8B`，text `#F1EDF8`，muted `#C8ACD6`，accent `#7E60BF`，accent-deep `#C8ACD6`，accent-soft `#2E236C`。正文/按钮/焦点态须满足对比度，红绿只提亮不改色相。
4. **主题机制**：首帧防 FOUC，localStorage 持久化，未选择时跟随 prefers-color-scheme；切换按钮有文字和 aria；meta theme-color 同步；375 不横溢。禁止把浅色卡片/按钮残留成“白色岛屿”。
5. **图表同色**：ECharts 背景、坐标轴、文字、tooltip、品牌紫系列随主题更新，保留红绿与数据。切换只改颜色，不重算数据/布局。覆盖 new/job/symbol/showcase/help/login/profile/feedback/factor-request/strategy/console/login_callback 等 SaaS 页面；8080/8081 非本任务页面不改。
6. **保护在途工作**：保留 Step 5 replay 全部未提交改动与 Kimi 游戏文件，不覆盖、不格式化、不提交它们。按 R-DEPLOY-001 先备份再部署 ECS，仅重启 qre-saas；用户验收后才 commit/push。不跑真实回测，不推进游戏、性能或其他挂起项。
7. **验证**：静态 token/无旧主紫残留检查、主题单测、相关与全量测试；真实 Chromium 验证浅/夜切换、reload 持久、系统偏好、375、主要页面和 9090。更新 04/05/08/09/10/11/12/14/16 与实施证据。

## 实施结果（2026-10-27，已部署待人工验收，未 commit/push）

- **交付**：7 个产品文件——新增 `src/quant_research_engine/gui/static/night-mode.css`、`night-mode.js`；`gui/static/replay.js` 加 `QRETheme.themeChart`；`gui/saas/templates/base.html`、`login_callback.html`、`job.html`、`symbol.html` 挂载点与标记。浅色 token、字体、排版、间距、布局、动效、文案、数据零改动；8080/8081 未改。
- **夜间色板（8 token）**：bg `#17153B`、card `#2E236C`、line `#433D8B`、text `#F1EDF8`、muted `#C8ACD6`、accent `#7E60BF`、accent-deep `#C8ACD6`、accent-soft `#2E236C`；红绿只提亮不改色相。`#guest-note` 告警色（`#B4761F`/`#3D3118`）刻意保留。
- **机制落地**：首帧内联防 FOUC；`<html data-theme>` 三态 + `localStorage('qre-theme')`；未选择跟随 `prefers-color-scheme`；meta theme-color 同步；按钮带文字与 aria；ECharts 全要素随主题改且不重算数据/布局。
- **边界 6 遵守情况**：Step 5 replay 未提交改动与 Kimi 游戏文件未覆盖、未格式化、未提交（`git diff HEAD` 中 base/job/symbol/replay.js 的夜间模式外改动均为此前在途内容）。
- **验证**：专项 24 passed；相关 6 文件 148 passed；全量 **2871 passed + 6 skipped**；浏览器审计 **138 ok / 0 FAILURES**；ECS 应用层 7 条 URL 全 200、7 文件 SHA256 与本地相等；**仅重启 qre-saas**（MainPID 487122），worker 未触碰。证据 `.tmp/night-mode/`、ECS 备份 `/tmp/qre-night-mode-pre-20261027/`。
- **未做**：未 commit/push、未跑真实回测；公网域名因 DNS/代理不可达，验证等价于应用层（`Host: www.aghuice.com` → `127.0.0.1:8090`）。

## Task ID

QRE-SAAS-REPLAY-BOUNDARIES（P2：重播边界核验与补强）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26；用户批准继续主线，挂起任务放最后，游戏等待用户后续意见）

## 目标与边界

1. **先核对现状，不重复造轮子**：`replay.js` 已有同日同类 >5 聚合展开；symbol 重播已优先 orders、round trips 兜底，并与静态图共用多因子布局。逐条用测试证明这些路径后，只修真实缺口，不把 backlog 当成未实现清单。
2. **同日聚合**：覆盖同日 >5 入场/出场混合、展开/收起、seek 回退与重播、重复初始化；事件数与标的口径一致，不出现重复行、未来事件或失效按钮。若有多笔同标的同日事件，聚合计数须明确按事件还是去重标的，保持与可见文案一致。
3. **orders 事件源**：symbol 验证 orders 真实价量优先、空 orders 才 round trips 兜底、缺失字段不造值；job 检查现有数据是否已含 orders，若无则仅利用现有 round trips 的 entry/exit_price/quantity 补足事件信息，不新增大 payload、不改 worker/引擎/schema。
4. **多因子副图**：验证 0/1/多因子、均线 overlay、MACD 同面板、chip 状态、动态 grid/height、重播接管与退出后静态重建一致；不得引入第二套 K 线模块。修复仅限已复现问题。
5. **验证与发布**：先补 Node/纯逻辑和模板回归，再跑相关套件与全量测试；真实 Chromium 验证上述边界、末帧=静态报告、1280/375 无 JS error/横溢。按 R-DEPLOY-001 备份后直接部署 ECS，仅同步实际改动文件并重启 qre-saas；用户验收后才 commit/push。不跑真实回测，不做性能/压测/移动端专项，不推进挂起项或游戏。

## 实施结果（2026-10-27，已部署待人工验收，未 commit/push）

- **改动文件**：`src/quant_research_engine/gui/static/replay.js`、`src/quant_research_engine/gui/saas/templates/symbol.html`、`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/lab_result.py`、`tests/test_saas_replay_boundaries.py`（新，7 例）。未改 schema/worker/引擎/API/配额。
- **现状核验（先证明再修）**：展开/收起、seek 回退（无未来事件/重复行）、重播重置、destroy→attach 重入、markPoints 无未来事件、symbol orders 优先 + round trips 兜底、多因子 overlay/MACD 同面板/chip 三态/动态 grid·height/接管退出——均已实现且完整，补回归锁定（factor-layout 用例首跑即绿、零改动）。
- **真实缺口 1（聚合计数口径）**：`popEvents` 头部按事件数计「只」——symbol 页 6 笔同日买单显示「当日入场 6 只」（实为 1 只 6 笔）。修复：新增 `aggHead` 按 `ev.sym` 去重计「只」，事件数 > 标的数时披露「（M 笔）」，明细列全部事件；`evChipText` 统一 chip 文案（qty/price 缺省不拼装）。
- **真实缺口 2（job 事件价量）**：chart_data round trips 点无价量，而 round_trips.csv 本就写入 quantity/entry_price/exit_price。修复：`_trade_points` 有列时补足（缺列不加键、不造值，仅对新 run 生效、不回填）；job.html 事件带 sym + 价量；symbol.html 事件改 sym/symbol/qty/price 字段（orders 优先、空 orders 才兜底）。旧产物自然降级为纯标的 chip。
- **测试**：TDD RED=5 failed → GREEN=7 passed（replay.js/factor-layout.js 真实文件 vm 加载 + 两个模板函数抽取 + _trade_points 三态）；相关 6 文件 188 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2863 passed + 6 skipped**（零回归）。证据 `.tmp/replay-boundaries/{red,green,full-tests}-evidence.txt`。
- **真实 Chromium**（临时库 + 8099 staging + seed/worker 协议模拟，未跑回测）：10/10 零 JS error 零横溢（1280 与 375）——job 聚合头「当日入场 5 只（6 笔）」+ 展开 6 笔价量明细 + 收起 + seek 回退 + 退出重建；symbol「当日入场 1 只（6 笔）」+ EMA5 overlay/MACD 面板 + 末帧已实现盈亏 478.00 与静态强一致 + 退出重建。证据 `.tmp/replay-boundaries/`（browser-evidence.json + 8 截图）。
- **ECS 发布**：四文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-replay-boundaries-pre-20261026/` → scp 四文件 → 仅重启 qre-saas（active；worker 在家未动）；无 schema 变更。公网（匿名 job58）：replay.js 新口径标记在位、进入/快进/末帧/退出全程零 JS error，旧数据降级纯标的 chip 不造值；9090 隧道 job58 200。证据 `production-verification.txt`。
- **遗留**：价量补足仅对新 run 生效（历史 job chip 为纯标的，符合不重放/不回填原则）；同标的同日多笔在 ≤5 时仍逐笔展示（chip 含量价可区分）；事件流无虚拟滚动（长任务事件量大时 DOM 行数多，属既有性能取舍，本轮不做性能专项）。

## Task ID

QRE-SAAS-NL-A1（自然语言输入前置校验与 DeepSeek 裁判评估）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26；用户批准继续主线，小游戏暂停；用户随后明确不配置 Jev，改用现有 DeepSeek）

## 目标与边界

1. **规则层先于缓存、限流和 LLM**：在 `POST /api/saas/nl/compile` 空输入检查后执行纯函数校验；拒绝乱码/纯数字/过短或明显缺少入场、出场语义的输入，返回具体缺失项与合法示例。规则必须覆盖中英文常见交易词与 MACD 金叉/死叉等既有经典输入，不得把指标别名误判成乱码。
2. **三级决策**：`pass` 进入既有 A2/A3；`reject` 返回 422 且不可强制绕过；`review` 返回 422、`code=nl_input_review` 与缺失/风险项，用户确认后以 JSON 布尔 `force=true` 重发，只有 review 可绕过。拒绝与确认均不得创建 job。
3. **DeepSeek 替代 Jev，复用现有 `QRE_NL_LLM_*`**：删除 Jev/TypeSafe 适配、配置与评估资产，不新增任何密钥或 SDK。使用 `gui.nl_compiler.call_llm` 注入独立裁判 system prompt，要求严格 JSON 三分类 strategy/not_strategy/unclear；容错解析失败、超时与 HTTP 错误时降级规则层，不伪装裁判成功，不记录策略文本或密钥。
4. **成本控制**：缓存命中直接返回，不调用裁判；缓存 miss 先在既有配额内计数，再调用 DeepSeek 裁判，通过后才调用编译，裁判拒绝也占一次配额，防止利用免费裁判刷 token。DB 故障回退路径同样先限流再裁判。force 只豁免 review，不绕过硬拒绝、缓存、配额或编译。
5. **隐私与 UI**：自然语言入口用既有 tip-trigger 说明文本会发送给 DeepSeek 用于校验与编译；不新增灰色小字。复用 new.html 的等待遮罩和模态，确认后原样重发；不改变编译 YAML、缓存 key、配额数值、worker、引擎和结果。
6. **小样本评估**：保留中文人工标注样本集，评估脚本改调现有 DeepSeek；自动测试全部 stub。真实评估只跑分层小样本（不超过 12 条），记录分类混淆、延迟和失败；不得伪造成本或准确率。规则全集可离线运行，DeepSeek 不跑全量 54 条。
7. **验证与发布**：TDD 先 RED 后 GREEN；覆盖 pass/reject/review/force、DeepSeek 故障矩阵、缓存命中零裁判、裁判占配额、A2/A3 不回归、两个 NL 页面入口。运行相关套件和全量测试；真实 Chromium 验证拒绝、确认继续、成功编译。按 R-DEPLOY-001 备份后直接部署 ECS；用户验收后才 commit/push。不跑真实回测，不推进游戏、移动端、压测或硬件。

## 实施结果（2026-10-26，用户验收通过，已部署并发布）

- **改动文件**：`src/quant_research_engine/gui/saas/nl_input_guard.py`（新）、`src/quant_research_engine/gui/saas/app.py`、`src/quant_research_engine/gui/saas/templates/new.html`、`src/quant_research_engine/gui/saas/templates/strategy.html`、`configs/nl_input_guard_samples.json`（新，54 条人工标注）、`scripts/nl_deepseek_eval.py`（新）、`tests/test_nl_input_guard.py`（新，67 例）；更新 3 处既有用例输入（`test_gui_saas_pages.py` NL 路由 3 例、`test_saas_nl_compile_cache.py` 13 处、`test_saas_public_beta_ops.py` 4 处——合成短描述按新行为改为经典合法描述）。未改 schema/引擎/worker/配额数值/YAML 编译/缓存 key。
- **规则层合同**（纯函数 `rule_check`，零 IO）：reject（422 `nl_input_rejected`，不可绕过）= strip 后 <6 字符 / 无中英文字符（纯数字符号）/ 纯数字 / 可识别字符占比 <60%（乱码）/ 无任何交易语义且 <16 字符；review（422 `nl_input_review`，可 force 绕过）= 缺少入场语义（missing=["entry"]）/ 缺少出场语义（missing=["exit"]）/ 无交易语义的长文本；pass=其余。词表覆盖中英文入场（买入/金叉/突破/buy/golden cross…）、出场（卖出/死叉/止损/sell/stop loss…）、指标（MACD/EMA/RSI/均线/布林/网格/股票…）。经典 MACD 金叉死叉、EMA 上穿买入下穿卖出、网格「买一格/卖一格」等均 pass（50 条人工标注样本 50/50 一致）。
- **DeepSeek 裁判合同**（第二道防线，非单点；用户 2026-10-26 明确不配置 Jev/TypeSafe，改用现有 `QRE_NL_LLM_*` 通道）：复用 `gui.nl_compiler.call_llm(description, config, system_prompt=REFEREE_SYSTEM_PROMPT, timeout=30)`，独立裁判 prompt 要求严格 JSON 三分类（strategy/not_strategy/unclear；无置信度输出、不伪造校准结论）；去 fenced block + 截取 JSON 对象容错解析；异常/结构错误 → `llm_error`/`bad_structure` 降级规则层。strategy → 维持规则层结论；not_strategy/unclear → 升级 review（不硬拒）。**不记录策略文本、不读取/打印密钥。**
- **端点编排**（`POST /api/saas/nl/compile`）：empty 检查后 → 规则层（`force=false` 走 evaluate_input；`force=true` 仍跑 rule_check 硬拒拦截——force 只豁免 review）→ 既有 prompt/缓存快路径/锁内复检 → 配额计数 → **DeepSeek 裁判（仅 cache miss + 配额计数后；管理员与会员同样经过裁判（无 admin 豁免）；force 已确认不再裁判）** → 通过才 compile_nl。裁判拒绝也占一次配额（防免费刷 token）；DB 故障回退路径同样先文件限流再裁判再编译（`_referee_gate` 小 helper 两条路径同源）。缓存命中零裁判；规则层不占配额、不写缓存。
- **前端**：new.html 新增 `#nl-review-modal`（缺失项 + 合法示例 + 返回修改/仍要编译），`doNlCompile(force)` 处理 `nl_input_review`（弹模态）与 `nl_input_rejected`（结果区展示原因+示例，无模态）；NL 入口 h3 增加隐私 tip-trigger（文本会发给已配置的校验/编译服务商）。strategy.html 重编译改 `sdRecompile(force)` + 行内确认区 `#sd-nl-review`。零新增灰色小字。
- **测试**（DeepSeek 方向重跑）：TDD RED=29 failed → GREEN；`tests/test_nl_input_guard.py` 67 passed（规则三态/领域语境/裁判 prompt 独立性与容错解析/故障降级/组合矩阵/reject 不可绕过/缓存命中零裁判/miss 裁判后才编译/裁判 review 占配额不编译/DB 回退路径同构/force 严格布尔/页面标记与无灰字）；`test_saas_nl_compile_cache.py` 与 `test_saas_public_beta_ops.py` 增加 autouse 裁判桩（不关心裁判的既有用例）；相关 6 文件 237 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2840 passed + 6 skipped**（基线 2833+6，+7 零回归）。证据 `.tmp/nl-input-guard/deepseek-{red,full-tests}.txt`。
- **评估**：`configs/nl_input_guard_samples.json` 54 条人工标注 + `scripts/nl_deepseek_eval.py`（替代并删除 nl_jev_eval.py）；规则层全集 **54/54 与标注一致**；**DeepSeek 裁判真实小样本已运行**（ECS 生产凭证、分层 ≤12 条：deepseek-flash、0 失败、延迟 533–1590ms；混淆矩阵 not_strategy 4/4、strategy 3/4（1 unclear→review 软行为）、boundary 2/4——boundary 在生产已被规则层拦截、裁判看不到）。证据 `.tmp/nl-input-guard/deepseek-eval.json`。
- **真实 Chromium**（临时库 + 8099 staging + stub LLM + worker 不启动，未跑回测）：5/5、零 JS error、零横向溢出——拒绝（原因+示例、无模态、YAML 不被改写）、review 模态→仍要编译→成功、直接成功、strategy 页重新编译 review→确认→已重新编译、375 不破版（含模态开启态）。证据 `.tmp/nl-input-guard/`（browser-evidence.json + 5 截图）。
- **ECS 发布**：按 R-DEPLOY-001 多级备份（最终 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/`）→ 同步 nl_input_guard.py、app.py、new.html、strategy.html → 仅重启 qre-saas（active；worker 在家未动）；无 schema 变更、未 apply。生产复用既有 DeepSeek 配置，未配置 Jev，未索取/输出任何密钥。
- **公网验证**（临时游客会话）：reject 422 `nl_input_rejected`（原因+4 示例）且 force 仍 422；review 422 `nl_input_review`（missing=["exit"]）；合法编译不回归——「MACD 金叉买入，死叉卖出」200 cache_hit=true（A2A3 缓存路径无损）、新合法描述 force 200 ok=true（真实 DeepSeek 编译一次）；jobs 表 10→10 未建任务；nl_compile_events 2→4（两条真实编译事件）；9090 隧道 `/saas/new` 与 `/saas/strategies/1` 200 且 A1 标记齐全；公网四页 200。
- **遗留**：裁判无置信度输出、不做阈值校准结论（unclear 走 review 软确认不阻挡）；裁判拦截量不计入 nl_compile_events（未来可加 guard 维度）；规则层为文本语义判断，不做语义可达性。

## 复核修正（2026-10-26，主 Agent 3 项 Required Fixes 已解决，重新部署待人工验收）

1. **领域语境门槛**：原规则只要同时含买/卖即 pass，非交易文本（买房/买菜/买机票）在无裁判的生产直接放行。新增 `DOMAIN_WORDS`（收盘价/开盘价/涨停/跌停/交易日/换手率/估值/基本面/涨跌幅/持仓/委托/行情…）与 `STRONG_TRADING_WORDS`（金叉/死叉/止损/做多/突破/止盈…），`_has_domain_context` = 领域词 ∪ 指标词 ∪ 强交易词；**有入出场词但无领域语境 → review（不得 pass）**。50 条合法样本零误杀（新增收盘价/连续涨跌/开盘价涨停/换手率/估值等 domain 用例）；`configs/nl_input_guard_samples.json` 增至 54 条（+4 对抗样本），规则层 54/54。
2. **UI**：strategy.html 重编译区增加与 new.html 同源的隐私/校验 tip-trigger；new.html review 模态补 `role="dialog"`/`aria-modal="true"`/`aria-labelledby`。
3. **force 严格布尔**：`data.get("force") is True`——字符串 "false"/"true" 均不视为确认（回归 `test_force_on_reject_still_blocked`）。
- TDD：RED=8 failed → GREEN；guard 60 passed；相关 6 文件 230 passed + 1 skipped；**全量 2833 passed + 6 skipped**（基线 2821+6 零回归）。Chromium 重跑 6/6（对抗样本 review 模态；`shot_stable` 几何稳定后截图，nl-review-modal-1280.png 不再截在透明过渡中）。ECS 备份 `/tmp/qre-nl-a1-review1-pre-20261026/` 后同步四文件仅重启 qre-saas；公网对抗文本 422 review、force 字符串 422、合法 MACD cache_hit=true 不回归。


## 复核修正（2026-10-26，主 Agent 2 个路径一致性 Required Fixes 已解决，重新部署待人工验收）

1. **删除 admin 裁判豁免**：原锁内路径 `if not is_admin and not force` 让管理员绕过 DeepSeek 裁判——未经用户要求的新权限差异、任务书未定义。修正：管理员仍**不限编译配额**，但与会员一样经过裁判（`if not force`）；同步删除注释、测试（`test_admin_skips_referee` → `test_admin_also_refereed`：admin 裁判拒绝 → 422 review、连续拒绝不限流、force 后可编译）与文档中的管理员特例。
2. **DB 回退路径 force 语义一致**：原 `except SQLAlchemyError` 回退路径无条件调用 `_referee_gate()`，导致 `force=true` 用户在 DB 故障时又被裁判拦回，与正常路径不一致。修正：仅 `not force` 时裁判；规则硬拒仍在最前不可绕过。回归：DB 故障 + force=true → 跳过裁判进入编译；DB 故障 + 裁判拒绝 → 422 不编译；DB 故障 + force + 乱码 → 422 reject。
- TDD：RED=2 failed → GREEN；guard 67 passed；相关 6 文件 237 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2840 passed + 6 skipped**（零回归）。真实 Chromium 复跑 7/7 零 JS error 零横溢。ECS 备份 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/`（app.py）后同步并仅重启 qre-saas；公网最小复核：合法 MACD 缓存命中 200（零裁判零配额，配额 5→5）、乱码 + force 仍 422、公网三页与 9090 隧道 200、jobs/cache 不变。裁判 prompt 未变，未重复真实 12 条评估。
## Task ID

QRE-SAAS-PUBLIC-BETA-OPS（P1：公测运营反馈闭环与关键浏览器自动化）

## Created By

KIMI_CODE（2026-10-26；依据 `14_LAUNCH_ROADMAP.md` §11.3 条目 4「运营反馈闭环」）

## 目标与边界

1. **9090 管理台新增「公测运营」tab（GET /api/saas/console/ops，admin 门禁不变）**，指标全部来自权威库/执行路径，明确时间窗口、分母与空数据口径，不编造历史：
   - NL 编译：成功率、缓存命中率、热门失败原因。新增最小隐私安全事件表 `nl_compile_events`（ok/cache_hit/error_class/scope/created_at；**不存策略文本、API key、原始 IP**）；**自本功能上线起统计**，上线前显示「—」。
   - 回测（kind='full'，smoke 内部试算不计入）：成功率、平均排队时长（started_at−created_at）、平均执行时长（finished_at−started_at）、热门失败原因（error_class 分组）。jobs 表有全量历史，窗口 今日/近7天/近30天/累计 均为真实值。
   - 游客到注册转化：游客独立会话数（jobs.guest_key 去重，**仅统计提交过任务的游客，未提交访客不可见——口径明示**）与当日/窗口新增注册（users.created_at）两个**独立计数**。二者无跨会话关联：**不计算转化率**（ratio=null + measurement=unlinked；未关联总量的比可超过 100%，是误导），未来做真实转化须先建会话关联记录，本切片只做诚实降级、不扩展用户追踪 schema。
   - 空数据口径：分母为 0 时比率返回 null，前端显示「—」。时间窗口 today 按 **Asia/Shanghai 自然日**（A 股运营口径；UTC 零点会漏当日凌晨 8 小时），7d/30d/all 为滚动窗口/不限。
2. **意见反馈分类与处理状态闭环（最小可用，不建工单系统）**：`feedback` 新增 `category`（bug/experience/factor/other，默认 other，提交端 allowlist 校验）与 `status`（open/doing/done/closed，默认 open）。提交页加类型选择、本人列表透出类型/状态；管理台反馈 tab 支持按类型/状态筛选与状态流转（POST /api/saas/console/feedback/<id>/status，仅 admin，非法状态 400、不存在 404）。保留既有用户隔离、每日 20 条上限、管理员鉴权。
3. **关键浏览器自动化**：可重复执行资产落 `deploy/saas/public-beta-audit/`（seed.py + browser_audit.py + run_audit.sh，复用 `.tmp/browser-venv` Playwright 与 `.tmp/ms-playwright` Chromium；Playwright 仅测试工具，不进生产依赖）。场景覆盖：游客/登录、新建页、NL 编译 stub、任务等待/失败恢复、结果只读与权限、反馈分类、管理台运营指标；桌面 1280 与 375 只验证不破版；不启动真实 worker、不跑真实回测，任务状态经 seed/worker 协议模拟。
4. **Schema 由 postgres 幂等 apply**（`nl_compile_events` 建表 + feedback 两列 DO 块；ECS 表 owner 是 postgres，应用层懒自愈只兜底本地/测试库）；发布仅同步 app.py、console.html、feedback.html、cloud_schema.sql 并重启 qre-saas，不重启 worker。
5. TDD 先 RED 后 GREEN：新 `tests/test_saas_public_beta_ops.py`；相关套件 + 全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` 必须通过。证据落 `.tmp/public-beta-ops/`。
6. 遵守 R-UI-001（无灰色小字备注，解释用 tip-trigger+data-tip+LabUI.helpTips）、R-ADMIN-001（运营指标展示与执行/库同源）、R-DEPLOY-001（先部署后验收再提交）。

## 验证

- 单测：事件记录（成功/失败/缓存命中/scope、无文本无 IP）、ops 窗口与比率/排队/失败分组/转化口径与空数据 null、反馈分类 allowlist 与状态流转权限矩阵、页面标记（ops tab、反馈筛选与状态列、feedback.html 分类控件）。
- 真实 Chromium（临时 PG + 8099 staging + stub LLM + worker 协议模拟）：上述 7 类场景零 JS error、零横向溢出（1280 与 375）。
- ECS：备份 → postgres apply schema → scp 四文件 → 仅重启 qre-saas → 9090 隧道验证 ops API/tab 与反馈流转；公网临时数据彻底清理，不输出凭证。保留「已部署待用户验收，未 commit/push」。

## 实施结果（2026-10-26，用户验收通过，已部署并发布）

- **改动文件**：`src/quant_research_engine/gui/saas/ops_support.py`（新）、`src/quant_research_engine/gui/saas/app.py`、`src/quant_research_engine/gui/saas/templates/console.html`、`src/quant_research_engine/gui/saas/templates/feedback.html`、`deploy/saas/cloud_schema.sql`、`deploy/saas/public-beta-audit/{seed.py,browser_audit.py,run_audit.sh}`（新）、`tests/test_saas_public_beta_ops.py`（新）。未改引擎/worker/数值/配额/NL A2A3 语义。
- **TDD**：RED=17 errors（对 HEAD 基线 stash 实现）；GREEN=17 passed；相关 5 文件 227 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2770 passed + 6 skipped**（基线 2753+6 零回归）。证据 `.tmp/public-beta-ops/{red,green,full-tests}-evidence.txt`。
- **真实 Chromium**（临时库 + 8099 staging + stub LLM + worker 协议模拟，未启动真实 worker/回测）：9/9、零 JS error、零横溢；`browser-evidence.json` + 11 截图（含 375 两张）。
- **生产缺陷热修**：`feedback_id_seq` 缺 USAGE → 登录用户提交反馈 500（feedback 特性此前从未部署 ECS，首次上线暴露；同 share_links 序列坑）。生产 GRANT USAGE, SELECT；schema 增加角色存在时幂等 DO 块（含序列存在性检查）。
- **发布**：ECS 四文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-public-beta-ops-pre-20261026/` → scp 五文件 → postgres 幂等 apply → 仅重启 qre-saas（active，worker 在家未动）。生产 ops 鉴权三态、空口径诚实（编译前 nl.total=0/first_event_at=None）、反馈闭环、游客真实 DeepSeek 编译两次 cache_hit false→true（A2A3 无回归）、ops all 窗口 nl.total=2/first_event_at=2026-10-26；临时数据清理（temp_users=0/feedback=0）；9090 隧道 console 200 含 ops 标记、ops API 无 token 401；公网 /saas/、login、new、feedback、help 200，/saas/console 仍 404。证据 `production-verification.txt`。
- **遗留**：NL 指标自功能上线起统计（上线前无历史，不回填）；游客访客口径仅覆盖提交过任务的独立会话；转化率不计算（需会话关联）；反馈状态无备注字段；`nl_compile_events` 无自动清理（仅索引）。

## 复核修正（2026-10-26，主 Agent 2 项 Required Fixes 已解决，重新部署待人工验收）

1. **转化比率误导**：`compute_ops` 不再计算 new_users/guest_sessions 之比（生产实测「注册 / 游客 300.0%」）；返回 `ratio=None` + `measurement="unlinked"`；console 卡改「转化率 —」，保留两个真实计数；未扩展用户追踪 schema。回归 `test_conversion_ratio_never_computed`。
2. **今日边界**：`window_start('today')` 改上海当日零点（`_now_shanghai()` + `ZoneInfo("Asia/Shanghai")`，转 UTC 比较）；7d/30d/all 不变。回归 `test_today_start_is_shanghai_midnight` + DB 级 `test_today_window_includes_shanghai_early_morning`。
- TDD：RED=4 failed → GREEN；ops 测试 20 passed；相关 3 文件 135 passed；**全量 2772 passed + 6 skipped**（1 例已知 flake 复跑通过）。Chromium 重跑 9/9 零 JS error 零横溢（console-ops-1280/375 确认无伪转化率）。ECS 备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/` 后仅同步 ops_support.py + console.html 并重启 qre-saas（无 schema 变更）。

## Archive: TRADING-GAME-V1-CORE（《我不是股神》纯交易状态机首切片）

## Created By

KIMI_CODE（2026-10-26，长期设计 `docs/agent/22_TRADING_GAME.md` 已获用户批准）

## 目标与边界

1. 新建独立、纯 Python 的 `game` 交易核心，不依赖 SaaS/前端，支持初始资金、限价委托、未成交、T+1、100 股、0.01、现金/持仓/总权益和结束判定。
2. 直接复用 `core.models.Order/Bar/Fill/OrderSide` 与 `markets.ashare.AShareMarketProfile` 的费率、成本和市场规则，不复制费率常量。
3. 每股票同一时间只允许一个 pending 委托；触及委托价成交且滑点为 0，一字涨停禁买、一字跌停禁卖，未触及不成交，重复委托/重复结算拒绝。
4. 先 TDD，再实现；本切片不做 UI、数据库、随机抽样、公网中继或全量回测。后续切片再接匿名逐日数据与页面。

## 验证

覆盖触及/未触及、跳空、一字板、T+1、整数手、价格边界、资金/持仓不足、刷新/重复结算幂等、费用勾稽、总权益结束条件。只做小样本单元测试，不跑真实回测。

## Archive: QRE-SAAS-NL-A2A3（持久限频与版本化编译缓存）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26，批准计划 `mister-terrific-echo-vision.md`）

## 目标与边界

1. `nl_rate_limits` 用 PostgreSQL 原子计数替代游客文件计数；游客仍每日 10 次且 403/code 不变，会员每日次数不限但 6 次/分钟防突发（超限 429），admin 不限。
2. `nl_compile_cache` 以规范化描述 + model/base_url + 完整 prompt 哈希 + 编译缓存版本生成 key；同 key advisory lock 防并发重复调用。只缓存 ok=true 结果，命中不调用 LLM、不占配额，失败不缓存。
3. 不改 `gui/nl_compiler.py` 的编译/纠错/YAML 校验，不运行真实回测，不公开缓存、不存 API key、不新增灰色小字备注。生产先 postgres apply schema 再发代码。
4. 新支撑模块 `gui/saas/nl_compile_support.py` + app.py 编排 + schema + `tests/test_saas_nl_compile_cache.py`；TDD 先 RED 后 GREEN，覆盖缓存命中/版本失效/并发/限流持久化/恢复窗口/admin/失败不缓存。
5. **R-ADMIN-001（用户补充）**：9090 总览必须展示 NL 真实生效权限（游客每日 10、会员每分钟 6、admin 不限）与缓存/限流计数，值直接来自执行常量与两张表，不复制第二套配置；完成可视化与公网核验后才允许 commit/push。

## 发布规则

遵循 R-DEPLOY-001：备份 `/tmp/qre-nl-a2a3-pre-20261026/`，直接部署并仅重启 qre-saas；用临时 session 对生产 MACD 描述纯编译两次，第二次 cache_hit=true 且 YAML 一致，不创建回测。更新 04/05/09/10/11/14/16/17，保留「已部署待人工验收，未 commit/push」。验收通过后才提交；不通过立即回滚。建议提交 `feat(saas): 增加持久编译限流与策略缓存`。

## Archive: QRE-SAAS-CLASSIC-ACTIONS-UI（经典策略按钮与结果操作卡精修）

## Created By

KIMI_CODE 规划，Step 5 实施（2026-10-26，批准计划 `amadeus-cho-cannonball-cyborg.md`）

## 目标与边界

1. 经典策略页删除灰色长文/弱链接与重复提示，底部改为「复现经典策略」+「新建同款策略」主按钮，页头说明移入既有问号提示；策略 subtitle 保留。
2. job 将 `#box-actions` 与 `#box-share` 合并进 `#result-actions-card`，保存=主按钮、信号/分享=次按钮；保留全部现有 ID、权限、事件绑定和 API。新增空安全 `syncResultActionCard()`，任一组可见才显示外层。
3. 改动区域禁止 `.opt`、muted/faint 段落或灰色小字备注；解释统一 `tip-trigger + data-tip + LabUI.helpTips`。按钮至少 44px 高，375px 不横溢。
4. 不改 API/schema/引擎/worker/数值/权限，不跑真实回测；TDD 先 RED 后 GREEN，临时 PG + Chromium 模拟任务验收。

## 发布规则

遵循 R-DEPLOY-001：测试后核对基线并备份 `/tmp/qre-classic-actions-pre-20261026/`，直接同步 `showcase.html`、`job.html`、`lab-theme.css` 到 ECS 并仅重启 qre-saas；公网验证后保留「已部署待人工验收，未 commit/push」。用户通过后才提交；不通过立即回滚。更新 04/05/09/10/11/14/16 与必要的 12 号 UI 文档。

## 实施结果（2026-10-26，已部署待人工验收，未 commit/push）

- **改动文件**：`src/quant_research_engine/gui/saas/templates/showcase.html`、`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/static/lab-theme.css`、`tests/test_saas_classic_actions_ui.py`（新）、`tests/test_saas_access_hardening.py`（3 处更新）、`tests/test_gui_saas_pages.py`（1 处 marker）。未改 API/schema/引擎/worker/数值/权限。
- **TDD**：RED=新测试 11 失败 + access_hardening 2 失败；GREEN=新 12 passed、access_hardening 66 passed、相关 10 文件 289 passed、全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → **2701 passed + 5 skipped**（基线 2689+5 零回归）。证据 `.tmp/classic-actions-ui/red-evidence.txt`、`green-evidence.txt`、`full-tests.txt`。
- **真实 Chromium**（临时库 `qre_readonly_share_browser` + 8099 staging，worker 协议模拟 completed，未跑真实回测）：9/9、零 JS error、零横溢；`browser-evidence.json` + 7 截图（showcase/job/signal-panel/guest/readonly 桌面 1280 + showcase/job 375）。
- **发布**：ECS 三文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-classic-actions-pre-20261026/` → scp 三文件 → 仅重启 qre-saas。公网：showcase/job58/`/static/lab-theme.css` 200 且新标记齐全、删除标记为零、CSS SHA256 与本地一致；`/saas/`、help、login、new、symbols 两页 200。证据 `public-verification.txt`。
- **遗留**：`syncResultActionCard` 只在 init 两个入口同步；若未来新增第三种操作组需同步纳入数组。游客/只读整体隐藏已由 Node 矩阵 + 真实浏览器双重覆盖。

## Archive: QRE-SAAS-UI-DECLUTTER-001（结果页口径展示与说明页导航精简）

## Created By

KIMI_CODE 直接实施（2026-10-26，用户明确指定三项 UI 删减）

## 目标与边界

1. job/showcase/个人回测记录三处不显示结果合同、验证徽标、合同版本与新旧口径；`result_contract` 继续留在 API 和系统内部，showcase verified 公开门槛不得放宽。
2. 删除 job/symbol 各模块的 `/saas/help#...` 说明链接，保留既有悬停提示；`renderContract` 只驱动曲线口径提示。
3. `/saas/help` 顶部跳转为桌面 sticky 侧边栏目，卡片标题 20px；窄屏无横溢。帮助页不再展示验证状态或新旧口径。
4. 仅改模板、`lab-theme.css` 与测试；不改 API/schema/引擎/worker/数值/权限，不跑真实回测。

## 验证

TDD 先 RED 后 GREEN；相关套件 + 全量测试；真实 Chromium 检查 job/symbol/showcase/profile/help 桌面与 help 375 的标签消失、侧边布局、字体、锚点、零 JS error 与零横向溢出。证据 `.tmp/ui-declutter/`。不自动 commit/push/ECS。

## Archive: QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-26，用户批准计划 superman-hellcat-crystal）

## 目标

让登录用户把自己的已完成回测结果分享给他人只读查看，同时保持默认私有、链接可撤销、可设有效期、明文令牌只显示一次：

1. **最小 schema**：`share_links`（token_hash 唯一 / job_id ON DELETE CASCADE / owner_id / expires_at / revoked_at / created_at + 两个索引）；不要 token 明文/前缀、guest_key、last_used_at。应用层按现有 information_schema + 进程 guard 懒自愈建表；生产发布前必须由 postgres 幂等 apply `cloud_schema.sql`，避免表 owner/权限问题。
2. **令牌生命周期**：`secrets.token_urlsafe(32)`；库中只存完整 SHA-256(token + 现有 salt) 哈希；明文仅出现在创建响应。创建 URL `/saas/jobs/<job_id>?share=<token>`；校验只允许未撤销、未过期且 job_id 一致的记录。
3. **所有者管理 API**：创建（登录+本人+completed；游客 401、他人/不存在 404、未完成 409；有效期只接受 1/7/30/0 天，默认 7，服务端算 expires_at）；列表（仅本人最近 50 条，状态 active/expired/revoked，不回 hash/token）；撤销（仅创建者，重复/他人/不存在统一 404，立即失效）。
4. **公开只读通道**：`_require_completed_result` 在有效 `?share=` 时按 token 对应 job 放行只读（readonly_kind=share），不依赖登录或游客会话；无效/过期/撤销/错 job 不降级授权（匿名 401、登录他人 404，错误体与既有语义一致，不泄露任务或链接状态）。范围仅现有结果 GET；不开放 jobs/results 列表、用户策略 API 或 worker/console；generate 对 showcase 和 share 都 403；其余写端点仍只认原归属。
5. **未验证与 showcase 边界**：未验证历史结果允许所有者主动分享，合同徽标「旧口径·未验证」必须保留；showcase 仍只允许 verified；游客不能创建分享。
6. **UI**：job 页登录+completed+非公开只读显示「分享结果」（自定义模态选有效期、成功后代只读 input + 复制、明确只显示一次、不写 localStorage）；profile「我的分享」列表与撤销二次确认；分享视图 chip「只读分享」+ 中性返回文案，与 showcase 区分；隐藏取消/保存/信号/重跑/游客引导。

## 实施边界

- 不改回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3、策略库、默认私有语义；不跑真实回测；不做压测/性能/硬件；不做移动/App 专项（仅保持 375 不破版）；不 commit/push/部署 ECS。
- 游客每日清理 jobs 逻辑不改（CASCADE 自动清理孤儿分享）；showcase verified 门与 P0-2 游客隔离语义零变化。
- 复用既有自定义模态/淡紫组件与 Clipboard API，不新增依赖、不新增长篇灰字。

## Validation

- TDD 先 RED 后 GREEN：重点扩展 `tests/test_saas_access_hardening.py`（fixture 清理纳入 share_links），覆盖创建准入/存储形态/全端点绑定/过期/撤销/写保护/CASCADE/未验证/showcase 不变 + 前端 Node harness（job 分享流、只读文案分流、profile 列表与撤销、token 传播、localStorage 零痕迹）；`tests/test_gui_saas_pages.py` 三个既有 Node harness 补 shareUrl/shareSuffix/initShareButton 透传桩。
- 相关 22 个文件 655 passed；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2687 passed + 5 skipped，基线 2651+5，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/worker 协议模拟，不启动真实 worker/回测）：登录创建复制→匿名只读渲染→异 job/过期/撤销拒绝→profile 撤销二次确认；URL 不写 localStorage；零 JS error、零横向溢出；证据 `.tmp/readonly-share/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；凭证扫描命中项均为 token 字段名/测试 dummy，人工核对无真实凭证；更新 04/05/06/08/09/10/11/14/16/17/19。

## Archive: QRE-SAAS-RESULT-UNDERSTANDING（P1 第二切片：结果理解、集中帮助与数据/费用口径）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准计划 wonder-woman-medusa-psylocke）

## 目标

让普通用户能看懂回测结果，而不在结果页堆叠长备注：新增公开、集中的「使用说明」页，从结果页各模块精准跳转；同时补齐交易费用、数据截止和 VaR/ES 的关键口径。只整理和展示现有数据。

1. 新增 `GET /saas/help`（游客与登录用户均可访问，继承 base，不新增 API 或数据库表）：按 `#contract`/`#metrics`/`#benchmark`/`#fees`/`#risk`/`#attribution`/`#replay` 锚点分节，内容简明可扫描；合同口径文案由路由传入 `DAILY_RETURN_BASIS`/`TOTAL_RETURN_BASIS`（result_contract 常量同源，不复制权威口径）。主导航加入精简「使用说明」入口，沿用现有 active 状态和移动样式，不增加侧边悬浮按钮。
2. job/symbol 各模块标题区加入小型「说明 →」链接（合同/收益曲线/交易磨损/FRM/归因分别跳对应锚点；个股摘要数据截止跳 `#contract`）；job 收益曲线 tip 在 `renderContract(c)` 时用合同口径更新，无合同时保留静态回退；主指标仍保持 6 张，盈亏比只在帮助页与重播解释。
3. 五张交易磨损卡增加卡级提示（佣金/卖出印花税/过户费及其他残差含滑点/总磨损/磨损占买入成交额合计；毛收益=未扣费、净收益=扣除费用）；job 费率 chip 增加默认/自定义配置提示；`bench-bar` 增加基准含义提示；重播指标为盈亏比、持仓暴露度、当前持仓增加统一提示。全部复用 `LabUI.helpTips`，桌面重复 hover、键盘 focus、移动 tap 可用，不新增常驻灰字。
4. symbol worker gzip 与本地 fallback 两条返回路径都注入 `data_until`（不改 gzip 产物、不回填）；头部 `#sym-note` 显示数据截止并链接 `#contract`，缺字段显示「未声明」；VaR/ES UI 与 job/风险报告统一为损失正数，仅改显示符号，不改风险原值与计算。

## 实施边界

- 不改 schema、收益/风险/费用数值、回测引擎、worker 执行逻辑、配额、NL A2/A3；不运行真实回测；不做性能/容量/硬件/云迁移；不 commit/push/部署 ECS。
- 不新增主指标卡（第 7 张）、不重算指标、不改 `risk` 原值；帮助页不写营销文案、不堆灰字、不引入第四色相或新 JS 框架。
- 保留 P0 权限语义（默认私有、游客会话归属、showcase verified 公开只读）与结果合同语义（verified/unverified 分类、两种收益口径权威文案）。

## Validation

- TDD 先 RED 后 GREEN：`tests/test_saas_result_help.py`（新，17 例）+ `test_saas_help_copy.py`（+2）+ `test_saas_symbol_ux.py`（+2 API）+ `test_gui_saas_pages.py`（+1 Node harness）；P0-2/P0-1B 既有用例全保留。
- 相关套件 502 passed；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2651 passed + 5 skipped，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/worker 协议模拟，不跑真实回测）：帮助页锚点导航、模块深链、连续 hover/focus/tap、symbol data_until 与 VaR/ES 正号、1280/375 零 JS error 零横溢；证据 `.tmp/result-understanding/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；更新 04/05/08/09/10/11/14/16/17。

## Archive: QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片：回测等待状态、worker 离线提示与失败恢复）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准计划 big-barda-red-tornado-ghost-rider）

## 目标

在不跑真实回测、不做压测/性能/硬件、不改数据库 schema 的前提下，把已有但未被公网使用的队列位置、worker 心跳和取消能力接到用户界面：

1. 统一任务运行态响应：`GET /api/saas/jobs/<id>` 与 `/api/results/<id>/summary` 的 409 共用一套只读口径（queue_position 仅 queued、worker_online 布尔）；409 增补 strategy_id/error_class/error_message/cancel_requested，failed 返回真实失败原因；不泄露 worker 细节。
2. new.html 准确表达等待：排队位置/离线提示/已等待时间进 wait-mask；单次 15s AbortError 继续轮询；HTTP 500/终态 fail-fast；80 轮上限是独立 PollTimeoutError（不冒充策略失败、不自动提交全量）；createJob 15s 提交超时。
3. job.html 队列/离线/取消/失败恢复：活跃任务取消（自定义模态二次确认，复用 P0-2 游客会话归属）；failed/expired 展示真实 error_message；登录用户可「按原策略重新回测」跳 `/saas/new?strategy=<id>`，游客仅返回新建页；showcase 只读零取消入口。
4. 可访问性与移动：wait-mask 状态文本 aria-live=polite，秒数行纯视觉；375px 无横溢、按钮 44px；不改设计 token/8080/18080。

## 实施边界

- 不改 schema、回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3；不启动真实 worker、不跑真实回测（浏览器任务全部 seed/worker 协议端点模拟）；不做压测/性能/硬件；不 commit/push/部署 ECS。
- 游客取消必须复用 P0-2 `qre_guest_sid`/guest_key 归属：同会话成功、异会话 401、缺失会话不得看到或取消旧任务；登录用户他人 404；匿名/他人/不存在语义不泄露存在性。

## Validation

- TDD 先 RED 后 GREEN：`tests/test_saas_first_success_ux.py`（21 例）+ `tests/test_gui_saas_wait_mask.py`（3 例）+ `tests/test_gui_saas_pages.py` 新增 25 例 Node harness；旧 fail-fast 用例的 body-pending 预期改为「超时后继续轮询」。
- 相关套件 + 全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q`（2627 passed + 5 skipped，零回归）。
- 真实 Chromium（临时 PG + 8099 staging + seed/协议模拟）：queued N/离线/running/failed 恢复、游客同会话取消与异会话 401、登录用户取消与原策略重跑回填、15s 临时超时重试恢复、桌面 1280 与移动 375，证据 `.tmp/first-success-ux/`。
- `scripts/check-progress-docs.sh`、`scripts/git-finalize-check.sh`、`git diff --check` 通过；更新 04/05/08/09/10/11/14/17。

## Archive: QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Task ID

QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Created By

KIMI_CODE 布置，Step 5 实施（2026-10-25，用户批准按统一 Todo 推进）

## 目标

1. 核查 ECS `SAAS_TEST_ACCOUNT_EMAIL/PASSWORD` 是否存在，只报告存在性，不输出凭证。若存在，备份 `/etc/qre-saas.env` 后移除/注释并重启验证正式 Authing/账号登录不受影响。
2. 枚举全部面向用户的 job/result/symbol GET 端点，补齐匿名与其他用户的 IDOR 测试：不得泄露任务存在性，统一既有 401/404 语义；showcase verified 公开行为不变。
3. 新游客结果从“纯 IP 归属”改为随机、HttpOnly、SameSite=Lax 的游客会话 Cookie 归属，防止同 Wi-Fi 互见。Cookie 缺失时由应用自动签发，密钥只用现有 salt，不明文存敏感信息。
4. 旧游客结果允许在原 guest_key 匹配时迁移一次到新随机会话；迁移后旧 key 不再作为新任务归属。明确历史同 IP 风险只限旧数据，新会话彼此隔离。
5. 默认私有、Authing、worker token、结果合同和 showcase verified 语义不变；主动分享留 P1，不做。

## 实施边界

- 使用现有请求/响应和用户鉴权链路，保持最小改动；数据库如需迁移必须幂等、可回滚。
- 不运行真实全量回测，不删除历史任务，不输出或提交任何凭证，不 commit/push/部署，待主 Agent 与用户验收。

## Validation

- 枚举端点清单与测试一一对应；匿名/其他用户/本人/不存在/公开白名单各分支通过。
- 两个独立游客会话结果互不可见；旧结果迁移一次后属新会话，其他会话不得访问；新游客任务不依赖 IP。
- ECS 测试账号只读检查与必要的安全配置修改有备份和正式登录验证。
- 相关与全量测试，真实 Chromium 双游客上下文与移动检查，证据 `.tmp/access-hardening/`。
- 更新 04/05/06/09/10/11/14/16/17/19（如涉及权限）和最终检查；不 commit/push/ECS 代码部署。
