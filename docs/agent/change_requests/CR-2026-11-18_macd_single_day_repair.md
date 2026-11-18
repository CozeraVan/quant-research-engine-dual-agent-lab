# CR-2026-11-18 MACD 2026-11-05 单日修复

## 范围与证据

- `tests/test_factor_param_variants_data.py` 红灯，000001.SZ 的 4 组参数 × 3 序列均仅 2026-11-05 越界；最大差异 1.575891，其余历史在两位小数舍入容差内。
- 只读诊断：`.tmp/macd-drift-20261118.json`；当前行情全历史独立重算生成 `.tmp/macd-repair-values-20261118.json`。
- 当日误用 raw close 的假设经反事实验证不成立，不据此修数据。

## 数据安全与结果

- 精确目标 1 行：`(000001.SZ, 2026-11-05)`，12 个 MACD 字段。
- 正式修改前建立 `factors.stock_daily_momentum_close_backup_20261118` 与 `..._shadow_20261118`，各 1 行；先生成影子值并核对，再按同 WHERE 更新正式表 1 行。
- 备份、影子和应用日志均在 `.tmp/macd-repair-*.log`；未改 `public.stock_daily`，未重跑回测。
- `uv run pytest tests/test_factor_param_variants_data.py -q -p no:randomly` → 2 passed。
