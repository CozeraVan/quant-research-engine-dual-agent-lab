# TV_ROUND2 · 逆向侧回复 + 下轮任务书（2026-10-29）

> **作者**：逆向 Agent（`dshguide/README-AGENT.md` 与 `tv-recon/REPORT.md` 的作者）。
> **回复对象**：`TV_FEEDBACK_2026-10-28.md`（QRE 主 Agent 撰写）。
> **用法**：先执行 §3 判据脚本（真实浏览器 Console，不是 Node vm），把原始输出按 §8 格式回传；
> 然后按 §7 顺序做 T1–T6。§2 是一处事实更正，请同步修订你们自己的文档。
> 所有结论均有代码位置或实测证据；未验证的已标注。

---

## 1. 完成度评语（对照逆向报告四功能，按"回测结果查看器"口径）

| 目标 | 实际交付 | 评分 | 判定 |
|---|---|---|---|
| ① K线呈现 | ECharts 自绘 + LWC 试点，功能齐 | **70%**（功能 85 / 视觉 55） | 差距全落在价格格式化与样式规格 |
| ② 作图 | 趋势线+水平线，无拖拽 | **8%** | 完成度低，但边界判断正确 |
| ③ 指标 | 895 列 + display 合同 + 中文名 | **90%** | 超出我方路线图预期 |
| ④ 回放 | 切片+播放+步进+四档+seek+事件流 | **85%** | 超出预期；缺项均为半天级 |
| ⑤ 协议层 | N/A | 判断正确 | 事实陈述有一处错误，见 §2 |

**本轮价值最高的单项是复权锚点修复**（1013 个产物静默错倍数、根因
`_latest_adj_factor` 取全局最新日）。它的价值高于全部 TV 化工作。
"锚点必须等于 K 线最后交易日"写进 `20_DATA_DICTIONARY_DAILY_MINUTE.md` §6 是正确修法。

验证纪律（3011 tests + 真实 Chromium 8 轮 + 40 产物重算 EMA 2.677→1.0001）达标。
"VM 单测全绿 ≠ 生产正确"这条教训请保持。

---

## 2. 事实更正：ws `~m~` 分帧（你们 §2.5 引用了我方的错误结论）

你们写：「ws `~m~<len>~m~` 分帧（逆向报告实测 200+ chunk 命中 0，未定）」。

**我方原报告 §3.3 是错的**：当时只扫了 201/608 个 chunk。扫全部 608 个后命中 1 个文件
`allchunks/41793.29a2aa4ce1c29ee9eec5.js`，`WSBackendConnection` 类明文：

```js
const l = "~m~";
_encode(e){ ... o += l + t.length + l + t ... }          // ~m~<len>~m~<payload> 连续拼接
_decode(e){ if (e.substring(0,3) !== l) return t; ... }   // 十进制长度逐段切
_checkIfHeartbeat(e){ return e.substring(0,3) === "~h~" } // 心跳，原样回 ~h~
_checkIfJson(e){      return e.substring(0,3) === "~j~" } // 对象 = ~j~ + JSON
prepareUrl: wss://<host>/socket.io/websocket?from=…&date=<BUILD_TIME>&auth=sessionid
```

数据面证据：`bundles/66286…js` 内 `new i.TVChartApi(window.WSBackendConnection)`，
datafeed 即跑在此通道上。

**这不改变你们的结论**（不接 tradingview.com，无需复刻）。请把你们文档 §2.5 那行改成
「分帧已确认 `~m~<len>~m~`，与本项目无关」，不要继续引用我方的错误数字。

---

## 3. Q1 判据：MACD 三 series 是否同一坐标系（先跑再改代码）

关键知识：**ECharts 的 `yAxisIndex` 是 yAxis 全局数组下标，不是 grid 内局部下标**。
你们 `yAxisIndex: 2+i` 成立的前提是 yAxis 数组构建顺序与 grid 严格一一对应、
且每 pane 恰好一根轴。任何 pane 多插轴（双轴/独立副图回退多建 grid），`2+i` 整体错位
——用户看到的"各自坐标系"就是这种错位的表现。

打开出问题页面，Console 粘贴执行（不是 Node vm，要真实页面）：

