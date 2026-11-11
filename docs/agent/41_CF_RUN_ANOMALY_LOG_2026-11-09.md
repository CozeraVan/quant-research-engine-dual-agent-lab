# 41_CF_RUN_ANOMALY_LOG_2026-11-09.md — 经典策略全量回测（CF）异常与中断登记

本文件是 **CF 队列（118 个经典策略 × 全市场全期）运行期间出现的所有中断、异常与设计缺陷** 的
唯一登记处。规则：**每一条都必须有「现象 / 根因 / 处置 / 验证 / 状态 / 未来修复项」**，
未修复项留在 §2 的待办表里逐项推进，修完把状态改成 ✅ 并把验证证据写进 `05_PROGRESS.md`。

- 队列工具链：`scripts/classic_catalog/{driver,fullscale,event_watch,inventory,report,supervise,switch_parallel}`
- 事件流（每任务开始/终态）：`40_CF_QUEUE_EVENT_LOG_2026-11-04.md`
- 运行态（不入库）：`.tmp/classic-catalog-fullscale/{job_ids.json,results.jsonl,retry_counts.json,supervisor.log}`

---

## 1. 已发生并已处置的异常

### A-01 WebBridge 会话瞬断（502 / 标签丢失）造成队列退出 ✅已缓解

- **现象**：多次在提交阶段 `RuntimeError: WebBridge 瞬断重试耗尽（5 次）：HTTP Error 502: Bad Gateway`，
  `fullscale.py` 抛异常退出；`list_tabs` 返回 `tabs:[]`。
- **根因**：WebBridge（127.0.0.1:10086）与浏览器标签是外部状态，浏览器重启/代理瞬断即丢；驱动自己无法恢复。
- **处置**：`driver.evaluate` 早已对 502/503/504 与 HTML 错误页做 5 次退避重试；外层改为 `supervise.sh`
  每 120s 检查——队列不在跑就先 `list_tabs`→缺失则 `navigate` 重建 →校验 `/api/saas/me` →再 `--resume`。
- **验证**：`supervisor.log` 记录 21:41→21:43、02:45→02:47 两次自动恢复；`job_ids.json` 幂等键保证零重复建单。
- **状态**：已缓解（脚本级自愈，每次中断损失约 2 分钟）。

### A-02 监管 `flock` 的 fd 泄漏 → 新监管自锁 → 队列空转 1h49m ✅已修

- **现象**：2026-11-07 20:46 切换并行后新监管打印「已有 supervisor 实例持有锁，本次退出 pid=82025」即退出，
  驱动再没被拉起，队列 20:46→22:35 完全空转。
- **根因**：`exec 9>"$LOCK"; flock -n 9` 用的是 fd 9，bash 默认把该 fd 继承给子进程；
  `event_watch` 是长驻进程，它继承 fd 9 就把锁永久占住。
- **处置**：`supervise.sh` 两处子进程拉起都加 `9>&-`；`switch_parallel.sh` 启动监管前扫描
  `/proc/*/fd/9` 指向 `supervisor.lock` 的进程并清理。
- **验证**：修复后两轮切换均能正常拉起监管；锁持有者扫描为空。
- **状态**：已修。

### A-03 重启竞态：worker 早于 PG crash recovery → job298 报 57P03 ✅已修（时序未实测）

- **现象**：CF-063/job298 `engine_error: RuntimeError: 回测失败：(psycopg.OperationalError) …
  FATAL: the database system is starting up`。
- **根因**：机器重启后 `qre-saas-worker.service` 13:01:48 自启并领到排队任务，而本机 PG 因强制重启
  正在 crash recovery（`syncing data directory`），直到 13:05:15 才 `accepting connections`。
  unit 里 `After=postgresql.service` 只保证「start 命令返回」，不保证「能接受连接」。
- **处置**：新增 drop-in `deploy/saas/qre-saas-worker.service.d/db-ready.conf`：`ExecStartPre` 循环
  `pg_isready`（300×2s，最多等 600s）+ `TimeoutStartSec=900`；装机后 `daemon-reload` 不重启。
- **验证**：`systemctl show -p ExecStartPre` 生效、就绪探测手测 25ms 返回 0、`systemd-analyze verify` 无告警。
- **状态**：已修，但**重启时序本身未实测**（下次重启机器才是真验证点）。

### A-04 驱动「遇失败即停」+ resume 复等已终态 job → 死循环 → 空转 17.8h ✅已修

