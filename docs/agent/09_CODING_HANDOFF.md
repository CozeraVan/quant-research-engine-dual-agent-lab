# Coding Handoff

## Task ID

QRE-DATA-CLEANUP-EXECUTION（用户批准的遗留数据清理与分钟 CSV 只读检查）

## Release Status

DONE（2026-10-27）。四库和指定旧回测产物已删除，留档在 `/home/van/quant-workspace/backups/local-cleanup-20261027/`。活跃目录与两个待验收 staging 库保留；`qre-outputs` 27G→536M，磁盘可用 386G→418G，8080/8092 HTTP 200。8081 staging 重用前需重建/替换 aguhuice_local。三份新分钟 CSV 仅只读检查，等待 17:20 timer 自动入库；未清洗、未压缩、未手动入库。M10.4 依赖环境已存在，无重复安装。未 commit/push。

## 历史盘点摘要（只读阶段）

**三项高风险（待用户决定，均未动手）**：

1. **`public.stock_daily_qfq_legacy` 已不存在**。全库所有 schema `ilike '%legacy%' or ilike '%qfq%'` → 0 条；本地无 `tushare_data` dump（`~/quant-workspace/backups/ecs-aguhuice/` 只有 ECS aguhuice SaaS 库 dump）⇒ 2026-10-12 方案A（qfq → 原始价+adj_factor）的**回滚能力已永久失去且不可恢复**。新口径自 10-12 生产生效、因子已全历史重算，但该选项不再存在。
2. **分钟线压缩缺口 140 GB**。`stock_minute_1m` 922 chunk：708 已压缩 = **396 MB**，214 未压缩 = **140 GB**（压缩比约 350:1）。其中 **213 个 `range_end` 早于 T-7 仍未压缩**，覆盖 2022-09-01 → 2026-10-08（2022:18/11G、2023:52/33G、2024:52/34G、2025:51/35G、2026:40/27G），违反 20 §3.4 规则。`minute_compress.log` 称 10-11 已压 707 个，但未压缩 chunk 内部 ID（2022-09-01 = `_hyper_67_56121_chunk`）高于已压缩集合（`_hyper_67_45526` 等）⇒ 那些 chunk 是压缩后新建、再未压。重跑 `quant_ts/compress_minute_chunks.sh`（幂等，已跑通过一次）预计回收 ~139 GB。
3. **分钟线落后日线 10 天**：`stock_minute_1m` 最新 2026-10-16 vs `stock_daily` 2026-10-26。`minute-csv-ingest.timer` 自 10-18 起每天「扫描到 CSV 0 个」⇒ 用户未再拷新 CSV。需确认暂停还是漏拷。

**「已入库」≠「可安全删除」核查结论**：`/home/van/mindata` **已空**（0 文件 / 24 KB / 仅剩 `mindata/` 与 `mindata/2026/` 两个空目录 inode）。日志只记录 5 个 CSV（20261012–1016，2026-10-18 17:06）走过「先校验 `rows_csv==rows_db` 再删除」；`import_minute_csv.py` **无任何 unlink/remove/rmtree 代码** ⇒ 4308 个历史 CSV 属脚本外删除（`mindata/` mtime 2026-10-11 23:19 晚于审计最后写入 20:10，顺序对但无轨迹）。数据侧已验证完整：审计 4318 条全部 `rows_csv==rows_db`（0 不一致）、审计日期与表日期双向差集均 0、抽查 8 个日期（含磁盘打满失败的 2022-08-22/25/29）`rows_db` vs 实时行数 **8/8 MATCH**。**源 CSV 不可恢复，今后发现缺口只能回原始数据商重新下载。**

**可删候选（待确认，未动）**：`aguhuice_test`(7.5MB,0 表)、`quant_hub`(10MB,0 public 表)、`aguhuice_local`(8.9MB,3 users/15 jobs,9-27→10-05)；`qre-outputs/refresh/incremental` 17G(8-02)、`gui-console/runs` 5.4G(8-20)、`backtests` 4.3G(8-18)、`gui-run` 442M(9-13) 及约 20 个 7 月 `*_check` 目录。任务书提到的 `qre_saas`/`dbg` **均不存在**。

**勿动**：`refresh/registry.json`/`state.json`/`delta/`（KB 级活配置，`gui/refresh_registry.py` 引用，绝不能随 17G 一起删）；`saas_uploads`（今日仍在写）、`market_risk`(10-26)、`video_packages`(10-24)；`.tmp/ms-playwright` 681M + `.tmp/browser-venv` 142M（浏览器审计工具链）；两个上一任务 staging 库（各自任务验收后再删）。

**高风险单项**：`akshare_data` 5.8GB——`stock_ticks` 36,147,932 行 / 2026-04-07→04-24 / 10 分区；`AK_DB_URL` 仅 `quant_ts/config.py` 定义、全仓无消费者。

**备份缺口**：本地无 `tushare_data` 逻辑备份，513GB 主库只有磁盘+TimescaleDB 自身保护。

## Verification（全部只读实跑）

```sql
-- 审计一致性：0 行
select trade_date, rows_csv, rows_db from public.stock_minute_1m_audit where rows_csv is distinct from rows_db;
-- 审计 vs 实际表双向差集：各 0 行
select trade_date from public.stock_minute_1m_audit except select distinct trade_date from public.stock_minute_1m;
select distinct trade_date from public.stock_minute_1m except select trade_date from public.stock_minute_1m_audit;
-- 单日实时行数比对（含磁盘打满重试日期）：8/8 MATCH
select count(*) from public.stock_minute_1m where trade_date='2022-08-25';  -- 1180224 = 审计 rows_db
-- 压缩缺口：213 | 140 GB
select count(*), pg_size_pretty(sum(pg_relation_size(format('%I.%I',chunk_schema,chunk_name))::bigint))
from timescaledb_information.chunks
where hypertable_name='stock_minute_1m' and not is_compressed and range_end < (now()-interval '7 days');
-- 压缩 vs 未压缩总量：708 chunks=396MB / 214 chunks=140GB
select is_compressed, count(*), pg_size_pretty(sum(pg_relation_size(format('%I.%I',chunk_schema,chunk_name))::bigint))
from timescaledb_information.chunks where hypertable_name='stock_minute_1m' group by 1;
-- 遗留表搜索：0 行
select table_schema||'.'||table_name from information_schema.tables where table_name ilike '%legacy%' or table_name ilike '%qfq%';
-- 审计完成时间（对比 mindata mtime）：2026-10-11 20:10:20 vs mindata mtime 2026-10-11 23:19:18
select max(done_at) from public.stock_minute_1m_audit where done_at::date='2026-10-11';
```
辅助命令：`du -sh /home/van/mindata`（24K）、`find /home/van/mindata -type f | wc -l`（0）、
`journalctl -u minute-csv-ingest.service`（10-18 起每天「扫描到 CSV 0 个」）、
`systemctl status minute-csv-ingest.timer`（enabled/active，Mon–Fri 17:20，`Persistent=true`）、
`stat -c '%n %y' /home/van/mindata /home/van/mindata/2026`、`df -h /`（1007G/570G used/386G avail, 60%）。

**测试**：无代码改动，无需回归；`scripts/check-progress-docs.sh` 通过。

## Next Step（等用户逐项确认后再立项，本轮不做）

见 04 号文档「待用户确认清单」7 项与 20 号文档 §7.3。任何清理动作执行前必须：①用户明确确认该项；②对库操作先 `pg_dump` 或至少记录表结构+行数；③对文件操作先 `du`+`find` 留档；④分钟线压缩属例行运维，可直接跑但建议仍先知会用户。

# Coding Handoff

## Task ID

QRE-ECS-SSH-HARDENING（root SSH 与部署发布纪律加固）

## Release Status

已生效待人工验收，未 commit/push（2026-10-27）。生产变更：`/etc/ssh/sshd_config.d/99-qre-hardening.conf`（新）+ `99-aguhuice-hardening.conf` 一行（`PermitRootLogin prohibit-password` → `no`）+ `/etc/sudoers.d/90-qre-deploy`（新）+ `/etc/sudoers.d/deploy` 权限 0644 → 0440。**无 schema 变更、未重启 worker、未跑真实回测。** root 直连已拒，deploy+sudo 为唯一入口。

## Implementation Summary

- **审计（改 SSH 前，顺序未倒置）**：deploy 密钥登录 uid=1000（公钥指纹 `SHA256:ghZ0NGRMwpXkAk6CrAnmDILAxRYhJ3lhLCUntkLPooE` 与本机一致）；`sudo -n` → uid=0；`/srv/aguhuice/qre/configs/factor_registry.json` 与 `deploy/saas/metadata.json` 可读；`/tmp → sudo -n install → sudo -n rm` 部署链干跑成功；deploy 自建隧道 9091 → `/saas/new` 200、`/api/saas/factors` 902/902 带 zh。既有会话全程未断。
- **审计抓出的锁死风险**：`passwd -S deploy` = `L`（密码锁定），`/etc/sudoers.d/deploy` 只放通 `/usr/bin/systemctl` 与 `/usr/bin/docker`——`sudo -n` 当时实际不可用。直接禁 root 会同时失去装文件、PG 备份恢复、证书、防火墙能力。修法：新增 `/etc/sudoers.d/90-qre-deploy` = `deploy ALL=(ALL:ALL) NOPASSWD: ALL`（0440 root:root，`visudo -c` 全绿）；顺带修 `sudoers.d/deploy` 0640→0440（原 0644 被 `visudo -c` 报 bad permissions）。
- **`/etc/ssh/sshd_config.d/99-qre-hardening.conf`（新，实际内容）**：
  ```
  # QRE-ECS-SSH-HARDENING（2026-10-27）
  # 独立加固 drop-in：禁 root 直连、禁密码与键盘交互认证、仅公钥登录。
  # AllowTcpForwarding 保持可用——9090 SaaS 管理台经 SSH 隧道访问（admin-tunnel.sh），
  # 关闭会直接把管理台变成不可达。
  # 其他 sshd 项一律不动。回滚：删除本文件后 `systemctl reload ssh`（不断会话）。
  PermitRootLogin no
  PasswordAuthentication no
  KbdInteractiveAuthentication no
  PubkeyAuthentication yes
  AllowTcpForwarding yes
  ```
- **为什么必须改 `99-aguhuice-hardening.conf` 一行**：sshd 对同一关键字取**先出现者**，`Include /etc/ssh/sshd_config.d/*.conf` 按字典序展开，`99-aguhuice-hardening.conf` < `99-qre-hardening.conf`。实测：只留新文件 → `permitrootlogin no`；两文件并存 → 回退 `without-password`。故该文件 `PermitRootLogin prohibit-password` → `no`，另两行（`PasswordAuthentication no`/`PubkeyAuthentication yes`）原样未动。
- **生效流程**：`sshd -t` 通过 → `systemctl reload ssh`（非 restart，既有会话/隧道不断）。`sshd -T` 复核：`permitrootlogin no`/`passwordauthentication no`/`kbdinteractiveauthentication no`/`pubkeyauthentication yes`/`permitemptypasswords no`/`allowtcpforwarding yes`。
- **`deploy/saas/deploy-ecs.sh`（新，0755）**：deploy+sudo 唯一部署入口。拒绝绝对路径 → 本地按仓库相对路径解析 → scp 到 `/tmp/qre-deploy-<STAMP>/`（先按相对路径远程 `mkdir -p`，scp 不自建嵌套目录）→ 生成远程脚本 `sudo -n bash` 执行：`mkdir -p` 业务/备份目录 → 已存在文件先 `cp -a` 到 `/tmp/qre-deploy-<STAMP>.bak/` → `install -o deploy -g deploy -m 0644` → `rm -rf` 临时目录 → `sudo -n systemctl restart qre-saas`（仅此单位）→ `systemctl is-active` + `curl` 应用层校验。带 `--dry-run`。两个已修真 bug：①scp 远程嵌套目录；②内联 `bash -c` 字符串二次转义（改为远程脚本文件 + 路径本地展开写死）。
- **`deploy/saas/admin-tunnel.sh`**：`HOST` 默认 `root@` → `deploy@47.119.127.40`，注释说明 root 已禁、TCP 转发为此保留。**`deploy/saas/pull-ecs-backup.sh`**：`HOST` 默认同样改 `deploy@`（`/srv/aguhuice/backups` 为 0644，deploy 可读，已实测能 `head` 最新 dump）。**`scripts/sync_saas_metadata.py`**：用法注释的 `scp ... root@...` 改为指向 `./deploy/saas/deploy-ecs.sh` 并注明禁 root。

## Verification

- **root 拒绝**：`ssh root@47.119.127.40` → `Permission denied (publickey)`。
- **deploy 全通**：新连接 uid=1000；`sudo -n id -un` = root；`sudo -n systemctl is-active` qre-saas=active / qre-worker=inactive / nginx=active / ssh=active；业务文件可读；`sudo -n fail2ban-client status sshd` 正常（Currently banned 0 / Total banned 1）。
- **9090 隧道保留**：`sshd -T` `allowtcpforwarding yes`；reload 后既有 root 隧道仍 200；deploy 新建 9092 → `/saas/new` 200(103937B)、`/saas/console` 200；`admin-tunnel.sh`（deploy@）起 9090 → 同两项 200。陈旧 root 隧道已停，现网无 root 会话（`ps` 确认隧道进程为 `deploy@`）。
- **deploy-ecs.sh 真实端到端**：用与生产 SHA256 相同的 `deploy/saas/metadata.json`（`29045e2485…`）实跑 → scp/installed/active/MainPID 493988/api 200//saas/new 200 四步全过，跑完生产 SHA256 仍 `29045e2485…`（字节未变）。dry-run、`--dry-run` 两文件、拒绝绝对路径（rc=2）均验证。
- **测试**：无 `src/` 改动、无测试引用这三个脚本；`bash -n` 三脚本全过；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2890 passed + 6 skipped**（基线一致，零回归）。
- **备份/回滚**：`/tmp/qre-ssh-hardening-pre-20261027/`（`etc/ssh/sshd_config`、`etc/ssh/sshd_config.d/99-aguhuice-hardening.conf`、`etc/sudoers.d/deploy` 原样副本）。回滚：`sudo rm /etc/ssh/sshd_config.d/99-qre-hardening.conf` + 把 `99-aguhuice-hardening.conf` 的 `PermitRootLogin` 改回 `prohibit-password` → `sudo systemctl reload ssh`；`sudo rm /etc/sudoers.d/90-qre-deploy`。两步均不断业务。云控制台 VNC 救援见 `16_ECS_DEPLOYMENT.md` §6。

# Coding Handoff

## Task ID

QRE-FACTOR-ZH-COVERAGE（剩余 341 列中文显示名维护）

## Release Status

已部署待人工验收，未 commit/push（2026-10-27）。ECS 仅重启 qre-saas（新 MainPID 491196），未重启 worker、未跑真实回测、无 schema 变更。

## Implementation Summary

- `scripts/gen_factor_registry.py`：新增三个模块级字典 `ALPHA191_ZH`(191) / `ALPHA101_ZH`(31) / `FINANCIAL_ZH`(119，含 quality 87 + growth 16 + `_pit_financial_panel` 14 + candle 1 + value 1) 与 `_coverage_zh(table, column)`；在 `build_registry()` 的 `if manual.get("zh"): entry["zh"] = manual["zh"]` 之后以 `elif not entry["zh"]:` 挂载——**只补空、不改名**。未改 FAMILY_RULES / MANUAL_ENTRIES / EXTRA_ALIASES / 别名生成 / common / core / display 任何逻辑。
- 命名依据：alpha191 逐条对照 `indicators_tushare/alpha191/formulas.py` 的 191 个 docstring（GTJA191 编号口径，DolphinDB 实现口径与 errata 注释一并核对）；alpha101 逐条对照官方 486 文档表达式表（`change_requests/factor_specs_p4p5p7.md` §三）；quality/growth 逐条对照 `panel_factors/quality.py::compute_all`、`panel_factors/growth.py` results 与 `change_requests/factor_specs_p1p3.md` §三/§四；`_pit_financial_panel` 按 `panel_factors/pit_panel.py` FAMILIES（inc/bs/cf/fi）+ Tushare 标准字段语义；`cdl_doji_10_0_1` = `factors/candle_factors.py` 的 ta.cdl_doji。
- `_rank` 列统一「·排名」后缀（同名计算项的截面排名，双列并存）；三处口径注记见 04/21 号文档（`gpm_q`、`ar_ap_to_revenue`、`npm_tsh`）。
- 重新生成 `configs/factor_registry.json` 与 `deploy/saas/metadata.json`（`.venv/bin/python scripts/gen_factor_registry.py --out configs/factor_registry.json --snapshot configs/factor_catalog_llm.json`，再 `QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data .venv/bin/python scripts/sync_saas_metadata.py --out deploy/saas/metadata.json`）。生成器自校验通过（无失效 canonical / 悬空别名 / display 告警），覆盖报告 895/895、未维护 0 列。

## Verification

- 注册表/呈现/相关 10 文件（`test_factor_registry`、`test_factor_display_contract`、`test_gui_factor_wizard`、`test_gui_lab_result`、`test_saas_factor_picker`、`test_gui_saas_pages`、`test_nl_factor_pipeline`、`test_gui_nl_compiler`、`test_saas_replay_boundaries`、`test_saas_night_mode`）：**321 passed**。
- 全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → **2890 passed + 6 skipped**（与基线一致，零回归）。
- 零漂移：重新生成前后逐字段比对，除 zh 外 **0 处差异**；341 条 null→中文名，0 条覆盖既有条目。与生产旧版（554 zh）比对同样只有 341 处 zh 差异，display 合同未回归。
- 两处测试随覆盖状态更新（契约未放宽）：`tests/test_factor_display_contract.py::test_no_fabricated_zh` 由「应有 null 列」改为「不得空串 / 不得英文列名冒充 + 覆盖须 100%」；`tests/test_gui_factor_wizard.py::test_build_factor_groups_zh_falls_back_to_none_for_unregistered` 改用未注册列 `alpha999_unregistered` 验回退，并补断言 `alpha001` 已带中文名。
- 真实 Chromium（本地 staging 8099 + 生产 SSH 隧道 9090 各一遍）：`/api/saas/factors` 902/902 带 zh 且无英文列名冒充；`/saas/new` → 自选因子交易 → 因子弹窗三栏逐级进「Alpha191 量价因子」，因子列 30 条全中文名；中文搜索命中（毛利率 13 / 十字星 1 / 五年盈利价格比 2 / 产权比率年度变化 2）；英文列名搜索仍可用；无匹配走空态；零 JS error。脚本与截图 `.tmp/factor-zh-coverage/`。
- ECS：备份 `/tmp/qre-factor-zh-pre-20261027/`（configs/factor_registry.json + deploy/saas/metadata.json）→ scp 两文件 → 仅重启 qre-saas；两文件生产 SHA256 与本地逐一相等。应用层验证（ECS 上 `curl -H "Host: www.aguhuice.com" http://127.0.0.1:8090/...`）：`/api/saas/factors` 902/902 带 zh，`/saas/new`、`/saas/`、`/saas/help`、`/saas/login` 均 200。未跑真实回测、未 commit/push。

## Task ID

QRE-SAAS-NIGHT-MODE（保留原色板，仅新增夜间模式）

## Release Status

已部署待人工验收，未 commit/push（2026-10-27）。ECS 仅重启 qre-saas（MainPID 487122），未重启 worker、未跑真实回测、无 schema 变更。

## Implementation Summary

- `gui/static/night-mode.css`（新，270 行）：`html[data-theme="dark"]` 下 8 个夜间 token（bg `#17153B`／card `#2E236C`／line `#433D8B`／text `#F1EDF8`／muted `#C8ACD6`／accent `#7E60BF`／accent-deep `#C8ACD6`／accent-soft `#2E236C`）+ 组件映射（卡片、表格、表单、按钮、开关、模态、tooltip、滚动条、焦点环）；浅色部分不新增覆盖规则，`#guest-note` 告警色保留。
- `gui/static/night-mode.js`（新，275 行）：`QRETheme` 三态解析（`localStorage('qre-theme')` → `prefers-color-scheme`）、切换按钮状态与 aria、meta theme-color 同步、系统偏好变更监听、`themeChart(chart)` 递归改写 ECharts option 的背景/坐标轴/文字/tooltip/系列边界色与品牌紫，保留红涨绿跌配色与全部数据。
- `gui/static/replay.js`：图表 option 组装后调用 `QRETheme.themeChart`（无 `QRETheme` 时安全跳过），不改重播逻辑。
- `gui/saas/templates/base.html`：`<head>` 内 meta theme-color、首帧内联防闪脚本、`night-mode.css`/`night-mode.js` 引入，顶栏主题按钮（文字 + aria）。
- `gui/saas/templates/login_callback.html`：独立页补 meta、内联防闪脚本、深色 `:root` 兜底样式、css/js 引入，主题按钮用 `tt-btn tt-float` 浮动变体。
- `gui/saas/templates/job.html`、`symbol.html`：图表创建后调用 `QRETheme.themeChart`（与 Step 5 在途改动分层，仅追加主题挂钩）。
- `tests/test_saas_night_mode.py`（新，24 例）：token 集与无旧主紫残留、模板标记计数、三态解析与 localStorage、themeChart 不改数据、按钮 a11y、375 无横溢相关静态断言。

## Verification

- 专项 `tests/test_saas_night_mode.py`：24 passed；相关 6 文件 148 passed；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → **2871 passed + 6 skipped**（与基线一致，零回归）。
- 浏览器审计（真实 Chromium，`.tmp/browser-venv`）：`138 ok / 0 FAILURES`，exit 0；覆盖 12+ 页面 × 浅/夜 × 1280/1000/375、点击切换、reload 持久、系统偏好、无白底卡片/白按钮、正文与按钮焦点对比度、375 不横溢；截图与 `audit.log` 在 `.tmp/night-mode/`。
- 两次判据修正（工具层，非产品放宽）：①`<details>` 关闭时 `content-visibility:hidden` 使 `getBoundingClientRect` 非零并读到过期浅色值（login 4 项失败全在折叠区）→ 先展开再断言；②job `tagChart` 是 treemap 无笛卡尔轴 → 仅对含笛卡尔系序列断言轴色，浅色轴色取 ECharts 默认 `#6E7079`。
- ECS：5 文件与生产基线 diff 仅夜间模式行 → 备份 `/tmp/qre-night-mode-pre-20261027/` → scp 7 文件（SHA256 与本地逐一相等）→ 仅重启 qre-saas；应用层 7 条 URL 全 200（见 `04_TASK_HANDOFF.md` 实施结果），`/saas/console` 68285B 主题标记齐全。
- 未验证项：`www.aghuice.com` 真域名 TLS 路径（本机与 ECS 均无 DNS，本地代理对该域名 `SSL_ERROR_SYSCALL`），故验证止于 ECS 本地 `Host` 头 8090 应用层；TLS/nginx 未改动。

## Task ID

QRE-SAAS-REPLAY-BOUNDARIES（P2：重播边界核验与补强）

## Release Status

已部署待人工验收，未 commit/push（2026-10-27）。ECS 仅重启 qre-saas；未重启 worker、未跑真实回测、无 schema 变更。

## Implementation Summary

- `gui/static/replay.js`：`popEvents` 增加 `evChipText`（chip 文案统一：symbol + qty 股@price + pnl，缺字段不拼装）与 `aggHead`（按 `ev.sym` 去重计「只」；事件数 > 标的数时披露「（M 笔）」；明细展开列全部事件）。阈值触发仍按事件数 >5（视觉密度）。
- `gui/saas/templates/symbol.html`：`mountKlineReplay` 事件结构改 `sym/symbol/qty/price`（orders 优先、空 orders 才 round trips 兜底；缺字段不下发）。
- `gui/saas/templates/job.html`：`mountReplay` 事件带 `sym` 与 round trips 价量（旧产物缺字段则不下发）。
- `gui/lab_result.py`：`_trade_points` 在 CSV 有 quantity/entry_price/exit_price 列时补足到散点（`_f` 解析；缺列不加键；仅新 run 生效）。
- `tests/test_saas_replay_boundaries.py`（新，7 例）：replay.js/factor-layout.js 真实文件 vm 加载 + 模板函数抽取 + _trade_points 三态。

## Verification

- TDD：RED=5 failed → GREEN=7 passed；相关 6 文件 188 passed；全量 **2863 passed + 6 skipped**。证据 `.tmp/replay-boundaries/{red,green,full-tests}-evidence.txt`。
- 真实 Chromium（临时库 + 8099 staging + seed/worker 协议模拟）：10/10、零 JS error、零横溢（1280 与 375）。证据 `.tmp/replay-boundaries/`（browser-evidence.json + 8 截图）。
- ECS：备份 `/tmp/qre-replay-boundaries-pre-20261026/` → scp 四文件 → 仅重启 qre-saas；公网匿名 job58 重播全程零 JS error。证据 `production-verification.txt`。

## Task ID

QRE-SAAS-NL-A1（自然语言输入前置校验与 DeepSeek 裁判评估）

## Release Status

RELEASED（2026-10-26 用户验收通过，已部署 ECS，本次 commit/push）。ECS 仅重启 qre-saas；未重启 worker、未跑真实回测；无 schema 变更。

## Implementation Summary

- `src/quant_research_engine/gui/saas/nl_input_guard.py`（新）：规则层 `rule_check`（纯函数三态 + 中文缺失项/合法示例）；Jev 客户端 `jev_config/build_jev/jev_classify`（官方 systemone、Bearer、Choice input_kind、四种故障降级）；`evaluate_input` 组合决策（规则硬拒短路 Jev；Jev 只升级 review 不硬拒；阈值随 JevConfig）。
- `src/quant_research_engine/gui/saas/app.py`：`POST /api/saas/nl/compile` 在 empty 后插入 guard——`force=false` 走 evaluate_input；`force=true` 仍跑 rule_check 硬拒拦截（只豁免 review）；reject/review 均 422 带 reasons/missing/examples。
- `src/quant_research_engine/gui/saas/templates/new.html`：`#nl-review-modal` + `doNlCompile(force)`；reject 结果区展示；NL 入口隐私 tip-trigger。
- `src/quant_research_engine/gui/saas/templates/strategy.html`：`sdRecompile(force)` + `#sd-nl-review` 行内确认区。
- `configs/nl_input_guard_samples.json`（新，50 条标注）+ `scripts/nl_jev_eval.py`（新，离线评估；Jev 仅在有凭证时真实运行）。
- `tests/test_nl_input_guard.py`（新，48 例）；既有 3 个测试文件的合成输入更新为经典合法描述。

## Verification

- TDD：RED=collection error → GREEN=48 passed；相关 6 文件 265 passed + 1 skipped；全量 **2821 passed + 6 skipped**（基线 2773+6 零回归）。证据 `.tmp/nl-input-guard/{red,full-tests}-evidence.txt`。
- 离线评估：规则层 50/50；Jev not_run_missing_credentials（无凭证，未伪造）。证据 `.tmp/nl-input-guard/jev-eval.json`。
- 真实 Chromium（临时库 + 8099 staging + stub LLM + worker 不启动）：5/5、零 JS error、零横溢（1280 与 375）。证据 `.tmp/nl-input-guard/`（browser-evidence.json + 5 截图）。
- ECS：备份 `/tmp/qre-nl-a1-pre-20261026/` → scp 四文件 → 仅重启 qre-saas；公网 reject/review/force/合法编译（cache_hit 与真实编译）全部符合合同，jobs 10→10，nl_compile_events 2→4；9090 隧道两页 200。证据 `.tmp/nl-input-guard/production-verification.txt`。

## 复核修正（2026-10-26，主 Agent 3 项 Required Fixes 已解决）

- `nl_input_guard.py`：新增 `DOMAIN_WORDS`/`STRONG_TRADING_WORDS` 与 `_has_domain_context`——有入出场词但无领域语境 → review（不得 pass）；对抗样本（买房/买菜/买机票/买水果）与 domain 用例（收盘价/涨跌/开盘价/涨停/换手率/估值）入测试与 `configs/nl_input_guard_samples.json`（54 条，规则层 54/54）。
- `app.py`：`force = data.get("force") is True`（字符串不视为确认）。
- `strategy.html`：sd-src-nl 区增加隐私/校验 tip-trigger（与 new.html 同源）。
- `new.html`：review 模态补 role=dialog/aria-modal/aria-labelledby=nl-review-title。
- 验证：TDD RED=8→GREEN；guard 60 passed；相关 6 文件 230 passed + 1 skipped；全量 **2833 passed + 6 skipped**；Chromium 6/6（截图改 `shot_stable` 几何稳定后拍摄）。ECS 备份 `/tmp/qre-nl-a1-review1-pre-20261026/` 后同步四文件仅重启 qre-saas；公网复核通过。

## DeepSeek 方向落地（2026-10-26，用户明确暂不配置 Jev）

- `nl_input_guard.py`：删除 Jev/TypeSafe 客户端、环境变量与 requests 依赖；新增 `REFEREE_SYSTEM_PROMPT`（独立裁判 prompt，严格 JSON 三分类）、`build_referee(config)`、`referee_classify(description, config, *, call_llm_fn=None)`（复用 `nl_compiler.call_llm`，`_parse_referee_label` 去 fenced block + 截取 JSON 对象 + 三分类校验；异常→llm_error、结构错→bad_structure，均降级）；`evaluate_input(description, referee=None)` 语义不变（裁判只升级 review 不硬拒）。
- `app.py`：`_referee_gate()` 小 helper（config None/故障 → 放行；not_strategy/unclear → 422 `nl_input_review` + DeepSeek 原因）；锁内路径「配额后 + `not is_admin and not force`」调用；DB 故障回退路径「文件限流后」调用同一 helper（两路同源不漂移）。
- `new.html`/`strategy.html`：隐私 tip 改为 DeepSeek 措辞。
- `scripts/nl_deepseek_eval.py`（替代已删除的 nl_jev_eval.py）：规则层全集离线；裁判分层 ≤12 条真实调用，记录混淆/延迟/失败。
- 验证：TDD RED=29→GREEN；guard 67 passed；相关 6 文件 237 passed + 1 skipped；全量 **2840 passed + 6 skipped**；Chromium 7/7（新增裁判 review 场景）。ECS 备份 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 后同步四文件仅重启 qre-saas；公网计数证据 jobs 10→10 / cache 3→4 / events 5→7 / guest 配额 3→5。

## 路径一致性复核修正（2026-10-26，2 项 Required Fixes）

- `app.py`：锁内裁判门 `if not is_admin and not force` → `if not force`（删除 admin 豁免：管理员不限配额，但与会员一样经过 DeepSeek 裁判）；DB 故障回退路径 `_referee_gate()` 外包 `if not force:`（force 用户在回退路径跳过裁判，与正常路径一致；规则硬拒仍在最前不可绕过）。
- 测试：`test_admin_skips_referee` → `test_admin_also_refereed`（admin 裁判拒绝 422、连续拒绝不限流、force 后可编译）；`test_db_fallback_still_referees` 增加 force 跳过裁判/乱码硬拒两断言。
- 验证：TDD RED=2→GREEN；guard 67 passed；相关 6 文件 237 passed + 1 skipped；全量 **2840 passed + 6 skipped**；Chromium 7/7。ECS 备份 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/` 后同步 app.py 仅重启 qre-saas；公网最小复核（MACD 缓存命中零裁判零配额、乱码+force 仍 422）通过。

## Task ID

QRE-SAAS-PUBLIC-BETA-OPS（P1：公测运营反馈闭环与关键浏览器自动化）

## Release Status

RELEASED（2026-10-26 用户验收通过，已部署 ECS，本次 commit/push）。ECS 仅重启 qre-saas；未重启 worker、未跑真实回测。

## Implementation Summary

- `src/quant_research_engine/gui/saas/ops_support.py`（新）：反馈分类/状态 allowlist 与窗口定义（单一权威）；`ensure_ops_tables`（nl_compile_events 建表 + feedback 两列，information_schema 先查，失败降级 False）；`record_nl_event_on/record_nl_event`（同连接/独立短事务，尽力而降）；`compute_ops`（窗口内 NL/回测/转化/反馈聚合，比率分母为 0 返回 None，不估算）。**复核修正**：`window_start` today 按 Asia/Shanghai 自然日（`_now_shanghai()` + zoneinfo）；conversion 只回两个独立计数（ratio=None + measurement=unlinked，不计算未关联总量的比）。
- `src/quant_research_engine/gui/saas/app.py`：NL 编译四终态事件记录（超限不计入、scope 由提前判定的 is_admin 同源给出、ops_ready 门防锁事务毒化）；反馈创建/列表/console 筛选的分类与状态；`POST /api/saas/console/feedback/<id>/status`；`GET /api/saas/console/ops`。
- `src/quant_research_engine/gui/saas/templates/console.html`：「公测运营」tab（窗口切换 + 四区指标 + 两张失败原因表 + tip 口径说明）；反馈 tab 类型/状态筛选、类型/状态列、状态流转按钮；≤768px tab 折行（375 不破版）。
- `src/quant_research_engine/gui/saas/templates/feedback.html`：提交类型选择；历史表类型/状态列。
- `deploy/saas/cloud_schema.sql`：nl_compile_events + feedback 两列 + feedback_id_seq 幂等授权。
- `deploy/saas/public-beta-audit/`（新，可重复执行资产）：seed.py / browser_audit.py / run_audit.sh。
- `tests/test_saas_public_beta_ops.py`（新，20 例：17 例首版 + 3 例复核修正回归）。

## Verification

- TDD：RED=17 errors（HEAD 基线）；GREEN=17 passed；相关 5 文件 227 passed + 1 skipped；全量 2770 passed + 6 skipped（基线 2753+6 零回归）。证据 `.tmp/public-beta-ops/{red,green,full-tests}-evidence.txt`。
- **复核修正（主 Agent 2 项 Required Fixes）**：TDD RED=4 failed（转化比率 ×2 + 上海日界 ×2）→ GREEN；ops 测试 20 passed；相关 3 文件 135 passed；全量 **2772 passed + 6 skipped**（1 例已知 flake `test_gui_risk_report.py::test_post_starts_job_and_poll` 首跑偶发失败，单独与全文件复跑 passed）。证据 `.tmp/public-beta-ops/review1-{red,audit-run,full-tests}.txt`。
- 真实 Chromium（临时库 + 8099 staging + stub LLM + worker 协议模拟，未启动真实 worker/回测）：9/9、零 JS error、零横溢（1280 与 375）；复核后重跑 9/9，`console-ops-1280.png` 与 `console-ops-375.png` 确认「转化率 —」、无 300% 伪比率、tab 折行正常。证据 `.tmp/public-beta-ops/`（browser-evidence.json + 11 截图 + audit-run.txt）。
- ECS：整任务回滚点 `/tmp/qre-public-beta-ops-pre-20261026/`；本轮修改前备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/`；仅同步 ops_support.py + console.html（无 schema 变更）并重启 qre-saas；生产 API/隧道/公页验证与临时数据清理见 `.tmp/public-beta-ops/production-verification.txt`。

## Task ID

TRADING-GAME-V1-CORE（《我不是股神》WSL 可玩 Demo 首切片）

## Release Status

WSL 可玩 Demo 已跑通，未部署 ECS、未 commit/push（2026-10-26）。专项 22 passed，全量 2753 passed + 6 skipped；真实 Chromium 开盘买入通过，证据 `.tmp/trading-game/`。

## Implementation Summary

- `game/engine.py`：纯订单/成交/现金/持仓/费用状态机，复用 core.models 与 AShareMarketProfile。
- `game/session.py`：随机窗口与匿名 session，开盘/收盘两阶段，open 先行、完整 K 线收盘后可见；订单/权益代理。
- `game/data.py`：原始价+adj_factor 前复权、候选抽样、因子按日对齐；Timestamp 标准化和逻辑列名归一；ema_250 替代库内不存在的 ema_200。
- `game/web.py`：内存 session 注册与创建/推进/下单/收盘/结果 API，owner Cookie 隔离，匿名响应不含真实 symbol/date/未来数据。
- `game/templates/game.html`：淡紫 K 线/成交量/指标/交易/账户/记录；下单与收盘防竞速。
- 测试：专项 22 passed、全量 2753 passed + 6 skipped；真实 DB 抽样、真实 Chromium 开盘买入、1280/375 无横溢/无 JS error。未部署 ECS、未做公网中继、未 commit/push。

## Current Release

RELEASED（2026-10-26 用户验收通过，QRE-SAAS-NL-A2A3 含管理台同步，已 commit/push + ECS）：持久限频与版本化编译缓存 + 9090 管理台「自然语言编译」卡发布。发布前复核全量 2753 passed + 6 skipped；公网两次纯编译 cache_hit false→true、YAML 一致、未创建回测，overview nl 字段与执行常量/两表计数一致。以下保留各任务实施记录。

## Task ID

QRE-SAAS-NL-A2A3（持久限频与版本化编译缓存 + 管理台同步）

## Release Status

RELEASED（2026-10-26 用户验收通过，已 commit/push + ECS）。发布前复核全量 2753 passed + 6 skipped；生产 postgres apply 两表 + aguhuice CRUD 授权核实，app.py/console.html SHA256 与本地一致，仅重启 qre-saas。

## Implementation Summary

- **Schema（deploy/saas/cloud_schema.sql）**：新增 `nl_rate_limits`（scope TEXT / subject_hash TEXT / window_start TIMESTAMPTZ / hits INT DEFAULT 0 / updated_at，PK (scope, subject_hash, window_start)）与 `nl_compile_cache`（cache_key PK / description / result JSONB / model / prompt_hash / cache_version / created_at / last_hit_at / hit_count，+ idx_nl_compile_cache_last_hit）。两表无序列；DO 块在 `aguhuice` 角色存在时幂等 GRANT 两表 SELECT/INSERT/UPDATE/DELETE，本地无角色跳过（share_links 同款模式）。应用层 `ensure_nl_tables` information_schema + 进程 guard 懒自愈（仅兜底本地/测试库，生产以 postgres apply 为准）。
- **新模块 src/quant_research_engine/gui/saas/nl_compile_support.py**：`normalize_description`（NFKC + trim + 连续空白折叠）、`normalize_base_url`、`build_cache_key(description, model, base_url, prompt, cache_version)`（SHA256 覆盖五项）、`prompt_fingerprint`、`NL_COMPILER_CACHE_VERSION="2026-10-26.1"`、窗口助手（guest_daily=date.today()；member_minute=当前 UTC 分钟 + reset_seconds）、`guest_subject_hash`（复用 _guest_key）/`member_subject_hash`（sha256("nl:user:"+uid+salt)[:32]）、`consume_quota`/`consume_quota_on`（原子 upsert RETURNING）、`cache_lookup`（engine 级快路径，命中深拷贝 + 更新 last_hit_at/hit_count）、`cache_get`/`cache_touch`/`cache_store`（连接级，锁事务内）、`advisory_lock`（pg_advisory_xact_lock(hashtext(key))）。
- **app.py 路由编排（/api/saas/nl/compile）**：空描述 400 → nl_config/build_system_prompt/构建 cache_key → 快路径缓存命中直接返回 cache_hit=true（不调 LLM 不占配额）→ `engine.begin()` 同 key 咨询锁 + 复检缓存 → 配额（admin 直接放行；游客 consume guest_daily=10，超限 403/code=guest_nl_limit 原文案；会员 consume member_minute=6，超限 429/code=nl_rate_limited+scope+reset_seconds）→ `compile_nl` → 仅 ok=true 且 config 可用时写缓存 → not_configured 返回 503。配额与缓存在同一锁事务（每请求仅占一个连接，避免嵌套取连接耗尽连接池；正常返回即提交，编译失败同样计数）。SQLAlchemyError 时游客回退 `_guest_nl_hit` 文件计数、会员 503 rate_limit_unavailable（不因故障放开限流）。
- **管理台同步（R-ADMIN-001）**：`api_console_overview` 在读连接前 `ensure_nl_tables`，随后新增 `nl` 对象：guest_daily/member_minute 直接读路由闭包外的当前执行常量 `GUEST_NL_DAILY_LIMIT`/`MEMBER_NL_MINUTE_LIMIT`（改常量即时跟随，无第二套配置）、admin="不限"、cache_version、rate_limit_rows/rate_limit_hits 与 cache_entries/cache_hits 读两表真实行（sum 聚合）。console.html 总览在 Worker 资源卡前新增「自然语言编译」卡（`id="ov-nl"` metric-strip + h2 tip-trigger 解释），`loadOverview` 调 `renderNlCompile(d.nl)`：游客每日/会员每分钟/管理员/缓存版本/缓存条目/累计命中/限流计数七张 metric 卡，解释走 title/tip，无 `.opt` 灰字。管理员鉴权（_require_admin）不变。
- **踩坑记录**：① SQLAlchemy 2.0 `engine.connect()` 退出不提交——锁事务必须用 `engine.begin()`，否则缓存写入被回滚；② 锁事务持有连接期间再取连接（consume 独立事务）会 Pool 死锁——配额改在锁事务内同连接执行；③ 同会员同分钟共享一行 nl_rate_limits，行锁会使该会员并发编译自然串行（原子计数固有属性，非缓存锁）；「不同 key 不串行」测试因此改用两个不同会员；④ Node harness 断言误把限额当 hits——限额来自常量（10/6），hits 来自两表（13），两者必须分开断言。
- **测试**：`tests/test_saas_nl_compile_cache.py`（新，23 passed + 1 skipped）+ `tests/test_gui_saas_console.py` 新增 `TestNlCompileConsole`（常量一致/常量改动跟随/两表计数/鉴权不变）与 `TestConsolePageNlCard`（卡标记/tip-trigger/无 .opt/位于 Worker 卡前/JS 读 d.nl）。既有 NL/权限/分享测试零改动。
- **部署**：ECS 基线核对一致 → 备份 `/tmp/qre-nl-a2a3-pre-20261026/`（app.py+schema）与 `/tmp/qre-nl-console-pre-20261026/`（app.py+console.html）→ postgres apply → scp 三文件（A2A3）与两文件（console）→ 仅重启 qre-saas（未重启 worker）。公网临时游客会话经典 MACD 描述纯编译两次 cache_hit false→true、YAML 一致、jobs 10→10；9090 隧道临时 admin session 验证 overview nl 字段与常量/表计数一致（临时账号与会话已清理）。

## Task ID

QRE-SAAS-SHARE-ABSOLUTE-URL（分享链接补全公网域名）

## Release Status

已部署待人工复验，未 commit/push（2026-10-26）。最终全量 2703 passed + 5 skipped；生产创建返回完整公网 URL，公开页面与撤销验证通过。

## Implementation Summary

- 先验证用户链接：summary=200、readonly_kind=share、Chromium 只读渲染无 JS error，排除 token 失效；实际缺陷为创建响应只有相对路径。
- `app.py::api_share_link_create`：新增 `public_base_url = SAAS_PUBLIC_BASE_URL or request.url_root`，返回 `<base>/saas/jobs/<id>?share=<token>`；生产 env 固定 `SAAS_PUBLIC_BASE_URL=https://www.aguhuice.com`。
- `tests/test_saas_access_hardening.py`：新增创建 URL 必须为绝对公网地址；access_hardening 68 passed，全量 2703 passed + 5 skipped。
- ECS：备份 `/tmp/qre-share-absolute-url-pre-20261026/`（app.py 与 0600 env），同步 app.py + env 后仅重启 qre-saas。真实创建 URL 前缀正确、公开页面 200、撤销 200；临时 session/link 清理。未跑真实回测。

## Task ID

QRE-SAAS-SHARE-SEQUENCE-GRANT（分享创建 HTTP 500 权限热修）

## Release Status

已部署待人工复验，未 commit/push（2026-10-26）。最终全量 2702 passed + 5 skipped；生产真实创建/撤销 API 均 HTTP 200，schema 哈希一致，临时数据已清理。

## Implementation Summary

- 生产日志根因：`psycopg.errors.InsufficientPrivilege: permission denied for sequence share_links_id_seq`，不是结果操作卡或分享前端问题。
- `deploy/saas/cloud_schema.sql`：在 `share_links` 索引后增加 DO 块，角色 `aguhuice` 存在时授予表 SELECT/INSERT/UPDATE/DELETE 与序列 USAGE/SELECT；角色不存在的本地临时库跳过，保持可重复 apply。
- 同文件将既有 `showcase`/`showcase_daily` 定义纳入权威 schema，消除新库懒建表时序依赖；生产 IF NOT EXISTS 不改动既有表。
- `tests/test_saas_access_hardening.py`：新增表+序列 GRANT 静态回归；access_hardening 67 passed、相关 88 passed、全量 2702 passed + 5 skipped。
- ECS：备份 `/tmp/qre-share-sequence-grant-pre-20261026/`，生产 GRANT + 两次幂等 apply；真实 POST 创建与撤销均 200，临时链接/session 删除，share_links=0。未跑真实回测。

## Task ID

QRE-SAAS-CLASSIC-ACTIONS-UI（经典策略按钮与结果操作卡精修）

## Release Status

已部署待人工验收，未 commit/push（2026-10-26；R-DEPLOY-001）。相关 10 文件 289 passed + access_hardening 66 passed，全量 **2701 passed + 5 skipped**（基线 2689+5 零回归）；真实 Chromium 9/9 零 JS error 零横溢，证据 `.tmp/classic-actions-ui/`。ECS 三文件与 HEAD 基线一致，备份 `/tmp/qre-classic-actions-pre-20261026/` 后同步 `showcase.html`、`job.html`、`lab-theme.css` 并仅重启 qre-saas（worker 未动、未跑真实回测）；公网 showcase/job58/`/static/lab-theme.css` 200 且新标记齐全、删除标记为零、CSS SHA256 与本地一致。**待用户人工验收通过后才 commit/push；不完整恢复上述备份。**

## Implementation Summary

- `showcase.html`：页头 `.opt` 备注 → H1 旁 `tip-trigger`（data-tip 承载只读/更新/风险）；删 `#sc-hint` 元素与 `getElementById('sc-hint')` 赋值；底部卡改 `card showcase-cta`（「复现经典策略」+ 问号提示 + `btn btn-primary`「新建同款策略」→ `/saas/new`）；subtitle 渲染逻辑原样保留。
- `job.html`：新增外层 `chart-box hidden#result-actions-card`（标题「结果操作」+ 问号提示）；`#box-actions`/`#box-share` 改 `result-action-group hidden` 内部组；保存/确认信号=`btn btn-primary`（移除 confirm 的 `background:var(--accent)` 内联），信号/分享=`btn btn-ghost`；`#action-status`/`#share-status` 类改 `result-action-status`；信号面板灰字「T+1 参考…扫描范围：」改「扫描范围」标签 + `tip-trigger`（data-tip 承载 T+1 与范围口径），radio/select/ID/scope 值不变；readonly 隐藏清单加 `result-actions-card`；新增 `syncResultActionCard()`（空安全、双组 or 判断、`classList.toggle('hidden', !visible)`），`initResultActions`/`initShareButton` 全分支（readonly/游客/无 sid/无 box/已绑定/显示）结束后调用；保存/信号/分享 API、状态回填、`actionsBound`/`shareBound` 防重绑不变。
- `lab-theme.css`：文件末尾追加局部规则块（注释标记 `QRE-SAAS-CLASSIC-ACTIONS-UI`）：`.result-action-group`（首组无顶距）、`.result-action-buttons`（flex/gap 10px/wrap/居中）、`.result-action-buttons .btn` 与 `.showcase-cta .btn` `min-height:44px`、`.result-action-status`（13px `--ink` 可读状态文本）、`.result-action-scope`、`.showcase-cta`（flex wrap、h2 右推）；≤768px：CTA 纵排全宽、操作按钮 `flex:1 1 auto` 居中。无新色相、无 `--faint`、不动 `.btn-sm` 与其他页面。
- 测试：新 `tests/test_saas_classic_actions_ui.py`（静态断言 + 两个 Node harness：完整脚本段可见性矩阵四形态/连续初始化/失败重试/单绑定；`syncResultActionCard` 单独抽取空安全跑 null document）；`tests/test_saas_access_hardening.py` 更新只读隐藏清单字符串、readonly harness `known` 与循环（加 `result-actions-card`）、share harness 增 `syncResultActionCard(){}` 透传桩（该 harness 只抽取分享段）；`tests/test_gui_saas_pages.py` 的 readonly marker 同步为新行。

## Archive: QRE-SAAS-UI-DECLUTTER-001（结果页口径展示与说明页导航精简）

## Release Status

RELEASED（2026-10-26，实现 `8accb66` 已 push + ECS，未跑真实回测）。相关 138 passed，全量 2689 passed + 5 skipped，真实 Chromium 6/6；证据 `.tmp/ui-declutter/`。ECS 备份 `/tmp/qre-ui-declutter-pre-20261026/`，六文件 SHA256 与 HEAD 一致；公网 job58/symbol58/showcase/profile/help 200，删除标记为零，侧边栏目与 20px 标题生效。

## Implementation Summary

- `_records_scripts.html`：删除 `contractBadge` 及拼接，任务状态 badge 保留；API 的 `job.result_contract` 不再被模板消费。
- `showcase.html`：删除页头与行内验证徽标/合同版本，精简底部提示；公开 verified 过滤仍由服务端执行。
- `job.html`：删除 `#box-contract` 全部 DOM 与渲染，删除四处模块帮助深链；`renderContract` 仅更新 `#curve-tip`。
- `symbol.html`：删除收益/磨损/风险三处帮助深链与 `#sym-note` 口径链接，数据截止保留。
- `help.html`：七锚点迁入 `.help-layout > .help-side + .help-content`；删除验证状态行与新旧口径文字，页头不再宣称结果页深链。
- `lab-theme.css`：190px 桌面 sticky 侧栏、20px 卡片 h2；≤760px 单列布局 + 双列静态导航。
- 测试：`test_saas_result_help.py`、`test_saas_help_copy.py`、`test_saas_result_contract.py`、`test_gui_saas_pages.py` 同步锁定新合同边界；后端 API 与权限用例原样通过。

## Archive: QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

## Release Status

RELEASED（2026-10-26，实现 `08b4a27` 已 push + ECS，未跑真实回测）。最终全量 2688 passed + 5 skipped；真实 Chromium 12/12。生产由 postgres apply `share_links` 后发布；公网创建→匿名只读→撤销通过。生产复核补一项 showcase 边界：显式无效/撤销 share 参数不得回退公开 showcase（两处 fallback 增加 `not share_token`），无参数 showcase 入口不变；job58/74 生产验证均通过，临时链接已清理。证据 `.tmp/readonly-share/`。

## Implementation Summary

### Schema 与自愈（deploy/saas/cloud_schema.sql、src/quant_research_engine/gui/saas/app.py）

| 符号 | 行为 |
|---|---|
| `share_links`（新表） | `id BIGSERIAL PK` / `token_hash TEXT NOT NULL UNIQUE`（64 位十六进制完整哈希）/ `job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE` / `owner_id BIGINT NOT NULL REFERENCES users(id)` / `expires_at TIMESTAMPTZ`（NULL=永久）/ `revoked_at TIMESTAMPTZ` / `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`；索引 `(job_id, created_at DESC)`、`(owner_id, created_at DESC)`；无明文/前缀/guest_key/last_used |
| `_share_token_hash(app, token)` | `sha256("share:"+token+_auth_salt(app))` 完整十六进制；域分离前缀，复用现有 salt |
| `_ensure_share_links(engine)` | information_schema 先查再 CREATE + 进程 guard（`_SHARE_LINKS_ENSURED`/`_SHARE_LINKS_OK`）；CREATE 失败（ECS owner 踩坑）返回 False，调用方按「分享不可用」降级，不报错、不降级授权 |
| import | `datetime` 增加 `timedelta`/`timezone` |

### API（app.py，位于结果系统之后、后台管理之前）

| 端点 | 行为 |
|---|---|
| `POST /api/saas/jobs/<id>/share-links`（新） | 登录 + `_load_job_for_user` 本人 + status=completed；游客 401、他人/不存在 404、未完成 409；`expires_days` 只接受整数 1/7/30/0（默认 7，拒绝字符串/浮点/布尔无静默取整）；`secrets.token_urlsafe(32)`；返回 `{ok,id,url,expires_at}`——唯一明文 token 响应；表不可用 503 |
| `GET /api/saas/share-links`（新） | 仅当前用户最近 50 条（created_at DESC）；返回 id/job_id/strategy_name/created_at/expires_at/revoked_at/status（revoked＞expired＞active 判定）；不回 token_hash/明文；未登录 401 |
| `POST /api/saas/share-links/<id>/revoke`（新） | `UPDATE ... WHERE id AND owner_id AND revoked_at IS NULL RETURNING id`；仅创建者；重复/他人/不存在统一 404；未登录 401 |
| `_load_job_for_share(job_id, token)`（新） | token_hash 命中且未撤销、未过期且 job_id 一致才返回 job+strategy+result 行；其余一切返回 None（不降级、不泄露）；表不可用返回 None |
| `_public_readonly_kind()` / `_is_public_readonly()`（新） | share＞showcase＞None；替代原先散落的 `getattr(g, "showcase_readonly", ...)` |
| `_require_completed_result` | 开头解析 `?share=`：有效则置 `g.share_readonly` 直接放行（不看登录/游客会话）；无效则走原有匿名 401 / 登录他人 404 分支，错误体逐字节不变 |
| `api_result_summary` | `readonly` 改 `_is_public_readonly()`，新增 `readonly_kind` |
| `api_result_symbol_detail` 404 体 | 同样回带 `readonly`/`readonly_kind`（前端据此区分文案） |
| `api_symbol_detail_generate` | `_is_public_readonly()` 即 403；share 文案「分享链接为只读，不支持按需生成」，showcase 文案「经典策略为只读展示」不变 |

### 前端模板（templates/job.html、profile.html、symbols.html、symbol.html）

- `job.html`：新增 `#box-share`（分享结果卡，默认 hidden）、`#share-modal`（有效期单选 1/7/30/0，默认 7）、`#share-link-modal`（只读 input + 复制 + 「只显示一次」说明）；分享脚本段 `SHARE_TOKEN`/`shareUrl`/`shareSuffix`/`initShareButton`/`createShareLink`/`copyShareLink`（Clipboard API，失败回退 focus+select 手动复制）；poll() 的四个结果 API 与 `#big-symbols` 链接经 `shareUrl`/`shareSuffix`；readonly 分支按 `readonly_kind` 分流 chip（只读分享 / 经典策略展示 · 只读）与返回链接（`/saas/` 首页 / `/saas/showcase`），隐藏清单加入 `box-share`；completed 非只读且登录时 `initShareButton(data)` 显示入口。
- `profile.html`：新增 `#share-card`（我的分享表：任务/策略/创建时间/有效期/状态/撤销按钮，仅 active 行有撤销）与 `#share-revoke-modal`（二次确认）；`loadShares`/`renderShares`/`bindShareRevoke`；records include 移到分享段之前（保证 Node harness 可单独抽取分享段）；未登录（401）隐藏卡片。
- `symbols.html`/`symbol.html`：`SHARE_TOKEN`/`shareUrl`/`shareSuffix`；symbols 列表 API 与行内跳转、symbol 详情与 gen-status API 带 token；返回链接经 Jinja `share_qs` 保留 token；分享视图缺产物文案「该分享未提供该股详情。」（showcase 不变）。

### 测试

- `tests/test_saas_access_hardening.py`（+34 例，fixture TRUNCATE 纳入 share_links）：创建准入（游客 401/他人不存在 404 同体/未完成 409/allowlist 含 1.5 与字符串拒绝/缺省 7 天/未验证可分享且合同 verified=false/响应即唯一明文面）、存储（列最小集/仅 64 位 sha256(token+salt)/两条 hash 不同/明文不入库/列表字段与 scoped/状态机）、撤销（立即生效且与错 token 同体/重复他人不存在 404/未登录 401）、读取通道（有效 token 匿名与他人登录全端点 OWNER_OK/readonly_kind=share/本人正常访问无标记/异 job 全拒/无效不降级同体/过期同体/列表与 console 与 worker 不开放/写保护 generate 403+delete/cancel/revoke 原权限/share 与 showcase kind 区分）、CASCADE（删 job 无孤儿）、游客不能创建。
- `tests/test_saas_access_hardening.py` 前端 Node（+10 例，自建 `_EL_FACTORY` + job/share/readonly/profile 三个 harness）：分享/经典文案分流、游客与公开视图无入口、创建只显示一次且 localStorage 零痕迹、有效期传参、复制两条路径、失败可重试、token 传播、profile 列表状态与撤销二次确认与未登录隐藏。
- `tests/test_gui_saas_pages.py`：三个既有 Node harness 增加 `shareUrl/shareSuffix/initShareButton` 透传桩（token 传播由专用 harness 覆盖）；`test_job_polling_access_and_readonly_guards` marker 更新为 shareUrl 包裹形式。

### 主 Agent 复核记录（2026-10-26）

1. `_ensure_share_links` 首次失败后不能永远返回 True：拆 `_SHARE_LINKS_ENSURED`（已尝试）与 `_SHARE_LINKS_OK`（可用性）两个字典，失败后每次仍返回 False（分享创建 503、读取按无效 token）。
2. 有效期 allowlist 拒绝 `1.5`：`int(1.5)` 会静默取整成 1，改为严格 `isinstance(int)` 且非 bool。
3. 过期测试最初误把「最新一条」当目标：直接 `UPDATE share_links SET expires_at = now() - interval '1 day'` 全表置过期，语义更直白。
4. 浏览器审计三处修正（均为审计脚本问题，非产品缺陷）：API 返回相对 URL 需补 BASE；异 job token 断言必须用匿名上下文（登录所有者看自己任务本就 200）；撤销要按 `#{job_id}` 定位行（列表按创建时间倒序，first 行是另一条链接）。

### 主 Agent 截图复核 Required Fixes（2026-10-26，2 项聚焦修正）

1. **公开只读页全局游客条未隐藏**：分享页顶部仍显示 base.html 的 `#guest-strip`（「游客模式…注册/登录」），与报告「游客引导全部隐藏」不符且误导匿名接收者。修正：job.html 公开只读分支隐藏清单加入 `guest-strip`（showcase 与 share 都适用）；分享视图在脚本解析时（`SHARE_TOKEN` 存在）即隐藏，消除摘要返回前的闪现；`symbols.html`/`symbol.html` 分享视图同样解析时隐藏。base 的游客条显示 IIFE 先于页面 scripts 执行、只按登录态显示，本次零改动；撤销/无权页不改变 base 行为。回归：marker 断言隐藏清单含 `guest-strip`；Node readonly harness 的 known 元素表加入 `guest-strip` 并在 share/showcase 两 kind 断言 hidden；真实 Chromium 以 `getComputedStyle` 断言 share 桌面/移动/showcase 三处 `display=none`（新增 showcase 夹具用例 + `showcase-job-1280.png`）。
2. **分享时间直接展示 ISO 微秒**：创建成功 modal 与 profile「我的分享」的创建时间/有效期原样输出 `2026-10-27T00:35:53.414386+08:00`。修正：新增 `fmtShareTime`，统一走全站既有 `LabUI.fmtLocalTime`（`static/lab-ui.js`：UTC ISO → 本地 `YYYY-MM-DD HH:mm`，无微秒；与 console/signals/strategy 等页同口径），LabUI 缺失时回退原值（不编日期），`expires_at` NULL 仍为「永久有效」。回归：job/profile 两个 Node harness 注入与 lab-ui.js 同实现的 LabUI 桩，断言 modal 与列表匹配 `/\d{4}-\d{2}-\d{2} \d{2}:\d{2}/` 且不含 `T\d{2}:\d{2}:\d{2}` 与 `\.\d{6}`；新增 LabUI 缺失回退与「永久有效」用例；列表夹具补 active+`expires_at=null` 行（撤销按钮预期改 [1,4]）；浏览器同步断言并截图复核。
3. 额外清理：创建分享 docstring「本本人」→「本人」。复跑：access_hardening 66 passed、相关 23 文件 656 passed、真实 Chromium 12/12；未 commit/push/ECS、未跑真实回测、无格式化 churn。

## Archive: QRE-SAAS-RESULT-UNDERSTANDING（P1 第二切片：结果理解、集中帮助与数据/费用口径）

## Release Status

RELEASED（2026-10-25，实现 `9fd3b3d` 已 push + ECS，未跑真实回测）。全量 2653 passed + 5 skipped；真实 Chromium 10/10。ECS 备份 `/tmp/qre-result-understanding-pre-20261025/`，公网帮助页/深链/个股 data_until 与文件 SHA256 验证通过，生产证据 `.tmp/result-understanding-production/`。

## Implementation Summary

### 后端（src/quant_research_engine/gui/saas/app.py）

| 符号 / 端点 | 行为 |
|---|---|
| `GET /saas/help`（新） | 公开帮助页路由（无鉴权门槛，游客与登录用户均可访问）；`render_template("help.html", daily_return_basis=DAILY_RETURN_BASIS, total_return_basis=TOTAL_RETURN_BASIS)`——口径文案与 `result_contract` 常量同源，不复制 |
| `api_result_symbol_detail`（gzip 路径） | 返回前 `data["data_until"] = _jsonable(row["result_data_until"])`；不改 gzip 产物、不回填 |
| `api_result_symbol_detail`（本地 fallback） | `build_lab_symbol_detail` 结果同样注入 `data_until`；产物缺失的 404 分支不变（仍带 can_generate） |
| import | `result_contract` 增加导入 `DAILY_RETURN_BASIS` / `TOTAL_RETURN_BASIS` |

### 前端模板与静态（templates/base.html、help.html、job.html、symbol.html、static/replay.js、static/lab-theme.css）

- `base.html`：主导航新增 `<a href="/saas/help" data-nav="help">使用说明</a>`（置于「经典策略」与「个人信息」之间）；nav active 判定增加 `nav === 'help' && path.indexOf('/saas/help') === 0`；`@media (max-width:400px)` 补 `header.topbar{padding:0 10px}`、logo 24px、`.mainnav{gap:0}`、链接 11.5px/6px——修掉第 5 个导航项在 375px 登录态的顶栏溢出（lab-theme 的 `.mainnav{gap:4px}` 后加载，须 `header.topbar` 前缀提优先级）。
- `help.html`（新）：page-head + `.help-jump` 锚点胶囊 + 七张 `.card.help-sec`（id=contract/metrics/benchmark/fees/risk/attribution/replay），每节一张两列 `.tbl`（项目/含义），合同节两种口径由 `{{ daily_return_basis }}`/`{{ total_return_basis }}` 注入；尾部「还想自己试？」卡链接新建/经典策略；无营销文案、无常驻灰字（`class="opt"` 仅 1 处免责）。
- `job.html`：`#box-contract`/`#box-main`/`#box-fees`/`#box-risk`/`#box-tags` 标题区各加 `<a class="inl" href="/saas/help#…">说明 →</a>`；曲线 tip 按钮加 `id="curve-tip"`（静态回退文案保留）；`renderContract` 在合同带 `daily_return_basis`/`total_return_basis` 时重写该 tip；`renderFees` 的 `wc()` 增加 tip 形参，五卡 + 费率 chip + 毛/净 `.wb-label` 全部挂 `data-tip`（卡与标签加 `tabindex=0`）；`bench-bar` 的「基准：」标签挂基准含义 tip；VaR/ES 卡 tip 补「损失以正数展示，数值越大风险越高」。
- `symbol.html`：收益曲线/交易磨损/风险分析标题区加「说明 →」（#benchmark/#fees/#risk）；`load()` 末尾把 `#sym-note` 改为 innerHTML：`数据截止 <date|未声明> + 口径说明 → + 全量 N 个交易日|K线暂缺`；`renderRisk` 的 VaR/ES 由 `pct(-var)` 改 `pct(var)`（损失正数，与 job/风险报告一致），三张卡 tip 统一补正号约定；`renderWear` 两个分支的 `wc()` 均加卡级 tip 与毛/净标签 tip。
- `replay.js`：`renderMetrics` 指标卡数组改为 4 列（label/value/class/tip），盈亏比/当前持仓/暴露度补 tip，卡片输出带 `tabindex=0 data-tip`；纯逻辑 `frameMetrics` 零改动。
- `lab-theme.css`：仅新增 `.help-sec{scroll-margin-top:76px}` 与 `.help-jump`（既有 token，无新色相/循环动效）。

### 测试

- `tests/test_saas_result_help.py`（新，17 例）：帮助页 200（匿名/登录）、七锚点、禁链与术语、合同文案同源、模块深链、6 卡锁定 + 盈亏比不进主指标卡、`renderContract` 曲线 tip 合同同源与无合同回退（Node harness）、`renderFees` 五卡 + 费率 chip tip（Node harness）、费率默认文案、bench tip、symbol 磨损 tip、`replay.js` 三卡 tip（Node harness 跑真实 `renderMetrics`）、symbol 两路径 `data_until`、VaR/ES 正号静态断言。
- `tests/test_saas_help_copy.py`（+2）：帮助页/导航/深链静态纪律；磨损/费率/基准/重播 tip 存在性。
- `tests/test_saas_symbol_ux.py`（+2）：gzip 与本地 fallback 两路径 `data_until`（原字段不受影响）。
- `tests/test_gui_saas_pages.py`（+1）：`#sym-note` 渲染 data_until/未声明/口径链接（symbol harness 补 `esc` 页面 helper 桩，其余用例不变）。

### 复核记录（2026-10-25）

1. 移动 375 顶栏溢出为真实缺陷（非测试噪声）：登录态 5 项导航 + lab-theme `gap:4px` 使顶栏 389px > 375px；已在 ≤400px 断点修复并把审计断言改为对比固定视口宽（移动模拟会撑大 innerWidth，只用 innerWidth 会漏报）。
2. `#curve-tip` 静态回退保留：无合同时 `renderContract(null)` 不清空 tip，避免曲线说明消失。
3. `data_until` 注入点在响应层（两路径一致），不改 worker 回传协议、不改 gzip 产物、不回填历史。

### 主 Agent 复核 Required Fix（2026-10-25，聚焦修正：过户费/其他重复计入）

1. **缺陷**：`worker/runner.py` 的 `wear.other_cost = total_cost − commission − stamp_tax` 已包含 `transfer_fee`（与滑点等残差，与 job 的 `fees_summary.other_cost` 同口径），但 `symbol.html` worker 回传分支显示 `(w.transfer_fee||0)+(w.other_cost||0)`，把过户费算了两遍（夹具 5.09/10.26/0.5/15.85 → other_cost=0.5，修复前显示 1.00）。
2. **修正**：worker 回传分支改为只显示 `w.other_cost`（与 job.html 一致）；**未改 runner、未改任何费用原值或总磨损**；本地 fallback 第二分支仍按订单拆分显示 `过户费合计`（`transfer`），保持现状。
3. **回归**：`tests/test_saas_result_help.py::TestSymbolWearNoDoubleCount` 2 例（Node harness 跑真实 `renderWear`：修复前 `1.00 元`→RED，修复后 `0.50 元`，并校验 `commission+stamp+other==total_cost`；本地 fallback 分支保持订单拆分）；`tests/test_saas_symbol_ux.py` 磨损夹具补 `other_cost==0.5` 与勾稽断言（锁定数据契约）。
4. **浏览器证据同步**：`.tmp/result-understanding/browser_audit.py` 的 seed 磨损改为自洽（commission 42.10 + stamp 28.40 + other 12.80 = total 83.30，transfer_fee 3.2 为 other 的子集），symbol 页断言「过户费/其他 = 12.80 元」且不出现 16.00 元，三卡相加=总磨损；重跑 10/10 通过，截图已肉眼复核。

## Archive: QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片：等待状态、离线提示与失败恢复）

## Release Status

RELEASED（2026-10-25 用户批准 commit + push + ECS；实现 `a84a9a3` 已发布），未跑真实回测。全量 2629 passed + 5 skipped；真实 Chromium 12/12 场景通过（证据 `.tmp/first-success-ux/`）。ECS 五文件 SHA256 与仓库一致，备份 `/tmp/qre-first-success-ux-pre-20261025/`，生产证据 `.tmp/first-success-ux-production/`。

## Implementation Summary

### 后端统一运行态（src/quant_research_engine/gui/saas/app.py）

| 符号 | 行为 |
|---|---|
| `_queue_position(conn, priority, created_at)` | 排队位置 SQL（同优先级按创建先后，前面还有几个 queued）——从 GET job 内联提出，供两处共用 |
| `_worker_online(conn)` | 任一 worker `last_heartbeat_at > now() - interval '3 minutes'`（与管理台既有在线口径一致）；只回布尔 |
| `_job_runtime_fields(engine, row)` | queued → `queue_position`；queued/leased/running/uploading → `worker_online`；终态不加 |
| `GET /api/jobs/<id>`（含 /api/saas 别名） | `_job_view` 之后 `item.update(_job_runtime_fields(...))`；既有字段与权限语义不变 |
| `_require_completed_result` 409 体 | 增补 `queue_position`（仅 queued）/`worker_online`/`strategy_id`/`cancel_requested`/`error_class`/`error_message`；`error` 文案保持「任务未完成（status）」不变 |
| `POST /api/jobs/<id>/cancel`（含 /api/saas 别名） | 游客按会话归属：`_guest_identity` 取 guest_key；owned 判定 = 登录用户 user_id 匹配 / 游客 user_id IS NULL 且 guest_key 匹配；不 owned → 匿名 401（`_with_guest_cookie` 补签发会话 Cookie）/ 登录 404，与不存在同体；queued 直接 canceled、running 置 cancel_requested、终态 409 均不变 |

### 前端（templates/new.html、templates/job.html、static/wait-mask.js、static/lab-theme.css）

- `new.html`：`createJob` 包 `newRequestWithTimeout` 15s（AbortError → 「提交等待超时……避免重复提交」可读错误）；`pollJob` try/catch 包裹轮询请求，AbortError `continue`，其余原样抛出；80 轮耗尽抛 `PollTimeoutError`（name 区分，消息「任务仍在后台执行，请前往任务页查看」）；新增 `waitedText` / `jobWaitStatus` / `renderJobWait`（wait-mask title/sub/meta）；`pipeStopAt`（非失败停留：超时提示 + 任务页链接，不写「失败」前缀、不提交全量）；startRun 冒烟 catch 按 `PollTimeoutError` 分流。
- `job.html`：`#status-card` 增 `#job-status-extra`（aria 无关的视觉副行）、`#status-actions`（`#btn-cancel-job` + `#cancel-status`）、`#recover-actions`（`#recover-error` + `#btn-rerun`）与 `#cancel-modal`（复用 `.modal-mask`/`.modal`，确认钮红底）；`renderJobRuntime` / `renderJobRecovery` / `setCancelModal` / `doCancelJob`；poll() 的 409 分支改调这两个渲染函数；completed 分支显式隐藏三个新区块并禁用取消按钮（防呆）。
- `wait-mask.js`：title/sub `aria-live="polite"`；新增 `meta` 状态字段 → `.wm-meta`（`aria-hidden="true"`、无 aria-live）；`show/update` 透传 meta；其余语义不变。
- `lab-theme.css`：仅新增 `.wm-meta{...tabular-nums}` 一条规则（无新色相、无新组件）。

### 测试

- `tests/test_saas_first_success_ux.py`（新，21 例）：运行态字段（queued N / running 无 queue_position / worker 在线-离线-过期 / 无 worker 明细泄露 / 游客可见）、409 契约（queued 全字段 / failed 真实 error_message+error_class+strategy_id / running 有 worker_online 无 queue_position / 权限语义不变 / 游客 owner 409 + 异会话 401 / showcase completed readonly 不变）、取消矩阵（登录 queued+running / 游客同会话 / 异会话 401 同体 / 无 Cookie 401 且任务不变 / 游客不能取消用户任务 / 他人 404 同体 / 匿名不存在 401 / 终态 409 / 401 带会话 Cookie）。
- `tests/test_gui_saas_wait_mask.py`（新，4 例）：aria-live/meta 降噪、文本未变不写 DOM 回归、keepmask 与 spinner、CSS meta 与移动规则。
- `tests/test_gui_saas_pages.py`：`TestNewPageWaitStates` 8 例（文案标记、AbortError 继续轮询、500/终态 fail-fast、PollTimeout 独立错误且 80 轮、queue/offline 文案与 meta、createJob 超时、pipeStopAt 中性态）+ `TestJobPageRuntimeAndCancel` 6 例（queued 409 渲染、N=0 与 cancel_requested、取消模态全流程与防重复、running 取消请求已发送、登录/游客恢复链接、readonly 零取消）；改写 `test_new_login_url_and_poll_job_fail_fast`（body pending → 超时后继续轮询至 completed）与 `test_job_page_uses_results_detail_apis`（旧断言精确到 `/result` 嵌套路径，新增 `/cancel` 断言）。

### 主 Agent 复核 Required Fixes（2026-10-25，聚焦修正）

1. `pipeStopAt` 去掉 `fail` 类，改中性「后台等待中」（移除 doing/fail + `.pipe-st` 文案，无新色相/组件）；`pipeFailAt` 失败红态仅保留给真实失败。回归 `test_pipe_stop_at_is_neutral_not_failure`。
2. `jobWaitStatus` 离线提示覆盖全部活跃态（queued/leased/running/uploading，终态不读）；`pollJob` 终态优先抛后端 `error_message`（回退 `error`/通用文案）。
3. wait-mask `apply` 仅在 title/sub 文本实际变化时写 DOM（aria-live 不被轮询重复触发），meta 照常更新，API 不变。回归 `test_wait_mask_skips_dom_write_when_text_unchanged`。
4. 浏览器取消模态证据改为等待可见 + 动画稳定后断言 computed display / bounding box / 按钮可见再截图（桌面 1280 / 移动 375 / 登录用户三处），截图已肉眼复核；`browser-evidence.json` 记录模态事实（display=flex、确认钮 102×38）。

## Archive: QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Task ID

QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Release Status

RELEASED（2026-10-25 用户批准 commit + push + ECS；实现 `0799890` 已发布）。ECS 仅同步 app.py 与 cloud_schema.sql 注释并重启 qre-saas，未重启 worker；公网双独立游客 Cookie 值与隔离语义验证通过。未跑真实回测。

## Implementation Summary

### 游客会话归属（src/quant_research_engine/gui/saas/app.py）

| 符号 | 行为 |
|---|---|
| `GUEST_COOKIE_NAME="qre_guest_sid"` / `GUEST_COOKIE_MAX_AGE=30d` | Cookie 常量 |
| `_guest_session_key(app, sid)` | 归属键 = sha256(`gsess:`+sid+salt)[:32]（同形同列，无 schema 变更） |
| `_guest_identity(app)` | (归属键, 需签发 sid)；有 Cookie 复用、缺失才生成；**绝不轮换** |
| `_attach_guest_cookie(app, resp, sid)` | HttpOnly + SameSite=Lax + Max-Age + Secure(`SAAS_GUEST_COOKIE_SECURE`，默认 0) |
| `_with_guest_cookie(app, err, sid)` | (response, status) 错误元组补挂 Cookie |
| `_migrate_legacy_guest_jobs(app, engine, new_key)` | 旧 IP 键行一次性 UPDATE 到新会话键；幂等 + 进程级 guard |
| `_guest_key(app, ip)` | 保留：仅用于旧数据迁移与游客 NL 限流（IP 成本口径） |

接入点：`POST /api/jobs`（新会话首次创建任务时迁移，先迁移后计数；403 配额响应也带
Cookie）、`GET /api/jobs/<id>`（匿名 401 与不存在一致；成功/失败按需签发）、
`_require_completed_result`（summary/chart-data/tag-analysis/risk-analysis/symbols/
symbol detail/gen-status 共用；匿名 401、409 带 Cookie）、`DELETE /api/results/<id>`
（游客按会话删除；他人/不存在统一 404）。`_load_job_for_guest(job_id, guest_key)`
改签名传键。console 游客统计注释更新为 distinct 会话口径。`deploy/saas/cloud_schema.sql`
guest_key 注释同步。模块 docstring 补游客归属说明。

### IDOR 测试（tests/test_saas_access_hardening.py，31 例）

游客 Cookie（签发/属性/随机/换 IP 不失效/双会话隔离/无 Cookie 同 IP 401/登录用户看
游客任务 404）；历史迁移（一次性/只读不迁移/今日旧任务占配额/幂等）；结果端点矩阵
（匿名 401、他人 404、本人业务态、不存在错误体一致、showcase verified 只读 200、
未验证白名单 401-404 且不进公开列表、游客会话结果端点）；job 详情矩阵（含
/api/saas 别名）；列表与相邻端点（8 个列表 401 + 按归属隔离 + 策略详情 401/404）；
写表面（delete 矩阵、showcase generate 403、worker token 不变）；NL 限流仍按 IP。

### ECS 处置（已执行）

`/etc/qre-saas.env` 备份 `…bak-access-hardening-20261025-173458`（0600）→ 注释
`SAAS_TEST_ACCOUNT_EMAIL/PASSWORD` → restart qre-saas（active）→ 正式登录 8 项验证
全过（含测试账号正确密码 401）。新增 `SAAS_GUEST_COOKIE_SECURE=1`（下次重启生效）。

## Verification Commands

```bash
.venv/bin/pytest tests/test_saas_access_hardening.py -q          # 31 passed
.venv/bin/pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py \
  tests/test_saas_result_contract.py tests/test_gui_saas_console.py \
  tests/test_saas_authing.py tests/test_saas_feedback.py \
  tests/test_saas_signals.py tests/test_saas_worker_status.py \
  tests/test_worker.py -q                                        # 329 passed（相关）
.venv/bin/pytest tests/ --ignore=tests/data_test -q              # 2590 passed + 5 skipped
PLAYWRIGHT_BROWSERS_PATH=.tmp/ms-playwright \
  .tmp/browser-venv/bin/python .tmp/access-hardening/browser_audit.py
```

证据：`.tmp/access-hardening/`（report.md、browser-evidence.json、7 截图、seed.py、
browser_audit.py、server.log）。

## Archive: QRE-SAAS-RESULT-CONTRACT-001（P0-1B 结果合同版本、口径标签与旧结果隔离）

## Task ID

QRE-SAAS-RESULT-CONTRACT-001（P0-1B 结果合同版本、口径标签与旧结果隔离）

## Release Status

实现 `37bcffa` 已 push。ECS 已 apply results.result_contract 并同步生产文件，`qre-saas` active；公网 showcase 仅 58/66，74 匿名 401，58 合同字段正确。备份 `/tmp/qre-result-contract-pre-20261025.tgz`，未重启 worker。

## Implementation Summary

新增 `src/quant_research_engine/gui/saas/result_contract.py`（结果合同唯一权威：版本
`2026-10-25.1`、两种收益口径文案、验证状态、显式例外表 58/66=verified、74=unverified、
其余历史默认未验证；分类函数无时间入参）。在 worker 回传接收层
`app.py::api_result_meta` / `api_report_result_legacy` 注入 `result_contract`
（`results.result_contract` JSONB 懒自愈列，`cloud_schema.sql` 同步）。API 只增字段：
`/api/results/<id>/summary`、`/api/results`、`/api/saas/showcase`、
`/api/saas/console/showcase`。`/api/saas/showcase` 与 showcase 公开只读通道
（`_load_job_public`）只放行 verified；白名单行/job/产物不动，属主权限不变。
前端复用 badge + data-tip：`job.html` 合同徽标与两种口径提示、`showcase.html`
已验证徽标与口径说明、`_records_scripts.html` 记录行合同标签。

**测试**：`tests/test_saas_result_contract.py` 21 例（RED→GREEN）+
`tests/test_gui_saas_pages.py` +2 例（JS harness，含 `renderContract` stub 修复 3 例旧失败）；
相关套件 180 passed + 1 skipped；全量 `pytest tests/ --ignore=tests/data_test`
→ **2559 passed + 5 skipped**。真实 Chromium 桌面 1280 / 移动 375 各 3 页通过
（专用临时库 + 8099 临时 staging，验收后已清理），证据 `.tmp/result-contract/`。

## Release Status

**未 commit / 未 push / 未部署 ECS / 未跑真实回测 / 未回填历史数值**，等主 Agent 与用户验收。
ECS 上线需先由 DBA apply `deploy/saas/cloud_schema.sql`（app 账号非 owner，ALTER 会
must be owner）；未 apply 也能启动（降级不写该列、按例外表解析，74 仍不公开）。
worker 无需改动。详细报告 `.tmp/result-contract/report.md`。

---

# Coding Handoff

## Task ID

QRE-SAAS-PARAMETER-TIPS-001（回测参数口径与单位提示）

## Implementation Summary

`new.html` 基础/高级参数 label 增加 `data-tip` 与 `tabindex=0`，复用 `LabUI.helpTips()`。说明共享/批量资金、金额元、比例小数、0/留空不限、次日价格、风险比例、费用与代码后缀；不改默认值、YAML 或回测。新增 `tests/test_saas_parameter_tips.py`；真实 Chromium 桌面/移动各 14 项通过，证据 `.tmp/parameter-tips/`，全量 2536 passed + 5 skipped。未 commit/push/ECS。

## Release Status

参数提示实现 commit `6291674` 本地完成（不 push）。ECS 仅同步 new.html，备份 `/tmp/qre-parameter-tips-pre-20261025.tgz`，`qre-saas` active，哈希一致，公网参数提示生效；未重启 worker。

实现 commit `ec1fd13` 已 push。ECS 同步注册表、metadata、相关 Python 模块与 new.html，备份 `/tmp/qre-factor-registry-pre-20261025.tgz`，`qre-saas` active，哈希一致；公网因子 API 中文字段生效，真实 NL MACD 编译 ok 且 holding=0，未创建回测、未重启 worker。

## NL Holding Hotfix

`gui/nl_compiler.py` 新增 `_with_default_holding`：缺 holding 补 0；描述无期限语义时覆盖模型编造天数为 0，明确期限保留；已有天数仅标量替换，其他 YAML 原文不动。staging 使用现有 OpenAI 兼容配置（凭证不入仓）后，真实 `/api/saas/nl/compile` 的 MACD/RSI/BOLL/KDJ/MA 五例全过且 holding=0，未创建回测。报告 `.tmp/factor-registry/nl-holding-default-report.json`。

## Implementation Summary

**注册表数据** `configs/factor_registry.json`（版本 1.0）：`market_fields`（7 个行情字段
及中文别名）、`tables`（19 张 factors 表的类别/价格口径/列数）、`families`（200+ 族规则
摘要：abbr/zh_base/default_output/default_params/param_order/aliases/族识别关键词）、
`factors`（895 条目，每项 `table/column/canonical/category/price_basis/family/output/
params/zh/aliases/common/core`）、`extra_aliases`（跨条目别名，如「布林带」→ 上/中/下轨
三个 canonical，形成候选而非静默覆盖）。

**生成器** `scripts/gen_factor_registry.py`：`FAMILY_RULES` 用列名正则 + 命名组解析参数
（`ema_5`→{period:5}、`macd_12_26_9`→{fast,slow,signal}、`bbu_20_2_0_2_0`→4 参数），
按 `zh_base` + `param_order`（或 `zh_params`，用于布林带/ALMA/PSAR 等参数串不美观的族）
生成中文名；`_is_common`/`_is_default_params` 决定别名挂载范围——**族别名只挂在「常用 +
默认参数」条目上**，避免全量别名进 JSON 与 Prompt；`MANUAL_ENTRIES` 人工补全财务与中文
习惯名；`CORE_TARGETS`（25 条）打 `core` 标记供 Prompt 常用示例派生，缺失会在生成时告警。
重新生成：`QRE_MARKET_DB_URL=postgresql+psycopg:///tushare_data .venv/bin/python
scripts/gen_factor_registry.py`。

**加载层** `gui/factor_registry.py`：`normalize_alias`（NFKC 全角转半角 → 小写 → 去空白/
下划线/连字符/间隔号/中文标点 → 剥离首尾句读；保留括号与逗号以便 `MACD(12,26,9)` 唯一命中）。
`FactorRegistry.resolve(text, price_basis=None)` 四级解析：①`_canonical_keys` 精确命中
（`factors.t.c` 与 `t.c` 两种写法）；②`_market_keys` 行情字段单独识别（不混入
factor_fields）；③`_alias_index` 归一化别名命中后用文本里的数字收窄；④`_family_from_text`
族识别（关键词取 abbr/zh_base/规则显式声明的族识别词，最长优先，**剩余部分不得含英文字母**——
否则 `macd_signal_12_26_9` 会被误判成 MACD 快线，应交回旧别名字典子串兜底）+ params 过滤
+ 族默认参数。`_finish` 收口：唯一命中→`_unique_result`（补「未指定参数→族默认值」提示）；
显式 price_basis 过滤；仅价格口径不同（同 category 同 column）时按
close→typical_price→average_price 取首个并生成 notice；其余返回 ambiguous + candidates。
`validate_registry(snapshot)` 查坏 canonical 与悬空别名；`coverage_report(snapshot)` 出
覆盖统计与未注册清单；`duplicate_aliases()` 列出别名的多目标（必须形成候选）。

**展示链路** `gui/factor_wizard.py::registry_display_fields` + `build_factor_groups`：
每个 item 追加 `zh/canonical/price_basis/aliases`（label 保留作旧数据回退）。
`scripts/sync_saas_metadata.py` 复用同一函数并新增 `_report_registry`（校验 + 覆盖报告）。
`gui/factor_catalog_llm.py` 新增 `registry_validation`/`registry_coverage`。

**弹窗** `gui/saas/templates/new.html`：`loadFactorCatalog` 把 `it.zh/it.canonical/
it.price_basis/it.aliases` 写进 `FACTOR_OPTIONS`；新增 `PRICE_BASIS_ZH`、`fpFactorLabel`
（zh 优先，null 回退 label）、`fpBasisZh`、`fpItemText`（中文名 + （口径））、`fpSubLabel`
（子类栏显示「大类(口径)」，数据键 sub 不变）、`fpSearchHaystack`（中文名/canonical/列名/
别名/大类/子类小写拼接）。`fpButtonText`/`syncFactorPickerButton`/`fpRender` 全部改走
`fpItemText`/`fpSubLabel`；`title` 改为「中文名（canonical）」作辅助对照。缺字段的旧
metadata 下 `o.zh`/`o.basis` 为 undefined，文案自动回退旧形态。

**NL 链路** `gui/factor_correction.py`：`COMMON_FACTOR_TARGETS` 改为
`_derive_common_factor_targets()`（注册表 core 条目，异常时回退内置清单）；新增
`registry_resolve_column(column, qualified_table, column_lookup)`——列已存在不解析；
唯一命中且同表且列在候选池内才替换（带 notice），跨表只给候选不自动改写，歧义给
candidates。`correct_factor_fields` 同表分支中**先注册表、后旧子串别名**，registry
纠正记录带 `via: "registry"` 与可选 `notice`；`format_corrections_note` 末尾追加去重后的
notice 行。`nl_compiler.build_system_prompt` 口径不变（canonical 目录 + 核心示例）。

测试：`tests/test_factor_registry.py`（新增 40 项）、`tests/test_gui_factor_wizard.py`
（+2）、`tests/test_saas_factor_picker.py`（+3，含注册表 fixture 的 Node VM 场景）、
`tests/test_gui_saas_pages.py`（+1）、`tests/test_gui_factor_correction.py`（+6）、
`tests/test_nl_factor_pipeline.py`（+6，含 11 条 NL 小样本矩阵与端到端 stub 编译）。

**验证命令与结果**：
- `uv run python -m pytest tests/test_factor_registry.py -q` → 40 passed
- `uv run python -m pytest tests/test_gui_factor_wizard.py -q` → 38 passed
- `uv run python -m pytest tests/test_saas_factor_picker.py -q` → 13 passed
- `uv run python -m pytest tests/test_gui_saas_pages.py -q` → 74 passed
- `uv run python -m pytest tests/test_gui_factor_correction.py tests/test_nl_factor_pipeline.py
  tests/test_gui_nl_compiler.py tests/test_factor_registry.py -q` → 95 passed
- `uv run python -m pytest tests/ -q --ignore=tests/data_test` → 2533 passed, 5 skipped
- `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check` → 通过
- 真实 Chromium `.tmp/factor-registry/browser_audit.py` → 桌面 1280×900 与移动 375×812
  各 13 项通过，零 JS error、零横向溢出

**限制与后续**：未运行真实全量回测、未调用真实 LLM；未 commit、未 push、未部署 ECS。
8081 lab 侧 `lab.html` 的自有向导副本未改（lab 侧冻结）。`deploy/saas/metadata.json`
已在本地重新导出，部署 ECS 时需同步该文件与 `configs/factor_registry.json`。

---

## Task ID

QRE-SAAS-FACTOR-PICKER-MODAL（自选因子三栏弹窗选择器）

## Implementation Summary

`gui/saas/templates/new.html`：`makeFactorSelect(cls)` 现在创建 `span.wz-factsel.factor-picker-field`，内嵌 `.factor-select-btn` 按钮 + 原有三个 select（`.wz-fact-group`/`.wz-fact-sub`/`cls`）。按钮 `textContent` 为「大类 / 子类 / 因子」（未选为「选择因子」），`title` 为「标签（字段）」+ `aria-haspopup="dialog"`。`syncFactorSelect` 末尾调用 `syncFactorPickerButton(wrap)`，因此目录加载、`setFactorSelectValue`（策略还原）与弹窗回填三条路径的按钮文案自动一致。

弹窗 `#factor-picker-modal`（复用 `.modal-mask` + `.modal.factor-picker`，`role="dialog"`/`aria-modal`/`aria-label`）包含 `#factor-picker-close`、`#factor-picker-search`、三栏 `#fp-list-group`/`#fp-list-sub`/`#fp-list-factor`、搜索结果 `#factor-picker-results` 与空态 `#factor-picker-empty`。`openFactorPicker(wrap)` 记录 `fpWrap` 与 `fpLastFocus`（直接取该 wrap 的按钮，不依赖 `document.activeElement`，规避 Safari 点击按钮不聚焦的差异），按当前值定位三栏，清空搜索并 `search.focus()`；`fpRender()` 无关键词时渲染三栏（当前项加 `.sel` 紫底），有关键词时对 `FACTOR_OPTIONS` 做只读过滤（`label/value/group/sub` 小写匹配）并展示完整层级；`fpPick(level, value)` 对 group/sub 只更新下级，对最终因子执行 `syncFactorSelect` 写回 → `sel.dispatchEvent(new Event('change', {bubbles:true}))` → `closeFactorPicker()`。`closeFactorPicker()` 关闭、清 `fpWrap`、把焦点还给 `fpLastFocus`。目录未就绪（`catalogReady === false`）时不弹窗，只在 `#wz-factor-status` 沿用既有错误提示。

Esc 与 Tab 焦点锁通过 `document` 上的 keydown 监听实现（仅在弹窗 `show` 时生效）：Escape 关闭；Tab 在 `#factor-picker-modal button, #factor-picker-modal input` 中循环，并过滤 `[hidden]` 容器内的节点。遮罩点击（`e.target === this`）与关闭按钮同样只关不改值。

`gui/static/lab-theme.css` 新增 `.factor-select-btn` 与 `#factor-picker-modal` 下的 `.fp-head`/`.fp-close`/`.fp-search`/`.fp-cols`/`.fp-col`/`.fp-list`/`.fp-item`/`.fp-results`/`.fp-empty`/`.fp-hint` 规则，全部使用既有主题变量（`--lav`/`--tint`/`--line`/`--shadow-1` 等），无新色相、无循环动效；桌面 `max-width:780px`、`max-height:min(600px,calc(100vh - 48px))`；768px 下 `width:calc(100vw - 24px)`、`max-height:calc(100vh - 40px)`、三栏 `grid-template-columns:1fr` 单列堆叠、`.fp-list{max-height:30vh}`、按钮 `min-height:44px` 且允许折行。

测试：`tests/test_saas_factor_picker.py`（新增）静态断言弹窗结构与契约 + 自建 Node VM mini-DOM harness 驱动真实向导源码，覆盖打开/父子联动/写回/一次 change/焦点返回、Esc 与遮罩只关不改值、目录未就绪不弹窗、搜索（过滤/空态/清空恢复/搜索选中/切回三栏清空残留）、向导回归（固定值、条件增删、AND/OR、快照→还原深比较）、渲染后内联脚本 Node 解析；`tests/test_gui_saas_pages.py` 新增 `TestFactorPickerModal`（渲染页弹窗标记 + CSS 隐藏规则与移动端降级）。

**验证命令与结果**：
- `uv run python -m pytest tests/test_saas_factor_picker.py -q` → 10 passed
- `uv run python -m pytest tests/test_gui_saas_pages.py tests/test_saas_factor_picker.py -q` → 83 passed
- `uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py tests/test_saas_help_copy.py tests/test_saas_factor_picker.py -q` → 242 passed
- `uv run python -m pytest tests/ -q --ignore=tests/data_test` → 2474 passed, 5 skipped
- `bash scripts/check-progress-docs.sh && bash scripts/git-finalize-check.sh && git diff --check` → 通过
- 真实 Chromium（`.tmp/browser-venv` + `.tmp/ms-playwright`，8091 staging）`.tmp/factor-picker-modal/verify.py` → 桌面 1280×900 与移动 375×812 合计 **64/64 通过**，零 JS error、零页面横向溢出。

**限制与后续**：未运行真实全量回测；未 commit、未 push（等用户批准）；8081 lab 侧 `lab.html` 的自有向导副本未改（lab 侧冻结，且 SaaS 与 lab 的 `.wz-factsel` 通过新增 `.factor-picker-field` 类隔离，互不影响）。

---

## Archive: QRE-SAAS-JOB-STRATEGY-CARD（SaaS 回测详情页「策略信息」折叠卡：summary API 携带策略定义 + job.html 默认折叠摘要行）

## Implementation Summary

**数据链路**：strategies 表现有列已够用（name/nl_text/yaml/entry_mode/wizard_state/created_at，CR-2026-10-04 模块一起落库，NL 原文在 nl_text——无 schema 变更、无「NL 原文未落库」遗留）。`gui/saas/app.py`：`_load_job_for_user`/`_load_job_for_guest` 的 SELECT 提取公共 `_STRATEGY_COLS` 追加 entry_mode/nl_text/wizard_state/created_at；`GET /api/results/<id>/summary` 响应新增 `strategy` 对象（六键，经 _jsonable），会员/游客两路径同源，权限语义不变（他人 404、异 IP 游客 401）。**模板** `gui/saas/templates/job.html`：结果区顶部（metric-strip 前）新增 `#box-strategy` 折叠卡——`.sec-toggle`+`.sec-body`（grid-template-rows 0fr→1fr，既有折叠组件）默认折叠，摘要行「策略名 · 入口类型 · 创建于 <本地时间>」（LabUI.fmtLocalTime；entry_mode 映射 自然语言描述/快速向导/策略代码，存量回退 nl_text→nl 否则 yaml，兜底「未知」）；展开按入口分态：NL=原文+编译后 YAML，向导=条件组可读描述（复刻 strategy.html wizardSummaryHtml）+YAML（无快照降级 YAML+说明），代码=YAML 原文；YAML 用既有 `pre.compiled-yaml.pv` 深色块+行号+简高亮（hlYamlLine 与新建页同款）。零新色相/字体，escH 全量转义。**测试**：tests/test_gui_saas.py test_detail_endpoints 补 strategy 断言 + 新增 test_detail_strategy_info_modes（nl 入口）；目标 94 passed；全量 `uv run python -m pytest tests/ -q` → 2388 passed, 4 skipped 零回归。**未做**：8081 lab_result.html 未同步（任务书标注非必须）；ECS 部署仅需发代码重启。**验证命令**：`/home/van/.local/bin/uv run python -m pytest tests/ -q`。未 git commit，等用户/主代理审批。

---

## Archive: QRE-CUMRET-CHART（收益曲线口径修复：chart_data 新增 cumret 键 + 前端优先用 cumret + job#58/#66 ECS jsonb 补丁）

## Implementation Summary
---

## Archive: QRE-PRICE-COLUMN-PARAM（web 高级参数「入场价格 / 出场价格」：引擎 exit_price_column 独立参数 + open/close/vwap 全链透传）

## Implementation Summary

**引擎层**：`portfolio/single_symbol.py`、`single_symbol_vectorized.py`、`batch.py`、`shared.py` 的请求 dataclass 新增 `exit_price_column: str | None = None`（None=跟随入场价列，默认行为逐字节不变）；simulator 卖出点（single_symbol.py:244）、vectorized `_Prepared.exit_prices` 数组 + `_run_loop` 卖出点（同列时复用 entry 数组零额外内存）、shared `_execute_due_sells` 卖出价（shared.py:302）三路径统一改读出场价列；shared `_prepare_frame` 列裁剪白名单加出场价列；batch 两分支透传给 SingleSymbolBacktestRequest。**vwap 数据可得性**：`public.stock_daily` 有原生 `vwap` 列（元、原始价尺度，20 号数据字典 §2）——不做 amount/vol 换算；hfq（QRE_PRICE_BASIS=raw）下 `postgres.py::load_daily_bars` 既有复权循环 `(open,high,low,close,pre_close,vwap)×adj_factor` 已覆盖 vwap 同尺度，新增打桩测试锁定。**透传链**（仿 max_holding_days/8b9312c 模式）：`gui/engine.py` 新增 `PRICE_COLUMN_CHOICES=("open","close","vwap")`、`_resolve_price_columns`（缺省 open、出场缺省跟随入场、非法值 ValueError）与 `_extend_market_fields`（vwap 等非默认列并入装配 market_fields 防 frame 缺列）；run_backtest/_run_via_module 新增 `entry_price/exit_price` 形参，run 记录与 precheck full_params 携带（None 不落键），三模式（single/batch/shared + streaming batch）请求对象均注入；`worker/runner.py` execute_job 透传 params.entry_price/exit_price（空串归 None）；`gui/strategy_lab_routes.py` /api/run 白名单校验 + 透传，`templates/run_detail.html` 全量重跑 fullParams 链同步。**UI**：`gui/saas/templates/new.html` 与 `gui/templates/lab.html` 高级参数区各加「入场价格/出场价格」两个下拉（次日开盘价/次日收盘价/次日均价 VWAP，默认开盘价），buildParams/buildRunPayload 携带，预览栏 paramsYaml 同步两行。**测试**：新增 `tests/test_price_columns.py` 13 例（vwap 成交价、出场独立性、默认跟随逐字节不变、5 组 entry×exit sim↔vec 等值、batch 两 impl 透传、shared 独立/默认、raw 模式 vwap×adj_factor 缩放）；test_gui_engine.py +4（resolve/extend 语义、run 记录+透传+非法拒绝、precheck full_params 携带）；test_worker.py +1（TestParamPassthrough：落库值到达 run_backtest kwargs、旧 job 无键传 None）。全量 `uv run python -m pytest tests/ -q` → 2385 passed, 4 skipped 零回归。**冒烟**（/tmp/qre_price_smoke.py，不入仓）：000001.SZ/600519.SH/000002.SZ/300750.SZ × 2025 全年 × 双均线（sma_5×sma_20，batch/vectorized），entry open/close/vwap 各一次，35 笔买入逐笔对库（load_daily_bars 同口径）0 mismatch，三档总收益 6.29%/5.81%/6.97% 互异确认切换生效。未 git commit，等用户/主代理审批。

---

## Archive: QRE-BATCH-IPO-INJECTION（batch 全市场净值曲线新股初始资金注入计为收益修复）

## Implementation Summary

**根因**（job#66 实证）：`portfolio/full_market_report.py::build_full_market_equity_curve` batch 分支逐日对各股 total_equity 直接求和，中途 IPO 股票首日带完整 initial_cash 进入总和被计为收益（job#66：+220.3% vs 真实 −14.76%）。**改动**：①该函数 batch 分支重写——concat 各股曲线为单表、按 (trade_date, symbol) 去重排序，groupby 聚合日级 total_equity/cash/market_value/position_count；daily_return 交集口径：`prev` 表把每股净值映射到下一全局交易日，merge 得「昨日∩今日均在市」子集，daily_return_t = Σe_t/Σe_{t-1}−1，新股进入当日贡献 0（注入=外部现金流），cumulative 累乘；同时消除旧 O(日×股) 逐日过滤循环。②`portfolio/risk.py::summarize_equity_curve`：曲线含 daily_return 列时 returns 取该列、total_return 取 cumulative_return 末值，否则维持 pct_change——shared_cash/个股曲线无 daily_return 列或两者等价，数值不变。③`build_strategy_performance` batch 分支：新增 `_aggregate_batch_total_return(summary)`（Σfinal_equity/Σinitial_cash−1，两列缺省时回退 None→曲线口径），strategy_total_return 与 excess_return_vs_buy_hold 现算逻辑共用该值；buy_hold_return 经核查为 per-symbol 均值（analytics.py），不受注入影响未动；shared_cash 分支未动；前端 gui/ 直读 equity_curve.csv（lab_result/risk_report/engine），零改动。**测试**：tests/test_full_market_report.py +3（TestBatchEquityCurveIpoInjection：进入日 daily_return=104000/103000−1 显式排除注入、strategy_total_return==(109000+97500)/200000−1 手工复算、缺资金列回退曲线口径）；全量 `uv run python -m pytest tests/ -q` → 2368 passed, 4 skipped 零回归。**job#66 离线复核**（/tmp/verify_job66_injection_fix.py，不入仓）：Σfinal/Σinitial−1=−14.756% 精确；修正日收益 min=−0.42%/max=+0.37%（旧 ±25% 尖峰消失），累乘 +9.29%（日复利等权口径，与资金加权 −14.76% 的差为再平衡溢价，口径差异已记录 06 决策日志）。未 git commit，等用户/主代理审批。

---

## Archive: QRE-PARAM-PASSTHROUGH（SaaS 高级参数落库与引擎生效一致性：max_holding_days 参数权威化）

## Implementation Summary

**链路核查**：web 表单 → `POST /api/jobs`（jobs.params 原样落库）→ worker claim（17 协议 params_json）→ `worker/runner.py::execute_job` → `gui/engine.py::run_backtest` → 引擎请求。费率类（commission_rate/min_commission/stamp_tax_sell/滑点）经 `params.profile_overrides` 全链透传且 ECS 实证一致（job 59-71 落库值 == worker run 记录 status.json；job 62 round_trips 费用非零且与费率手算吻合）；历史「费用为 0」系 C5 params_json 丢弃事故，已修且有回归。**实证残留根因 = max_holding_days**：worker 从不传该参数且 run_backtest 无此形参，引擎只读 YAML `holding.max_holding_days`（spec.py:90），前端仅在 YAML 缺 holding 键时注入表单值（new.html applyName）——ECS job 65/66 落库 max_holding_days=0（用户要不限）但 YAML=60，引擎实跑 60 天。**修复**（params 显式给时为权威，覆盖 YAML holding 节）：①`gui/engine.py` run_backtest/_run_via_module 新增 `max_holding_days: int | None`，纯函数 `_override_holding_days`（None=不动 YAML；0=不限；frozen spec 走 dataclasses.replace），precheck full_params 与 run 记录同步携带；②`worker/runner.py` 透传 params.max_holding_days（含 0，不按 falsy 丢弃）；③`gui/strategy_lab_routes.py` /api/run + `templates/run_detail.html`：8081 precheck→全量重跑链同样透传（整数校验 ≥0）；④`gui/saas/templates/new.html` buildParams：留空落库 0（=不限），对齐占位符承诺。**测试**：test_gui_engine.py +2（覆盖语义 None/20/0 且原 spec 不变；run_backtest 记录+透传，0 透传/缺省不落键）；test_worker.py +2（TestParamPassthrough：params 全字段端到端到达 run_backtest kwargs；旧 job 无键传 None）。全量 `uv run python -m pytest tests/ -q` → 2365 passed, 4 skipped 零回归。未 git commit，等用户/主代理审批。

---

## Archive: QRE-P8-PANEL-DAILY（panel_factors 全体系日更接线 + 8080 纳管 + P5 risk pair-aware warmup 修复）

## Implementation Summary

indicators 侧：新 `scripts/panel_factors_daily.py`——仿 alpha191_daily 的 watermark 幂等范式，8 步串行（pit_panel→value_size→quality→growth→liquidity→risk→alpha101→channel_b），每步独立 `python -m panel_factors.*` 子进程（内存隔离，守 R-MEM-001）；watermark=各表 max(trade_date)（通道B 取 alpha_125d_000300 非空最大日），已覆盖 stock_daily 最新交易日则跳过退出 0，否则从 watermark+1 补到最新（各模块内部 warmup 前推 + 裁剪 + ON CONFLICT 覆盖，增量==全量）；pit 失败跳过 value/quality/growth 三个下游，价格类步骤照常；任一步失败退出 1 可安全重跑；支持 --only/--start/--end/--force。新 `scripts/verify_p8_incremental.py`（抽样 20 股单日全市场复算逐值比对 + 连跑两次幂等；截面因子必须全市场复算，--codes 子集会破坏横截面口径——首轮假阳性即此因）。**P5 risk 修复**：`risk.py` 新增 `_pair_aware_warmup_start`（SELECT max(trade_date) ... row_number() rn=1326，按个股实际行数供给 warmup），替代单纯 get_warmup_start（市场交易日口径）——回归族「最近 1320 个有效样本对」窗口下，窗口期停牌 >20 日的股票（实测 290 只）原会被误产 NaN；修复后 2026-10-09 全市场单日复算与存量全量值逐值一致。systemd：`deploy/systemd/panel-factors-daily.{service,timer}`（OnCalendar=Mon..Fri 17:45，Persistent=true，已 cp /etc/systemd/system + enable --now）。QRE 侧：`gui/admin.py` 新增 `PANEL_FACTOR_TABLES` 8 表并入 `managed_factor_tables()` 两条路径（pending→日更中，参与滞后判定/健康灯），TIMER_UNITS 增 panel-factors-daily.timer，EXPECTED_COLUMNS_SCRIPT 注入 panel 各模块权威列清单（_pit 97/value 12/size 3/quality 110/growth 27/liquidity 35/risk 25/alpha101 31 + momentum_close 并入通道B 8 列）；`gui/daily_jobs.py` 增「panel-factors」管线；`templates/admin.html` UNIT_TO_PIPELINE 增 'panel-factors-daily.timer'→'panel-factors'。**测试**：indicators `pytest tests/test_panel_factors_daily.py tests/test_alpha191_daily.py` 24 passed；QRE `pytest tests/test_gui_admin.py tests/test_gui_admin_manage.py tests/test_gui_admin_p3b.py tests/test_gui_app.py tests/test_gui_saas_console.py` 146 passed（更新 4 例 pending 语义改用假设表 stock_daily_newfactor + managed 断言并入 PANEL_FACTOR_TABLES，新增 2 例）。**实测耗时**（首次追数 10-13~10-16 四交易日，全市场）：pit 1.3 / value_size 3.9 / quality 1.5 / growth 1.2 / liquidity 0.5 / risk 0.9 / alpha101 1.1 / channel_b 1.0 min，合计 ~11.4min；单日全市场复算（验证轮）：45s/199s/93s/63s/23s/87s(修复后)/61s/53s。**8080 验证**：/api/admin/overview factors 表 8 张 panel 表 daily_pipeline=true 无「未接日更」徽标，lagging_tables 不含之；/api/admin/timers 含 panel-factors-daily.timer installed+active。未 git commit，等用户/主代理审批。

---

## Archive: QRE-SYMBOL-PERF-ZERO-TRADE（symbol_performance 零交易股票漏报口径修复：shared_cash symbol 集合并入 failed_orders + has_trades 标识列）

## Implementation Summary

修复 job#58 暴露的 summary.csv（5531 行）与 symbol_performance.csv（5398 行）口径不一致。**改动仅 `src/quant_research_engine/portfolio/full_market_report.py`**：①shared_cash 分支 symbol 集合从 round_trips 扩展为 round_trips ∪ failed_orders——零成交但有失败委托的股票入表（trade_count=0、win_count=loss_count=0、net_profit=0.0、win_rate=None、failed_order_count=N），原 `if rt.empty: return` 早退改为仅在两表皆无 symbol 时早退；②batch 分支过滤语义不动（有成交或有委托才入表，C 类完全无交易仍剔除），failed_order_count 透传确认上游 `batch.py::_summary_row`（:181）已产出该列，`record.get(..., 0)` 兜底缺列，引擎零改动；③symbol_performance 新增 `has_trades` 布尔列（trade_count>0；batch 侧对 NaN/None 安全），同步 `_SYMBOL_PERFORMANCE_COLUMNS` 与 `COLUMN_LABELS`（「有交易」）。**验证**：`tests/test_full_market_report.py` +3——test_failed_only_symbol_included（有交易 A + 仅失败 B 两行，B trade_count=0/net_profit=0/failed_order_count=2/has_trades=False，A has_trades=True）、test_failed_only_symbol_included_when_round_trips_empty（rt 空仍出失败行）、test_symbol_performance_filters_zero_trade_symbols 补 has_trades 映射与 failed_order_count 兜底断言（A/B 保留 C 剔除语义不变）；全文件 66 passed。全量 `uv run python -m pytest tests/ -q` 零回归。**取舍**：新增列而非复用 trade_count==0 推断——bool 列对前端更直接且侵入小（report_manifest symbol_performance 只要求 symbol+trade_count，不受影响）。未 git commit，等用户/主代理审批。

---

## Archive: QRE-DEAD-PENDING-FIX（回测引擎「dead-pending」静默吞信号修复：缩量重试 + insufficient_cash 登记 + pending 重置）

## Implementation Summary

**根因**（前置只读排查确诊）：full_compound 仓位买入股数 `raw_quantity = int(cash // price)`，当名义额+费用略超现金（典型：000002.SZ 9900 股×10.10+费用 30.9969=100020.99 > 100000）买入被拒，但 `single_symbol.py` 的 `if total_cash_needed <= cash` 失败分支什么都不做——不写 failed_order、不重置 `pending_buy_index`，而入场要求 `pending_buy_index is None`，该股后续所有入场信号被静默吞掉（job#58 有 135 只股票零交易，含 000002/000016/000725）；向量化路径注释自述「保留 dead pending 语义」。**改法**（两条引擎路径同步实现，行为严格一致）：①`markets/ashare.py` 新增 `fit_buy_quantity_to_cash(quantity, price, cash)`——先以 `cash // price`（lot 取整）为上界，再逐手（buy_lot=100）递减直到 `notional + calculate_cost(BUY, notional) <= cash`，费用含 min_commission=5 元地板（这正是 `现金/(1+费率)//价格` 估算法会错的 case），返回 0 表示一手都买不起；②两个引擎买入执行块重构：`buy_quantity <= 0`（现金买不起一手）→ 直接登记 failed_order（reason=`insufficient_cash`）+ 重置 pending；validation 通过但 名义+费用>现金 → 缩量重试，缩量 ≥1 手按缩量成交（缩量单不重跑 validate_order：同 bar 同价、仍整手、数量更小，结果必同），缩量到 0 → 登记 `insufficient_cash` + 重置 pending。fixed_cash 模式同走缩量/登记（raw 从 initial_cash 算、可负担性对当前现金）。资金充足时代码分支完全未触，既有行为逐字节不变。**验证**：新增回归 5 例——test_portfolio_single_symbol.py +2（缩量成交 9800 股+后续信号再买再卖共 2 笔往返；5000 元买 50 元股两次信号各登记 insufficient_cash）、test_single_symbol_vectorized.py +3（同两场景断言 sim==vec 完全相等 + fixed_cash 一致）；`pytest tests/test_portfolio_single_symbol.py tests/test_single_symbol_vectorized.py tests/test_ashare_market_profile.py` → 144 passed；全量 `pytest tests/` → **2357 passed + 4 skipped（85s）零回归**。**真库验证**（postgresql tushare_data）：000002.SZ 2010-01-04→2026-10-16（3919 根，stock_daily ⋈ stock_daily_momentum_close），entry `(macd_12_26_9 > macds_12_26_9) and (macdh_12_26_9 > 0)`、exit `macd_12_26_9 < macds_12_26_9`、holding_days=0、初始 10 万 → **151 笔往返 / 302 订单 / 0 failed**，首笔 2010-01-19 买入 9800 股@10.10（9900 缩量 1 手，费 30.68），sim 与 vec orders/trades/summary 逐帧相等。**遗留**：full_market_report.py batch 分支 build_symbol_performance 以 round_trips 为准，零交易股票（即便有 failed_orders）从 symbol_performance 漏掉、与 summary.csv 口径不一致——本次只修引擎未改报表层，已登记 05_PROGRESS。未 git commit，等用户/主代理审批。

---

## Archive: QRE-NL-FACTOR-AUTOCORRECT-001（NL 编译链路因子名自动纠错层：存在性校验 + 保守自动替换 + 候选提示 + prompt 注入真实目录）

## Implementation Summary

痛点（05_PROGRESS 已记录）：NL 策略编译链路中 DeepSeek 会编造数据库中不存在的因子列名（如 `rsi14`、`MACD`），产出 YAML 在因子存在性检查处失败，用户只见红色报错不知改法。本任务在引擎/编译器侧落地纠错层（8080 与 8081 共用 `strategy_lab_routes.py` / `nl_compiler.py`；8081 冻结页 `gui/lab*.py` 零改动）。①**新 `gui/factor_correction.py` 纯函数层**（零 DB 零 IO）：`auto_fix_column` 保守三规则——归一化（小写+去下划线）等价（`rsi14`→`rsi_14`、`MACD_12_26_9`→`macd_12_26_9`）、唯一候选归一化编辑距离 1 且次优差距 ≥3、唯一前缀匹配（`macd`→`macd_12_26_9` 仅当 macd 系列只有一列；signal/histogram 并列则不纠正给候选）；`suggest_similar_columns` 归一化距离排序 Top-5（确定性 tie-break）；`correct_factor_fields` 对解析后 mapping 就地改写 target（alias 与信号表达式不动）——同表候选优先，同表为空跨 8 个标准因子表兜底（列名对、表写错直接换表）；`COMMON_FACTOR_TARGETS` 18 条常用已落库列；`format_corrections_note`/`format_unresolved_hint` 中文提示。②**`nl_compiler.compile_nl` 集成**：missing_factors 判定前先跑纠错；全部纠正成功 → safe_dump 重写 YAML（重写后复跑 validate_yaml，异常兜底退回原 YAML）正常返回，warnings 标「已自动纠正因子名…X→Y」并附 `corrections` 字段；仍有未解决项 → 照旧入补因子队列，error 由「编译失败」改为 actionable 提示（每因子 Top-5 候选 + 常用因子清单），响应附 `suggestions` 字段。③**prompt 注入**：`_DSL_DOC` 追加「严禁编造因子名」硬约束（命名格式 + 错例），`build_system_prompt` 追加 COMMON_FACTOR_TARGETS「常用已落库列」。④**`strategy_lab_routes` 手工 YAML 通道**（POST /api/strategies/create mode=manual）同样先纠错再入队，错误响应带 suggestions/corrections。测试 **tests/test_gui_factor_correction.py +17**（纯函数 9：归一化等价/大小写/唯一前缀/歧义前缀不纠正/歧义距离不纠正/唯一距离1/精确不动/候选排序/格式化；mapping 层 4：精确不动/编造自动纠正/无匹配给候选/跨表换表；prompt 注入 1；compile_nl 集成 3：编造纠正成功返回 ok 且不入队、精确匹配原样保留不 dump、无匹配入队且 error 含候选与常用清单）。验证：`uv run pytest -q` → **1960 passed + 4 skipped**（1943 + 17）。真实演示（内存 lookup 桩）：`rsi14` + `macd_x_12_26_9` → 自动纠正为 `rsi_14` + `macd_12_26_9` 并标注；`rsi_99` → 报错附候选 rsi_14/rsi_6/sma_20/macd_12_26_9。无 CR（用户直接指派）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-007（「聚类动量」页 v7 前端渲染性能：Top/Bottom 50 截断 + 精简列不输出隐藏单元格 + 行级 content-visibility + sticky 仅展开模式 + 分区局部重渲）

## Implementation Summary

用户反馈「聚类动量」tab 卡顿严重；排查确认瓶颈纯在前端 DOM（服务端 RSS 正常、API 1MB/0.22s、无轮询）：concept 分区 1066 行 × 20 列 ≈ 2.1 万单元格，每格带内联热力 style，首列 position:sticky（大行数 sticky 是已知重绘杀手），且每次排序/切窗/切列整表重渲。纯前端渲染优化（API 契约与数据内容零变化，pool_momentum.py 零改动，8081 零改动）：①**默认 Top/Bottom 50 截断**（admin.html）：新 `MOM_EDGE_N=50` + `momShowAll={concept,state}` 状态；momTable 排序后默认只渲染 `slice(0,50) + slice(-50)`，中间插 `.mom-gap` 提示行（「… 中间省略 N 行」+「显示全部 N 行」按钮 `.mom-expand`，展开后表尾给「收起为 Top/Bottom 50」`.mom-collapse`）；加速度排序下 Top/Bottom 正是顶部观察 + 底部回避名单两端。②**精简列不再渲染后隐藏**：momTable 行/表头改为数组 cells/heads 按需 push——非当前窗口 fwd、回看 ret×4、vwap×2、vol_chg、short_rank 等 mom-col-x 扩展列仅在 `momFull=true` 时生成 td/th（数据仍在 JS 内存，「展开更多列」时才渲染）；CSS `.mom-compact .mom-col-x{display:none}` 规则删除。③**行级渲染跳过**：CSS `.mom-scroll tbody tr { content-visibility: auto; contain-intrinsic-size: auto 36px; }`，屏外行不参与首屏布局/绘制（「显示全部」大表时收益最大）。④**sticky 仅展开模式启用**：首列 sticky 四处选择器改挂 `.mom-scroll.mom-sticky`（momFull 时才加该类——横向滚动只在全列时出现，精简 9 列一屏放得下无需 sticky）。⑤**分区局部重渲**：momBindPoolLinks 拆为 `momBindPoolLinksIn(el)` + `renderMomentumTable(poolType)`（只重建对应分区 tbody）；展开/收起只重渲本分区；排序键两表共享，表头排序仍两表一起重渲（state 仅 14 行成本可忽略，保证箭头一致）；窗口切换走 renderMomentum 两表重渲（热力/高亮口径变化必须）。行/表头构建全程数组 join，无 O(n²) 字符串拼接。回避徽章、行热力、回避汇总卡、详情面板、成员明细功能全部保留（momAvoidHtml/momSummaryHtml/loadMomentumDetail 零改动）。渲染规模（真库 concept 1066 + state 14）：优化前 1066×20 + 14×24 ≈ 21,656 单元格；优化后默认视图 (50+50+1)×9 + 14×13 ≈ 1,091 单元格（≈ −95%），展开更多列（全 20 列）后 101×20+14×24 ≈ 2,356。测试 +1（79 总）：TestAdminPageV6 新增 test_v7_render_perf_markup（MOM_EDGE_N=50/momShowAll/mom-expand/显示全部/mom-collapse/mom-gap/mom-compact 不存在/mom-sticky/renderMomentumTable 标记）；test_v5_markup 删 mom-compact 断言；test_v5_css 改断言（.mom-scroll.mom-sticky、.mom-compact 不存在、content-visibility: auto、.mom-gap）。验证：`uv run pytest -q` → **1943 passed + 4 skipped**（1942 + 1）；admin.html 内联 script node --check 过；`sudo -n systemctl restart qre-gui` active；curl /admin 200 含新标记、overview API 200（988KB / 0.12s）。无 CR（用户直接指派）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-006（「聚类动量」页 v5 榜单可读性：横向滚动 + 首列 sticky + 精简列开关 + 详情面板上移）

## Implementation Summary

用户反馈两个 UI 问题：concept 榜单 17+ 列横向溢出挤压、点池名后详情渲染在页面最底部需长滚。修复（改动集中 admin.html + style.css + 测试，pool_momentum.py 零改动、零新纯逻辑）：①**榜单横向滚动 + 首列 sticky**：momTable 输出包一层 `<div class="mom-scroll">`（overflow-x auto）；CSS 首列 th/td `position: sticky; left: 0`（thead 角格 z-index 3、tbody z-index 2，右侧 1px 分隔影），斑马纹行首列背景 var(--bg)、热力行（tr 带 inline style）首列 `background: inherit` 保持热力连续——为此 momTable 行只在 heat 非空时才输出 style 属性（避免空 style 匹配 tr[style] 导致首列透明）。②**默认精简列 + 「展开更多列」开关**：momPctCell/momTh 加可选 cls 参；非当前窗口的 fwd 列、回看 ret×4、vwap×2、vol_chg、短窗排名标 `mom-col-x`，前端新状态 `momFull=false` 时容器加 `.mom-compact`（CSS `display:none` 隐藏扩展列）；精简列 = 池名（含⚠回避徽章）/股票数/当前窗口 fwd/速度排名/加速度/共振/事后×3（state 分区 + 事件 4 列），空数据 colspan 随视图动态（concept 9/20，state 13/24）；窗口切换按钮旁新 `#btn-mom-cols` 开关（文案「展开更多列」↔「收起为精简列」，切换重渲）。③**详情面板上移**：删除底部 `data-section="mom-detail"` 折叠区；新 `#mom-detail-panel` 固定在 `#mom-summary` 汇总卡之下、榜单之上（含标题 `#mom-detail-title` + `#mom-detail-close` 关闭按钮 + 原 #mom-detail/#mom-members 容器）；`loadMomentumDetail` 开头 unhide 面板、写标题、`scrollIntoView` 平滑滚动到位，点其他池原地替换内容，关闭按钮隐藏并清空。④**成员明细限高内部滚动**：renderMomentumMembers 输出包 `.mom-scroll mom-members-scroll`（max-height 420px，overflow auto；表头 sticky 沿用全局 `thead th` 规则）。concept 分区标题改注「点击池名在上方详情面板看 250 日时序 + 成员明细」。8081 零改动。测试 +2（78 总）：TestAdminPageV6 模板标记（面板/关闭按钮/位置序：mom-summary < mom-detail-panel < mom-concept、旧底区移除、btn-mom-cols/mom-col-x/mom-compact/mom-scroll/mom-members-scroll）+ CSS 规则断言（sticky left:0、overflow-x、compact 隐藏、限高 420px）。验证：`uv run pytest -q` → **1942 passed + 4 skipped**（1940 + 2）；admin.html 内联 script node --check 过；`sudo -n systemctl restart qre-gui` active；curl /admin 200 含新标记（24 处）、overview API 200（真库 latest 2026-09-03，concept 1066/state 14）、detail（state/量比:突增）200 ok。无 CR（用户直接指派）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-005（「聚类动量」页 v4 底部减速回避名单：⚠ 回避徽标 + 顶部回避卡 + 声明卡补句）

## Implementation Summary

依据 cluster-ashare M7 全历史描述性实验结论（fwd_ret_3 最弱 Bottom10 池未来 3-5 日显著继续跑输，日均约 −0.2%，NW t=−3.86，FDR q=0.001，20 日后消失；顶部信号全部无效），8080「聚类动量」tab 落地回避名单。①**纯函数 `compute_bottom_avoid`**（gui/pool_momentum.py）：单 pool_type 截面内 fwd_ret_3（window 参数化）最低的 `AVOID_BOTTOM_N=10` 个池标 `avoid=True`；fwd 为 None 或 `n_stocks < AVOID_MIN_STOCKS=10`（成员过少信号不稳）不参与判定；有效池不足 10 时全部回避（state 组 14 有效池 → 最低 10 个回避）；纯函数 `avoid_list` 输出按 fwd_ret_3 升序的摘要。②**overview payload** 加 `avoid`（按 pool_type 分组：pool_key/fwd_ret_3/n_stocks）与 `avoid_bottom_n`/`avoid_min_stocks`；历史回看模式复用 trade_date 链路，回避按选中日截面计算保持 point-in-time；note 补回避口径。③**前端**（admin.html）：榜单行池名后加 `<span class="mom-avoid">⚠ 回避</span>` 徽章（title 注明依据「短窗最弱十分位，历史验证未来 3-5 日平均继续跑输约 0.2%/日（NW t=−3.86，FDR q=0.001，20 日后消失）」）；新 `#mom-avoid` 顶部汇总卡（`momAvoidHtml`，concept/state 各一行：池名 + fwd_ret_3，点击复用 `.mom-pool` 链接跳详情——renderMomentum 先渲卡再由 momBindPoolLinks 统一绑定）；声明卡新增一条：底部回避名单口径 + 验证数字 + 「顶部榜单各信号全历史验证均无选股价值——本页主要价值 = 底部回避名单」+ 历史回看 point-in-time 说明。④**style.css 纯追加**：`.mom-avoid` 实心白底 + 红边框徽章（区别于行热力半透明红/绿背景）、`.mom-avoid-card` 左侧红边。8081 零改动。测试 +11（76 总）：compute_bottom_avoid 6（bottom_n 标记/None 剔除/n_stocks 剔除/有效池不足/空与全 None/window 参数）、avoid_list 1、overview avoid 标记+payload 1、point-in-time 1、路由 avoid 字段 1、模板 v4 标记 1。验证：`uv run pytest -q` → **1940 passed + 4 skipped**（1929 + 11）；`sudo -n systemctl restart qre-gui` active，curl /admin 200、overview API 含 avoid 字段。真库 2026-08-31 回避名单：concept = 申万L3:疫苗（−5.73%）/医疗研发外包（−5.55%）/半导体设备（−4.96%）/通信线缆及配套（−4.80%）/半导体材料（−4.76%）/CRO（−4.02%）/国家大基金持股（−3.63%）/中芯概念（−3.38%）/申万L2:电子化学品Ⅱ（−3.35%）/申万L3:电子化学品Ⅲ（−3.35%）；state 有效 14 池取最低 10（跳空:低开 −2.35% 居首）。无 CR（用户直接指派）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-004（「聚类动量」页 v3 历史回看：日期选择器 + 事后验证列 + 验证摘要条）

## Implementation Summary

8080「聚类动量」tab 支持任意历史交易日回看，用于验证「加速度 Top 池是否随后跑赢」。①**日期选择器**：overview 新查 `DISTINCT trade_date WHERE fwd_ret_3 IS NOT NULL`（249 个可选日，降序）入 payload `dates`；`pool_momentum_overview(db_url, trade_date=None)` 加日期参（缓存键同步含日期），缺省仍为最近 fwd 已补齐日；前端 `#mom-date` 下拉，切换即重拉该日完整榜单（表天然 point-in-time：当日排名/共振只用 ≤T 数据）。②**事后验证列**（纯函数 `compute_post_returns`）：SQL 先取 T 之后 DISTINCT 交易日 LIMIT 20，再拉 (T, T+20日] 的 fwd_ret 日序列；post_w = ∏(1+fwd_ret)−1 over (T, T+w]，不足 w 日或窗口内含 None → None（未满窗口）；榜单两分区各加「事后3日/5日/20日」三个可排序列。③**验证摘要条**（纯函数 `accel_top_summary`）：按 pool_type 各算一行——加速度 Top 10 池（加速度 None 的池不入 Top）的 post_5 均值/中位数/胜率 vs 全体池 post_5 均值（缺失值各自剔除，全缺 → None）；前端 `#mom-summary` 卡片渲染。④**单池详情/成员明细随选中日期**：detail 加 `end_date` 参（SQL `trade_date <= :end`），members 已有 trade_date，前端均传 momData.latest_date。⑤**真库验证**：`?trade_date=2025-09-05` → concept 加速度 Top10 post_5 均值 +0.19%（胜率 0.3）vs 全体 1064 池 +0.88%；state Top10 post_5 均值 +0.64%（胜率 0.9）vs 全体 14 池 +0.95%——该日加速度 Top 并无超额，如实呈现；2025-08-21（最早日，20 日窗口满）concept Top10 post_5 −1.92% vs 全体 −0.29%，Top1 赛马概念 post_20=+16.14%；detail end_date=2025-09-05 序列正确截断（末日 2025-09-05）；members trade_date 生效。测试 +11（65 总）：compute_post_returns 复利/None 阻窗/缺序列 3、accel_top_summary 3（含 None 排除、accel None 不入 Top 但入全体）、overview 日期参数+post 列+摘要 2、无 post 日期全 NULL 1、detail end_date 1、路由带参 1（其中模板标记断言合并）。验证：`uv run pytest -q` → **1929 passed + 4 skipped**（1918 + 11）；admin.html script node --check 过；`sudo -n systemctl restart qre-gui` active，curl 全 200。无 CR（用户直接指派）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-003（「聚类动量」页升级 M7 v2 前瞻口径：fwd_ret 主口径 + 事件池统计 + 一日滞后处理）

## Implementation Summary

cluster-ashare M7 v2 已上线（pool_momentum_daily 新增 fwd_ret / fwd_ret_3/5/20/50 / next_premium / survive_3 / survive_5 / win_rate_1 九列，250 日已回填），本任务把 8080「聚类动量」页切到前瞻口径（用户已批准）。①**主口径切换**：`compute_acceleration` / `compute_heat` 加 `metric="fwd_ret"` 默认参（回看 metric="ret" 可选），`resonance_flag` 改判 fwd_ret_w>0 且 vwap_ret_w>0 且 vol_chg_w>0；_SELECT_COLS 扩到 26 列（ret×4 回看对照 + fwd×4 + vwap×4 + vol×4 + 事件×4）。②**末日滞后处理**：overview 新查 `max(trade_date) WHERE fwd_ret_3 IS NOT NULL`，榜单默认展示最近 fwd 已补齐日；payload 加 `latest_date_overall` / `fwd_lag` / `fwd_note`，fwd_lag=true 时前端红色 ⚠ 提示「前瞻收益 T+1 收盘后补齐：末日 X 的 fwd 列仍为 NULL（正常一日滞后），榜单展示最近已补齐日 Y」；完全无 fwd 数据时回退最新日不炸（加速度/热力全 None）。③**事件池**：行级 `has_event` = 四事件列任一非空；state 分区表加 4 列（次日溢价/存活3日/存活5日/胜率T+1，可排序，survive 末日数天 NULL 正常），concept 分区不显示；section 标题注明「对标同花顺涨停复盘的前瞻统计」。④**前端**：主榜单列重排为 fwd×4（主，窗口高亮）+ 回看ret×4（列名标「回看」）+ vwap×2 + vol_chg + 排名×2 + 加速度 + 共振（concept 17 列 / state 21 列）；窗口切换排序键改 `fwd_ret_w`；声明卡整体改写（主口径=当日成分等权再平衡前瞻收益对标东财板块指数、回看仅对照、artifact 池回看是同义反复、concept 快照前视偏差保留、一日滞后说明）；单池详情主线换 fwd_ret_3/20/50 + fwd_ret（粗色），回看 ret_3/20/50 浅色辅线，vwap/vol_chg 辅线保留；成员明细表不变、表头注明「成员回看指标（描述性）」。⑤**测试**（+9，54→63 总；v2 口径切换涉及旧 fixture 同步改 fwd 列）：fwd 排名独立于回看、metric="ret" 显式可选、heat 用 fwd、共振看 fwd、has_event 三态（artifact 池/普通 state/concept）、fwd_lag 三态（滞后展示补齐日+提示文案/无滞后/全表无 fwd 回退不炸）、detail fwd 序列与末日 NULL、模板 v2 标记断言。验证：`uv run pytest -q` → **1918 passed + 4 skipped**（1909 + 9）；admin.html script node --check 过；`sudo -n systemctl restart qre-gui` active。真库 curl 实测：overview latest_date=2026-08-31（overall 2026-09-01，fwd_lag=true，提示文案正确）；concept fwd_ret_3 榜首「昨日打二板以上表现」fwd3=+15.38%（heat3=1.0、共振=true），其次融资融券/昨日连板；state 分区 8 个 artifact 池 has_event=true 且 next_premium/win_rate_1 有值（跳空:高开 win_rate_1=0.658），非 artifact 池（趋势:sma20上方5日）has_event=false；detail（state/连涨:3日）250 日 fwd_ret 序列末日 None 正常。无 CR（用户已批准口径切换）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-002（「聚类动量」页三项优化：池内个股明细、表头排序、行热力色阶）

## Implementation Summary

在 POOL-MOM-001 基础上三项增强，8080 管理台「聚类动量」tab，全程只读。①**池内个股明细**：新 API `GET /api/admin/pool-momentum/members?pool_type=&pool_key=&trade_date=`（trade_date 缺省=池动量表最新交易日）——成员名单 concept 取 cluster.company_tags 快照（与 M7 管线 fetch_members 同口径，含全部 layer，前视偏差注明）、state 取当日 cluster.daily_tags（point-in-time）；个股指标由 `compute_member_metrics` 纯函数即时算自 public.stock_daily（51 交易日窗口：ret_w=close×adj_factor 比值−1、vwap_ret_w=vwap 比值−1、vol_chg_w=近 w 日均量/近 50 日均量−1，窗口内缺行→None，与管线宽表 shift/rolling(min_periods) 语义一致）；名称 LEFT JOIN reference.stock_basic（内层 try/except 降级无名称不拖垮页面）。前端单池详情区在 7 序列图下新增「池内个股明细」表（代码/名称/收盘/ret×4/vwap×2/vol_chg×2，默认 ret_3 降序）。**真库口径验证**：华为概念 771 成员中 770 只有行情（== 池表 n_stocks 770），成员等权平均 ret_3=0.017031048806369808 与 cluster.pool_momentum_daily 池值**逐位相等**。②**表头排序**：主榜单全部数值列（n_stocks/4 窗 ret/4 窗 vwap/vol_chg_w/速度排名/短窗排名/加速度）+ 成员明细全列点击表头切换升降序，当前列标 ▼/▲，None 恒排末位；纯前端 `momGenericSort`（Python 侧同口径纯函数 `sort_rows` 供默认序与测试）。③**行热力**：后端纯函数 `compute_heat` 在 overview 按 pool_type 组内对每个窗口算 ret_w 截面分位 heat=2×分位−1 ∈ [-1,1]（抗极值，并列共享，None→None，单有效值→None）；前端 `momHeatColor` 按 A 股红涨绿跌映射 rgba 透明度（0.06+0.30×|heat|），行背景渐变，切换窗口随 momWindow 重算；「长弱短升」高亮自背景色改为**左侧 4px 绿边 + 池名加粗**（style.css 旧 .mom-hl 背景规则移除——纯追加惯例的例外，避免与热力背景冲突，注释注明）。页面声明卡同步（热力口径 + 高亮新呈现）。8081 零改动。测试 tests/test_gui_pool_momentum.py +21（45 总：sort_rows 3、compute_heat 4、compute_member_metrics 手算/缺当日/缺 t−w/短历 vol 4、members 数据层 6（含名称降级、空成员、无行情）、members 路由 2、模板标记 1）。验证：`uv run pytest -q` → **1909 passed + 4 skipped**（1888 + 21）；admin.html script node --check 过；`sudo -n systemctl restart qre-gui` active；curl /admin 200；members API 两池类型真库 200（华为概念 771 成员带名称/全指标，量比:突增 state 池正常）。无 CR（用户直接指派优化）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-001（8080 管理台新增「聚类动量因子研究」tab：cluster-ashare M7 池动量管线只读展示）

## Implementation Summary

8080 管理台 admin.html 新增第 8 个 tab「聚类动量」（data-tab="mom"），只读 `cluster.pool_momentum_daily`（PK (trade_date, pool_type, pool_key)；concept 1066 池 + state 14 池，已回填 250 交易日约 27 万行），全程只读不写库。①**数据层** `gui/pool_momentum.py`（新，照抄 market_risk.py 模式：`_store` + `_cached` TTL 300s + ok=False 自降级）——`pool_momentum_overview`（max(trade_date) 当日全截面 → 按 pool_type 分组 → 组内 `compute_acceleration` 排名 → `sort_by_acceleration` 降序）；`pool_momentum_detail`（单池近 250 日 ret_3/ret_20/ret_50 + vwap_ret_3/50 + vol_chg_3/50 序列，DESC 查出后反转升序；pool_type 白名单校验）。②**纯逻辑**（零 DB 直接可测）：`rank_desc`（降序竞争排名、并列共享名次、None 不参与）；`compute_acceleration`——速度=ret_50 排名，加速度=ret_50 排名−ret_3 排名（正=短窗跃升），「长弱短升」=速度排名>n/2 且短窗排名≤max(1,n//10)；`resonance_flag`——ret_w>0 且 vwap_ret_w>0 且 vol_chg_w>0（严格大于；vol_chg_50 构造上恒 0 故 w=50 永不共振，页面注明）；`sort_by_acceleration`（None 恒末位）。③**路由**（app.py）：`GET /api/admin/pool-momentum`、`GET /api/admin/pool-momentum/detail?pool_type=&pool_key=`。④**前端**（admin.html）：口径与偏差声明卡（concept 池当前快照前视偏差 demo 接受 / state 池 point-in-time 无偏差 / 加速度口径 / 共振口径 / 免责声明）、最新交易日概览卡（日期+两池数量）、窗口切换按钮（3/5/20/50，切换赚钱效应列高亮+共振口径+排序列，默认按加速度降序）、concept/state 两分区榜单表（池名可点击、n_stocks、4 窗 ret、4 窗 vwap_ret、当前窗 vol_chg、速度排名/短窗排名/加速度（带+号）/共振标记；长弱短升行 `.mom-hl` 绿色高亮）、单池详情 section（点击池名拉 detail API，复用 `riskSvgLine` inline SVG polyline 渲 7 条序列，零新前端框架）。⑤**style.css 纯追加**（.mom-hl/.mom-hl-demo/.mom-win）。8081（lab*.py）零改动。测试 `tests/test_gui_pool_momentum.py` +24（纯逻辑 12：排名/加速度/长弱短升/共振/排序；数据层 7：fake store 分组排名/空表/DB 挂/查询失败/详情升序/空池/非法参数；路由 3；admin tab 存在性 1）。验证：`uv run pytest -q` → **1888 passed + 4 skipped**（基线 1864 + 24 净增，全绿）；admin.html 单 script 块 node --check 过；`sudo -n systemctl restart qre-gui` 后 is-active=active；真库 curl 实测——/admin 200 含 data-tab="mom" 与 API 路径（3 处命中）、/api/admin/pool-momentum 返回 latest=2026-09-01、concept 1066 + state 14（榜首 比亚迪概念 加速度 +766、ret_50 弱（-8.9%）而 ret_3 急升（+6.2%）的真实长弱短升样例）、detail（concept/华为概念、state/量比:突增）均返回 250 日序列 ok。`git diff --name-only HEAD` 仅 app.py/admin.html/style.css + 两个新文件。无 CR（用户直接指派的 demo 页，无架构/数据模型变更）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-RESULT-030（B 层关键词换代：jieba 碎片词 → 东财+同花顺概念板块成分；8080 总览「概念标签源」卡片）

## Implementation Summary

跨仓任务。cluster-ashare 侧（详见该仓 README/docs）：新 `src/tags_lb_concept.py` 双源采集 B 层概念板块成分（东财 akshare 接口 + 同花顺自带分页抓取——akshare 1.18.x 已删 cons_ths；q.10jqka.com.cn 落地页 + page_info + 无 field 段 ajax 翻页、hexin-v 现算、尾页空表终止、回绕页去重、浮点代码截断映射 stock_basic.symbol）、`scripts/drop_lb_jieba.py` 删旧 NLP B 层（97,838 行已执行）、`run_mvp1 build-tags` 周更接线、`tags_lb.py` DEPRECATED。本仓（QRE）改动：①`gui/admin.py` 新 `overview_concept_tags(db_url)` + `CONCEPT_TAG_SOURCES` 常量——cluster.company_tags B 层 GROUP BY source（tag 条数/概念数/覆盖股票数/最新 first_seen），表缺失 present=False、DB 挂 ok=False，自降级不拖垮总览（同 overview_derivatives 模式）；②`gui/app.py` `/api/admin/overview` payload 加 `concept_tags`；③`gui/templates/admin.html` 总览加 `#ov-concept-tags` 卡片（概念标签源（B 层），表格：源/概念数/标签条数/覆盖股票/最新入库，零数据源标红「无数据」）。8081 归因端（lab_result.py）零改动——直接消费新 B 层。测试 `tests/test_gui_admin.py` +7（正常/缺源补零/表缺失/DB 挂/总览 payload/失败不 503/模板断言）。验证：`uv run pytest -q` → 1840 passed + 4 skipped（全绿，基线 1833+7）；带库 test_client 实测 /api/admin/overview concept_tags 返回 em_concept(290 概念/26,701 标签/5,261 股) + ths_concept(375/15,847/4,190)；8081 tag-analysis 实测示例 run 20260831T045758989180 B 层 20 块全真概念词；admin.html node --check 过。未重启 service、未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-ENTRY-018（8081 回测台「新增策略」tab 三入口递进重构：自然语言 / 快速向导 / 高级 YAML）

## Implementation Summary

按用户拍板规格把 lab.html「新增策略」tab 的平铺结构替换为三入口 tab（8081 独占模板，8080 index.html/admin.html/app.py 零改动，`git diff --name-only HEAD` 仅 lab.html + style.css + test_gui_lab.py）。①HTML：`.entry-tabs` 子 tab 条（① 自然语言·默认 active ② 快速向导 ③ 高级 YAML）+ 三个 `.entry-content` 面板；回测参数区与沙箱面板为三入口共用。②自然语言：rows=5 大输入框 + `#nl-examples` 4 个 `.nl-example` 示例句按钮（点击填入输入框并 focus）；编译成功 `yamlEl.value = d.yaml` 同步到高级 YAML 编辑器，结果框给「→ 前往查看/修改」链接调 `switchEntryTab("yaml")`。③快速向导：因子 checkbox 菜单栏删除，改为**带搜索的分组下拉**——`/api/factors` 各组（含行情字段组）展开为 `FACTOR_OPTIONS`（别名冲突 `_2` 后缀，`ALIAS_TARGET` 记 factors.table.column），每个 `.wz-factsel` = filter 输入（实时按 label/别名关键字重建 select 的 optgroup）+ select；条件行 = 左因子下拉 → `.wz-op` 比较符（上穿 crosses_above/下穿 crosses_below/大于/小于/大于等于/小于等于）→ 右值（`.wz-rfield` 因子下拉，或勾选 `.wz-isfixed`「固定值」填 `.wz-rnum` 数字）；上穿/下穿编译为真实穿越事件 `(l > r) and (l.shift(1) <= r.shift(1))`（表达式 DSL 支持 `.shift`，右值为数字时 shift 退化常量）。入场/出场 `span.req` 红色 * 必选（buildYamlPreview 两组均强制），占位示例预填 EMA5 上穿 EMA200 / 下穿（`prefillPlaceholderConditions`，因子库实测含 ema_5/ema_200，缺失则回退 close/pre_close）；止盈/止损/移动止损/最大持仓天数/条件组 AND·OR 收进折叠 `#sec-wz-advanced`「高级选项（可选）」。`selectedFactors` 不再靠勾选维护，`usedFactors()` 从条件行实际使用推导。④高级 YAML：编辑器 + 验证/存入沙箱/上传/模板照旧，底部新增 `#btn-save-smoke`「存入沙箱 + 冒烟测试」（saveToSandbox() 抽取复用 → /api/strategies/smoke → 5s 轮询 + 滚动到沙箱面板）= 两步确认第 1 步。⑤回测参数：必选 * 仅回测区间（init `setRangeYears(2)` 默认近两年）与标的范围（`#param-all-market` 默认 checked、codes disabled）；模式/资金/佣金 0.0003/最低佣金 5.0/印花税 0.0005/滑点/止损止盈/precheck/引擎/executor/DB/profile/output 全部并入折叠 `#sec-adv-params` 高级参数（默认值不变）。⑥两步确认显性化：沙箱列表晋升按钮改「正式回测（晋升）」，confirm 文案带冒烟指标摘要（`smokeSummary` map，loadSandbox 时从 smoke.metrics 填充；无摘要时明示「尚无已通过的冒烟摘要」）；API 契约与后端零变化。⑦style.css 纯追加（.entry-tab/.entry-content/.nl-example/.wz-factsel/#nl-description），既有规则零改动；零新前端框架/CDN。测试 `tests/test_gui_lab.py` +1（test_lab_strategy_three_entry_tabs：三 tab 标记与默认 active、≥3 示例句含规格两句、req 必选标注四处、两个折叠面板、btn-save-smoke、「正式回测（晋升）」、摩擦默认值、旧 `#wz-factor-groups` 移除断言），既有 12 用例零改动通过。验证：`uv run pytest -q` → 1808 passed + 4 skipped（全绿）；node `new Function` 语法自检三个 <script> 块全过；`sudo -n systemctl restart qre-gui-lab.service` 后 is-active=active、curl 8081 / 200 且含 `data-entry-tab="nl"/"wizard"/"yaml"`（entry-tab/nl-example/btn-save-smoke 共 18 处命中）、8080 / 200。无 CR（用户已拍板规格）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-PORT-017（回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081）

## Implementation Summary

纯移植，零优化/功能增删。①路由共享：新 `gui/strategy_lab_routes.py::register_strategy_lab_routes(app)`——create_app 内「新增策略/策略状态/run 查看」相关闭包路由原样搬入（/api/validate、/api/run、/api/runs* 与 /runs、/runs/<id> 页面、/api/templates GET/POST/<name>、/api/factors、/api/nl_compile、/api/strategies/create|sandbox|smoke|promote|sandbox/delete|deep-validate(+status)、/api/admin/refresh(+register/unregister)、/api/admin/strategies/toggle|delete、/admin/strategy/<id>、/api/admin/strategy/<id>/artifact 白名单下载）；`create_app` 尾部调用同一注册函数。机械核对：新 create_app 路由表与 git HEAD 逐条相等（59/59 rule+method）。兼容锚点：try_acquire_run_slot/release_run_slot/run_backtest 在 app.py 保持 re-export，共享模块经 gui.app 命名空间调用时解析——test_gui_strategy_create.py 的 monkeypatch（打在 gui.app.*）零改动通过。②新 `gui/lab.py`（create_lab_app/launch_lab_gui，模板/静态目录调用时读 gui_app.TEMPLATE_DIR/STATIC_DIR 以兼容既有 monkeypatch 测试模式）+ `templates/lab.html`（两 tab「新增策略」「回测管理」，内容由脚本从 index.html strategy tab 与 admin.html onboard tab 精确切片组装，含 tab 切换/section 折叠 helpers、排序 JS、搜索框、toggle/删除、gate/风险徽标；CSS 复用 style.css；附 /runs 页面保证 tab 内 run 链接可用）。③CLI：`qre gui` 不变；`qre gui --lab` 启动 lab（默认 8081，显式 --port 优先）。④systemd：`deploy/hardened/qre-gui-lab.service` 仿 qre-gui.service（端口 8081、SyslogIdentifier=qre-gui-lab），已 sudo cp + daemon-reload + enable --now（enabled/active）。⑤测试 `tests/test_gui_lab.py` +12。验证：`uv run pytest -q` → 1807 passed + 4 skipped（全绿）；冒烟 8081 / 双 tab 在、/api/admin/refresh stopped 118/118、策略详情 200；8080 / 与 /admin 200、同 API 结果一致。无 CR（纯移植无设计决策）。两个 service 均已重启。未 git commit，等用户审批。

---

## Archive: QRE-DERIV-ADAPTER-013（衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道，CR D1.5/D2.2/D3.2）

## Implementation Summary

新模块 `data/derivatives.py`（QRE 对业务库只读；唯一直接读 derivatives schema 的代码）：`load_zero_curve`（yc_curve 即期曲线 yield%÷100 视为年复利 → periodic_to_continuous(m=1) 转连续复利近似，披露；当日无数据取 ≤trade_date 最近日，`latest_curve_date` 查实际日期）；`load_cb_terms`/`cb_cashflows`/`cb_bond_floor`（cb_basic 条款 → coupon_schedule 现金流近似：常数票息、剩余期限取整付息网格、到期按面值 100 无赎回溢价 → convertible_bond_floor + 同日 cb_daily.bond_value 对比）；`load_option_chain`（opt_daily.settle JOIN opt_basic opt_code 前缀匹配，T=actual/365，r=0.25y 节点，逐合约 implied_vol 反解越界记 None，平值 call/put 隐波断言 (1%,150%)）。已知缺口：库内无 ETF 日线（510050.SH 不在 stock_daily/index_daily），标的价格查库失败时须传 `underlying_price`，示例脚本用平值 put-call parity 反推（披露）。示例 `scripts/derivatives_adapter_smoke.py`；测试 `tests/test_data_derivatives.py` 15 个（纯函数 11 + DB 冒烟 4，无 QRE_MARKET_DB_URL 时 skip）。冒烟实测 2026-08-21：曲线 8 节点 1.164%–2.110%；兴业/上银/通22/重银/牧原债底 99.14–101.74 vs bond_value 105.4–111.2（差异主因到期赎回溢价 106–115 未含，可解释已披露）；50ETF 平值 K=3.0 call/put IV 均 13.67%。全量 1795 绿 + 4 skipped（基线 1784 + 11 净增）。未 commit、未重启 qre-gui。详见 05_PROGRESS.md 顶部与 CR §11。

---

## Archive: QRE-GUI-DERIV-CARD-012（总览 tab 衍生品数据卡片）

## Implementation Summary

总览 tab 加第四张卡片「衍生品数据」：`gui/admin.py` + `overview_derivatives`（只读 derivatives schema 五表：to_regclass 存在性 + reltuples 估算行数（-1 未 ANALYZE 降级 None）+ 日表 MAX(trade_date)，静态表仅行数；表缺失 present=False、整域异常 ok=False 自降级；_cached TTL 300s 沿用现有模式）；`app.py` overview 端点挂 derivatives 节；`admin.html` + ov-derivatives 卡片渲染（零表 → 「未初始化」+ D1.4 备注）。真库冒烟 ok（5/5 在库，日表 watermark 2026-08-21）。测试 +5（三态 + 端点 + 卡片存在性），全量 1784 绿（1779 + 5）。未 commit、未重启 qre-gui。详见 05_PROGRESS.md 顶部。

---

## Archive: QRE-RISK-GUIDE-011（大盘风险 tab 通俗说明块）

## Implementation Summary

`admin.html`「大盘风险」tab 新增可折叠「💡 怎么看懂这个页面」说明块（总分/红绿灯/四指标白话/热力表读法/免责声明）+ 三个 section 标题附白话提示；`test_gui_market_risk.py` +1（guide 存在性断言）。纯模板文案，无逻辑变更。验证：test_gui_market_risk.py 14/14 绿。详见 05_PROGRESS.md 顶部。

---

## Archive: QRE-RISK-BAROMETER-M3-010（大盘/板块风险风向标 M3：日更 timer 接入 + GUI 风向标页 + 阈值首轮校准观察）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；M1=64addd7、M2=b0713d7 已提交，R2–R7 也在待审批队列)

## Implementation Summary

M3 落地（CR `docs/frm/CR_2026-08-23_market_risk_barometer.md` §5 M3 阶段，
CR 状态改「✅ M1–M3 已完成」）：

**改动清单**：
- `deploy/hardened/qre-barometer.{service,timer}`（新）：Mon..Fri 18:30、
  Persistent=true、oneshot、沿用 qre-refresh hardened 护栏（Restart
  on-failure、MemoryMax=4G、Nice=10、TimeoutStartSec=1800）；ExecStart
  `uv run python -m quant_research_engine.risk.barometer_job`（无参 =
  默认最近交易日）；安装命令在头部注释，未 sudo。
- `risk/barometer_job.py`：+ `latest_trade_date`（trade_calendar 最近
  开市日）；main 无 --date/--d0 时默认该日（timer 调用口径）。
- `apps/cli.py`：+ `qre barometer` 子命令（--date/--d0/--d1/--chunk/
  --no-json/--no-cluster，转发 barometer_job.main）。
- `gui/admin.py`：TIMER_UNITS + qre-barometer.timer（「大盘风险风向标」）+
  QRE_BAROMETER_INSTALL_HINT；`gui/daily_jobs.py`：PIPELINES +
  qre-barometer（日更中心手动触发）。
- `gui/market_risk.py`（新）：`market_risk_overview` 只读
  market_risk.daily（_store + _cached TTL 300s + 降级）——最新 market 行
  （总分/灯/四指标/双判据详情）、近 252 日五序列、行业/簇两视图板块表
  （行业按总分降序、簇按突破占比降序）。
- `gui/app.py`：+ `/api/admin/market-risk`；`gui/templates/admin.html`：
  + 「大盘风险」tab（总分仪表盘红黄绿灯、五序列客户端 inline SVG
  polyline、行业/动态簇热力表切换、预警双判据详情表；复用现有
  tab/section/risk-card/health-* 样式，零新前端框架）。
- `docs/frm/CR_2026-08-23_market_risk_barometer.md`：状态改 M1–M3 已完成。
- `docs/agent/06_DECISION_LOG.md`：阈值首轮校准观察（red 11/1850=0.59%
  全为已知风险事件、amber 11.8%、corr 0.10≈P95、breach 3%≈P93，
  初值保留）。
- 测试（+14）：`tests/test_gui_market_risk.py` 13（overview 排序/空表/
  双降级/路由 200/admin tab 存在/TIMER_UNITS/install_hint/deploy 文件
  静态校验/PIPELINES/CLI 解析与分发）+ `test_risk_barometer_job.py` +1
  （默认最近交易日）。

**真实冒烟**：market_risk_overview 真库 ok（2026-08-20 总分 63.3 green、
252 日序列、105 行业、14 簇）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1778 passed, 4 warnings（1764 + 14 净增）
market_risk_overview() 真库直连 ok
scripts/check-progress-docs.sh → passed；git diff --check → clean
```

## Known Limitations

- qre-gui 未重启（用户约束），GUI 页面未经浏览器人工核对；timer 未安装
  （sudo 由主代理/用户执行，命令见 deploy 文件头注释与 admin 日更中心
  install_hint）。

## Next Steps

无（CR M1–M3 全部完成）。用户侧待办：sudo 安装 qre-barometer.timer +
重启 qre-gui 后人工核对「大盘风险」tab。

---

# Coding Handoff (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Task ID

QRE-RISK-BAROMETER-M2-009（大盘/板块风险风向标 M2：数据装配 + 历史回填 + market_risk_daily 产出）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；M1=64addd7 已提交，R2–R7 也在待审批队列)

## Implementation Summary

M2 落地（CR `docs/frm/CR_2026-08-23_market_risk_barometer.md` §5 M2 阶段）：
新 `risk/barometer_job.py`（risk 包唯一读写 DB 层）——取数
（stock_daily.pct_chg/100 收益面板、daily_basic.total_mv 市值、
stock_basic.industry 行业、cluster.daily_tags 当日簇 <5 跳过、
trade_calendar 日历）→ 调 M1 纯函数 → 写 `market_risk.daily` 表
（独立 schema，PK (trade_date, scope)，ON CONFLICT 幂等 upsert，
scope ∈ market / industry:<行业> / cluster:<tag>）+ JSON 产物
outputs/market_risk/<date>.json。区间按年分块、每块前补 312 交易日
buffer（252 分位 + 60 相关 warmup），块间幂等。入口
`python -m quant_research_engine.risk.barometer_job --date D |
--d0 --d1 --chunk year`。簇行只出当日截面指标（成员逐日变动，
M2 不算簇分数，scores=None 披露）；行业与全市场完整分数。
M1 内核零行为改动（barometer.build_barometer indicators 仅增列
n_stocks 序列）。

**真实回填**：2019-01-02 → 2026-08-20，8 年块，~21 分钟单进程，
220,034 行 / 1,850 交易日 × 120 scope（1 market + 105 industry +
14 cluster tag），JSON 产物 1,850 个。

**方向性验证（全过）**：2020-02-03 疫情 red（突破占比 85.2% P100、
总分 87.7 P99）；2024-01-29~02-05 微盘危机连续 red（总分 93.9–99.4
P99–100，02-05 突破 58.6% P100）；常态 2023-06 green（P10–21）；
全样本 red 11 天全部为已知风险事件（+2024-10-09、2025-04-07）。

**测试**（+10）：`tests/test_risk_barometer_job.py`——分块边界、
DDL、幂等 upsert（ON CONFLICT + NaN→None）、簇 <5 跳过、端到端
monkeypatch 管线 + JSON 产物、空日历报错。全量 1764 绿。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1764 passed, 4 warnings（1754 + 10 净增）
回填：2019-01-02→2026-08-20，8 chunks，220,034 行，~21min
scripts/check-progress-docs.sh → passed；git diff --check → clean
```

## Known Limitations

- 簇分数 M2 不算（成员逐日变动）；2020-02-04 离散度 12.0 为新股首日
  ±44% 极端收益（数据特征，等权 std 对离群敏感，披露）；
  daily_basic 缺个别 BJ 股市值 → reindex 补 NaN 加权剔除。
- 日更 timer（M3）未接；单日模式实测 ~80s（315 日 buffer × 5565 股）。

## Next Steps

M3：日更 systemd timer（18:30，Persistent）+ GUI 风向标页 +
阈值首轮校准记录进 06_DECISION_LOG。

---

# Coding Handoff (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Task ID

QRE-RISK-BAROMETER-M1-008（大盘/板块风险风向标 M1：cross_section + barometer 纯函数内核）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2–R7 也在同一待审批队列)

## Implementation Summary

大盘/板块风险风向标 M1 落地（依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §2/§4/§5 M1 阶段）：
截面聚合 + 组合法 + 分数归一化 + 预警判定的纯函数内核，零 DB。

**改动清单**：
- `risk/cross_section.py`（新，纯函数零 DB、向量化）：
  `ewma_variance_panel`（逐列 EWMA 方差面板，σ²_1=r²_1、NaN 跳过、
  方差顺延，与 volatility.ewma_variance_series 单列口径 atol 1e-15
  一致）；`cross_sectional_volatility_stats`（逐日 σ 中位数/90 分位/
  覆盖数）；`cross_sectional_dispersion`（当日收益等权 ddof=1 标准差 +
  市值加权 Σw(r−μ_w)² 口径标准差，权重行内归一化）；
  `average_pairwise_correlation`（滚动 60 日窗口、完整窗口个股才计入、
  等权=相关矩阵上三角均值、市值加权=w_i·w_j 偶权加权均值的常规近似
  并披露）；`var_breach_ratio_series`（r<−VaR 严格口径同 HIT）；
  `cross_sectional_summary` 一把梭（VaR 用 EWMA 参数法 μ=0、
  σ forecast=raw.shift(1) 防前视）。
- `risk/barometer.py`（新，纯函数零 DB）：`portfolio_return_series`
  （等权/市值加权组合日收益）；`portfolio_risk_summary`（100% 复用
  volatility.latest_ewma_forecast + tail.historical/ewma_parametric_var_es
  出 EWMA σ 与 VaR/ES 95/99）；`rolling_percentile_score`（252 日滚动
  分位 0–100，历史不足 → None+warmup，不伪造）；`evaluate_alert`
  （相关 20 日升幅与突破占比双超阈 red/单超阈 amber/否则 green，相关
  历史不足判据不触发并披露）；`build_barometer`（全市场 + groups 映射
  板块统一 dict，<2 成员组跳过记入 skipped_groups，总分=五指标
  SCORE_COMPONENTS 非 warmup 等权均值）。
- `risk/constants.py`：+ BAROMETER_CORR_WINDOW=60、
  BAROMETER_SCORE_WINDOW=252、BAROMETER_ALERT_CORR_LOOKBACK=20、
  BAROMETER_ALERT_CORR_JUMP=0.10、BAROMETER_ALERT_BREACH_RATIO_MAX=0.03、
  BAROMETER_BREACH_CONFIDENCE=0.99、CROSS_SECTION_SIGMA_QUANTILE=0.90
  （全部结果 dict 回显；阈值初值 CR §2 注明待首批真实数据校准）。
- `risk/__init__.py`：增列 barometer/cross_section（docstring 同步）。
- 测试（+30）：`tests/test_risk_cross_section.py`（17：面板对单列一致性/
  NaN 顺延/手算两步递推/分位手算/离散度手算/等权 vs 加权差异/完全相关
  面板/相关 == np.corrcoef/窗口 warmup/偶权方向/不完整列剔除/突破计数与
  边界/summary 集成 shift 防前视）；`tests/test_risk_barometer.py`
  （13：组合收益手算/组合法对 tail+volatility 逐键一致/滚动分位已知值/
  warmup 降级/预警 green/amber×2/red/相关历史不足披露/组装结构与跳过组/
  warmup 传播总分 None/等权 vs 市值加权差异/常量回显）。

## Validation Evidence

```
uv run pytest tests/test_risk_cross_section.py tests/test_risk_barometer.py → 30 passed
uv run pytest tests/ -x -q → 1754 passed, 4 warnings（基线 1724 + 30 净增，全绿）
scripts/check-progress-docs.sh → passed
git diff --check → clean
注：全量首跑 test_gui_risk_report.py::test_post_conflict_409 失败，单独与
全量复跑均绿（环境敏感 flake，非本任务引入）
```

## Known Limitations

- 加权平均相关为 w_i·w_j 偶权常规近似（非严格加权相关系数，docstring
  披露）；加权离散度未做 1−Σw² 集中度校正。
- 预警阈值 +0.10/3% 为 CR 注明待校准初值，M3 首批真实数据校准。
- M2 数据装配层（barometer_job.py 读库）本阶段不做。

## Next Steps

M2：barometer_job.py 数据装配（daily_basic.total_mv 市值、
stock_basic.industry 行业、cluster.daily_tags/company_tags 簇、
public.stock_daily 收益面板——数据事实已核查在库）+ 历史回填
252+60 交易日 + market_risk_daily 产出。

---

# Coding Handoff (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Task ID

QRE-RISK-PORTFOLIO-007（FRM 风险管理模块 R7：组合层汇总 + risk_report 扩展 + GUI 卡片 + 可选闸扩展）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2–R6 也在同一待审批队列)

## Implementation Summary

FRM 风险模块 R7 落地（依据已批准 CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md`
R7 阶段；R5 = commit 5472832、R6 已完）：组合层汇总 + risk_report 扩展 +
GUI 卡片 + 可选晋升闸判据，全部向后兼容（默认 run 产物零变化）。

**改动清单**：
- `risk/portfolio.py`（新，纯函数零 DB）：`summarize_mixed_portfolio`——
  股票腿沿用 R1–R4 收益序列法（performance_summary + 当前 1 日 EWMA 参数
  VaR/ES 参照）；债券/转债腿 `bonds.portfolio_aggregate`（DV01 可加、
  D/C 市值加权）+ 可选逐头寸 `bonds.key_rate_shifts` KR01 按节点加总
  （kr01_sum 与 DV01 并列披露，口径可不同不强制相等）；期权腿
  `options.portfolio_greeks`（数量×单值求和）；可选 DGV-VaR——config
  显式给 `dgv.spot_shock_sd` 才计算（组合层无标的价格水平无法自动推导，
  披露于 docstring）。输出 JSON 可序列化（numpy→list）；三腿至少给一条
  否则 ValueError；仅股票输入退化为仅 equity 节。
- `risk/report.py`：config 显式传入非空 `bond_positions`/`option_positions`/
  `bond_kr01` 之一才追加 `report["portfolio"]` 节（`_safe` 兜底，
  meta.sections["portfolio"] 回显；portfolio_config 可覆盖，缺省继承
  外层 rf/lam/ann）；`render_risk_markdown` 有该节才渲染
  「### 组合与衍生品风险」（DV01/久期/凸性 + KR01 表 + 组合 Greeks +
  DGV-VaR；error 节降级）。
- `risk/constants.py`：+ `GATE_DV01_MAX=None`、`GATE_GREEKS_MAX=None`
  （R7 可选闸判据阈值，默认 None=不启用）。
- `gui/risk_report.py::evaluate_gate_risk`：两阈值全 None（默认）时返回
  dict 与 R4 逐键一致、不读 portfolio 节；任一非 None 且 report 有
  portfolio 节时追加 |DV01| 与 |Δ|/|Γ|/|vega| 限额检查（超阈 →
  reason `dv01_exceeds_limit`/`greek_<name>_exceeds_limit` → warning）；
  节缺失/字段缺失子项记 None 不触发（与 R4 缺失语义一致）。
- `gui/app.py::_risk_display`：+ portfolio 视图（fixed_income/kr01_rows/
  options/dgv_var，error 节跳过）；`templates/run_detail.html`：
  `risk_view.portfolio` 存在时追加「衍生品风险（组合层）」卡片（沿用
  risk-card 模式，无此节不显示，老 run 页面零变化）。
- 测试（+28）：`tests/test_risk_portfolio.py`（新 14：纯股票退化/混合合并
  手算/KR01 加总对单头寸一致+ΣKR01≈DV01/零市值报错/DGV 开关与校验/
  JSON 序列化）；`tests/test_risk_report.py`（+7：默认关向后兼容/期权腿/
  债券腿/error 降级/markdown 两态/老 meta 无 sections 渲染不炸）；
  `tests/test_gui_risk_report.py`（+7：卡片有无两渲染、闸默认关闭
  逐键一致/DV01 超阈 warning/未超阈 ok/Greeks 超阈/启用但无节不触发）。

**向后兼容**：默认 run 收尾钩子不传衍生品键 → risk_report.json 与 summary.md
产物零变化；老格式 report（无 portfolio 节、甚至无 meta.sections）GUI 渲染、
markdown 渲染、闸评估均不炸（专项测试覆盖）。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1724 passed, 4 warnings（2026-08-23，
基线 1696 + 28 净增，全绿）
定向：test_risk_portfolio.py 14/14、test_risk_report.py 29/29、
test_gui_risk_report.py 24/24 全绿
```

## Known Limitations

- DGV-VaR 需调用方显式给 spot/vol shock（组合层无标的价格水平）；多腿
  风险因子相关性（股票腿与期权标的）未建模，披露于 derivatives_var。
- 闸扩展默认关闭；启用需改 constants（GATE_DV01_MAX/GATE_GREEKS_MAX），
  属用户显式决策。
- 当前 run 均为纯股票策略，portfolio 节无真实产出路径（行情接入留待
  未来数据源 CR，见 CR §5）。

---

# Coding Handoff (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006（FRM 风险管理模块 R6：期权计算内核 + DGV-VaR）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2/R3/R4/R5 也在同一待审批队列)

## Implementation Summary

FRM 风险模块 R6 落地（依据已批准 CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md`
R6 阶段；R5 = commit 5472832）：risk 包新增期权内核与 Delta-Gamma-Vega VaR
适配器两个纯函数模块（零 DB、零行情），公式与数值例题以
`docs/frm/FRM量化风控知识摘要.md` 为准（二叉树收敛例参数 S=29,K=30,r=3%,
σ=25%,T=1 已核对教材原文 p193 确认）。

**改动清单**：
- `risk/options.py`（新）：`bsm_price`（式 15.6–15.9：无股息/连续股息 q/
  离散股息 S₀−D 修正，输出 d1/d2）；`black76_price`（式 15.12/15.13
  期货期权）；`implied_vol`（scipy brentq，区间 IV_BRACKET）；
  `crr_tree`（式 14.4–14.7：u=e^{σ√Δt}、d=1/u、p=(e^{(r−q)Δt}−d)/(u−d)、
  欧式+美式 backward induction、第一层两节点输出 delta 式 14.1、
  return_grid 可选输出全节点网格+美式行权标记）；`bsm_greeks`
  （式 16.1 + Table 16.2 含 q 版全组）；`black76_greeks`（期货期权版，
  rho=−f·T，theta 利用 F₀N′(d1)=KN′(d2) 化简为 r·f−时间衰减项）；
  `american_greeks_numeric`（书4 Ch16 方法：delta 第一层、gamma 第二层
  两个 delta 差、theta 隔层中节点、vega/rho ±h 微扰重建树）；
  `portfolio_greeks`（头寸加权求和）。
- `risk/derivatives_var.py`（新）：`dgv_pnl`（ΔV ≈ Δ·δS + ½Γ(δS)² +
  vega·δσ，式 2.3 + vega 项，支持逐情景数组）；`dgv_var`（二次型 P&L
  解析矩——非中心卡方累积量 κ_r = 2^{r−1}(r−1)!(1+rλ)b^r，
  λ=a²/4b²，vega 只进 κ2；正态/Cornish-Fisher 分位 VaR，损失正号与
  tail.py 同口径；δS/δσ 独立假设披露）；`dgv_var_series`（逐日 VaR
  序列，直接喂 backtest_var.backtest_var_summary，不新造回测引擎）。
- `risk/constants.py`：+ `IV_BRACKET=(1e-4, 5.0)`、
  `DEFAULT_TREE_STEPS=50`（书4 Ch14 实务 30–50 步）、
  `GREEK_SHOCK_SIGMA=GREEK_SHOCK_RATE=1e-4`；全部结果 dict 回显。
- `risk/__init__.py`：导出 options/derivatives_var，docstring 升 R6。
- 测试（+39）：`tests/test_risk_options.py`（25）、
  `tests/test_risk_derivatives_var.py`（14），沿用既有 risk 测试风格。

**数值验收对照**（CR §4 R6 行全覆盖）：
- BSM 教材例 S=56,K=60,r=5%,σ=30%,T=1.5：d1=0.2001、d2=−0.1674、
  c=8.3069、p=7.9715 精确复现；parity c−p = S₀−Ke^{−rT} 1e-10 自洽；
- 隐波反解教材例：市价 7.00 → σ=0.2514（abs 5e-4）；
- 二叉树美式 put（S=29,K=30,r=3%,σ=25%,T=1）：2 步=3.058
  （节点 B=0.494 不行权、C=5.699 提前行权、欧式=2.838、美式溢价 0.22）、
  4 步=3.097、20/50/100/500 步 = 3.082/3.067/3.059/3.055 全复现
  （abs 5e-4）；
- Greeks：BSM PDE θ+rSΔ+½σ²S²Γ=rf（call/put/q 版均 1e-10）；
  解析 Greeks 对中心差分（rel 1e-5）；美式数值 Greeks 200 步逼近
  BSM（delta/gamma abs 1e-3）；Black76 rho=−f·T 精确；
- DGV-VaR：delta 中性纯 gamma 解析矩核对（E=½ΓsS²、Var=½Γ²sS⁴、
  偏度 2√2、超额峰度 12，χ²₁ 解析值）；解析矩对 200 万 MC
  （rel≤2%）；CF-VaR 对 MC 99% 分位（rel 5%，偏度<0.5 适用域）；
  VaR 序列 + backtest_var_summary 集成：2000 日合成回测违约率
  ≈1%、独立性 LR 不拒绝。

**关键披露**：Cornish-Fisher 摘要声明教材章节未点名（按业界标准实现并
标注）；CF 仅偏度适中时有效，高偏度纯 gamma χ² 型 P&L 下分位失真
（docstring + 测试注明）。Black76 theta 首版符号错误经有限差分
自检发现并修正（θ = r·f − F₀e^{−rT}N′(d1)σ/(2√T)）。

**存量兼容**：既有 risk 模块零行为改动；1657 基线测试零改动全绿。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1696 passed, 4 warnings（2026-08-23，
基线 1657 + 39 净增；风险包新单测 39/39 绿）
```

## Known Limitations

- CRR 收敛 O(1/n) 振荡：树↔BSM 收敛测试容差 abs 3e-3（500–1000 步）。
- DGV 假设 δS/δσ 独立（rho=0），多因子协方差扩展留待 R7+。
- CF 高偏度失真已知限制（上述披露）；Heston/波动率曲面/LSM/奇异期权
  按 CR §6 不做。

---

# Coding Handoff (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005（FRM 风险管理模块 R5：利率与债券计算内核）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2/R3/R4 也在同一待审批队列)

## Implementation Summary

FRM 风险模块 R5 落地（依据已批准 CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段）：risk 包新增利率与债券两个纯函数内核（零 DB、零行情，输入为 dict/现金流表），公式与数值例题以 `docs/frm/FRM量化风控知识摘要.md` 为准。

**改动清单**：
- `risk/rates.py`（新）：`convert_compounding`（式 16.2）/
  `periodic_to_continuous`（式 16.4）/`continuous_to_periodic`（式 16.5）/
  `future_value`/`present_value`（式 16.1/16.3）/`spot_to_discount_factor`/
  `discount_factor_to_spot`（书4 Ch10）/`interp_zero_rate`（linear 利率线性
  或 log_linear 折现因子对数线性，域外平坦外推披露）/
  `bootstrap_zero_curve`（书4 Ch9 附息债由短到长解 d(k)，输出连续复利
  零息利率）/`forward_rate`（连续式 + 式 10.5 半年复利增长因子比）/
  `par_yield`（式 16.7/10.4）。曲线统一约定：连续复利零息利率（小数），
  期限年。
- `risk/bonds.py`（新）：`coupon_schedule`（付息日估值口径现金流表）/
  `price_from_yield` + `ytm`（scipy brentq，区间 YTM_BRACKET）/
  `accrued_interest`（actual/actual 式 9.2 与 30/360 书3 Ch17 双口径）/
  `clean_to_dirty`/`dirty_to_clean`/`yield_duration_convexity`（式 12.6：
  Macaulay/Modified D、Yield/Modified C）/`price_from_zero_curve`（曲线
  折现 + shift 参数）/`effective_duration_convexity`（式 12.1/12.3 ±Δr
  重定价）/`dv01`/`dv01_from_duration`/`duration_from_dv01`
  （D=10,000×DV01/Value）/`portfolio_aggregate`（DV01 可加、D/C 市值
  加权）/`dv01_hedge_face`（对冲面值=组合DV01/工具每面值DV01）/
  `parallel_shift_approx`（式 12.4 二阶）/`key_rate_shifts`（书4 Ch13
  三角帽局部线性 shift、端点外延、Σw=1 → ΣKR01=DV01 一阶自检）/
  `convertible_bond_floor`（债底=ΣCF·e^{−(r+s)t}，spread duration ±Δs
  重定价）。
- `risk/constants.py`：+ `DEFAULT_DAY_COUNT="actual/actual"`（中国惯例）、
  `CURVE_INTERPOLATION="linear"`、`KEY_RATE_TENORS`（0.25–30y 十节点）、
  `RATE_SHOCK_BP=1.0`、`YTM_BRACKET=(-0.05, 1.0)`；全部在结果 dict 回显。
- `risk/__init__.py`：导出 rates/bonds，docstring 升 R1+R2+R5。
- `pyproject.toml`：补 `scipy>=1.11.0` 显式依赖（R1 起 constants.py
  import scipy 但未声明，CR §3 点名顺手修复）。
- 测试（+52）：`tests/test_risk_rates.py`（26）、`tests/test_risk_bonds.py`
  （26），命名/结构沿用既有 risk 测试风格（类分组 + 教材例题 + 手算 +
  自检恒等式 + 边界报错）。

**数值验收对照**（CR §4 R5 行全覆盖）：
- 书4 Ch9 bootstrap：d = 0.991909/0.980944/0.969406/0.956909 精确复现
  （atol 1e-6），折现回验各债 dirty price 自洽；
- par yield 式 16.7/10.4：2.2103%（手算一致），平价债回验=100；
- 平坦曲线连续年金解析解：P=8.6394、D=4.7504、C=30.862（周付息网格
  逼近 rel<1e-2）；
- DV01↔duration：duration_from_dv01 与 effective duration 一致（1e-12）；
- ΣKR01=DV01：一阶恒等式 rel 3.5e-6（rtol 1e-4 自检 True），5y 债风险
  集中 5y 节点、7y+ 节点暴露为 0；
- 平行移动 +100bp：二阶近似 vs 直接重定价 rel 偏差 1.9e-5（<1e-3 容差）；
- 转债债底：手算 3 期折现一致（1e-10）、s=0 退化为无风险折现价、
  spread duration = r+s 水平 effective duration（rel 1e-6）。

**存量兼容**：既有 risk 模块零行为改动；1605 基线测试零改动全绿。

## Validation Evidence

```
uv run pytest tests/ -x -q → 1657 passed, 4 warnings（2026-08-23，
基线 1605 + 52 净增；风险包新单测 52/52 绿）
```

## Known Limitations

- KR01 的 ΣKR01=DV01 为一阶恒等式，残差是价格对利率非线性的二阶项
  （量级 ~C·n·(Δr)²，测试容差 rtol 1e-4），已在 note 披露。
- 插值域外平坦外推（端点值），已在 docstring/note 披露。
- PCA 冲击、转债条款引擎、信用违约模型、互换/期货定价按 CR §6 不做。

---

# Coding Handoff (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004（FRM 风险管理模块 R4：晋升全量回测闸加入风险判据）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2/R3 也在同一待审批队列)

## Implementation Summary

晋升全量回测闸（QRE-GUI-PROMO-GATE-001，commit cfb860d）加入 FRM 风险
判据维度：闸评估时读该 run 的 `runs/<run_id>/risk_report.json`，ES99 超阈
或 VaR 覆盖率 Kupiec LR 被拒绝 → `risk.status=warning`，与 failed 同效阻止
日更（force 可覆盖）；主判据（交易≥30 且超额>0）照旧。

**改动清单**：
- `risk/constants.py`：+ `GATE_ES99_MAX = 0.03`（99% ES 历史模拟日收益
  损失口径上限）、`GATE_VAR_CONFIDENCE = 0.99`（VaR 回测试用置信节，
  与 ES99 同置信；LR 显著性 5% 沿用 backtest_var 既有 reject_5pct）。
- `gui/risk_report.py`：+ `evaluate_gate_risk(run_id)`——load_risk_report
  → risk 判据 dict（status ok|warning|unavailable + es99/es99_threshold/
  var_lr_reject/var_confidence/reasons/report_run_id）。ES99 取
  `tail.99pct.historical_simulation.es`（经验日收益口径）；VaR 取
  `var_backtest.levels.99pct.coverage.reject_5pct`（Kupiec 覆盖率 LR；
  独立性检验不进闸判据）。report 缺失/损坏 → unavailable 不阻断；
  关键字段缺失 → 该子项记 None 不触发 warning。
- `gui/strategy_create.py::finalize_promotion_gate`：payload 增加
  `"risk": evaluate_gate_risk(record.run_id)`（run 失败时同路径评估，
  report 不存在自然落 unavailable）；docstring 同步。
- `gui/refresh_registry.py::gate_blocks_daily`：forced → False；
  gate=="failed" 或 risk.status=="warning" → True。注释/文档串同步。
- `gui/templates/admin.html`：闸列 risk=warning 时追加
  `<span class="gate-badge gate-risk">⚠ 风险警示</span>`，tooltip 显示
  ES99/阈值 + VaR 回测（99% Kupiec LR）结论与 force/日更跳过语义。
- `gui/static/style.css`：+ `.gate-risk`（橙色徽标）。
- 测试（+7）：`tests/test_gui_strategy_create.py` R4 节——risk ok /
  warning（ES 超阈）/ warning（LR 拒绝）/ unavailable（无 report）/
  warning+force 不阻断（均含 gate_blocks_daily 联动，monkeypatch
  risk_report.RUNS_DIR 落假报告）；`tests/test_gui_admin_strat_tab.py`
  `test_admin_html_gate_risk_badge`（徽标类/tooltip 字符串 + CSS 断言）。

**存量兼容**：旧 gate json 无 risk 节 → gate_blocks_daily 不受影响，
admin 不显示徽标；下次晋升回测评估自然写入。

## Validation

- `uv run pytest tests/test_gui_strategy_create.py tests/test_gui_admin_strat_tab.py
  tests/test_refresh.py tests/test_gui_admin_p3b.py -q` → 103 passed。
- 全量 `uv run pytest tests/ -x -q` 结果见 10_REVIEW_REPORT.md。



## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization；R2 也在同一待审批队列)

## Implementation Summary

把 risk 包接进回测生命周期与 GUI（CR R3 阶段；R1=96db59d / R2=f52c0f4）。

**改动清单**：
- `risk/report.py` + `render_risk_markdown(report_dict) -> str`：汉化
  「## 风险分析」节，比率两位小数 / p 值四位，分区=分布与尾部（矩+JB+
  VaR/ES 三口径×95/99 表）/ VaR 回测（违约数·覆盖率 LR p·独立性 LR p·
  结论 + 多重检验警示）/ 波动率（EWMA 日+年化、GARCH α+β·长期波动·
  半衰期、regime）/ 压力测试（四情景表 + Peak/VaR 参照 + reverse，有键
  才渲染）/ 绩效（Sharpe/Sortino，有基准加 β/Treynor/IR/α）/ Bootstrap
  CI（有键才渲染）。error 节降级「数据不足」一行。零 GUI 依赖。
- 新 `gui/risk_report.py`：`extract_strategy_returns(record)`（定位组合级
  equity_curve.csv——列头含 daily_return 或 total_equity 且不含 symbol
  列，per-symbol 目录文件排除；daily_return 直取，缺则 pct_change 退化；
  trade_date→DatetimeIndex；有 benchmark_close 列才取基准）；
  `generate_risk_report`（var_backtest 开/stress 开/bootstrap 可配；
  JSON tmp+os.replace 原子写 runs/<run_id>/risk_report.json；markdown
  幂等追加产物 summary.md「## 风险分析」节——先移除既有同名副，无
  summary.md 退化写 runs/<run_id>/risk_report.md）；
  `finalize_risk_report`（仅 completed，bootstrap 关）；
  `start_risk_report_job`（复用 daily_jobs.start_script_job，
  lock_key=risk-report:<run_id>，in-process runner，bootstrap 开）。
- `gui/engine.py:354-361`：_execute_and_finalize 尾部新钩子，与
  smoke/promotion_gate 同模式 try/except 兜底。
- `gui/app.py`：run_detail 路由加载 risk_report.json + `_risk_display`
  卡片视图；POST /api/runs/<run_id>/risk-report（404/400 非 completed/
  409 同 run 重入）+ GET …/risk-report/job/<job_id>（校验 pipeline 前缀）。
- `templates/run_detail.html`：「风险分析」区——有报告渲染六组卡片
  （VaR/ES 三口径表、分布/JB、VaR 回测表+结论、波动率、四情景压力表、
  绩效）；无报告且 completed → 「未生成」+ 生成按钮（POST→5s 轮询→
  完成自动刷新）；failed → 提示无分析。`static/style.css` 加
  .risk-cards/.risk-card。
- 测试：新 `tests/test_gui_risk_report.py` 17 个（提取口径×4、finalize
  ×4、engine 钩子接线×1 含异常吞掉、端点×5、模板×3）；
  `tests/test_risk_report.py` +TestRenderMarkdown 4 个。
- **#4 admin 策略列表 badge 未加**（任务书允许）：admin 策略表数据源
  refresh_overview（outputs/refresh 产物，非 GUI run）无 risk_report.json，
  需对 refresh 管线额外跑风险分析，超出 R3「别硬塞」边界。

**真实 E2E**（未重启 qre-gui，直接 module executor 跑）：
run 20260822T114522831346（mr01a，5 股 × 2024-01~2025-12，vectorized）
→ completed；risk_report.json n=484；99% VaR 参数正态 1.50%/历史模拟
1.79%，ES 1.72%/2.19%；JB=629.81 p<0.0001 拒绝正态（超额峰度 5.35）；
VaR 回测 95% 违约 19/24.15（covLR p=0.2648）、99% 7/4.83（p=0.3524）、
独立性 p=0.2244/0.6743 均不拒绝；EWMA σ≈0（策略长时段空仓，R2 口径
如实输出，Peak/VaR 比值失真 -2532.15 已知现象留后续）；GARCH α+β=1.00
非平稳如实标注；2024 小微盘情景覆盖（36 天，损失 -6.20% 即盈利），
其余三情景「样本不覆盖」；Sharpe 0.02/Sortino 0.03；summary.md 风险节
追加且既有结构保留。

## Validation

```
uv run pytest tests/ -x -q → 1599 passed, 4 warnings（1578 + 21 净增）
（首跑 test_gui_factor_wizard.py::test_job_lock_conflict 失败 → 全量复跑
  全绿，已知环境敏感 flake）
scripts/check-progress-docs.sh → passed
git diff --check → clean
```

## Git Finalization

未 commit（用户约束：不 commit、不重启 qre-gui.service）。建议 commit
message：`feat(risk): FRM 风险模块 R3 回测报告与 GUI 集成`。

---

# 以下为历史 handoff（QRE-RISK-CORE-002 及更早）

## Task ID

QRE-RISK-CORE-002（FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

在 R1 包（commit 96db59d）上落地 R2 三模块 + 报告扩展，风格延续 R1
（纯函数、零 DB、参数集中 constants.py、结果 dict 全参数回显 + 口径 note）。

**新模块与接口**：
- `backtest_var.py`（书2 Ch6）：`hit_series(returns, var_series)`（I_t =
  1{L_t > VaR_t}，严格大于，索引对齐去 NaN）；`coverage_lr_test(hits,
  confidence)`（Bernoulli LR = −2[(n−x)ln((1−p)/(1−p̂)) + x·ln(p/p̂)] ~
  χ²₁，0·ln0 按极限 0 处理；附 scipy binomtest 精确二项 p 值——教材方法
  ①③；note 注明公式同 Kupiec 但摘要声明教材未点名）；
  `independence_lr_test(hits)`（Christoffersen 一阶 Markov 转移矩阵 LR_ind
  ~ χ²₁，零计数单元跳过；note 注明摘要只给思路 E[HIT_t·HIT_{t+1}]=(1−p)²
  未点名 Christoffersen）；`false_positive_probability(alpha, n)` =
  1−(1−α)ⁿ；`backtest_var_summary`（统一 dict：violations/expected/
  violation_rate/coverage/independence/conclusion）。
- `stress.py`（书4 Ch8）：`HISTORICAL_SCENARIOS` 常量（crash_2015
  2015-06-15~09-30 / bear_2018 全年 / covid_2020 2020-01-20~03-31 /
  microcap_liquidity_2024 2024-01-01~02-29）；`replay_scenario(strategy,
  window, benchmark=None, var=None, es=None)`（窗口内累计损失 1−Π(1+r)、
  峰谷=窗口内净值最大回撤、Peak/VaR 与 Peak/ES、基准窗口累计收益、
  相关性崩溃=窗口内 vs 窗口外 Pearson 相关 delta，呼应 LTCM 红线）；
  `replay_historical_scenarios`（批量，样本不覆盖的窗口记 error 不抛）；
  `reverse_stress(strategy, benchmark, loss_threshold, horizon=21)`（β 穿透
  S*=阈值/β，在基准 h 日滚动累计收益分布上给经验分位与 σ 倍数；β≤0
  报错——市场冲击不构成损失通道需假设性情景）。
- `inference.py`（书2 Ch13）：`bootstrap_metric_ci(returns, metric,
  method="cbb"|"iid", ...)`——CBB 用 arch.bootstrap.CircularBlockBootstrap
  （arch 8 参数名是 seed 不是 random_state，已实测），块长默认
  ceil(√n)；指标 = 年化收益（日均×252）/夏普（与 performance 同口径）/
  最大回撤（净值峰谷）；percentile 置信区间 + MC 标准误 σ̂/√b（式 13.3）；
  iid 对照 note 标注「波动聚类下低估不确定性，A 股禁用其作结论依据」；
  `bootstrap_summary`（三指标 × CBB+iid + iid_underestimates 标志）。
- `report.py`：report_version 升 "R2"；`build_risk_report` 新增三节——
  `var_backtest`（默认开；VaR 序列默认 z_X·sqrt(ewma_forecast_series)
  μ=0 RiskMetrics 口径，n_obs 因 shift(1) 减一；`config.var_series` 可
  显式覆盖；附多重检验假阳性警示 1−0.95^10/^100）、`stress`（config
  stress=True 开；需 DatetimeIndex，否则 error 降级；VaR/ES 参照取最高
  置信水平 EWMA 参数法；`reverse_stress_threshold` + benchmark 时附
  reverse stress）、`bootstrap`（config bootstrap=True 开，reps/seed/
  ci_level/block_size 可配，默认 seed=42 固定可复现）；meta 加 sections
  开关回显。

**测试（46 个新增，1532 → 1578）**：tests/test_risk_backtest_var.py（16）、
test_risk_stress.py（12）、test_risk_inference.py（11）、test_risk_report.py
增补（+7，含 top-level keys 更新）。已知答案核对清单：
- HIT 手算（严格 >、对齐丢 NaN）；
- 覆盖率 LR 手算 n=100/x=10/p=0.05 → 4.13085（p≈0.0421 拒绝）；p̂=p →
  LR=0；x=0 → −2·n·ln(1−p)；x=n → −2·n·ln(p)；精确二项对 scipy；
- 独立性 LR 手算 hits=[0,0,1,0,0,1,0,0]（n00=3/n01=2/n10=2/n11=0，π̄=2/7）；
  高持续 Markov 链拒绝、iid Bernoulli 不拒绝；
- 假阳性 1−0.95^10=0.401263、^100=0.994079（教材值）；
- 情景回放手算：r=[−0.10,0.02,−0.05,0.01] → 累计 −0.119179、峰谷 0.05、
  Peak/VaR=2.5；相关性崩溃合成（窗口内 corr=1、窗口外≈0）delta>0；
- reverse stress 手算：r=2b → β=2 精确、S*=0.10、0.95^5−1=−0.22622、
  分位/σ 倍数对 numpy 独立复算；β≤0 报错；
- bootstrap：固定 seed CI 含样本统计量；MC 标准误=σ̂/√b rel 1e-12；
  同 seed 完全复现；块长 ceil(√400)=20；最大回撤手算 0.2；夏普口径与
  performance 一致；AR(1) φ=0.6 下夏普/年化收益 iid_std < cbb_std
  （iid_underestimates=True）；
- report：var_backtest 默认开/显式 var_series 覆盖/config 关；stress 默认
  关、非 DatetimeIndex 降级 error、2018 样本回放 + reverse stress；
  bootstrap 默认关、开启后结构 + JSON 可序列化。

## Key Decisions

- **覆盖率 LR 同时给渐近 χ² 与精确二项 p**：教材 Ch6 列三种方法，LR（③）
  与精确分布（①）互补；未实现 CLT 渐近检验（②，与 ③ 大样本等价）。
- **独立性按 Christoffersen 转移矩阵实现**：摘要声明教材只给思路、未点名
  Kupiec/Christoffersen；注释与返回值 note 如实标注出处差异（CR 允许）。
- **默认 VaR 序列取 μ=0 RiskMetrics 口径**（VaR_t = z·σ_t^EWMA）：避免用
  全样本均值造成前视；note 披露，`var_series` 可随时显式覆盖。
- **reverse stress 用 β 线性穿透**：教材提示情景放大是近似（压力期相关性
  上升不能线性外推），note 已声明；β≤0 直接报错不硬算。
- **iid_underestimates 测试用 AR(1) 而非纯 ARCH**：纯波动聚类下最大回撤
  的 iid/CBB 离散度差异不稳定（实测 0.1478 vs 0.1488 反向）；教材机制的
  稳健体现是序列自相关下均值类统计量（夏普/年化收益）iid 低估 CBB。
- **arch 8 API**：CircularBlockBootstrap 参数名是 `seed`（非 random_state），
  实测确认。

## Files Changed

- `src/quant_research_engine/risk/backtest_var.py`（新）、`stress.py`（新）、
  `inference.py`（新）
- `src/quant_research_engine/risk/constants.py`（情景库/REVERSE_STRESS_HORIZON/
  BOOTSTRAP_* / default_block_size）、`report.py`（三节扩展，R2）、
  `__init__.py`（导出新模块）
- `tests/test_risk_backtest_var.py`、`test_risk_stress.py`、
  `test_risk_inference.py`（新）；`tests/test_risk_report.py`（+7）
- `docs/agent/08_IMPLEMENTATION_BRIEF.md`（R2 brief）、`10_REVIEW_REPORT.md`、
  `04_TASK_HANDOFF.md`、`05_PROGRESS.md`、`11_AGENT_STATE.md`

## Validation

1. `uv run pytest tests/ -x -q` → **1578 passed, 4 warnings**（基线 1532 +
   46 净增；风险包 107/107 绿）
2. `scripts/check-progress-docs.sh` → passed
3. `git diff --check` → clean

## Known Limitations / Follow-ups

- R3（markdown 渲染、回测报告集成钩子、GUI 展示区）未做；R4 晋升闸单独 CR。
- 基线复跑插曲：首跑 `test_gui_factor_wizard.py::test_job_lock_conflict`
  失败（1 failed / 787 passed），单独复跑与全量复跑均绿——与已知
  环境敏感 flake（test_daily_job_lock_per_pipeline / test_api_run_success）
  同族，非本任务引入。
- 情景库只存日期窗口常量；真实行情回放由调用方提供序列（R3 集成时接
  回测产物 + 基准）。
- Bootstrap b=1000 × 3 指标 × 2 方法约秒级；report 默认关，由 config 显式开。

## Task ID

QRE-RISK-CORE-001（FRM 风险管理模块 R1：risk 包核心 tail/volatility/dependence/performance + 报告骨架）

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

新包 `src/quant_research_engine/risk/`（纯函数 + pandas/numpy/arch/scipy，
不读 DB、不依赖 QRE 内部状态，可被 cluster-ashare 独立 import）。公式一律
以 `docs/frm/FRM量化风控知识摘要.md` 为准，损失取正号约定（书4 Ch1）。

**包结构与接口**：
- `constants.py`：ANNUALIZATION_FACTOR=252、CONFIDENCE_LEVELS=(0.95,0.99)、
  EWMA_LAMBDA=0.94、DEFAULT_RISK_FREE_RATE=0.03、REGIME_QUANTILES=(1/3,2/3)、
  Z_95/Z_99（scipy 精确值）；每个结果 dict 回显所用参数。
- `tail.py`：parametric_normal_var_es / historical_var_es /
  ewma_parametric_var_es / skew_kurtosis / jarque_bera_test /
  distribution_summary。历史模拟用 numpy linear 插值（披露），
  ES=不低于 VaR 的损失均值（含 VaR，ES≥VaR 恒成立）；偏度/峰度双口径
  （sample analog 1/n = scipy bias=True；n−1 校正 = bias=False）；
  JB 用 scipy（教材式 12.11 是 T−1，scipy 是 T，note 披露）。
- `volatility.py`：ewma_variance_series（raw：σ²_n=λσ²_{n−1}+(1−λ)r²_n，
  手算 [1e-4,1.18e-4,1.6492e-4] 核对）+ ewma_forecast_series（raw.shift(1)
  point-in-time 防前视）+ ewma_volatility_series + latest_ewma_forecast +
  fit_garch11（arch，收益 ×100 拟合 ÷100² 还原 ω/V_L；α+β<1 平稳、
  V_L=ω/(1−α−β)、半衰期 ln(0.5)/ln(α+β)）+ volatility_regime
  （三分位规则写死并披露）。
- `dependence.py`：spearman_corr / kendall_corr（scipy，式 12.13/12.14）、
  is_positive_definite（最小特征值 > 1e-8）、simple_to_log_returns /
  log_to_simple_returns（log1p/expm1，式 12.5）。
- `performance.py`：beta（式 5.1）/ sharpe_ratio（与引擎 portfolio/risk.py
  同口径：(mean(r−rf/252)/std(ddof=1))·√252）/ sortino_ratio /
  treynor_ratio / information_ratio / jensens_alpha（市场模型回归截距，
  日频 α 与 ×252 年化均报）/ performance_summary（benchmark=None 时
  基准相关键为 null）。
- `report.py`：build_risk_report(returns, benchmark=None, config=None) -> dict
  （机读 R1 骨架；meta 参数回显 + distribution/tail/volatility/dependence/
  performance 六节；数据不足的节降级 {"error": ...} 不抛异常；markdown
  渲染留 R3）。

**测试（61 个新增）**：tests/test_risk_{tail,volatility,dependence,
performance,report}.py。教材例题/解析解复现：书4 Ch1 式 1.7
（μ=−20,σ=30,99% → VaR 49.79/ES 59.96）；EWMA 三步手算；GARCH 确定性
模拟（手写递推固定 seed，真值 ω=1e-6/α=0.08/β=0.90）→ 拟合 α≈0.076/
β≈0.899、平稳、半衰期 27.7 天 sane；α+β=1.05 模拟 → stationary=False；
EWMA 与 arch 固定参数 GARCH(ω=0,α=0.06,β=0.94) 交叉一致（shift(1) 后
~1e-12）；偏度/峰度对 scipy 双口径；JB 正态样本不拒绝/t4 拒绝；
Spearman/Kendall 手算小样本（0.5、1/3）；equicorrelation PD 通过 /
[[1,2],[2,1]] 拒绝；simple↔log 往返 1e-12；Sharpe 手算 10.5131 且与
portfolio/risk.py 同输入同值（rel 1e-9）；Sortino 手算 36.66；IR 手算
4.205；Jensen 精确线性恢复（α=0.001, β=1.5）；regime 三段合成标签正确；
report 结构键/参数回显/benchmark=None 降级/JSON 可序列化。

**依赖**：pyproject.toml + uv.lock 新增 arch>=6.3.0（前一轮已装，实际
arch 8.0.0 / scipy 1.18.1）。

## Key Decisions

1. **EWMA raw 口径采用 brief 手算数（σ²_n 含 r_n）**：式 3.2 原文用 r_{n−1}，
   但 brief 明确给出手算序列 [1e-4, 1.18e-4, 1.6492e-4]（要求 σ²_n 含 r_n）。
   两者仅一阶平移关系；raw 序列末值即次日预测，point-in-time 对齐另提供
   ewma_forecast_series（raw.shift(1)）满足「rolling 必须 shift(1) 防前视」。
   与 arch 交叉验证确认语义（arch day-t 方差仅用 r_{t−1} = 本实现 shift(1)）。
2. **GARCH 模拟用确定性手写递推**：arch 8.0.0 的 simulate 不再接受 seed 参数
   （np.random.seed 亦不复现），测试改为固定 default_rng 的手写式 3.4 递推。
3. **arch 8.0.0 无 RiskMetrics2006/EWMAVariance 的 arch_model 字符串入口**：
   交叉验证改用固定参数 GARCH（ω=0, α=1−λ, β=λ，EWMA 是其特例）。
4. **历史模拟 ES 取「≥VaR」均值**（含 VaR 本身）：保证 ES≥VaR 在任意小
   样本/并列值下恒成立；口径写进返回 dict 的 note。
5. **Sharpe 与引擎同口径**（std ddof=1、rf/252 日化、×√252），用
   summarize_equity_curve 做同输入一致性抽查（rel 1e-9）。

## Files Changed

- 新增：`src/quant_research_engine/risk/{__init__,constants,tail,volatility,
  dependence,performance,report}.py`
- 新增：`tests/test_risk_{tail,volatility,dependence,performance,report}.py`
  （61 用例）
- 既有（前一轮）：pyproject.toml / uv.lock（arch>=6.3.0）、
  docs/agent/08_IMPLEMENTATION_BRIEF.md、docs/frm/（教材 + CR + 摘要）

## Validation

```
uv run pytest tests/ -x -q → 1532 passed, 4 warnings（基线 1471 + 61 净增，全绿）
风险包单测 61/61 绿（含全部教材例题复现）
scripts/check-progress-docs.sh → 见 10_REVIEW_REPORT
git diff --check → clean
```

## Known Limitations / Follow-ups

- R2（HIT/LR 回测、压力测试、CBB bootstrap）与 R3（markdown 渲染、回测报告
  集成、GUI 展示区）不在本任务范围（见 08 brief Non-Goals）。
- 非平稳 GARCH 输入（α+β≥1）触发 arch DataScaleWarning（爆炸模拟的固有
  现象），测试中显式 filterwarnings 压制。
- 未 git commit、未重启 qre-gui.service（用户约束）。

## Task ID

QRE-GUI-DEEP-VALIDATE-001 (deep-validate 501 骨架落地：策略 YAML → 逐日信号池 → 四关验证)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

承接 cfb860d 的 501 骨架，把 deep-validate 落地为真功能：GUI 对任意
catalog/沙箱策略一键跑 cluster-ashare 四关重型验证。

**① 路线选择（cluster 侧薄脚本，非 factor_executor）**：调查了
cluster-ashare `src/factor_executor.py`——其 condition_mask 语义是
「因子截面分位 + tag」筛池（服务 cluster.mined_factors），与 QRE 策略的
布尔表达式 DSL（如 `(close > sma_200) & (rsi_2 < 10)`）语义不匹配，强用会
改变策略含义。故采用任务书推荐路线：cluster-ashare 新增
`analysis/pool_from_conditions.py`（唯一新增文件，不改其既有代码），
输入条件 JSON、输出逐日池 parquet（trade_date, ts_code，直接可被
`signals.signal_from_parquet` 消费）。DB 访问与因子口径全留在 cluster 侧，
QRE 不碰业务库。表达式求值**不重写**：脚本把 QRE `src/` 插入 sys.path 直接
import `quant_research_engine.evaluation.signals.evaluate_expression_signal`
（纯 ast/pandas 模块），面板 sort(ts_code, trade_date) 后整表求值，与 QRE
EvaluationEngine 口径一致。列名/schema 表白名单正则校验防注入；只拉
used_fields（ast Name 节点）引用的列控内存。

**② QRE 转换器（新模块 `gui/deep_validate.py`，纯函数可单测）**：
- `spec_to_conditions(spec, d0, d1)`：StrategySpec → 条件 JSON
  （name/expression/factor_fields/market_fields/used_fields/d0/d1/qre_src/
  scope_note）。只纳入**入场**表达式；出场/止盈止损/持仓不进池（口径写进
  scope_note 与 job 结果）。
- `locate_strategy_yaml(name)`：沙箱优先，catalog rglob 按文件 stem 与
  experiment.name 双通道匹配。
- `parse_report_summary(md)` / `parse_validate_stdout(stdout)`：结论段
  GO/NO-GO + reasons + 「## 3. 四关结果」表逐关（天数/平均超额/t/正值率），
  已对真实 MF_001 / qre_mr01a 报告验证。

**③ 异步 job**：`start_deep_validate_job` 复用
`daily_jobs.start_script_job`（lock_key=`deep-validate:<name>` 同名串行
409）。runner 顺序跑两个 subprocess（cluster `.venv/bin/python`，各 4h
超时）：①pool_from_conditions.py → ②validate_factor.py --pool-parquet
--name qre_<name> --d0/--d1 --price-cache/--eval-cache（缓存键含区间落
`outputs/factor_mining/validation/qre_cache/`，断点续跑；daily_basic 缓存
存在则加 --basic-cache 启用 gate4）。终态解析 stdout + 报告 md 写
job_dir/result.json（verdict/conclusion/gates/pool 统计/report_path）。

**④ API（app.py）**：`POST /api/strategies/<name>/deep-validate`
（可带 d0/d1，默认 2015-01-01~今天）→ 404 未找到 / 400 invalid_yaml ·
no_entry_signal · missing_factors（复用 `_default_column_lookup` +
`find_missing_factor_columns`，缺失自动入 factor_request_queue）/ 500
cluster_unavailable（venv/脚本缺失预检）/ 409 同名在途；成功返回 job_id。
新增 `GET /api/strategies/<name>/deep-validate/<job_id>` 轮询（与因子冒烟
异步模式一致，终态附 result.json）。

**⑤ 前端（index.html）**：沙箱列表每行加「深度验证」按钮 + 行内 dv-slot
结果区；沙箱面板底部加「catalog/沙箱任意策略名 + d0/d1」通用入口。提交后
10s 轮询、**不设放弃上限**（仅连续 30 次网络失败才停）；终态渲染 GO 绿 /
NO-GO 红 + 逐关净超额/t + 池统计 + 报告路径 + 结论段。node --check 三段
内联 JS 全过。

**真实端到端冒烟**（catalog mr01a_rsi14_oversold_reversal，全历史默认
区间 2015-01-01~2026-08-19，直接命令行走 QRE 转换器→cluster 两脚本）：
- 池生成 41s：2826 信号日、1065 万条、平均 3770 只/日
  （rsi_14>30 本就是宽条件）；
- 四关验证 ~14min（含 1105 万行价格长表首建缓存）：**NO-GO**——
  gate1 -0.087%(t=-13.12)、gate2 -0.121%(t=-10.01)、
  gate3 子组合净超额 -0.130%(t=-10.75)、gate4 等权 -0.080%(t=-18.64)；
  报告 `cluster-ashare/outputs/factor_mining/validation/
  qre_mr01a_rsi14_oversold_reversal_四关验证报告.md`，
  parse_report_summary 逐关解析正确。

**测试**：`uv run pytest tests/ -x -q` → **1471 passed**（1454 + 17 净增：
新文件 test_gui_deep_validate.py 16 例——转换器/定位/报告解析/job worker
mock subprocess happy+pool失败+validate失败+日期校验/API 404/400×3/500/409/
提交+轮询；旧 501 测试删除）。未重启 qre-gui（用户约束）；未 commit。

上一任务：QRE-GUI-PROMO-GATE-001。

## Task ID

QRE-GUI-PROMO-GATE-001 (全量回测结果成为晋升后的状态闸)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

承接 76045d2「冒烟闭环+晋升闸」：晋升触发的全量回测不再跑完就完，结果评估为
promotion gate 并反哺日更与 dashboard。

**① 晋升回测打标记**：`gui/app.py` `/api/strategies/promote` 的全量回测 mark 改为
`{promotion_gate: True, promoted_strategy, purpose: "promote_full",
promotion_forced: bool}`，仍经 `run_backtest(mark=...)` 在线程启动前合并进
record（沿用上一轮消竞态结论）。force 晋升响应新增 `gate_note`（「闸结果仅展示，
不阻止日更（强制在库）」）。

**② 收尾评估钩子**：`gui/engine.py` `_execute_and_finalize` 尾部新增
promotion_gate 钩子（与 sandbox 钩子并列，try/except 兜底）→
`strategy_create.finalize_promotion_gate`（strategy_create.py:214 区域新增）：
判据写死 `GATE_MIN_TRADES=30` 且 `excess_return_vs_buy_hold > 0` → passed，
否则 failed；run 失败记 failed + error；指标复用 `extract_run_summary`
（SMOKE 同款 4 键）。结果原子写到 **`outputs/refresh/gates/<name>.json`**
（选型理由：与 registry.json/state.json 同族状态存储，在 outputs 下不进 git，
不污染 catalog；catalog 旁 <name>.gate.json 方案会弄脏仓库工作树）。
`gui/refresh_registry.py` 新增 `DEFAULT_GATES_DIR` / `gate_path` / `load_gate` /
`save_gate`（tmp+os.replace）/ `load_all_gates` / `gate_blocks_daily`
（failed 且非 forced 才阻止日更）。

**③ 日更联动**：`scripts/refresh_batch.py` 新增 `_apply_gate_filter()`（纯函数，
可测）；main() 在 stopped 过滤后跳过 gate=failed 非 forced 策略（`--strategies`
显式指定优先不做闸过滤），打印 `promotion-gate: skipped N failed strategies: ...`，
跳过名单记入 batch config `gate_skipped`（incremental 与 full 两处）。
`refresh_registry.list_catalog_strategies` 加 `skip_failed_gate=False`（默认
False——注册/开关校验语义不变）+ `gates_dir` 参数；`refresh_overview` 每行加
`gate` / `gate_blocks_daily`，顶层加 `gate_skipped`（跳过原因落 API 响应）。

**④ dashboard**：admin.html 策略状态 tab 表加「全量回测闸」列：
passed=绿✓通过 / failed=红✗未过（title tooltip 展示交易次数/超额/回撤/判据/
评估时间，标注「日更跳过」）/ 无 gate 文件=灰—未评估 / forced 且 failed=橙
⚑强制在库；style.css 加 `.gate-badge` 四态样式。

**⑤ force 通道**：force 晋升的 run mark 带 promotion_forced=True，闸评估照跑、
payload 透传 forced=True；`gate_blocks_daily` 对 forced 恒 False（不阻止日更）；
dashboard 显「强制在库」。

**⑥ 四关验证预留**：`POST /api/strategies/<name>/deep-validate` 端点骨架
（app.py，501 + code=not_implemented + design 字段：目标 CLI 路径、缺失的
「策略→信号池转换器」说明、四步规划），不实现转换逻辑。

**测试**：`uv run pytest tests/ -x -q` → **1454 passed**（1437 + 17 净增，全绿）。
新增：gate 评估判据 passed/failed×3(交易不足/超额≤0/缺指标)/run失败/forced 透传/
无标记忽略 7 例 + engine 钩子 completed/failed 2 例 + API mark 与 force gate_note +
deep-validate 501（test_gui_strategy_create.py）；gate 读写/阻止语义/catalog skip/
overview 字段 3 例（test_gui_admin_p3b.py）；admin.html 列渲染断言 1 例
（test_gui_admin_strat_tab.py）；_apply_gate_filter 单测 + refresh_batch e2e
跳过+config 记录 2 例（test_refresh.py）。node --check admin.html 内联 JS 随
test_gui_admin 通过。未重启 qre-gui（用户约束），真实 E2E 待重启验证。

上一任务：QRE-GUI-CREATE-GAPS-001。

## Task ID

QRE-GUI-CREATE-GAPS-001 (新增策略/因子闭环四缺口：冒烟回写 / 晋升闸 / 因子冒烟异步化 / 死代码)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

关联 CR：change_requests/2026-08-12_gui_create_strategy_factor.md。

**缺口 1 策略冒烟闭环**：
- `gui/engine.py`：`run_backtest` 加 `mark` 参数（线程启动前合并进 run 记录，
  消除事后打标记的竞态）；`_execute_and_finalize` 尾部钩子——record 带
  `sandbox_strategy` 时调 `strategy_create.finalize_smoke`（try/except 兜底）。
- `gui/strategy_create.py`：`finalize_smoke`（status=completed/failed +
  metrics[交易次数/总收益/超额/最大回撤，取自 engine.extract_run_summary] +
  finished_at + error）；`_atomic_write_json`（tmp+os.replace，record_smoke
  同用）；`read_smoke`；`list_sandbox` 对 running sidecar 自愈（查 run 终态
  补写，覆盖 GUI 重启丢 daemon 线程场景）。
- `index.html` 沙箱列表：通过=绿「冒烟通过」+ 指标摘要 / 失败=红 + 失败原因
  摘要（120 字截断）/ 在途=灰「冒烟中」；点击冒烟后每 5s 轮询刷新至多 2 分钟。

**缺口 2 晋升状态闸**：`strategy_create.promote` 与 `factor_create.promote_factor`
加 `force=False`；sidecar 缺失或 status != completed → code=smoke_not_passed，
路由层 409 +「先通过冒烟测试」；force=true 绕过且响应带 `forced: true` +
warning 注明。因子侧新增最小 sidecar `sandbox/factors/<name>.smoke.json`
（读 `read_smoke_record`，删因子时连删）。策略侧 gate 在查重之后（结构性
冲突优先报错）。

**缺口 3 因子冒烟异步化**：
- `gui/factor_create.py`：`start_smoke_job` 复用 `daily_jobs.start_script_job`
  （lock_key=`factor-smoke:<name>` 同名串行）；worker 内部跑既有 `run_smoke`
  （120s 超时与末行 JSON 解析不变，仅抽出 `_smoke_cmd`/`_parse_smoke_stdout`
  复用）；终态双写 job_dir/result.json + 沙箱 sidecar。
- `app.py`：POST /api/factor-create/smoke 提交即返回 `{ok, job_id, status:
  "running"}`（锁冲突 409）；新增 GET /api/factor-create/smoke/<job_id>
  （running 透传 / 终态合并 result.json）。
- `index.html` fc-smoke 改轮询（2s 间隔），终态渲染与既同步版一致。

**缺口 4 死代码**：删 `static/style.css` 的 `.p3c-hidden` + TODO-P3c-restore
注释（全仓 grep 确认模板/JS 零引用）。

**测试**：`uv run pytest tests/ -x -q` → 1437 passed（1417 + 20 净增，全绿）。
新增：策略侧 finalize/hook/自愈/gate/force 10 例；因子侧 start_smoke_job 3 例、
晋升闸 3 例、discard 连删 1 例、API 异步提交/409/轮询/force 4 例（test_api_smoke
按异步契约改写）。node --check 三段内联 JS OK。未重启 qre-gui（用户约束），
真实 E2E 待服务重启后验证。

上一任务：QRE-ADMIN-FACTOR-FRESH-001。

## Task ID

QRE-ADMIN-FACTOR-FRESH-001 (因子状态 tab 加新鲜度/滞后判定)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

背景：VM 停机导致 alpha191 日更漏跑（因子表停 08-17、stock_daily 已 08-18），
总览 tab 显示滞后，但因子状态 tab 只做列级三方对账、无新鲜度判定，全绿，
用户视角矛盾。本任务给因子状态 tab 补交易日 lag 判定。

**改动文件**：

1. `src/quant_research_engine/gui/admin.py`：
   - 新增 `trade_day_lag(table_watermark, daily_watermark, trade_dates)`：
     交易日差 = stock_daily 日期序列中晚于表 watermark 且不晚于基准的
     日期个数（非自然日差，跨周末不误报）；任一输入缺失返回 None。
   - 新增 `_fresh_level(lag)`：0→"ok" / 1→"warn" / ≥2→"err" / None→None。
   - `factor_status()`：复用 `overview_daily(db_url)["recent_trade_dates"]`
     （既有 DISTINCT trade_date 查询，同一 `_cached` TTL 300s），try/except
     包裹——失败时 trade_dates=None → 全表 fresh/lag_days=null、
     `fresh_available=False`，列级对账不受影响。每表 entry 加
     `lag_days`/`fresh`；返回加 `fresh_available` 与
     `summary.lagging`（lag≥1 计数）/`summary.stale`（lag≥2 计数）。
     alpha191 表在纳管清单内，同样判定（watermark 缺失→null 降级）。
2. `src/quant_research_engine/gui/templates/admin.html` 因子 tab：
   每表 `<summary>` 行 watermark 后加新鲜度徽标（ok=「最新」绿 /
   warn=「滞后1日」黄 / err=「严重滞后N日」红 / null=opt「-」）；
   summary 区在 lagging>0 时追加「新鲜度：滞后 X / 严重滞后 Y 张」；
   `fresh_available===false` 时提示降级。复用 ok/err/health-yellow/opt
   语义类，零 CSS 新增。
3. `tests/test_gui_admin.py`：+5 用例——`trade_day_lag` 交易日差
   （07-24 五→07-27 一自然日 3 天但 lag=1）与缺失输入降级、
   `_fresh_level` 分档、factor_status lag=1 warn 集成（防自然日差回归）、
   lag 0/3 分档 + summary lagging/stale 计数、overview_daily 异常时
   fresh=null 且列级对账不受影响的降级路径。既有 three_way 用例的
   summary 断言改为逐 key（summary 新增两键）。

**真实验证**（2026-08-19）：`sudo -n systemctl restart qre-gui.service` →
active；`curl /api/admin/factor-status` → daily_watermark 2026-08-18、
fresh_available true、alpha191 wm 2026-08-17 lag=1 fresh=warn、其余 10 张
纳管表 lag=0 fresh=ok，summary green=537/yellow=0/red=0/lagging=1/stale=0。

**测试**：`uv run pytest tests/ -x -q` → 1417 passed（1412 + 5，全绿）。

上一任务：QRE-ADMIN-CLUSTER-001。

## Task ID

QRE-ADMIN-CLUSTER-001 (dashboard 新增「聚类分析」页：只读展示 cluster-ashare 因子工厂产出)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

管理台定位保持「只查询状态」：全部数据源只读（PG 只发 SELECT，文件只读），
不写任何数据；每个分区独立 try/except 降级，某数据源不可用时该分区显示
错误+重试按钮，不拖垮整页。

**改动文件**：

1. `src/quant_research_engine/gui/cluster_admin.py`（新增，~330 行）：
   - `cluster_repo()`：`QRE_CLUSTER_REPO` 环境变量，默认
     `Path(__file__).parents[4]/"cluster-ashare"`（= /home/van/quant-workspace/cluster-ashare，
     与 QRE_INDICATORS_REPO 先例一致）。
   - `factor_registry(db_url)`：SELECT cluster.mined_factors（factor_id/
     family/status/definition/evidence），展开为 因子 id/条件 key/类型/状态
     （在库=绿 active、衰减观察=黄 decay）/跨年数 n_years/方向一致率
     consistency/+5 超额 excess_d5；status_counts 汇总。
   - `m4_overview(repo)`：读 clustering/m4_meta.json（k、ARI、n_sig、
     hidden.explain 画像、top_dims）+ m4_trajectories_alive.csv（20 轨迹，
     q<0.05 且正超额标 significant 排前）+ hidden_cluster_members.csv
     前 50 行。
   - `monitor_health(repo)`：glob 最新 monitor_*.md，`parse_monitor_md`
     解析 markdown 因子表（MF_ 行过滤表头/分隔线），按建议列计数 +
     「建议转衰减观察」清单。
   - `report_links(repo)`：REPORT_ARTIFACTS 清单（不存在的跳过）+ 最新
     monitor 报告置顶；`resolve_artifact` 白名单：resolve 后必须在
     factor_mining 根内且后缀 ∈ {.md,.csv,.json}。
   - `cluster_overview`：聚合四分区，分区级异常兜底。
   - 全部走 admin._cached TTL 300s（含 single-flight）。
2. `src/quant_research_engine/gui/app.py`：+2 路由——`GET /api/admin/cluster`
   （聚合 JSON）、`GET /api/admin/cluster/artifact/<path>`（send_file 下载，
   白名单外 404）。
3. `src/quant_research_engine/gui/templates/admin.html`：第 6 个 tab
   「聚类分析」，4 个 section-toggle 分区 + loadCluster() JS
   （fetchWithTimeout 30s、cardError 重试、注册表客户端搜索过滤）；
   沿用现有 ok/err/health-yellow/kpi/num/admin-card 样式类，零 CSS 改动。
4. `tests/test_gui_cluster.py`（新增 14 用例）：monitor md 解析、
   m4_overview 正常/缺文件/坏 JSON 降级、monitor 缺目录/空目录降级、
   report_links 存在性过滤、resolve_artifact 越界+后缀白名单、
   factor_registry fake-store + /api/admin/cluster 路由 200 分区降级、
   下载路由正反例、/admin 页面含新 tab。

**真实验证**（2026-08-19）：
`sudo -n systemctl restart qre-gui.service` → active；
`curl /admin` 200；`curl /api/admin/cluster` → 四分区全 ok：
registry total=38（在库 35/衰减观察 3），m4 k=20 sig=2 trajs=20
members=50，monitor report=monitor_2026-08-18.md 正常 9/关注 23/
建议转衰减 5（MF_008/011/015/025/035），links artifacts=13；
下载 m4_meta.json 200、monitor md 200、parquet 404、路径穿越 404。

**测试**：`uv run pytest tests/ -x -q` → 1412 passed（1398 + 14，全绿）。

上一任务：QRE-M5C-MINED-FACTOR-STRAT-001。

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization; 回测结论为「未复现 M3b 超额」，策略上线与否待用户决策)

## Implementation Summary

零 QRE 代码改动任务（同 P6 先例）：cluster.mined_factors 综合分 Top 3
（MF_001/002/003，M3b 跨年度加固存活）各转译一个 QRE 策略，走通
「沙箱→冒烟→晋升→全市场回测→报告 audit」全闭环。

**转译方案（关键决策）**：QRE 信号 DSL（evaluation/signals.py）只支持行内
"因子 vs 阈值/布尔组合"（比较 + and/or + 算术 + .shift），**不支持截面
rank/分位**；alpha072/082 在 factors.stock_daily_alpha191 中也非 cs_rank
（2026-08-17 实测 min 21.07 / max 99.39），P6 的固定阈值近似不可用。
两条候选路（阈值绝对化 / 读 cluster.mined_factor_signals）都被否：
阈值随 regime 漂移；signals 是长表且未命中股票无行（QRE 行情×因子
inner join 会把缺行股票丢出 universe）。最终方案：cluster-ashare 侧用共享
executor（condition_mask，与 M3b 验证/注册表信号同一函数）逐日全市场
物化 0/1 宽表 `cluster.mined_factor_flags(trade_date, ts_code, mf_001/002/003)`
（未命中也写 0），QRE 以既有三段式寻址 `cluster.mined_factor_flags.mf_00X`
直接引用（FactorFieldRequest 本就支持任意 schema），entry 为行内等值
`mf_00X == 1`。QRE 对业务库只读红线不受影响：建表/写库全部由
cluster-ashare 脚本执行（deploy/sql/20260818_mined_factor_flags.sql +
analysis/factor_flags_export.py，回填 279 交易日 1,526,215 行，
与 mined_factor_signals 重叠窗口逐行一致，双向差集为 0）。

**策略**（cross_sectional，T 日信号 T+1 开盘，持仓 5 日对齐 M3b +5 窗口，
止损 8%，universe 过滤 ST/停牌/风险警示/上市<120 日）：

| 策略 | 因子 | 条件语义 |
|---|---|---|
| cs07a_mf001_atrr14_high_hv20_normal_mvp | MF_001 | atrr_14 截面≥80% ∧ 非 hv20:极低 |
| cs07b_mf002_alpha072_low_mvp | MF_002 | alpha072 截面≤20% |
| cs07c_mf003_alpha082_low_mvp | MF_003 | alpha082 截面≤20% |

**闭环各环节**：

1. 沙箱登记（save_to_sandbox：validate+查重+落盘 outputs/sandbox/strategies/）3/3 ok。
2. preflight 实测 cluster schema 寻址正常（check_factor_schema/coverage/join 全 ok）。
3. 冒烟（qre backtest-batch，20 股 × 2026-02-18~2026-08-17）3/3 ok：
   trades 14/91/76，成本生效，无失败单异常；sidecar 已记录。
   注：cs07a 冒烟仅 1/20 股有交易（MF_001 信号池偏中小盘，20 只大盘样本命中少），
   冒烟只验证链路，全市场回测覆盖 1346 只有交易股票。
4. 晋升（promote → strategies/catalog/cross_sectional/）3/3 ok。
5. 全市场回测（batch_backtest_runner，3820 股（universe 过滤后）×
   2025-08-18~2026-08-17，--apply-stops --universe-filter --compact --workbook
   --jobs 3，基准 reference.index_daily/000300.SH）3/3 ok，各 ~556s，
   批次 `outputs/backtests/b21f1008ec98/`。
6. report-audit：3 backtest + 3 eval manifest 全部 status=ok / issues=0。

**回测指标（近 1 年，含成本，基准 000300.SH +11.83%）**：

| 策略 | 组合总收益 | 超额 vs 基准 | 最大回撤 | 夏普 | 交易数 | 胜率(笔) | 正收益股比例 |
|---|---|---|---|---|---|---|---|
| cs07a MF_001 | +0.75% | **-11.08%** | -1.65% | 0.32 | 14,441 | 44.2% | 14.5% |
| cs07b MF_002 | +0.54% | **-11.29%** | -1.28% | 0.28 | 13,660 | 46.2% | 30.1% |
| cs07c MF_003 | +0.26% | **-11.58%** | -1.39% | 0.14 | 13,013 | 45.5% | 29.0% |

eval 阶段事件前瞻（~25 万事件/策略）：+5 日均值 +0.32%/+0.14%/+0.09%，
胜率 46.6%/46.8%/46.6%（<50%），中位数全为负。

**与 M3b 预期对比（结论：方向不一致）**：M3b evidence 的 +5 超额
（MF_001 +7.89% / MF_002 +3.53% / MF_003 +3.74%）在 QRE 近 1 年
全市场口径下未复现——三策略超额全为显著负值。口径差异需如实说明：
M3b 是「涨幅 Top1% 异动日触发」的事件采样（2015-2025 跨 regime  pooled，
无成本无止损、收盘口径）；QRE 是「每日全市场信号」全时段触发
（T+1 开盘、含成本、8% 止损、5 日到期）。近 1 年为基准 +11.8% 的
偏牛 regime，且 M5b 监控首报已显示 37 因子中 28 个近 20 日超额为负
（近期整体衰减），二者一致。**建议：MF_001/002/003 由「在库」转
「衰减观察」（cluster 侧 mined_factors.status，待用户确认后执行），
不接入自动交易日更**；策略 YAML 保留 catalog 供后续 regime 切换后复测。

**测试**：`uv run pytest tests/ -x -q` → 1398 passed（零代码改动，基线持平）。
日更：refresh registry 为空 = 全量扫描，cs07a/b/c 会随 refresh 日更拾取
（refresh 仅重算回测产物，非交易执行）。

## Task ID

QRE-ADMIN-TIMERS-001 (dashboard 日更定时任务清单补全)

## Summary

- gui/admin.py TIMER_UNITS 新增 3 条：alpha191-daily.timer、cluster-ashare-daily.timer（含 ExecStartPost 的 daily_tags 增量）、cluster-ashare-tags-weekly.timer。纯配置数组追加，无逻辑改动。
- 验证：pytest 1398 绿；systemctl restart qre-gui 后 /api/admin/timers 返回 6 条 installed+active。

## Task ID

QRE-GUI-ALPHA191-GROUP-001 (alpha191 进因子下拉 + GUI 开机自启服务)

## Written By

KIMI_CODE (single agent)

## Summary

- `gui/factor_wizard.py`：`build_factor_groups` 对 `stock_daily_alpha191`（无价格后缀，parse_factor_table_name 返回 None）单独成组 alpha191；`CATEGORY_LABELS` 加 `alpha191: Alpha191 量价因子`。验证：重启 GUI 后 `curl /api/factors` 10 组，alpha191 组 191 项。
- `deploy/hardened/qre-gui.service`（新增）：GUI 常驻 systemd 服务，EnvironmentFile 读 .env，Restart=on-failure，MemoryMax=2G，已安装并 `enable --now`（开机自启生效，实测 active + 200）。
- 测试：`uv run pytest tests/ -x -q` → 1398 passed。

## Task ID

QRE-ALPHA191-STRAT-LOOP-001 (P6：头部 alpha191 因子新建策略闭环自测)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

零代码改动任务：3 个头部 alpha191 因子各设计一个阈值策略，走通
「沙箱→冒烟→晋升→全市场回测→报告→日更登记」全闭环，**无断点、无引擎修复**。

**策略设计**（阈值标定：alpha083/099 本身即 cs_rank 输出 ∈[-1,0]，阈值即
截面分位；alpha042 阈值取自 2024-08-14 起全市场分位数 p90≈0.015/中位≈-0.24）：

| 策略 | 因子语义 | 入场 | 出场 | 持仓 |
|---|---|---|---|---|
| pv06a_alpha083_high_rank_mvp | -RANK(COV(RANK(HIGH),RANK(VOL),5)) | alpha083 > -0.2（前20%） | alpha083 < -0.5 | 10 天，止损 8% |
| pv06b_alpha099_high_rank_mvp | 同族，HIGH→CLOSE | alpha099 > -0.2 | alpha099 < -0.5 | 同上 |
| pv06c_alpha042_high_rank_mvp | (-RANK(STD(HIGH,10)))*CORR(HIGH,VOL,10) | alpha042 > 0.0（≈前12%） | alpha042 < -0.25 | 同上 |

**闭环各环节（耗时实测）**：

1. 沙箱登记（save_to_sandbox：validate+查重+落盘 outputs/sandbox/strategies/）
   3/3 ok，各 ~0.15s。
2. 冒烟（qre backtest-batch，20 大盘股 × 2026-02-14~08-14）3/3 ok：
   57.5s / 46.7s / 49.3s；round trips 129 / 124 / 100，信号正常产出；
   smoke sidecar 已记录。
3. 晋升（promote → strategies/catalog/price_volume/）3/3 ok，各 ~0.15s。
4. 全市场回测（batch_backtest_runner，5560 股 × 2025-08-14~2026-08-14，
   vectorized，chunk 400，compact+workbook，apply-stops，universe-filter，
   benchmark 000300.SH，jobs 3）3/3 ok，各 683/692/694s（eval ~14s，
   preflight ~74s）。产物 outputs/backtests/alpha191_p6/568f665c8217/。
5. 报告：每策略 backtest_report.html/xlsx + 图 + report_manifest 齐全；
   `qre report-audit` status=ok（matched 3 / missing 0 / issues 0）。
6. 日更登记：registry include 空 = 全量扫描 catalog，晋升即被
   refresh_batch 拾取；`refresh_batch.py --check-only --strategies pv06*`
   正常（watermark 2026-08-14 vs state 2026-08-11 → refresh needed）。

**回测关键指标**（batch 每股 100 万满仓复利口径；benchmark=沪深300）：

| 策略 | 总收益 | 基准收益 | 最大回撤 | 交易数 | 胜率 | Sharpe | PF |
|---|---|---|---|---|---|---|---|
| pv06a alpha083 | +1.61% | +11.76% | -1.08% | 17170（2688 股） | 48.8% | 0.77 | 1.12 |
| pv06b alpha099 | +1.03% | +11.76% | -1.11% | 17054（2689 股） | 48.8% | 0.53 | 1.10 |
| pv06c alpha042 | +1.44% | +11.76% | -1.45% | 11637（2694 股） | 49.6% | 0.72 | 1.15 |

（正收益但跑输基准——满仓复利 per-symbol 口径下正 IC 因子的截面优势被
稀释，符合"链路验证"定位；非投资建议，R-QRE-008。）

## Validation

- `uv run pytest tests/ -x -q` → **1398 passed**（无代码改动，无新增测试需求）。
- preflight 小样本（3 股）全 ok：alpha083 coverage 1.0、join 1.0；
  全市场批次 preflight=warning 为 universe 排除计数>0 的设计行为
  （check_universe excluded→warning，见 preflight.py:232），非断点。

## Findings / Follow-ups

- 无断点：alpha191 因子三段式寻址（factors.stock_daily_alpha191.<col>）在
  validate/查重/preflight/eval/backtest/refresh 全链路开箱可用。
- 策略收益口径提示：batch per-symbol 满仓复利会稀释截面选股效应；后续若要
  验证截面超额，可跑 shared-cash + score_weight 变体（未做，超出本任务）。

---

## Task ID

QRE-EVAL-ALPHA191-001 (Alpha191 赚钱效应评估管线 + GUI 路径 C 登记)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`src/quant_research_engine/evaluation/alpha191.py`**（新增）：口径常量
   （ALPHA191_TABLE / ALL_ALPHA_FACTORS / FORWARD_HORIZONS=[1,3,5,10,20] /
   PRIMARY_HORIZON=5 / QUANTILES=5 / 显著性阈值 0.05+0.55）；
   `daily_rank_ic()`（逐日 Spearman，与引擎 ic_summary 同公式，补引擎不落盘的
   std 供 ICIR）；`summarize_factor_result()`（ic_win_rate 取方向一致率：负 IC
   因子取 1−正向占比；top_minus_bottom=Q5−Q1，quantile=1 为因子最低组）；
   `build_leaderboard()`（|mean_rank_ic| 降序、NaN 垫底）；
   `evaluate_alpha_factors()`（每批 batch_size=10 个因子一次
   ResearchFrameAssembler.build(ts_codes=None, market_fields=["close"],
   factor_fields=FactorFieldRequest.from_target(f,"factors.stock_daily_alpha191.f"))，
   逐因子 evaluate(signal="close > 0" 占位, quantiles=5, 成本引擎默认 None)，
   批后 del+gc；单因子失败记 None 行不阻断）。
2. **`scripts/eval_alpha191.py`**（新增薄 CLI）：--start/--end（默认近 2 年）/
   --factors(all|逗号列)/--top(stdout 打印行数，CSV 始终全量)/--output
   （默认 outputs/alpha191/leaderboard.csv）/--batch-size/--db-url。
3. **`tests/test_eval_alpha191.py`**（新增 6 用例）：合成面板（因子驱动次日
   收益）端到端正 IC/★、排序与列结构、日频 IC、失败行不阻断、CLI main
   （monkeypatch store+evaluate）写 CSV、resolve_factors 校验。
4. **`gui/templates/index.html`**：新增因子 tab 路径说明卡 h2 改
   「路径说明（A / B / C）」并加路径 C 文案（Alpha191 通道，指向
   indicators_tushare/alpha191/README.md，本期不支持 GUI 内新建）。纯文案，
   JS/路由零改动。
5. **引擎/catalog/assembler 零改动**：stock_daily_alpha191 直接走既有
   FactorFieldRequest 三段式寻址（factors.<table>.<column>），无需 factors.yaml
   纳管适配。

## Validation

- `uv run pytest tests/ -x -q` → **1398 passed**（1392 + 6 净增，全绿）。
- 真实小样本（postgresql+psycopg:///tushare_data）：
  - 用户指定窗口 2025-08-01~2026-08-13：3 因子全 None（observation_dates=0）——
    回填当前仅完成 2010→2013 + 日更当日 2026-08-13，该窗口无因子数据，管线
    行为正确（非装配缺陷）。
  - 改用已覆盖窗口 2012-08-01~2013-08-13：alpha001 rank_ic=0.0551/胜率 0.812/
    ICIR 0.890/★；alpha006 0.0512/0.705/0.521/★（top_minus_bottom NaN）；
    alpha012 0.0204/0.624/0.327；234 个交易日。leaderboard 写 /tmp/alpha_eval_smoke.csv。

## Findings / Follow-ups

- **上游数据疑点（未处理，登记）**：alpha006 在回填段逐日仅 ~3 个 distinct 值
  （2013-01-15：2157 行仅 3 值；全窗口 53 万行仅 701 distinct），疑似
  indicators 侧 alpha006 公式把时序 corr 算成截面/常量。引擎 qcut 无法分 5 层
  → top_minus_bottom NaN 是正确表象。建议回填完成后在 indicators 侧核查
  alpha006（GTJA #6 = −corr(open, volume, 10) 应为逐股时序）。
- 回填完成前用默认近 2 年窗口跑 `--factors all` 会得到大量 None 行；待 P3c
  行数/覆盖验证通过后再跑全量 leaderboard。
- ★ 判定用方向一致率（负 IC 因子按反向计），与用户任务书「胜率≥0.55」的
  字面口径有解释性偏离，已在 alpha191.py docstring 注明。

---

## Task ID

QRE-ADMIN-ALPHA191-RECON-001 (dashboard 因子对账登记 stock_daily_alpha191)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

alpha191 面板通道表（indicators_tushare 侧 `alpha191/` 子包日更，独立于
config/factors.yaml 的 category×price 体系）登记进管理台因子对账：

1. **`gui/admin.py`**：
   - 新增 `ALPHA191_TABLE = "stock_daily_alpha191"` 常量；
     `managed_factor_tables()` 在 yaml 推导与 fallback 两条路径都并入该表。
   - `overview_factors()` 的表过滤改为「不符合 `<category>_<price>` 命名
     **且不在纳管清单**才跳过」，alpha191 由此进入对账（watermark/滞后判定）。
   - `EXPECTED_COLUMNS_SCRIPT` 追加读取 indicators 侧
     `alpha191/factors_manifest.yaml`（由 indicators
     `scripts/gen_alpha191_manifest.py` 从 FORMULAS 注册表生成，191 列），
     合成 `stock_daily_alpha191` 的期望列；manifest 缺失时静默跳过（降级不变）。
2. **不做的事**：`parse_factor_table_name` 正则未动 —— admin 的
   因子补全/删列按钮对 alpha191 返回 400（alpha191 回填走自己的
   `alpha191.runner`，不经 run_factor_admin）；factor_wizard 分组也不含它。
3. **测试**：tests/test_gui_admin.py 更新 2 个既有断言（config/fallback 清单
   含 alpha191，fallback 计数 10→11）+ 新增
   `test_factor_status_includes_alpha191`（绿/红分流）。

## Validation

- `uv run pytest tests/ -x -q` → **1392 passed**（1391 + 1 净增，全绿）。
- 真实对账（2026-08-14，`postgresql+psycopg://…/tushare_data`）：
  `factor_status()` 中 `factors.stock_daily_alpha191` watermark=2026-08-13、
  db_cols=191、green=191 / yellow=0 / red=0，`expected_available=True`；
  `overview_factors()` 含该表且不在 lagging_tables。
- 依赖前置：indicators 侧已生成 `alpha191/factors_manifest.yaml`（191 列）
  并完成当日日更点火（5560 行 upsert，alpha191-daily.timer 17:00 工作日）。

## Follow-ups

- alpha191 全历史回填进行中（indicators 侧后台任务），回填完成前列可能
  短暂显示 red（缺列）——对账语义正确，无需处理。

---

## Task ID

QRE-GUI-UIUX-001 (GUI 全站 UI/UX 优化：Data-Dense Dashboard 浅色风格)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

按 ui-ux-pro-max 数据库选定的 Data-Dense Dashboard（浅色）方案执行，不改任何
元素 id / JS 逻辑 / API / 表单字段 / 文案：

1. **`static/style.css` 全量重写**：设计变量集中 `:root`
   （--bg #F8FAFC / --card #FFF / --border #E2E8F0 / --text #1E293B /
   --muted #64748B / --primary #1E40AF / --primary-hover #1E3A8A /
   --ok #16A34A / --warn #B45309 / --err #DC2626 / --radius 6px / --mono），
   全站引用变量。按钮分级体系 .btn / .btn-primary / .btn-ghost /
   .btn-danger-outline / .btn-sm；表格斑马纹 + hover 高亮 + sticky 表头 +
   .num 右对齐 tabular-nums；tab 改下划线式（active 2px primary 指示条）；
   section-toggle 改白底 + 左侧 4px primary 竖条；health-green/yellow/red 与
   .ok/.err 颜色值换为语义色（类名不变）；字体 system-ui + PingFang SC /
   Microsoft YaHei 回退，等宽列 ui-monospace 栈。
2. **`templates/base.html`**：nav 与标题合并为紧凑顶栏 .topbar
   （左 brand「QRE 控制台」，右导航链接）。
3. **按钮分级归类（仅加 class）**：primary 实底仅 btn-run（运行回测）、
   fc-generate（生成代码）、btn-compare、btn-full-run；刷新/验证/加载文件/
   模板/编译/提交申请/查重/冒烟 → .btn-ghost；危险操作（mt-delete、fc-promote、
   sb-delete、fc 沙箱删除、wz-admin-confirm 全量回填）→ .btn-danger-outline。
4. **信息直读化**：admin 健康灯 CSS 级放大为状态条（#ov-health p 16px 半粗）；
   最新交易日 / 批次数 / 磁盘占用加 .kpi（19px 半粗）；估算行数、因子表行数、
   超额收益/最大回撤、批次体积/策略数、run_detail 摘要值、compare A/B/差异列、
   strategy_status_detail 指标值加 .num；admin.html 三处内联 `color:#a80`
   替换为 .health-yellow。
5. **未动**：所有 id、事件绑定、JS 逻辑、API、文案语言；「引擎输出，非投资建议」
   提示保留；tests 断言只引用 id（btn-nl-compile / btn-save-sandbox），无需改断言。

## Validation

- `uv run pytest tests/ -x -q` → **1391 passed**（全绿，无断言改动）。
- 临时实例 `uv run qre gui --host 127.0.0.1 --port 8123`：
  - `curl /` → 200，含 class="topbar"/brand、btn-primary ×2、btn-ghost ×8；
  - `curl /admin` → 200，含 topbar、btn-ghost ×5、btn-danger-outline；
  - `curl /static/style.css` → 含 --primary: #1E40AF。
- 实例已用 `pkill -f 'qre g[u]i'` 杀掉，8123 端口确认释放。

## Files Changed

- `src/quant_research_engine/gui/static/style.css`（全量重写）
- `src/quant_research_engine/gui/templates/base.html`（顶栏）
- `src/quant_research_engine/gui/templates/index.html`（按钮 class）
- `src/quant_research_engine/gui/templates/admin.html`（按钮 class + kpi/num/health-yellow）
- `src/quant_research_engine/gui/templates/runs.html`、`run_detail.html`、
  `compare.html`、`strategy_status_detail.html`（按钮 class / .num 列）

# Coding Handoff (archive: QRE-GUI-HOME-REFACTOR-001, GUI 首页三 tab → 两 tab 重构)

## Task ID

QRE-GUI-HOME-REFACTOR-001 (GUI 首页三 tab → 两 tab 重构)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`templates/index.html` 整体重写（1549 行 → ~1060 行）**：三 tab（wizard/builder/
   editor）合并为两 tab。「新增策略」（默认 landing）三段垂直流：顶部 NL 面板
   （nl-*，/api/nl_compile 产物填同页底部预览栏，缺因子引导跳「新增因子」tab）→
   中部可视化构建（wizard step1 因子实时枚举 + step2 条件/持仓风控，wz-fill-editor
   改为校验后同页填入 #strategy-yaml 并 scrollIntoView，不再跳 tab）→ 底部 YAML
   预览栏（可编辑）+ 操作行（验证/加载文件/模板/保存模板/存入沙箱）+ 回测参数表单
   （常显精简项 + 默认折叠「高级参数」区：引擎/执行方式/DB URL/market profile/
   输出目录）+ 沙箱策略面板。运行逻辑不变（预检勾选 → 小范围）。「新增因子」tab：
   路径说明卡 + 路径 A（wz-admin-* 新因子申请整体移入）+ 路径 B（fc-create 子区
   从 admin.html 整体移入，/api/factor-create/* 调用不变）。JS 重组为三个 IIFE
   （tabs+section toggle / strategy / factor），元素 ID 全部保留（b-* 除外，全删），
   rerun_yaml sessionStorage 回填改为同页滚动。tab-builder HTML 与其 JS IIFE 全删；
   后端 /api/builder/* 保留，app.py 零改动。
2. **`templates/admin.html`**：因子 tab 的 fc-create 子区 HTML 与 fc JS 全删，
   原地留「→ 新增因子请前往首页」链接（href="/"）；其余不动。
3. **测试**：test_gui_factor_wizard.test_index_page_contains_wizard 与
   test_gui_app.test_index_includes_builder_tab 改为新两 tab 结构断言（含
   fc-create 在首页、tab-builder/builder-layout/b-id 不存在）；
   test_gui_admin.test_admin_page_200 增加 admin 无 fc-create + 跳转链接断言。
4. **文档**：STRATEGY_AUTHORING §3 通道表重写（三入口合一页）；indicators
   FACTOR_AUTHORING §8 改为首页「新增因子」tab 路径 B（路径 A 同页）。

## Validation Output

```bash
uv run pytest tests/ -x -q → 1391 passed, 4 warnings（全绿）
node --check（index.html / admin.html 内联 JS 提取）→ 双双语法通过
scripts/check-progress-docs.sh → passed
```

临时 GUI 冒烟（127.0.0.1:8123，未跑真实回测/backfill）：`/` 含 tab-strategy /
tab-factor / fc-code / wz-factor-groups，无 tab-builder / builder-layout / b-id；
`/admin` 无 fc-create / fc-code，含「新增因子请前往首页」；
/api/factors、/api/factor-create/sandbox、/api/strategies/sandbox 均 200。
进程已清理。

# Coding Handoff (archive: QRE-ADMIN-STRAT-INCREMENTAL-FIX-001, 策略状态 tab 增量结果合并：date_end 停在全量批次的显示 bug)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

问题：策略状态 tab 数据只来自 `outputs/backtests/**/<sid>/backtest/strategy_performance.json`，
而每日增量 refresh（qre-refresh.timer 20:30）只写 `outputs/refresh/incremental/<sid>/`，
date_end 停在最近全量批次（2026-07-27），日更实际已到 2026-08-11。

1. **`gui/refresh_registry.py`**：
   - 新增 `DEFAULT_INCREMENTAL_ROOT = outputs/refresh/incremental`；
     `_load_incremental_result()` 读 `<sid>/backtest/summary_metrics.json`
     （5 键）+ 同目录 `state.json` 仅取 `data_watermark`/`last_processed_date`
     （缺字段容错，不伪造 date_end；symbols 大字段不用于展示）。
   - `latest_strategy_result(sid, backtests_dir, incremental_root=None)` 合并两源：
     增量 mtime 更新 → source="merged"，新鲜字段（date_end/symbol_count/
     traded_symbol_count/mean_total_return/total_trades/positive_return_symbol_rate）
     取增量；全量指标（excess_return_vs_buy_hold/max_drawdown/date_start/
     strategy_name 等）仍取最新批次，附 `full_metrics_as_of`（批次 date_end）与
     `full_metrics_source_file`；artifact_dir 指向增量目录（详情页下载链接随之切换）。
     批次更新 → "batch"；仅增量 → "incremental"。返回新增 `source`/`source_mtimes`，
     原键（metrics/source_file/artifact_dir/mtime）不变。缓存键纳入增量根
     （`strategy_result:<bt>:<inc>:<sid>`），`clear_strategy_result_cache` 同步。
   - `refresh_overview(..., incremental_root=None)`：策略行 date_end 用合并新鲜值，
     新增 `source` 与 `full_metrics_as_of`（仅当 < date_end 时下发，供前端标注）。
2. **`gui/app.py`**：产物下载路由白名单从仅 backtests 扩到 backtests +
   refresh/incremental 双根（root.parents 任一命中即合法）。
3. **`templates/admin.html`**：超额/回撤单元格在 `full_metrics_as_of < date_end` 时
   加小字"（全量截至 YYYY-MM-DD）"；date_start 缺失时区间列容错显示 "— ~ date_end"。
4. **`templates/strategy_status_detail.html`**：来源行标注 batch/incremental/merged；
   回测区间行附全量 as_of 小字。equity_curve.csv（133MB 级）保留下载链接，无内联预览。
5. **测试 `tests/test_gui_admin_strat_tab.py`（+7 条）**：仅增量、merged（增量更新）、
   批次更新保持 batch、缺 watermark 容错、缓存键隔离、overview 行合并值。

## Validation Output

```bash
uv run pytest tests/test_gui_admin_strat_tab.py tests/test_gui_admin_p3b.py -x -q → 39 passed
uv run pytest tests/ -x -q → 1391 passed（1385 + 6 净增，全绿）
```

真实数据验证（2026-08-12）：`latest_strategy_result("mr03a_bollinger_lower_reversion")`
→ source="merged"，date_end=2026-08-11（增量 state.json watermark），
symbol_count 3788 / traded 2261（增量），max_drawdown −0.4636 / benchmark_excess
−0.3454 / date_start 2010-01-04（全量批次），full_metrics_as_of=2026-07-27，
artifact_dir=outputs/refresh/incremental/mr03a_bollinger_lower_reversion。
`refresh_overview()` 同行字段一致（source=merged，full_metrics_as_of=2026-07-27）。

# Coding Handoff (archive: QRE-GUI-FACTOR-CREATE-P2-001, GUI 新因子创建闭环：NL/手写 → 生成草稿 → 查重 → 沙箱冒烟 → 确认晋升 → indicators 入库)

## Task ID

QRE-GUI-FACTOR-CREATE-P2-001 (GUI 新因子创建闭环：NL/手写 → 生成草稿 → 查重 → 沙箱冒烟 → 确认晋升 → indicators 入库)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **`gui/factor_nl_compiler.py`**（新）：因子 NL 生成器。复用 `nl_compiler.call_llm`
   （新增可选 `system_prompt` 参数）与 `nl_config`。独立系统提示词（FactorBase
   约束 + SMA/ATR 两个 few-shot），两段式输出协议 `<<<CODE>>>` / `<<<META>>>`
   （YAML: name/category/column/periods|params），超范围输出 `<<<ERROR>>>` 转
   "请走人工通道"。`check_code_safety(code)`：AST 白名单——只允许 import
   pandas/pandas_ta/numpy/typing/core.factor_base；禁 open/eval/exec/compile/
   __import__/input/globals/locals；禁危险 dunder（__class__/__globals__/
   __subclasses__ 等 12 个；`__init__` 等常规魔术方法允许）；语法错误即拒绝。
   `generate_factor_code(description, http_post=None, env=None)` →
   {ok, code, meta} / {ok: False, code, error}。
2. **`gui/factor_create.py`**（新，纯函数层，repo/runner/job_starter 可注入）：
   - `check_factor_duplicate(name, category, column, params, tables_columns=None,
     config_path=None)`：库内现列（表 `stock_daily_<cat>_<col>`，列名
     `<name>_<suffix>` 精确/前缀匹配）+ config 条目双源查重；同名指标（任意
     类别/价格列）一律拒绝并引导走 factor-admin 通道。
   - 沙箱：`save_factor_to_sandbox`（安全检查 → `sandbox/factors/<name>_factor.py`）、
     `list_sandbox`、`discard_factor`。
   - `run_smoke`：subprocess 跑 indicators `sandbox/smoke_factor.py`（uv run，
     cwd=repo，120s 超时），解析 stdout 最后一行 JSON。
   - `check_no_admin_running`：pgrep -af "run_factor_admin|run_factor_repair"
     为空检查（过滤含 "pgrep" 的行，消除 bash -c 自匹配误报）。
   - `promote_factor(name, category, column, params, ...)`：pgrep 闸 → 复制
     `factors/<name>_factor.py`（已存在拒绝）→ 二次安全检查 → 备份 + 追加
     config（periods/params/[null] 三种风格）→ `start_script_job(lock_key=
     "indicators")` 后台跑 `validate --codes 600519.SH --sample-rows 800 &&
     backfill --baseline-ref HEAD --categories <cat> --max-workers 4 --execute`
     （bash -c 串联）；写入失败自动回滚（删文件、恢复备份）。
3. **indicators `sandbox/smoke_factor.py`**（新）：CLI 冒烟——importlib 加载文件 →
   唯一 FactorBase 子类 → DBManager.load_stock_history 只读单股近 N 日 →
   逐参数 calculate() → 断言无异常/列存在/跳过 warmup 非全 NaN/列名规范化无重复；
   stdout 末行 JSON，exit 0/1。
4. **API（`gui/app.py`，6 个 `/api/factor-create/*`）**：nl-generate（只回填不执行）
   / check（安全+查重，DB 挂降级 warning）/ smoke（同步 ≤120s）/ promote
   （409=admin_busy|duplicate_name|job_conflict）/ sandbox / sandbox/delete。
   job 状态复用 `/api/admin/daily-jobs/<job_id>`。
5. **前端 `templates/admin.html`** 因子 tab 加「新建因子」折叠子区：NL 描述框 +
   生成代码 → 代码编辑框 + name/category/column/periods 表单（meta 预填）→
   查重+安全检查 / 冒烟测试 / 晋升入库（confirm 二次确认 + job 轮询）+ 沙箱列表
   （删除）。全中文、零新框架。
6. **测试 `tests/test_gui_factor_create.py`（42 条）**：假 http_post LLM 输出、
   安全检查恶意样本、查重命中/不命中/同后缀不误判、冒烟子进程 mock、promote
   pgrep 闸/复制/yaml 追加/回滚（tmp 假 indicators 树）、API 全链路 Flask
   test client。

## Validation Output

```bash
uv run pytest tests/test_gui_factor_create.py -q → 42 passed
uv run pytest tests/ -k gui -q → 270 passed
uv run pytest tests/ -x -q → 1385 passed
```

真实 E2E（2026-08-12，真实 DeepSeek + 真实 DB）：
- `generate_factor_code("VIDYA 可变指数动态平均线，周期 20")` → VIDYAFactor
  （overlap/close，periods [20]），代码含 get_price_series + p=None/list/int 分支。
- 查重（真实 factors schema + config）：无冲突。
- 冒烟：`sandbox/smoke_factor.py --code 600519.SH --days 400 --params '[20]'` →
  ok，400 行，输出列 `vidya_20`，warmup 288 后非全 NaN，exit 0。
- 晋升（真实 GUI server :8123，POST /api/factor-create/promote）→
  `factors/vidya_factor.py` + config 追加（备份 factors.yaml.bak-20260812T030850），
  job_id `20260812T030850074330`：validate 已通过（exit 0），backfill
  （--categories overlap --execute，4 workers）进行中；backfill 前已确认
  plan noop、无 run_factor_admin 在跑，范围严格只有 vidya_20 一列。
- 查重闸实证：先生成过 roc（周期 25），发现 roc 已注册（params [null]），
  同名拒绝规则因此加入（否则会产生重复 roc 类互相覆盖）。

# Coding Handoff (archive: QRE-GUI-STRATEGY-CREATE-P1-001, GUI 策略创建闭环：查重 → 沙箱 → 冒烟 → 确认晋升 → catalog)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting git finalization)

## Implementation Summary

1. **新模块 `gui/strategy_create.py`**（纯函数层，目录均可注入）：
   - `check_strategy_duplicate(name, catalog_dir, sandbox_dir, scan_sandbox)`：扫
     catalog（rglob `*.yaml` 读 experiment.name）+ 沙箱，命中返回中文冲突描述。
   - `save_to_sandbox(yaml_text)`：validate_yaml → 查重 → 落盘
     `outputs/sandbox/strategies/<name>.yaml`。沙箱独立于 catalog，refresh 日更
     只扫 catalog，天然隔离。
   - `list_sandbox()`：名称/文件/mtime/最近冒烟（sidecar `<name>.smoke.json`，
     由 `record_smoke()` 写入）。
   - `promote(name, category)`：类别白名单（CATALOG_CATEGORIES 7 类）→ 复制到
     `strategies/catalog/<category>/` → 删沙箱 YAML（保留 smoke sidecar）。
   - `discard(name)`：删沙箱 YAML + sidecar。
   - 常量：`SMOKE_DEFAULT_CODE="600519.SH"`、`SMOKE_WINDOW_DAYS=180`。
2. **API（`gui/app.py` create_app 内）**：
   - `POST /api/strategies/create` {mode: manual|nl, yaml_text?|description?}：
     nl 走 `compile_nl`；manual 走 validate_yaml + 因子存在性检查（复用
     `nl_compiler._default_column_lookup` + `find_missing_factor_columns`，缺因子
     入 handoff 队列并返回 code=missing_factors，DB 不可用降级 warning）→
     查重（409）→ 存沙箱。
   - `GET /api/strategies/sandbox`：列表 + 类别白名单。
   - `POST /api/strategies/smoke` {name, code?}：`run_backtest(mode="single",
     codes=[600519.SH], 近 180 天, background=True)`，run 记录打
     `sandbox_strategy`/`purpose=smoke` 标记（`_mark_run` 落盘 status.json），
     run_id 写 sidecar。
   - `POST /api/strategies/promote` {name, category}：promote() 后立即触发一次
     全量后台回测（`mode="shared"`、空 codes=全市场、近 2 年窗，对齐 refresh 默认
     window-years=2；refresh 本身是独立 CLI 管线故不复用其调用）。并发槽满时
     降级为 warning（策略随下次日更运行）。
   - `POST /api/strategies/sandbox/delete` {name}：discard。
3. **前端 `templates/index.html`**（编辑器 tab，无新框架）：编辑器操作行加
   "存入沙箱"按钮；"沙箱策略"面板（列表 + 冒烟/晋升(类别下拉)/删除按钮，
   冒烟状态链接到 /runs/<run_id>）。
4. **测试 `tests/test_gui_strategy_create.py`**（23 条）：查重命中/不命中、
   落盘与列出、缺因子分支（假 lookup + 假 enqueue）、promote 白名单/移动/查重拦截、
   API 全链路（Flask test client，run_backtest mock 掉）。

## Validation Output

```bash
uv run pytest tests/test_gui_strategy_create.py -q → 23 passed
uv run pytest tests/ -k gui -q → 228 passed
uv run pytest tests/ -x -q → 见 05_PROGRESS.md / 10_REVIEW_REPORT.md
真实冒烟：见 10_REVIEW_REPORT.md（600519.SH 近 6 个月，GUI 等价链路）
```

# Coding Handoff (archive: QRE-FACTOR-PANEL-E2E-001)

# Coding Handoff

## Task ID

QRE-FACTOR-PANEL-E2E-001 (GUI factor panel end-to-end acceptance: rsi_9 + 3 deep fixes)

## Written By

KIMI_CODE (single agent)

## Status

DONE (committed)

## Implementation Summary

1. **factor_admin.py**: PLAN/SAMPLE_BACKFILL/FULL_BACKFILL commands now pin
   `--baseline-ref HEAD`. Without it, run_factor_admin's default baseline
   (116d7cd) selects ~291 columns — a full-history recompute of everything
   including statistics semantics — instead of only the requested factor.
   Found during the first real panel run (sample stalled 20+ min).
2. **Regression test**: `test_factor_admin_backfill_commands_pin_baseline_head`.
3. **Acceptance strategy** `gui_accept_rsi14_reversal.yaml` (wizard-built):
   rsi_14 < 30 entry / > 70 exit, 8% stop; registered for the 20:30 refresh
   auto-coverage check.
4. **Panel acceptance facts**: duplicate-factor rejection works (rsi_21
   refused with config rollback); rsi_9 created, sample-verified, full
   backfill 5551 stocks / 13,363,067 rows / 0 failures; values sane
   (rsi_9 > rsi_14 in uptrend, all within [0,100]).
5. **Upstream fixes in indicators_tushare** (commit 9ffefbd): disarmed
   _ensure_hypertable auto-compression; CREATE INDEX gated to
   non-TimescaleDB mode (861-chunk lock convoy, two real stalls).

## Validation Output

```bash
uv run pytest -q → 1319+1 passed (baseline regression included)
rsi_9: 13,363,067 rows / 5,544 stocks / latest 2026-07-31 / 0 out-of-range
compression: 0 chunks, 0 policies after cleanup
```

# Coding Handoff (archive: QRE-REFRESH-INCREMENTAL-001)

# Coding Handoff

## Task ID

QRE-REFRESH-INCREMENTAL-001 (refresh 增量合并：小水印差只跑新增交易日并合并进既有结果)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1319 tests green, 7 new; real-DB equivalence PASS; awaiting commit approval)

## Implementation Summary

- **设计**：docs/design/refresh_incremental.md。核心决策——**复用 7 月增量引擎**（`orchestration/incremental.py::run_incremental`，real-DB gate 曾证分段≡全跑字节一致），不新造合并逻辑：
  - **未平仓持仓延续（最大难点）**：由 checkpoint（`incremental_state.py` per-symbol 状态机：持仓数量/入场信息/trailing 锚/待成交订单存*触发日*/现金）解决；continuation 窗口带 warmup（150 天×2）且最早回溯至最早持仓入场日 −7 天，窗口边界无缝续跑；flat symbol 现金由累计 orders 精确重放。
  - **合并**：orders/trades/failed concat+键去重(keep=last)+排序重写；equity 追加写、汇总时去重；buy-hold 锚定原窗口 first_mark_price。
  - **聚合指标**：`_recompute_summary` 每次从拼接后完整台账重算 summary.csv（总收益/超额/胜率），非增量估计。
  - **失效兜底**：config_hash 不匹配 → 自动 bootstrap；水印差 >45 自然日（≈30 交易日）→ 删 state_dir 全窗重建。
- **实现**（scripts/refresh_batch.py）：`--mode incremental|full`（默认 incremental；`--full-window` 保留旧行为）；`--incremental-threshold-days`（默认 45）；`should_full_rebuild()` / `write_incremental_summary_metrics()`（合并后 summary.csv → backtest/summary_metrics.json，供 delta 报告复用）/ `run_incremental_refresh()`（逐策略编排，单策略失败不阻塞）；增量结果存 `outputs/refresh/incremental/<sid>/`，state.json config 记 mode，last_run.json 记每策略 watermark/updated/new_rows/duration。docstring 更新。
- **测试**：tests/test_refresh_incremental.py 7 例（阈值回退/无 checkpoint/损坏 checkpoint、summary_metrics 聚合、编排 mock（小差不重建/大差删目录重建/单策略失败隔离/参数透传）、合并去重+聚合重算契约）；tests/test_refresh.py 三个旧脚本用例 argv 加 `--mode full` 保持原语义。
- 真实 outputs/refresh/state.json 已备份至 /tmp（未改动真实 outputs；验证全部走临时目录）。

## Validation Output

```bash
uv run pytest -q → 1319 passed (基线 1312 + 7 新增)
# 真实等价性（2 策略 × 200 股 × 2 年窗，临时目录）：
#   watermark=2026-07-31，D1=2026-07-17（10 交易日前）
#   tf01a_ma_cross_20_120:  bootstrap(D1) 351 trades → 增量续跑 +3 = 354
#     vs 一次性 bootstrap(D2) 354，trades_match=True
#     mean_total_return diff=3.5e-18，末日权益 max|diff|=4.7e-10
#   mr01a_rsi14_oversold_reversal: 332 + 0 = 332，match=True，
#     mean_return diff=0.0，equity diff=0.0
#   EQUIVALENCE: PASS（差异仅在浮点舍入内）
```

## Known Limitations

- continuation 不回删滚动窗口起点之前的旧台账（long-run 累积）；需要严格滚动窗口语义时用 `--full-window`。
- universe_filter 只影响新入场，既有持仓保留（7 月设计 §4.3 既定语义）。
- GUI 策略详情页的结果提取搜索 `outputs/backtests/**`，不覆盖增量存储 `outputs/refresh/incremental/`（后续可扩展 latest_strategy_result 数据源）。
- 增量模式不写 batch_summary/delta_report（delta 报告仍属 full 模式；增量每策略指标在 last_run.json 与各 state_dir/backtest/summary_metrics.json）。
- 全量 111 策略首次 bootstrap 仍需完整跑一次（之后每日增量为分钟级）；验证只用了 200 股，全量首次运行成本未实测。

---

# Coding Handoff (archive: QRE-ADMIN-STRAT-TAB-001)

## Task ID

QRE-ADMIN-STRAT-TAB-001 (策略状态 tab 四项修改：详情页链接、四列精简、开关按钮、删除连动产物)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1312 tests green, 13 new; awaiting commit approval)

## Implementation Summary

1. **策略详情页**：`/admin/strategy/<sid>`（新模板 strategy_status_detail.html）= catalog YAML 简介（`strategy_admin.strategy_catalog_info`：头部注释块 + experiment.name + 出入场条件 + 持仓天数）+ 最近结果指标卡 + 产物下载（`/api/admin/strategy/<sid>/artifact/<rel>`，双白名单：产物根在 backtests 内 + 目标在产物根内）。
2. **四列精简**：`refresh_registry.latest_strategy_result()`（`outputs/backtests/**/<sid>/backtest/strategy_performance.json` 取 mtime 最新，300s 缓存，excess 缺失时 benchmark_* 兜底）；refresh_overview 每策略输出 date_start/end、traded/total symbols、excess_return、max_drawdown，无结果 None（前端"—"）。旧列（注册/状态/变化/均值/Δ）删除。
3. **开关按钮（registry v2）**：`{"include": [...], "stopped": [...]}`，兼容纯数组与线上旧格式 `{"strategies": [...]}`（视为 include、stopped=[]）。include 空=全量模式（默认全开启）；`set_strategy_stopped` 只改文件不触发运行（提示"将于下个定时任务生效"）。`refresh_batch.load_registry_ids` 返回 `{ids, stopped}`：ids=include−空判断，主流程 discover 后过滤 stopped（--strategies 优先且不过滤）。按钮绿=开启/灰=停止；横幅文案更新（全量=默认全开启停止除外 / 注册=只跑注册未停止）。
4. **删除连动产物**：`strategy_admin.delete_strategy` 改为删 catalog YAML + 移出注册表（include+stopped 双清）+ 删除 `outputs/backtests/*/<sid>/`（白名单：resolve 后 parent.parent==backtests 根，更深嵌套不动）+ 清结果缓存，返回 deleted_files/deleted_dirs/errors。不做运行中检查（GUI 弹窗文案含"不可恢复"）。
5. 测试：`tests/test_gui_admin_strat_tab.py` 13 个（结果提取最新/benchmark 兜底/缓存/无结果、四列数据、v2 stopped 两模式、旧格式兼容、catalog 简介、删除连动白名单、toggle/详情/artifact 路由含越界）；p3b/manage 旧测试同步 v2 语义。

## Validation Output

```bash
uv run pytest -q → 1312 passed (基线 1299 + 13 新增)
# 真实只读冒烟：latest_strategy_result(mr01a) 正确选中 full_history_overnight/0e875c6a10da
# （benchmark_excess 兜底生效）；产物 25 文件；registry v2 读取线上 {"strategies": []} 正常；
# 详情页 200 含指标卡；artifact 下载 200 (5390B) → SMOKE OK
```

## Known Limitations

- 详情页数据源为"最新 mtime 的 strategy_performance.json"，refresh 滚动窗口（2 年）与全历史批次区间不同，指标卡不标注来源批次类型（source_file 可见）。
- stopped 过滤在 `discover_strategies` 之后按文件名 stem 排除；--strategies 显式指定时不应用 stopped（设计：显式优先）。
- 删除连动只清 `<backtests>/<batch>/<sid>` 一级目录；refresh delta 报告（跨策略合订本）中的该策略行不删（下次 refresh 自动刷新）。
- 后台 refresh 运行中删除策略可能出现该策略目录被重建（运行完成时）——弹窗已提示风险，未加锁。

---

# Coding Handoff (archive: QRE-ADMIN-MANAGE-001)

## Task ID

QRE-ADMIN-MANAGE-001 (管理台 Tab4/Tab5：策略删除、因子补全/删列、维护区清理)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1299 tests green, 15 new; awaiting commit approval)

## Implementation Summary

1. **恢复策略管理**：admin.html 去掉全部 .p3c-hidden（注册/移出、新建策略链接、前往新因子申请）；每行新增"删除策略"（prompt 输入策略 id 二次确认）→ `gui/strategy_admin.delete_strategy`：删 `strategies/catalog/<id>.yaml` + 自动 `unregister_strategy`；outputs 历史产物不删，返回 artifact_dirs 仅提示。
2. **因子补全**：因子状态 tab 每表"补全此表"（confirm）→ POST `/api/admin/factor-backfill` → `daily_jobs.start_script_job`（新增通用任务入口，与管线锁同一 `_active_jobs`；lock_key=indicators 与日更共用）跑 `run_factor_admin.py backfill --baseline-ref HEAD --categories <类别> --max-workers 4 --execute`；黄列文案注明补全只对配置内列生效。
3. **因子删列**：indicators 新官方脚本 `scripts/drop_factor_columns.py`（dry-run 默认；安全检查：纳管表名正则+表存在、禁删 ts_code/trade_date、列必须在库存在、在当前 config 展开集内（项目自身 factor 类纯展开）拒绝除非 --force 并告警）；GUI 黄列 chip 带 ×（绿列无按钮）→ prompt 输入列名确认 → `/api/admin/factor-columns/drop` → 同锁后台任务。
4. **Tab 5 维护区**：`gui/maintenance.py` — `list_batches`（du 体积/mtime/策略数/受保护标记，300s 缓存）+ `delete_batches`（名称正则 + resolve 后 parent==root 白名单 + PROTECTED={refresh, incremental} 拒删 + 删后清相关缓存）；UI 勾选 + 显示合计释放体积 + 输入 DELETE 二次确认。
5. 测试 `tests/test_gui_admin_manage.py` 15 个：策略删除+注册表联动+产物保留提示、通用任务与管线锁互斥、drop 脚本保护列/非法表拒绝（真实 subprocess，免 DB 路径）、批次列表保护标记、白名单删除（受保护/越界/注入名/符号链接逃逸拒绝）、6 个路由用例（命令构造断言、409、400）、页面 MANAGE UI 断言。旧 query-only 页面断言同步更新。

## Validation Output

```bash
uv run pytest -q → 1299 passed (基线 1284 + 15 新增)
# drop 脚本真实冒烟（indicators uv 环境，全程零写入）：
#   --columns rsi_14（配置列）→ 拒绝「在日更配置展开集中，拒绝删除」exit 2
#   --columns ts_code → 拒绝「关键列不可删除」exit 2
#   --table public.stock_daily → 拒绝「非法因子表名」exit 2
#   --columns rsi_14 --force → WARNING + DRY-RUN 打印 ALTER TABLE，exit 0，未执行
# 注：当前全库已无黄列（上游近期扩充了 config），黄列删除按钮暂无可作用对象，语义保留。
```

## Known Limitations

- 批次删除为路由内同步 rmtree（GB 级几秒~十几秒）；未走后台任务（rmtree 非脚本调用），大目录删除时请求会阻塞到完成。
- 补全/删列任务与日更 indicators 管线共锁：日更运行中按钮会 409（设计行为）。
- 因子补全按表类别整体 backfill（官方脚本粒度），无法只补单表中的部分列。
- 删列后 GUI 对账缓存最长 300s 才刷新（pollFsJob 完成时前端会主动重拉，已缓解）。

---

# Coding Handoff (archive: QRE-HAZARD-FIX-001)

## Task ID

QRE-HAZARD-FIX-001 (三隐患修复：注册表语义告警 + overview 冷载提速 + hardened 安装脚本)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1284 tests green, 2 new; awaiting commit approval)

## Implementation Summary

1. **注册表语义告警（隐患 #5）**：`refresh_registry.refresh_overview` 新增 `mode` 字段
   （`full_catalog` 空注册表 / `registry` 仅注册策略）；admin.html 策略状态 tab 顶部显眼横幅
   （`.mode-banner` 黄底）：全量模式显示"当前为全量模式（N 策略）；注册任意策略后将切换为
   仅注册策略模式"；注册模式显示蓝底对应文案。新增 2 测试（mode 两态 + 页面横幅断言）。
2. **overview 冷载提速（隐患 #4）**：瓶颈实测 `COUNT(DISTINCT ts_code)` on 858 chunk =
   10.34s（占首载 9.98s 的绝大部分）。改为 `pg_stats.n_distinct` 估算（0.003s；负值按占比
   × reltuples 处理），键名改 `estimated_symbol_count`，前端标签"估算股票数"，与 reltuples
   估算语义对齐；300s 缓存 + single-flight 不变。FakeStore 同步改 pg_stats 分支。
3. **安装脚本（隐患 #1 准备）**：`scripts/install_timers_hardened.sh`（bash -n 通过，未执行）：
   4 步打印（cp → daemon-reload → enable --now → list-timers 确认），全用 sudo；末尾打印
   quant_ts/indicators 两项目 hardened unit 的手动安装指引（不代装；提示先停旧 unit 防重复触发）。

## Validation Output

```bash
uv run pytest -q → 1284 passed (基线 1282 + 2 新增)
bash -n scripts/install_timers_hardened.sh → OK
# overview 冷载实测（time curl，临时 8899 端口已关停）：
#   改前首载 9.98s（COUNT DISTINCT=10.34s 单独计时确认）
#   改后首载 2.19s（剩余主要为 du -sb 4.18GB 遍历 + 10 表 MAX(trade_date)）
#   二载 0.0015s（缓存命中）
# 估算精度：pg_stats n_distinct=5209 vs 精确 5549（-6.1%，标"估算"可接受）
```

## Known Limitations

- 冷载剩余 ~2.2s 主要是 du 遍历产物目录；如需再降可放宽 du 缓存粒度或后台预热，未做。
- n_distinct 依赖 ANALYZE 统计，新大批入库后估算会滞后到下次 analyze（Autovacuum 正常周期内）。
- install 脚本未执行（按任务要求）；执行后 qre-refresh.timer 才生效。

---

# Coding Handoff (archive: QRE-ADMIN-DASH-QUERY-001)

## Task ID

QRE-ADMIN-DASH-QUERY-001 (管理台 dashboard 查询台化：加载体验 + overview 提速 + 新建/入库 UI 暂缓)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1281 tests green, 3 new; awaiting commit approval)

## Implementation Summary

- **前端加载体验（admin.html）**：新增 `fetchWithTimeout`（AbortController 30s）+ `cardError`（中文错误+重试按钮）；overview/timers/factor-status/refresh 四个 fetch 本已独立，现全部带 30s 超时与 per-card catch（超时/失败只影响该卡片，其余卡片与全部按钮不受影响）；页面骨架静态 HTML 立即渲染，按钮从不等待数据。
- **后端提速（admin.py）**：`CACHE_TTL_SECONDS` 60→300（overview_daily 的 COUNT(DISTINCT ts_code)/858-chunk watermark、overview_factors、du -sb 全部经同一 `_cached` 路径，自动对齐 300s）；`_cached` 升级 single-flight（per-key lock + 双重检查，并发同 key 共享一次计算）。
- **新建/入库 UI 暂缓（代码保留）**：新增 `.p3c-hidden{display:none!important}` + TODO-P3c-restore 注释——策略状态 tab 的注册/移出按钮（JS 生成，包 hidden span）、表头"新建策略（因子向导）"链接、因子状态红区的"前往新因子申请"链接；回测工作台首页（/）的因子向导/NL 通道不动（属回测区）；日更中心"立即运行"保留（触发已完善脚本）。
- **查询体验**：因子状态 tab 加 `fs-search`（按表名/列名客户端即时过滤 .fs-table）；策略状态 tab 加 `ob-search`（按策略 id 过滤 .ob-row）；汇总计数不变。
- 测试：TTL=300 断言、single-flight 并发共享（4 线程 1 次计算）、页面查询台模式断言（搜索框存在、p3c-hidden ≥2、TODO 标记、红区链接仅在隐藏 span 内）。

## Validation Output

```bash
uv run pytest -q → 1281 passed (基线 1278 + 3 新增)
# time curl 实测（临时 8899 端口，已关停）：
#   GET /admin                 0.004s（骨架）
#   /api/admin/overview 首载   9.98s（冷缓存：COUNT DISTINCT + du + 858 chunk）
#   /api/admin/overview 二/三载 0.0009s / 0.0010s（300s 缓存命中）
#   /api/admin/factor-status   1.70s → 0.02s；timers 0.017s；refresh 0.004s
```

## Known Limitations

- overview 冷缓存首载仍 ~10s（COUNT DISTINCT 858 chunk 为真实成本；single-flight 保证并发只算一次，前端卡片独立不阻塞其它区）。若要首载也快，需把 distinct count 换估算（pg_stats），留待用户拍板。
- 隐藏的注册/新因子/新策略功能的路由与后端逻辑全部保留可用（仅 UI 隐藏），P3c 恢复只需去掉 p3c-hidden。
- 搜索为客户端过滤（不重新请求），346 列 chip 全部渲染在折叠 details 内，未做虚拟化。

---

# Coding Handoff (archive: QRE-ADMIN-STATUS-REFocus-001)

## Task ID

QRE-ADMIN-STATUS-REFocus-001 (管理台定位修正：撤数据查询，因子状态三方对账，策略状态重组)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1278 tests green; awaiting commit approval)

## Implementation Summary

- **撤 Tab 3 数据查询**：删除 `/api/admin/query/daily`、`/api/admin/query/factor` 路由；`admin.py` 删除 `query_daily`/`query_factor`/`rows_to_csv`/`_clamp_limit`/`MAX_QUERY_LIMIT`（仅服务于此）；admin.html 查询 tab/JS 全撤；相关 11 个测试删除/改写（含路由 404 断言）。
- **新 Tab 因子状态**（`admin.factor_status` + GET `/api/admin/factor-status`）：三方对账仅状态——a) 库中列（纳管表 get_table_columns 剔除 ts_code/trade_date）；b) 日更应存在列；c) watermark。标注 green/yellow/red + 汇总计数 + 红列链向新因子申请；未纳管孤儿表保持信息段。
- **日更列展开方式（选择与理由）**：选用 subprocess 调 indicators_tushare 自身 uv 环境跑**纯展开脚本**（`FactorRegistry.discover` + `load_factor_specs` + `resolve_specs` + 每个 factor 实例 `preview_columns(params)`），不用 `run_factor_admin.py plan`/`collect_expected_columns`——后者经 `load_tasks` 会写 meta schema（ensure_supporting_schemas/register_*），违反只读定位；纯展开不实例化 DBManager、零 DB 接触，且用项目自己的 factor 类做输出列命名（权威，含 macdh/macds 等多输出与参数后缀）。实测 1.4s 展开 10 表 206 列 0 失败；300s 缓存。失败降级 `_config_level_tasks`（直接解析 yaml 为 指标名+类别+价格列+参数，标注"配置级"）。
- **Tab 4 重组为"策略状态"**：tab 改名，内容沿用（catalog × 注册表 × delta + 注册/移出 + 因子向导链接）。
- 测试：新增 4 个对账用例（展开成功/失败、三路状态标注含汇总、降级配置级）+ 3 个路由用例（查询 404、factor-status 200/503）；p3b 页面断言随改名更新。

## Validation Output

```bash
uv run pytest -q → 1278 passed (1282 − 11 查询用例 + 7 新用例)
# 真实只读冒烟（实际执行）：expected_available=True；summary green=206 yellow=138 red=0；
# 10 纳管表逐表计数合理（green 合计恰等于配置展开 206 列，0 缺列）；
# unmanaged=[stock_daily_vortex_close] → SMOKE OK
```

## Known Limitations

- 138 个 yellow（在库不在日更配置）为历史配置删减的真实状态，仅展示不处理。
- 配置展开每次缓存 300s；factors.yaml 变更后最长 5 分钟才在对账中反映（P1.5 新因子链本身写 yaml 后sample 回填，不经过此缓存路径，不受影响）。
- 黄列没有"重新纳入日更"按钮（属 P3c/配置编辑范畴）；红列仅链接到向导新因子申请。
- 策略 Tab 的每策略信息仍依赖最近一次 delta_report（refresh 机制所限）。

---

# Coding Handoff (archive: QRE-ADMIN-CONSOLE-P3B-001)

## Task ID

QRE-ADMIN-CONSOLE-P3B-001 (管理台 P3b：日更手动触发 + 接入中心/refresh 注册表)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1282 tests green, 18 new; awaiting commit approval)

## Implementation Summary

- **refresh 注册机制（选择与理由）**：refresh 原生 = 全量扫描 catalog + `--strategies` 过滤，无注册表、无 per-strategy watermark（state 仅全局 last_data_date）。最小改动方案：新增注册表文件 `outputs/refresh/registry.json`，`scripts/refresh_batch.py` 增加 `--registry`（默认该路径），文件存在且非空时自动作为策略过滤（`--strategies` 显式给定优先；文件缺失/空/损坏 → 全量扫描，与现状逐字节一致）。理由：复用既有 `discover_strategies` 过滤通道，不改 systemd unit（timer 未安装，用户安装后自动生效），不引入第二套状态。
- 新模块 `gui/daily_jobs.py`：三管线命令表（quant-ts `sync_manager.py --mode daily`、indicators `run_daily.py --max-workers 4`、qre-refresh `scripts/refresh_batch.py --jobs 4`；uv=`/home/van/.local/bin/uv`，cwd 各项目根）；每管线独立锁（重入 RuntimeError→409）；后台线程 subprocess，落盘 `outputs/gui-console/daily-jobs/<job_id>/{status.json,output.log}`；`journalctl_tail`（读不需 root，失败回退项目 logs 目录最新 .log tail）。
- 新模块 `gui/refresh_registry.py`：注册表 load/save/register/unregister（去重排序）、`list_catalog_strategies`、`refresh_overview`（state + 注册表 + 最新 delta_report.json 每策略 status/transition/收益/Δ）。
- `gui/app.py`：POST `/api/admin/daily-jobs/<pipeline>`（404/409）、GET `/api/admin/daily-jobs/<job_id>`、GET `/api/admin/daily-logs/<pipeline>`、GET `/api/admin/refresh`、POST `/api/admin/refresh/register|unregister`（catalog 校验 400）。
- `templates/admin.html`：Tab 2 改"日更中心"，每卡片"立即运行"（confirm 弹窗）+"最近日志"按钮 + 任务区 3s 轮询日志 tail；新 Tab 4"接入中心"：refresh state/delta 摘要 + 全 catalog 注册表（加入/移出按钮）+ 因子向导入口链接。
- 测试 `tests/test_gui_admin_p3b.py` 18 个：registry loader（缺/空/坏→None）、注册读写去重、catalog 列举、refresh_overview 组装、daily job 命令构造/失败/管线锁/未知管线、journalctl 正常/回退/无回退、路由 200/400/404/409 与注册全流程。另：test_gui_admin 旧断言随 tab 改名"日更中心"更新；test_gui_factor_wizard 锁测试 sleep 0.3→0.6 消抖（全量并发下曾偶发）。

## Validation Output

```bash
uv run pytest -q → 1282 passed (基线 1264 + 18 新增)
```

## Known Limitations

- 未真实触发三条管线脚本（按任务要求 mock subprocess）；首次手动触发建议盯 output.log。
- refresh 无 per-strategy watermark（机制本身是全量滚动窗口重跑）；Tab4 的"每策略"信息来自最近一次 delta_report，首次运行前为空。
- 注册表生效后，移出注册表的策略不再被日更覆盖（其历史批次仍在 outputs）；这是机制语义无误但需用户知晓。
- journalctl 回退仅覆盖 quant-ts/indicators 的 logs 目录；qre-refresh 无项目日志目录（timer 未安装）。
- Tab 5 维护区未做（P3c）。

---

# Coding Handoff (archive: QRE-ADMIN-FACTOR-HEALTH-FIX-001)

## Task ID

QRE-ADMIN-FACTOR-HEALTH-FIX-001 (管理台因子健康灯误报修复：纳管表机制)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1264 tests green, 26 admin 例；awaiting commit approval)

## Implementation Summary

- 问题：`factors.stock_daily_vortex_close`（0 行孤儿表，历史 admin 遗留）被报滞后 → 健康灯红色误报。真实链路：indicators_tushare 只写 10 张规范类别表，vortex 数据在 trend_close 内且新鲜（13,460,834 行至 2026-07-27）。
- `gui/admin.py`：新增 `managed_factor_tables()`（读 indicators_tushare config/factors.yaml 的 category+column 组合推导 `stock_daily_<category>_<column>`，已实测推出恰好 10 张表；repo 不可用回退 `MANAGED_FACTOR_TABLES_FALLBACK` 硬编码 10 表）；`overview_factors` 拆分为 `tables`（纳管，含 watermark/滞后判定；纳管但 schema 缺失的也如实列出 watermark=None）与 `unmanaged_tables`（孤儿表信息段：表名+估算行数，不参与健康灯）；`lagging_tables` 只含纳管表。
- `templates/admin.html`：因子卡片增"纳管表 N 张"计数与"未纳管表（不参与健康灯）"信息行。
- 测试：FakeStore 支持按表 watermark；新增 4 例（config 推导、repo 缺失回退、孤儿进未纳管段、孤儿不影响健康灯）；既有 overview/路由用例改为显式 monkeypatch 纳管清单（环境无关）。

## Validation Output

```bash
uv run pytest -q → 1264 passed (基线 1260 + 4 新增)
# 真实只读冒烟：managed=10，unmanaged=[stock_daily_vortex_close(-1 估算)]，
# lagging=[]，health=green「全部对齐 2026-07-27」→ SMOKE OK
```

---

# Coding Handoff (archive: QRE-ADMIN-CONSOLE-P3A-001)

## Task ID

QRE-ADMIN-CONSOLE-P3A-001 (统一管理台 P3a：只读总览 + 日更状态 + 数据查询)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1260 tests green, 22 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/admin.py`（纯只读：SELECT + systemctl show + du）：
  - `overview_daily`：pg_class.reltuples 估算行数、MAX(trade_date)、COUNT(DISTINCT ts_code)、最近 15 个 distinct trade_date（60s TTL 缓存）。
  - `overview_factors`：11 表估算行数 + 各表 watermark + 相对日线 watermark 的滞后表清单（缓存）。
  - `overview_backtests`：批次数、策略产物目录数、du -sb 占用（outputs 符号链接先 resolve——冒烟发现 du 只量链接本身 21B，已修为 4.18GB）。
  - `parse_systemctl_show`/`timer_status`：逐管线查 timer+service（NextElapse/ActiveEnter/ExecMainStatus/Result/ActiveState/UnitFileState/LoadState）；unit 不存在 → not_installed，qre-refresh 附安装命令文本。
  - `health_status`：全对齐 green、最小滞后 ≤3 天 yellow、否则/缺数据 red。
  - `query_daily`/`query_factor`：参数化 SQL、limit 钳制 ≤1000；因子表名走 `parse_factor_table_name` 正则 + table_exists，列名走 get_table_columns 白名单（实时枚举防注入）；`rows_to_csv`。
- `gui/app.py`：GET `/admin`、`/api/admin/overview`（三域+健康灯，DB 挂 503）、`/api/admin/timers`、`/api/admin/query/daily`、`/api/admin/query/factor`（JSON + ?format=csv 下载，400 校验）。
- `templates/admin.html`（新）：三 tab 中文页面；总览三卡片+健康灯+刷新；日更三管线卡片（qre-refresh 显示未安装+安装命令文本，无按钮）；查询双表单（因子下拉 optgroup 复用 /api/factors）+ 分页 + CSV 链接。`base.html` 导航加"管理台"。`style.css` 追加卡片/健康灯样式。UI 无任何未实现的 P3b/P3c 按钮。
- 测试 `tests/test_gui_admin.py` 22 个：白名单拒非法表/列名（含注入串）、limit 钳制、CSV 格式、参数化断言（值不进 SQL 文本）、systemctl 解析（正常/未安装）、health 三色、overview（fake store）、du 缓存命中、路由 200/400/503。不连真 DB。

## Validation Output

```bash
uv run pytest -q → 1260 passed (P1.5 基线 1238 + 22 新增)
# 真实 DB 只读冒烟（实际执行）：
# daily: est_rows=13,296,204 watermark=2026-07-27 symbols=5,549 recent=[07-27,07-24,...]
# factors: 11 tables, lagging=[factors.stock_daily_vortex_close]
# backtests: batches=5 strategy_dirs=6 size=4.18GB latest=refresh
# health: red（vortex 表无数据 — 真实状态）
# timers: quant-ts installed(active, next 07-28 16:30, last exit=1 exit-code)；
#         indicators installed(active, next 16:40, success)；qre-refresh not_installed + hint
# query_daily/factor 000001.SZ 2026-07: total=19, 首行数值正确 → SMOKE OK
```

## Known Limitations (P3b/P3c)

- 手动触发日更、接入中心（refresh 注册）、维护区（产物清理）未做，UI 无对应按钮。
- quant-ts service 上次 exit=1（exit-code）为真实状态，仅展示不处理。
- vortex 表空导致健康灯红 —— 真实数据状态，留待上游补齐。
- COUNT(DISTINCT ts_code) 为精确 count（858 chunk，~2s 级），已加 60s 缓存兜底。
- timer 日志 tail 未做（P3b 随手动触发一起）。

---

# Coding Handoff (archive: QRE-GUI-FACTOR-WIZARD-001)

## Task ID

QRE-GUI-FACTOR-WIZARD-001 (GUI 因子前置三步向导 + indicators_tushare 新因子申请联动)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1238 tests green, 28 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/factor_wizard.py`：`parse_factor_table_name`（命名规律 `stock_daily_<category>_<price_col>` 已实库确认 11 表）+ `build_factor_groups`（类别中文分组 + 行情组，剔除 ts_code/trade_date）+ `load_factor_tables_columns`（只读 information_schema 实时枚举）+ 条件/YAML 纯函数 `build_condition`/`combine_conditions`/`build_strategy_yaml`（比较+布尔，生成后过 validate_yaml）。
- 新模块 `gui/factor_admin.py`：`indicators_repo`（env `QRE_INDICATORS_REPO`，默认 `<workspace>/indicators_tushare`，已验证解析正确）；`read_indicators`/`parse_periods`（逗号正整数校验）；`append_factor_entry`（.bak-时间戳备份 + 文本追加，category 取自同名现有 entry）+ `rollback_config`；任务状态机 `start_factor_job`（单任务锁 → 备份追加 → 后台线程 validate → plan → sample backfill --execute → awaiting_execute_confirmation；失败即停并回滚 yaml）+ `confirm_execute`（人工确认 → 全量 backfill --execute）；状态/日志落盘 `outputs/gui-console/factor-admin/<job_id>/{status.json,steps.log}`；step_runner 可注入。
- `gui/app.py`：GET `/api/factors`（DB 挂 503 中文）、GET `/api/factor-admin/indicators`（配置缺失 503）、POST `/api/factor-admin/request`（400 校验/409 锁）、GET `/api/factor-admin/jobs/<id>`、POST `/api/factor-admin/<id>/execute`（状态闸 409）。
- `templates/index.html`：新首屏"因子向导" tab（YAML 编辑器改标"高级"）：Step1 分组 checkbox + factor_fields 预览；Step2 四段式条件行（左下拉/运算符/右类型切换/右操作数）+ 出入场组 AND/OR + 持仓/stops + 实时 YAML 预览 + "校验并填入编辑器"（安全闸不变）；Step3 指标/价格下拉 + 周期校验 + 任务卡片（3s 轮询、日志 tail、awaiting 时显示"确认全量回填"按钮）；NL 缺因子错误加"前往新因子申请"链接（预填指标名/周期猜测）。`style.css` 追加向导样式。
- 测试 `tests/test_gui_factor_wizard.py` 28 个：表名解析、分组/标签/剔列、条件各运算符与右值类型、AND/OR、YAML 生成（出入场/stops/校验失败）、periods 校验、yaml 追加/备份/回滚（临时目录副本，未碰真实 repo）、任务状态机成功链+确认执行、失败回滚、锁冲突、错误状态确认、路由 200/400/404/409/503。

## Validation Output

```bash
uv run pytest -q → 1238 passed (P2 基线 1210 + 28 新增)
# 真实环境只读冒烟：load_factor_tables_columns() → 9 因子组 346 列 + 行情组 7；
# read_indicators(真实 repo) → 69 指标名 / 3 价格列。SMOKE OK
```

## Known Limitations

- 全量回填链路未真实执行（按任务要求 mock subprocess）；首次真实跑建议先小样本观察 steps.log。
- factors.yaml 追加为文本块（不保注释往返，但不动既有内容；pyyaml 可正常解析，已验证）。
- Step2 仅比较+布尔；算术组合（如 close/ma-1）留 P3。跨周期（上穿/下穿）同 P2 限制。
- params 型指标（如 kama [10,2,30]）暂只支持 periods 输入；params 申请留待后续。
- 向导 alias 冲突时前端加 `_2` 后缀；极长列名列表（346 列）在折叠 details 内渲染，未做搜索过滤。

---

# Coding Handoff (archive: QRE-GUI-WORKBENCH-P2-001)

## Task ID

QRE-GUI-WORKBENCH-P2-001 (GUI 回测工作台 P2：自然语言 → 策略 YAML 编译器，通道 C)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1210 tests green, 16 new; awaiting commit approval)

## Implementation Summary

- 新模块 `gui/nl_compiler.py`：配置全走 env（`QRE_NL_LLM_BASE_URL/API_KEY/MODEL`，OpenAI 兼容 chat completions，stdlib urllib，60s 超时，无新增依赖）；`build_system_prompt` 注入真实 DSL 说明（StrategySpec 字段 + 信号表达式安全子集，crosses_above 按 compiler 现状降级为当周期比较并如实告知模型）+ `_INDICATOR_CATALOG` 因子目录 + 2 个精简 few-shot（取自 catalog mr01a 与 GUI 默认 bollinger）；`strip_yaml_fence` 剥围栏 → 复用 `engine.validate_yaml` → 复用 `factor_request_queue`（`find_missing_factor_columns`/`build_requests_for_strategy`/`upsert_requests`）做因子存在性检查，缺因子写队列并返回中文"已搁置"；DB 不可用时跳过检查并带 warning。返回 `{"ok", "yaml"|"error"+code+草稿}`。安全闸：编译结果只填编辑器，前端无任何自动执行路径。
- `gui/app.py`：POST `/api/nl_compile`（空描述 400，未配置 503，其余 200）。
- `templates/index.html`：编辑器页顶部"自然语言描述策略"文本框 + "编译为 YAML"按钮 + 状态区；成功填入 YAML 编辑器并提示"请检查确认后再提交回测"，失败显示中文错误与可编辑草稿；`static/style.css` 追加 `.nl-panel`。
- 测试 `tests/test_gui_nl_compiler.py` 16 个：配置缺失/完整、prompt 内容、围栏剥离、正常往返（含围栏）、LLM HTTP 异常、非法 YAML 回传草稿、非 YAML 输出、缺因子入队（校验队列文件内容）、DB 不可用跳过检查、路由 400/503/200（urlopen 全 mock）、首页含通道 C UI。

## Validation Output

```bash
uv run pytest -q → 1210 passed (P1 基线 1194 + 16 新增)
```

## Known Limitations

- 因子目录注入为指标目录（名称:类别）+ 命名约定，非全量列清单（控制 token）；模型可能生成不存在的列名 → 由因子存在性检查兜底（需 DB 可用）。
- 无 DB 时跳过因子检查（带 warning），缺因子要待提交回测时才暴露。
- "上穿/下穿"语义降级为当日比较（与现有 compiler 一致），非真正的穿越事件检测。
- 未对真实 LLM 做端到端验证（无配置凭据）；提示词质量需真实环境调优。

---

# Coding Handoff (archive: QRE-GUI-WORKBENCH-P1-001)

## Task ID

QRE-GUI-WORKBENCH-P1-001 (GUI 回测工作台 P1：参数表单 + 异步限流 + 出口强化 + run 对比)

## Written By

KIMI_CODE (single agent)

## Status

DONE (1194 tests green, 22 new; awaiting commit approval)

## Implementation Summary

- `gui/engine.py`：`run_backtest` 扩展签名（profile_overrides / engine_impl / stop_loss/take_profit/trailing_stop / precheck / background，全部带向后兼容默认值）；`background=True` 时 daemon 线程执行、立即返回 status=running，结束回写 status.json（含 artifacts）；模块级锁 + 计数实现全局 2 并发槽位（`try_acquire_run_slot`/`release_run_slot`）；`apply_precheck` 截断前 20 只 × 近 180 天；`build_market_profile` 用 dataclasses.replace 覆盖 AShareMarketProfile 成本字段；`_execute_engine` batch/shared 传入 stops 与 engine_impl；codes 为空 → ts_codes/symbols=None 走全市场。新增 `extract_run_summary`（rglob 找 strategy_performance.json，回退解析 stdout key=value，含键别名映射）、`compare_run_summaries`（diff=B-A）、`equity_curve_svg`（inline SVG 折线，无 JS 依赖）、`SUMMARY_METRIC_FIELDS`（中文标签+百分比标记）。
- `gui/app.py`：`/api/run` 接收新表单字段；all_market 校验（single 模式拒绝）；非 cli 执行先取槽位，满了返回 409"已有 2 个回测在运行，请稍后再提交"；新增 `/compare?a=&b=` 页面路由；run_detail 传入摘要行 + 权益 SVG；注册 `fmtval` Jinja 过滤器（两位小数/百分比）。
- 模板：`index.html` 参数面板中文化全表单（标的/区间快捷键/摩擦/规则/引擎/预检默认勾选），提交后跳转提示；`run_detail.html` 预检横幅 + "放大到完整范围"按钮（用 request.json 的 full_params 重提）、摘要卡、artifact 按 xlsx/csv/json/其他分组、权益 SVG、running 时 3 秒 meta refresh；`runs.html` 对比复选框（限选 2 个）+ running 自动刷新；新增 `compare.html`（并排表 + 差异列红绿着色）；`base.html` 加 head block；`style.css` 追加 P1 样式。
- CLI executor 路径未动。
- 测试：`tests/test_gui_workbench.py` 22 个新用例（成本覆盖、预检截断、槽位限流、409、预检 full_params 记录、参数透传、摘要提取两路、对比差值、SVG、页面路由）；`tests/test_gui_app.py::test_api_run_success` 适配异步语义（先 running 后轮询 completed）。

## Validation Output

```bash
uv run pytest -q → 1194 passed (基线 1172 + 22 新增)
```

## Known Limitations (留给 P2/P3)

- 预检仅截断代码清单与区间，全市场预检仍是全 universe 拉数据（区间截断控制体量）。
- run 对比为摘要指标级；无曲线叠加图（P3）。
- 无任务取消按钮；NL→YAML 编译器属 P2。
- 全市场模式依赖 assembler ts_codes=None 全量加载，内存风险由 2 并发限流 + 预检缓解。

---

# Coding Handoff (archive: QRE-FULLHISTORY-BATCH-001)

## Task ID

QRE-FULLHISTORY-BATCH-001 (111-strategy full-history overnight batch)

## Written By

KIMI_CODE (single agent)

## Status

DONE (111/111 OK; docs synced; awaiting commit approval)

## Implementation Summary

- Ran `scripts/run_full_history_overnight.sh` twice (agent-launched): batch `7a7091245d87` 22 ok / 89 error (281min), then after DB fix resume batch `0e875c6a10da` 89/89 ok (1381min). Range 2010-01-04→2026-07-27, 5,547 symbols.
- Root cause of 89 errors: TimescaleDB catalog empty (all hypertable registrations lost), orphan chunks under inheritance (stock_daily: 858). Plan-time locks × jobs 4 exhausted lock table (64×100). Fix: user ran `ALTER SYSTEM SET max_locks_per_transaction = 512` + postgres restart. Timescale re-registration still open.
- Aggregated `outputs/backtests/full_history_overnight/aggregate_summary.csv` (111 rows). Headline: mean strategy_total_return -3.11% vs buy-hold +93.58%; 0/111 beat buy-hold; mean benchmark excess -36.31%; mean DD -48.24%; win rate 43.52%; best tf01a +2.17%, worst pt03a -51.37%. Per-symbol excess columns present for M10.4 clustering.

# Coding Handoff (archive: QRE-OVERNIGHT-FULLHISTORY-PREP-001)

## Written By

KIMI_CODE (single agent)

## Status

DONE (awaiting commit approval)

## Implementation Summary

1. `scripts/run_full_history_overnight.sh`: manual overnight full-history batch — all 111 catalog strategies, `2010-01-04` → run day, vectorized engine, `--jobs 4 --symbol-chunk-size 400 --compact --workbook --apply-stops --universe-filter --metadata-columns board industry_group market_cap_bucket liquidity_bucket --benchmark-table reference.index_daily --benchmark-code 000300.SH --skip-preflight --skip-eval --resume`, output `outputs/backtests/full_history_overnight`, tee log `outputs/backtests/full_history_overnight_<ts>.log`. Usage: `bash scripts/run_full_history_overnight.sh`.
2. Outputs cleanup: `~/qre-outputs/backtests/` 19G → 2.9G. Deleted `full_batch_106` (15G, superseded by quick_batch_106), `profile_baseline`, `full_history_check2`, hash dirs `199494f22100 1de849b37935 47b7a9906d90 b87003a71839 dd5b0e5037d4`. Archived `full_batch_106/61e67b53b644/batch_summary.json` → `~/qre-outputs/_archive/full_batch_106_summaries/`. Kept: `quick_batch_106`, `full_history_cn`, `blank_check`, `refresh`.
3. `.venv-ml` via `uv venv` (host lacks python3.12-venv/ensurepip) + scikit-learn/pandas/numpy; `.gitignore` += `.venv-ml/`; README Quick Start += overnight script line.

## Validation Output

```bash
bash -n scripts/run_full_history_overnight.sh → OK
du -sh ~/qre-outputs/backtests/ → 2.9G (was 19G)
.venv-ml python -c "import sklearn" → (see 05_PROGRESS for recorded versions)
```

# Coding Handoff (archive: QRE-REPORT-BENCHMARK-001)

## Task ID

QRE-REPORT-BENCHMARK-001 (report blank columns + benchmark data/wiring)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting docs sync and commit approval)

## Implementation Summary

1. **Report blank columns (user policy: fill or delete)**:
   - Filled from engine results: `open_trade_count` (position held at window end), `win_count/loss_count/gross_profit/gross_loss/profit_factor` (from trades), `sortino` (downside-deviation ratio), `information_ratio_vs_buy_hold` (active-return mean/std × √252, enabled by new `buy_hold_equity` column in both engines' equity curves), `turnover` (traded notional ÷ mean equity), MFE/MAE in round_trips (equity-segment excursions, None-safe guards), `run_id` (resolved run id threaded through research_run → both backtest paths).
   - Deleted: `industry` column (100% blank, no source until upstream stock_basic; `industry_group` kept as placeholder). `board` now falls back to `derive_board(symbol)` when frame metadata is NaN.
   - Incremental-mode buy-hold anchor fix: continuation windows re-anchor `buy_hold_equity` to the ORIGINAL window's first mark price (engine's frame-local anchor broke split-run equality — caught by `test_incremental.py`, fixed via summary_inputs `first_mark_price`).
2. **Benchmark data (B1)**: root cause of `reference.index_daily` staleness found — TimescaleDB catalog lost all hypertable registrations while orphan `_hyper_79_*` chunks persisted under `reference.index_daily` (inheritance), making `create_hypertable` fail and silently killing the daily sync task. Fixed in `quant_ts/handlers/reference_data_handler.py`: hypertable activation moved to its own transaction with try/except WARN (plain table is fine; sync never blocked). Resynced all 5 indexes to 2026-07-24 (matches stock_daily watermark). 399006.SZ starts 2010-06-01 (source coverage, documented).
3. **Benchmark wiring (B2)**: research_run batch paths (unchunked + chunked) compute benchmark-relative metrics when `benchmark_table`+`benchmark_code` are set (alpha/beta/IR/tracking error/up-down capture/excess, merged into summary_metrics as `benchmark_*`); runner `--benchmark-table/--benchmark-code/--benchmark-value-column` flags with paired-arg guard; verification: alpha −0.0003, beta 0.0092, IR −2.0884 vs 000300.SH on real data.

## Validation Output

```bash
uv run pytest -q → 1172 passed
index_daily: all 5 indexes fresh to 2026-07-24 (4020/4020/4020/4020/3921 rows)
symbol_performance: only board had 1 blank (now derive_board fallback)
round_trips: run_id/MFE/MAE all filled
benchmark summary_metrics: benchmark_alpha/beta/IR/tracking_error/up_capture/down_capture/excess present
```

# Coding Handoff (archive: QRE-INCREMENTAL-BACKTEST-001)

## Task ID

QRE-INCREMENTAL-BACKTEST-001 (P1 incremental backtest + daily update)

## Written By

KIMI_CODE (single agent, with coder subagent for implementation)

## Status

DONE (implementation + real-DB acceptance gate PASS; awaiting commit approval)

## Implementation Summary (per approved design docs/design/incremental_backtest.md)

1. **State store** (`orchestration/incremental_state.py`): `SymbolState` (cash/quantity/entry info/cost parts/trailing anchor/pending dates) + `StrategyCheckpoint` (schema_version, strategy_id, config_hash — spec YAML + engine impl + profile/stops/universe sha1[:12], last_processed_date, watermark). Hash mismatch or corruption → rebuild.
2. **Incremental engine** (`orchestration/incremental.py`): watermark detection, no-op when W ≤ D, warmup-window frame load (chunked 400), per-symbol continuation via `run_working_incremental` (shared `_run_loop` with `run_working` — no logic fork), checkpoint-symbol exemption from universe re-filtering, cash reconstruction by replaying accumulated orders (bit-exact for full_compound).
3. **Ledgers**: orders/trades/failed (read+concat+dedup keep-last) + equity_curve (append, dedup at summary time) + `summary.csv` recomputed from accumulated ledgers (aligned with batch `_summary_row`). Ledgers written before checkpoint.
4. **CLI + timer**: `scripts/incremental_update.py --strategy <id|all>` (per-strategy try/except, summary table, --dry-run); `deploy/qre-incremental.{service,timer}` (daily 18:30, delivered not installed).
5. **Engine refactor**: vectorized engine's event loop extracted to `_run_loop` shared by `run_working` and the new incremental entry (start_index + initial state + schedule-beyond-frame); public API unchanged (127 related tests green).

## Acceptance Gate (design §5, non-negotiable)

- Synthetic: bootstrap ≡ full batch; incremental(T1)+incremental(T2) ≡ full run byte-identical including rolling-expression warmup, cross-boundary pending orders, trailing anchors, new symbols, idempotent no-op.
- **Real-DB gate: PASS** — mr04a × 50 codes: full [2024-01-01→06-30] vs bootstrap [→03-31] + incremental [→06-30]: orders 70 rows, trades 35, equity_curve 5,849, summary 50 — **all IDENTICAL**. Incremental update runtime **0.3-0.5s** (vs minutes for any replay).

## Files Changed

- New: `orchestration/incremental_state.py`, `orchestration/incremental.py`, `scripts/incremental_update.py`, `deploy/qre-incremental.{service,timer}`, `tests/test_incremental.py` (9)
- Modified: `portfolio/single_symbol_vectorized.py` (shared `_run_loop` extraction)
- `uv run pytest -q` → **1172 passed** (1163 + 9 new)

## Known Limits (documented)

- `summary.csv` does not yet include `metadata_columns` composition (board/cap/liquidity) — follow-up.
- Watermark-day signals schedule pending into tomorrow (by design — matches next-day replay semantics).
- fixed_cash checkpoint cash uses override semantics (tested only implicitly).

# Coding Handoff (archive: QRE-COST-BREAKDOWN-001)

## Task ID

QRE-COST-BREAKDOWN-001 (commission/stamp tax/transfer fee columns)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + real-data verification; awaiting docs sync and commit approval)

## Root Cause (user question: "为什么佣金、印花税列仍然为空")

The MT5-style schema columns (`commission`/`stamp_tax`/`transfer_fee`/`slippage_amount`) existed in the report builders but were **hardcoded to None** — the engine only tracked a combined `cost` (single number from `calculate_cost`), so the components were never computed per order.

## Implementation Summary

1. `AShareMarketProfile.calculate_cost_breakdown(side, notional)`: per-component breakdown (commission with ¥5 minimum, transfer fee, stamp tax on sells only); `total` matches `calculate_cost` exactly (test-locked).
2. Both batch engines (simulator + vectorized, identical columns): order rows gain `price_raw` (pre-slippage), `commission`, `stamp_tax`, `transfer_fee`; trade rows gain `entry_commission/stamp_tax/transfer_fee` + `exit_*` counterparts.
3. Report builders: `build_trades_ledger` now maps real components and computes `slippage_amount = |price_executed − price_raw| × quantity`; `build_round_trips` gains `commission`/`stamp_tax`/`transfer_fee` (entry+exit sums) — components sum exactly to the existing `total_cost`.
4. Tests (2 new): breakdown math (¥5 minimum, sell-only stamp, zero notional, total==calculate_cost), orders/trades carry components with exact sums; the existing dual-engine randomized equality suite covers column identity automatically.

## Validation Output

```bash
uv run pytest -q → 1162 passed (1160 + 2 new)
real sample (mr04a × 3 codes):
  buy: commission 299.85 + transfer 10.00 = cost 309.85 ✓
  sell: commission 289.91 + stamp 483.19 + transfer 9.66 = cost 782.76 ✓
  round trip: commission 589.77 + stamp 483.19 + transfer 19.66 = total_cost 1092.61 ✓
```

# Coding Handoff (archive: QRE-REPORT-CN-001)

## Task ID

QRE-REPORT-CN-001 (report layer: localization, strategy intro, blank filling, 2dp)

## Written By

KIMI_CODE (single agent, with coder subagent for the mechanical layer)

## Status

DONE (implementation; full-market rerun with latest data in flight)

## Implementation Summary (user's 4 requirements)

1. **全面汉化** (display layer): `COLUMN_LABELS`/`KEY_LABELS` maps in `full_market_report.py`; xlsx column headers + Key sheets + Artifacts descriptions + full HTML (sections, metric cards, tables) in Chinese. Sheet names and file names stay English (manifest contracts); CSV headers and values untouched (machine contracts for downstream pandas analysis).
2. **策略说明块**: `_build_strategy_intro()` renders strategy name/id/family, entry/exit conditions, holding days, stop params, universe rules, initial cash, execution mode at the top of the Overview sheet and HTML. Payload threading (`_strategy_identity` + `_run_request_payload` in research_run) now carries strategy_id/name/family/date_start/date_end — the fields the user reported blank.
3. **填空白格**: new shared `data/metadata_compose.py::compose_symbol_metadata` (board via derive_board, industry_group unknown while stock_basic is empty, cap/liquidity buckets from daily_basic) + `merge_symbol_metadata` (fillna, no column duplication); merged into frames in `_run_backtest` and per chunk in `_run_batch_chunked` when metadata_columns requested; `scripts/strategy_fit_report.py` deduped to the shared helper. NaN/None render as `-`.
4. **两位小数**: xlsx cell number_format — ratio columns (return/rate/pct/win/excess/drawdown tokens, count/duration excluded) `0.00%`, others `0.00`; HTML same policy (x.xx%); CSV keeps raw precision (documented decision).
5. **Performance date fix** (self-review catch): date_start/date_end in the Performance sheet were still `-` (engine summary doesn't carry them); added run_request backfill in both batch and shared branches.
6. **Latest data rerun**: watermark 2026-07-24 (daily timers healthy); same 2 strategies × full market × 2010-2026 in flight.

## Files Changed

- `src/quant_research_engine/data/metadata_compose.py` (new)
- `src/quant_research_engine/orchestration/research_run.py` (payload + metadata merge)
- `src/quant_research_engine/portfolio/full_market_report.py` (localization, intro, formatting, date backfill)
- `scripts/strategy_fit_report.py` (shared helper)
- `tests/test_report_cn_localization.py` (new, 19), `tests/test_full_market_report.py` (label updates)

## Validation Output

```bash
uv run pytest -q → 1160 passed (1141 baseline + 19 new)
small-sample xlsx inspection: 汉化表头 ✓ 策略说明块 ✓ Overview 日期/名称 ✓ 元数据列 ✓ 0.00/0.00% 格式 ✓ NaN→'-' ✓
data watermark: 2026-07-24 (fresh)
full rerun: outputs/backtests/full_history_cn/ (in flight)
```

# Coding Handoff (archive: QRE-CHUNKED-BATCH-001)

## Task ID

QRE-CHUNKED-BATCH-001 (full-history OOM fix + universe list_date fix)

## Written By

KIMI_CODE (single agent)

## Status

IN_PROGRESS (chunked path + fixes verified; final 2-strategy validation run in flight)

## Implementation Summary

1. **OOM root cause (WSL2 ×3 crashes)**: a full-market 16-year research frame (~21M rows × ~15 cols incl. strings) is ~3-4GB per worker; two workers + pandas transient copies killed WSL2's memory ceiling.
2. **Symbol-chunked backtest path** (`research_run._run_batch_chunked` + `--symbol-chunk-size N`): per-chunk frame slice load → engine → accumulate → gc; results are byte-identical to unchunked (batch engines are per-symbol independent; equality test `tests/test_chunked.py`). Progress lines per chunk. Universe filter applies per chunk with globally-loaded metadata and a merged `universe_report.json`.
3. **Universe `min_listing_days` bug fix**: `load_universe_metadata` derived `list_date` from each symbol's first bar in `stock_daily`, which starts 2010-01-04 — so every pre-2010 stock had `list_date` ≥ 2010-01-04 and was dropped when the run start minus N days preceded the data history (observed: `min_listing_days` dropped ALL 5,544 symbols, 0 trades). Fix: symbols whose first bar equals the table's data start now get `list_date = NaT` (unknown → kept); only symbols with first bar AFTER the data start are treated as genuinely dated. Regression test added.
4. **--workbook flag** (earlier slice, commit `ea05895`): compact mode can also emit `backtest_report.xlsx` + HTML + charts from in-memory results (no per-symbol trees).

## Validation So Far

```bash
uv run pytest -q → 1141 passed (chunked equality + universe regression)
run 1 (before list_date fix): universe dropped ALL 5544 symbols → caught by zero-trade metrics
run 2 (after fix): in flight — verify trades > 0, charts present, metrics sane
```

# Coding Handoff (archive: QRE-UPSTREAM-FACTOR-DELIVERY-001)

## Task ID

QRE-UPSTREAM-FACTOR-DELIVERY-001

## Written By

KIMI_CODE (single agent)

## Status

DONE (upstream delivery complete; 5/5 strategies unblocked)

## Implementation Summary

1. **Investigation**: canonical project `/home/van/quant-workspace/indicators_tushare` (git main; `/home/van/indicators_tushare` is a stray .venv). systemd timers confirmed: `quant-ts-daily` 16:30 (data sync) → `indicators-tushare-daily` 16:40 (factor update), both enabled — yaml-config factors auto-join the daily schedule with zero scheduler changes.
2. **Edits (indicators repo, no git action)**: `config/factors.yaml` sma periods += 7/9/26/50/52 + `atrraw` entry; `factors/volatility_factors.py` new `ATRRawFactor` class (raw `atr_{n}` naming; identical formula to existing `atrr_10` — pandas_ta RMA/Wilder, discovered and documented).
3. **Project flow**: validate (success/0 failures) → plan (7 target columns confirmed; superset = other pending config columns in overlap/volatility also covered per project config-parity behavior) → small-sample backfill (000001.SZ) → **value parity verified** vs hand-computed SMA/Wilder-ATR (storage-rounding diffs only, 100% non-null) → full-history backfill: **processed 5,544 stocks, failed_count 0**.
4. **Final coverage**: sma_7 13.28M rows/5,541 stocks, sma_9 13.27M/5,539, sma_26 13.17M/5,531, sma_50 13.04M/5,416, sma_52 13.03M/5,415, atr_10 13.26M/5,539.
5. **QRE side**: `factor_request_queue.py recheck` → **7 newly fulfilled, 0 pending**. Small-sample re-run of the 5 shelved strategies: 4 OK + tf07e failed with a NEW root cause — signal expression precedence bug `(sma_7 / sma_65 - 1).abs() > 0.03 & (close > sma_20)` (Python parses `> (0.03 & ...)`). Fixed with parens in BOTH the YAML and `scripts/generate_strategy_yamls.py`; tf07e now OK. **All 5/5 strategies unblocked.**
6. Daily updates: from the next 16:40 trigger, `run_daily.py` covers the new columns automatically (yaml-driven).

## Validation Output

```bash
indicators validate → success, failure_count 0
small-sample parity: sma_7/9/26/50/52 + atr_10 within storage rounding, 100% non-null
full backfill: processed 5544, failed_count 0
queue recheck: 7 newly fulfilled, 0 pending
unblock batch (5 strategies × 3 codes × smoke): 5/5 OK after tf07e expression fix
uv run pytest -q → 1137 passed
```

## Notes

- The full backfill also covered other pending config columns in the overlap/volatility categories (project config-parity behavior) — disclosed and accepted.
- tf07e's precedence bug only surfaced now because the strategy was shelved before ever reaching expression evaluation; the paren fix is in the YAML and the generator (regeneration-safe).
- indicators repo working tree left untouched (their pre-existing uncommitted changes not mine to resolve).

# Coding Handoff (archive: QRE-STRATEGY-FIT-STABILITY-001)

## Task ID

QRE-STRATEGY-FIT-STABILITY-001 (M10.1 v1.1)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + pilot; awaiting self-review and user-approved commit)

## Implementation Summary

1. **Artifact** `symbol_month_returns.csv`: per-(symbol, calendar month) `total_return` (last/first equity − 1, NaN when first ≤ 0) via the concat window collector, written by `write_batch_result` in BOTH modes — scope adjusted from "compact only" to both modes to preserve the M9.1 contract that compact outputs are a strict subset of standard outputs (the committed parity test caught it). Manifest role `symbol_month_returns` with required columns `{window, symbol, total_return}`; passes `qre report-audit`.
2. **Stability metric** (`analysis/strategy_fit.py`): `load_batch` picks up the artifact when present; per strategy at pool_tier — `stability_months_covered` (months with ≥1 pool stock reporting), `stability_ratio` (fraction of covered months where pool mean monthly return > universe mean), `stability_pool_month_mean_min`. Blank when the artifact is absent (older batches). Surfaced in `strategy_fit_summary.csv` and the markdown ranking table (`ratio/months` format). Informational only, no hard gate.
3. **Tests** (3 new): artifact content vs hand-computed oracle + manifest entry + ReportManifest validation; stability computation (pool wins one of two months → ratio 0.5, covered=2, min locked); blanks without artifact. Existing compact-parity test updated via the both-modes decision.
4. **Pilot**: 2 strategies × 3 codes × smoke — artifact written per strategy, audit clean, fit report shows stability columns.

## Validation Output

```bash
uv run pytest -q → 1137 passed, 4 warnings (1134 baseline + 3 new)
pilot: artifact OK; qre report-audit → 0 issues; fit summary stability columns present
```

## Note for Existing Batches

Older batches (incl. quick_batch_106) lack `symbol_month_returns.csv`; the fit report shows blank stability for them. Future batches and refresh runs include it automatically. If stability on the 2024 catalog is wanted before the next scheduled run, a `--resume`-compatible re-run is needed (user decision).

# Coding Handoff (archive: QRE-ANALYTICS-CONCAT-001)

## Task ID

QRE-ANALYTICS-CONCAT-001 (M9.1b ≤30s target completion)

## Written By

KIMI_CODE (single agent)

## Status

DONE — **≤30s acceptance target MET** (backtest stage 25.9s)

## Implementation Summary

1. **Concat window collector** (`_collect_window_return_rows`): one concatenated frame across symbols (per-symbol stable sort preserved for contract equality), one datetime conversion, ONE `groupby([window, symbol], sort=False)` aggregation for first/last — replacing ~5,292 per-symbol pandas groupby objects. Row order contract (dict order, windows ascending) preserved via sort=False first-occurrence semantics.
2. **Concat rolling collector** (`_collect_rolling_return_rows`): output assembled from concatenated numpy arrays into ONE final DataFrame — eliminating per-symbol DataFrame construction + the expensive 5,292-frame `pd.concat`.
3. **Equality gate**: `tests/test_analytics_vectorized.py` (risk.py oracle) passes unchanged; real-DB benchmark diff vs baseline is byte-identical for all six artifacts.
4. **Final benchmark (BENCH4)**: backtest stage **25.852s** (vs 40.172s before this slice, vs 1,718.9s original simulator baseline → **66.5×**); eval 18.4s. New decomposition: frame load ~17s (now dominant), engine ~6s, analytics ~2-3s. The M9.1b ≤30s acceptance line is now MET.

## Validation Output

```bash
uv run pytest tests/test_analytics_vectorized.py -q → 6 passed (oracle unchanged)
uv run pytest -q → 1134 passed
BENCH4 stage_durations_s: {'backtest': 25.852, 'eval': 18.419}
artifacts vs baseline: summary.csv/metrics/window M/Q/Y/rolling_20 ALL IDENTICAL
```

# Coding Handoff (archive: QRE-TRAILING-STOP-BATCH-001)

## Task ID

QRE-TRAILING-STOP-BATCH-001 (M10.2b follow-up)

## Written By

KIMI_CODE (single agent)

## Status

DONE (implementation + verification; awaiting self-review and user-approved commit)

## Current Owner

KIMI_CODE

## Implementation Summary

1. **Semantics (locked, batch-path model)**: anchor starts at actual fill `entry_price`, updates every bar while holding with the bar's `high` (fallback to `mark_price_column` when `high` unavailable); trigger when `close <= anchor × (1 - trailing_stop_pct)` → sell next bar open, reason `trailing_stop`. Precedence: pending retry > holding expiry > stop_loss > take_profit > trailing_stop > exit_signal. Deliberate difference from the shared engine (intraday low/high touch + same-day fill) — documented.
2. **Simulator** (`single_symbol.py`): `trailing_stop_pct` field; `trailing_anchor` state (set on fill, updated per bar, reset on exit); trigger branch at locked precedence.
3. **Vectorized engine**: identical anchor/branch; dense candidate set when ANY stop type enabled (fixed or trailing); `high` column array with close fallback.
4. **Wiring**: `BatchBacktestRequest.trailing_stop_pct` + validation (>0); both batch paths thread it; `ResearchRunRequest.trailing_stop_pct` override (None = spec value when `apply_stops`); runner `--trailing-stop-pct`; batch_summary config echo. Shared-mode passthrough was already wired in M10.2b and now uses the hoisted value.
5. **Tests** (5 new deterministic + randomized suite extended with trailing params): trigger with hand-computed anchor/exit, anchor reset between trades, high-column fallback, precedence vs exit_signal (reconstructed after the first data design let exit_signal preempt — documented), batch validation.

## Files Changed

- `src/quant_research_engine/portfolio/single_symbol.py`, `single_symbol_vectorized.py` (anchor + branch)
- `src/quant_research_engine/portfolio/batch.py` (field + validation + threading)
- `src/quant_research_engine/orchestration/research_run.py`, `batch_runner.py`, `scripts/batch_backtest_runner.py` (override + flag)
- `tests/test_single_symbol_vectorized.py` (+5 deterministic, randomized suite now includes trailing)

## Validation Output

```bash
uv run pytest -q → 1134 passed, 4 warnings (1129 baseline + 5 new)

# R-QRE-009 real-DB small-sample:
#   mr04a × 3 codes × smoke, --apply-stops --trailing-stop-pct 0.05:
#     simulator vs vectorized → summary.csv IDENTICAL
#   A/B (1% trailing vs off): summaries differ — trailing measurably honored
#   real trailing_stop exit observed (000001.SZ)
```


## 2026-10-24 FRM 回传修复

修改 `worker/runner.py`：risk_report.json 在 result/files 清单中最高优先，避免全量任务 20MB 上限将其挤掉。测试 `tests/test_saas_symbol_ux.py::TestWorkerSymbolDetailFiles::test_risk_report_survives_upload_budget`。

```bash
uv run pytest tests/test_saas_symbol_ux.py -q  # 38 passed
uv run pytest tests/test_worker.py tests/test_gui_saas.py tests/test_gui_risk_report.py -q  # 118 passed
```

部署后需重启本机 `qre-saas-worker` 才会对后续任务生效。

## 2026-10-27 M10.4 + 游戏修复实施交接

### M10.4（DONE，未部署/未提交）

实现文件：`src/quant_research_engine/analysis/ml_cluster.py`、`scripts/strategy_fit_ml_report.py`、`tests/test_strategy_fit_ml.py`；共享报告合同仅在 `portfolio/report_manifest.py` 增加 kind 与 4 个 role 的必需列。CR：`docs/agent/change_requests/CR-2026-10-27_m10_4_ml_cluster.md`。

CLI：

```bash
.venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33
```

注意 `.venv-ml` 没有 pytest；测试使用主环境 `uv run`，通过 `PYTHONPATH=.venv-ml/lib/python3.13/site-packages` 影子加载 sklearn，未安装新依赖。主 Agent 复核命令与结果：

```bash
PYTHONPATH=.venv-ml/lib/python3.13/site-packages uv run pytest tests/test_strategy_fit_ml.py tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py -q
# 158 passed
uv run pytest tests/test_strategy_fit_ml.py tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py tests/test_cli.py -q
# 469 passed, 14 skipped
PYTHONPATH=src uv run python -c 'from pathlib import Path; from quant_research_engine.portfolio.report_manifest import ReportManifest; m=ReportManifest.from_path(Path("outputs/strategy_fit_ml/f365c8a07b33/ml_cluster_manifest.json")); print(m.validate_contents())'
# []
```

默认真实结果为 41 insufficient + 40 all_noise；eps=2.0 的敏感性记录见 CR。未运行任何回测。

### 游戏（本地实现完成，待用户试玩）

在当前 `game/` 基线修复价格型因子与游戏 OHLC 的复权口径错位，新增独立重算审计，并重做一体化交易终端。不要使用 `.tmp/trading-game-v11-rejected/` 否决版。主 Agent 已重跑 `28 passed`、8092 HTTP 200 并查看三尺寸截图。`ema_250` 上游 11 点异常留待独立数据处理，不在本轮全库重算。

### 全仓已知红灯

最新全仓为 `2902 passed, 20 skipped, 1 failed`；失败测试硬编码读取已批准清理的外部 run YAML。后续单独改为自包含 `tmp_path` 夹具，不恢复旧回测产物。

## 2026-10-27 工程收口 + M10.4 sensitivity 实施交接

### 测试债务
- `tests/test_showcase_roller.py`：新增 `HOLDING_OVERRIDE_YAML` 最小合法 YAML；`test_build_roll_params_holding_override` 使用 `tmp_path`，不再依赖 `/home/van/qre-outputs/...`。slow E2E 的 `JOB74_YAML` 仍存在但默认 skip，未改。
- 验证：`uv run pytest tests/test_showcase_roller.py -q` → 14 passed, 1 skipped。

### M10.4 sensitivity

- `src/quant_research_engine/analysis/ml_cluster.py`：`SENSITIVITY_KIND`、`STATUS_CHOICES`、`parse_eps_grid()`、`analyze_eps_grid()`、`write_eps_sensitivity()`。
- `scripts/strategy_fit_ml_report.py`：可选 `--eps-grid`；默认 `None`。非法/空网格 exit 2，不写 sensitivity。
- 输出：`ml_cluster_sensitivity.csv`、`ml_cluster_sensitivity_strategies.csv`、`ml_cluster_sensitivity.json`；不覆盖主产物，不登记进主 manifest，重复运行字节级一致。
- 验证：`PYTHONPATH=.venv-ml/lib/python3.13/site-packages uv run pytest tests/test_strategy_fit_ml.py tests/test_strategy_fit.py tests/test_portfolio_report_manifest.py -q` → 165 passed。
- 真实只读：`.venv-ml/bin/python scripts/strategy_fit_ml_report.py --fit-dir outputs/strategy_fit/f365c8a07b33 --eps-grid 1.0,1.5,2.0` → eps=1.0/1.5/2.0 成簇策略 0/2/5，noise 490/451/396。

### 主 Agent 复核

- 全量 `uv run pytest tests/ -q` → `2906 passed, 24 skipped, 4 warnings`；`git diff --check` clean；`scripts/check-progress-docs.sh` passed。
- 未部署 ECS、未 commit/push、未跑回测、未碰游戏与共享文档由主 Agent 已统一回写。

## 2026-10-27 SaaS FRM 日收益直方图修复实施交接

### 根因

- SaaS `/api/results/<id>/risk-analysis` 只调用 `build_lab_risk_view(report)`，没有像 8081 `build_lab_risk_analysis()` 一样补 `histogram`；因此经典策略即使有 `risk_report.json`，前端“日收益分布”也因 `d.histogram` 缺失而显示“暂无分布数据”。
- 生产实测（修复前）：job 58/66 `has_report=true`、`n_obs=4068/4069`，但响应没有 `histogram` 键。
- 不能直接复用 `extract_strategy_returns()`：经典策略 SaaS 上传目录只有 per-symbol `equity_curve.csv`，没有组合级文件；这些文件也没有 `symbol` 列，可能被误选为组合曲线，且 `total_equity.pct_change` 会重新引入新股注资跳变。

### 修复

- `src/quant_research_engine/gui/lab_result.py`：新增纯函数 `daily_returns_from_cumret()` 与 `histogram_from_cumret()`。日收益由 `result_chart_data.cumret` 相邻累计值 `(1+c_t)/(1+c_{t-1})-1` 还原；缺口/非有限值重新起算，不造连续收益。
- `src/quant_research_engine/gui/saas/app.py`：`api_result_risk_analysis()` 在 `has_report=true` 时用 `dist.mean/std + chart_data.cumret` 生成 `histogram`；无报告/无 cumret/退化输入时保持 `None`。
- 测试：`tests/test_gui_lab_result.py` 新增 2 个纯函数用例；`tests/test_gui_saas.py` 新增 SaaS 端点直方图用例，并给 `_completed_job` 增加 `cumret`。TDD 先 RED 后 GREEN。

### 验证与发布

- `uv run pytest tests/test_gui_lab_result.py tests/test_gui_saas.py tests/test_saas_access_hardening.py -q` → 189 passed。
- `uv run pytest tests/ -q` → `2909 passed, 24 skipped, 4 warnings`。
- ECS：备份后同步 `lab_result.py` + `saas/app.py`，仅重启 qre-saas（MainPID 498077）。生产实测 job 58/66 `histogram` 均为 40 箱、点数分别 4068/4069，与 `n_obs` 一致。
- 未 commit/push、未跑回测、未改 schema/worker/引擎/游戏。

## 2026-10-27 TradingView 化 Spike 实施交接

- 交付：`docs/agent/change_requests/CR-2026-10-27_tv_chart_core_spike.md` 追加 §0–§10；`.tmp/tv-chart-spike/` 产生 B 路原型、A/B 同数据基准、playwright 验证与截图。
- 生产改动：零。未新增生产依赖，未改 `pyproject.toml`/`package.json`，未抓取 TradingView 站点资产，仅从 npm 隔离获取 lightweight-charts 5.2.1 并记录 Apache-2.0/shasum。
- 结论：A 42/50、B 37/50、C 24/50；推荐 A 主力 + B 受控试点；B 的 attribution 为硬阻塞。
- 主 Agent 复核：CR 与 `.tmp` 产物存在，`node --check` 通过，`git diff --name-only HEAD` 只有 brief 文档，无 `src/`、测试、模板、静态资源改动。
- 未部署 ECS（无生产代码改动）、未 commit/push。

## 2026-10-27 A 路图表修复实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`src/quant_research_engine/gui/static/replay.js`、`tests/test_saas_chart_a_fix.py`、CR 实现记录。
- ResizeObserver：单例 + `klineObserved` 去重；无 observer 时 window.resize 兜底；删除旧的对已 dispose 实例 resize 绑定。
- 重播：`visibleWindow()` 纯函数导出到 core；渲染只发可见窗口；事件标记过滤窗口；自建容器才绑 window.resize，destroy 解绑；接管模式不重复绑。
- 主 Agent 复核：diff 范围仅两文件+测试；相关 127 passed；全量 2914 passed/24 skipped + 1 环境性 PG teardown error，目标文件复跑 21 passed；性能证据 `.tmp/a-replay-perf/result.json`。
- 发布：ECS 仅同步两文件，MainPID 498885；生产 `/saas/jobs/58`、`/static/replay.js` 200，replay.js 含 `visibleWindow`。未 commit/push。

## 2026-10-27 A 路遗留修补实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/static/replay.js`、`tests/test_saas_chart_a_fix.py`。
- `replay.js` 新增 `windowDisplayData()` 并导出 core；renderFrame 对 `zeroBase` 系列按窗口基线平移。
- `job.html` 策略/基准系列设 `zeroBase: true`；mainChart resize 加 dispose 守卫。
- 主 Agent 复核：相关 130 passed；全量 2917 passed/24 skipped；生产部署后 job58/replay.js 200 且包含新标记。未 commit/push。

## 2026-10-27 静态 K 线 TV 化首片实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_saas_static_kline_tv.py`、CR 实现记录。
- 新增左侧工具栏、`#kline-ohlc` 信息区、右侧价格标尺、动态 grid/xAxis/yAxis、量/因子开关与缩放重置；重播进入前禁用工具栏并清空信息区。
- 主 Agent 复核：diff 仅 `symbol.html` + 新测试；相关 159 passed；全量 2927 passed/24 skipped；截图 1280/375 已目视确认；生产 job58 个股页 200 且包含 `kline-tools`。未 commit/push。

## 2026-10-27 MACD 旧别名拆面板修复实施交接

- 改动：`src/quant_research_engine/gui/static/factor-layout.js`、`tests/test_factor_display_contract.py`。
- 根因：旧产物因子名为 `macd_dif/macd_dea/macd_hist` 且无 `display`，旧启发式不识别，导致 MACD 三线被拆成三个副图。
- 修复：`familyOf()` 新增 MACD 类别名正则，归一到同一 `triple` 家族；支持 `dif/dea/signal/hist/histogram` 与可选参数后缀；带参后缀不与裸别名串键。
- 主 Agent 复核：`tests/test_factor_display_contract.py` 19 passed；相关 182 passed；全量 `2926 passed, 24 skipped, 1 failed`，失败为已知 risk report timing flake，单文件复跑 24 passed。
- 发布：ECS 同步 `factor-layout.js`，qre-saas active；`/static/factor-layout.js` 200 且包含新别名规则。未 commit/push。

## 2026-10-27 因子呈现复权口径系统性修复实施交接

- 改动：`src/quant_research_engine/gui/factor_registry.py`、`src/quant_research_engine/gui/lab_result.py`、`src/quant_research_engine/game/factors.py`、`tests/test_gui_lab_result.py`、CR 新文件。
- 新增共享 `PRICE_SCALED_FAMILIES` / `NON_PRICE_FAMILIES` / `MIXED_FAMILY_PRICE_PREFIXES` / `is_price_scaled()`；游戏改为复用同一分类，删除重复表。
- `lab_result._fetch_factor_panels()` 查询最新 adj_factor，价格型因子和阈值除以锚点；无量纲因子不换算。
- `lab_result._fetch_stock_daily()` 统一前复权@最新；`_fetch_symbol_range_returns()` 恒 hfq，不再依赖 `QRE_PRICE_BASIS`。
- 主 Agent 复核：相关 107 passed；全量 2930 passed/24 skipped；ECS 部署后页面/API 200。未 commit/push。

## 2026-10-27 K 线重播 TV 化首片实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`src/quant_research_engine/gui/static/replay.js`、`tests/test_saas_replay_tv.py`、两个既有测试的抽取正则、CR 实现记录。
- `mountKlineReplay()` 复用静态 helper：`klineGridSpec`、`klineAxisLabelIndex`、`klineInfoHTML`、`klineSetInfo`；yAxes 右置并可带 formatter。
- `replay.js` 只加可选透传：`yAxes[].position/formatter`、`opts.axisPointer`、`opts.axisLabelIndex`；默认路径不传即原输出。
- 主 Agent 复核：相关 141 passed；全量 2936 passed/24 skipped；`.tmp/replay-tv/` 33/33，截图已目视确认；ECS 部署后 job58/symbol/replay.js 200。未 commit/push。

## 2026-10-27 重播遗留清理实施交接

- 改动：`src/quant_research_engine/gui/static/replay.js`、`src/quant_research_engine/gui/saas/templates/symbol.html`、多个既有测试 harness、CR 实现记录。
- 新增 `formatTooltipValue()`、`klineHeightForPanes()`；K 线重播 `tooltipPercent:false`，成交量 series 级万手 formatter；静态/重播高度共用。
- 主 Agent 复核：相关 120 passed；全量 2946 passed/24 skipped；ECS 部署后 job58/920832/replay.js 200。未 commit/push。

## 2026-10-27 重播灰字备注清理实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_saas_replay_tv.py`。
- `#btn-kreplay` 增加 `data-tip`；删除 `#kreplay-note` 动态插入与 remove 逻辑。
- 主 Agent 复核：相关 122 passed；全量 2948 passed/24 skipped；生产旧 note 0、data-tip 1。未 commit/push。

## 2026-10-27 持仓期年化分母修复实施交接

- 改动：`src/quant_research_engine/gui/static/lab-ui.js`、`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_lab_ui_holding_days.py`。
- 新增 `LabUI.tradingDaysHeldInRange(dates, dateIdx, trades, i0, i1)`：按 entry→exit 自然日并集剔周末计数，区间裁剪、无退出/越界安全。
- job/symbol 的 `exposureCards()` 用 `heldDays` 作为年化分母；曝光度仍按区间内有持仓的 equity 条目数计算。
- 主 Agent 复核：新测试 3 passed；相关 192 passed；全量 2939 passed/24 skipped；ECS 部署后生产页面包含 `252 / heldDays`。未 commit/push。

## 2026-10-27 同类指标防护加固实施交接

- 改动：`src/quant_research_engine/gui/lab_result.py`、`src/quant_research_engine/gui/saas/templates/job.html`、`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_lab_ui_holding_days.py`。
- `lab_result` 年化收益加 `base > 0` 与 `TypeError` 保护；前端区间收益/年化/基准收益加除零与负基数保护。
- 主 Agent 复核：相关 193 passed；全量 2940 passed/24 skipped；ECS 部署后 job58/920832 200 且包含新保护。未 commit/push。

## 2026-10-27 重播灰字备注清理实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_saas_replay_tv.py`。
- `#btn-kreplay` 增加 `data-tip`；删除 `#kreplay-note` 动态插入与 remove 逻辑。
- 主 Agent 复核：相关 122 passed；全量 2948 passed/24 skipped；生产旧 note 0、data-tip 1。未 commit/push。

## 2026-10-27 历史旧个股详情刷新实施交接

- 改动：`src/quant_research_engine/gui/lab_result.py`、`src/quant_research_engine/gui/saas/app.py`、`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_gui_saas.py`、`tests/test_gui_saas_pages.py`、CR 实现记录。
- 新增 `factor_basis` 标记与 `generate?refresh=1`；前端旧详情刷新入口；只读详情 200 增加 `readonly/readonly_kind` 并隐藏入口。
- 主 Agent 复核：相关 263 passed；全量 2956 passed/24 skipped；ECS 部署后 job58/920832/showcase readonly 验证通过。未 commit/push。

## 2026-10-27 K 线画线工具首片实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_saas_static_kline_tv.py`、`tests/test_saas_replay_tv.py`、CR 实现记录。
- 新增 `klinePixelToPoint()`、`klineDrawingSeries()`、`klineDrawApply()` 等；画线按钮纳入 `KLINE_TOOL_KINDS`，重播禁用自动覆盖。
- 主 Agent 复核：相关 131 passed；全量 2961 passed/24 skipped + 1 已知 timing flake，目标文件复跑通过；ECS 部署后生产入口存在。未 commit/push。

## 2026-10-28 个股详情加载失败修复实施交接

- 改动：`src/quant_research_engine/gui/lab_result.py`、`src/quant_research_engine/gui/saas/app.py`、`src/quant_research_engine/worker/runner.py`、`tests/test_json_finite_contract.py`、`tests/test_gui_saas.py`、`tests/test_gui_lab_result.py`、CR 新建。
- 新增 `lab_result.json_safe()`：递归归一化（datetime/date→ISO、NaN/±Inf→None），三处出口唯一实现。
- `_jsonable()`（SaaS 全量 JSON 出口）与 `_json_sanitize()`（worker 写产物）均委托 `json_safe`；lab 详情路由 `jsonify(json_safe(data))`。
- `_fetch_factor_panels()` 两处因子查询加 `math.isfinite` 过滤，DB NaN 按缺口处理，新产物自身干净。
- 主 Agent 复核：新增/回归 4 passed；相关 152 passed；全量 2960 passed/24 skipped（2 例存量 ConsoleOps 失败已在 pristine HEAD 复现，与本次无关）。
- 生产：ECS 同步 `app.py` + `lab_result.py`；原始 API NaN token 归零；无头 Chromium 验证 job58 的 301308/001309/301018/920832.BJ 全部正常；job58+job66 各 80 只严格 JSON 扫描 bad=0。未 commit/push。

## 2026-10-28 job#78 个股详情刷新入口修复实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_gui_saas_pages.py`、CR 新建。
- `showSymbolDetailRefresh()` 去重由 `(host.children || []).some(...)` 改为 `Array.prototype.some.call(host.children || [], ...)`——HTMLCollection 没有 Array 方法，原写法在浏览器必抛 TypeError 并被 `load()` catch 吞成整页失败。
- harness `symbolEl()` 的 `children` 改为 `htmlCollectionView()` 的 HTMLCollection 形态（内部 `_children` 维护），新增 `childById()`；`test_symbol_detail_refresh_entry_for_legacy_payload` 增加 `calls.failure === 0` 断言。
- 主 Agent 复核：harness 改完先 RED 复现线上，源码修复后 GREEN；`test_gui_saas_pages.py` 94 passed；全量 2960 passed/24 skipped。
- 生产：真实 DOM 验证 + 真实 job#78 产物端到端 `load()` 0 失败；job58/66 回归通过。未 commit/push。

## 2026-10-28 指标设置与面板管理实施交接

- 改动：`src/quant_research_engine/gui/static/factor-layout.js`、`src/quant_research_engine/gui/saas/templates/symbol.html`、`tests/test_factor_display_contract.py`、`tests/test_saas_static_kline_tv.py`、CR 实现记录。
- `plan()` 新增可选第三参 `paneOrder`；`symbol.html` 新增 `kt-ind` 按钮、指标设置模态、`paneOrder/setPaneOrder/movePane/hidePane` 与 `klineIndicatorDialog`。
- 副图顺序持久化 `qre_pane_order`（单一 JSON 数组键），非法输入降级空数组。
- 主 Agent 复核：`plan()` 第三参 6 组断言 + DOM 合同 + harness 交互流；相关 162 passed；全量 2964 passed/24 skipped。
- 生产：真实浏览器验证通过（MainPID 512078）；过程教训——机械移动函数区块时误删 `renderFactorChips` 的 `const slot`，VM 单测全绿但生产炸，已补真实页面渲染验证。
- 未 commit/push。

## 2026-10-28 使用说明侧边栏玻璃胶囊实施交接

- 改动：`help.html`、`lab-theme.css`、`night-mode.css`、新增 `static/help-nav.js` 与 `tests/test_saas_help_nav.py`、CR。
- 未动 `base.html`、其它模板、`night-mode.js`，无外部依赖。
- 主 Agent 复核：127 相关 passed；全量 2988 passed/24 skipped；生产真实浏览器复测动画三段（拉伸 1→1.18、压扁 0.90、过冲 1.048→1）、夜间、375、reduced-motion 全部符合需求。
- 未 commit/push。

## 2026-10-28 全站卡片磨砂玻璃 + 光标光斑 + 轻微 3D 倾斜实施交接

- 改动：`static/lab-theme.css`、`static/night-mode.css`、新增 `static/card-fx.js`、`saas/templates/base.html`（仅加一行 `<script>`）、`tests/test_card_fx.py` 新建、CR 新建。未动任何业务模板结构。
- 玻璃：`backdrop-filter:blur(28px) saturate(140%)` + 48% 白底 + 1px 半透明白描边 + 顶部 inset 高光 + 24px 圆角 + 两层大投影；`--card-radius` 新 token，不动 `--radius`。
- 背景装饰层 `body::before`（fixed / `pointer-events:none` / `z-index:-1` / 四团品牌紫径向渐变）：负 z-index 方案免去给 `.wrap`/`.container` 提层级，也不碰 `.topbar{z-index:40}` 与既有浮层。
- 光斑 `::before`（`z-index:-1` + 父级 `isolation:isolate`，压在文字之下，不影响对比度）+ 描边环 `::after`（`mask-composite:exclude` 只留 1px）。
- 倾斜 `.fx-tilt`（JS 判定 `!querySelector('canvas')` 且非嵌套内层才挂；图表卡 computed `transform` 恒为 `none`）；CSS `clamp()` 与 JS 双向钳制 ±4。
- 踩坑记录：① 数学函数不能裸乘 `1deg`（必须包 `calc()`），且 `clamp(-1,…)` 钳的是度、把 3.98° 钳成 1°；② `background` 简写会重置 `background-image`，玻璃底拆成 `background-color` + `background-image`；③ 装饰层第一版出血到视口外，卡片中心采不到紫色（差 1 个色阶）。
- 测试：`tests/test_card_fx.py` 18 例（源码合同 + 夜间 token + JS 接线 + Node vm 纯函数 harness）；目标组合 145 passed；全量 `3006 passed, 24 skipped`。
- 生产已部署（`deploy-ecs.sh` 四个运行时文件），无头 Chromium 七页自验通过；帧率结论：委托监听簿记成本 ≈0ms，剩余成本来自无 GPU 环境下浏览器对 `blur(28px)` 的软件重采样（关掉 `backdrop-filter` 即回 60fps）。截图与报告在 `.tmp/card-fx/`。未 commit/push。

## 2026-10-28 因子前复权锚点实施交接

- 改动文件：`src/quant_research_engine/gui/lab_result.py`、`src/quant_research_engine/gui/saas/app.py`、
  `tests/test_gui_lab_result.py`、`tests/test_gui_saas.py`、`tests/test_saas_symbol_ux.py`、
  `tests/test_saas_result_help.py`、CR `CR-2026-10-28_factor_qfq_anchor.md`。
- 关键实现：`_latest_adj_factor(conn, ts_code, as_of=None)`，`as_of` 非空时 SQL 追加
  `AND trade_date <= :d`；调用点传 `dates[-1] if dates else None`。
  `None` 仅用于无 K 线日期的兜底路径，行为与旧版一致。
- 预防机制位置：`create_saas_app()` 内 gzip 详情解包之后、`data.get("ok")` 判断之前，
  判 `not data.get("factor_basis")` 即置 `data = None`。前端据此出生成按钮。
- 夹具注意：`tests/test_gui_saas.py` 的 `test_legacy_artifact_without_basis_is_not_served`
  必须在 `TestSymbolDetailRefresh` 类内（依赖该类 fixture），勿放错类。
- 存量产物 rescale 分类单一来源 `gui.factor_registry.is_price_scaled`；
  注册表 JSON 顶层 key 是 `factors`（list，895 项），不是 `entries`。
- 测试：全量 `3009 passed, 24 skipped`。CR 含完整实证数据（比值法）。
- 未 commit/push。

## 2026-10-28 K 线双引擎互斥实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`（新增 `klineDisposeEngines()`，
  三个调用点改走它）、`tests/test_lwc_kline_adapter.py`（新增 `TestKlineEngineExclusive` 2 例）、
  `tests/test_saas_static_kline_tv.py`、`tests/test_saas_replay_tv.py`、
  `tests/test_saas_chart_a_fix.py`、`tests/test_gui_saas_pages.py`（harness 抽取区 + DOM 桩）、
  CR 新建。
- **harness 抽取区坑**：`klineDisposeEngines` 定义在 `let klineResizeBound` 之前，四个 harness 原抽取区
  都不含它 → `ReferenceError: klineDisposeEngines is not defined`。已用「前置区块」方式补齐：
  static/replay/chart_a_fix 三个文件加 `_dispose_source()` 前置；`test_gui_saas_pages.py` 给
  `_run_symbol_script_js` 加可选 `prefix_pattern` 参数（与 job 版同型），测试处传 `SYMBOL_DISPOSE_PATTERN`。
- **DOM 桩坑**：`makeEl`/`el` 桩缺 `firstChild`/`removeChild`，已补（真实 echarts/LWC 会往容器插节点）。
- 测试：`test_lwc_kline_adapter.py` 10 passed；相关 6 文件全绿；全量 `3011 passed, 24 skipped`。
- 真实浏览器验证（Chromium + 生产同款 echarts/LWC）：修复前 echarts→lwc 后容器 2 子元素、
  scrollHeight 800（叠加 + 高度翻倍）；修复后恒 1 个，8 轮切换零 pageerror。
  证据 `.tmp/engine-excl/`。已部署 ECS（MainPID 542952，回滚副本 `/tmp/qre-deploy-20261028T115036Z.bak`）。
- 未 commit/push。

## 2026-10-28 平均持股周期 + 风险调整收益实施交接

- 改动：新增 `static/perf-metrics.js`、`tests/test_perf_metrics.py`、`docs/agent/24_PERF_METRICS_CONTRACT.md`、
  CR；改 `saas/templates/job.html`、`saas/templates/symbol.html`、`gui/engine.py`、`gui/lab_result.py`、
  `tests/test_gui_saas_pages.py`（3 处 harness 补桩）、`tests/test_saas_classic_actions_ui.py`（1 处）、
  `tests/test_saas_result_help.py`（主指标卡 6→7 契约改写）。
- `renderRiskAdjusted` 是唯一新增渲染入口，job 与 symbol 各一份（基准不同），
  都在 `#ra-strip`，三项全 null → `display:none` + 清空 innerHTML。
- `avgHoldingDays` / `holdingDaysOf` 口径 = 自然日，与 `round_trips.holding_days` 逐值一致（已实证）。
- 后端只加键不改逻辑：`SUMMARY_METRIC_FIELDS` 三项 + chart_data metrics 三项。
- 测试：`test_perf_metrics.py` 10 passed；相关 5 文件 154 passed；全量 `3018 passed, 24 skipped`。
- RED 两次：β 分母写错 → 交叉验证红；不跳空 closes 基准 → 渲染测试红。
- 未 commit/push。

- 真实浏览器端到端已验（`.tmp/perf-browser/verify.py`，Chromium + 路由拦截 fixture）：
  job 7 卡 + α=12.00%/β=0.89/IR=0.78（**与 Python performance_summary 完全一致**）；
  symbol 平均持股周期 48.7 天 + 交易表逐笔 31/35/80/—；全 null 隐藏且清空；
  375px 无横溢；零 pageerror/console error。

## 2026-10-28 LWC 图例开关修复实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/symbol.html`（仅 `lwcRenderLegend`）、
  `tests/test_lwc_kline_adapter.py`（新增 `TestLwcLegendToggle` 3 例）、CR 新建。
- `pill(label, color, key, isStatic, restore)`；点击 `setChipState(key, hiddenNow ? restore : 'hidden')`，
  `hiddenNow` 由 `chipStates()[key] === 'hidden'` 实时得出（不用闭包的 `on`）。
- 图例数据源 `plan.chips`（含隐藏组）；副图行 `paneChips.length` 判显隐。
- restore 值：`__vol__`/`__marks__` → `'on'`；overlay chip → `c.states[0]`（'overlay'）；
  pane chip → `c.states[0]`（'pane'）。
- overlay pill key 用 `c.key`（`fkey(f) === f.col || f.name`，与原 `o.f.col || o.f.name` 等价）。
- RED：改回旧写法 3 例全红。全量 `3024 passed, 24 skipped`。真实浏览器（Chromium + LWC 引擎）
  5 pill、三类往返全通、隐藏后 pill 不消失、零 pageerror。未 commit/push。

## 2026-10-28 LWC 图例开关修复（第二批 commit）

（本条的进度/handoff 记录随上一批 metrics commit 一并落入 `04/05/09/11` 四份文档，
此处补一条索引，避免两份改动的文档记录分家。）

- 改动范围：`src/quant_research_engine/gui/saas/templates/symbol.html`（仅 `lwcRenderLegend`）
  + `tests/test_lwc_kline_adapter.py`（新增 `TestLwcLegendToggle` 3 例）
- 权威记录：`docs/agent/change_requests/CR-2026-10-28_lwc_legend_toggle.md`
- 关键结论：双引擎下同一交互有两条实现（ECharts `renderFactorChips` / LWC `lwcRenderLegend`），
  改一条必须回归另一条——本轮 bug 正是只回归了 ECharts 那条。

## 2026-10-28 小卡条 UI 统一实施交接

- 改动：`src/quant_research_engine/gui/saas/templates/base.html`（仅一段 CSS）、
  `tests/test_perf_metrics.py`（新增 `TestMetricStripStyleContract` 4 例）、CR 新建。
- 六条小卡条（`#metric-strip`/`#sum-strip`/`#range-strip`/`#ra-strip`/`#replay-metrics`/`#kreplay-info`）
  统一：`display:flex;flex-wrap:wrap;gap:10px` + `--tint` 紫底 + 两档 `flex:1 1 <min>px`
  （密集条 130px，简介/ra 条 250px）。旧 `grid-template-columns` 规则已删。
- **加新小卡条时的硬规则**：必须把新 ID 同时加进 flex 规则和紫底规则，
  否则会回落白底 + grid 半行（`TestMetricStripStyleContract` 会抓）。
- `.metric-card` 不在磨砂玻璃卡族内（`.card`/`.chart-box`/`.big-link`），紫底平坦卡是既有设计。
- 测试 4 例 RED 验证通过；`test_perf_metrics.py` 14 passed；全量 `3028 passed, 24 skipped`。
- 真实浏览器（job/symbol × 3 视口）全通过；`.tmp/perf-browser/verify.py` 可复跑
  （先 `.venv/bin/python` 渲染，再 `.tmp/browser-venv/bin/python ... browser`）。
- 未 commit/push。

## 2026-10-29 小数据卡统一实施交接

- 新增文件 `static/card-class.css`（必须随部署上传；URL `/static/card-class.css`）。
  base.html 在 night-mode.css 之后加 `<link>`——**加载顺序是硬要求**，
  同特异性下后加载才胜出，这是压住 lab-theme `.risk-cards .metric-card` 粉底粉框的唯一机制。
- 基类规则用容器类选择器把特异性提到与 lab-theme 同级：
  `.metric-strip .metric-card, .wear-cards .metric-card, .risk-cards .metric-card,
  .metric-card{background:#fff;border:1px solid var(--lav);border-radius:10px}`。
- 数值色提级是必须的：`.metric-card .m-value.pos`（0,3,0）否则被
  `.metric-card .m-value`（0,2,0）压住，盈亏不再红绿。`.wb-val.pos/.neg` 同理。
- 模板改动：两个 `wc()` 去掉 `style="color:var(--lav-deep)"` 内联；磨损条毛/净收益
  6 处 `.wb-val` 加 `pos/neg` 类（job 2 处 fees + symbol 4 处：wear 块 2 + 回退块 2）。
- 测试：`TestMetricStripStyleContract` 8 例，RED 两次（删 `.wear-cards` 选择器 → 红；
  删 `.m-value.pos` 提级 → 红）。全量 `3032 passed, 24 skipped`。
- 真实浏览器：`.tmp/perf-browser/verify.py`（先 `.venv/bin/python` 渲染，再
  `.tmp/browser-venv/bin/python ... browser`）；fixture 需含 wear/risk/fees_summary/
  risk_analysis（**risk-analysis 必须带 `has_report: true`**，否则 loadRisk 整块隐藏）。
- 未 commit/push。

## 2026-10-29 小数据卡磨砂玻璃实施交接

- 改动：`static/card-class.css`（两处规则）、`tests/test_perf_metrics.py`
  （`test_all_cards_frosted_glass` 改写）、CR 新建。
- 基类规则（注意选择器顺序与缩进，测试用正则逐项匹配）：
  `.metric-strip .metric-card, .wear-cards .metric-card, .risk-cards .metric-card,
  .metric-card { background-color:var(--glass-bg); background-image:var(--glass-sheen);
  border:1px solid var(--glass-line); border-radius:var(--card-radius);
  box-shadow:inset 0 1px 0 var(--glass-hi),var(--glass-shadow); padding:12px 14px;
  -webkit-backdrop-filter:blur(28px) saturate(140%); backdrop-filter:blur(28px) saturate(140%); }`
- 磨损/风险条收回规则同样四项（background-color + background-image + border-color +
  box-shadow），**不用 background 简写**。
- padding 从 8px/10px 统一到 12px 14px——24px 圆角配原来的 8px padding 会显得挤。
- 未 commit/push。