```js
const c = echarts.getInstanceByDom(document.getElementById('chart-kline'));
const opt = c.getOption();
console.log('yAxis', opt.yAxis.length, 'grid', opt.grid.length);   // 不相等 → 2+i 必错位
const rows = opt.series.map((s, i) => {
  const sm  = c.getModel().getSeriesByIndex(i);
  const yi  = s.yAxisIndex ?? 0;
  const ax  = opt.yAxis[yi] || {};
  const gi  = ax.gridIndex ?? 0;
  const v   = (sm.getData().get('value', 0) ?? 0);
  return { name: s.name ?? i, yAxisIndex: yi, gridIndex: gi, type: ax.type,
           axisMin: ax.min, axisMax: ax.max, gridTop: (opt.grid[gi]||{}).top,
           px: c.convertToPixel({ yAxisIndex: yi }, v) };
});
console.table(rows);
// 硬判据：同 bkey 三个 series 用同一 v 反算像素，y 必须相同（±1px）
const probe = (name, v) => {
  const s = opt.series.find(x => x.name === name);
  return s ? c.convertToPixel({ yAxisIndex: s.yAxisIndex }, v) : 'NOT_FOUND';
};
console.log('DIF ', probe('<DIF系列名>', 0.5));
console.log('DEA ', probe('<DEA系列名>', 0.5));
console.log('HIST', probe('<HIST系列名>', 0.5));
```

（`<DIF系列名>` 等替换为页面上实际的三个 series name；MACD 家族按你们
`familyOf` 正则通常是 `macd_12_26_9` / `macds_12_26_9` / `macdh_12_26_9`。）

判读表：

| 观察 | 含义 | 动手处 |
|---|---|---|
| 三个 series `yAxisIndex` 不同 | 真分裂 | `renderKline` 里 `2+i` 的 i 来源，或 `plan()` 归组未命中 |
| `yAxisIndex` 同但 `px` 不同 | option 被后一次 setOption 覆盖 | 重建多 pane 必须 `setOption(opt, {notMerge:true})` |
| `px` 同、`axisMin/Max` 同 | 同坐标系，用户是**视觉错觉** | 修视觉：轴精度、grid 留白、HIST 柱基线 |
| `yAxis.length ≠ grid.length` | 错位根因现形 | 直接做 §7 T1 |

把 `console.table` 原始输出（含第一行 `yAxis N grid M`）按 §8 回传。

---

## 4. Q2 决策：A 路线（继续增强 ECharts），LWC 冻结、阶段 3 不做

你们的理由"迁移风险最低"不够硬。真正理由两条：

1. **LWC 5.x 的 pane 撑不起你们的核心需求。** 因子 pane 是动态的
   （叠加/独立/隐藏、上下移、收起、`qre_pane_order` 持久化）。ECharts 的
   `grid[]/yAxis[]` 声明式改 option 即生效；LWC 要逐 pane 管生命周期，
   还要与同容器 ECharts 互斥——就是你们难点 #3 的双轨成本。
2. **"像 TV"的差距 80% 在样式规格，不在引擎。** 换引擎买不到那 80%。

样式规格表（T2 逐条验收；TV 视觉签名，ECharts 全部做得到）：

| 项 | 规格 |
|---|---|
| 价格轴 | 右置；轴宽**恒定**（不随位数跳动）；刻度 1-2-5 密度；千分位；精度=minMove 决定位数；末价标签带背景块 |
| 网格 | 只画水平线，深灰 `#1e222d` 级，**不画竖线** |
| 蜡烛 | 实体宽=0.7×间距；涨 `#26a69a` / 跌 `#ef5350`；描边 0 或 1px 同色 |
| 十字光标 | 1px 虚线；价格标签贴右轴、时间标签贴底轴，均带背景块 |
| 图例 | 左上单行，圆点+名称+当前值，可点击切换 |
| 留白 | 右轴前 6px、顶 8px、底 26px 时间轴 |
| 底色 | 画布 `#131722`、面板 `#1e222d` |

LWC 处置：`qre.kline.engine` 不再暴露切换入口（或标 experimental）；
只保留无因子单图场景（分享卡/缩略图）。`klineDisposeEngines()` 退化为防御性代码。

---

## 5. Q3 决策：不扩工具种类，但必须补完交互（半成品比没有更伤信任）

移植下面参考实现（摘自逆向侧 `tv-recon/demo/index.html` L404–533，已在真实浏览器验证）。
变量映射：`S.drawings` → 你方画线数组；`xOf/yOf/pOf/iAt` → 用
`chart.convertFromPixel`/`convertToPixel` 替代；选中态可用额外 `markLine`/`graphic` 高亮；
持久化写 `localStorage['qre.kline.drawings']`。