- **现象**：CF-083/job319 失败后，驱动每次 `--resume` 都复等这个已终态 job，9 秒内 `rc=1`，
  连退 3 次，监管快速失败计数 3/3 → 写 `SUPERVISOR_HALTED` 退出 → 队列从 11-08 17:16 停到 11-09 11:03。
- **根因**：`run_queue` 的失败策略是「停下来等人工修因」，对基础设施瞬态（回传被拒、数据库未就绪）
  同样适用，导致一个瞬态失败就把整条队列钉死；而 HALT 只落本地文件，没有外部告警。
- **处置**：新增 `is_infra_failure()`（只认 `result_upload_*` 前缀与 `database system is starting up` /
  `OperationalError` / `connection to server` 关键字）+ `AUTOMATIC_RETRY_CAP=2`；命中自动换键
  `v1→v2→v3` 重跑并重新入队。策略/因子类失败仍立刻 `return 1`（测试锁定）。
- **验证**：`test_classic_catalog_fullscale.py` 11 passed（含「429 自动重跑后 completed」「策略失败不重跑」）。
- **状态**：已修。

### A-05 产物回传 429 被判终态 → 白丢一次完整计算 ✅已修（双层）

- **现象**：CF-083 已算出 135,714 笔，回传被 ECS nginx 拒绝 `HTTP 429 Too Many Requests`（nginx/1.24.0 页面），
  worker 落 `result_upload_http_429` 整单 failed。
- **根因**：①`daemon._UPLOAD_HTTP_CLASSES` 把 429 归入不可重试分类；②nginx worker 通道
  `limit_req zone=qre_worker rate=120r/m burst=30`，双路并发分片上传+心跳/claim 直接触顶。
- **处置**：①worker 回传对 `{429,502,503,504}` 有限重试（退避 5/15/45s），安全性由
  `client.upload_files` 的 upload_token 幂等 + 已落盘文件不进 remaining（等价断点续传）保证；
  ②nginx `qre_worker` 放宽为 `rate=300r/m burst=120`（仅 `X-Worker-Token` 可进），备份
  `/tmp/aguhuice.nginx.bak-20261109-110626`，`nginx -t` 通过后 graceful reload。
- **验证**：`test_result_upload_error_classes.py` 16 passed（新增 `TestDaemonUploadRetry` 4 例）；
  公网 `home=200 / api=401`。
- **状态**：已修。

### A-06 在途预算闸把 2 路并行压回 1 路 ✅已修

- **现象**：`--concurrency 2` 与 `--heavy-slots 2` 都生效，但 worker 日志反复
  `[heavy-2] 在途预算不足（已用 13.97GB + 本任务 13.97GB > worker 预算 15.5GB），暂缓领取`，
  job303 一直 `queued`，实际仍是单路。
- **根因**：`capacity.ADMISSION_BUDGET_GB["heavy"]` 取 item3 压测最坏包络 13.97GB，两条重槽互斥。
- **处置**：`_heavy_admission_gb()` 支持 `QRE_WORKER_HEAVY_ADMISSION_GB` 覆盖（非正/不可解析回退 13.97），
  `/etc/qre-saas-worker.env` 设 6.5（依据：CF 12 个 heavy 任务 cgroup 峰值仅 6.05 GiB）。
  三层护栏不变：cgroup 18G、`RLIMIT_AS` 12G、RSS 早停 80%。
- **验证**：切换后实测双进程并行、9h36m 完成 10 个任务（≈2.1×）、cgroup `memory.peak` 9.42 GiB、
  期间跑完 1,251,369 笔的最大交易量任务（CF-077）未触发 OOM/早停；`test_worker_capacity.py` 等 44 passed。
- **状态**：已修。

### A-07 单任务等待上限 3h 过紧 ✅已修

- **现象**：`TimeoutError: job 301 exceeded 10800s`（CF-065 已跑 179 分钟仍在跑）。
- **根因**：`wait_owner` 默认 3h，但重交易量策略实测 208 分钟（CF-054）甚至更久。
- **处置**：调用处上限提到 6h（21600s）并写明依据；`wait_owner` 默认参数保持 10800 兼容既有测试。
- **验证**：`py_compile` + 既有 6 例测试通过；超时后监管 12 秒内自动 resume，无数据损失。
- **状态**：已修。

