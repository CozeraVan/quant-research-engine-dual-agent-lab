# CR-2026-10-30 · 2.3 个股 K 线主图抬高

> 任务书：`docs/agent/change_requests/TASK-2026-10-30_deepseek_ui_round4.md` §2.3
> 实施：DeepSeek 子 agent / 复核：Kimi
> 改动文件：`src/quant_research_engine/gui/static/replay.js`、`src/quant_research_engine/gui/saas/templates/symbol.html`、
> `tests/test_saas_replay_tv.py`、`tests/test_saas_replay_boundaries.py`

---

## 1. 改动

### 1.1 共享高度公式（`static/replay.js:159-168`）

静态 `renderKline` 与重播 `mountKlineReplay` 共用 `klineHeightForPanes`，只改这一处：

| 副图数 | 旧 | 新 |
|---|---|---|
| 0 | 520px | **620px** |
| 1 | 640px（480+1×160） | **740px**（560+1×180） |
| 3 | 960px（480+3×160） | **1100px**（560+3×180） |

```js
function klineHeightForPanes(paneCount) {
  var n = Math.max(0, Math.floor(Number(paneCount) || 0));
  return n > 0 ? 560 + n * 180 : 620;
}
```

单副图增量 160→180、基座 480→560：主图（K 线）因此从 320px 抬到 380px，
副图（MACD/量）同时略获 20px，避免「主图变高、副图变挤」。

### 1.2 首帧占位（`symbol.html:116`）

`#chart-kline` 内联高度 `520px` → `620px`，与 `klineHeightForPanes(0)` 一致，
ECharts 初始化前不再有一次高度跳变（有副图时运行时会被 helper 覆盖成 740px）。

## 2. 测试（先 RED，后 GREEN）

先改测试、跑 RED（`.tmp/ds-round4/` 已记录）：

```
tests/test_saas_replay_tv.py .......F..          ← 3 failed
  TestReplayFrameLayout::test_exit_restores_static_tv_view   actual '520px' expected '620px'
  TestTooltipUnitCleanup::test_replay_height_matches_static_formula  actual 520 expected 620
  （另一处 helper 公式断言 520/640/960）
tests/test_saas_replay_boundaries.py  F
```

改实现后：

```
uv run pytest tests/test_saas_replay_tv.py tests/test_saas_replay_boundaries.py \
  tests/test_saas_static_kline_tv.py -q
→ 39 passed
```

`tests/test_saas_static_kline_tv.py:406/514/643` 仅在注释里提到 helper，无数字断言，未改。

## 3. 真实浏览器实测（`.tmp/ds-round4/measure.py browser --tag=after2.3`）

| 视口 × 主题 | `#chart-kline` 高度 | 宽度 | docW/scrollW |
|---|---|---|---|
| 1920 light / dark | **740px** | 1778 | 1920/1920 |
| 1440 light / dark | **740px** | 1298 | 1440/1440 |
| 375 light / dark | **740px** | 163 | 375/375 |

- 6 组合均为 `740px`：fixture 带 1 个 MACD 合并副图，运行时 helper 覆盖了内联 620px，
  说明「静态内联首帧 + 运行时公式」两条路径都对。
- 三个视口 `docW == scrollW == bodyScrollW`，无横向溢出。
- `=== PAGEERRORS ===` → `(none)`。
- 截图：`.tmp/ds-round4/after2.3-{1920,1440,375}-{light,dark}-{job,sym}-{top,risk}.png`。

## 4. 未动

- **pane 比例**：任务书明确不动 25%/42%/10% 那组；本次只改容器总高，`grid` 高度分配逻辑未碰。
- 工具栏、TV 布局、右侧标尺、画线逻辑未改。
- `tests/test_saas_replay_tv.py` 中 `620px not in _mount_body()` 改为 `620px`——该断言是
  「重播不得再写死高度」，`replay.js` 里只出现在注释，代码无字面量，通过。

## 5. 遗留

- 375px（单列）下 K 线宽仅 163px、高 740px，纵向很瘦；本轮只按要求抬高高度，
  窄屏的宽高比问题记入遗留，等后续是否对 ≤768px 单独降档再定。