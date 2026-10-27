# Task Handoff

## Task ID

QRE-DATA-CLEANUP-EXECUTION（用户批准的遗留数据清理与分钟 CSV 只读检查）

## Current Status

DONE（2026-10-27；指定遗留项已清理，分钟 CSV 未手动入库/清洗/压缩，未 commit/push）

## Task Note

- 新增 `mindata/2026/20261019`、`20261020`、`20261021` 三份 CSV 仅做只读检查：表头与 `COLMAP` 匹配，每份约 132MB / 135.4 万数据行；审计表和分钟表最新均为 2026-10-16，三日均为 pending。`minute-csv-ingest.timer` enabled/active，下次触发 2026-10-27 17:20 CST，将自动入库、校验行数并删除 CSV；本轮未手动触发。
- 用户明确批准后删除 `akshare_data`、`aguhuice_test`、`quant_hub`、`aguhuice_local`，以及已盘点的 `qre-outputs` 陈旧回测/实验产物。保留 `refresh/registry.json`、`state.json`、`delta/`、`saas_uploads`、`market_risk`、`video_packages` 和两个待验收 staging 库。
- 清理前留档在 `/home/van/quant-workspace/backups/local-cleanup-20261027/`：`aguhuice_local.dump` 为可恢复全量备份；`akshare_data.schema.sql` 仅表结构，`akshare_data.counts.txt` 记录 36,147,932 行与日期范围，**akshare 数据本体未备份，删除不可恢复**；`old-outputs-manifest.json` 记录文件清理清单。
- 验证：`qre-outputs` 27G → 536M，磁盘可用 386G → 418G；8080 dashboard 与 8092 游戏均 HTTP 200。8081 staging 配置仍引用已删除的 `aguhuice_local`，下次使用该 staging 前必须重建/换库。
- 用户暂停分钟数据清洗与压缩，本轮均未执行。M10.4 依赖已批准；既有 `.venv-ml` 已有 scikit-learn 1.9.0 / pandas 3.0.5 / numpy 2.5.1，无需重复安装。

### 历史盘点（2026-10-27 早些时候，只读；当时未删除任何文件/表/数据库）

### 盘点结果（2026-10-27，只读；未删除任何文件/表/数据库）

**A. `/home/van/mindata` 残留 CSV —— 已经是空的**
- 现状：**0 个文件，24 KB**（只剩 `mindata/` 与 `mindata/2026/` 两个空目录 inode）。文档记载的 324GB / 4313 个交易日 CSV 已全部不在。
- 谁删的（有据）：`quant_ts/logs/minute_import.log` 显示**只有 5 个 CSV 是被「先校验后删除」的流程删的**——2026-10-18 17:06:43–17:06:50，`mindata/2026/` 的 20261012–20261016 五个文件，每个都先 `rows_csv == rows_db` 校验通过才删。`import_minute_csv.py` 内**没有任何 unlink/remove/rmtree 代码**，因此 2009–2026-10-11 的 4308 个历史 CSV 是**无日志的脚本外删除**。
- 时间线证据：审计表最后一条写入 `2026-10-11 20:10:20`，`mindata/` 顶层目录 mtime `2026-10-11 23:19:18`——即删除发生在全部校验记录写完之后约 3 小时。顺序是对的，但**没有审计轨迹**。
- **「已入库」≠「可安全删除」的核查（本轮重点）**：审计表 4318 条（2009-01-05 → 2026-10-16），`rows_csv` 与 `rows_db` **全部相等**（0 条不一致）；审计日期与 `stock_minute_1m` 实际日期**双向差集均为 0**；另抽查 8 个日期（含磁盘打满那次失败的 2022-08-22/25/29）比对审计 `rows_db` 与当前实时行数，**8/8 MATCH**。结论：DB 内数据完整一致，**但源 CSV 已不可恢复**——今后若发现缺口，唯一补救是回原始数据商重新下载。
- 定时工作流：`minute-csv-ingest.timer` enabled/active，Mon–Fri 17:20（`Persistent=true`，User=van，oneshot），2026-10-18 至今每天「扫描到 CSV 0 个」。
- 清理建议：**无可删文件**。两个空目录建议保留（入库脚本扫描 `/home/van/mindata/**/*.csv`，删目录需同步改脚本）。

**B. `stock_minute_1m_audit` 与定时入库日志**
- 审计表：4318 行，PK `trade_date`，列为 `trade_date/file_path/rows_csv/rows_db/done_at`；`done_at` 分布 = 2026-10-11 4313 条 + 2026-10-18 5 条。
- 日志实际路径是 `quant_ts/logs/minute_import.log`（516 KB）——**文档 20 §3.6 写的 `minute_daily_ingest.log` 不存在，属文档错误，本轮已修**。
- 日志含 29 条 ❌/ERROR，全部是 2026-10-11 17:09–17:15 的**磁盘打满事故**（`No space left on device`，日期 20220822/23/24/25/29）。这 5 个日期当天稍后重试成功并入库（`done_at` 17:15–17:56），本轮已抽查验证行数一致。
- **日更依赖缺口**：`stock_minute_1m` 最新交易日 **2026-10-16**，而 `stock_daily` 最新 **2026-10-26**——分钟线已**落后日线 10 天**。原因：分钟线只入用户拷进 `mindata` 的 CSV，10-16 之后没有新文件。需要用户确认是「有意暂停分钟线」还是「忘了拷数据」。

**C. 日线 `stock_daily_qfq_legacy` —— 已经不存在（最高风险）**
- 全库（所有 schema）搜索 `%legacy%`/`%qfq%`：**0 条**。该表已被删除。
- 文档 20 §2.1 与 11 号文档均写明「旧表保留为 `public.stock_daily_qfq_legacy`（回滚用，方案A验收后删除）」——即 2026-10-12 前复权口径改原始价口径（方案A）的**回滚路径已经消失**。
- 本地**没有 `tushare_data` 的 dump**（`~/quant-workspace/backups/ecs-aguhuice/` 只有 ECS 上 aguhuice SaaS 库的 dump），因此**不可恢复**。
- 缓解事实：新口径（原始价 + `adj_factor` 列，读取层复权）自 2026-10-12 起生效，因子 10 表 + alpha191 已按新口径全历史重算并抽查通过，生产回测一直跑在新口径上。**但「回滚到 qfq」这个选项从此没有了**，需用户明确接受。

**D. 分钟线压缩缺口（新发现，140GB 可回收）**
- `stock_minute_1m` 共 922 chunk：**708 个已压缩 = 396 MB**，**214 个未压缩 = 140 GB**（压缩比约 350:1）。
- 其中 **213 个 chunk 的 `range_end` 早于 T-7 却仍未压缩，合计 140 GB**，覆盖 2022-09-01 → 2026-10-08（2022:18 个/11G、2023:52/33G、2024:52/34G、2025:51/35G、2026:40/27G）——**违反文档 20 §3.4「T-7 之前的 chunk 必须处于压缩态」**。
- `minute_compress.log` 结尾写「2026-10-11 17:55:09 压缩完毕 707 chunks」，但未压缩 chunk 的内部 ID（如 2022-09-01 对应 `_hyper_67_56121_chunk`）明显高于已压缩集合（`_hyper_67_45526` 等），说明这些 chunk 是在那次压缩**之后**才创建的，之后再没跑过压缩。
- 处置：重跑既有脚本 `quant_ts/compress_minute_chunks.sh`（幂等、已跑通过一次），预计回收 **~139 GB**。这是本轮发现的**最大且最低风险**的收益项。

**E. 测试库 / 遗留库**
| 库 | 大小 | 内容 | 判定 |
|---|---|---|---|
| `aguhuice_test` | 7.5 MB | **0 张表** | 可删候选（空壳） |
| `quant_hub` | 10 MB | **0 张 public 表** | 可删候选（空壳） |
| `aguhuice_local` | 8.9 MB | 3 users / 15 jobs（2026-09-27 → 10-05） | 可删候选（陈旧本地测试数据，需确认无配置引用） |
| `qre_factor_display` | 8.7 MB | 1 user / 1 completed job | 上一任务 staging，**待 QRE-FACTOR-DISPLAY-CONTRACT 验收后**可删 |
| `qre_readonly_share_browser` | 8.7 MB | 1 user / 3 completed jobs | 上一任务 staging，验收后可删 |
| `akshare_data` | **5.8 GB** | `stock_ticks` 36,147,932 行，2026-04-07 → 04-24，10 个分区 | **高风险待确认**：`AK_DB_URL` 只在 `quant_ts/config.py` 定义，全仓无任何消费者；数据是 4 月的 tick 实验 |
- 任务书提到的 `qre_saas` / `dbg` **两个库都不存在**（早已不在）。

**F. 文件系统遗留（`/home/van/qre-outputs`，27G，仓库 `outputs` 符号链接指向它）**
- `refresh/incremental` **17G**，最后写入 2026-08-02 → 陈旧产物；但同目录下 `registry.json`/`state.json`/`delta/` 是 **KB 级且被 `gui/refresh_registry.py` 引用的活配置**，**绝不能整目录删**。
- `gui-console/runs` **5.4G**，最后写入 2026-08-20 → 陈旧 run 产物（`worker/runner.py` 以此为 runs 根）。
- `backtests` 4.3G（2026-08-18）、`gui-run` 442M（2026-09-13）→ 陈旧。
- **活跃勿动**：`saas_uploads`（今天还有 job_38 写入）、`market_risk`（10-26）、`video_packages`（10-24）。
- 另有约 20 个 7 月的 `*_check` / `*_smoke` 小目录属旧实验产物。
- QRE 仓库 `.tmp` 874M：`ms-playwright` 681M + `browser-venv` 142M 是浏览器审计工具链（要留），其余约 60M 是各任务证据。
- 磁盘：1007G 总 / 570G 已用 / **386G 可用（60%）**——无告急，但压缩那 139G 仍是实打实的回收。

**待用户确认清单（不做任何实际操作）**
1. `stock_daily_qfq_legacy` 已消失：接受「永失 qfq 回滚能力」，还是要求从 tushare 重新拉一批 qfq 历史做应急档？
2. 分钟线 `compress_minute_chunks.sh` 是否现在重跑（回收 ~139GB，幂等，已有一次成功记录）？
3. 分钟线数据停在 2026-10-16、日线已到 2026-10-26：是继续暂停分钟线，还是恢复拷贝 CSV？
4. `akshare_data`（5.8GB、4 月 tick、无消费者）是否删除？
5. 空壳库 `aguhuice_test` / `quant_hub`、陈旧 `aguhuice_local` 是否删除？
6. `qre-outputs` 里 17G `refresh/incremental` + 5.4G `gui-console/runs` + 4.3G `backtests` 是否清理（保留 `refresh/registry.json`/`state.json`/`delta`）？
7. 两个上一任务 staging 库（`qre_factor_display` / `qre_readonly_share_browser`）是否等各自任务验收通过后再删？

**本轮未做**：未删除任何文件/表/数据库、未修改生产或 WSL 数据、未跑真实回测、未碰游戏；未 commit/push。

## Task ID

QRE-ECS-SSH-HARDENING（root SSH 与部署发布纪律加固）

## Current Status

已生效待人工验收，未 commit/push（2026-10-27；root 直连已禁，deploy+sudo 为唯一入口）

## Task Note

- 先验证 deploy 密钥登录与 sudo，再禁 root 直连；保留 9090 TCP 转发，仅密钥认证，防锁死。
- 独立 sshd drop-in，备份后 `sshd -t` 再 reload；验证 deploy 新连接、sudo、服务和隧道，root 按预期拒绝。
- 同步 deploy+sudo 部署纪律、备份与云控制台救援路径；不碰 WSL 数据库、worker、因子、UI 或游戏，不跑真实回测，不 commit/push。

### 实施结果（2026-10-27，已生效待人工验收，未 commit/push）

- **先审计后变更（顺序未倒置）**：改动 SSH 前已实际证明 ① deploy 密钥登录成功（uid=1000， authorized_keys 公钥指纹 `SHA256:ghZ0NGRMwpXkAk6CrAnmDILAxRYhJ3lhLCUntkLPooE` 与本机一致）；② `sudo -n` 非交互可用（`uid=0`）；③ 业务文件可读（`/srv/aguhuice/qre/configs/factor_registry.json`、`deploy/saas/metadata.json`）；④ 完整部署链干跑成功（写 `/tmp` → `sudo -n install` 到业务路径 → `sudo -n rm` 清理）；⑤ deploy 可建 SSH 隧道（9091 → ECS 8090，`/saas/new` 200、`/api/saas/factors` 902/902 带 zh）。全程未断开任何既有会话。
- **审计发现的真实缺口（已修，否则一禁 root 就锁死）**：`deploy` 虽在 `sudo` 组，但 `/etc/sudoers.d/deploy` 只放通 `/usr/bin/systemctl` 与 `/usr/bin/docker`，且 deploy 密码为锁定态（`passwd -S deploy` = `L`）——即**改动前 `sudo -n` 实际不可用**，禁 root 后会既不能装文件也不能做 PG 备份恢复/证书/防火墙等运维。已新增 `/etc/sudoers.d/90-qre-deploy`（`deploy ALL=(ALL:ALL) NOPASSWD: ALL`，0440 root:root，`visudo -c` 全绿）。同时修掉一个既有隐患：`/etc/sudoers.d/deploy` 权限是 0644（`visudo -c` 报 bad permissions），已改 0440。
- **sshd 变更**：新增独立 `/etc/ssh/sshd_config.d/99-qre-hardening.conf`（0644 root:root）——`PermitRootLogin no` / `PasswordAuthentication no` / `KbdInteractiveAuthentication no` / `PubkeyAuthentication yes` / `AllowTcpForwarding yes`（9090 管理台隧道依赖 TCP 转发，显式保留）。**必须说明的一处附带改动**：既有 `99-aguhuice-hardening.conf` 的 `PermitRootLogin prohibit-password` 改成了 `no`。原因是 sshd 对同一关键字**取先出现者**，而 `Include sshd_config.d/*.conf` 按字典序展开，`99-aguhuice-hardening.conf` 排在 `99-qre-hardening.conf` 之前——已实测证明：只留新文件时 `permitrootlogin no` 生效，两文件并存时生效值回退为 `without-password`。因此「仅新增一个 drop-in」在物理上无法覆盖 root 登录项，只能改那一行；该文件其余两行（`PasswordAuthentication no`/`PubkeyAuthentication yes`）原样未动。
- **生效值（`sshd -T` 复核）**：`permitrootlogin no`、`passwordauthentication no`、`kbdinteractiveauthentication no`、`pubkeyauthentication yes`、`permitemptypasswords no`、`allowtcpforwarding yes`。`sshd -t` 通过后 **`systemctl reload ssh`**（非 restart），既有会话与隧道未断。
- **验证（全部实跑）**：①既有 root 隧道（pid 115776）reload 后仍 200；②**root 新连接被拒**：`Permission denied (publickey)`；③deploy 新连接 + `sudo -n`（root）+ `qre-saas active` / `qre-worker inactive` / `nginx active` / `ssh active`；④deploy 新建隧道 9092 → `/saas/new` 200、`/saas/console` 200；⑤`fail2ban-client status sshd` 经 `sudo -n` 正常；⑥已把陈旧 root 隧道换成 `admin-tunnel.sh`（deploy@）起的 9090，现网**无任何 root 会话**。
- **脚本与纪律落地**：`deploy/saas/deploy-ecs.sh`（新，可执行）——deploy+sudo 唯一部署入口：拒绝绝对路径 → scp 到 `/tmp/qre-deploy-<STAMP>/` → 远程脚本 `sudo -n install -o deploy -g deploy -m 0644` 到业务路径（先 `cp -a` 留回滚副本）→ `sudo -n systemctl restart qre-saas`（仅此单位，worker 在家不动）→ 应用层 curl 校验；带 `--dry-run`。`admin-tunnel.sh`、`pull-ecs-backup.sh` 的 `HOST` 默认值由 `root@` 改 `deploy@`；`scripts/sync_saas_metadata.py` 用法注释改为指向 `deploy-ecs.sh` 并注明禁 root。
- **deploy-ecs.sh 真实端到端已跑通**（不是只 dry-run）：用与生产 SHA256 完全相同的 `deploy/saas/metadata.json`（`29045e24…`）实跑一次，四步全过（installed → active → MainPID 493988 → api/saas/factors 200 / /saas/new 200），跑完生产文件 SHA256 仍为 `29045e24…`（字节未变）。过程中修掉两个真 bug：scp 不自建远程嵌套目录（先按相对路径 `mkdir -p`）；内联 `bash -c` 字符串被二次转义搞坏（改为生成远程脚本文件再 `sudo -n bash` 执行，路径本地展开写死）。
- **测试**：无 `src/` 改动（仅脚本与文档），无测试引用这三个脚本；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2890 passed + 6 skipped**（与基线一致，零回归）。`bash -n` 三个脚本全过；dry-run 与「拒绝绝对路径」分支均验证。
- **备份与回滚**：本地 `/tmp/qre-ssh-hardening-pre-20261027/`（`etc/ssh/sshd_config`、`etc/ssh/sshd_config.d/99-aguhuice-hardening.conf`、`etc/sudoers.d/deploy` 原样副本）。回滚两步都不断业务：①`sudo rm /etc/ssh/sshd_config.d/99-qre-hardening.conf` 并把 `99-aguhuice-hardening.conf` 的 `PermitRootLogin` 改回 `prohibit-password` → `sudo systemctl reload ssh`；②`sudo rm /etc/sudoers.d/90-qre-deploy`。云控制台救援路径见 `16_ECS_DEPLOYMENT.md` §6。
- **未做**：未 commit/push、未跑真实回测、未碰 WSL 数据库/worker/因子/UI/游戏；worker 仍 inactive 在家，无 schema 变更。

## Task ID

QRE-FACTOR-ZH-COVERAGE（剩余 341 列中文显示名维护）

## Current Status

已部署待人工验收，未 commit/push（2026-10-27；341/341 全部按真实公式维护，0 列遗留 null）

## Task Note

- 维护 Alpha191 191、Alpha101 31、quality/growth `_rank` 与少量财务字段中文名；只能依据真实公式/官方定义/明确字段语义，无法确认保留 zh=null，禁止为覆盖率伪造翻译。
- 保持 canonical、display 图表合同、别名解析与 common/core 不变；生成 registry 与 metadata 并校验。
- 跑注册表/呈现/全量测试，核查自选因子中文展示与搜索；备份后直接部署 ECS 待验收，不 commit/push，不跑真实回测，不碰游戏。

### 实施结果（2026-10-27，已部署待人工验收，未 commit/push）

- **维护 341/341 列，未维护 0 列**：alpha191 191、alpha101 31、quality 87、growth 16、`_pit_financial_panel` 14、candle 1、value 1。中文名覆盖 **554 → 895/895（100%）**，`deploy/saas/metadata.json` 902/902 项全部带 zh。
- **命名依据（全部可溯源，无一条凭感觉翻译）**：alpha191 逐条对照 `indicators_tushare/alpha191/formulas.py` 的 191 个 docstring（GTJA191 标准编号口径，DolphinDB 实现口径与 errata 注释一并核对）；alpha101 逐条对照官方 486 文档表达式表（`docs/agent/change_requests/factor_specs_p4p5p7.md` §三）；quality/growth 逐条对照 `panel_factors/quality.py` 的 `compute_all()`、`panel_factors/growth.py` 的 results 段与 `factor_specs_p1p3.md` §四/§三表达式表；`_pit_financial_panel` 为 Tushare 标准字段语义（`panel_factors/pit_panel.py` 的 FAMILIES 口径：inc=利润表/bs=资产负债表/cf=现金流量表/fi=财务指标，流量列 `_ttm` 后缀）；`cdl_doji_10_0_1` 为 `factors/candle_factors.py` 的 ta.cdl_doji 十字星形态；`etp5_rank` 与既有 `etp5`「五年盈利价格比」同源。
- **口径说明（避免误读）**：quality/growth 的 `_rank` 列是同名计算项的截面排名，统一后缀「·排名」；`gpm_q` 官方描述与 `gpm_ttm` 相同、实现取同一 TTM 口径，故中文名标为「毛利率(TTM口径)」（列名保留 q）；`ar_ap_to_revenue` 为「预收预付净额/营业收入(TTM)」（新准则后 adv_receipts 大面积 NULL，实现用 contract_liab 兜底并减去预付款项）；`npm_tsh` 按官方语义为「归母净利润/平均总股本」（官方表达式写 Equity 均值疑笔误）；`cash_profit_ratio` 为「现金利润偏离比」（(经营现金流TTM−净利润TTM)/净利润TTM）。
- **实现方式（最小侵入）**：`scripts/gen_factor_registry.py` 新增三个模块级字典 `ALPHA191_ZH`(191)/`ALPHA101_ZH`(31)/`FINANCIAL_ZH`(119) 与 `_coverage_zh(table, column)`，在 `build_registry()` 的 `if manual.get("zh")` 之后以 `elif not entry["zh"]` 挂载——**只补空、不改名**，族规则/手工条目既有中文名、别名、common/core、display 全部原样。未走 FAMILY_RULES 正则，避免污染既有族逻辑；未给 `_rank` 列新增别名（别名解析不变）。
- **零漂移核验**：重新生成前后逐字段比对（`configs/factor_registry.json`）——除 zh 外 **0 处差异**（canonical/display/aliases/common/core/params/tables/families/extra_aliases 全等），341 条全部由 null 补为中文名，**无一条覆盖既有条目**；与生产旧版（554 zh）比对同样只有 341 处 zh 差异，证明 display 合同未回归。
- **测试**：注册表/呈现/相关 10 文件 **321 passed**；全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → **2890 passed + 6 skipped**（与基线一致，零回归）。两处测试随覆盖状态更新（仍是同一契约、非放宽）：`test_no_fabricated_zh` 由「应有 null 列」改为「不得空串/不得英文列名冒充 + 覆盖须 100%」；`test_build_factor_groups_zh_falls_back_to_none_for_unregistered` 改用未注册列 `alpha999_unregistered` 验回退，并补断言 `alpha001` 已带中文名。
- **真实浏览器核查（两次）**：①本地 staging 8099（临时库 `qre_factor_display`，未跑回测）；②**生产**（SSH 隧道 9090 → ECS 8090）。两次均：`/api/saas/factors` 902/902 带 zh 且无英文列名冒充；`/saas/new` 进入「自选因子交易」→ 打开因子选择弹窗 → 三栏逐级进「Alpha191 量价因子」，因子列 30 条全部中文名（首条「量能变动与日内收益相关性（反向）」，第 14 条「5日价格变动」）；中文搜索命中（「毛利率」13 条、「十字星」1 条、「五年盈利价格比」2 条、「产权比率年度变化」2 条）；英文列名搜索仍可用；无匹配走空态；全程零 JS error。证据 `.tmp/factor-zh-coverage/`（browser_audit.py、prod_browser_audit.py、factor-picker-cols.png、factor-picker-empty.png）。
- **ECS 部署（R-DEPLOY-001）**：核对生产两文件 SHA256 与上一轮基线一致（registry `6b5187ef…`/metadata `f1e7dbad…`）并拉回本地逐字段比对（仅 341 处 zh 差异）→ 备份 `/tmp/qre-factor-zh-pre-20261027/`（configs/factor_registry.json + deploy/saas/metadata.json）→ scp 两文件并改回 deploy 属主 → **仅重启 `qre-saas`（active，新 MainPID 491196）**，`qre-worker` 保持 inactive 未触碰 → 两文件生产 SHA256 与本地逐一相等（registry `020b0874…`/metadata `29045e24…`）。generator 为开发工具，不同步生产。
- **应用层验证**：`www.aguhuice.com` 本机与 ECS 均无 DNS，故在 ECS 上以 `curl -H "Host: www.aguhuice.com" http://127.0.0.1:8090/...` 端到端：`/api/saas/factors` 902/902 带 zh（`alpha001→量能变动与日内收益相关性（反向）`、`gpm_q→毛利率(TTM口径)`、`cdl_doji_10_0_1→CDLDOJI十字星形态`、`etp5_rank→五年盈利价格比·排名` 等抽查通过）；`/saas/new` 200(103937B)、`/saas/` 200(45033B)、`/saas/help` 200(31830B)、`/saas/login` 200(27552B)。TLS 与 nginx 配置未改动。
- **未做**：未 commit/push、未跑真实回测、未碰游戏与 8092；验收不通过可恢复 `/tmp/qre-factor-zh-pre-20261027/` 两文件并重启 `qre-saas`。建议提交信息 `feat(factors): 维护剩余 341 列中文显示名`。

## Task ID

QRE-FACTOR-DISPLAY-CONTRACT（因子别名与呈现属性统一协议）

## Current Status

已部署待人工验收，未 commit/push（2026-10-27；Step 5 实现，Kimi 复核与部署收尾）

## Task Note

- 每个 canonical 已固化 `display`：`chart_type/panel_id/role/series_type/axis/precision/color/price_basis/render_order`，由 `gen_factor_registry.py` 生成并校验；旧注册表无 display 才走启发式回退。
- EMA/BOLL/overlap 必须 overlay；MACD/PPO/PVO 同参数 DIF+DEA+HIST 同副图；RSI/风险/流动性/Alpha 独立副图；panel_id 含价格口径，避免同列不同口径串键。
- `factor-layout.js`、SaaS metadata 和 symbol/replay 均消费同一合同；NL resolve 与既有 replay/Night Mode 语义保留。
- 新 `tests/test_factor_display_contract.py` 19 例 + factor_registry 40 例，合计 59 passed；全量 **2890 passed + 6 skipped**。真实 Chromium 以生产目录驱动 replay：EMA 主图、MACD 同副图、夜间切换不破坏合同、375 无横溢，证据 `.tmp/factor-display-contract/`。
- Step 5 两次 2 小时超时后由 Kimi 完成验证部署。ECS 备份 `/tmp/qre-factor-display-pre-20261027/`，仅同步运行所需文件并重启 qre-saas；未跑真实回测、未 commit/push。建议提交 `feat(factors): 统一因子呈现属性与图表合同`。

- 因子 canonical 注册表除中文名/别名外，新增 overlay/pane、panel_id、role、series_type、axis、precision、color、price_basis、render_order，作为因子数据成员，禁止页面各猜指标。
- EMA/BOLL 必须 overlay；MACD/PPO/PVO 同副图；RSI/风险/流动性/Alpha 独立副图；panel_id 含价格口径防冲突。
- `gen_factor_registry.py` 生成并校验全量 display 属性；SaaS 静态/replay/NL 共用。`factor-layout.js` 只消费属性，旧数据才启发式回退。
- 保护 replay 与 Night Mode 改动，不碰游戏；完成 Node/全量/Chromium 后直接部署 ECS 待验收，不 commit/push，不跑真实回测。

## Task ID

QRE-SAAS-NIGHT-MODE（保留原色板，仅新增夜间模式）

## Current Status

已部署待人工验收，未 commit/push（2026-10-27；用户否决全部浅色候选，Kimi 复核）

## Task Note

- 三个浅色重装修候选全部否决，8093–8095 已关闭，候选与半成品缓存已删除；现有浅色色板保持不变。
- 仅新增夜间模式：不动字体/排版/间距/布局/组件/动效/文案/数据；红涨绿跌保留，遵守 `12_UI_STYLE_GUIDE.md` 全部长期标准。
- 首帧防闪烁、localStorage、系统偏好、meta theme-color、ECharts 随主题改色；375 不横溢。
- 保护 Step 5 replay 和 Kimi 游戏改动；完成测试后直接部署 ECS 待验收，不 commit/push，不跑真实回测。

### 实施结果（2026-10-27，已部署待人工验收，未 commit/push）

