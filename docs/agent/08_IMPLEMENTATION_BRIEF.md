# Implementation Brief

## Task ID

QRE-SAAS-PARAMETER-TIPS-001（回测参数口径与单位提示）

## Created By

KIMI_CODE（2026-10-25；用户指定，不交给 Step 5）

## Goal

为新建策略页全部基础/高级回测参数补充 label 悬停、键盘聚焦和移动点击说明，解决金额、比例、默认值与共享/批量资金口径不清。复用 `LabUI.helpTips()`，不增加可见灰字，不改参数默认值、YAML 或回测行为。

## Implementation

- 覆盖策略 ID、回测区间、标的范围、板块/概念、随机数量、指定代码，以及模式、初始资金、持仓、入出场价格、止损止盈、移动止损、佣金、最低佣金、印花税和滑点。
- 金额单位元；比例小数（0.08=8%、0.0003=0.03%）；0/留空含义逐项说明。
- 共享资金为多标的共用总资金，批量为每股独立初始资金；VWAP、止损止盈和移动止损口径与现有引擎一致。
- `tests/test_saas_parameter_tips.py` 先 RED 后 GREEN，真实 Chromium 桌面与移动逐字段验证。

## Validation

- 桌面 1280 与移动 375 各 14 个高级参数提示完整可见，无 JS error/横向溢出，证据 `.tmp/parameter-tips/`。
- 全量 `uv run python -m pytest tests/ -q --ignore=tests/data_test` → 2536 passed + 5 skipped。
- 未运行真实回测；未经用户批准不 commit/push/部署。
