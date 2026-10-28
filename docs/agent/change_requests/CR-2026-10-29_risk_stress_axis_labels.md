# CR-2026-10-29 修复 FRM 压力测试图两个情景轴标签不显示

状态：已实施，未 commit/push（等用户验收）

## 1. 现象（用户报）

「在 FRM 模块中，有两组数据底座表没有显示 '2018 单边熊市' '2024 小微盘流动性危机'」。

## 2. 根因：ECharts category 轴 `interval` 默认 `'auto'` 会隔一个藏一个

**先排除了后端**：拉生产 job 58 的 `risk_report.json`，4 个情景全都有数据
（`bear_2018` 累计 -8.39%/243 日、`microcap_liquidity_2024` -0.37%/37 日），
`build_lab_risk_view` 转换后 `stress.scenarios` 也是 4 条，`skipped` 为空。

**真因在图表渲染**：`renderRiskStress` 的 xAxis 没配 `axisLabel`，ECharts 对
category 轴默认 `interval: 'auto'`——它测量标签宽度后发现会重叠，就**每隔一个
隐藏一个**。4 个情景于是只画第 1、3 个的轴标签，第 2、4 个（正是 2018 和 2024）
只剩光秃秃的柱子。用户描述成"两组数据底座表没有显示"非常准确——缺的确实是
柱子底下的轴标签。

真实浏览器截图对比（修复前/后）已确认。

## 3. 修复（`lab_result.html` 与 `job.html` 两处同改）

1. **`axisLabel: { interval: 0, hideOverlap: false }`** —— 强制全部显示，禁止重叠隐藏
2. **轴标签取冒号前短名**：`description.split('：')[0]`
   （"2015 股灾" 而非 "2015 股灾：千股跌停 + 流动性枯竭"）——4 个短标签在
   ~950px 里各有 ~237px，不会再触发重叠判断
3. **tooltip 补回完整信息**：自定义 formatter 输出完整 `description` + `n_days`
   （交易日数）+ 两个 series 的百分比值——轴标签缩短后信息不丢失

## 4. 测试

新增 `tests/test_gui_risk_report.py::TestStressAxisLabels` 3 例：

- `test_both_templates_force_all_axis_labels`：两个模板都必须有
  `axisLabel: { interval: 0, hideOverlap: false }`，且不得显式写 `'auto'`
- `test_axis_label_uses_short_name_before_colon`：必须 `split('：')[0]`
- `test_tooltip_shows_full_description_and_n_days`：tooltip 必须含完整描述与 `n_days`

**RED 验证**：把 job.html 改回 `interval: 'auto'` → 契约测试立即红；恢复后 27 passed。

真实浏览器：用生产 job 58 的 `risk_report.json` 现算 risk view 灌进页面，
断言 `n==4`、`interval==0`、`hideOverlap==false`、标签无冒号（短名）、
两条 series 各 4 点、`skipped` 为空；截图 `.tmp/perf-browser/stress.png`
可见 4 个情景标签全部显示。

## 5. 影响面

只改两个模板的 `renderRiskStress`（xAxis + tooltip）。后端、数据、其它图表未动。