### A-09 SSH 瞬断打断状态轮询（rc=255）导致驱动退出，监管 2 分钟恢复 ✅已缓解（根因未修）

- **现象**：2026-11-10 02:26:47 驱动 `rc=1` 退出，traceback 落在
  `poll_jobs → runner(ssh … psql …)`：`subprocess.CalledProcessError … returned non-zero exit status 255`。
  当时在飞 job335/336。
- **根因**：`poll_jobs()` 每轮都通过 `ssh deploy@47.119.127.40 psql` 取状态，**没有对 SSH 瞬断做重试**；
  本机到 ECS 的一次连接失败（rc=255）就把整轮驱动打死。与 A-01 同类：外部依赖瞬态被当致命错误。
- **处置（本轮）**：`supervise.sh` 在 02:29:01 自动 `--resume`，中断仅 2 分 14 秒，任务在服务端照常跑完，
  后续 CF-097/098/099 正常完成与提交，无重复建单、无数据丢失。
- **根因修复（待做，见 F-11）**：给 `poll_jobs` / `assign_owner` / `wait_owner` 的 runner 调用加
  「SSH rc=255 / 超时」有限重试与退避（可参考 `driver.Browser` 的瞬断重试写法）。
- **状态**：已缓解（自愈），未根治。

### A-08 操作教训：`cd repo && nohup … &` 的优先级误判为「文件被删」❌非产品缺陷

- **现象**：`cat .tmp/…/supervisor.log` 报 No such file，一度怀疑有清理进程删文件。
- **根因**：`cd repo && nohup cmd &` 中 `&` 作用于整条 `&&` 列表，整条命令进后台，
  后续 `cat` 仍在 `/home/van` 下解析相对路径。
- **处置**：命令一律用 `cd repo;` 分号或绝对路径。文件从未丢失。
- **状态**：已澄清（记录在案，避免再误判为产品 bug）。

---

### A-10 PC 崩溃后恢复（11-10 10:26 崩溃 → 10:39 恢复）✅已恢复，且顺带验证 A-03

- **现象**：PC 整体崩溃重启（本机 uptime 归零）。崩溃瞬间 worker 上在跑 CF-108/job345 与 CF-109/job346；
  本地驱动/监管/事件监视全部消失；本地 PG 进入 crash recovery（10:35 起 `syncing data directory`，
  到 **10:39:11** 才 `accepting connections`）；Windows Chrome 也随之退出，WebBridge 会话 `tabs:[]`。
- **恢复过程（10:35→10:40，约 5 分钟）**：
  1. 本机 PG 自动 crash recovery，`pg_isready` 每 20s 轮询确认 10:39:11 就绪；
  2. **worker 全程停在 `activating (start-pre)`**（journal 10:35:25 `Starting …`），直到 PG 就绪才真正起进程
     （MainPID 2698，active/running）——这是 A-03 的 `db-ready.conf` 第一次在真实重启中生效，
     **没有再出现 57P03「database system is starting up」失败**；
  3. WebBridge：从 WSL 直接拉起 Windows Chrome（`/mnt/c/Program Files/Google/Chrome/Application/chrome.exe`），
     再用 `navigate(newTab)` 在 `classic-catalog-smoke` 会话重建标签（tabId **1523283702**），`/api/saas/me` 200；
  4. 拉起 `supervise.sh`（pid 2803）→ 自动 `--resume --concurrency 2`（driver 2834）、事件监视 2811。
- **在飞任务的损失**：job345/job346 的 runner 随崩溃消失，服务端租约到期后 reaper 重排，
  **`attempts` 1→2、lease 刷新到 10:53:53**，worker 重新领取并从头计算——两单约 2 小时的中间结果无法挽回（崩溃固有代价）。
  驱动按 `job_ids` 复等同一 job id，**没有重复建单**。
- **状态**：已恢复；恢复后 `heavy-slots 2`、两个子进程同时在跑（2706/2708），cgroup peak 从新开机重新计。

---

### A-11 两个策略全期全市场零交易 ✅已修复并重跑（均属策略层，不是引擎缺陷）