- **改动 7 个产品文件**：新增 `gui/static/night-mode.css`、`gui/static/night-mode.js`；`gui/static/replay.js` 加 `QRETheme.themeChart` 挂钩；`saas/templates/base.html`（meta theme-color + 主题按钮挂载 + css/js 引入）、`login_callback.html`（首帧内联防闪 + 深色 `:root` + 按钮 `tt-btn tt-float`）、`job.html`、`symbol.html`（图表主题化挂载点）。
- **机制**：三态（未选择跟随 `prefers-color-scheme`／显式 light／显式 dark），`localStorage('qre-theme')` 持久化；`<html data-theme>` + 首帧内联脚本防 FOUC；8 个夜间 token 覆盖 bg/card/line/text/muted/accent/accent-deep/accent-soft；ECharts 背景、坐标轴、文字、tooltip、系列色随主题改，保留红绿与数据、不重算不重排。
- **刻意保留**：`#guest-note` 深色告警色（`#B4761F` / `#3D3118`）在夜间保持原样，属告警语义而非主题色。
- **测试**：新 `tests/test_saas_night_mode.py` 24 例（token 集、无旧主紫残留、模板标记、主题函数、图表配色不改数据）；专项 24 passed；相关 6 文件 148 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2871 passed + 6 skipped**（与基线一致，零回归）。
- **浏览器审计**：`138 ok / 0 FAILURES`（exit 0），覆盖 12+ 页面 × 浅/夜 × 1280/1000/375、切换、reload 持久、系统偏好、无白底岛屿、正文与按钮焦点可读、375 不横溢；截图与证据 `.tmp/night-mode/`。
- **两项审计判据修正（工具修正，非产品放宽）**：①`<details>` 关闭时 `content-visibility:hidden` 使 `getBoundingClientRect` 非零并读到过期浅色值（login 4 项失败全在折叠区）→ 先展开再断言；②job `tagChart` 是 treemap 无笛卡尔轴 → 判据改为「含笛卡尔系序列才断言轴色」，浅色轴色取 ECharts 默认 `#6E7079`。
- **ECS 部署（R-DEPLOY-001）**：5 文件与生产基线逐一 `diff` 一致（差异仅夜间模式行，aggHead 等 Step 5 成果已在生产）→ 备份 `/tmp/qre-night-mode-pre-20261027/` → scp 7 文件 → **仅重启 `qre-saas`（MainPID 487122）**，`qre-worker` 保持 inactive 未触碰 → 7 文件 SHA256 与本地逐一相等。
- **应用层验证**：生产域名 `www.aghuice.com` 在本机与 ECS 均无 DNS，本地代理 7897 对该域名 `SSL_ERROR_SYSCALL`，故改用 ECS 上 `curl -H "Host: www.aghuice.com" http://127.0.0.1:8090/...` 做端到端应用层验证（TLS/nginx 未改）：`/saas/new` 200(103937B)、`/saas/` 200(45033B)、`/saas/help` 200(31830B)、`/saas/login` 200(27552B)、`/static/night-mode.css` 200(15250B)、`/static/night-mode.js` 200(8469B)、`/saas/console` 200(68285B)；各页 css/js/按钮/meta 标记计数齐全。
- **未做**：未 commit/push、未跑真实回测；验收不通过可恢复 `/tmp/qre-night-mode-pre-20261027/` 七文件并重启 `qre-saas`。建议提交信息 `feat(saas): 新增夜间模式（浅色不变）`。

## Task ID

QRE-SAAS-REPLAY-BOUNDARIES（P2：重播边界核验与补强）

## Current Status

已部署待人工验收，未 commit/push（2026-10-27）

## Task Note

- **核验结论**：展开/收起、seek 回退、重播重置、重复初始化、markPoints 无未来事件、symbol orders 优先 + 兜底、多因子 overlay/MACD 同面板/chip 三态/动态 grid·height/接管退出/末帧与静态一致——均已实现，补 7 例回归锁定（factor-layout 零改动）。
- **修复 1（聚合计数口径）**：`replay.js` `popEvents` 头部原按事件数计「只」（symbol 页 6 笔同日买单误显示「6 只」）。新增 `aggHead`：按 `ev.sym` 去重计「只」，事件数 > 标的数时披露「（M 笔）」，明细列全部事件；`evChipText` 统一 chip 文案（qty/price 缺省不拼装、不造值）。
- **修复 2（job 事件价量）**：`lab_result._trade_points` 在 round_trips.csv 有 quantity/entry_price/exit_price 列时补足到散点（缺列不加键；仅对新 run 生效、不回填）；job.html 事件带 sym + 价量；symbol.html 事件改 sym/symbol/qty/price 字段。旧产物降级为纯标的 chip。未新增大 payload 结构、未改 worker/引擎/schema。
- **测试**：TDD RED=5 failed → GREEN；新 `tests/test_saas_replay_boundaries.py` 7 passed（replay.js/factor-layout.js 真实文件 vm 加载 + 模板函数抽取 + _trade_points 三态）；相关 6 文件 188 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2863 passed + 6 skipped**（零回归）。
- **真实 Chromium**（临时库+8099 staging，未跑回测）：10/10 零 JS error 零横溢——job「当日入场 5 只（6 笔）」+展开 6 笔价量明细+收起+seek 回退+退出重建；symbol「当日入场 1 只（6 笔）」+EMA5/MACD 面板+末帧已实现 478.00 与静态强一致；375 两视图不破版。证据 `.tmp/replay-boundaries/`。
- **ECS**：四文件与 HEAD 基线一致 → 备份 `/tmp/qre-replay-boundaries-pre-20261026/` → scp 四文件 → 仅重启 qre-saas（worker 在家未动）；无 schema 变更。公网匿名 job58：进入/空仓快进/末帧/退出零 JS error，旧数据纯标的 chip 不造值；9090 隧道 200。
- **遗留**：价量补足仅对新 run 生效；≤5 笔同日同标的仍逐笔展示（chip 含量价可区分）；事件流无虚拟滚动（既有取舍）。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-replay-boundaries-pre-20261026/` 四文件重启 qre-saas。** 建议提交 `fix(saas): 修正重播同日聚合计数并补足事件价量`。

## Task ID

QRE-SAAS-NL-A1（自然语言输入前置校验与 DeepSeek 裁判评估）

## Current Status

DONE（2026-10-26 用户验收通过，DeepSeek 裁判已部署 ECS，本次 commit/push 发布）

## Direction Change

- 删除 Jev/TypeSafe 适配和配置，复用现有 `QRE_NL_LLM_*` 与 `call_llm`，不需要也不读取新密钥。
- DeepSeek 裁判只在缓存 miss 后运行，先占既有编译配额再裁判，通过后才编译；缓存命中零裁判，拒绝也占配额，防止免费刷 token。
- 真实 DeepSeek 评估只跑不超过 12 条分层样本，不跑全量样本或真实回测。

## Task Note

- **规则层**（`gui/saas/nl_input_guard.py` 纯函数，零 IO，位于 empty 检查后、prompt/缓存/配额/LLM 前）：reject（422 `nl_input_rejected`，**不可绕过**）= <6 字符 / 无中英文字符 / 纯数字 / 乱码率≥40% / 无交易语义且 <16 字符；review（422 `nl_input_review`，**可 force 绕过**）= 缺入场（missing=entry）/ 缺出场（missing=exit）/ 无交易语义长文本；pass=其余。词表覆盖中英文常见交易词与 MACD/EMA/RSI/均线/布林/网格等指标别名；经典「MACD 金叉买入，死叉卖出」「EMA 上穿 20 日均线时买入，下穿卖出」「网格交易每跌 2% 买一格」均 pass；50 条人工标注样本规则层 50/50。
- **DeepSeek 裁判**（第二道防线，非单点；用户明确不配置 Jev，改用现有 `QRE_NL_LLM_*`）：复用 `nl_compiler.call_llm` 注入独立裁判 system prompt，严格 JSON 三分类 strategy/not_strategy/unclear（无置信度、不伪造校准结论）；fenced/prose 容错解析，异常/超时/结构错误降级规则层。strategy 维持结论；not_strategy/unclear 升级 review（不硬拒）。**只在 cache miss + 配额计数后运行；缓存命中零裁判；裁判拒绝也占配额；管理员与会员同样经过裁判（admin 仅不限配额）；force 已确认不再裁判（两条路径一致）；DB 故障回退路径同样先限流、非 force 再裁判。** 不记录策略文本、不读取/打印密钥。
- **端点**：`force=true` 仅豁免 review——reject 仍按规则层硬拒；规则层不占配额、不写缓存、不调 LLM；裁判在 cache miss + 配额后运行，拒绝也占配额、不编译不写缓存；A2/A3 缓存命中与限流语义零回归。
- **前端**：new.html `#nl-review-modal`（缺失项+合法示例+返回修改/仍要编译）+ `doNlCompile(force)`；reject 在结果区展示原因与示例（无模态）；NL 入口 h3 隐私 tip-trigger。strategy.html 重编译 `sdRecompile(force)` + 行内确认区。零新增灰色小字。
- **测试**：TDD RED→GREEN；新 `tests/test_nl_input_guard.py` 48 passed；相关 6 文件 265 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2821 passed + 6 skipped**（基线 2773+6 零回归）；3 个既有测试文件的合成输入按新行为更新为经典合法描述。证据 `.tmp/nl-input-guard/`。
- **评估资产**：`configs/nl_input_guard_samples.json`（54 条中文人工标注）+ `scripts/nl_deepseek_eval.py`（规则层全集离线 54/54；DeepSeek 裁判只跑 ≤12 条分层小样本，真实调用记录混淆/延迟/失败）。**裁判真实小样本已在 ECS 运行**：deepseek-flash、0 失败、延迟 533–1590ms、not_strategy 4/4、strategy 3/4（1 unclear→review）。
- **真实 Chromium**（临时库+8099 staging+stub LLM，未跑回测）：5/5 零 JS error 零横溢——拒绝、review 确认后 force 编译成功、直接成功、strategy 页重新编译闭环、375 不破版（含模态态）。证据 `.tmp/nl-input-guard/`（browser-evidence.json + 5 截图）。
- **主 Agent 复核 3 项 Required Fixes 已解决并重新部署**（2026-10-26）：①领域语境门槛——新增 DOMAIN_WORDS/STRONG_TRADING_WORDS 与 `_has_domain_context`：有入出场词但无股票/价格/指标/交易语境至少 review 不得 pass（修「我想买房，之后卖房」「今天买菜后卖给邻居」在无 Jev 生产直接放行）；50 条合法样本零误杀，54 条样本（含 4 条对抗）规则层 54/54。②strategy.html 重编译区增加同源隐私 tip-trigger；new.html review 模态补 role=dialog/aria-modal/aria-labelledby。③`force` 只认 JSON 布尔 true（`data.get("force") is True`），字符串 "false"/"true" 不视为确认。TDD RED=8→GREEN，guard 测试 60 passed，相关 6 文件 230 passed + 1 skipped，全量 **2833 passed + 6 skipped**；Chromium 重跑 6/6（新增对抗样本用例；截图改几何稳定后拍摄）。备份 `/tmp/qre-nl-a1-review1-pre-20261026/` 后同步四文件仅重启 qre-saas；公网两条对抗文本 422 review、force 字符串 422、合法 MACD cache_hit=true 不回归。
- **ECS**：三文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-nl-a1-pre-20261026/` → scp 四文件（app.py/nl_input_guard.py/new.html/strategy.html）→ 仅重启 qre-saas（worker 在家未动）；无 schema 变更。公网：reject/review/force/合法编译（cache_hit=true 与真实编译各一）全部符合合同，jobs 10→10，nl_compile_events 2→4；9090 隧道两页 200 且 A1 标记齐全；公网四页 200。
- **主 Agent 复核 2 个路径一致性 Required Fixes 已解决并重新部署**（2026-10-26）：①删除 admin 裁判豁免——管理员不限配额但与会员一样经过 DeepSeek 裁判（原 `not is_admin` 绕过是未经要求的新权限差异）；②DB 故障回退路径改为仅 `not force` 时裁判（原无条件裁判导致 force 用户在 DB 故障时又被拦回，与正常路径不一致）；规则硬拒仍在最前不可绕过。回归：`test_admin_also_refereed`、DB 故障 + force 跳过裁判/裁判拒绝拦截/乱码硬拒。TDD RED=2→GREEN；guard 67 passed；相关 6 文件 237 passed + 1 skipped；**全量 2840 passed + 6 skipped**；Chromium 7/7。ECS 备份 `/tmp/qre-nl-a1-deepseek-review1-pre-20261026/`（app.py）后同步仅重启 qre-saas；公网最小复核：MACD 缓存命中 200 零裁判零配额（配额 5→5）、乱码+force 仍 422、公网三页与 9090 隧道 200。
- **DeepSeek 方向变更落地**（2026-10-26，用户明确暂不配置 Jev）：删除 Jev/TypeSafe 客户端、环境变量、requests 依赖与 `scripts/nl_jev_eval.py`（无死代码）；裁判改复用 `QRE_NL_LLM_*` + `call_llm(system_prompt=…)`；编排改为「规则层 → 缓存快路径/锁内复检 → 配额 → 裁判 → 编译」，缓存命中零裁判、裁判拒绝占配额。测试 67 passed、相关 6 文件 237 passed + 1 skipped、**全量 2840 passed + 6 skipped**；Chromium 7/7（新增裁判 review 场景）；ECS 备份 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 后同步四文件仅重启 qre-saas。公网：规则拒绝/review 不占配额；非策略描述 cache miss 时 DeepSeek 裁判拦截（422 review、配额 +1、缓存不写、events 不记）；合法 MACD cache hit 零裁判；新合法描述裁判+编译两阶段成功。计数证据：jobs 10→10、cache 3→4、events 5→7、guest 配额 3→5。
- **遗留**：裁判无置信度输出、不做阈值校准结论；裁判拦截量不计入运营事件表；规则层不做语义可达性判断。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-nl-a1-deepseek-pre-20261026/` 四文件并重启 qre-saas。** 建议提交 `feat(saas): 增加自然语言输入校验与 DeepSeek 裁判`。

## Task ID

QRE-SAAS-PUBLIC-BETA-OPS（P1：公测运营反馈闭环与关键浏览器自动化）

## Current Status

DONE（2026-10-26 用户验收通过，已部署 ECS，本次 commit/push 发布）

## Task Note

- **范围铁律**：不改回测引擎、worker 执行逻辑、结果数值、配额、NL A2/A3 的限额与缓存语义；不跑真实回测；不做压测/性能/硬件；不触游戏；桌面 1280 与 375 只验证不破版，不做移动端专项；未 commit/push。
- **Schema**（`deploy/saas/cloud_schema.sql`，生产已由 postgres 幂等 apply）：`nl_compile_events`（ok/cache_hit/error_class/scope/created_at；**不存策略文本、API key、原始 IP**；自功能上线起统计）+ feedback `category`（bug/experience/factor/other，缺省 other）与 `status`（open/doing/done/closed，缺省 open）；feedback_id_seq 授权 DO 块（修生产 500，见下）。
- **9090 管理台「公测运营」tab**（`GET /api/saas/console/ops`，admin 门禁不变；窗口 today/7d/30d/all，**today 按 Asia/Shanghai 自然日**）：NL 编译次数/成功率/缓存命中率/失败原因 Top5/统计起点（事件表口径，上线前显示「—」）；回测（kind='full'；smoke 内部试算与用户主动取消不计入）成功率/平均排队/平均执行/失败原因 Top5；游客到注册转化（游客独立会话=guest_key 去重、新增注册=users.created_at，**二者无关联，不计算转化率**——ratio=null + measurement=unlinked，未提交任务的访客不可见）；反馈按类型/状态计数。分母为 0 → null → 前端「—」，不编造历史。
- **NL 编译事件记录**（app.py 四个终态）：快路径命中、锁事务内命中（同连接 + ops_ready 门）、miss 编译后（error_class=compile_nl code）、DB 回退路径补记；超限 403/429 不计入；scope 由 is_admin 提前判定同源给出。
- **反馈分类闭环（最小可用，不建工单系统）**：提交 category allowlist（400）；本人列表透出 category/status；console 筛选 ?category=&status=；`POST /api/saas/console/feedback/<id>/status`（admin；非法 400/不存在 404）；既有用户隔离、每日 20 条上限、管理员鉴权全部保留；ops 表缺失时按旧形态降级不 500。
- **测试**：TDD 先 RED（17 errors，对 HEAD 基线）后 GREEN；新 `tests/test_saas_public_beta_ops.py` 17 passed；相关 5 文件 227 passed + 1 skipped；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2770 passed + 6 skipped**（基线 2753+6 零回归）。证据 `.tmp/public-beta-ops/`。
- **主 Agent 复核 2 项 Required Fixes 已解决并重新部署**（2026-10-26）：①转化比率误导——不再计算 new_users/guest_sessions 之比（可 >100%，生产实测 300.0%）；API 返回 ratio=null + measurement=unlinked，console 卡改「转化率 —」，保留两个真实计数，**未扩展用户追踪 schema**；②today 窗口改 Asia/Shanghai 自然日（`_now_shanghai()` + zoneinfo，原 UTC 零点漏当日凌晨 8 小时）。新回归 3 例（`test_conversion_ratio_never_computed`、`test_today_start_is_shanghai_midnight`、`test_today_window_includes_shanghai_early_morning`），TDD RED=4 failed → GREEN；ops 测试 20 passed；全量 **2772 passed + 6 skipped**（1 例已知 flake 复跑通过）；Chromium 重跑 9/9 零 JS error 零横溢，`console-ops-1280/375.png` 确认无伪转化率；备份 `/tmp/qre-public-beta-ops-review1-pre-20261026/` 后仅同步 ops_support.py + console.html 并重启 qre-saas（无 schema 变更）。
- **关键浏览器自动化资产**（可重复执行）：`deploy/saas/public-beta-audit/{seed.py,browser_audit.py,run_audit.sh}`，复用 `.tmp/browser-venv` Playwright + `.tmp/ms-playwright` Chromium（仅测试工具，未进生产依赖）；场景覆盖游客/登录、新建页、NL 编译 stub、任务等待/失败恢复、结果只读与权限、反馈分类、管理台运营指标；真实 Chromium 9/9、零 JS error、零横向溢出（1280 与 375）。
- **生产缺陷热修**：`feedback_id_seq` 缺 USAGE 导致登录用户提交反馈 HTTP 500（feedback 特性此前从未部署 ECS，首次上线暴露；同 share_links 序列坑）。已生产 GRANT USAGE, SELECT；schema 增加角色存在时幂等 DO 块。
- **ECS 发布**：四文件与 HEAD 基线 SHA256 一致 → 备份 `/tmp/qre-public-beta-ops-pre-20261026/` → postgres apply → scp 五文件 → 仅重启 qre-saas（worker 在家未动）。公网：临时 admin/member 会话完成 ops 鉴权三态、空口径、反馈闭环、游客真实 DeepSeek 编译两次 cache_hit false→true（A2A3 无回归）；编译后 ops all 窗口 nl.total=2/first_event_at=2026-10-26；临时数据全部清理（temp_users=0/feedback=0）；9090 隧道 console 200 含 ops 标记、ops API 无 token 401；/saas/、login、new、feedback、help 200，/saas/console 仍 404。证据 `.tmp/public-beta-ops/production-verification.txt`。
- **未解决/遗留**：NL 指标自功能上线起统计（2026-10-26 前无历史，不回填）；游客访客口径仅覆盖提交过任务的独立会话；转化只有总量比（无跨会话关联）；反馈状态无备注字段（最小闭环）；`nl_compile_events` 无自动清理（仅索引）。**未 commit/push，待用户人工验收；不通过恢复 `/tmp/qre-public-beta-ops-pre-20261026/` 四文件并重启 qre-saas。** 建议提交 `feat(saas): 新增公测运营指标与反馈分类闭环`。

## Task ID

TRADING-GAME-V1-CORE（《我不是股神》WSL 可玩 Demo 首切片）

## Current Status

WSL 可玩 Demo 已跑通，未部署 ECS、未 commit/push（2026-10-26）

## Task Note

- 完成纯交易状态机、随机股票/窗口、匿名逐日揭盲、前复权数据、现有因子、Web API 与可玩页面；真实 Chromium 完成开盘买入，费用与 T+1 正确。
- 开盘只显示 open，收盘才显示完整 K 线与当日指标；真实代码/日期/未来数据不离开服务端。
- 复用 `core.models`、`AShareMarketProfile`、现有因子和淡紫 UI，不复制费率或回测引擎；EMA 使用库内 ema_250（库内无 ema_200）。
- 游戏专项 22 passed，全量 2753 passed + 6 skipped；1280/375 无横溢、无 JS error，证据 `.tmp/trading-game/`。本地入口 `http://127.0.0.1:8092/game`。
- 后续：补齐异常订单/结果细节、持久化与公网中继；不提前做美术、分时、财报、杠杆、扰动或 Steam。

## Current Release

DONE（2026-10-26 用户验收通过，QRE-SAAS-NL-A2A3 含管理台同步，已 commit/push + ECS）：持久限频与版本化编译缓存已发布，9090 管理台总览新增「自然语言编译」卡（限额直接读执行常量 GUEST_NL_DAILY_LIMIT/MEMBER_NL_MINUTE_LIMIT，计数读 nl_rate_limits/nl_compile_cache 真实行，R-ADMIN-001 同源）。游客每日 10 次改 PostgreSQL 原子计数（原 403/code=guest_nl_limit 不变），会员新增 6 次/分钟防突发（超限 429/code=nl_rate_limited/reset_seconds，每日仍不限），admin 不限；同输入编译结果缓存命中不再调用 LLM 也不占配额。发布前复核全量 2753 passed + 6 skipped；公网两次纯编译第一次 cache_hit=false、第二次 true 且 YAML 一致，未创建回测；公网 overview nl 字段与常量/表计数一致。以下各任务保留实施与部署过程记录。

## Task ID

QRE-SAAS-NL-A2A3（持久限频与版本化编译缓存）

## Current Status

DONE（2026-10-26 用户验收通过，已 commit/push + ECS）

## Task Note

- **Schema（deploy/saas/cloud_schema.sql，两表均无序列）**：`nl_rate_limits`（scope/subject_hash/window_start/hits/updated_at，PK (scope, subject_hash, window_start)）与 `nl_compile_cache`（cache_key PK/description/result JSONB/model/prompt_hash/cache_version/created_at/last_hit_at/hit_count + last_hit_at 索引）；按 share_links 模式在 `aguhuice` 角色存在时幂等 GRANT 两表 CRUD，本地无角色跳过。生产已由 postgres apply，两表与授权均核实。
- **新模块 gui/saas/nl_compile_support.py**：`normalize_description`（NFKC+trim+空白折叠）、`build_cache_key`（规范化描述+model+规范化 base_url+完整 build_system_prompt 哈希+`NL_COMPILER_CACHE_VERSION="2026-10-26.1"`）、`consume_quota_on`（单条 INSERT … ON CONFLICT DO UPDATE … WHERE hits<limit RETURNING，原子不突破）、cache get/store/touch、`pg_advisory_xact_lock(hashtext(key))` 同 key 防重复 LLM（不同 key 不串行）、游客 subject 复用 `_guest_key(ip)`、会员 `sha256("nl:user:"+uid+salt)` 截断不落原始 IP。
- **app.py 编排（/api/saas/nl/compile）**：快路径查缓存→同 key 咨询锁+复检→配额（admin 直接放行；游客 guest_daily=10 超限 403/code=guest_nl_limit 原文案；会员 member_minute=6 超限 429/code=nl_rate_limited+scope+reset_seconds）→compile_nl→仅 ok=true 写缓存→响应补 cache_hit。不改 gui/nl_compiler.py 编译/纠错/YAML 校验；not_configured 仍 503 且不缓存；`_guest_nl_hit` 文件计数保留为 DB 故障回退（会员 DB 故障 503 不放开）。
- **管理台同步（R-ADMIN-001）**：`api_console_overview` 新增 `nl` 对象——guest_daily/member_minute 直接读当前执行常量（改动常量即时跟随，无第二套配置）、admin=不限、cache_version、rate_limit_rows/hits 与 cache_entries/hits 读两表真实行；console.html 总览在 Worker 资源卡前新增「自然语言编译」卡（metric 卡 + tip-trigger 解释，无灰色小字）。管理员鉴权不变（匿名 401/会员 403）。
- **验证**：新 `tests/test_saas_nl_compile_cache.py` 23 passed + 1 skipped（本地无 aguhuice 角色跳过 grants 断言）；console 测试 +5（常量一致/常量改动跟随/两表计数/鉴权/页面卡）；相关 4 文件 206 passed；全量 **2731 passed + 6 skipped**（基线 2703+5 零回归）。临时 PG+8099 staging 真实 HTTP 与 Node harness 通过；公网两次纯编译第一次 cache_hit=false、第二次 true 且 YAML 逐字节一致，jobs 表 10→10 未建回测；公网 overview nl 字段与常量/表计数一致。证据 `.tmp/nl-a2a3/`、`.tmp/nl-console/`。
- **遗留/注意**：编译缓存版本覆盖 prompt 与因子目录（完整 prompt 哈希），后处理变化须手动 bump；同会员同分钟的并发编译会按配额行锁自然串行（原子计数固有属性）；缓存表无自动清理（仅 last_hit_at 索引供未来统计）。

## Task ID

QRE-SAAS-SHARE-ABSOLUTE-URL（分享链接补全公网域名）

## Current Status

已部署待人工复验，未 commit/push（2026-10-26）

## Task Note

- **核查**：用户提供的链接实际在服务端和前端均有效（summary 200、readonly_kind=share、真实 Chromium 完整只读渲染），但创建响应只返回 `/saas/jobs/...` 相对路径，不能直接作为外部分享 URL。
- **修复**：`api_share_link_create` 改为 `SAAS_PUBLIC_BASE_URL`（缺省回退 `request.url_root`）+ 任务分享路径；生产配置固定 `SAAS_PUBLIC_BASE_URL=https://www.aguhuice.com`，避免反代协议/Host 漂移。既有相对链接无需撤销，仍可使用。
- **验证**：新增绝对 URL 回归，access_hardening 68 passed；全量 **2703 passed + 5 skipped**。生产真实创建返回完整 `https://www.aguhuice.com/saas/jobs/78?share=...`，公开页面 200，撤销 200；临时链接/session 清理，app.py 哈希一致。备份 `/tmp/qre-share-absolute-url-pre-20261026/`（含 app.py 与 0600 env 备份），未跑真实回测。

## Task ID

QRE-SAAS-SHARE-SEQUENCE-GRANT（分享创建 HTTP 500 权限热修）

## Current Status

已部署待人工复验，未 commit/push（2026-10-26）

## Task Note

- **根因**：生产 `share_links` 由 postgres 建表，应用角色 `aguhuice` 虽有表 CRUD 权限，但缺少 `share_links_id_seq` 的 USAGE，真实 POST `/api/saas/jobs/78/share-links` 因此连续 HTTP 500。此前直接 SQL 插入验证未覆盖应用角色序列权限。
- **修复**：生产执行 `GRANT USAGE, SELECT ON SEQUENCE share_links_id_seq TO aguhuice`；`cloud_schema.sql` 增加角色存在时幂等 GRANT（表 CRUD + 序列），避免下次部署复发。
- **附带 schema 完整性**：全量测试暴露新临时库 `showcase` 懒建表时序问题，将既有 `showcase`/`showcase_daily` 同构定义纳入权威 schema；生产仅 IF NOT EXISTS 跳过，不改业务行为。
- **验证**：新增授权回归后 access_hardening 67 passed、相关 88 passed，最终全量 **2702 passed + 5 skipped**。生产用临时 session 调真实创建/撤销 API 均 HTTP 200，临时链接/session 清理，share_links=0；schema SHA256 一致，showcase/showcase_daily 存在且序列 USAGE=true。备份 `/tmp/qre-share-sequence-grant-pre-20261026/`。未跑真实回测，未 commit/push。

## Task ID

QRE-SAAS-CLASSIC-ACTIONS-UI（经典策略按钮与结果操作卡精修）

## Current Status

已部署待人工验收，未 commit/push（2026-10-26；R-DEPLOY-001 直接部署 ECS，用户人工验收通过后才提交）

## Task Note

- **经典策略页（showcase.html）**：页头第二行 `.opt` 只读/更新/风险备注删除，信息移入 H1 旁 `tip-trigger`（`data-tip="只读展示 · 数据每日收盘后更新 · 过往表现不构成投资建议。"`），主描述保留；表格下 `#sc-hint` 元素与 JS 赋值删除（行进详情已有实际交互）；底部「如何复现这些策略？」灰字长文卡改为精简 CTA——标题「复现经典策略」+ 问号提示（自然语言/自选因子可复现）+ `btn btn-primary`「新建同款策略」（链接仍 `/saas/new`）。策略自身 subtitle 是内容，保留不动。
- **结果操作卡（job.html）**：`#box-actions` 与 `#box-share` 合并进外层 `chart-box hidden#result-actions-card`，标题「结果操作」+ 问号提示；两组改为内部 `result-action-group`，hidden 仍由各自初始化函数控制。`btn-save-lib`/`btn-signal-confirm` 升主按钮（移除 confirm 内联紫色），`btn-signal-open`/`btn-share` 为次按钮；`action-status`/`share-status` 改 `result-action-status` 正常可读状态文本。信号面板「T+1 参考/风险提示」灰字段落移入「扫描范围」标签旁问号提示；radio/select/ID/scope 值不变。新增空安全 `syncResultActionCard()`：任一组非 hidden 才显示外层，两组皆 hidden 则整体隐藏；`initResultActions()`/`initShareButton()` 每个显示/隐藏分支结束后调用；readonly 分支隐藏清单加入 `result-actions-card`。保存/信号/分享 API、状态回填、权限与事件绑定不变，不重复绑定（`actionsBound`/`shareBound` guard 保留）。
- **样式（lab-theme.css）**：仅追加局部规则 `.result-action-group`/`.result-action-buttons`/`.result-action-status`/`.result-action-scope`/`.showcase-cta`，按钮 min-height 44px、gap 10px、inline-flex 居中；≤768px CTA 纵排全宽、操作按钮自适应居中；无新色相、无灰色小字备注样式、不动全站 `.btn-sm`。
- **测试**（TDD 先 RED 后 GREEN，证据 `.tmp/classic-actions-ui/`）：RED=新文件 11 失败 + `test_saas_access_hardening.py` 2 失败（只读隐藏清单 marker 与 readonly harness）；GREEN=新 `tests/test_saas_classic_actions_ui.py` 12 例（静态断言：CTA/删除标记/原 ID 与契约/按钮层级/改动区域无 `.opt`/`syncResultActionCard` 分支调用/只读清单/CSS 局部规则；Node 可见性矩阵：保存+信号+分享、仅分享、游客、只读四形态 + 连续初始化与失败重试不重复绑定 + 空安全）；更新 3 处既有断言（access_hardening 只读清单字符串/known/循环 + share harness 的 sync 透传桩；`test_gui_saas_pages.py` 的 `if (jobData.readonly)` marker）。相关 10 文件 289 passed + access_hardening 66 passed；**全量 `.venv/bin/pytest tests/ --ignore=tests/data_test -q` → 2701 passed + 5 skipped**（基线 2689+5，零回归）。
- **真实 Chromium**（`.tmp/browser-venv` + chromium，临时库 `qre_readonly_share_browser` + 8099 临时 staging，seed/worker 协议模拟 completed，未启动真实 worker、未跑真实回测）：9/9 通过、零 JS error、零横向溢出——showcase CTA（删除标记为零、主按钮 44px、两个问号 hover 完整说明）；登录结果页三操作按钮层级（44px×4）、信号面板三 scope radio 与 sector 二级行、confirm 端到端开启监控、分享模态打开/取消；375px 登录态 job/showcase 零横溢、按钮 44px；游客任务页与 showcase 只读（匿名）均整体隐藏结果操作卡。截图 7 张已复核，证据 `.tmp/classic-actions-ui/`（browser-evidence.json、red/green-evidence.txt、public-verification.txt）。
- **发布**：核对 ECS 三文件与本地 HEAD 基线 SHA256 一致后，备份 `/tmp/qre-classic-actions-pre-20261026/`，scp 同步 `showcase.html`、`job.html`、`lab-theme.css`，仅重启 qre-saas（worker 未动）。公网验证：showcase 200 含「新建同款策略」主按钮与两个提示、删除标记为零、全页仅剩 subtitle 一处 `.opt`；job58 200 含 `result-actions-card`/`syncResultActionCard`/新按钮类与只读隐藏清单；`/static/lab-theme.css` 200 且 SHA256 与本地一致（`ffcc286b…`）；`/saas/`、`/saas/help`、`/saas/login`、`/saas/new`、symbols 两页均 200。未跑真实回测。**未 commit/push，待用户人工验收**；不通过则恢复 `/tmp/qre-classic-actions-pre-20261026/` 并重启 qre-saas。建议提交信息（仅验收通过后使用）：`refactor(saas): 精修经典策略与结果操作按钮`。

