# Implementation Brief

## Task ID

QRE-SAAS-ACCESS-FALLBACK-FINAL-REVIEW（whole-branch review 全量发现收口）

## Created By

KIMI_CODE（2026-10-24；用户明确指定修复、测试、文档，并授权 commit/push/ECS 部署）

## 背景与关键现状

- `job.html` 的 summary/chart/tag/risk 直接等待 `apiFetch` 与 `resp.json()`，没有 records/symbol 已有的 AbortController、deadline、epoch 保护，响应头或响应体永久 pending 时页面无法收口。
- `symbol.html` 已有请求控制，但 5 分钟活跃等待上限错误复用「加载失败」语义；job 与 symbol 的成功重渲染还会重复注册 replay/save/watch/resize 监听。
- showcase 个股缺失响应虽保留 `can_generate`，但公开只读场景前端仍展示必定被后端 403 拒绝的生成按钮；new 的 `pollJob` 未把 expired 当成立即终态；job chart/tag 的 401 尚未统一无权。

## Goal

1. 为 job 主轮询和 risk 建立覆盖请求与 JSON body 的统一超时/取消 helper；重试可 abort 并 supersede 旧轮次，旧响应不得覆盖新轮次，timer 始终单例。chart/tag 401 统一无权，chart 404 保持失败，tag 404 保持无归因。
2. symbol 的 5 分钟活跃等待上限显示「已暂停自动刷新」、任务可能仍运行的说明与重试，不显示加载失败。
3. job 与 symbol 一次性交互绑定和每轮数据渲染分离或显式幂等；连续成功及失败后重试均不累积监听，单次点击只发一次 POST。
4. showcase 404 响应新增 `readonly` 且保留 `can_generate` 兼容；前端只读时仅说明公开经典策略无该股详情，不展示生成按钮，后端 403 authoritative guard 不变；new 的 expired 立即终态。
5. 全部按 TDD 先 RED 后 GREEN；跑指定五个 SaaS 测试文件与渲染模板 Node 解析，更新长期文档、最终修复报告并执行 finalize 检查。

## Validation

- 目标 RED/GREEN：job 四资源 fetch/body pending、重试 abort/epoch/timer、401 分流与监听计数；symbol 暂停文案、连续初始化与失败后重试监听计数；showcase readonly 前后端；new expired。
- `/home/van/.local/bin/uv run python -m pytest tests/test_gui_saas.py tests/test_gui_saas_pages.py tests/test_saas_authing.py tests/test_gui_lab.py tests/test_saas_symbol_ux.py -q`
- 渲染后的相关 Jinja 模板内联脚本逐段 Node `new Function()` 解析。
- `bash scripts/check-progress-docs.sh`、`bash scripts/git-finalize-check.sh`、`git diff --check`。
- 不运行真实全量回测；完成后 push 并部署 ECS。拟提交信息：`fix(saas): 收口详情请求与只读交互边界`（用户已明确授权 commit/push/ECS 部署）。
