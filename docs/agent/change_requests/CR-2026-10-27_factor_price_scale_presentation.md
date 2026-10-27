# CR-2026-10-27 因子呈现复权口径系统性排查与修复

## 背景

用户反馈“每次 K 线/技术指标调用都会出问题”，要求彻底排查别名、呈现与复权口径，避免重复救火。本 CR 记录系统性根因和修复边界。

## 排查事实（2026-10-27）

1. **注册表层健康**：`configs/factor_registry.json` 895/895 列有中文名，`validate_registry()` 0 issue，`validate_display()` 0 issue，coverage 100%。
2. **别名歧义已受控**：`duplicate_aliases()` 有 91 项，主要是同列不同价格口径（close/typical/average）与少数同义财务列；`resolve()` 对歧义返回 candidates，不静默错配。
3. **旧产物别名拆面板**：生产 job58 个股详情 factors 为 `macd_dif/macd_dea/macd_hist` 且 `col/display` 为空；旧启发式不识这类别名，导致 MACD 三线拆成三个副图。已在 `factor-layout.js` 修复。
4. **复权口径系统性根因（严重）**：
   - 因子表按 **hfq（原始价 × adj_factor）** 落库；
   - 引擎 raw 模式也把价格列 × adj_factor，所以回测信号与因子同口径；
   - 但 GUI K 线详情按 **前复权@最新（price × adj_factor / latest_adj_factor）** 展示；
   - 因此 EMA/BOLL/MACD 等价格型因子直接叠加到 K 线会差 `latest_adj_factor` 倍。
   - 实测：000001.SZ 2026-10-27 `ema_5=1616.44`，K 线 close=11.47，adj=142.0699；1616.44/142.0699≈11.38，才与 K 线同尺度。
5. **买入持有收益也曾依赖环境变量**：`_fetch_symbol_range_returns()` 在 `QRE_PRICE_BASIS != raw` 时用原始 close，跨除权会跳空；已改为恒用 hfq。

## 修复边界

- 不改引擎回测语义：引擎仍消费 hfq 因子与 hfq 价格列。
- 只修 GUI/呈现层：
  - `_fetch_stock_daily()` 不再依赖 `QRE_PRICE_BASIS`，详情 K 线统一前复权@最新。
  - `_fetch_factor_panels()` 对价格型因子除以该股最新 `adj_factor`；无量纲因子不换算；阈值同步换算。
  - `_fetch_symbol_range_returns()` 恒用 hfq 计算买入持有收益。
- 建立单一价格尺度分类：`gui.factor_registry.is_price_scaled()`，游戏与 GUI 共用，避免两套家族表漂移。
- 旧 gzip 产物仍可能带未换算因子；新生成详情/新 run 才带修正口径。历史产物不重算、不回填。

## 验证

- 新增测试：
  - `_factor_is_price_scaled` 分类；
  - `_fetch_factor_panels` 价格型因子换算、阈值换算、无量纲不换算；
  - `_fetch_symbol_range_returns` 恒 hfq 且不依赖环境变量；
  - 游戏 price basis 测试改用共享分类后继续通过。
- `tests/test_gui_lab_result.py tests/test_factor_registry.py tests/test_trading_game_price_basis.py tests/test_trading_game_factors.py` → 107 passed。
- 全量 `uv run pytest tests/ -q` → `2930 passed, 24 skipped, 4 warnings`。
- ECS：同步 `lab_result.py` + `factor_registry.py`，qre-saas active；job58/symbol/factors API 200。

## 遗留

- 历史 job 的旧 `_symbol_details/*.json.gz` 可能仍是未换算因子；需要时按个股重新生成，不做批量回填。
- 分时因子、分钟级 K 线复权适配仍挂起。
- 重播界面尚未完整 TV 化。