- **现象**：CF-018 `bo09e_channel_retest_breakout`、CF-074 `mr08a_mfi_oversold_reversal` 全期全市场 0 笔。
- **CF-018：自引用恒假（已证实，数学证明）**。入场含 `close.shift(1) > close.shift(1).rolling(20).max()`——
  shift 后再 rolling 的 20 日窗口**含被比较对象自身**，严格大于自身 ⇒ 恒假。同族 bo09a/b/c/d 全写
  `close > close.shift(1).rolling(N).max()`（今日 vs 昨日 N 日最大），只有 bo09e 多写一个 shift。
  **修复建议**：改为 `(close.shift(1) > close.shift(2).rolling(20).max()) & (close > sma_20) & (close > close.shift(1))`
  （昨日创 20 日新高 + 今日仍在 20 日线上方 + 今日上行），符合作者「突破后回踩不破再上行」本意。
  影响面=1 个 YAML。
- **CF-074：条件组合近乎互斥（已实测，非数据缺陷）**。入场 `(rsi_14<30) & (close>sma_60) & (rsi_14>昨)`。
  因子覆盖率 sma_60 98.4% / rsi_14 100%（不是缺因子）；按引擎口径（`QRE_PRICE_BASIS=raw` → `close×adj_factor` 后复权）
  全市场 14,884,053 行中：`rsi<30` 697,951 次、`close_hfq>sma_60` 6,841,387 次、**两者同时只有 4 次**。
  即「深度超卖」与「高于长期均线」天然互斥，该过滤条件把策略打空。
  **修复建议**：把趋势过滤改成「长期趋势向上」（`sma_60 > sma_60.shift(20)`）或删去 `close>sma_60`，
  保留超卖+拐头（`rsi<30 & rsi>昨`）这个本体。
- **口径澄清（重要，避免再误判）**：因子库 `factors.*` 存的是**后复权**尺度（`raw×adj_factor`），
  引擎 `data/postgres.py` 在 `QRE_PRICE_BASIS=raw` 下同样把价格列 ×`adj_factor`，**两边尺度一致，没有系统性偏差**。
  调试/探针若直接用 `stock_daily.close` 与 `sma_N` 比较会得到错误结论（我曾因此误判）。
- **通用教训（策略库质量闸门）**：进全量队列前先做**信号存在性检查**（抽样若干年，统计入场次数），
  零交易应标「口径待核」而非「回测完成」。已写进 36 runbook 的提交前置建议。
- **状态**：✅ 已修复并重跑（2026-11-11）。CF-018 → job356 **45,983 笔**（总收益 -8.30%，胜率 29.7%）；CF-074 → job357 **10,165 笔**（总收益 +8.47%，胜率 61.1%）。showcase 已换到新 job，`CF_RESULT_INDEX.json` 已刷新。**注意**：CF-018 修复后为负收益，属有效但亏损的策略结论。

---

### A-12 新端点插入位置切断既有 decorator 叠加，抢占了 `/api/jobs/<id>` ✅已修（测试发现）

- **现象**：部署参数快照后，`tests/test_gui_saas.py::TestTiersD1D2::test_guest_submit_and_limits` 失败
  （`KeyError: 'job'`）；ECS 上 showcase 因整列读 `chart_data` 把 2GB 实例 OOM（见 §3 of 42）。
- **根因**：`api_get_job` 原本是**两个 decorator 叠加**——
  `@app.get("/api/jobs/<int:job_id>")` 与 `@app.get("/api/saas/jobs/<int:job_id>")` 共用一个视图。
  我把新端点插在这两个 decorator **中间**，导致 `/api/jobs/<id>` 被绑到新的 `api_get_job_params` 上，
  旧路由的返回结构从「job 视图」变成「参数快照」。
- **处置**：把新端点移到整个 decorator 叠加块**之前**，两个原 decorator 保持相邻；
  showcase 查询改为只取 `chart_data->'metrics'`。
- **验证**：`test_gui_saas.py` 82 passed（含新增「showcase 不得整列读 chart_data」回归）、
  全套 228 passed, 13 skipped；公网 `/api/saas/showcase` 200 / 1.34s / 119 条，调用后内存 727MB/1612MB。
- **教训（新增 UI/API 纪律）**：给既有路由旁边加端点时，先确认该路由是不是 decorator 叠加；
  新代码一律插在**叠加块之前**，不许插在两个 decorator 之间。
- **状态**：已修，已重新部署 ECS。

---

## 2. 待修复清单（未来逐项推进）

