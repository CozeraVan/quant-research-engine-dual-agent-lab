# CR-2026-10-29 小数据卡改「白底磨砂玻璃」（card-class.css 二次修订）

状态：已实施，未 commit/push（等用户验收）
关联：`CR-2026-10-29_card_class.md`（同日先把这类卡改成白底紫框，本轮按用户要求改为磨砂玻璃）

## 1. 需求（用户 2026-10-29 追改）

「当前这些小 div 全成了完全白底，我忘记了我们的这些小 div 是**玻璃材质**的，
请重新设计为白底的磨砂玻璃」：

- 半透明白色磨砂：`backdrop-filter:blur(28px) saturate(140%)`，白色 45%–60% 透明度
- 1px 半透明白色描边
- 顶部内侧一道细高光
- 圆角 24px
- 大而柔的紫色阴影

## 2. 关键判断：不新造轮子，直接复用 `.card` 家族的玻璃 token

`lab-theme.css` 早已定义一整套玻璃 token，且 `.card` / `.chart-box` / `.big-link`
三个大卡族都在用：

```css
--card-radius:24px;
--glass-bg:rgba(255,255,255,.48);      /* 45%–60% 区间偏下沿 */
--glass-line:rgba(255,255,255,.5);     /* 1px 半透明白描边 */
--glass-hi:rgba(255,255,255,.75);      /* 顶部内侧细高光 */
--glass-shadow:0 1px 2px rgba(74,58,120,.06),0 18px 46px -14px rgba(74,58,120,.26);
--glass-sheen:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,0) 45%);
```

而且 **`night-mode.css` 的暗色玻璃覆盖名单里本来就有 `.metric-card`**，
`card-fx.js` 的 `TILT_SEL = '.metric-card,.entry-card'` 也早就含它——
**说明设计意图一直是玻璃，只是 CSS 从没跟上**。所以本轮只改 `card-class.css` 的基类，
不动 token、不动 night-mode、不动 card-fx。

## 3. 改动（只改 `static/card-class.css` 两处）

### 3.1 基类：白底紫框 → 磨砂玻璃

```css
.metric-strip .metric-card, .wear-cards .metric-card,
.risk-cards .metric-card, .metric-card {
  background-color: var(--glass-bg);
  background-image: var(--glass-sheen);
  border: 1px solid var(--glass-line);
  border-radius: var(--card-radius);
  box-shadow: inset 0 1px 0 var(--glass-hi), var(--glass-shadow);
  padding: 12px 14px;
  -webkit-backdrop-filter: blur(28px) saturate(140%);
  backdrop-filter: blur(28px) saturate(140%);
}
```

### 3.2 磨损/风险条收回规则：粉底粉框 → 玻璃（同上四项）

## 4. 两个必须保留的细节（都是踩过的坑）

1. **`background` 必须拆成 `background-color` + `background-image`**：
   `background` 简写会重置 `background-image`，把 `--glass-sheen`（顶部受光形成的
   玻璃厚度）抹掉。CR-2026-10-28 磨砂玻璃首版就踩过，已写进
   `12_UI_STYLE_GUIDE.md` §3.16，本轮测试也加了断言
   （`assert "background: " not in rule`）。
2. **`backdrop-filter` 要写 `-webkit-` 前缀 + 标准两行**（与 `.card` 一致）。

## 5. 测试

`TestMetricStripStyleContract::test_all_cards_frosted_glass` 由「白底紫框」改写为
「磨砂玻璃」，逐项断言：`backdrop-filter` 两行、禁用 `background` 简写、
`--glass-bg` / `--glass-sheen` / `--glass-line` / `--glass-hi` + `--glass-shadow` /
`--card-radius`（并交叉断言 lab-theme 里 `--card-radius:24px`）、
磨损/风险条收回规则同样四项且不用简写。

`test_perf_metrics.py` **18 passed**。

## 6. 真实浏览器验证（Chromium）

对 job/symbol × 1440/1024/375 六组合 + job 磨损 5 卡 + job 风险 4 卡 + symbol 磨损 5 卡
+ symbol 风险 7 卡，断言玻璃五要素 + 数值色三分 + 行内等宽 + 非末行填满 + 无溢出：

| 项 | 实测值 |
|---|---|
| 背景 | `rgba(255, 255, 255, 0.48)`（全部一致） |
| 描边 | `rgba(255, 255, 255, 0.5)`（全部一致） |
| 圆角 | `24px`（全部一致） |
| 磨砂 | `blur(28px) saturate(1.4)`（全部一致） |
| 投影 | 含 `inset` 顶部高光 + `74, 58, 120` 紫投影 |
| 数值色 | 中性 `rgb(74,58,120)` 紫 / 盈利 `rgb(201,58,58)` 红 / 亏损 `rgb(30,142,90)` 绿 |
| 布局 | job 指标条 7 一行、symbol 简介条 4+4、ra 条 3 撑满；375px 正常换行 |
| pageerror / console error | **0** |

同时复验：α=12.00% / β=0.89 / IR=0.78、平均持股周期 45.3/48.7 天、
LWC 图例 5 pill 往返全通。全量 `3032 passed, 24 skipped`。
截图 `.tmp/perf-browser/symbol-cards.png`（可见小卡与周边 chart-box 同一玻璃质感）。

## 7. 影响面

只改 `static/card-class.css` 一个文件。token / night-mode / card-fx / 模板均未动。
