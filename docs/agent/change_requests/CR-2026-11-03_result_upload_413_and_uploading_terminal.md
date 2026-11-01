# CR-2026-11-03 · 全量回测结果回传缺陷：413 丢结果 + uploading 无终态导致重算

> 来源：`docs/agent/27_STRESS_TEST_2026-11-02.md` §8.14 / §8.15（2026-11-02 全期全量压测实测）。
> 严重度：**高**——一次 42 分钟 / 6 GB 的全市场计算可因回传失败整体作废，且失败后会再跑一遍。
> 状态：**已立项，未改代码**。压测纪律要求「只记录不修」，修复留待本 CR 批准后实施。

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

**仍未实施**：
- B：分片上传（单 part + 自定义 manifest，或分批多次 POST）——根治方案，排期待定；
- §8.5：20 MiB 超预算文件静默跳过、无 `truncated` 标记；
- §8.7：`/tmp/qre-worker-job*` 不清理；
- §8.11：batch 全量 `progress` 不更新；
- §8.15 的 reaper 侧加固：`_reap_expired` 仍会把 `uploading` + 租约过期的 job 重排
  （现在 worker 会主动 fail，但若 worker 进程被 kill 在回传中途，仍会走重排路径）。