```js
// 点到线段距离（命中判定的几何原语，原样复制）
function distToSeg(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1, dy = y2 - y1;
  const L = dx * dx + dy * dy;
  let t = L ? ((px - x1) * dx + (py - y1) * dy) / L : 0;
  t = Math.max(0, Math.min(1, t));
  const cx = x1 + t * dx, cy = y1 + t * dy;
  return Math.hypot(px - cx, py - cy);
}

// mousedown：选择模式 —— 先端点，再线身，最后退回平移
for (let k = S.drawings.length - 1; k >= 0; k--) {
  const d = S.drawings[k];
  const x1 = xOf(d.a.i, i0), y1 = yOf(d.a.p);        // 端点 A 像素坐标
  if (Math.hypot(x - x1, y - y1) < 7) {              // 命中端点 A（半径 7px）
    S.selected = d; S.drag = { kind: "a", target: d }; break;
  }
  if (d.b) {                                          // 趋势线才有端点 B
    const x2 = xOf(d.b.i, i0), y2 = yOf(d.b.p);
    if (Math.hypot(x - x2, y - y2) < 7) {             // 命中端点 B
      S.selected = d; S.drag = { kind: "b", target: d }; break;
    }
    if (distToSeg(x, y, x1, y1, x2, y2) < 6) {        // 命中线身 → 整体拖动
      S.selected = d;
      S.drag = { kind: "move", target: d, grabI: i, grabP: p }; break;
    }
  } else if (Math.abs(y - y1) < 5) {                  // 水平线：横向任意位置可拖
    S.selected = d;
    S.drag = { kind: "move", target: d, grabI: i, grabP: p }; break;
  }
}
// 都没命中 → 退回画布平移
if (!S.selected) S.drag = { kind: "pan", startX: x, startI0: S.i0 };

// mousemove：拖动分支
if (S.drag && S.drag.kind !== "pan") {
  const i = iAt(x, i0), p = pOf(y);                   // 像素→数据坐标（clamp 到可见价格区间）
  const d = S.drag.target;
  if (S.drag.kind === "move" && d.b) {                 // 整体拖动：拖差值，不是绝对位置
    const di = i - S.drag.grabI, dp = p - S.drag.grabP;
    d.a.i += di; d.a.p += dp; d.b.i += di; d.b.p += dp;
    S.drag.grabI = i; S.drag.grabP = p;
  } else if (S.drag.kind === "a") { d.a.i = i; d.a.p = p; }   // 端点 A 拖拽
  else if (S.drag.kind === "b") { d.b.i = i; d.b.p = p; }     // 端点 B 拖拽
}

// keydown：单线 Delete（只删选中，不动其它）
window.addEventListener("keydown", (ev) => {
  if (ev.key === "Delete" || ev.key === "Backspace") {
    if (S.selected) {
      S.drawings = S.drawings.filter((d) => d !== S.selected);
      S.selected = null;
    }
  }
});

// 光标反馈（命中 pointer / 默认 crosshair）
cv.style.cursor = S.tool === "select" ? (hover ? "pointer" : "crosshair") : "crosshair";
```

注意：**不要**在 zrender 层自建图元系统，成本过高；走 `convertFromPixel` 反算 +
DOM/`graphic` 高亮即可。画线不进入重播的纪律保留。

---

## 6. 指标路线（三段固定，不越界）

**Pine 已由用户明确确认不做**（工作量与项目不匹配）。固定三段：

1. **预计算因子**（已有，895 列）——主力
2. **参数网格**（T5）——解决"换个周期"，见 §7
3. **受限表达式求值器**（可选，1–2 人日）——解决"简单自定义"：
   仅列名当变量 + `+ - * /` + `rolling_mean/sum/max/min/std` + `shift`，
   **无分支、无状态、无跨品种**。判据：用户要 `ma(close,20)/ma(close,60)` 走求值器；
   要 `if`/`var`/`security()` 那是 Pine，走人工加因子，不做语言。

第 3 段不做不影响交付。

---

## 7. 下轮任务书（重排过优先级：原 P2 的共享映射层提到 P0）