## Archive: QRE-SAAS-UI-DECLUTTER-001（结果页口径展示与说明页导航精简）

## Current Status

DONE（2026-10-26 用户批准提交并部署；实现 `8accb66` 已 push + ECS，未跑真实回测）

## Task Note

- **三处口径标签隐藏**：job 结果页 `#box-contract` 及其徽标/版本说明删除；showcase 顶部与每行的验证徽标/合同版本删除；个人回测记录 `contractBadge` 删除。`result_contract` API、历史分类、showcase verified 公开门槛和内部分享权限不变。
- **重复说明入口删除**：job 的基准/费用/风险/归因及 symbol 的收益/费用/风险/数据截止处 `/saas/help#...` 链接全部移除；现有 `tip-trigger` 悬停说明保留，`renderContract` 仅继续驱动曲线口径提示。
- **使用说明改版**：桌面为 190px sticky 侧边栏目，七锚点不变，卡片 h2 增至 20px；≤760px 转为静态顶部双列导航。帮助页删除验证状态/新旧口径文案，改「收益口径与数据截止」。
- **验证**：TDD RED=9 项；相关 138 passed；全量 **2689 passed + 5 skipped**。真实 Chromium 6/6（job/symbol/showcase/profile/help 桌面 + help 375），零 JS error、零横向溢出，截图已复核，证据 `.tmp/ui-declutter/`。临时 staging 与临时库已清理。
- **发布**：实现 `8accb66` 已 push。ECS 备份 `/tmp/qre-ui-declutter-pre-20261026/` 后同步六个前端文件并仅重启 qre-saas；公网 job58/symbol58/showcase/profile/help 均 200，删除标记为零，help 侧栏与 20px 标题生效，六文件 SHA256 与 HEAD 一致。纯模板/CSS/测试改动，无 API/schema/引擎/worker/数值/权限改动，未跑真实回测。下一项回归主线：经典策略按钮与结果操作卡 UI 精修。

## Archive: QRE-SAAS-RESULT-UNDERSTANDING（P1 第二切片：结果理解、集中帮助与数据/费用口径）

## Current Status

DONE（2026-10-25 用户批准提交并部署；实现 `9fd3b3d` 已发布，未跑真实回测）

## Task Note

- **范围**：P1 结果理解切片。不改 schema/引擎/worker 执行逻辑/结果数值/配额/NL A2/A3；不跑真实回测；不做压测/性能/硬件。详细设计与实现见 `08_IMPLEMENTATION_BRIEF.md` 与 `09_CODING_HANDOFF.md`，自审见 `10_REVIEW_REPORT.md`。
- **新增公开帮助页**：`GET /saas/help` + `help.html`（七锚点，合同文案同源）；主导航「使用说明」。job/symbol 模块「说明 →」精准深链，主指标卡保持 6 张。
- **口径提示**：五类磨损卡、毛/净收益、费率、基准和重播指标复用 `LabUI.helpTips`；symbol 两条 API 路径注入 `data_until`，VaR/ES 统一损失正数呈现。
- **复核修正**：个股 worker 回传分支只显示 `other_cost`，不再把已包含其中的 transfer_fee 再加一次；本地 fallback 保持订单拆分口径，费用原值与总磨损不变。
- **验证**：全量 2653 passed + 5 skipped；真实 Chromium 10/10，零 JS error、零横溢；移动 375 导航单行，证据 `.tmp/result-understanding/`。
- **发布**：实现 `9fd3b3d` 已 push。ECS 备份 `/tmp/qre-result-understanding-pre-20261025/` 后同步 app.py、base.html、job.html、symbol.html、help.html、replay.js、lab-theme.css 并重启 qre-saas；公网 `/saas/help` 200、七锚点齐全、job 帮助链接生效、58 个股详情返回 data_until=2026-10-09、74 匿名 401，文件 SHA256 与仓库一致。生产证据 `.tmp/result-understanding-production/`。下一阶段：移动端与可访问性；压测与硬件继续暂停。

## Task ID

QRE-SAAS-READONLY-SHARE（P1：默认私有的可撤销只读分享）

## Current Status

DONE（2026-10-26 用户批准提交、推送与 ECS；实现 `08b4a27` 已发布，未跑真实回测）

## Task Note

- **范围铁律**：严格按批准计划实施；不改回测引擎/worker 执行逻辑/结果数值/配额/NL A2/A3；未跑真实回测；未做压测/性能/硬件；未做移动/App 专项（仅 375 验证不破版）。移动端/App 挂起决策（06 同日条目）保留不动。
- **Schema**：`deploy/saas/cloud_schema.sql` 新增 `share_links`（token_hash 唯一 64 位哈希 / job_id ON DELETE CASCADE / owner_id / expires_at / revoked_at / created_at + 两个索引），无明文/前缀/guest_key/last_used；应用层 `_ensure_share_links` information_schema + 进程 guard 懒自愈，CREATE 失败按「分享不可用」安全降级；生产已由 postgres 幂等 apply，表 owner=postgres。
- **令牌**：`secrets.token_urlsafe(32)`；库中只存完整 `sha256("share:"+token+SAAS_AUTH_SALT)`；明文只在创建响应出现一次；创建 URL `/saas/jobs/<job_id>?share=<token>`；校验只允许未撤销、未过期且 job 一致的记录。
- **API**：`POST /api/saas/jobs/<id>/share-links`（登录+本人+completed；游客 401、他人/不存在 404、未完成 409；有效期只接受 1/7/30/0 天，默认 7）；`GET /api/saas/share-links`（仅本人最近 50 条，不回 hash/token）；`POST /api/saas/share-links/<id>/revoke`（仅创建者，重复/他人/不存在统一 404，立即失效）。
- **公开只读通道**：`_require_completed_result` 识别有效 `?share=` 绑定单 job 放行（`readonly_kind="share"`），不依赖登录/游客会话；无效/过期/撤销/错 job 不降级（匿名 401、登录他人 404，错误体与不存在逐字节一致），也不得回退 showcase；范围仅现有结果 GET，不开放 jobs/results 列表、策略/worker/console；generate 对 share/showcase 都 403；写端点仍按原归属。
- **未验证与 showcase**：未验证结果允许 owner 主动分享且合同徽标「旧口径·未验证」原样保留；showcase verified 门不变；游客不能创建分享。
- **前端**：job.html 登录+completed+非只读显示「分享结果」（自定义模态选有效期、只读 input+复制、只显示一次、不写 localStorage）；分享视图 chip「只读分享」+「← 返回首页」，showcase 仍「经典策略展示 · 只读」+「← 返回经典策略」；取消/保存/信号/下载/游客引导全部隐藏；profile「我的分享」列表与撤销二次确认；symbols/symbol 页 token 随 API 与导航传播。
- **验证**：TDD 先 RED 后 GREEN；最终全量 **2688 passed + 5 skipped**；真实 Chromium 12/12 零 JS error、零横溢，证据 `.tmp/readonly-share/`。
- **生产发布**：实现 `08b4a27` 已 push。ECS 备份 `/tmp/qre-readonly-share-pre-20261026/`，postgres apply schema 后同步六个文件并仅重启 qre-saas。公网用 job74 验证有效分享 200/readonly_kind=share、撤销 401；用 job58 复核显式无效或撤销分享参数不得回退 showcase（401），无参数 showcase 仍 200。临时链接已删除，share_links=0，未跑真实回测。下一项：经典策略按钮与结果操作卡 UI 精修。

## Archive: QRE-SAAS-FIRST-SUCCESS-UX-001（P1 首切片：等待状态、离线提示与失败恢复）

## Current Status

DONE（2026-10-25 用户批准 commit + push + ECS；实现 `a84a9a3` 已发布，未跑真实回测）

## Task Note

- **范围**：P1 首次成功路径首切片。不改 schema/引擎/worker 执行逻辑/结果数值/配额/NL A2/A3；不跑真实回测；不做压测/性能/硬件。详细设计与实现见 `08_IMPLEMENTATION_BRIEF.md` 与 `09_CODING_HANDOFF.md`（同名前新节），自审见 `10_REVIEW_REPORT.md`。
- **后端**：`app.py` 新增 `_queue_position`/`_worker_online`/`_job_runtime_fields` 单一只读口径；GET job 补 `worker_online`；summary 409 增补 queue_position/worker_online/strategy_id/error_class/error_message/cancel_requested（failed 返回真实原因）；取消端点接入 P0-2 游客会话归属（同会话可取消、异会话/无 Cookie 401、登录他人 404、终态 409）。
- **前端**：new.html 等待态文案 + AbortError 续轮 + PollTimeoutError 独立超时 + createJob 15s 超时；job.html 队列/离线/取消（自定义模态二次确认）/failed 恢复（登录用户 `/saas/new?strategy=<id>`、游客返回新建页、showcase 只读零入口）；wait-mask aria-live=polite + `.wm-meta` 秒数行（纯视觉）。
- **验证**：主 Agent 复跑聚焦 115 passed；全量 2629 passed + 5 skipped；真实 Chromium 12/12（临时库 + 8099 staging，seed/协议模拟，零 JS error、零横溢、375 取消钮 44px），证据 `.tmp/first-success-ux/`。
- **发布**：实现 `a84a9a3` 已 push。ECS 备份 `/tmp/qre-first-success-ux-pre-20261025/` 后仅同步 app.py、new.html、job.html、wait-mask.js、lab-theme.css 并重启 qre-saas；公网五个文件 SHA256 与仓库一致，页面包含新运行态/取消/恢复标记，58 verified 200、74 匿名 401、Authing 302。生产证据 `.tmp/first-success-ux-production/`。下一阶段进入结果理解与集中帮助；压测与硬件继续暂停。

## Archive: QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Task ID

QRE-SAAS-ACCESS-HARDENING-001（P0-2 测试账号、结果 IDOR 与游客归属）

## Current Status

DONE（2026-10-25 用户批准 commit + push + ECS；实现 `0799890` 已发布，未跑真实回测）

发布记录：全量复跑 2590 passed + 5 skipped。ECS 仅同步 app.py 与 cloud_schema.sql 注释并重启 qre-saas；公网双独立游客 Cookie 均为 43 位随机值且 Secure/HttpOnly/Lax，私有 74 匿名 401、verified 58 匿名 200、showcase 仅 58/66、Authing 302。备份 `/tmp/qre-access-hardening-pre-20261025-release/`，生产证据 `.tmp/access-hardening-production/`。

## Task Note

- **ECS 测试账号已移除**（brief 目标 1）：只读核查确认存在（活跃键、值非空、移除前 bypass 实测 200、users 表 1 行遗留）；备份 `/etc/qre-saas.env.bak-access-hardening-20261025-173458`（0600）后注释两键并 restart qre-saas（active）。正式登录验证：登录页 200、Authing 302→demo.authing.cn、callback 假 code 400、me 401、测试账号正确密码 401（bypass 失效）、worker token 401、游客越权 400、showcase 200。env 另增 `SAAS_GUEST_COOKIE_SECURE=1`（下次重启生效）。全程未输出凭证。
- **IDOR 矩阵**（目标 2）：`tests/test_saas_access_hardening.py` 31 例覆盖匿名 401 / 其他用户 404 / 本人 200 / 不存在（错误体与他人一致，不泄露存在性）/ showcase verified 公开只读 200 / 未验证白名单 401-404；写表面 delete 与 showcase generate 403 锁定。
- **游客归属 = 随机会话 Cookie**（目标 3）：`qre_guest_sid`（随机 43 位、HttpOnly、SameSite=Lax、30 天、Secure 可配），归属键 sha256("gsess:"+sid+salt)[:32] 同形同列无 schema 变更；`_guest_identity` 缺失才签发（绝不轮换）；接入 POST /api/jobs、GET /api/jobs/<id>、`_require_completed_result`（8 结果端点）、DELETE /api/results/<id>；游客 NL 限流仍按 IP。
- **历史迁移语义**（目标 4）：旧 IP 归属结果只在同一 IP 的**新会话首次创建任务**时一次性迁移（先迁移后计数，今日旧任务占当日配额）；只读不迁移；第二个同 IP 新会话见空档 401；迁移后旧 key 不归属也不可访问；新会话彼此隔离。
- **不变式**：默认私有、Authing、worker token、结果合同、showcase verified、409/404 语义不变；主动分享不做（P1）。
- **验证**：相关 329 passed；全量 2590 passed + 5 skipped；真实 Chromium 三上下文同 IP 双游客隔离 + 迁移可见 + 移动 375，证据 `.tmp/access-hardening/`。
- **剩余人工验收**：真人 Authing 登录由用户实机确认；users 表遗留测试账号行（无密码哈希）未删除，不影响密码登录关闭与本次权限加固结论。下一阶段按用户最新范围进入 P1 首次成功路径，不做压测或硬件推进。

## Archive: QRE-SAAS-RESULT-CONTRACT-001（P0-1B 结果合同版本、口径标签与旧结果隔离）

## Current Status

DONE（2026-10-25 用户接受未验证隔离规则并批准 commit + push + ECS 部署）

## Task Note

- **新结果带 `result_contract`**：版本 `2026-10-25.1`、`data_until`、两种收益口径
  （曲线=日收益累乘交集口径剔注入；总收益=初始资金加权 Σfinal/Σinitial−1）、
  验证状态。注入点在 worker 回传接收层（`api_result_meta` / `api_report_result_legacy`），
  worker 与引擎零改动。
- **历史不删不改**：`results.result_contract` 可空；历史行零 UPDATE，分类由
  `LEGACY_RESULT_CONTRACTS` 显式例外表决定——58/66 verified（2026-10-19 修正后人工复核）、
  74 unverified（price_basis 通过≠收益口径已验证）、其余历史默认未验证。
  分类函数不接受时间入参（签名被测试锁死），不存在按当前日期动态猜新旧。
- **公开展示**：`/api/saas/showcase` 与 showcase 公开只读通道只放行 verified；
  74 从公开可见消失，但 showcase 白名单行、job、产物全部保留，管理台
  `/api/saas/console/showcase` 仍可见并带未验证原因；属主本人照旧可见自己的 74。
- **权限语义不变**：默认私有、游客 guest_key 归属、X-User-Id dev 后门、
  `_require_completed_result` 的 401/404/409 分支均未改（未验证项对匿名/他人返回与
  未挂白名单相同的响应，不泄露存在性）。
- **页面**：`job.html` 合同徽标（已验证口径=绿 / 旧口径·未验证=红）+ data-tip 两种口径 +
  合同版本与数据截止；`showcase.html` 页头与每行已验证徽标；`_records_scripts.html`
  记录行合同标签。复用现有 badge/tip 组件，无新色相、无新 CSS。
- **验证**：TDD 先 RED 后 GREEN（21 例新文件 + 2 例 JS harness）；相关 180 passed + 1 skipped；
  全量 2559 passed + 5 skipped；真实 Chromium 桌面 1280 / 移动 375 各 3 页通过，
  零 JS error、零横向溢出。证据与详细报告 `.tmp/result-contract/`。
- **发布**：未 commit/push/部署。ECS 需 DBA apply `deploy/saas/cloud_schema.sql`
  的 `results.result_contract` 列；worker 不改不动。

---

# Task Handoff

## Task ID

QRE-SAAS-PARAMETER-TIPS-001（回测参数口径与单位提示）

## Current Status

DONE（2026-10-25 用户批准通过，允许本地 commit + ECS 部署，不 push）

## Task Note

- 新增版本化注册表 `configs/factor_registry.json`（895 个因子字段条目 + market_fields +
  tables + families + extra_aliases）与只读加载层
  `src/quant_research_engine/gui/factor_registry.py`（`normalize_alias` /
  `FactorRegistry.resolve` / `validate_registry` / `coverage_report`）。生成器
  `scripts/gen_factor_registry.py` 采用「规则生成 + 特殊人工维护」：FAMILY_RULES 按列名
  规律生成中文名/参数/别名，MANUAL_ENTRIES 人工补全财务与中文习惯名；未维护条目的 `zh`
  为 null（**不伪造中文名**），展示回退 canonical 并进入覆盖报告。
- canonical `schema.table.column`、YAML、回测、隐藏 select、条件快照、策略还原全部零改动。
  `/api/saas/factors` 只增字段（`zh`/`canonical`/`price_basis`/`aliases`），旧数据缺字段时
  前端回退既有 label。
- 消歧规则：完整 canonical 精确命中 → 归一化别名唯一命中 → family+params 结构化匹配 →
  同名多价格口径默认 close 并 notice（显式 typical_price/average_price 可选）→ 其他歧义
  返回 candidates 不猜。MACD 三输出（DIF=macd / DEA·信号线=macds / 柱=macdh）不混淆。
- 弹窗（`new.html`）按钮/三栏/搜索结果中文名为主 + 价格口径可见 + canonical 悬停对照；
  搜索匹配中文名、canonical、列名、全部别名与大类/子类。LLM Prompt 只保留 canonical
  目录与 25 条核心示例，**不注入全量别名**。
- 文件：`configs/factor_registry.json`（新增）、`gui/factor_registry.py`（新增）、
  `scripts/gen_factor_registry.py`（新增）、`gui/factor_wizard.py`、
  `gui/factor_catalog_llm.py`、`gui/factor_correction.py`、`gui/saas/templates/new.html`、
  `scripts/sync_saas_metadata.py`、`scripts/gen_factor_catalog_llm.py`、
  `deploy/saas/metadata.json`（重新导出）；测试 `tests/test_factor_registry.py`（新增 40 项）、
  `tests/test_gui_factor_wizard.py`、`tests/test_saas_factor_picker.py`、
  `tests/test_gui_saas_pages.py`、`tests/test_gui_factor_correction.py`、
  `tests/test_nl_factor_pipeline.py`。
- 验证：注册表 40 passed；向导 38；弹窗 13；saas pages 74；纠错+NL+编译器+注册表 95 passed；
  全量 `pytest tests/ --ignore=tests/data_test` → **2533 passed, 5 skipped**。
  `gen_factor_catalog_llm.py` / `sync_saas_metadata.py` 均报告「注册表校验通过」。
  真实 Chromium 8091 桌面 1280×900 与移动 375×812 各 13 项通过（中文按钮/三栏/搜索、
  中文别名、英文别名、canonical 搜索、同名 close/典型价可区分、未注册回退、YAML 一致、
  固定值、Esc、零 JS error、零横向溢出）；证据 `.tmp/factor-registry/`。
- 覆盖统计：554/895 列有中文名（61.9%）；341 列未维护（Alpha191 191 + Alpha101 31 +
  质量/成长 `_rank` 族 + 少量财务报告期字段），展示回退 canonical。
- 边界：未运行真实全量回测；未调用真实 LLM（stub http_post + 内存 column_lookup）；
  未 commit、未 push、未部署 ECS。

---

---

## Task ID

QRE-SAAS-FACTOR-PICKER-MODAL（自选因子三栏弹窗选择器）

## Current Status

DONE（2026-10-25 用户认可完成度并批准 commit + push）

## Task Note

- 交互：每个因子位置由三个堆叠下拉改为「当前因子选择按钮 + 三栏弹窗 + 搜索」。按钮显示
  「大类 / 子类 / 因子」，未选时显示「选择因子」；点击父级只更新下级，点最终因子回填并关闭；
  搜索匹配 label/value/group/sub 并展示完整层级；支持关闭按钮、Esc、点遮罩、Tab 焦点锁，
  打开后焦点进搜索、关闭后焦点回原按钮。
- 数据契约：`.wz-left`/`.wz-rfield` select 降级为隐藏数据字段（`.factor-picker-field
  select{display:none}`），仍是唯一值来源；`readGroup()`、`snapshotWzArea()`、`usedFactors()`、
  YAML 预览、固定值切换、策略还原、price basis 归一全部零改动。弹窗复用 `FACTOR_OPTIONS`、
  `factorGroups()`、`factorSubs()` 与既有目录加载结果，不新增 API、不加依赖。
- 文件：`gui/saas/templates/new.html`（弹窗结构 + `openFactorPicker`/`closeFactorPicker`/
  `syncFactorPickerButton`/`fpRender`/`fpPick`/`fpList`）、`gui/static/lab-theme.css`
  （`.factor-select-btn` / `.fp-*` 族 + 768px 移动端降级）、`tests/test_saas_factor_picker.py`
  （新增 10 项）、`tests/test_gui_saas_pages.py`（新增 `TestFactorPickerModal` 2 项）。
- 验证：目标测试 10 passed；与 saas pages 合计 83 passed；相关 SaaS 回归 242 passed；
  全量 2474 passed + 5 skipped。真实 Chromium 8091 桌面 1280 与移动 375 共 64/64 项通过
  （左右因子三级选择、搜索/清空/空态、连续三次开关、Esc/遮罩/关闭按钮、焦点返回、Tab 焦点锁、
  按钮与 YAML 一致、固定值、条件增删、AND/OR、无 JS error、无横向溢出）；
  截图与结果 `.tmp/factor-picker-modal/`。
- 部署：仅同步 `new.html` 与 `lab-theme.css` 两个生产文件并重启 `qre-saas`（未重启 worker，
  未部署测试/文档）。覆盖前备份 `/tmp/qre-factor-picker-pre-20261025-124220/{new.html,lab-theme.css}`；
  ECS 上两文件 SHA256 与本地一致（new.html `fd844541…`、lab-theme.css `1ff80af8…`），
  公网 `/saas/new` 200 且含全部弹窗标记，公网 CSS 与本地逐字节一致。
- ECS 既有未提交改动：11 个 SaaS 模板/静态文件与本地 HEAD 逐字节一致（上一任务
  help-copy 部署遗留，与本任务无关），无覆盖风险。
- 边界：未运行真实全量回测，未 commit、未 push；等用户实机验收。

---

---

## Archive: QRE-SAAS-JOB-STRATEGY-CARD（SaaS 回测详情页「策略信息」折叠卡）

## Current Status

DONE (implementation；**未 commit**——改动留工作区待批准；全量 2388 passed + 4 skipped 零回归)

## Task Note

- 数据链路：`gui/saas/app.py` `_load_job_for_user`/`_load_job_for_guest` SELECT 提取公共
  `_STRATEGY_COLS`（追加 s.entry_mode/nl_text/wizard_state/created_at）；`GET /api/results/<id>/summary`
  响应新增 `strategy` 对象（name/entry_mode/nl_text/wizard_state/yaml/created_at）。
  strategies 表列早已齐备（CR-2026-10-04），NL 原文 = nl_text 列，**无 schema 变更、无遗留缺口**。
- 模板：`gui/saas/templates/job.html` 结果区顶部新增 `#box-strategy`——`.sec-toggle`+`.sec-body`
  默认折叠；摘要行 = 策略名 + 入口类型（自然语言描述/快速向导/策略代码，存量回退+未知兜底）+
  创建时间（LabUI.fmtLocalTime）；展开按入口分态（NL 原文+YAML / 向导条件组可读描述+YAML /
  YAML 原文），YAML 走既有 `pre.compiled-yaml.pv` 深色块+行号+简高亮，零新色相/字体。
- 权限：会员本人/游客同 IP 既有语义不变，策略内容本就属任务所有者可见范畴，无新增泄露面。
- 测试：tests/test_gui_saas.py test_detail_endpoints 补断言 + 新增 test_detail_strategy_info_modes；
  目标 94 passed；全量 2388 passed + 4 skipped。
- 未做：8081 lab_result.html 未同步（任务书标注非必须）；ECS 部署仅需发代码重启（无 DB 迁移）。

---

## Archive: QRE-CUMRET-CHART（收益曲线口径修复：chart_data 新增 cumret 键 + job#58/#66 ECS jsonb 补丁）

## Current Status
---

## Archive: QRE-BATCH-IPO-INJECTION（batch 全市场净值曲线「新股初始资金注入计为收益」聚合 bug 修复）

## Current Status

DONE (implementation; **未 commit**——改动留工作区待批准；
tests/test_full_market_report.py +3（TestBatchEquityCurveIpoInjection），全量 2368 passed + 4 skipped 零回归)

## Task Note

- 根因：`build_full_market_equity_curve` batch 分支逐日直接求和各股 total_equity，
  2010 后 IPO 股票首日带完整 initial_cash（10 万）进入总和，被 daily_return/total_return
  计为收益。job#66：曲线 +220.3% vs 真实 Σfinal/Σinitial−1=−14.76%（与 profit_factor 0.90 勾稽）。
  此 bug 同时解释 job#58/#66 正反策略「双盈利」假象；修复前历史 batch 全量回测总收益率/收益日历均不可信。
- 修法：①batch 分支重写为交集口径 daily_return（昨日∩今日在市股票，注入视为外部现金流）
  + 向量化；②risk.summarize_equity_curve 优先用曲线自带 daily_return/cumulative_return 列
  （shared/个股曲线数值不变）；③strategy_total_return 改 `_aggregate_batch_total_return`
  （Σfinal/Σinitial−1，缺列回退曲线口径）；buy_hold_return 系 per-symbol 均值不受注入影响，不动；
  shared_cash 分支不动；前端直读 equity_curve.csv 无需改。
- 验证：新增 3 例回归（进入日收益不含注入、聚合口径手工复算一致、缺列回退）；全量测试零回归；
  job#66 真实产物离线复核（/tmp/verify_job66_injection_fix.py）：新口径 −14.756% 精确命中，
  修正后日收益 ±0.4% 量级（旧 ±25% 注入尖峰消失）。详见 05_PROGRESS 2026-10-19 条与 06 决策日志同日条。

---

## Archive: QRE-PARAM-PASSTHROUGH（SaaS 高级参数落库与引擎生效一致性修复）

## Current Status

DONE (implementation; **未 commit**——改动留工作区待批准；
tests/test_gui_engine.py +2 / tests/test_worker.py +2，全量 2365 passed + 4 skipped 零回归)

## Task Note

- 核查结论：费率类高级参数（佣金率/最低佣金/印花税/滑点）经 params.profile_overrides
  全链透传且与 ECS 实证一致（job 59-71 落库==worker run 记录；job 62 产物费用非零吻合手算）；
  历史「费用为 0」系 C5 params_json 事故（已修有回归）。
- 实证残留根因：max_holding_days 只落库不透传——worker/runner.py 未传、run_backtest 无形参，
  引擎只读 YAML holding 节；前端仅 YAML 缺键时注入。ECS job 65/66：落库 0（不限）但 YAML=60，
  引擎实跑 60 天。
- 修法：params 为权威来源——engine.py 新增 max_holding_days 形参 + `_override_holding_days`
  （None=不动 YAML，0=不限）；runner 透传（含 0）；8081 /api/run + run_detail.html 重跑链同步；
  saas new.html 留空落库 0 对齐「留空=不限」占位符。
- 验证：新增 4 测试全绿；ECS 库抽查 + 本地 worker run 记录比对完成（详见 05_PROGRESS）。

---

## Archive: QRE-P8-PANEL-DAILY（panel_factors 全体系日更接线：P0-P3/P4/P5/P7/通道B 接入 panel-factors-daily.timer + 8080 纳管）

## Current Status

