# CR-2026-11-03 · 全量回测结果回传缺陷：413 丢结果 + uploading 无终态导致重算

> 来源：`docs/agent/27_STRESS_TEST_2026-11-02.md` §8.14 / §8.15（2026-11-02 全期全量压测实测）。
> 严重度：**高**——一次 42 分钟 / 6 GB 的全市场计算可因回传失败整体作废，且失败后会再跑一遍。
> 状态：**A+C 与剩余五项（B 分片上传 / §8.5 截断标记 / §8.7 清理 / §8.11 progress /
> §8.15 reaper）均已实施并通过测试**（2026-11-03 step5review 后台实施）；
> 主 Agent 验收（真实小样本 + ECS 部署 + worker 重启）后提交。详见 §5。

---

## 1. 问题一：产物回传 413，blob 一个都没落盘（§8.14）

### 1.1 实测证据（item2 / job 7）

- 计算全成功：04:07:08 认领 → 04:49:59 失败，执行 **2581s（43 分钟）**，内存峰值约 6 GB。
- `POST /api/worker/jobs/7/result/meta` 返回 200，`results.summary` / `chart_data` /
  `artifacts`（含 **1,537 条 sha256**）全部入库。
- `POST /api/worker/jobs/7/result/files` 返回 **413**，产物文件**一个都没有落盘**。
  前端/下游看到的是「结果可用、下载全 404」的半成品状态。

### 1.2 根因

worker 一个文件一个 multipart part，manifest 1,537 part；Flask 3.1.3 默认
`MAX_FORM_PARTS = 1000`，werkzeug 3.1.8 `sansio/multipart.py` 直接抛
`RequestEntityTooLarge`。**与 20 MiB 体积无关**：item1 同为 20 MiB 但只有 333 part → 200。

触发条件是**产物文件数**，不是字节数。逐股明细越多越危险（约 820 只以上时
`_symbol_details` 175 + 逐股 CSV 就接近上限）。

### 1.3 次级缺陷：worker 不识别 4xx

客户端只看到 `Connection reset by peer`，日志写成「等租约过期重排」，
把真实的 HTTP 413 掩盖成连接问题，排障时完全指错方向。

### 1.4 修复方向（三选一或组合，实施时定）

| 方案 | 改动 | 风险 |
|---|---|---|
| A. 服务端提高 `MAX_FORM_PARTS`（如 5000） | `create_saas_app()` 里 `app.config["MAX_FORM_PARTS"] = 5000` | 极低，一行配置 |
| B. worker 改单 part + 自定义 manifest，或分批多次 POST | 改 `worker/runner.py` 回传逻辑 | 中，动 worker 协议实现 |
| C. 4xx 必须落 `error_class=result_upload_http_<code>`，不退化成连接错误 | 改 worker 错误分类 | 低 |

建议 **A + C 先做**（低风险、直接止损），B 作为后续优化（分片上传才是根治）。

---

## 2. 问题二：`uploading` 无终态 + reaper 整单重排（§8.15）

回传失败后 job 停在 `uploading`，`finished_at` / `error_class` / `error_message` 全空，
无任何告警。同时 `_reap_expired`（`gui/saas/app.py:1016-1043`）会把
「`uploading` + 租约过期 + `attempts < max_attempts`」重排回 `queued`，
**同一份 42 分钟 / 6 GB 的全市场计算会被重复执行**。本轮靠「失败不重试」规则手工置
`failed` 规避，不是系统行为。

修复方向：
1. 回传失败必须落终态（`failed`）与 `error_class=result_upload_*`，不允许长期滞留 `uploading`；
2. `_reap_expired` 不得把「已产生 `results` 行」的 job 重排回 `queued`（或重排时复用本地 tmp 产物）；
3. 半成品状态（meta 已入库、blob 缺失）需要可观测标记，前端能提示「结果不完整」。

---

## 3. 关联发现（同批实测，一并登记）

| 编号 | 发现 | 影响 |
|---|---|---|
| §8.5 | `RESULT_FILES_MAX_BYTES = 20 MiB` 超预算文件**直接 `continue` 跳过，不写任何 `truncated` 标记** | item1 产出 1.1 GB / 5208 文件，只回传 333 个 / 20,971,520 字节（正好卡上限）；`symbol_details` 为 null。全量逐股明细绝大部分只存在于 worker 本地 |
| §8.7 | `/tmp/qre-worker-job<id>-*` job 结束不清理 | item1 留下 1.1 GB；连续跑会持续累积 |
| §8.11 | batch 全量模式下 `progress` / `progress_message` 全程不更新 | 前端进度条无法反映真实推进，无法区分「正常跑 64 分钟」与「卡死」 |
| §8.12 | 全量单跑下逐 job 耗时分布退化为单值（N=1） | 队列耗时特征需多 job 并发场景另测 |

---

## 4. 影响面与验收门

- 改动文件（预估）：`gui/saas/app.py`（`MAX_FORM_PARTS`、reaper 条件）、
  `worker/runner.py`（4xx 分类、可能的分片上传）、对应测试。
