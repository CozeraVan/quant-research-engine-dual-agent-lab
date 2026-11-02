# CR-2026-11-03 · 评审修复 B1–B6（主 Agent 自查后逐项修正）

> 来源：主 Agent 在「只审阅不推进」阶段对 step5 工作（M1–M6、P0-9）的代码级评审。
> 本 CR 记录六个问题的根因、修法与验证；**不含任何新功能**。
> 验证：全量 `uv run pytest -q -p no:randomly` → **3388 passed, 34 skipped**（零回归）。
> 部署：ECS 同步 `app.py` + `agent_api.py`，MainPID 610212，回滚副本
> `/tmp/qre-deploy-20261102T020030Z.bak`；生产 `/saas/`、`/saas/new`、`/api/saas/factors` 均 200。

---

## B1（P1）`NON_RETRYABLE` 误含 `result_upload_error`

- **根因**：daemon 注释与 `17_JOB_PROTOCOL.md` §3.4 都写「传输/5xx 可重试」，
  但服务端把 `result_upload_error` 放进了 `NON_RETRYABLE`，导致连接重置/5xx 也直接 failed。
  daemon 调 `fail()` 不传 `retryable`，由服务端推导，行为与文档矛盾。
- **修法**：从 `NON_RETRYABLE` 移除 `result_upload_error`（4xx 各码仍不可重试）。
- **测试**：`test_result_upload_error_classes.py::test_transport_upload_error_is_retryable`
  锁定「`result_upload_error` 在 `ERROR_CLASSES` 中且**不在** `NON_RETRYABLE` 中」。

## B2（P1）成本信封严重低估，全量场景不可用

- **根因**：`full_a_full` 档基准 `est_seconds=900` 是拍的，`_profile_years()` 对「全区间」
  返回 100，17.8 年全市场估 **160s**，实测 **4312s**（低估 27 倍）；`sample300_5y`
  按 stock-years 线性缩放，20 只×1.5 年估 4.2s，M6 实测约 86.5s/job（低估约 20 倍）。
  线性模型不含固定开销（小 run 由数据加载/绘图/序列化主导）。
- **修法**：改为**两段式模型** `est = FIXED_OVERHEAD + RATE × stock_years`。
  用两组实测点拟合：M6（20 只×1.5 年 = 30 股年 → 86.5s）与 item1/2/3 均值
  （5201 只×17.8 年 = 92578 股年 → 3579s）：
  `RATE = 0.03773 s/股年`，`FIXED = 85.4s`。
  `SCALE_PROFILES` 四档同步改为实测/推算锚点，并标注 `measured_at` 与来源。
- **测试**：`test_validate_ok_returns_cost_estimate_without_executing`（`method=="two_part_model"`、
  估值区间 100–250s）、`test_validate_full_market_estimates_full_profile`、
  `TestCapabilities::test_cost_envelope_shape_and_units`（四档单调性）。

## B3（P1）会话预算 `max_artifact_bytes` 对全量 run 实际失效

- **根因**：`research_run_usage()` 用 `results.artifacts` 的 size 求和，而 20MiB 回传预算
  静默截断让全量 run 只回传约 1% 的产物。统计的是「成功回传的 1%」，不是真实产物体积。
- **修法（本轮只做显式披露，不假装修好）**：`usage` 新增 `artifact_accounting: "uploaded_only"`；
  研究会话详情新增 `artifact_note` 说明该值可能只有真实体积的约 1%。
- **根治（未做，已登记）**：worker 在 `result/meta` 里补 `produced_bytes` 字段并持久化。
  在根治前，真正有效的产物侧保护只有「夜间窗口 + 会话 job 数上限」。

## B4（P2）夜间窗口 start > end 时全部 job 永久顺延

- **根因**：判定 `start_h <= hour < end_h` 在跨零点配置（如 22:00-06:00）下恒为 False。
- **修法**：`start_h > end_h` 时按「晚段或早段」判定（`hour >= start or hour < end`）；
  `start_h == end_h` 视为无开放窗口（全部顺延，配置错误可被发现）。
- **测试**：`test_nightly_window_cross_midnight_supported`、
  `test_nightly_window_same_start_end_means_closed`。

## B5（P2）限流清理每请求都执行 DELETE

- **修法**：只在**每第 10 次成功计数**时清理一次。
- **过程教训**：第一版把清理放在 INSERT 之前，引用了尚未赋值的 `allowed`，
  被外层 `except` 吞掉后静默把限流变成 no-op——回归测试当场抓住。
  已改为放在 INSERT 之后，并在注释中写明这一点。
- **测试**：`test_rate_limit_rows_cleaned_up` 改为连发 10 次请求触发清理。

## B6（P2）`_apply_config_to_yaml` 对非 mapping 的 `data` 节会 500

- **修法**：进入函数先校验 `raw["data"]` 与 `data["factor_fields"]` 均为 mapping，
  不满足抛 `ValueError`（路由层统一 400）。