DONE (implementation; **未 commit**——两仓库改动留工作区待批准；
indicators: tests/test_panel_factors_daily.py 等 24 passed；
QRE: test_gui_admin* 等 146 passed)

## Task Note

- indicators_tushare：新 `scripts/panel_factors_daily.py`（watermark 幂等增量编排，
  8 步串行子进程：pit_panel→value_size→quality→growth→liquidity→risk→alpha101→channel_b，
  pit 失败跳过其下游；--only/--start/--end/--force 修复模式）+ `scripts/verify_p8_incremental.py`
  （20 股抽样单日全市场复算 vs 存量全量值逐值比对 + 连跑两次幂等）+
  `tests/test_panel_factors_daily.py`（10 例 Fake DB）+
  `deploy/systemd/panel-factors-daily.{service,timer}`（已装 /etc，Mon..Fri 17:45，enable）。
- **P5 risk warmup 修复**：回归族 1320 有效样本对窗口原按市场交易日数供给 warmup，
  窗口期停牌 >20 日的 ~290 股被误产 NaN；改 `_pair_aware_warmup_start`
  （个股第 1326 行历史日期取 max），增量与全量逐值一致（2026-10-09 验证 PASS）。
  残留：历史各年 chunk 起点附近旧口径 NaN 未回填（可选全量重跑修复）。
- QRE 8080：`gui/admin.py` 新增 PANEL_FACTOR_TABLES（8 表入 managed，转「日更中」
  参与滞后判定与健康灯）+ TIMER_UNITS 增 panel-factors-daily.timer +
  EXPECTED_COLUMNS_SCRIPT 注入 panel 各模块权威列清单；`gui/daily_jobs.py`
  增「panel-factors」手动管线；`templates/admin.html` UNIT_TO_PIPELINE 增映射。
- 验证：第三轮全市场单日复算 8/8 PASS（2026-10-09，20 股）；幂等（值/行数不变）；
  日更二次运行全 SKIP(fresh) 退出 0；8080 API 确认 8 表 daily_pipeline=true、
  无 pending 徽标、timer installed。
- 首次追数耗时（10-13~10-16 四交易日）：pit 1.3 / value_size 3.9 / quality 1.5 /
  growth 1.2 / liquidity 0.5 / risk 0.9 / alpha101 1.1 / channel_b 1.0 min（合计 ~11.4min）。

---

## Archive: QRE-SYMBOL-PERF-ZERO-TRADE（symbol_performance 零交易股票漏报口径修复——failed_orders 并入 + has_trades 标识列）

## Current Status

DONE (implementation; **未 commit**——commit 待用户/主代理批准；
tests/test_full_market_report.py 66 passed 含 +3 新测试，全量套件零回归)

## Task Note

- 根因（主代理已确诊）：job#58 summary.csv 5531 行 vs symbol_performance.csv 5398 行；
  batch 分支过滤（有成交或有委托才入表，有意设计不动）与 shared_cash 分支
  （symbol 集合仅取 round_trips）口径不一致，零交易/仅失败委托股票漏出。
- 修法（src/quant_research_engine/portfolio/full_market_report.py）：
  ①shared_cash 分支 symbol 集合 = round_trips ∪ failed_orders，rt 空但 failed 非空也出表，
  失败专属行 trade_count=0 / net_profit=0.0 / failed_order_count=N；
  ②batch 分支过滤不动；failed_order_count 上游确认由 batch.py::_summary_row 产出（无需引擎改动），
  缺列兜底 0；
  ③新增 has_trades 布尔列（trade_count>0），同步 _SYMBOL_PERFORMANCE_COLUMNS 与
  COLUMN_LABELS（「有交易」），前端可区分有交易 vs 仅失败委托/未成交。
- 测试：tests/test_full_market_report.py +3（failed_only_symbol_included、
  failed_only_symbol_included_when_round_trips_empty、既有过滤测试补 has_trades/兜底断言）。
- 取舍：加列侵入小且语义直接，优于让前端用 trade_count==0 推断；manifest 校验不受影响。

---

## Archive: QRE-DEAD-PENDING-FIX（回测引擎「dead-pending」静默吞信号 bug 修复——缩量重试 + insufficient_cash 失败登记）

## Current Status

DONE (implementation; **未 commit**——commit 待用户/主代理批准；
模拟器+向量化目标套件 144 passed，新增回归 5 例，真库 000002.SZ 验证 151 笔往返)

## Task Note

- 根因：full_compound 买入 `int(cash // price)` 名义额+费用略超现金时被拒，但既不改写
  failed_order 也不重置 pending_buy_index → 该股后续入场信号全被静默吞掉
  （job#58 共 135 只零交易股票，含 000002/000016/000725）。
- 修法（single_symbol.py 与 single_symbol_vectorized.py 两路径同步）：
  ①`AShareMarketProfile.fit_buy_quantity_to_cash` 逐手缩量直到 名义+费用 ≤ 现金
  （费用走 calculate_cost 同口径，含 min_commission 5 元地板）；
  ②缩量 ≥1 手按缩量成交；仍不足 1 手或一手都买不起 → failed_orders 记
  reason=insufficient_cash 并重置 pending，后续信号可重试；fixed_cash 同语义。
- 资金充足路径未触，既有行为逐字节不变（vectorized↔simulator 相等性套件守护）。
- 真库验证：000002.SZ 2010 起 MACD 金叉单票回测 151 笔往返、首笔 2010-01-19
  买入 9800 股@10.10（9900 缩量 1 手），sim/vec 逐帧相等。
- **遗留（报表层，本次未改）**：full_market_report.py batch 分支 build_symbol_performance
  （:575 起）以 round_trips 为准，零交易股票（即便有 failed_orders）从
  symbol_performance 漏掉、与 summary.csv 口径不一致。
- 测试：tests/test_portfolio_single_symbol.py +2、tests/test_single_symbol_vectorized.py +3。

---

## Archive: QRE-SAAS-SMOKE-INCIDENT (CR-2026-10-11：job 54 smoke 全市场超时事故修复——四 bug)

## Current Status

DONE (implementation; **未 commit**——commit + ECS 部署 + 重启本机 qre-saas-worker 待用户批准；
`-k saas` 238 passed 零回归，saas/workbench/security/portfolio/compiler/worker/spec 套件全绿)

## Task Note

- 四 bug 修法与证据详见 change_requests/CR-2026-10-11_saas_smoke_incident.md：
  ①apply_precheck 空 codes 改为按 run_id seed 随机抽样（绝不放行全市场）+ worker 侧
  smoke 跳过 tag_analysis/symbol_details 全量后处理；
  ②max_holding_days 0/null=不限（yaml_guard 放宽 + spec 显式 0→0/缺省→1 + compiler
  0 值不再被 `or` 穿透 + 三个引擎 holding_period 守卫），顺带 risk.*_pct: 0=不启用
  （校验 [0,1)，spec _optional_pct 归一 None）；
  ③daemon 心跳连续失败 3 次（max_heartbeat_failures 可配）判定 lease 丢失，
  置 canceled 终止子进程、释放槽位、不回传；
  ④build_lab_symbol_detail 新增 stats=/round_trips_by_symbol= 参数，
  build_symbol_detail_files 一次解析逐股复用，两处 O(n²) 消除。
- 新测试 9 例（precheck 抽样/holding 0/risk 0/引擎 holding 0 三例/心跳两例/O(n²) 回归）。
- 真库小样本实测：空 codes+max_codes=1 → 抽 1 只可复现；NL MACD YAML（holding=20、
  risk 0 值）校验通过且 spec 归一正确。
- **部署注意**：无 DB 迁移；commit 后须重启本机 qre-saas-worker 加载新 runner/daemon。

---

## Archive: QRE-NL-FACTOR-PIPELINE (CR-2026-10-09：NL 编译因子名四层防线——MACD signal 编造 bug)

## Current Status

DONE (implementation; **未 commit**——用户明确本轮只本机实现+测试，commit 等批准；
`-k saas` 237 passed 零回归 + 新增 12 全绿；顺手修了一个日期过期 flake)

## Task Note

- 四层全部落地（细节见 change_requests/CR-2026-10-09_nl_factor_pipeline.md）：
  ①configs/factor_catalog_llm.txt 真实目录快照（559 列压缩 12 行，
  gen_factor_catalog_llm.py 可再生成）注入 build_system_prompt + 硬约束；
  ②configs/factor_aliases.json + auto_fix_column 第 0 层别名变体；
  ③compile_nl 修复回路（_fixup_prompt 回喂，最多 2 次，fix_attempts 透出）；
  ④format_unresolved_hint 补「申请新因子」指引（前端 missing_factors 弹层链路不变）。
- 测试 tests/test_nl_factor_pipeline.py +12 全绿；用户报告案例
  macd_signal_12_26_9→macds_12_26_9 有精确断言（test_auto_fix_macd_signal_to_macds）。
- 顺手修 flake：test_saas_signals 信号日期硬编码 2026-10-01/02 在 10-09 过期
  （recent_signals_7d 窗口）→ 改相对今天生成。
- **未 commit**：工作区含全部改动（git status 见汇报）；ECS 部署待 commit 批准后
  下一轮做（configs/ 快照入仓库即上 ECS，无需数据库迁移）。
- 注意：catalog 快照是本地因子库口径，因子库新增列后需重跑生成脚本再提交。
- **2026-10-10 生产实测 hotfix（ff0e39e 后追加）**：①@{} 压缩语法 LLM 误读
  （仍写 macd_signal_12_26_9）→ 目录改平铺全列名（559 列零歧义）；
  ②ECS 无行情库 → lookup=None 纠错/重试层失效 → gen 脚本加写
  factor_catalog_llm.json，_default_column_lookup 失败回退快照；
  ③缺因子入队 OSError 兜底（ECS outputs 权限）。测试同步更新。

---

## Archive: QRE-SHARED-COST-BREAKDOWN (shared 模式交易费用拆分补齐——交易磨损卡佣金/印花税 0 值 bug)

## Current Status

DONE (implementation; `-k saas` 237 passed 零回归、portfolio/shared/market/worker 482 passed；
真库实测数值证据齐；awaiting git finalization 后部署 + 本机 worker 重启)

## Task Note

- 根因链（用户定位，核实无误）：shared.py `_trade_row` 只写 cost 总费用 →
  full_market_report shared_cash 分支不读拆分列 → round_trips.csv 拆分列空 →
  `_fees_summary` 聚合 0 → 前端佣金/印花税 0、总磨损全进「过户费/其他」。
- 修法（引擎口径变更，06 已登记）：shared.py 四路径（普通买/卖、rebalance 买/卖）
  改用 `calculate_cost_breakdown`（total==calculate_cost 原口径不变）；lot 存
  `entry_cost_parts`，`_consume_lots` 按比例分摊（缺拆分 lot 退化归佣金，总额不变）；
  `_trade_row` 补 6 列（键名与 vectorized 完全一致）；full_market_report shared_cash
  分支补读拆分聚合（与 batch 同口径）。存量产物不回填（文档注明）。
- 测试：test_portfolio_shared.py 默认列集合断言补 6 列 + 新增拆分正确性
  （组件和==cost、买入无印花税、卖出印花税>0）；test_full_market_report.py 新增
  shared→round_trips 链路回归（三列非空、组件和≈total_cost）。
- 实测数值证据（真库 shared 2025-06~12 × 000001.SZ+600519.SH，7 笔）：
  每行 commission=10.0（最低 5 元双边）、stamp_tax 4.46~5.12、transfer_fee≈0.19；
  _fees_summary 聚合 佣金 70.00 / 印花税 32.88 / 过户费 1.31 / 总磨损 104.19
  （修复前佣金/印花税为 0、104.19 全进 other）。

---

## Archive: QRE-SAAS-RESULT-ACTIONS (CR-2026-10-05：结果页显式入库 + 交易信号入口；策略库语义纠偏)

## Current Status

DONE (implementation; `-k saas` 237 passed（235 + 2 新增）零回归；staging 三态 +
游客态双端实测通过；awaiting git finalization 后部署；ECS 需手工 apply in_library 列)

## Task Note

- 核心语义（用户原话）：没超额收益的策略不该进策略库。现状是 api_create_job 提交即
  upsert 且列表全量显示 → 改为提交建行不入库。
- 约束与方案：jobs.strategy_id NOT NULL REFERENCES strategies(id)——提交必须建行
  （FK + 记录页展示），故加 `in_library BOOL DEFAULT false` 旗标：提交 upsert 不动
  旗标；策略库列表只显示 in_library=true；详情/回填不受限（job 关联行可读）。
  存量行 backfill true（**DO 块只在列不存在时迁移一次**——幂等 apply 不得翻回
  后来的未保存行，cloud_schema.sql 与应用层 ensure 同口径）。
- 后端：POST /api/saas/strategies/<id>/save（幂等置库，401/404）；POST watch
  隐含置 in_library=true（用户决策：信号依赖策略持久化）；/api/results/<id>/summary
  补 strategy_id（结果页轮询走的是它，不是 /api/saas/jobs/<id>——探针抓出的接线点）。
- 前端 job.html 结果页末尾「下一步」卡：「保存到我的策略库」（已保存回填置灰
  ✓）+「提示交易信号」面板（三选一：本次测试范围/指定板块二级菜单（复用
  /api/saas/universes）/全范围股票 → POST watch 三 scope_type）；游客整卡隐藏
  （现有游客引导条承担注册引导）。
- 测试：test_gui_saas.py 提交入库测试重写（提交后列表空/详情可读/保存后入库幂等/
  FK 禁删不变）；test_saas_signals.py +2（watch 隐含入库、save 401/404）；
  直插 helper 补 in_library=true；模板断言 +4（操作卡三要素）。
- 验证（staging Playwright 全实跑）：未保存态→点保存→「已保存 ✓」disabled+
  链接提示；信号面板三 scope + 板块二级菜单（7 组/31 项）；开启 sector watch
  落库正确且隐含入库；游客 375 操作卡隐藏零横滚；桌面+移动截图
  .tmp/mobile-audit/{desktop-ra-saved,desktop-ra-panel,m375-ra-actions,m375-ra-guest}.png。

---

## Archive: QRE-SAAS-TIER-BETA-RELAX (内测期两层权限调整：游客 10 只/10 年/随机补齐，注册用户全放开)

## Current Status

DONE (implementation; `-k saas` 235 passed 零回归；staging bypass=0 实例游客全流程实测；
awaiting git finalization 后部署 + 生产库 tier_policies 手工 UPDATE)

## Task Note

- 用户拍板（2026-10-05）：游客 近 2 年→10 年（3657 含宽限）、单股→最多 10 只
  （自选不足随机补齐 / 随机股票 N≤10 直用）；每日 1 次、次日清空不变；板块/全市场
  仍 403。member/paid 三值全 0=不限（每日 3 次取消），资源约束全交 R2 槽位体系。
- 随机补齐位置与理由：**worker 侧**（runner.fill_guest_codes，云端打
  `params.codes_auto_fill=N` 标记）。理由：云端 ECS 无行情库（数据不出家门），
  股票清单只在本地；worker 执行前用 universe.all_a_codes 抽样补齐（自选在前、
  无重复、池不足时给足可得数）。runner 抽成独立纯函数便于单测。
- 改动：app.py（GUEST_MAX_CODES=10/GUEST_MAX_DAYS=3657、_TIER_POLICY_DEFAULTS
  member/paid 全 0、游客闸门重写——codes ≤10 放行+标记补齐、>10 403、random_n
  1~10、universe 403、超 10 年 403、文案更新、me 接口 limit≤0 显示「不限」、
  console users quota_limit 读 member 实时值）；runner.py（fill_guest_codes +
  接入）；cloud_schema.sql 种子值同步；前端文案（base guest-strip、new 弹层/
  校验/游客收口（random 对游客放开、上限 10）、profile/login/job/feedback/console）。
- ⚠️ 运维坑（staging 实测抓出）：tier_policies 种子 ON CONFLICT DO NOTHING
  **不随代码常量更新**——部署后必须手工 UPDATE 各库三行，否则旧值生效
  （8092 实测旧行 guest.max_codes=1 把新语义压回「1~1 只」）。19 号文档已登记。
- 测试：test_gui_saas.py 游客链路重写（1 只标补齐/3 只放行+补齐/11 只 403/
  10 年放行/超 10 年 403/缺区间 400/随机 10 放行/随机 11 403/板块 403/日配额不变）+
  member 配额两测试改「不限」新口径；test_gui_saas_console.py 种子值断言更新；
  test_worker.py +4（补齐保留自选/无重复/已满不动/池小于缺口）。
- 验证：staging 8092（SAAS_AUTH_BYPASS=0 游客态实例）Playwright 桌面+375——
  弹层/提示条文案、scope 仅 codes+random 可见、random max=10、提交 random-10
  被云端接受并跳结果页（job 39），零 JS 报错（截图 .tmp/mobile-audit/
  {desktop,m375}-guest-{modal,submit}.png）。

---

## Archive: QRE-SAAS-REPLAY-LAYOUT-FIX (重播速度档换行 bug 系统性调试：全局 select{width:100%} 根因)

## Current Status

DONE (root cause found & fixed; `-k saas` 235 passed 零回归；五档宽度探针全过；
awaiting git finalization 后部署)

## Task Note

- 现象：用户强刷后重播控制条速度档仍单独成行。我上一轮只断言了 DOM 顺序
  （[播放,单步,速度,…] 正确），未测**计算布局**。
- 根因（探针实证）：五档宽度（1920/1440/1280/1024/768/414/375）下 `.rp-sel` 的
  getBoundingClientRect().width 恒等于 `.rp-bar` 全宽（1030px 等）——`base.html:56`
  全局规则 `input,select,textarea{width:100%}` 使速度档 select 独占整行，与视口
  宽度无关，所以任何窗口都换行。（`.rp-date` 因 `.date-input{width:auto}` 旧规则
  幸存，速度档无此豁免。）
- 修复（对症下药 + 结构性加固）：
  ①`.rp-sel{width:auto;min-width:72px;height:36px}`（lab-theme 后加载且类选择器
  优先级高于元素选择器，同时补齐 §1 行内控件 36px 等高——修复前 select 31px）；
  ②控制条改为两个语义分组：`.rp-group-main`（播放/单步/速度，flex-wrap:nowrap
  恒同排）+ `.rp-group-aux`（起始日/快进/计数，允许折行）——不再依赖
  `.rp-bar{flex-wrap:wrap}` 的宽度运气。
  ③中途自查发现「起始日」label 重复渲染（旧直挂 appendChild 与新分组并存，
  截图复核抓出），已去重。
- 验证（同一探针前后对照）：修复前 1920~375 全宽度 `.rp-sel` 独占整行（width=
  bar 宽）；修复后五档宽度 group-main 三子元素中心 y 差 = 0px、`.rp-lbl` 计数 = 1、
  进度条在 chart 正下方、零横滚；symbol 页 1280 同步确认。
  截图 .tmp/mobile-audit/{desktop,m375}-layout-fixed.png。
- 经验：DOM 顺序断言 ≠ 布局断言；涉及换行/独占行的验证必须测
  getBoundingClientRect 计算几何。

---

## Archive: QRE-SAAS-WAIT-MASK + QRE-SAAS-REPLAY-LAYOUT (首页长等待模态遮罩 + 重播控制条布局调整)

## Current Status

DONE (implementation; `-k saas` 235 passed 零回归；staging 锁定/两段式双路径/失败路径/
布局断言全过（含临时 worker 真实执行闭环）；awaiting git finalization 后部署)

## Task Note

- 遮罩组件 `static/wait-mask.js`（全站经 base.html 引入，可复用）：
  `LabUI.waitMask.show/update/hide/isOpen`——半透明深色背板 + 居中淡紫卡片
  （spinner + 阶段文案 + 副文案 + 可选分流按钮）；显示期间禁 ESC、禁背板点击、
  页面交互物理全锁（.wm-lock 禁滚动 + 背板拦截）；z-index 95（高于 .modal-mask 80 /
  cal-pop 60，低于 toast 99——大范围耗时护栏弹层 80 会被压，startRun 在
  confirmBigUniverse 前先关遮罩、确认后再开，已处理层级冲突）；有分流按钮时
  spinner 自动停转（等待语义交还用户）。CSS .wm-* 落 lab-theme.css（focus-visible
  紫环、0.2s 过渡、prefers-reduced-motion spinner 动画关闭、768px 按钮堆叠 44px）。
- new.html 接入：①生成策略——点击即开「AI 正在编译策略…」（副文案 10-40 秒），
  #nl-compile 与 #btn-run-main 同步置灰，finally 关遮罩走现有结果/报错；②运行回测
  两段式——pipeRunning 后开「冒烟校验中…」；游客路径切「提交任务中…」直跳；
  全量提交成功后切「已提交，排队执行中」+ 副文案「任务在云端运行，关闭页面不影响
  结果」+ 两按钮：「后台运行，查看记录」→ /saas/profile、「继续等待」→ 遮罩转
  「任务执行中…」轮询完成后跳结果页（超时/失败同样跳任务页看状态）；失败一律
  abort() 关遮罩走现有 pipeFailAt 报错。
  **踩坑**：wait-mask 按钮包装函数 `b.keepMask || b.onClick()` 短路导致
  keepMask=true 时 onClick 永不执行（「继续等待」假死），改先执行再判定。
- 重播布局（replay.js 两端生效）：速度档与播放/单步并列同一控制排；进度条移出
  控制排，经 `.rp-slider-row` 插到图表容器正下方（接管模式下 insertAfter chartEl，
  自建模式 append 于 chartEl 后）；destroy 同步移除 sliderRow。
- 验证（staging 8091 Playwright 全实跑）：
  - 布局断言两端：bar 子元素序 [播放,单步,速度,起始日,快进] 无 slider、
    `.rp-slider-row.previousElementSibling === chart`（桌面+375）✓；
  - 遮罩锁定：elementFromPoint 命中遮罩层、ESC+背板点击不关、遮罩下按钮点击
    无副作用、提交钮 disabled ✓；
  - 两段式（临时 worker 指 staging 真实执行）：冒烟段「冒烟校验中…」→ 提交后
    「已提交，排队执行中」+ 双按钮文案断言 → 路径A「继续等待」轮询后跳
    /saas/jobs/37 ✓、路径B「后台运行」跳 /saas/profile ✓；
  - 失败路径：NL 编译失败（staging 无 LLM 配置）遮罩正常关闭走报错 ✓；
  - 移动 375：卡片宽 343 自适应、按钮堆叠、零横滚零 JS 报错
    （截图 .tmp/mobile-audit/{desktop,m375}-mask-*.png、m375-replay-layout.png）。

---

## Archive: QRE-SAAS-REPLAY-POLISH (重播组件两项优化：控制条 UI/UX 打磨 + 接管原图表容器模式，用户批准)

## Current Status

DONE (implementation; `-k saas` 235 passed 零回归；staging 接管闭环 + UI 探针 +
reduced-motion 仿真全过；awaiting git finalization 后部署)

## Task Note

- 任务2 接管模式（用户原话「点击后会存在两个K线模块，建议在原K线模块上覆盖」）：
  replay.js 新增 `opts.chartEl`（接管既有容器——先销毁静态实例防 dataZoom/legend 残留）
  与 `destroy(keepDom)`（退出只撤控制条/日历、dispose 图表，容器交还调用方重建）；
  symbol.html 删 #box-kreplay 独立卡，控制条插槽 #kreplay-bar-slot 进 #box-kline，
  退出后 `renderKline(d)` 内存重建静态全量 + dataZoom 恢复；job.html 同理删
  #box-replay，接管 #chart-main，重播期间隐藏基准切换条与区间信息卡（避免口径并存），
  退出 renderMain(d) 恢复。**踩坑**：退出处理器里 `classList.add('hidden').innerHTML`
  链式调用（add 不返回元素）抛 TypeError 中断恢复流程，Playwright 探针抓出。
- 任务1 控制条打磨（ui-ux-pro-max 规则落地，与 12 号冲突处以 12 号为准）：
  ①emoji 图标全换内联 SVG（play/pause/step/skip）+ 文字标签 + title/aria-label；
  ②可点元素 cursor:pointer + hover 淡紫反馈 + :focus-visible 紫环（不去焦点环）；
  ③transition 0.2s（150-300ms 区间），播放↔暂停图标即时切换带 opacity 过渡；
  ④prefers-reduced-motion 媒体查询：事件弹入动画/峰值闪烁/按钮过渡全关
  （仿真实测 transitionDuration≈0）；⑤按钮 36px 等高（§1 行内控件硬规则）、
  8px 间距网格、播放钮主紫选中态与 entry-card.selected 同调性。
- 验证（staging Playwright 全实跑）：
  - symbol：进入重播 DOM 仅 1 个 #chart-kline（无第二模块）→ 浮动盈亏 −18.00 元
    → 退出静态还原 + dataZoom 双组件恢复 ✓；
  - job：进入接管（bench/strip 隐藏）→ 末帧累计收益 0.59% == 静态 ✓ → 退出
    基准条/区间卡/缩放全恢复 ✓；
  - UI 探针：cursor:pointer、高度 36px、transition 0.2s、.rp-btn:focus-visible
    规则存在；reduced-motion 仿真 transition≈0 ✓；
  - 移动 375 零横滚零 JS 报错（两端截图 .tmp/mobile-audit/{desktop,m375}-takeover-*.png）。
- 测试：模板断言随接管模式更新（box-replay/box-kreplay 移除 → bar-slot/exit 按钮）。

---

## Archive: QRE-SAAS-REPLAY-S2 (CR-2026-10-04 切片2：K线级重播（symbol.html 个股详情页）)

## Current Status

DONE (implementation; `-k saas` 235 passed 零回归 + 模板断言；staging 全链路 +
末帧强一致性 + 浮动盈亏手算核对通过；切片1 回归确认；awaiting git finalization 后部署)

## Task Note

- replay.js 向后兼容扩展（切片1 公共 API 未改，job 页回归实测 0.59% 不变）：
  ①series 支持 `type`（candlestick/bar/scatter 等）+ `extra` 任意 ECharts 配置透传；
  ②事件支持 `ev.price` 真实成交价定位（K线买卖点口径，candlestick 序列值取收[1]）；
  ③`opts.initialCursor`（默认近 2 年起播）；④`opts.height`（多副图加高）；
  ⑤yAxes 支持 `pct:false`（价格/量/因子轴不加 %——首版切片1 遗留的「全轴 %」
  在 K 线页暴露为价格轴显示 25% 的 bug，截图复核抓出修复）。
- symbol.html：K线卡标题加「▶ 重播」→ #box-kreplay 卡（可收起）——K线/成交量/
  因子副图逐日推进；事件源优先 orders（真实下单价量），缺失时 round trips 兜底
  （entry_price/exit_price/quantity 字段齐全）；「信」T 淡紫点与「入/出」T+1 相隔呈现。
- 侧边信息卡（onFrame 钩子渲染，组件零改动接入）：当前日 OHLC、成交量、各因子
  当前值、持仓状态（entry_price 入）、**浮动盈亏·毛**（(帧收盘−entry_price)×数量，
  随帧跳动，注明未扣卖出费用）、已实现盈亏累计（exit_date ≤ 帧的 net_pnl 合计）。
- 重播窗口：默认近 2 年起播（initialCursor 计算），全期 3991 根可经日历/进度条
  回看——组件截断渲染每帧全量重绘，实测 3991 根流畅无压力（无需 appendData）。
- 验证（staging 8091 Playwright 全实跑）：
  - 起播帧=近 2 年首日（slider 3506/3990），信息卡 OHLC/vol/rsi 逐帧正确；
  - 持仓中段 seek 2026-03-06：「持仓中（10.84 入），浮动盈亏·毛 −18.00 元」
    == 手算 (10.82−10.84)×900 ✓；
  - **末帧强一致性**：已实现盈亏累计 587.45 元 == 静态页 total_pnl 587.45 元 ✓；
  - 播放/单步/拖拽/快进（跳到 3852）全过；切片1 job 页重播回归 0.59% 不变 ✓；
  - 移动 375 零横滚零 JS 报错（两端截图 .tmp/mobile-audit/{desktop,m375}-kreplay.png）。
- 测试：test_gui_saas_pages.py symbol 页模板断言 +5（replay.js/box-kreplay/
  btn-kreplay/kreplay-mount/info/events）。

---

## Archive: QRE-SAAS-REPLAY-S1 (CR-2026-10-04 切片1：策略级回测重播 + 可复用重播引擎组件)

## Current Status

DONE (implementation; `-k saas` 235 passed 零回归 + 模板断言 +1；staging Playwright
全操作链路 + 末帧强一致性实测通过；awaiting git finalization 后部署)

## Task Note

- 重播引擎组件 `static/replay.js`（saas/lab 共享目录，切片2 个股页直接复用）：
  `QREReplay.core` 纯逻辑（indexDates/binEvents 事件按日归箱/positionCounts 差分展开
  持仓序列/nextEventfulCursor 空仓快进/frameMetrics 截断序列逐帧指标——累计收益/
  最大回撤+新峰值标记/夏普/胜率/盈亏比/持仓数/暴露度）+ `QREReplay.attach` UI 装配
  （播放/暂停、单步、速度 1/2/5/10、起始日复用 LabUI.attachCalendar、可拖进度条、
  空仓快进）。渲染红线：全量内存持有、每帧 [0,cursor] 截断喂 ECharts、rAF 节流。
  样式追加 lab-theme.css `.rp-*` 组件族（淡紫 tokens，768px 断点折行）。