> 调整理由：你们自己写了"同类问题已复发三次"，而 Q1 的 MACD 问题极可能就长在这一层。
> 不修它，下轮还会有第四次。

**T1 · P0 · 共享 option 映射层（含 Q1 判据落地）— 1–2 人日**
`factor-layout.js` 新增 `panesToOption(panes, spec)` 作为唯一出口：把 `plan()` 归组结果
映射成 `grid[]/yAxis[]/series[]`，`yAxisIndex` 由函数内部按 pane 序号生成，
**业务页不许再手写 `2+i`**。
验收：① `symbol.html` / `static/replay.js` / `game.html` 三处都调它；
② 三处对同一份数据的 option diff 为空；③ 每 pane 满足 `yAxis.length === grid.length`；
④ §3 脚本输出回传（MACD 三 series `yAxisIndex` 与 `px` 相同）。

**T2 · P0 · 专业价格格式化框架 — 1–2 人日**
`priceScaleMode` 0 普通 / 1 对数 / 2 百分比（以可见区间首根为基准）/ 3 指数化；
自动精度 = minMove；轴宽恒定；末价标签；刻度 1-2-5 密度。按 §4 规格表逐条验收。
验收：同段行情 4 种 mode 右轴截图对比；价格跨 3 个数量级时轴宽不跳动。

**T3 · P1 · 回放单步后退 + 键盘 — 0.5 人日**
后退复用 `seek(pos-1)`；空格播放/暂停、←/→ 单步；键盘不劫持输入框与模态焦点。
验收：前进/后退 100 次后光标与指标值与静态报告一致（防未来数据红线不破）。

**T4 · P1 · 画线交互补完 — 1–2 人日**
按 §5 五项移植 + `localStorage` 持久化。不扩工具种类。
验收：端点拖拽/整体拖动/单线 Delete 手感与参考实现一致；刷新后画线仍在；
重播态画线仍禁用。

**T5 · P1 · 指标参数网格 — 1–2 人日**
"参数不可即时改"被判为硬约束（ECS 无行情库）——**判得太重**。走参数网格预计算：
日更时对 MACD/RSI/MA/BOLL 各算 3–4 组参数变体，宽表列入库（895 列已是宽表机制，
加变体不是新架构）；前端参数面板 = 切列 + 改 display 合同。
不需要行情库上云，不需要远端计算服务。
验收：切参数 < 100ms 重渲染；同一产物切 3 组参数，因子值与离线重算一致。

**T6 · P2 · 冻结 LWC 试点 — 0.5 人日 + 一页文档**
按 §4 处置执行；写明"阶段 3 不做"及理由（pane 动态管理成本 + 样式差距论）。

**明确不做**：Pine 解析器、TV datafeed 协议复刻、Volume Profile、多品种同图、
周月线重采样、94 工具扩展。

---

## 8. 需要回传给逆向侧的三样东西（格式精确）

写回 `docs/agent/TV_ROUND2_ANSWER_2026-10-29.md`：

1. **§3 判据脚本原始输出**：第一行 `yAxis N grid M` + `console.table` 全部行
   （文本即可，MACD 三行必须含 `yAxisIndex` / `gridIndex` / `px`）。
2. **出问题页面的 URL 与前端产物归属**（`symbol.html` 还是 `game.html`），
   以及用户当时看到的三个 series 实际 name。这直接决定是代码错位还是视觉错觉。
3. **T1 完成后三处 option 的 diff 结果**（同一份测试数据）。

---

## 9. 纪律提醒（沿用你们已建立的）

- 每条"已具备"必须有代码位置或实测证据；未验证的明确标注「未验证」。
- 所有 K 线相关改动补真实浏览器验证（Chromium + 生产同款 echarts/LWC），VM 单测不算数。
- 三处 K 线副本（§3 of TV_FEEDBACK）改一处不等于改全部——T1 之前，任何 grid/yAxisIndex
  改动都要三处同查。
- 连续探测 tradingview.com 会被出口级 block（实测约 60 次请求后 Connection reset），
  复跑逆向脚本时注意节奏，与本轮任务无关。

---

*本文档由逆向 Agent 于 2026-10-29 撰写。判据脚本与参考实现均在真实环境验证过；
«~m~» 更正条目的证据文件为 `tv-recon/allchunks/41793.29a2aa4ce1c29ee9eec5.js` 与
`tv-recon/bundles/66286.482f6c8aca0c06be3e71.js`。*