- 验收门：
  1. 单测复现 413（构造 >1000 part 的 manifest）→ 修复后 200；
  2. 回传失败必须落 `failed` + `error_class`，且 `_reap_expired` 不重排有 `results` 行的 job；
  3. 全量回归不许变红；
  4. 真实小样本全市场回测一次，确认回传完整且有 `truncated` 标记（若实施 §8.5 的标记）。
- 部署纪律：先部署 ECS 再提交；worker 侧改动需重启本地 worker 才生效（要单独向用户报备）。

---

## 5. 状态（2026-11-03 更新）

**A + C 已实施并测试通过**（低风险止损两项）：
- A：`create_saas_app()` 显式 `app.config["MAX_FORM_PARTS"] = 5000`（实测 manifest
  1,537 part，默认 1000 会 413；触发条件是文件数而非字节数，故按文件数放大）。
- C：`worker/client.py::upload_files` 把 `HTTPError` 升级为带 status 的 `CloudError`；
  `worker/daemon.py` 抽出 `_report_results()`，回传失败**显式 `fail` 落终态**——
  4xx → `result_upload_http_<code>`（不可重试），传输/5xx → `result_upload_error`（可重试）。
  worker 与 SaaS 两侧分类白名单各存一份，由 `tests/test_result_upload_error_classes.py`
  （9 例）锁一致性；worker 相关测试 80 passed。
- `17_JOB_PROTOCOL.md` §3.4 error_class 表已补两个新分类与 P0-9 说明。

**剩余五项已实施（2026-11-03 step5review 后台实施，主 Agent 待验收）**：
- **B 分片上传**：`worker/client.py::upload_files` 按「≤100 文件或 ≤8 MiB」分批多次
  POST 同一端点（`_iter_upload_batches` + `_upload_batch`）；服务端零改动（既有
  upload_token 幂等 + remaining 结算即断点续传）。传输失败统一 `CloudError(status=None)`
  （可重试），全部批次后非 completed 抛错不谎报成功。测试
  `tests/test_result_upload_chunked.py`（16 例：>1000 小文件分片、chunk 边界、
  重试续传、重复提交幂等、sha256/清单外 400、单包 >5000 part 仍 413 的根因锁定、
  daemon 本地文件缺失 → result_upload_error）。
- **§8.5 截断显式标记**：`worker/runner.py::collect_result_files_with_meta` 产出
  truncated/included/skipped/预算元数据（旧 `collect_result_files` 薄封装保留）；
  payload 增补 `result_files` + `symbol_details`（后者此前被 `report_result` 丢弃，
  压测记录的恒 null 即此根因）；服务端落 `results.result_files` JSONB 列
  （schema 幂等 + 应用层懒补列，缺列降级），`/api/results/<id>/summary` 增量返回。
  测试 `tests/test_result_files_truncation.py`（11 例）。
- **§8.7 沙箱清理**：daemon 自建 `qre-worker-job<id>-` 目录并透传 runner
  （子进程模式经 `execute_job_subprocess(work_base=...)`）。**唯一删除前提 =
  completed 且云端完整副本已确认**（主 Agent Required Fix 2026-11-03 修正，
  旧稿「安全终态即删」会删掉上传失败时的唯一完整副本）：上传失败（failed）、
  上传开关关闭（blob 从未上云）、20 MiB 截断（云端缺文件）、取消/过期/回队/
  终态未知一律保留本地；叠加归属匹配（系统临时目录 + 精确前缀匹配本 job）。
  压测遗留 job7/job8 目录不在清理范围。测试 `tests/test_worker_tmp_cleanup.py`
  （清理 18 例：确认上传后才清 + 各类保留路径 + 归属保护）。
- **§8.11 progress 真实更新**：runner 守护线程按逐股产物计数写
  `<work_base>/progress.json`（batch 5%→90% 真实百分比；其他模式只报 phase 不虚构）；
  daemon 心跳携带（单调守卫），执行完 95、分片上传 95→99 ramp 兼续租。
  **Required Fix 2（job 212 生产实测，2026-11-03）**：终态 progress=100 /
  message='结果已回传' 由服务端在三条 completed 路径（files 全部落盘 /
  meta-only / 旧单包）同一事务落定——daemon 原「completed 后 heartbeat(100)」
  必被拒（heartbeat WHERE 只放行 leased/running/uploading），终态进度曾停在
  99；事后心跳已删除。回归 `tests/test_result_upload_terminal_progress.py`
  （5 例，真实临时 PG 库）。
- **§8.15 reaper 防重算**：`_reap_expired` 新增一句——`uploading` + 租约过期 +
  已有 results 行 → 直接 `failed`（`result_upload_error`，可读 message），不回队；
  无 results 的 uploading 与 leased/running 维持原语义。测试
  `tests/test_reap_uploading_with_results.py`（5 例，真实临时 PG 库）。

协议文档 `17_JOB_PROTOCOL.md` §3.2/§3.3/§3.4/§4.2 已同步；`deploy/saas/cloud_schema.sql`
补 `results.result_files`（ECS 老库需 DBA apply）。**未实施项**：无（CR 范围收口）。