- job.html 接入：收益曲线卡标题加「▶ 重播」，新开 #box-replay 卡（可收起）——
  净值/基准/回撤双 grid 逐日生长；事件流按日弹入（同日同类 >5 只聚合「当日入场 N 只」
  可展开）；指标面板 8 卡随帧重算（峰值刷新 .rp-peak-flash 视觉提示）；
  **时序红线**：图上「信」标记=信号日 T（成交日前一交易日，淡紫小点）与「入/出」
  成交日 T+1 相隔呈现 + 控制区口径文案 + 免责声明。
- 主轴以净值序列交易日为准，事件按日归箱对齐（信号日取成交日在主轴上的前一交易日）。
- 验证（staging 8091 Playwright，全实跑）：
  - core 探针断言：归箱/持仓差分/快进（空仓跳到下一事件或持仓变化日）/frameMetrics
    合成序列数值正确；
  - 操作链路：打开 → 单步 ×3（slider=3）→ 播放（按钮转暂停）→ 暂停 → 拖进度条；
  - **末帧强一致性**：重播累计收益 0.59% == 静态报告总收益率 0.59%（Playwright 断言）；
  - 空仓快进：开头跳到首个入场日 2026-03-04；速度档 10x；事件流 16 行弹入；
  - 起始日日历选 2026-03-07 → slider=5；移动 375 零横滚零 JS 报错（两端截图
    .tmp/mobile-audit/{desktop,m375}-replay.png）。
  - **测试脚本伪 bug 说明**：首轮「事件流 0 行」是脚本在组件自动暂停后又点播放
    （组件重播会清空事件流从 0 开始），非组件缺陷，复测 16 行正常。
- 测试：test_gui_saas_pages.py 模板断言 +5（replay.js 引用/box-replay/btn-replay/
  replay-mount/metrics/events）；组件逻辑无 node 测试设施，按惯例走页面探针断言（已做）。
- 切片2（symbol.html K线级）未做；组件已按复用设计（series/grids/yAxes/events/
  roundTrips 全参数化）。

---

## Archive: QRE-SAAS-SIGNAL-CONSOLIDATE (CR-2026-10-04 模块二 UX 收编：信号功能集成进「我的策略库」，用户拍板)

## Current Status

DONE (implementation; `-k saas` 235 passed（233 + 2 新增）零回归；staging 桌面+375
三态截图与红点闭环实测通过；awaiting git finalization 后部署)

## Task Note

- 产品决策（2026-10-04 用户反馈）：信号不做独立栏目/顶栏导航，收编进策略库。
  页面与接口全部保留，入口改挂在策略库。
- 顶栏：移除「信号」导航项与其红点；未读信号红点改挂「个人信息」导航
  （有未读信号时显示；进入 /saas/signals 或策略详情页信号区 mark-read 后消除；
  红点 span 置于文字前，保住既有 `个人信息</a>` 断言）。
- 策略列表 API 聚合（一条 watch 查询 + 一条按 watch 最近信号日聚合统计，无 N+1）：
  每行新增 watch（状态/范围/快照）、latest_signals（最近信号日 + entry/exit 计数，
  取各 watch max(trade_date) 当日）、signal_unread（最近信号日内
  created_at > signals_last_read_at 的条数 > 0；从未读过则全计未读）。
- 个人信息页策略库行：入口标签徽标 + 第二行小字——已开启=绿字「监控中（范围 N 只）
  · MM-DD：X 入场 Y 离场」；未开启=「开启监控 →」链接跳详情页监控卡；有未读信号时
  行首红点。卡片标题旁加「查看全部信号 →」链接到 /saas/signals。
- 策略详情页：监控卡下方新增「该策略信号记录」区（复用 /api/saas/signals?
  strategy_id=<id> 筛选——接口在模块二已支持该参数；按日期倒序 20/页分页 +
  「查看全部 →」链接 + T+1 免责）；详情页信号区可见即 mark-read（红点消除）。
- 信号中心 /saas/signals 保留但不进任何主导航；其红点元素 id 同步改 nav-records-dot。
- 测试：test_saas_signals.py +2（列表聚合三态：无监控行 null 字段、有监控行
  最近信号日统计取 max 日（10-01 旧日不混入）+ mark-read 后未读消除）。
- 验证：staging Playwright 桌面+375——导航红点 block→详情页 mark-read→none 闭环、
  行内红点/监控中徽标/开启监控链接三态、零横滚零 JS 报错；截图
  .tmp/mobile-audit/{desktop,m375}-consol-{profile,detail}.png。

---

## Archive: QRE-SAAS-SIGNAL-CENTER (CR-2026-10-04 模块二：策略信号监控 + 站内信号中心)

## Current Status

DONE (implementation; staging 验证通过；awaiting git finalization 后部署；ECS 新表
strategy_watches/signal_events 首次手工 psql apply，tier_policies/users 的 ALTER 由
应用懒自愈——这两张表 ECS 上 owner 是 aguhuice，无 owner 踩坑)

## Task Note

- 数据层（懒自愈 `_ensure_signal_tables` + cloud_schema.sql 同步）：
  `strategy_watches`（UNIQUE(strategy_id,user_id)，scope_type ∈
  last_run_universe/sector/all_a/custom，scope_payload JSONB 快照）；
  `signal_events`（UNIQUE(watch_id,trade_date,ts_code,signal_type) 幂等防重）；
  `users.signals_last_read_at`（未读红点）；`tier_policies` 加
  `scan_enabled BOOL DEFAULT true` / `max_watches INT DEFAULT 20`（_get_policy 同步读取，
  缓存兜底默认全开）。
- 用户侧接口：POST/DELETE `/api/saas/strategies/<id>/watch`（默认 last_run_universe
  自动取最近 job 的 params.codes 快照；max_watches 上限 403；scan_enabled=false 403；
  他人策略 404）；`GET /api/saas/signals`（date_from/to、strategy_id、signal_type、
  ts_code 筛选 + 分页，日期真实校验防 PG 500）；`GET /api/saas/signals/unread-count`；
  `POST /api/saas/signals/mark-read`。详情 API 加 watch + recent_signals_7d。
- worker 侧接口（X-Worker-Token）：`GET /api/worker/watches`（enabled + 策略 yaml +
  scope，scan_enabled=false 层级不下发）；`POST /api/worker/signals`（批量，
  ON CONFLICT DO NOTHING，单批 ≤10000，逐字段校验 400）。
- 扫描脚本 `deploy/saas/signal_scan.py`（本机 worker 侧）：拉 watches → resolve_codes
  （快照/custom 用 payload、sector 走 universe_members 本地库、all_a 取最近交易日
  有行情全体）→ load_panel（只拉表达式引用列，因子表按表分组一次 SQL，别名对齐）→
  compute_signals 按 ts_code 分组逐组求值（**shift 不跨股票边界**，与引擎求值器
  evaluate_expression_signal 同一 AST 白名单）判最新交易日 entry/exit → 分批回传。
  单 watch 失败记日志继续；QRE_SIGNAL_SCAN_LOOKBACK_DAYS 默认 40；单 watch 单日
  信号上限 5000。挂载 qre-refresh.service `ExecStartPost=-`（refresh 成功后触发，
  失败不影响 refresh 结果）。
- 页面：strategy.html 监控卡做实（开关 + 范围选择[默认最近回测快照/全A/自定义] +
  最近 7 日信号数 + 删除监控）；新页 /saas/signals 信号中心（筛选 + 分页表格 +
  进入即 mark-read + 免责「日线收盘后 T+1 参考信号，不构成投资建议」）；
  base.html 顶栏加「信号」入口（登录态才显示/查询）+ 未读红点（信号中心页跳过
  未读查询避免 mark-read 竞态回亮——实测发现）。
- 测试：tests/test_saas_signals.py +15（watch CRUD/默认快照/上限/scan 关闭 403/
  权限 401/404、worker 鉴权与下发过滤、幂等回传 inserted=0、400 校验、筛选分页、
  未读/mark-read、详情卡字段、扫描脚本 parse/compute 合成面板正确性+空信号+跨股边界）；
  test_saas_strategy_assets.py 一处断言更新（占位注释→sd-watch-card）。
  **踩坑**：cloud_schema.sql 里 tier_policies 的 ALTER 必须排在其 CREATE TABLE 之后
  （初版顺序错误致临时库 schema apply 失败，测试基建抓出）。
- 验证：staging 8091 实测 watch 创建→worker 拉取→信号回传→未读红点（block）→
  信号中心 mark-read→红点灭；桌面+移动截图零横滚零 JS 报错。

---

## Archive: QRE-SAAS-STRATEGY-ASSETS (CR-2026-10-04 模块一：策略库 → 策略资产)

## Current Status

DONE (implementation; `-k saas` 218 passed（208 + 10 新增）零回归；staging 8091 桌面
1280 + 移动 375 截图验证零横滚零 JS 报错；向导快照回填实测逐键正确；
awaiting git finalization 后部署；ECS 需手工 apply strategies 新列)

## Task Note

- 数据层：strategies 加 `entry_mode TEXT`（nl/wizard/yaml）+ `wizard_state JSONB`；
  `_ensure_strategy_asset_columns` 懒自愈（先查 information_schema 再 ALTER——ECS 表
  owner 是 postgres 的既有踩坑），存量推断迁移（nl_text 非空→nl 否则→yaml，幂等）；
  cloud_schema.sql 同步。`_infer_entry_mode`/`_norm_wizard_state` 规范化入参
  （非法 entry_mode 400；wizard_state 仅 dict 落库）。
- 写入链路：POST /api/saas/strategies 与 api_create_job 同名 upsert 均落
  entry_mode/wizard_state；upsert 用 COALESCE 保留旧快照（未传不覆盖）。
- 读取：列表 API 加 entry_mode；新 `GET /api/saas/strategies/<id>/detail`
  （登录 401 / 他人 404）返回策略全字段 + 全部历史 job（状态/区间/标的数/收益/超额，
  symbol_count 兜底口径同 /api/results）。
- 新页面 /saas/strategies/<id>（strategy.html）：源文件卡按 entry_mode 还原——
  nl=原文大文本框+「重新编译」（走 /api/saas/nl/compile，编译结果入 YAML 预览待保存）；
  wizard=快照条件组只读还原+「在向导中编辑 →」跳 /saas/new?strategy=<id>&mode=wizard
  （无快照明示降级 YAML 编辑）；yaml=代码编辑框；当前生效 YAML details 折叠展示。
  操作区：保存修改（同名 upsert）/另存为新策略/载入复测。历史回测卡（点击行跳结果页，
  复用 records 徽章风格）。信号监控卡留 `<!-- CR-2026-10-04 模块二占位 -->` 注释。
- 个人信息页策略库卡：名称旁加入口标签徽章（自然语言/自选因子/策略代码）+「详情」链接。
- new.html：提交 payload 加 entry_mode=curEntry() + wizard_state=collectWizardState()
  （快照口径 {entry/exit:{groups:[{comb,conds:[{left,op,fixed,right}]}],dividers}}）；
  nl_text 截断 200→2000（原文可还原）；loadStrategyFromQuery 按 entry_mode/mode 参数
  还原入口——nl 回填原文、wizard 等因子目录就绪后 restoreWizardState 重建条件组
  （10s 超时降级 yaml）、其余进 yaml 入口；顺手修 staging bypass 下 `!saasToken()`
  门导致回填不生效（改 isGuest() 判定）。
- 验证：Playwright 桌面+移动截图（.tmp/mobile-audit/{desktop,m375}-sd-{yaml,wizard,nl}.png、
  desktop-new-backfill-{wizard,nl}.png、records 两端）零 JS 报错零横滚；向导回填探针实测
  conds 逐键还原（ema_5 crosses_above ema_200 / rsi_14<30 / exit crosses_below）。
- 测试：tests/test_saas_strategy_assets.py +10（懒自愈+存量推断、保存/upsert/快照
  COALESCE/400、job 提交落模式、详情 401/404/200 历史列表、页面结构含模块二占位断言）。

---

## Archive: QRE-SAAS-MOBILE-ADAPT (移动端 web UI 适配：375px 逐页审计 + base.html 统一移动端规则)

## Current Status

DONE (implementation; `-k saas` 208 passed 零回归；staging 8091 移动端 375×812 全页
零横滚零 JS 报错 + 交互冒烟通过；桌面 1280px 回归截图无破坏；awaiting git finalization 后部署)

## Task Note

- 审计先行：Playwright（viewport 375×812 + isMobile + hasTouch）逐页截图 + 探针
  （页级 scrollWidth、溢出元素 Top5、<44px 点击目标计数、pageerror 收集），脚本与
  截图在 `.tmp/mobile-audit/`（gitignore 覆盖）。修复前问题清单：
  ①records/profile/login 页级横滚 767px（记录表 #jobs-table 712px 溢出）；
  ②job 页 625px（费率长 chip nowrap 392/424px + 交易磨损 .wear-cards 5 列网格
  卡片 min-width 溢出 + .wb-row 磨损条 label 170px/val 190px 固定宽）；
  ③symbol 页 571px（同上 + 交易明细表 517px）；④new 页无横滚（.yv YAML 行内滚动
  属容器内行为）；⑤全站小点击目标偏多（36px 控件/日历格 26px）。
  用户反馈的「header 两行」「textarea resize」现状已正常（960px 断点顶栏单行、
  textarea resize:none 均在），本次复核确认。
- 修复（全部集中在 saas/templates/base.html 内嵌样式末尾新增
  `@media (max-width:768px)` 规则块，模板结构零改动，桌面零改动）：
  表格 .tbl/.detail-table 块级 overflow-x 横滚；.meta-chips .chip 允许折行；
  按钮/导航/tab min-height 44px；输入控件 16px+44px（防 iOS 聚焦放大，checkbox/
  radio 例外）；日历格/翻页钮 40px（.cal-pop 前缀提优先级）；.metric-card
  min-width 96px；.page-head h1 22px；磨损块 .chart-box .wear-cards 降 2 列 +
  .wb-row 改 grid 96px/1fr/auto。
- **踩坑**：lab-theme.css 在 base.html 内嵌样式之后加载，同优先级裸类名覆盖被静默
  压掉（wear-cards 初版不生效，探针复核发现）→ 用 .chart-box 前缀提优先级
  （与 §9「ID/高优先级选择器压过」约定一致），已登记 12 号文档 §10。
- 验证：修复后全页 scrollWidth=375 零横滚、零 JS 报错；交互冒烟——三入口卡切换、
  日历弹层 31 个可点日、选「指定股票代码」填 000001 提交，流水线走通到
  「结构校验通过→冒烟测试 小范围验证中」（staging 无 worker，执行留生产验证）；
  桌面 1280px 五页回归截图无破坏（chips 单行、6 卡一行、磨损块原样）。
- 12 号文档新增 §10 移动端适配规则（768px 断点/44px 触达/表格横滚等落地细则与
  审计结论），变更记录已登记；测试无模板断言受影响（纯 CSS）。

---

## Archive: QRE-SAAS-R3-SLICE2 (R3 后台资源可视化 切片2：资源调配封装，方案 C=A+B 混合)

## Current Status

DONE (implementation; `.venv/bin/pytest tests/ -q -k saas` 207 passed（200 + 7 新增）零回归；
worker 侧 +4 单测；本地闭环冒烟通过（含期望配置比对日志）；awaiting git finalization 后部署)

## Task Note

- B 侧（云端期望配置 + 比对）：新表 `worker_configs`（worker_id 主键单行/worker，
  desired_light_slots/desired_heavy_slots/desired_light_min_avail_mb/
  desired_heavy_min_avail_mb/version(每次+1)/updated_at/updated_by）；
  `_ensure_worker_configs` 懒自愈（先查 information_schema.tables 再 CREATE，沿用
  切片1 owner 踩坑教训）；cloud_schema.sql 同步。
- `POST /api/worker/status` 响应新增 `desired_config`（无配置 → null）；worker daemon
  `_check_desired_config` 与当前生效 limits 比对：不一致记「期望配置 vN 待应用
  （逐键 当前→期望）+ worker-tune.sh 提示」，同 version 只提示一次；恢复一致记
  「期望配置 vN 已生效」。
- 管理台：console overview 的 workers_detail 每项新增 desired_config 与
  config_mismatch（`worker_config_mismatch` 纯函数：期望为 None 的键不约束，
  旧 worker 未上报 limits 视为不一致）；console.html Worker 卡显示「当前生效 vs
  期望 vN（时间/操作人）」两行，不一致值橙色加粗 + 不一致徽章 + 橙底行；不一致时
  显示可复制的 `bash deploy/saas/worker-tune.sh ...` 命令（复制按钮）；4 值编辑表单
  「设为期望」提交 `POST /api/saas/console/worker-config`（admin 门禁，校验非负整数，
  upsert + version+1，updated_by=user#uid）。
- A 侧：新脚本 `deploy/saas/worker-tune.sh`（bash）——4 参数校验非负整数，sed 更新
  /etc/qre-saas-worker.env（缺键追加，改前备份 .bak-<ts>），EUID 检查 sudo 自提权
  （`sudo VAR=.. bash $0 ...`），重启 qre-saas-worker 并打印状态；测试钩子
  QRE_WORKER_ENV_FILE 覆盖目标文件、QRE_WORKER_SERVICE 显式置空跳重启（本机 tmp
  文件实测：就地更新/追加/备份/非法值 exit 2 全过）。
- 一致性闭环：console 用「上报 limits == 期望」判定；worker 重启后上报自动回一致态，
  无确认回执。
- 测试：tests/test_saas_worker_status.py +7（保存接口 401/403/400×3、upsert version
  递增单行、status 响应回带/无配置 null、overview mismatch 三态流转、纯函数边界）；
  tests/test_worker_status.py +4（同 version 只记一次/新版本再提示、一致不记、
  应用后「已生效」、无配置静默）。
- 部署要点：**ECS 首次需手工建表**（owner 踩坑）：
  `sudo -u postgres psql aguhuice -f` worker_configs 段；本机 staging 库自动懒建。

---

## Archive: QRE-SAAS-R3-SLICE1 (R3 后台资源可视化 切片1：worker 实时状态上报 + 管理台展示)

## Current Status

DONE (implementation; `.venv/bin/pytest tests/ -q -k saas` 200 passed（基线 190 + 10 新增）零回归；
worker 侧 +9 单测；本地 test_client 闭环冒烟通过；awaiting git finalization 后 ECS 部署)

## Task Note

- 云端新端点 `POST /api/worker/status`（X-Worker-Token 鉴权，401/503/400 分层）：
  body {worker_id, mem_available_mb, mem_total_mb, slots:[{name,kind,busy,job_id}],
  limits:{light_slots,heavy_slots,light_min_avail_mb,heavy_min_avail_mb}}，
  整个负载落 `workers.status`（JSONB）+ `status_at`，同时刷新 last_heartbeat_at。
- workers 表新增 status JSONB / status_at TIMESTAMPTZ 两列：懒自愈 ALTER 模式
  （`_ensure_worker_status_columns` + 进程级 `_WORKER_STATUS_ENSURED` 标记，照抄
  weight_class 模式）；cloud_schema.sql 幂等追加（放在 workers CREATE TABLE 之后）。
  **踩坑 ×2**：①overview 里懒自愈 ALTER 必须在开读连接之前执行——读连接事务持有
  workers 共享锁，嵌套第二连接 ALTER 排他锁会自我等待（test_legacy_worker 用例实测
  挂死暴露）；②ECS 上 workers 表 owner 是 postgres（schema apply 所建），app 账号
  ALTER 即使 IF NOT EXISTS 也报 must be owner（上线首报 500 实测）——ensure 改先查
  information_schema，列在则不发 ALTER；新列首次手工 psql apply（已执行）。
- worker 侧：daemon.py 线程安全槽位状态表（`_slot_set`/`slots_snapshot`），
  `_slot_loop` 启动即注册空闲、claim 后置 busy(job_id)、finally 复位；
  后台 status 线程（`_status_loop`，间隔 env `QRE_WORKER_STATUS_SECONDS` 默认 15s，
  启动即报一次），上报失败仅记日志不中断；单槽旧模式 run_forever 等效上报
  （light_slots=1/heavy=0，槽位名 main）。client.py 加 `report_status`
  （stdlib urllib 不变）；slots.py 加 `mem_total_mb`（/proc/meminfo MemTotal，
  非 Linux 返回 None 降级）。mem_available_mb 为 inf 时降级 None（JSONB 落不了 Infinity）。
- 管理台：console overview JSON 新增 `workers_detail` 数组（name/last_heartbeat_at/
  online(心跳<60s)/mem_available_mb/mem_total_mb/slots/limits/status_at；**注意**：
  既有 `workers` 键是 {total,online} 汇总对象被 ov-jobs 卡片消费，未改动，明细走新键）。
  console.html 总览 tab 新增「Worker 资源」卡（#ov-worker-res，位于队列深度条与
  服务器资源卡之间）：每 worker 一张卡——绿/灰在线点、内存可用条（可用/总量 MB，
  未上报显示「旧版 worker」）、轻/重槽位格（忙碌紫底高亮 + title 显示 job_id，
  空闲灰底）。只读展示，无远程调参。
- 测试：tests/test_saas_worker_status.py +10（鉴权 401/503/400×2、落库+心跳刷新、
  overview 明细透出、旧 worker NULL 降级、缺列旧库懒自愈 ALTER、页面区块断言）；
  tests/test_worker_status.py +9（mem_total 解析/缺失、payload 组装与 inf 降级、
  上报成功/失败兜底、run_once 与 _slot_loop 槽位 busy 跟踪、status 线程周期上报）。
- 验证：`-k saas` 200 passed；/tmp/r3_smoke.py 本地闭环（daemon → CloudClient →
  Flask test_client → overview workers_detail 槽位/内存正确）。
- 部署要点：ECS git pull 后 restart qre-saas（懒自愈 ALTER 自动补列，无需手工 psql）；
  本机 worker restart 后 15s 内开始上报。env `QRE_WORKER_STATUS_SECONDS`
  有默认值 15，两端 env 文件无需改动。
  ⚠️ 2026-10-03 晚已收敛为唯一系统级 `qre-saas-worker`（见 16 号文档 C3 收敛条目），
  上文「qre-worker（user 级）」均已退役。

---

## Archive: QRE-CALENDAR-YEAR-PICKER (回测区间日历 年→月→日 钻取选择，共享组件两端同步升级)

## Current Status