| ID | 项 | 影响 | 建议做法 | 优先级 |
|---|---|---|---|---|
| F-01 | **HALT 无外部告警** | A-04 停了 17.8h 才发现 | 监管 HALT 时写状态文件 + 由 `event_watch` 把 HALT 事件写进 40 号日志；有条件时推送到用户（邮件/IM webhook） | P0 |
| F-02 | **回传重试未在大产物场景实测** | 大 manifest（1500+ 文件、8MiB 分片）下 429 反复重试可能撞租约/上传硬超时（30min） | 构造 >8MiB 多分片 + 注入 429 的集成测试，量总耗时与租约续期是否足够 | P0 |
| F-03 | **并发深度不自适应** | 现在固定 2 路；若某任务真实峰值上台阶，只能人工降回 1 路。**2026-11-09 21:34 实测 cgroup `memory.peak` 已达 16.09 GiB / 18 GiB（89%）**，当时两路仍在跑、无 OOM、无 RSS 早停，当前占用仅 1.50 GiB ⇒ 峰值来自某一对任务叠加 | 用 cgroup `memory.peak` + RSS 采样驱动「动态降档」：单任务峰值 >12GiB 或 cgroup peak >17GiB 时自动把 `--concurrency` 降到 1；在那之前人工盯 peak，跌破前维持 2 路 | P0 |
| F-04 | **重任务与并行冲突未自动识别** | R-MEM-001 规则 6 要求「单任务 ≥8GiB 不得并行」，目前靠人工判断 | 由 `capacity.estimate_peak_budget(交易数)` 在提交前算预算，>8GiB 的策略打 `serial_only` 标记，驱动跳过并行位 | P1 |
| F-05 | **CF 运行态不在版本控制内** | `job_ids.json`/`results.jsonl`/`retry_counts.json` 只在本机 `.tmp`，换机或清理即丢（本次已两次靠人工续接） | 每日快照进 `docs/agent/classic_catalog/snapshots/`（只保留最新 N 份）或入库 `cf_queue_state` 表 | P1 |
| F-06 | **重启时序未实测** ✅**已于 2026-11-10 10:35 崩溃重启中验证** | 无 | 证据：unit 10:35:25 进入 `activating (start-pre)` 并持续约 4 分钟，PG 10:39:11 才 accepting，worker 之后才拿到 MainPID；全程无 57P03 失败。后续只需保持该 drop-in 不被覆盖 | ✅ 已验证 |
| F-07 | **`--concurrency` 与槽位不匹配时无告警** | 只提交不执行（A-06 的体验：有管线没并行） | 驱动启动时读 `systemctl cat` 的 `heavy-slots` 与 `--concurrency` 比对，不一致就打印显式告警 | P2 |
| F-08 | **`_UPLOAD_HTTP_CLASSES` 与 SaaS 侧白名单靠测试锁一致** | 新增分类易漂移 | 已有 `test_worker_mirror_matches_saas_classes`；补一条「可重试集合也是 SaaS 侧可重试的子集」 | P2 |
| F-09 | **监管与驱动的失败策略仍分散** | 失败处理散在 `run_queue`/`supervise`/worker 三处，语义要人读代码才懂 | 抽出 `docs/agent/36` 里的失败策略表：哪类失败自动重试、哪类停、哪类告警，单一来源 | P2 |
| F-10 | **单机 8 核下 CPU 利用率仍低（~14%）** | 2 路只用到 ~0.5 核；并行深度受内存预算而非 CPU 限制 | 若后续把单任务预算实测降到 5GiB 级，可试 3 路（需 cgroup 18G 内 + F-03 的动态降档兜底），先做容量推演不直接上 | P2 |
| F-11 | **状态轮询对 SSH 瞬断无重试** | 2026-11-10 02:26 一次 ssh rc=255 直接打死驱动（A-09），靠监管 2 分钟才恢复 | 给 `poll_jobs`/`assign_owner`/`wait_owner` 的 ssh 调用加 rc=255/超时的有限退避重试（照抄 `driver.Browser` 的做法），并把「外部依赖瞬态不当致命错误」写成本项目通则 | P0 |

---

## 3. 使用规则

1. **任何新的中断/异常先登记到 §1**，写清现象、根因、处置、验证、状态；未彻底解决的同步进 §2 待办表。
2. 修完一项：把 §1 条目状态改 ✅、§2 对应行删除或标 ✅，验证证据写进 `05_PROGRESS.md` 同日条目。
3. 本文件只登记 CF 队列相关异常；引擎/数据层的既有事故仍在原文档（如 `27_STRESS_TEST`、`35_CAPACITY_MODEL`）。
