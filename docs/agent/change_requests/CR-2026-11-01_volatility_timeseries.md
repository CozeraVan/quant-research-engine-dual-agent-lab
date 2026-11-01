# CR-2026-11-01 · P2-15 波动率时序曲线：后端可选序列数据

> 任务：P2-15 波动率时序曲线。目标：让 FRM 波动率从“最新值 + 三档计数”升级为可画 EWMA/GARCH 年化波动时序曲线，并叠加低/中/高三档阈值参考线。为避免产物体积和稳定性风险，本轮先落地**后端可选序列数据**，默认关闭；前端曲线与生产开启策略后续单独推进。

---

## 1. 现状与缺口

- `risk_report.json` 只透出波动率相关 5 个字段：`ewma_latest`、`garch11`、`regime.counts`、`regime.latest`、`regime.thresholds_annual`。
- 前端 `vol-regime.js` 已支持阈值绝对轴 gauge，但**没有时间序列**，画不出“波动率随时间变化 + 阈值水平线”。
- 后端 `risk/report.py` 已内部计算 EWMA 序列用于 regime，但不下发；GARCH 只下发最新条件波动。

---

## 2. 本轮实现（后端，默认关）

### 2.1 新增加法

- `risk/volatility.py` 新增 `garch_volatility_series()`：GARCH(1,1) 条件波动率序列（小数口径，与 `fit_garch11()` 同一拟合路径）。
- `risk/report.py` 新增可选节 `volatility.series`：
  - 开关：`config.include_volatility_series`，默认 `False`；
  - 抽稀：`config.volatility_series_max_points`，默认 `500`，等间隔抽样，**末值必含**；
  - 年化：`日波动 × √annualization_factor`，保留 6 位小数；
  - 内容：`ewma_annual` / `garch_annual` 两个数组 + `annualization_factor` / `max_points` / `note`；
  - `meta.sections.volatility_series` 回显开关状态。
- `gui/lab_result.py::build_lab_risk_view()` 透出 `volatility.series`，缺节为 `None`，不抛错。

### 2.2 兼容性

- 默认关闭 → 现有 `risk_report.json` 与产物体积**零变化；
- 开启时若 GARCH 数据不足，`garch_annual` 为 `{"error": ...}` 降级，不拖垮整份报告；
- EWMA/GARCH 序列都来自已有口径，不引入第三种波动率算法。

---

## 3. 测试

- TDD RED→GREEN：
  - 默认关闭：`volatility` 无 `series`，`meta.sections.volatility_series=False`；
  - 开启：`ewma_annual` / `garch_annual` 非空、正数、长度 ≤ `max_points`、末值存在；
  - 与现有 `test_risk_report.py` / `test_risk_volatility.py` / `test_vol_regime.py` / `test_gui_risk_report.py` 全绿。

---

## 4. 未做 / 下一步

1. **前端时序曲线（已完成 2026-11-01）**：`vol-regime.js` 新增 `seriesModel()` / `seriesChartOption()`；`job.html` 与 `lab_result.html` 的 `renderRiskVol` 有序列时画 EWMA/GARCH 年化波动曲线 + 低/高阈值 markLine，无序列降级为阈值标尺；真实浏览器渲染冒烟通过（canvas 尺寸正常、零 pageerror）。
2. **生产开启策略**：前端已就绪，但 worker/config 仍默认 `include_volatility_series=False`；开启前需实测 `risk_report.json` 体积增量。
3. **性能优化（可选）**：当前开启后会额外拟合一次 GARCH；如成为默认路径，可考虑复用同一次拟合结果。

---

## 5. 风险

| 风险 | 处置 |
|---|---|
| 开启后 report 体积变大 | 默认关；开启时抽稀到 ≤500 点，前端就绪后实测增量再决定默认 |
| GARCH 重复拟合 | 可选优化，当前默认关不影响生产 |
| 前视/口径漂移 | 序列与 `ewma_volatility_series` / `garch_volatility_series` 同源，年化公式与现有字段一致 |