DONE (implementation; full test suite green (2212 passed + 4 skipped, 复跑确认); 仅本地 staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 范围：共享静态文件 `static/lab-ui.js`（LabUI.attachCalendar）+ `static/lab-theme.css`
  （cal-pop 组件族三条新规则）；8081 lab 与 SaaS 模板零改动（两端同源引用，自动同步升级）。
- 交互：点头部年月标题（新 .cal-title 按钮）逐级上钻——日视图→年份视图
  （12 年/页九宫格 .cal-grid-ym 4 列 + .cal-cell，翻页 ±12 年，标题「YYYY – YYYY 年」）
  →选年进月份视图（当年 12 个月，翻页 ±1 年）→选月回日视图；Esc 逐级返回
  （年→月→日→关闭弹层），年视图再点标题回日视图。头部 .cal-nav 翻页箭头各视图复用，
  无可翻内容时禁用。
- 约束：maxDate 禁未来逻辑与「数据截至 X（最近交易日）」页脚提示不变；新增可选
  opts.minDate 下界（年整年/月整月超界格子 :disabled 置灰禁点，clamp 夹取下界），
  调用方未传 minDate 行为与旧版完全一致（lab.html/new.html 零改动兼容）。
- 样式：选中起/止日所在年/月 .cal-cell.sel 紫底白字（--lav），与选中日一致；
  禁用格 #D5CFE3 同 .cal-day:disabled；无新色相、无循环动效。
- 键盘：标题/格子/翻页均原生 button 可 Tab 聚焦（:focus-visible 紫环全局生效），
  Esc 逐级回退/关闭。
- 测试：现有断言仅查 #cal-pop/attachCalendar 存在性（test_gui_lab.py:205、
  test_gui_saas_pages.py:96），无需修改；项目无 node 侧 JS 测试设施，按约定不新建。
  全量 pytest tests/ -q → 2212 passed + 4 skipped 零回归
  （test_gui_risk_report 一例首轮偶发失败，单测复跑通过，与本次 JS/CSS 改动无关）。
- 验证：staging 8091 Playwright（~/.kimi-code/skills/smart-web-scraper/qre-calendar-verify.js）
  截图 /tmp/qre-shots/cal-{0-page,1-date,2-year,3-month,4-back-to-date,4b-future-guard,5-final}.png；
  DOM 探针实测：三视图切换、年视图 2027 置灰+下一页禁用、maxDate=2026-09-28 当月
  29/30 禁点 28 可选、钻取选值正确（起始 2020-03-02/截止 2026-01-15）、Esc 回退与关闭、零 JS 报错。
- 12 号文档 §3.7 与变更记录已登记（QRE-CALENDAR-YEAR-PICKER）。未 commit、未部署。

---

## Archive: QRE-SAAS-EXPOSURE-METRICS (区间信息卡新增持仓暴露度/持仓期年化收益两张联动卡)

## Current Status

DONE (implementation; full test suite green (2212 passed + 4 skipped); 仅本地 staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 范围：saas/templates 的 job.html、symbol.html、base.html；lab 侧零改动。
- 数据口径：持仓暴露度 = 有持仓交易日数 ÷ 区间交易日数。数据源用结果已有
  round trips（job 级 chart_data.trades.points entry/exit 日期；symbol 级
  d.trades 全量），每笔 [entry,exit] 展开到交易日轴成逐日持仓布尔掩码，
  同日多笔重叠按 1 天去重；产物无逐日仓位序列，此为最准口径。
  持仓期年化 = (1+区间策略收益)^(252/持仓天数)−1（252=年交易日数）。
  区间无持仓 → 两卡均显示「—」；口径写 title 悬停提示；job 级 >500 笔
  sampled 时提示「按前 500 笔估算」。
- 联动：掩码在 renderMain/renderEquity 构建一次，updateRangeStrip（rAF 节流）
  切片求和，随滑块重算，与既有区间卡同链路。
- 样式：base.html #range-strip 由 repeat(5,1fr) 改
  repeat(auto-fit,minmax(130px,1fr)) 按卡数自适应（≤960px 仍降 2 列），
  卡片沿用淡紫底 metric-card 族（QRE-SAAS-DETAIL-CARD-UI）。
- 测试：零新增零修改；全量 2212 passed + 4 skipped 零回归。
- 验证：staging 8097 job 26，Playwright 宽+窄屏截图
  /tmp/qre-shots/expo-{job,symbol}-{wide,narrow}.png；探针实测 7 卡、缩放联动
  （80.00%/1.33% → 89.47%/4.41%）、无持仓区间「—」、数值抽查
  1.0059^(252/112)−1≈1.33% 正确、零 JS 报错。
- 12 号文档变更记录已登记（QRE-SAAS-EXPOSURE-METRICS）。未 commit、未部署。

---

## Archive: QRE-SAAS-DETAIL-CARD-UI (公网回测详情页/个股详情页卡片 UI 四项验收修改)

## Current Status

DONE (implementation; full test suite green (2212 passed + 4 skipped); 仅本地 staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 范围：只改 SaaS 侧 src/quant_research_engine/gui/saas/templates/
  （job.html、base.html），8081 lab 侧零改动。
- ① 区间信息卡末尾留白：根因是 lab-theme.css 把 .metric-strip 纠偏成
  repeat(6,1fr) 六列网格，五卡只占 5/6。base.html 加
  `#range-strip{grid-template-columns:repeat(5,1fr)}` 整行均分；≤960px 降 2 列。
- ② job.html 模块顺序对齐 12 号文档 §8：box-fees（交易磨损）+ box-risk（FRM）
  DOM 移到 box-main（收益曲线）之后、box-tags（归因）之前。
- ③ symbol.html 顶部 7 简介卡：`#sum-strip` 改
  `repeat(auto-fit,minmax(200px,1fr))` + padding 10px 14px + 数值 15px
  （对齐 §1.3 个股页口径），宽屏 5+2 舒展布局、宽高比约 3.4:1，窄屏自动降列。
- ④ 总结性卡片淡紫底：#metric-strip/#sum-strip/#range-strip 的 .metric-card
  统一 var(--tint) 底 + var(--tint-deep) 边（既有 token，无新色相）。
  均用 ID 选择器压过 lab-theme.css 后加载的同族规则。
- 踩坑（已记入 12 号文档变更记录）：Jinja 模板内联 CSS 中 `{#id` 连写会被当
  Jinja 注释起始 → 500 TemplateSyntaxError，须写 `{ #id` 留空格。
- 测试：零新增零修改（既有模板断言不含模块顺序，全绿）；全量
  2212 passed + 4 skipped 零回归。
- 验证：本地 staging（8097 + aguhuice_local + job 26；为截图把本地 run
  20260927T040759327205 的 per-symbol 产物复制到 outputs/saas_uploads/job_26/
  _symbol_details/ 并手工补 equity 字段——纯本地 staging fixture，不入库）。
  Playwright 宽屏 1440 + 窄屏 390 截图 /tmp/qre-shots/cardui-{job,symbol}-{wide,narrow}.png；
  DOM 探针：range-strip trailingGap=0、卡底 rgb(241,237,248)=--tint、模块顺序正确、
  零 JS 报错。
- 12 号文档变更记录已登记（QRE-SAAS-DETAIL-CARD-UI）。未 commit、未部署。

---

## Archive: QRE-SAAS-SYMBOL-UX-SHARED-FIX (per-symbol 产物回传 shared 模式数据缺陷修复)

## Current Status

DONE (implementation; deployed to ECS via scp 临时部署（最终 git pull 对齐由用户做）; full test suite green (2212 passed + 4 skipped); awaiting user-approved git finalization)

## Task Note

- 根因：shared（共享资金）模式引擎不产出 per-symbol 目录（`<output_dir>/<ts_code>/`
  仅 batch 有），build_lab_symbol_detail 的 equity/orders/failed_orders 全 None；
  此前验证的 job 19 恰为 batch 模式所以漏测。job 21（真实用户 shared 单票）线上
  收益曲线/买卖点缺失即此因。job 20 无产物属正常（smoke 0 笔交易）。
- 修法（worker/runner.py，SaaS 链路专属，lab 版零改动）：新
  `_enrich_shared_symbol_detail`——orders/failed_orders 从任务级 CSV 按 symbol
  过滤；wear 聚合块从 round_trips 真实费用列算出；equity 仅单票 shared run 取
  任务级 equity_curve.csv（口径正确），多股保持 None 不编数；回填
  summary.total_ret_pct。symbol.html：renderWear 优先消费 d.wear；round_trips
  口径交易明细补「费用」列。
- 存量修复：job 21 用本地 run 目录重跑 builder 生成修正 gz（10.9KB，equity
  480/kline 480/orders 19）scp 覆盖 ECS uploads/job_21/_symbol_details/。
- 验证：公网 demo01 新 shared 单票 job 23 全链路（裸代码 603970 → 新 worker →
  回传）API 与页面全模块渲染，截图 /tmp/qre-shots/pub-fix-symbol23.png 零 JS 报错。
- 部署：scp symbol.html + restart qre-saas；runner.py 本地 restart
  qre-saas-worker。临时部署，最终 git pull 对齐由用户做。
- 测试：tests/test_saas_symbol_ux.py +5；全量 2212 passed + 4 skipped 零回归。
- 未 commit。

---

## Archive: QRE-AUTH-MEMBERSHIP (Authing 身份层登录接入，A2-A6；18 号设计文档)

## Current Status

DONE (implementation; full test suite green (2207 passed + 4 skipped); 仅本地+staging 验证、代码未部署 ECS；awaiting user-approved git finalization + Authing 控制台回调白名单确认)

## Task Note

- 实施流程与设计文档 §6 的 Guard 方案不同：OIDC 授权码 + Authing 托管登录页跳转
  （与控制台已配置的回调 URL 匹配，零前端 SDK）。18 号文档已注记。
- A2：deploy/saas/cloud_schema.sql 幂等追加 users.authing_id（部分唯一索引）/
  avatar_url/member_since/member_expire_at；aguhuice_local 已 apply。
  **ECS 部署前须先 psql apply cloud_schema.sql**。
- A3：新模块 src/quant_research_engine/gui/saas/authing.py（换票/JWKS 缓存/验签，
  requests+pyjwt 惰性导入）；app.py 新增 GET /saas/login/authing（302+state）、
  GET /saas/login/callback（验签→按 sub 建档/关联→本地 session→
  login_callback.html 落 localStorage 跳工作台）、POST /api/saas/auth/authing
  （JSON 版）、POST /api/saas/auth/bind（绑定旧邮箱账号，迁移 authing_id）。
- 依赖：pyproject 加 pyjwt[crypto]>=2.8 + requests>=2.31（uv.lock 已更新）；
  ECS 精简 venv 已 pip install 完成。
- A4：login.html——Authing 主按钮 + 邮箱密码/绑定旧账号两个 details 折叠区；
  已登录不再自动跳工作台（保证绑定入口可达）。新模板 login_callback.html。
- A5：tests/test_saas_authing.py +22（本地 RSA mock JWKS 正反例/建档幂等/绑定四态）；
  全量 2207 passed + 4 skipped 零回归。
- A6：AUTHING_* 四键已写 ECS /etc/qre-saas.env 与本地 .env.saas-staging（0600）。
  代码未部署：等 commit 后 ECS git pull + apply schema + restart qre-saas。
- staging 实测（8091+aguhuice_local+真配置）：跳转 Authing 托管页链路通；
  **⚠️ Authing 报 redirect_uri_mismatch**——需用户在控制台「应用配置→登录回调 URL」
  确认白名单含 https://www.aguhuice.com/saas/login/callback。真实短信/扫码留用户实测。
- 截图：/tmp/qre-shots/auth-login-page.png / auth-login-expanded.png /
  auth-authing-hosted.png（mismatch 错误页）。

---

## Archive: QRE-SAAS-FEEDBACK-FACTOR-REQ (内测意见反馈页 + 申请新因子页 + 缺因子拦截跳转 + 全站侧边栏)

## Current Status

DONE (implementation; full test suite green (2185 passed + 4 skipped); 仅本地+staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 侧边栏：此前 SaaS 页面无侧边栏（仅顶栏）。base.html 新增统一 `.sidenav`
  组件（「意见反馈」/saas/feedback、「申请新因子」/saas/factor-request 两入口，
  所有 extends base.html 的页面自动获得），样式用既有 tokens（--tint/--accent），
  ≤960px 降级为顶部横排；当前页高亮由 base.html 公共 JS 按路径标记。
- 反馈（需求 1）：新表 `feedback(id,user_id,content,page,contact,created_at)`。
  **仅登录用户可提交**（游客 401 并引导登录；决策记录见 06 日志）；
  content 必填 ≤2000 字，page/contact 可选；单用户每日 20 条上限（429）。
  端点：POST/GET /api/saas/feedback（本人列表）；管理台只读
  GET /api/saas/console/feedback + console.html 新「反馈」tab。
- 申请新因子（需求 2）：独立页 /saas/factor-request（因子名称* / 计算公式 /
  用途 / 关联策略），复用既有 POST /api/saas/factor-requests（幂等迁移
  factor_requests 补 formula/purpose 两列，旧载荷兼容）；页内含「我的申请」
  列表（状态徽章）。支持 ?factors=a,b&strategy=x 预填（缺因子弹层跳转来源）。
- 缺因子拦截（需求 3）：①NL 入口——编译返回 missing_factors 弹层标题改为
  「当前数据库中不含此因子」，新增「去申请新因子 →」跳转按钮（预填因子+策略名），
  保留原「提交因子需求」快捷提交。②向导/YAML 兜底——startRun 校验段新增
  unknownYamlFactors()：解析 YAML factor_fields 别名，与已加载因子目录比对，
  未知则流水线第①步失败 + 同弹层（目录未加载时跳过，NL 路径服务端已校验）。
- 部署注意：ECS 需先 apply deploy/saas/cloud_schema.sql（幂等，已验证对
  aguhuice_local 重跑安全），再 rsync gui/saas/ 与重启 qre-saas。未 commit。
- 验证：新 tests/test_saas_feedback.py +21（反馈 CRUD/权限三态/日上限/隔离、
  factor 扩展字段回透与审核兼容、新页面元素、全页面侧边栏断言、禁链扫描、
  弹层跳转与兜底校验断言）；全量 pytest 2185 passed + 4 skipped 零回归。
  Playwright（本地 8095 staging + aguhuice_local）截图 13 张存
  /tmp/qre-shots/saas-*.png：侧边栏/反馈提交/申请预填提交/console 反馈 tab/
  缺因子弹层跳转落地/向导兜底拦截，零 JS 报错。

---

## Archive: QRE-SAAS-LARGE-UNIVERSE-GUARD (公网 SaaS 大范围板块/全市场提交耗时护栏)

## Current Status

DONE (implementation; full test suite green; 仅本地+staging 验证、未部署 ECS；awaiting user-approved git finalization)

## Task Note

- 背景：公网新建策略页选大板块/概念或全部 A 股（5531 只）提交全量回测耗时
  分钟级起，lab 版早有护栏，SaaS 侧缺失。
- 阈值口径（与 lab 版一致）：universe.py `LARGE_UNIVERSE_THRESHOLD=3000`；
  全部 A 股恒提示；板块/概念成员数 >3000 提示；指定代码/随机 N（≤2000）不触发。
- 计数来源：板块成员数用 /api/saas/universes 既有 `items[].count`；全部 A 股
  补新元数据字段 `all_a_count`（universe.py 新 `all_a_count()` =
  reference.stock_basic 行数）；`scripts/sync_saas_metadata.py` 生成逻辑更新，
  deploy/saas/metadata.json 已重生成；/api/saas/universes 双路径透出，缺失
  降级 None。
- 前端 saas/templates/new.html：流水线第③步提交 full job 前弹
  `#big-univ-modal`（12 号规范 .modal-mask/.modal 组件，非原生 confirm），
  文案含预计股票数与「几分钟到十几分钟」；确认才提交，取消收起流水线。
- lab 侧零改动。测试 +3（test_gui_saas.py metadata 透出+降级、
  test_gui_saas_pages.py 弹层断言、test_gui_lab.py all_a_count fake engine）。
  全量 pytest 零回归。未 commit；未部署 ECS（metadata.json 需随部署 scp，
  见 sync_saas_metadata.py docstring 命令）。

---

## Archive: QRE-SAAS-SYMBOL-UX (股票代码规范化/显示脱敏 + 超额收益修复 + per-symbol 产物回传打通公网个股详情 + 板块弹层修复)

## Current Status

DONE (implementation; deployed to ECS via rsync 临时部署（最终 git pull 对齐由用户做）; full test suite green; awaiting user-approved git finalization)

## Task Note

- A 代码规范化：`gui/saas/symbol_norm.py`（新，纯函数：normalize_ts_code /
  normalize_ts_codes / strip_ts_suffix / resolve_ts_code；60/68→SH、00/30→SZ、
  4/8/920→BJ；非法代码 ValueError 中文友好报错）。POST /api/saas/jobs 在游客校验
  之前规范化 params.codes 并落库（内部存储/API 保持带后缀原样）。
  显示脱敏：base.html 公共 `dispCode()` 剥后缀；symbols.html / job.html 下钻 /
  symbol.html 标题与 URL 一律无后缀（URL /saas/jobs/<id>/symbols/000001，API 端
  resolve_ts_code 先按本任务实际交易个股匹配、再按号段推断，非法 400）。
  8081 lab 侧零改动。
- B 超额收益「-」：根因是引擎 shared_cash 模式 strategy_performance 恒写
  buy_hold_return=None（8081 同数据同样「—」，非公网独缺）。修法在 worker
  runner._fill_excess_return：excess 为空时按实际交易个股区间等权买入持有补齐
  （附 buy_hold_note 口径说明），DB 不可用保持 None。存量 8 条 completed job
  （1/2/3/7/8/15/16/17）已用本地行情库算好经 psql 回填 ECS results.chart_data。
- C per-symbol 产物回传（ECS 无行情库的打通方案）：worker runner
  build_symbol_detail_files——回测后对实际交易个股逐个 build_lab_symbol_detail，
  剔除基准序列（任务级 chart_data 已有，ECS 按个股净值日期对齐注入）后 gzip 写
  `<output_dir>/_symbol_details/<ts_code>.json.gz`，登记 artifacts 随既有
  result/files 通道上传（15MB 上限，按 |总净盈亏| 降序截断；collect_result_files
  让 _symbol_details 优先进 20MB 清单）。ECS api_result_symbol_detail 优先读
  上传 gzip，缺失回退本地 build（staging 不变）。saas/templates/symbol.html 重写
  对齐 lab 版个股页模块（概述 7 卡 → 收益曲线+区间五卡 → 交易磨损 →
  日K+买卖点+因子副图 → 交易明细 → 下单记录 → 失败订单），旧任务无产物优雅降级。
- D 板块弹层：job.html 下钻表补齐 lab 版 10 列 + 列头排序（null 恒排末位）+
  截断提示；点击个股行跳个股回测详情（此前无响应）。
- 部署/验证：rsync 6 个 saas 文件到 ECS + restart qre-saas；本地 restart
  qre-saas-worker 生效 runner；公网 demo01 实测 job 19 全链路（提交裸代码
  000001/600519 → worker 回测 → 产物回传 → 页面全模块渲染，截图
  /tmp/qre-shots/pub-*.png，零 JS 报错）。
- **顺手修生产事故**：ECS PG workers 表（E1-E3 迁移所建）未授权 aguhuice，
  worker claim 全部 500（任务停摆）——已 GRANT 修复并加默认权限，心跳恢复。
- 测试：tests/test_saas_symbol_ux.py +31；test_gui_saas.py 一处断言更新
  （非法后缀 400 / 无交易合法代码 404）。全量 pytest 零回归。
- 未 commit。恢复命令见 16 号文档第 5 节运维速查。

---

## Archive: QRE-SAAS-ADMIN-TUNNEL (SaaS 管理台撤公网改 SSH 隧道访问 + PG 每日备份；方案 A，用户拍板)

## Current Status

DONE (implementation; deployed to ECS; full test suite green; awaiting user-approved git finalization)

## Task Note

- 2026-09-27 追加 QRE-SAAS-UI-ALIGN-FIX（用户验收发现公网与 lab 版 UI 差距，已部署）：
  顶栏对齐 lab 版（品牌 15px/700 深色、纯文本导航 14px 灰、无胶囊/激活底色、hover 主紫）；
  入口卡选中态补「标题+描述变主紫」（lab 版实测为 style.css .entry-tab.active 遗留蓝
  #1E40AF，SaaS 用 var(--accent) 等效）；回测区间修 `input{width:100%}` 撑破
  .date-input（加 .date-input{width:auto}），日历弹层与 lab 版一致。改动全部在
  saas/templates/base.html 覆盖块；禁链注意：CSS 注释里 "8081" 也撞
  TestNoAdminLinks，用「lab 版」代称。随本轮部署后公网「管理台」入口同步消失
  （注入 JS 删除生效），/saas/console 保持 404。Playwright 截图 /tmp/qre-shots/。
- nginx（仓库 deploy/landing/nginx-aguhuice.conf，已 scp 同步线上并 nginx -t / reload）：
  `location = /saas/console`、`= /api/saas/console`、`/api/saas/console/` 直接 return 404。
  实测：公网 /saas/console → 404、/api/saas/console/overview → 404、/saas/new → 200；
  ECS 本机 127.0.0.1:8090/saas/console → 200（隧道通路）。
- base.html 删除顶栏「管理台」注入 JS；tests/test_gui_saas_console.py 断言反转为不注入。
  坑：注释里写 "deploy/saas/admin-tunnel.sh" 含子串 "/admin" 会撞禁链断言，须改写措辞。
- 隧道：deploy/saas/admin-tunnel.sh（ssh -N -L 9090:127.0.0.1:8090 root@47.119.127.40），
  浏览器开 http://localhost:9090/saas/console，管理员账号正常登录。
- PG 备份：ECS root cron `17 3 * * * /srv/aguhuice/backups/pg-backup.sh`（pg_dump custom，
  保留 7 天）；本地 WSL cron `23 4 * * * .../deploy/saas/pull-ecs-backup.sh` scp 拉最新
  dump 到 ~/quant-workspace/backups/ecs-aguhuice/（留 7 份）。两端手动触发已验证
  （aguhuice-20260927-105046.dump，两端均 300,547B）。
- 全量 pytest 2130 passed + 4 skipped 零回归；check-progress-docs.sh 通过。
- 未 commit。恢复命令见 16 号文档第 5 节运维速查。

---

## Archive: QRE-SAAS-ADMIN-E1E3 (SaaS 后台管理：E1 总览 / E2 用户与因子审核 / E3 worker 运维)

## Current Status

DONE (implementation; full test suite green; awaiting user-approved git finalization)

## Task Note

按 15 号文档 E 阶段实现 SaaS 管理后台（本地开发，不部署）：

- schema（deploy/saas/cloud_schema.sql 幂等迁移）：users + role/status 两列；
  新 workers 表（claim/heartbeat 时 upsert，3 分钟阈值判在线）。
- 权限：users.role='admin' 判定；_require_admin 门禁（401/403）；禁用账号
  登录 403 + 既有 session 立即失效；/api/saas/me 返回 is_admin。
- 管理 API 前缀 /api/saas/console/*（不用 /admin——禁链纪律含注释，决策入
  06 日志）：overview / users（tier 调整、禁用恢复）/ factor-requests 审核
  （approve/reject+note）/ workers / jobs（失败查看、retry 回队、cancel）。
- 页面 /saas/console（console.html 五 tab，lab-theme 组件规范）；顶栏
  「管理台」入口仅 is_admin 时注入（base.html 公共 JS）。
- 测试管理员账号：先正常注册再 SQL 提升——
  `UPDATE users SET role='admin' WHERE email='<邮箱>'`；本地测试用例使用
  admin@example.com / boss@example.com（测试临时库，非真实账号）。
- 测试：tests/test_gui_saas_console.py +12；全量 2130 项零回归
  （test_gui_risk_report 一次瞬时失败复跑即绿，同 09-20 flake 记录）。
- 未 commit。E3 裁剪留后续：worker 指令下发、家里 PG 状态卡（需 worker 协议扩展）。

---

## Archive: QRE-UI-DESIGN-SYSTEM-DOC (UI 设计系统文档：8081 lab 冻结版蒸馏为自包含规范)

## Current Status

DONE (documentation only; awaiting user-approved git finalization)

## Task Note

重写 docs/agent/12_UI_STYLE_GUIDE.md（8.6KB→25.3KB）：设计 tokens
（色板/字体/圆角/阴影全量色值）、布局体系（页面骨架/栅格/36px 行内控件
等高硬规则）、组件库（按钮 7 变体/表单/折叠区/三入口卡+PCB/徽章/toast/
弹层/表格排序/日历/流水线/磨损条）、ECharts 图表约定（系列配色硬规则、
主图双 grid、treemap 三档显隐、K线买卖点）、动效规范（reduced-motion
硬规则）、降级语义、禁链纪律（含注释也扫）、SaaS 复刻约定。每条标注
源码 文件:行号。8081 lab 侧代码零改动。验证：check-progress-docs.sh 通过。
未 commit。

---

## Archive: QRE-WORKER-RUNNER (A3：worker 执行端闭环——取消传播/两步回传/产物清单/env 新名)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

runner.py +collect_result_files（sha256 清单、20MB 上限、幂等覆盖）；
daemon.py 取消传播（心跳见 cancel_requested → fail(canceled) + 丢弃结果，
引擎单体不可中途杀的取舍已注释）+ 两步回传（QRE_WORKER_UPLOAD_FILES
默认关）+ claim 长轮询；client.py +upload_files（multipart）/upload_fn 注入
/env 新名优先（QRE_SAAS_BASE_URL 等）；python -m quant_research_engine.worker
入口。服务端顺带修：fail canceled 终态、meta 对 completed 幂等。测试 +4，
worker+saas 55 passed。未 commit。下一步 A4：本地双进程真实端到端
（saas app + daemon 真引擎 smoke job 跑通）。

---

## Archive: QRE-JOB-API (A2：Flask 侧 job API 按 17 号协议改造——claim 长轮询/心跳迁移/两步 result/fail 分类/取消/幂等/惰性回收)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

按 docs/agent/17_JOB_PROTOCOL.md 改造 gui/saas/app.py 过渡版（不另起炉灶）。
schema 幂等迁移（jobs 加 8 列 + 列改名 + 状态枚举 done→completed，旧库升级
实测通过；坑：先 DROP 旧 CHECK 再 UPDATE）。端点：worker claim（长轮询
30s/空响应 200+null/SKIP LOCKED）/heartbeat（progress+message，首跳
leased→running，带 cancel_requested）/result/meta→files（upload_token+
sha256，SAAS_UPLOAD_DIR 落盘）/fail（error_class 分类）；用户
POST/GET /api/jobs、POST /api/jobs/<id>/cancel（queued 直消/执行中置标记/
终态 409）。惰性租约回收（无后台线程）+ 硬超时 expired。/api/saas/* 别名
兼容；worker/client.py 与 saas 模板同步。测试 test_gui_saas.py +11
（TestProtocolA2），全量见 05。未 commit。遗留：claim capabilities 过滤、
parent_job_id 派生 full、文件分块续传（见 05 条目）。

---

## Archive: QRE-BATCH-STREAMING-EMPTYCSV (流式批量回测空 CSV 崩溃修复：EmptyDataError 容忍)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

run 20260914T125635220084（5 年全市场）死于聚合阶段 "No columns to parse
from file"：无交易个股的空 DataFrame（无列）落盘为无表头空文件，磁盘代理
read_csv 读回抛错（非流式路径空 DataFrame 一直在内存所以从不触发）。
修复仅 streaming_batch.py 一处：`_DiskBackedSingleResult._read` 捕获
pd.errors.EmptyDataError 返回空 DataFrame（读侧容忍，字节兼容既有产物）。
测试 +1（空结果个股全链路 write_batch_result 不炸）。失败 run 产物不可信
（共享 output_dir 已被后续 run 部分覆盖且 run_manifest 缺失），建议重跑。
未 commit。前一任务 QRE-BATCH-STREAMING（见下档）。

---

## Archive: QRE-BATCH-STREAMING (批量回测内存峰值控制：流式分块，OOM 7.7G → 实测 299MB@500只×2年)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

OOM 根因（profiling 实锤）：装配器一次性加载全池 frame（500×2y 即 691MB RSS，
5000×5y 膨胀至 7.7G）。修复：新 `portfolio/streaming_batch.py` 流式分块
（QRE_BATCH_CHUNK_SIZE 默认 250；块内跑既有 BatchBacktestEngine → 逐股落盘
→ `_DiskBackedSingleResult` 磁盘懒加载代理 → 释放），gui/engine.py 与
apps/cli.py 的 batch 路径在 >250 只或全市场时走流式，小样本不变；产物格式
零变化（500×2y 产物逐位一致）。tests/test_streaming_batch.py +2，全量
2071+4 绿。未重启 qre-gui-lab（进行中的全市场 run 不动），改动下次 run 生效。
未 commit。前一任务 QRE-LAB-UI-LANDING（见下档）。

---

## Archive: QRE-LAB-UI-LANDING (设计稿 synthesis.html 视觉层与已批准结构调整原位落地 8081 lab 版)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

规范来源 docs/agent/12_UI_STYLE_GUIDE.md；性能依据 13_UI_PERF_NOTES.md。
8080 管理台零改动（diff 只含 lab_* 模板 / gui/lab_result.py / lab 测试 /
新增 lab-theme.css + lab-ui.js + lab_symbols.html）。

- 主题抽到 static/lab-theme.css（tokens/字体/动效/组件类，仅 lab 模板 link），
  交互组件抽到 static/lab-ui.js（PCB 排线 / 日历 / 流水线步骤态）。
- lab.html：三入口并列卡+PCB；预览栏（#strategy-yaml 迁至参数区后为唯一真相源，
  pv-params-line 参数合并行、复制按钮）；param-sname 公共策略 ID（applyNameToYaml
  提交时写入 name，用户手改后不再自动覆盖）；LabUI.attachCalendar 日历（最大可选
  = /api/admin/refresh state.last_data_date，禁未来函数）；唯一「运行回测」流水线
  ①/api/validate（先验 ID 合法字符）→②saveToSandbox+smoke+waitForCheck→③/api/run
  沿用原 payload 与 >3000 只护栏，后端零改动；各入口旧最终按钮（btn-save-smoke/
  wz-save-smoke/wz-fill-editor/btn-validate/btn-run）删除，startBacktest 保留未用。
  记录表加「股票数量」列（原有标的数更名）+ 状态徽章 + 删除改 #run-del-mask 二次
  确认弹层（/api/lab/runs/<id>/delete 不变）。
- lab_result.py：build_lab_chart_data 新增 fees_summary（round_trips.csv 费用列
  全量聚合；缺文件/缺列返回 None 前端整块隐藏）；新路由 /lab/runs/<run_id>/symbols。
  worker 复用该函数（SaaS job chart_data 随之带 fees_summary，纯增量键无回归）。
- lab_result.html：顺序 概述→收益曲线→box-fees 磨损→FRM→归因 treemap→big-link
  个股明细入口；dataZoom 区间卡 rAF 节流；配色换淡紫规范。
- lab_symbols.html（新）：A 层聚合成全量个股表，排序/搜索/完整代码回车直跳。
- lab_symbol.html：顺序 概述→收益曲线（区间卡五卡+滑块 rAF）→box-wear 磨损（该股
  orders/trades 聚合）→K线→交易明细→下单记录→失败订单；配色同步。
- 术语纪律：沙箱/晋升仍禁；「冒烟测试：单股票 × 短期区间」为用户本轮批准文案，
  test_gui_lab 去术语断言已放行「冒烟」一词。
- 测试：test_gui_lab.py / test_gui_lab_result.py 更新 + 3 新用例；lab 65 全绿；
  全量 pytest tests/ -q → 2067 passed + 4 skipped（基线 2065+4，净增 2）。
- 验证：sudo systemctl restart qre-gui-lab 后 /、/lab/runs/<id>(+symbols+symbol)、
  两个静态文件、chart-data 全 200；fees_summary 真值已对账。
- 未 commit。前一任务 QRE-WORKER-ARTIFACT-PERSIST（见 05_PROGRESS）。

## 遗留风险

- 浏览器观感未截图实测（无头环境）：PCB 排线/日历弹层/流水线动画建议人工开 8081 过一遍。
- 流水线第②步 smoke 用策略默认标的（saveToSandbox/smoke 语义），第③步才应用参数区
  区间/标的——与母板 SAAS-011 原流程语义一致，未改。
- 预览栏未做行号/语法高亮（设计稿有）；落地为纯 textarea + 参数合并行，后续可补。

---

<details><summary>历史交接存档</summary>

# Task Handoff

## Task ID

QRE-WORKER-ARTIFACT-PERSIST (缺陷修复：SaaS Worker 回测产物拷回持久存储，/tmp 沙箱丢失导致详情页全空)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

worker/runner.py：execute_job 在 run_backtest 返回后（成功/失败都执行）
调新 `_persist_artifacts`——/tmp 沙箱 output_dir 整体 copytree 到
RUNS_DIR/<run_id>/artifacts/（旧副本先清），record 的 artifacts map 绝对
路径与 output_dir 改写指向持久副本并重写 status.json；/tmp 原件保留。
非沙箱路径不受影响。测试 tests/test_worker.py +2（持久副本存在+路径
改写+删沙箱后 loader 可用+重跑先清后拷；fixture 补 RUNS_DIR 隔离）。
未 commit。前一任务 QRE-SAAS-012（标的范围富化，见下档）。

---

## Archive: QRE-SAAS-012 (8081 标的范围富化：申万行业/东财·同花顺概念/聚类池/通用行业 七组归类)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

新 `gui/universe.py`（只读：list_universes 七组 + universe_members 解析
codes）；lab.py 挂 8081 专属 /api/lab/universes[/members]（_cached TTL，
8080 不挂）；lab.html 标的范围原位改三选单选（全部 A 股/板块概念可搜索
下拉+成员数提示/自定义代码），提交前解析为 codes 传既有 /api/run，
引擎零改动；>3000 只或全市场 confirm 护栏。真库验收：七组数据齐全
（sw1 电子 618、ths CPO 98 等），members 解析正确。测试 +4（20 总），
全量 2063+4 绿。未 commit。遗留：用户 8081 验收；部署 ECS 时 universe
数据源在 Worker 侧（本地大库）直接可用，云端不落明细的设计不变。

---

## Archive: QRE-SAAS-011 (lab 页面原位减法：删「新增因子」tab + 一键回测流程后台化 + 导航清理)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户批评 QRE-SAAS-010 重做模板（「我说过在原页面的基础上进行更改」）；
纠偏：lab*.py 冻结解除，8081 lab 页面原位减法。改动：lab.html 删因子
tab（按钮/面板/TAB3 JS 全块）+ 缺因子改弹窗（POST /api/lab/factor-requests
JSONL 落 outputs/factor_requests.jsonl，TODO(M4) 迁云）+ 「存入沙箱+冒烟」
两按钮统一为「开始回测」（自动 smoke→轮询→通过自动 promote 全量回测，
失败显示人话）+ 可见文案去术语（沙箱/冒烟/晋升 → 我的策略/验证/发布）；
base.html nav 改 block（8080 默认不变），lab 三模板覆盖去 /admin 链接。
gui/lab.py 加 factor-requests 路由。saas/templates（SAAS-010）废弃保留
备查。8080 未动、引擎/worker/security 未动。验收：8081 restart 后首页
200、无禁词/无 admin 链接、/api/lab/runs 200、申请落盘实测。测试
test_gui_lab.py 更新 +1（17 总），lab 相关 107 passed，全量回归见 05。
遗留：用户 8081 验收新首页；ECS 部署；factor_requests 迁云。

---

## Archive: QRE-SAAS-010 (SaaS 前端以 lab 观感重做 + 流程后台化；SAAS-009 方向修正落实)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户 2026-09-07：SaaS 前端以验收过的 lab 页面为蓝本做减法移植
（SAAS-009：自研模板验收不通过）。模板全部重写（gui/saas/templates/，
lab*.py 只读未动）：base.html 换 lab 风 CSS 全套；new.html 两 tab +
策略代码预览（高级）折叠 + 单一「开始回测」（后台静默 smoke→通过自动
提交 full→跳结果页，零「沙箱/晋升/试算」字样，缺因子弹窗保留）；
dashboard 过滤内部 smoke job、无管理面入口；job.html 结果页对齐
lab_result.html（指标卡/meta chips/基准切换+滑块+回撤副图/归因 treemap
三 tab+排行表+下钻静态明细）。保留 SAAS-009 防刷新环修复（bypass 注入
模板，requireLogin 跳过）。CR-0004 追加用户分层构想（仅文档）；
03_ROADMAP 加 Milestone 11。测试 27 passed（+4：新断言 + 零术语词表），
全量 2058+4 绿。8081 lab 未动。未 commit。遗留：用户 8081 观感验收、
ECS 部署（M4）、个股详情页（后续）。

---

## Archive: QRE-SAAS-008 (8081 重定位为 SaaS staging：qre-gui-lab 切换为 SaaS 应用 + 本地 Worker 常驻)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户 2026-09-07 决策：8081 = SaaS staging（预发），ECS = 生产；流程约定
「改动 → 8081 验证 → 用户验收 → 部署 ECS」（已记入 11_AGENT_STATE）。
lab*.py 一行未动，8080 未碰。变更：`qre saas` CLI 子命令；saas app 加
SAAS_STUB_ECHO=1 开关（auth/code 响应带 dev_code，生产严禁）；8081 服务
qre-gui-lab（沿用服务名）ExecStart 切换为 qre saas，env 走
.env.saas-staging（0600，gitignore 已覆盖）；新系统服务 qre-saas-worker
（轮询 8081/5s/只读大库账号）已 enable --now。repo 侧新增
deploy/saas/qre-saas-staging.service 与 qre-saas-worker.service。
端到端已验证（dev_code 登录→smoke→worker done 65s，8080 无恙）。
测试 +2，全量 2054 passed + 4 skipped 零回归。未 commit。
遗留：ECS 部署（M4：OSS/备案/生产 env）；8080 因子审核界面（SAAS-007 后续）。
用户使用说明见 05_PROGRESS.md QRE-SAAS-008 条目与本文件下方。

### 使用说明（staging 日常）
- **免登录**（2026-09-07 用户决策，SAAS_AUTH_BYPASS=1）：直接打开
  http://<本机>:8081/saas/ 即可用；/saas/login 自动跳工作台。
  所有操作归属默认用户 staging@local。生产 ECS 保持验证码登录
  （bypass 严禁开启）。
- 任务进度：http://<本机>:8081/saas/ 自动刷新。
- 服务状态：systemctl status qre-gui-lab（SaaS 应用）/
  qre-saas-worker（Worker）；日志 journalctl -u qre-saas-worker -f。
- 改了代码要验收：sudo systemctl restart qre-gui-lab（worker 按需）。

---

## Archive: QRE-SAAS-007 (SaaS 因子治理：缺因子申请人工审核通道 + 页面链接清理)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户新规：用户对因子零增/改/读操作；缺因子引导换策略 + 可申请入库
（运营按热度人工审核离线计算）。判断：saas 无独立因子浏览入口（快速
向导的因子下拉=构建策略必要交互，保留）；四模板本就无 /admin·8080/
8081·factor-admin·factor-create 链接（已加参数化断言固化）。实现：
cloud_schema.sql +factor_requests 表（幂等）；POST/GET
/api/saas/factor-requests（24h 同集合去重 409、用户隔离）；new.html 缺
因子模态框（missing_factors 触发，「换个策略」/「提交因子需求」→
已提交）；dashboard.html 底部折叠「我的因子申请」状态列表。未 commit、
未动 8080/8081/lab*.py、未改 NL 编译器。测试 +10（API 4 + 禁链·元素 6），
test_gui_saas_pages.py 21 总。遗留：8080 管理台审核界面（后续任务）。
前一任务 QRE-SAAS-004（四功能前端 + 归因打通，见下档）。

---

## Archive: QRE-SAAS-004 (CR-0004 M1：SaaS 四功能前端——登录/工作台/新建回测/结果页)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部在 `gui/saas/` 内：templates/{base,login,dashboard,new,job}.html +
saas/app.py 挂 4 个页面路由与 2 个 API。vanilla JS 无框架（同 admin.html
风格），echarts 复用 gui/static/echarts.min.js（saas app static_folder 指向
共享目录，不双份）。页面：/saas/login（验证码两步、token localStorage、
登录即注册）；/saas/（任务列表+状态徽章+每 5s 自刷+失败原因）；
/saas/new（NL tab：示例 chips→POST /api/saas/nl/compile→YAML 可编辑；
向导 tab：/api/saas/factors 二级下拉+出入场阈值+高级选项折叠；强制先
smoke 试算通过才允许提交 full）；/saas/jobs/<id>（指标卡+净值 vs 基准+
回撤图，数据全来自 result.chart_data，5s 轮询，下载按钮 artifacts 空隐藏
TODO(M4)）。API：/api/saas/nl/compile 直接调既有 compile_nl（含
factor_correction 纠错层，LLM key 服务端 env）；/api/saas/factors 直接调
factor_wizard.build_factor_groups；GET /api/saas/jobs/<id> 收紧为登录+属主
校验（他人 404）；列表加 data_until。未 commit、未动 lab*.py/8080。
测试 tests/test_gui_saas_pages.py +11（页面 200/关键元素/echarts 静态/
NL 与因子路由 401·400·200·503/groups 结构）；既有 saas/worker 测试补
鉴权头。全量回归见 05。遗留：下载按钮接 OSS（M4）、真实浏览器观感
走查。注：归因热力已同日补齐（见 05 QRE-SAAS-004 补条目）——runner
chart_data 补 tag_analysis（trim：板块聚合全量+个股 TOP/BOTTOM 各 50），
job.html 加行业 treemap + 板块下钻 + 个股贡献榜。
另：同日完成 QRE-SAAS-M4-DRYRUN 真机闭环演练（详见 05 顶部条目）——
SaaS app + Worker 本地同机全链路真实跑通（真实 DeepSeek NL 编译 +
smoke/full 两 job done + 归因数据齐全），修复 yaml_guard experiment 键
白名单漏项（NL 产物含 market_profile/frequency 会被误杀）+ StubSender
SAAS_STUB_LOG 落盘开关。结论：达到「备案下来即可部署」的代码状态。

---

## Archive: QRE-SAAS-005 (CR-0004 M2：NL 生成代码沙箱加固——表达式 AST 白名单 + Docker 隔离执行器)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

威胁模型：NL 写策略=声明式 YAML 无代码执行，但信号表达式求值器
（evaluation/signals.py）允许任意 getattr/方法调用（注入面）；NL 写因子
生成 Python 源码在 indicators_tushare subprocess 执行（唯一真执行点，
已有 AST 白名单但无执行隔离）。实现（全新文件，引擎零改动）：
①`security/yaml_guard.py`——validate_expression AST 白名单
（禁裸调用/裸属性/下划线标识符/字符串常量/下标等，方法链白名单 30 个）
+ validate_strategy_yaml 严格 schema（节/键白名单、类型、因子引用标识符
+schema 白名单防 SQL 注入）；接线 worker runner.execute_job 执行前强制，
不过 → job failed。②`worker/sandbox.py`——run_sandboxed（禁网/512m/
1cpu/100 pids/只读根/nobody/120s 强杀按名 kill/输出限 1MB），docker 前缀
可注入（SANDBOX_DOCKER_SUDO）。③deploy/saas/sandbox.Dockerfile
（python:3.12-slim+pandas/numpy/pandas_ta，本次未实机构建，测试用
python:3.12-slim 直跑）。未 commit、未动 lab*.py/8080、未碰
factor_correction.py。测试 tests/test_security_sandbox.py 34 passed
（schema 正反例 + 真容器禁网/内存/超时/只读 6 条）。遗留：因子冒烟
沙箱化接入 factor-create 流程（禁网下数据须预导出挂载，M4 时定）、
沙箱镜像实机构建、SaaS 前端入口挂 yaml_guard（8081 裁剪切片）。

---

## Archive: QRE-SAAS-M3 (CR-0004 M3：Worker 客户端本体——出站轮询云端任务、本地跑回测、结果回传)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

新 `src/quant_research_engine/worker/` 包（client.py / runner.py /
daemon.py）+ `apps/cli.py` 新增 `qre worker` 子命令（纯追加，与
gui/barometer 同模式）+ `deploy/saas/qre-worker.service`（user 级模板，
注释含安装命令，未安装）。lab*.py / 8080 零改动，未 commit、未重启服务。
①client.py CloudClient：stdlib urllib（venv 无 requests），超时 30s +
指数退避重试（仅传输错误/5xx，最多 3 次，4xx 抛 CloudError）；env
SAAS_CLOUD_URL/SAAS_WORKER_TOKEN/SAAS_WORKER_ID；request_fn 注入点供测试
直连 saas app test_client。②runner.py execute_job 复用既有链路不 fork：
`gui.engine.run_backtest`（同 8081 批量回测入口）；smoke=既有 precheck
（20 股+180 天），full=全量；summary=extract_run_summary、
chart_data=lab_result.build_lab_chart_data；artifacts=[] TODO(M4) OSS；
data_until=净值曲线末日。③daemon.py：轮询 lease（默认 15s）→ 执行 +
心跳线程（默认 60s）→ done/failed 回传；异常全兜底不死；SIGTERM 等手头
任务完成再退（TimeoutStopSec=900 兜底）。本地大库：引擎数据层全 SELECT
只读（已核查 data/postgres/assembler/portfolio/risk_report，写点均为本地
文件），QRE_MARKET_DB_URL 注入 qre_worker_ro 只读账号即可，零改造。
测试 tests/test_worker.py 10 passed：端到端 done 闭环（mock 引擎层 +
真实 lab_result 组装）、daemon 单轮/空轮、失败回队→耗尽、心跳线程、
重试/放弃/4xx 不重试/错 token、CLI 注册。tests/test_gui_*.py+test_cli.py
909 passed 零回归。遗留：OSS 产物上传（M4）、沙箱加固（SAAS-005）、
真实云端联调（M4 部署后）、systemd 实机安装。

---

## Archive: QRE-SAAS-006 (CR-0004 M2：SaaS 登录鉴权——验证码登录 + Bearer session + 限流/配额，替换 X-User-Id 占位)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部改动限于 `gui/saas/app.py`、`deploy/saas/cloud_schema.sql`、
`tests/test_gui_saas.py`；lab*.py / 8080 零改动，未 commit、未重启服务。
①发送层可插拔（SAAS_AUTH_CHANNEL）：email=默认（smtplib STARTTLS 10s
超时，SAAS_SMTP_* 配置）；sms=占位抛「短信通道未开通」；stub=测试通道
记录到 app.extensions['sent_codes']。②新路由：POST /api/saas/auth/code
（6 位码、5 分钟、sha256(code:target:salt) 落 sms_codes、发送失败 502、
不暴露注册态；限流：同 target 60s、同 IP 10 次/小时，内存计数重启清零）、
POST /api/saas/auth/login（compare_digest 校验最新未用未过期码→一次性
used→无用户自动注册 email/phone 按 @ 判定→sessions 表 30 天 token）、
GET /api/saas/me。③jobs 用户侧路由切 Bearer token；X-User-Id 保留为
SAAS_DEV_AUTH=1 dev 后门（默认关）。④配额：当日任务数（含 smoke）>=
quota_daily → 429。⑤schema 幂等迁移：users+email（部分唯一索引）/
phone 可空、sms_codes+channel（phone 列实存 target，注释说明）、
新增 sessions 表；已实测连 apply 两次幂等。worker token 鉴权不动。
测试 22 passed（+11：全流程/错码/过期/复用/限流两档/502/无 token/
dev 后门开关/配额）；tests/test_gui_*.py 子集 584 passed 零回归。
遗留：图形验证码（TODO 注释，内测省略）、Worker 客户端（M3）、
8081 前端四功能 UI、生产 SAAS_AUTH_SALT/SAAS_SMTP_* 配置。

---

## Archive: QRE-SAAS-001/002 (CR-0004 8081 SaaS MVP M1 切片：云小库 schema + 云侧任务队列协议 + QRE-SAAS-004 骨架 app)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

全部为新文件，既有 8080/8081 路由与冻结 lab*.py 零改动、未 git commit、
未重启任何服务、未碰沙箱。①QRE-SAAS-001：`deploy/saas/cloud_schema.sql`
五表（users/sms_codes/strategies/jobs/results）幂等可 apply（前置已验证）。
②QRE-SAAS-002 + SAAS-004 骨架：新 `src/quant_research_engine/gui/saas/`
（__init__.py + app.py），`create_saas_app()` 独立 Flask app，路由全挂
`/api/saas/`：用户侧 POST /api/saas/jobs（yaml+params+kind=smoke|full，
X-User-Id 占位鉴权、用户不存在自动建行 phone=pending_<id>，登录为
QRE-SAAS-006）、GET /api/saas/jobs[/<id>]（状态/error/done 时 result
摘要，列表 50 倒序）；Worker 侧 POST /api/saas/worker/jobs/lease
（X-Worker-Token 校验 env SAAS_WORKER_TOKEN，未配置 503；事务内
SELECT ... FOR UPDATE SKIP LOCKED 取最旧 queued 或 lease 过期且
attempts<max_attempts 重排 → attempts+1/leased/15min 租约/leased_by，
返回含 strategy yaml+params）、.../heartbeat（顺延 15min 校验 leased_by）、
.../result（done 写 results ON CONFLICT(job_id) 幂等 + job done；
failed 则 attempts 耗尽置 failed 否则清租回 queued）。DB 走 env
SAAS_DB_URL，SQLAlchemy text() 全参数化，驱动复用项目既有 psycopg3
（postgresql+psycopg:///）。测试 tests/test_gui_saas.py +11（真实本地
PG 临时库：psql 以 van 经 unix socket 建/销库 + apply schema + 每用例
TRUNCATE）：全生命周期、lease 过期重排、attempts 耗尽置 failed、token
错 401、token 未配置 503、用户隔离、他人心跳/回传 409。新测试 11
passed；全量 `pytest tests/ --ignore=tests/test_gui_saas.py` →
1963 passed + 4 skipped 零回归。遗留：Worker 客户端本体（M3）、登录
鉴权（QRE-SAAS-006）、8081 前端四功能裁剪 UI。

---

## Archive: QRE-NL-FACTOR-AUTOCORRECT-001 (NL 编译链路因子名自动纠错层：存在性校验 + 保守自动替换 + 候选提示 + prompt 注入真实目录)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

痛点（05 已记录）：DeepSeek 编造库中不存在的因子列名（rsi14/MACD 等），
NL 编译产出 YAML 因因子缺失而失败，用户只见红色报错。本任务在
引擎/编译器侧（8080/8081 共用，8081 gui/lab*.py 页面仍冻结）落地：
①新 `gui/factor_correction.py` 纯函数层——`auto_fix_column`（保守：
归一化等价 rsi14→rsi_14 / 唯一距离 1 且次优差距 ≥3 / 唯一前缀，
其余一律不动给候选）、`suggest_similar_columns`（归一化编辑距离
Top-5）、`correct_factor_fields`（同表候选优先，同表空则跨标准因子表
兜底，列名对表写错直接换表）、`COMMON_FACTOR_TARGETS` 常用清单、
中文提示格式化。②`gui/nl_compiler.compile_nl`：missing_factors 判定前
先纠错——全部纠正成功则重写 YAML 正常返回（warnings 标注「已自动纠正
X→Y」，响应带 corrections）；仍有未解决项则照旧入补因子队列，error 从
「编译失败」改为 actionable 提示（每因子 Top-5 候选 + 常用因子清单），
响应带 suggestions。③prompt 注入：build_system_prompt 追加「严禁编造
因子名」硬约束 + COMMON_FACTOR_TARGETS 常用已落库列。④
strategy_lab_routes 手工 YAML 通道（/api/strategies/create mode=manual）
同样先纠错再入队，8080/8081 共享生效。测试 +17
（tests/test_gui_factor_correction.py：编造名纠错/精确匹配不动/无匹配
给候选/歧义前缀不纠正/prompt 注入/compile_nl 集成），全量 1960
passed + 4 skipped（1943 + 17）。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-006 (「聚类动量」页 v5 榜单可读性：横向滚动 + 首列 sticky + 精简列开关 + 详情面板上移)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户反馈：concept 榜单 17+ 列横向溢出挤压、点池名后详情在页面最底部
需长滚。修复（admin.html + style.css，pool_momentum.py 零改动）：
①momTable 包 .mom-scroll 横向滚动容器 + 首列池名 sticky（热力行首列
background:inherit，行仅 heat 非空才输出 style）；②默认精简列（池名/
股票数/当前窗口 fwd/速度/加速度/共振/回避徽章/事后×3），扩展列标
mom-col-x + .mom-compact 隐藏，「#btn-mom-cols 展开更多列」开关切全量
列（colspan 随视图 concept 9/20、state 13/24）；③删除底部
data-section="mom-detail" 折叠区，新 #mom-detail-panel 固定在
#mom-summary 之下、榜单之上（标题 + #mom-detail-close 关闭按钮 +
scrollIntoView，点其他池原地替换）；④成员明细包 .mom-members-scroll
限高 420px 内部滚动（表头 sticky 沿用全局规则）。测试 +2（78 总：
v5 模板标记 + CSS 断言），全量 1942 passed + 4 skipped。qre-gui 已重启
active；curl /admin 200 含新标记、overview（真库 2026-09-03：concept
1066/state 14）与 detail API 200。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-005 (「聚类动量」页 v4 底部减速回避名单：⚠ 回避徽标 + 顶部回避卡 + 声明卡补句)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

依据 M7 全历史结论（fwd_ret_3 最弱 Bottom10 未来 3-5 日继续跑输约
0.2%/日，NW t=−3.86，FDR q=0.001；顶部信号全部无效）：纯函数
compute_bottom_avoid（组内 fwd_ret_3 最低 10 个标 avoid，None 与
n_stocks<10 剔除）+ avoid_list 摘要；overview payload 加 avoid/
avoid_bottom_n/avoid_min_stocks，历史回看按选中日截面保持 point-in-time；
榜单行加「⚠ 回避」徽章（title 注明依据）、顶部 #mom-avoid 汇总卡
（点击跳详情）、声明卡补「顶部无选股价值，主要价值=底部回避名单」。
测试 +11（76 总），全量 1940 passed + 4 skipped。qre-gui 已重启
active；真库 2026-08-31 concept 回避名单居首「申万L3:疫苗」−5.73%。
未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-004 (「聚类动量」页 v3 历史回看：日期选择器 + 事后验证列 + 验证摘要条)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

overview 加 trade_date 参与 fwd 可选日期列表（下拉切换 point-in-time 榜单）；
纯函数 compute_post_returns（post_w = T 后 w 日 fwd_ret 复利，不足窗口→NULL
未满窗口）加「事后3/5/20日」三个可排序列；纯函数 accel_top_summary（加速度
Top10 post_5 均值/中位/胜率 vs 全体，按 pool_type 各一行）渲染摘要条；
detail 加 end_date、members 传选中日期。测试 +11（65 总），全量 1929
passed + 4 skipped。qre-gui 已重启 active；真库：2025-09-05 concept 加速度
Top10 post_5 +0.19% vs 全体 +0.88%（该日无超额，如实呈现）。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-003 (「聚类动量」页升级 M7 v2 前瞻口径：fwd_ret 主口径 + 事件池统计)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

M7 v2 新列（fwd_ret/fwd_ret_3/5/20/50/next_premium/survive_3/5/win_rate_1）
接入 8080 聚类动量页：速度/加速度/热力/共振全部切 fwd 口径
（compute_acceleration/compute_heat 加 metric 参、resonance 判 fwd），
回看 ret_w 降级对照列；overview 默认展示最近 fwd 已补齐日 + fwd_lag
红色提示（末日 NULL=正常 T+1 滞后）；state 分区 artifact 池加事件 4 列
（has_event 行级标记，对标同花顺涨停复盘）；详情主线 fwd、回看浅色辅线；
声明卡改写。测试 +9（54 总），全量 1918 passed + 4 skipped。qre-gui 已
重启 active；真库实测榜单日 2026-08-31，concept fwd_ret_3 榜首
「昨日打二板以上表现」+15.38%。未 git commit，等用户审批。

---

## Archive: QRE-GUI-POOL-MOM-002 (「聚类动量」页三项优化：池内个股明细 / 表头排序 / 行热力色阶)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

①新 API /api/admin/pool-momentum/members（pool_type/pool_key/trade_date，
后者缺省=最新）：成员 concept=cluster.company_tags 快照、state=当日
daily_tags；`compute_member_metrics` 纯函数即时算 stock_daily（51 日窗口，
复权/vwap/均量比口径与 M7 管线逐位一致——华为概念成员等权 ret_3 与池表值
完全相等、有效成员 770==n_stocks）；名称 reference.stock_basic 降级可选。
②主榜单全部数值列+成员表全列点击排序（▼/▲，None 恒末位，前端
momGenericSort / Python 侧同口径 sort_rows）。③行热力：compute_heat
（ret_w 截面分位 heat∈[-1,1]，红涨绿跌）随窗口切换重算；「长弱短升」
改左侧绿边+加粗避免与热力背景冲突。测试 +21（45 总），全量 1909 passed
+ 4 skipped。qre-gui 已重启 active，curl 实测全 200。未 git commit。

---

## Archive: QRE-GUI-POOL-MOM-001 (8080 管理台新增「聚类动量因子研究」tab：cluster-ashare M7 池动量管线只读展示)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

用户直接指派 demo 只读页。新 `gui/pool_momentum.py`（market_risk.py 同款
只读数据层：_store/_cached TTL 300s/自降级）只读 `cluster.pool_momentum_daily`；
纯逻辑（rank_desc 竞争排名 / compute_acceleration 速度=ret_50 排名·
加速度=ret_50 排名−ret_3 排名·长弱短升=速度后半区且短窗前 10% /
resonance_flag 价量三同正 / sort_by_acceleration）零 DB 可测。
app.py +/api/admin/pool-momentum 与 /api/admin/pool-momentum/detail；
admin.html +「聚类动量」tab（偏差声明卡：concept 池当前快照前视偏差
demo 接受、state 池 point-in-time 无偏差；窗口 3/5/20/50 切换；concept/
state 两榜单含 4 窗 ret + 4 窗 vwap_ret + vol_chg + 速度/短窗排名/加速度/
共振标记；长弱短升高亮；点击池名看 250 日 7 序列 inline SVG，复用
riskSvgLine，零新前端框架）；style.css 纯追加。8081 零改动。
测试 +24（tests/test_gui_pool_momentum.py）；全量 1888 passed + 4 skipped。
qre-gui 已重启 active，/admin 200、两 API 真库实测正常
（2026-09-01：concept 1066 / state 14）。未 git commit，等用户审批。

---

## Archive: QRE-GUI-LAB-RESULT-030 (B 层关键词换代：jieba 碎片词 → 东财+同花顺概念板块成分；8080 总览加「概念标签源」卡片)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

跨仓任务（cluster-ashare 改造 + 本仓消费/展示）：①cluster-ashare 新
`src/tags_lb_concept.py`（东财 akshare + 同花顺自带分页抓取双源采集，
layer='B' source='em_concept'/'ths_concept'，upsert 幂等 + 失败板块
extra_passes 补抓），`scripts/drop_lb_jieba.py` 删除旧 NLP B 层
（97,838 行 + 5,206 字典行，已执行），`tags_lb.py` 标 DEPRECATED，
`run_mvp1 build-tags` 周更接线（deploy 注释同步）。②本仓 admin.py 新
`overview_concept_tags`（B 层 source 分布，自降级），app.py 总览 payload
加 concept_tags，admin.html 加「概念标签源（B 层）」卡片。③8081 归因端
零改动验证：tag-analysis B 层已显示真概念词（华为概念/CPO概念/PCB 等）。
测试：本仓 1840 passed + 4 skipped（+7）；cluster-ashare 204 passed（+12）。
遗留：东财接口当日长时段断连，504 板块入库 290，网络恢复后重跑幂等补齐
（方法见 cluster-ashare README 已知限制）。

---

## Archive: QRE-GUI-LAB-PORT-017 (回测台新端口移植：新增策略 + 回测管理两页面 → 独立 Flask 应用 @8081)

## Current Status

DONE (implementation; awaiting user-approved git finalization)

## Task Note

纯移植，零优化/美化/功能增删。新 `gui/strategy_lab_routes.py`::
`register_strategy_lab_routes(app)` 共享注册（create_app 尾部调用，
路由表与 git HEAD 逐条相等 59/59）；新 `gui/lab.py`（create_lab_app /
launch_lab_gui）+ `templates/lab.html`（「新增策略」自 index.html
strategy tab、「回测管理」自 admin.html onboard tab 脚本精确切片，
含排序 JS/搜索/toggle/删除/gate 徽标，附 /runs 页面）。CLI：
`qre gui --lab`（默认 8081，--port 优先）；`qre gui` 不变。systemd：
`deploy/hardened/qre-gui-lab.service`（端口 8081、
SyslogIdentifier=qre-gui-lab）已 sudo 安装 enable --now
（enabled/active）。测试 `tests/test_gui_lab.py` +12；全量
`uv run pytest -q` → 1807 passed + 4 skipped（基线 1795 + 12）。
冒烟：8081 / 双 tab、/api/admin/refresh stopped 118/118（与 8080
一致）、/admin/strategy/<id> 200；8080 / 与 /admin 200。两个 service
均已重启。无 CR（纯移植无设计决策）。未 commit。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部。
上一任务：QRE-GUI-SORT-016 / QRE-GUI-DERIV-FRESH-015（见 05/09）。

---

## Archive: QRE-DERIV-ADAPTER-013 (衍生品数据适配层：yc_curve/cb/opt 三个只读 loader + 示例管道，CR D1.5/D2.2/D3.2)

## Task Note

新 `src/quant_research_engine/data/derivatives.py`（只读适配层，QRE 唯一读
derivatives schema 的代码）：`load_zero_curve`（yc_curve 即期 8 节点，
yield%÷100 视为年复利→连续复利近似披露；当日无数据取 ≤trade_date 最近日，
`latest_curve_date` 披露实际日期）、`load_cb_terms`/`cb_cashflows`/
`cb_bond_floor`（现金流近似：常数票息/期限取整付息网格/面值到期无赎回
溢价/利差默认 100bp → convertible_bond_floor + cb_daily.bond_value 对比）、
`load_option_chain`（settle JOIN opt_basic，T=actual/365，r=0.25y 节点，
逐合约 implied_vol，平值隐波断言 (1%,150%)）。已知缺口：库内无 ETF 日线
（510050.SH 不在 stock_daily/index_daily），标的价缺失时须传
`underlying_price`，示例脚本用平值 put-call parity 反推（披露）。
示例 `scripts/derivatives_adapter_smoke.py` + 测试
`tests/test_data_derivatives.py` 15 个（纯函数 11 + DB 冒烟 4 无库 skip）。
冒烟 2026-08-21：曲线 1.164%–2.110%；5 只存续转债债底 99.14–101.74 vs
bond_value 105.4–111.2（差异主因到期赎回溢价未含，可解释已披露 CR §11）；
50ETF 平值 K=3.0 call/put IV 13.67%。全量 1795 绿 + 4 skipped
（基线 1784 + 11 净增）。未 commit、未重启 qre-gui。详见
09_CODING_HANDOFF.md 顶部、05_PROGRESS.md 顶部、CR §11。
上一任务：QRE-GUI-DERIV-CARD-012 / QRE-RISK-GUIDE-011（见 05/09）。

---

# Task Handoff (archive: QRE-RISK-BAROMETER-M3-010)

## Task ID

QRE-RISK-BAROMETER-M3-010 (大盘/板块风险风向标 M3：日更 timer 接入 + GUI 风向标页 + 阈值首轮校准观察)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M3（CR 末阶段，CR 状态改「✅ M1–M3 已完成」）：deploy/hardened/
qre-barometer.{service,timer}（Mon..Fri 18:30、Persistent、hardened 护栏、
默认最近交易日单日模式，未 sudo）；`qre barometer` CLI；admin TIMER_UNITS
+ install_hint + daily_jobs PIPELINES 登记；/admin 新「大盘风险」tab——
新 `gui/market_risk.py::market_risk_overview`（只读 market_risk.daily、
_cached 300s、分区降级）+ 路由 /api/admin/market-risk + 仪表盘红黄绿灯/
五序列 inline SVG/行业+动态簇热力表/预警双判据详情（复用现有样式，零新
前端框架）；阈值首轮校准观察入 06（red 11/1850=0.59% 全为已知风险事件，
初值保留）。真库冒烟 ok（2026-08-20 总分 63.3 green）。1778 tests green
（+14）。未 commit、未重启 qre-gui、未装 timer（sudo 留主代理/用户）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-BAROMETER-M2-009
（M2 装配+回填，1764 green，b0713d7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M2-009, 风向标 M2 数据装配与回填)

## Task ID

QRE-RISK-BAROMETER-M2-009 (大盘/板块风险风向标 M2：数据装配 + 历史回填 + market_risk_daily 产出)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M2 在 M1（commit 64addd7，1754 绿）上落地：新 `risk/barometer_job.py`
（risk 包唯一读写 DB 层，业务表只读）——pct_chg/100 收益面板 +
total_mv 市值 + stock_basic.industry 行业 + cluster.daily_tags 当日簇
（<5 跳过）→ M1 纯函数 → 独立 schema `market_risk.daily` 表
（PK (trade_date, scope)，ON CONFLICT 幂等 upsert）+ JSON 产物
outputs/market_risk/<date>.json；年分块 + 312 交易日 buffer。真实回填
2019-01-02→2026-08-20 完成：220,034 行 / 1,850 日 × 120 scope，~21min。
方向性验证全过：2020-02-03 red（突破 85.2% P100）、2024-02 微盘连续 red
（总分 P99–100）、常态 green；全样本 red 11 天均为已知风险事件。
簇分数 M2 不算（成员逐日变动，披露）。1764 tests green（+10）。
未 commit、未重启 qre-gui。细节见 `09_CODING_HANDOFF.md` 顶部。
上一任务：QRE-RISK-BAROMETER-M1-008（M1 纯函数内核，1754 green，已提交 64addd7）。

# Task Handoff (archive: QRE-RISK-BAROMETER-M1-008, 风向标 M1 纯函数内核)

## Task ID

QRE-RISK-BAROMETER-M1-008 (大盘/板块风险风向标 M1：cross_section + barometer 纯函数内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

M1 在 R7（1724 绿）上落地（依据已批准 CR
`docs/frm/CR_2026-08-23_market_risk_barometer.md` §5 M1 阶段）：新
`risk/cross_section.py`（纯函数零 DB、向量化——EWMA 方差面板与单列口径
atol 1e-15 一致、截面波动率中位/90 分位、等权/市值加权离散度、滚动 60 日
平均两两相关等权 + w_i·w_j 偶权近似、VaR 突破计数/占比严格 r<−VaR 同
HIT 口径、cross_sectional_summary 一把梭 σ forecast shift(1) 防前视）；
新 `risk/barometer.py`（组合法封装 100% 复用 volatility/tail 出 EWMA σ
与 VaR/ES 95/99、252 日滚动分位分数 warmup 降级 None、红/黄/绿预警
双判据、build_barometer 全市场+板块统一 dict、分组映射调用方传入不感知
来源）；`risk/constants.py` 加 BAROMETER_CORR_WINDOW=60 /
BAROMETER_SCORE_WINDOW=252 / ALERT_CORR_LOOKBACK=20 / ALERT_CORR_JUMP
=0.10 / ALERT_BREACH_RATIO_MAX=0.03 / BREACH_CONFIDENCE=0.99 /
CROSS_SECTION_SIGMA_QUANTILE=0.90 全回显。1754 tests green（+30：
cross_section 17 + barometer 13）。未 commit、未重启 qre-gui（用户约束）。
细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-PORTFOLIO-007
（R7 组合层汇总，1724 green，待审批）。

# Task Handoff (archive: QRE-RISK-PORTFOLIO-007, R7 组合层汇总)

## Task ID

QRE-RISK-PORTFOLIO-007 (FRM 风险管理模块 R7：组合层汇总 + risk_report 扩展 + GUI 卡片 + 可选闸扩展)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R7 在 R6（期权内核 + DGV-VaR，1696 绿）上落地组合层与集成（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R7 阶段，CR 状态已改
「R5–R7 已完成」）：新 `risk/portfolio.py`（纯函数零 DB，
`summarize_mixed_portfolio`——股票腿沿用 R1–R4 收益序列法
performance_summary + EWMA VaR/ES 参照、债券/转债腿 DV01 可加/D·C 市值
加权 + 可选 KR01 按节点加总、期权腿组合 Greeks 加权求和、config 显式给
dgv.spot_shock_sd 才计算 DGV-VaR；仅股票输入退化为仅 equity 节）；
`risk/report.py` config 显式传入非空 bond_positions/option_positions/bond_kr01
才追加 `portfolio` 节（meta.sections 回显）+ markdown 渲染「组合与衍生品风险」；
GUI `_risk_display` + run_detail.html 追加「衍生品风险（组合层）」卡片
（有节才显示）；`risk/constants.py` 加 GATE_DV01_MAX/GATE_GREEKS_MAX
（默认 None=不启用），`evaluate_gate_risk` 启用时追加组合 DV01/Greeks 限额
判据，默认关闭时返回与 R4 逐键一致。1724 tests green（+28：portfolio 14 +
report 7 + gui 7）。默认 run 产物零变化，老格式 report 三处（markdown/GUI/
闸）健壮性专项测试覆盖。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-OPTIONS-006（R6 期权内核，
1696 green，待审批）。

# Task Handoff (archive: QRE-RISK-OPTIONS-006, R6 期权内核 + DGV-VaR)

## Task ID

QRE-RISK-OPTIONS-006 (FRM 风险管理模块 R6：期权计算内核 + DGV-VaR)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R6 在 R5（commit 5472832）上落地期权内核与 DGV-VaR 适配器（依据已批准
CR `docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R6 阶段，纯函数
零 DB 零行情）：新增 `risk/options.py`（BSM 式 15.6–15.9 无股息/q/离散
股息 S₀−D、Black's 式 15.12/15.13、隐波 brentq（IV_BRACKET）、CRR
式 14.4–14.7 欧式+美式含 q、第一层 delta、美式 Greeks 数值差分、
Greeks 全组 Table 16.2 含 q 版与期货期权版 rho=−f·T、组合 Greeks
加权求和）与 `risk/derivatives_var.py`（ΔV ≈ Δ·δS+½Γ(δS)²+vega·δσ、
非中心卡方累积量解析矩、正态/Cornish-Fisher 分位 VaR、VaR 序列对接
backtest_var.backtest_var_summary 复用 HIT/LR）；`risk/constants.py`
追加 IV_BRACKET/DEFAULT_TREE_STEPS=50/GREEK_SHOCK_*，全部结果 dict
回显。教材数值全复现：BSM 例 d1=0.2001/c=8.3069/p=7.9715+parity、
隐波 7.00→25.14%、美式 put 节点值 3.058/0.494/5.699（欧式 2.838）+
收敛 3.082/3.067/3.059/3.055（参数 S=29,K=30,r=3%,σ=25%,T=1 经教材
原文 p193 核对）、PDE 恒等式 1e-10、纯 gamma 解析二阶矩 Var=½Γ²sS⁴、
CF-VaR 对 MC rel 5%、VaR 序列回测违约率 ≈1% 不拒绝。1696 tests
green（+39）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui
（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-RATES-005（R5 利率与债券内核，1657 green，待审批）。

# Task Handoff (archive: QRE-RISK-RATES-005, R5 利率与债券内核)

## Task ID

QRE-RISK-RATES-005 (FRM 风险管理模块 R5：利率与债券计算内核)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R5 在 R1–R4 已完成的 risk 包上落地利率与债券计算内核（依据已批准 CR
`docs/frm/CR_2026-08-23_risk_derivatives_extension.md` R5 阶段，纯函数
零 DB 零行情）：新增 `risk/rates.py`（式 16.1–16.5 复利换算、PV/FV、
spot↔折现因子、书4 Ch9 附息债 bootstrap 零息曲线、线性/对数线性插值、
远期利率连续式与式 10.5、par yield 式 16.7/10.4）与 `risk/bonds.py`
（YTM brentq、actual/actual 与 30/360 应计利息、式 12.6 久期凸性、
式 12.1/12.3 effective duration/convexity、DV01 与 D↔DV01 换算、
组合聚合与 DV01 对冲配比、式 12.4 平行移动二阶近似、书4 Ch13 KR01
含 ΣKR01=DV01 自检、书3 Ch16/17 转债债底折现与 spread duration）；
`risk/constants.py` 追加集中参数（day count/插值/key rate 节点/Δr bp/
YTM bracket，全部结果 dict 回显）；`pyproject.toml` 补 scipy 显式依赖。
教材数值全复现：bootstrap d=0.991909/0.980944/0.969406/0.956909、
par yield 2.2103%、平坦曲线年金解析解 P/D/C、DV01↔D 自洽、
ΣKR01=DV01、+100bp 二阶近似 vs 重定价 rel 1.9e-5。1657 tests green
（+52）。既有 risk 模块零行为改动。未 commit、未重启 qre-gui（用户
约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-GATE-004（R4 晋升闸风险判据，1605 green，待审批）。

# Task Handoff (archive: QRE-RISK-GATE-004, R4 晋升闸风险判据)

## Task ID

QRE-RISK-GATE-004 (FRM 风险管理模块 R4：晋升全量回测闸加入风险判据)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R4 在 R3（risk_report.json 随 completed run 自动生成）上给晋升全量回测闸
（QRE-GUI-PROMO-GATE-001，commit cfb860d）加风险维度：`risk/constants.py`
集中阈值（`GATE_ES99_MAX=0.03`、`GATE_VAR_CONFIDENCE=0.99`）；
`gui/risk_report.py::evaluate_gate_risk(run_id)` 读该 run 的
risk_report.json——99% ES（历史模拟日收益口径）> 3% 或 99% 覆盖率
Kupiec LR `reject_5pct` → `risk.status=warning`；report 缺失/损坏 →
unavailable 不阻断；`strategy_create.finalize_promotion_gate` 写 gate json
新 `risk` 节，主判据照旧；`refresh_registry.gate_blocks_daily` 扩展为
failed 或 risk=warning 且非 forced 即阻止日更（force 通道照评估不阻断）；
admin.html 闸列 warning 追加「⚠ 风险警示」徽标（tooltip ES99 + VaR 回测
结论）+ style.css `.gate-risk`。1605 tests green（+6 净增：四情形 + force
覆盖 + 徽标渲染）。存量 gate json 无 risk 节行为不变。未 commit、未重启
qre-gui（用户约束）。细节见 `09_CODING_HANDOFF.md` 顶部。上一任务：
QRE-RISK-INTEGRATION-003（R3 集成，1599 green，commit 6852eaa）。

# Task Handoff (archive: QRE-RISK-CORE-002, R2 VaR 回测/压力测试/Bootstrap)

## Task ID

QRE-RISK-CORE-002 (FRM 风险管理模块 R2：VaR 回测 + 压力测试 + Bootstrap 推断)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

R2 在 R1（commit 96db59d）上落地三模块 + 报告扩展，公式以 FRM 知识摘要
为准：`backtest_var.py`（书2 Ch6：HIT 序列、覆盖率 Bernoulli LR + 精确
二项、独立性 Christoffersen 转移矩阵 LR——摘要未点名，注释标注出处
差异、多重检验假阳性 1−(1−α)ⁿ、backtest_var_summary 统一 dict）；
`stress.py`（书4 Ch8：A 股四历史情景库、回放=累计损失/峰谷/Peak/VaR +
相关性崩溃提示、reverse stress β 穿透反查市场冲击分位/σ 倍数）；
`inference.py`（书2 Ch13：arch CircularBlockBootstrap 块长 √n 给年化
收益/夏普/最大回撤算置信区间 + iid 对照 + MC 标准误 σ/√b）；`report.py`
升 R2（var_backtest 默认开用 EWMA μ=0 VaR、stress/bootstrap config 可选
开启）。46 个新测试全为已知答案核对（LR 手算 4.13085、转移计数手算、
情景回放手算 −0.119179/0.05/2.5、reverse β=2 穿透、bootstrap 固定 seed
CI 含真值 + MC 标准误核对、AR(1) 下 iid 低估 CBB）。1578 tests green
（+46 净增）。未 commit、未重启 qre-gui（用户约束）。细节见
`09_CODING_HANDOFF.md` 顶部。上一任务：QRE-RISK-CORE-001（R1 核心包，
1532 green，commit 96db59d）。

# Task Handoff (archive)

## Task ID

QRE-GUI-CREATE-GAPS-001 (新增策略/因子闭环四缺口)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

GUI「新增策略/新增因子」全链路四缺口补齐：①策略冒烟状态闭环——
engine._execute_and_finalize 终态钩子回写 `<name>.smoke.json`
（completed/failed + 关键指标 + finished_at，原子写），run 标记改由
run_backtest(mark=...) 预合并，list_sandbox 自愈滞留 running；前端沙箱列表
三色渲染 + 失败原因摘要 + 轮询刷新。②晋升状态闸——promote /
promote_factor 加 `force`，sidecar 非 completed → 409 smoke_not_passed，
force=true 管理员通道响应注明。③因子冒烟 120s 同步阻塞改异步——
start_smoke_job 复用 daily_jobs.start_script_job（lock_key=factor-smoke:<name>），
POST 即返 job_id + GET /api/factor-create/smoke/<job_id> 轮询 + 前端轮询，
120s 超时与 JSON 解析口径不变。④删 style.css .p3c-hidden 死代码。
1437 tests green（+20 净增）。未重启 qre-gui（用户约束），真实 E2E 待重启。
细节见 `09_CODING_HANDOFF.md` 顶部。

# Task Handoff (archive)

## Task ID

QRE-M5C-MINED-FACTOR-STRAT-001 (M5c：因子工厂 Top3 因子 → QRE 正式策略闭环验证)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

cluster-ashare M5c 联动任务：cluster.mined_factors Top3（MF_001/002/003）
转译为 cs07a/b/c（strategies/catalog/cross_sectional/），经沙箱→冒烟→晋升→
全市场近 1 年回测（批次 b21f1008ec98）→ report-audit 全通过。
截面分位语义由 cluster-ashare 物化表 cluster.mined_factor_flags 承载，
QRE 零代码改动。回测结论：近 1 年未复现 M3b 超额（超额 -11.1~-11.6%），
建议三因子转「衰减观察」——状态调整与是否 commit 均待用户审批。
细节见 `09_CODING_HANDOFF.md` 顶部。

## Task ID

QRE-STRATEGY-FIT-ANALYSIS-001 (M10.1, CR-0003 F3 phase 1)

## Current Status

DONE (implementation; review PASS in `10_REVIEW_REPORT.md`; awaiting user-approved git finalization)

## Task Note

This handoff now covers QRE-CONTINUOUS-REFRESH-001 (M10.3). Summary: watermark-gated continuous refresh — `orchestration/refresh.py` + `scripts/refresh_batch.py` (check-only/force/rolling window), per-strategy delta report with manifest/audit parity, systemd user units documented (not installed); small-sample e2e passed; no full-scale execution per standing instruction.

## Current Owner

KIMI_CODE

## Problem Summary

The quick batch (106 strategies × 5,292 symbols × 2024) ranks strategies only by market-wide returns, which buries strategies with strong class-specific edge (user's example: 3% market-wide / 12% best-class). This slice adds the strategy-fit analysis layer: winner-stock enrichment across board/industry/cap/liquidity classes, noise filtering, and multiple-testing-adjusted rankings — reading existing batch artifacts only, no new backtest runs (user instruction 2026-07-19).

## Implementation Summary

Planning only so far (per approved roadmap order M9.1b → M10.1 → M10.2 → M10.3):

1. New `analysis/strategy_fit.py`: batch loading, read-only metadata join (class columns are absent from batch summary.csv — documented gap), configurable noise filters (min trades / min class size / NaN), **significance-tier winner selection** (exact binomial test on per-symbol win rate vs p=0.5 at 90%/99%/99.9% + magnitude gates — user refinement replacing top-10%), strategy-level meta-test vs false-positive expectation, hypergeometric enrichment (pure Python), BH-FDR adjustment, `class_edge` flagging.
2. `scripts/strategy_fit_report.py` command writing summary/classes/markdown report + `report_manifest.json` (new kind, `qre report-audit`-compatible).
3. Runner `--metadata-columns` passthrough so future batches embed class columns (optional for v1).
4. v1 explicitly excludes time-window stability (needs a per-symbol monthly-returns artifact — follow-up v1.1 recorded in CR-0003).

Previous task `QRE-VECTORIZED-ENGINE-001` (M9.1b) finalized in commit `c86441b` (42.8× speedup, metric-identical).

## Standing User Instructions

- No full-scale backtest runs until the core engine work is mostly complete (2026-07-19). Small-sample-first (R-QRE-009) applies to the future full-history (M9.4) runs.
- This slice complies: it executes zero backtests (reads existing CSV/JSON artifacts + one read-only metadata query).

## Hard Constraints

- No new dependencies; pure Python statistics (hypergeometric via `math.comb`, BH-FDR).
- Deterministic outputs; manifest audit parity (R-QRE-007); read-only DB access only (R-QRE-005).

## Validation Evidence

```bash
uv run pytest -q → 1045 passed
real batch: 106 analyzed / 5 skipped; metadata 5,256 symbols
qre report-audit outputs/strategy_fit/f365c8a07b33/report_manifest.json --require-match → status=ok, 0 issues
```

</details>


## 2026-10-24 当前交接

FRM 间歇缺失已修复：根因是 result/files 20MB 上限按文件名字典序挤掉 risk_report.json；现已给 FRM 最高回传优先级并补回归测试。job58/66/74/78 云端报告已回填，58/66 使用收益修正后的净值重算。后续重点为既定待办：统一无权页、Web 文案精简、NL 编译加固等。

## 2026-10-27 当前交接：游戏终端修复 + M10.4 首片

- Night Mode、重播边界、因子呈现合同、341 列中文名、SSH 加固五项已获用户明确验收通过；不再列为待验收。
- 《我不是股神》由 DeepSeek 在当前 `src/quant_research_engine/game/` 基线完成修复：定位游戏 OHLC 前复权而因子为后复权口径，价格型因子按 `value / qfq_anchor` 对齐，非价格因子不换算；界面重做为主 K 线/成交量/MACD/RSI 一体化终端，右侧集中回合、委托、账户与成交。主 Agent 重跑游戏专项 `28 passed`，`http://127.0.0.1:8092/game` HTTP 200，并已查看桌面/移动截图。**待用户试玩验收，未部署 ECS、未 commit/push。** 上游 `ema_250` 在 2026-10-12…2026-10-26 尚有 11 点独立重算不一致（max_abs=0.287911），未掩盖、未全库重算。
- M10.4 ML 聚类首个分析切片由 Step 5 完成并经主 Agent 复核：新增 `analysis/ml_cluster.py`、`scripts/strategy_fit_ml_report.py` 与测试；DBSCAN + noise=-1，保留 M10.1 的 90/99/99.9 tier 和超额门控，sklearn 惰性导入。`strategy_fit_ml_cluster_manifest` 已登记 `ReportManifest`，真实产物内容校验 `issues=[]`。
- 真实只读产物：`outputs/strategy_fit_ml/f365c8a07b33/`；默认 eps=1.0 下 81 策略为 41 insufficient、40 all_noise，未伪造聚类结论；Step 5 的 eps=2.0 敏感性试运行有 5 策略成簇，说明结果对参数敏感。全程未跑新回测。
- 验证：ML 影子环境相关 `158 passed`；主环境相关 `469 passed, 14 skipped`；游戏 `28 passed`；`git diff --check` clean。全仓最新结果为 `2902 passed, 20 skipped, 1 failed`，唯一失败是 `test_showcase_roller.py::TestParams::test_build_roll_params_holding_override` 仍读取已按用户批准删除的外部 `qre-outputs/.../strategy.yaml`，不是本轮 ML/游戏断言失败，后续应把该测试改为自包含夹具。
- 下一步：用户试玩游戏；M10.4 的 UI/元数据扩展另行立项；主线下一项为 P2 会员分层、付费权益与微信信号推送，先对齐颗粒度再实施。

## 2026-10-27 工程收口 + M10.4 敏感性交接

- 用户选定本周主线：工程收口 + ML 工具化。DeepSeek 实施，Kimi 复核，未部署 ECS、未 commit/push、未碰游戏。
- 全仓唯一已知红灯已修复：`test_build_roll_params_holding_override` 原依赖已批准删除的外部 run YAML，现改为模块内最小 YAML + `tmp_path`，断言语义未弱化。
- M10.4 新增可选 `--eps-grid`：默认关闭时主产物与 manifest 合同不变；开启后输出 `ml_cluster_sensitivity.csv`、`ml_cluster_sensitivity_strategies.csv`、`ml_cluster_sensitivity.json`，不覆盖主产物，不登记进主 manifest。
- 真实只读敏感性：eps=1.0 → 0 成簇/490 noise；eps=1.5 → 2 成簇/5 簇/451 noise；eps=2.0 → 5 成簇/12 簇/396 noise。默认保守结论对参数敏感，后续 UI 必须标注筛查证据。
- 验证：`tests/test_showcase_roller.py` 14 passed/1 skipped；全量 `2906 passed, 24 skipped, 4 warnings`；ML 影子环境相关 `165 passed`；`git diff --check` clean。
- 遗留：41/81 策略显著股票 < 5，任何 eps 都 insufficient；网格只改善参数敏感性可见性，不改变样本不足事实。

## 2026-10-27 经典策略 FRM 日收益分布修复交接

- 根因：SaaS `risk-analysis` 端点只转 risk_report 视图，未生成直方图所需日收益序列；8081 有该逻辑，SaaS 漏接。生产 job 58/66 修复前 `has_report=true` 但响应无 `histogram`。
- 修复：新增 `daily_returns_from_cumret()` / `histogram_from_cumret()`，SaaS 端点用 `chart_data.cumret` 差分还原日收益；不用 `total_equity.pct_change`，不误用 per-symbol 曲线。
- 验证：相关 189 passed；全量 `2909 passed, 24 skipped, 4 warnings`；ECS 已部署，job 58/66 直方图 40 箱、点数 = n_obs。
- 状态：已部署待用户验收，未 commit/push。

## 2026-10-27 TradingView 化 Spike 交接

- DeepSeek 完成共享图表内核选型 Spike，生产代码零改动；CR：`docs/agent/change_requests/CR-2026-10-27_tv_chart_core_spike.md`。
- 推荐 A（增强 ECharts）做第一阶段主力，B（Lightweight Charts 5.2.1）仅在 `symbol.html` K 线区受控试点，C 自研不进第一阶段。
- 实测：4000 点重播 A rAF 40–41ms/帧，B 17.5–17.9ms/帧；375 下 B 无横向溢出。B 的 attribution 合规是硬阻塞。
- 下一项待用户批准：A 路先修 ResizeObserver + 重播增量更新；B 路是否并行试点由用户决定。

## 2026-10-27 A 路图表修复交接

- DeepSeek 完成 A 路两个痛点修复，Kimi 复核并部署 ECS；未 commit/push。
- 改动：`symbol.html` 单例 ResizeObserver + 当前实例 resize；`replay.js` 可见窗口裁剪（默认 240 点）+ 事件窗口过滤 + resize 归属解绑。
- 测试：新增 5 例；相关 127 passed；全量 2914 passed/24 skipped，另有 1 个 PG teardown 环境性 error，目标文件复跑 21 passed。
- 性能：4000 点重放同步每帧 39.1→9.5ms，rAF 45.8→16.8ms。
- 生产：qre-saas active，job58/static replay 200，生产 replay.js 含 `visibleWindow`。
- 待用户确认：重播曲线左端不再固定 0；`job.html` 旧 dispose resize 警告遗留。

## 2026-10-27 A 路遗留修补交接

- `job.html` resize 已加 dispose 守卫；重播策略/基准系列新增 `zeroBase`，左端回到 0，指标仍全量口径。
- 测试：相关 130 passed；全量 2917 passed/24 skipped。
- 生产已部署，`/saas/jobs/58` 200，生产 replay.js 含 `windowDisplayData`，job 页面含 dispose 守卫。未 commit/push。

## 2026-10-27 静态 K 线 TV 化首片交接

- DeepSeek 实施，Kimi 复核并部署；范围仅 `symbol.html` + 新测试。
- 交付：左侧工具栏、顶部 OHLC/因子信息区、右侧价格标尺、底部时间轴、缩放/重置、量/因子开关；因子合同与 Night Mode 不变。
- 测试：新增 10 例；相关 159 passed；全量 2927 passed/24 skipped。
- 生产：job58 个股页 200 且包含 `kline-tools`；未 commit/push。
- 遗留：重播界面未 TV 化；移动端信息密度仍高；面板全关的隐藏格分支未在浏览器触发。

## 2026-10-27 K 线重播 TV 化首片交接

- DeepSeek 实施，Kimi 复核并部署；范围仅 `symbol.html` + `replay.js` 最小可选透传 + 新测试。
- 重播布局复用静态 TV 规格：右侧标尺、底部时间轴、x 轴全联动；顶部信息区随当前帧更新 OHLC/量/涨跌/因子值。
- `replay.js` 仅新增可选 `yAxes[].position/formatter`、`opts.axisPointer`、`axisLabelIndex`；`job.html` 默认路径输出不变。
- 测试：新增 6 例；相关 141 passed；全量 `2936 passed, 24 skipped, 4 warnings`。
- 浏览器：`.tmp/replay-tv/` 33/33 通过，1280/375 已由主 Agent 目视确认。
- 生产：job58 个股页 200，`/static/replay.js` 含 `opts.axisPointer`。未 commit/push。
- 遗留：重播 tooltip 仍统一加 `%`；重播容器高度未与静态 460px 归一；375 信息区仍 ellipsis。

## 2026-10-27 重播遗留清理交接

- Step 5 实施，Kimi 复核并部署；范围仅 `replay.js` + `symbol.html` + 测试。
- tooltip：新增 `formatTooltipValue()`；K 线重播关闭统一 `%`，价格/因子按原值，成交量按万，candlestick 显示 OHLC；job 默认路径仍 `%`。
- 高度：静态/重播共用 `klineHeightForPanes()`。
- 375：`.kline-ohlc` 窄屏换行，不截断 OHLC/因子值。
- 测试：相关 120 passed；全量 `2946 passed, 24 skipped, 4 warnings`。
- 生产：job58/920832 200，replay.js 含 `formatTooltipValue`。未 commit/push。
- 遗留：`#kreplay-note` 旧灰字备注未清。

## 2026-10-27 重播灰字备注清理交接

- Step 5 实施，Kimi 复核并部署；`#kreplay-note` 动态段落删除，必要口径迁到 `#btn-kreplay` `data-tip`。
- 测试：相关 122 passed；全量 `2948 passed, 24 skipped, 4 warnings`。
- 生产：job58/920832 200，旧 note 0，按钮 data-tip 1。未 commit/push。

## 2026-10-27 历史旧个股详情按需刷新交接

- Step 5 实施，Kimi 复核并部署；新增 `factor_basis=qfq_anchor_v1` 标记，旧详情显示“刷新详情”，调用 `generate?refresh=1` 重算。
- 主 Agent 追加修正：showcase/分享只读详情 200 也返回 `readonly/readonly_kind`，前端只读视图不显示刷新入口。
- 测试：相关 263 passed；全量 `2956 passed, 24 skipped, 4 warnings`。
- 生产：job58/920832 200；showcase 详情返回 `readonly=true`；前端含只读刷新守卫。未 commit/push。

## 2026-10-27 K 线画线工具首片交接

- Step 5 实施，Kimi 复核并部署；范围仅 `symbol.html` + 测试。
- 新增趋势线/水平线/清除画线；像素坐标转真实日期价格，降级不造点；重播禁用画线。
- 测试：相关 131 passed；全量 `2961 passed, 24 skipped, 1 failed`（已知 timing flake，目标文件复跑 24 passed）。
- 生产：job58/920832 200，趋势/水平入口存在。未 commit/push。
- 遗留：画线不持久化；未跑浏览器实机。

## 2026-10-28 个股详情加载失败修复交接

- 根因：历史 gzip 产物因子序列含裸 `NaN`（PG 存 NaN 非 NULL），SaaS 读取出口 `_jsonable` 不过滤非有限浮点，Flask 写出非法 JSON，浏览器 `resp.json()` 抛 SyntaxError → 页面显示「加载失败，请稍后重试」。
- 修复：`lab_result.json_safe()` 成为唯一实现，lab 路由 / SaaS `_jsonable` / worker `_json_sanitize` 三处共用；`_fetch_factor_panels` 加 `math.isfinite` 过滤。
- 测试：相关 152 passed；全量 `2960 passed, 24 skipped`。
- 生产：ECS 已部署并验证通过（4 只原失败/正常样本 + 160 只严格 JSON 扫描 bad=0）。未 commit/push。
- 遗留：无。历史产物不重写（读取出口已覆盖）。

## 2026-10-28 job#78 个股详情刷新入口修复交接

- 根因：`showSymbolDetailRefresh()` 对 `Element.children`（HTMLCollection）调 `.some()`，浏览器抛 TypeError，被 catch 吞成「加载失败」。触发条件＝私人 job + 缺 `factor_basis` 的旧产物；showcase 只读路径被跳过，故此前只验只读页面未暴露。
- 附带修掉测试盲区：harness 的 `children` 改为 HTMLCollection 形态，此类 bug 以后可被测出。
- 测试：`test_gui_saas_pages.py` 94 passed；全量 `2960 passed, 24 skipped`。
- 生产：ECS 已部署，真实 DOM + 真实 job#78 产物端到端验证通过。未 commit/push。
