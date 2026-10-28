/* QRELwcAdapter — Lightweight Charts 适配层纯函数（CR-2026-10-28 B 路阶段 1）。
 *
 * 只做「detail JSON 合同 → LWC series 定义」的纯变换：不碰 DOM、不依赖
 * LightweightCharts 全局，可在 Node 里直接断言（tests/test_lwc_kline_adapter.py）。
 * 渲染与主题装配在下面的 mountKlineLwc()，由 symbol.html 的引擎开关派发。
 *
 * 合同要点（docs/agent/23_KLINE_IMPLEMENTATION.md §1.3）：
 * - kline.ohlc 顺序是 open, close, low, high；LWC 要 {open, high, low, close}；
 * - 缺失值是 null，必须转成 {time} 空点而不是 null（LWC 会拒收）；
 * - 时间是 YYYY-MM-DD 字符串，LWC 直用，不要转时间戳；
 * - 同一时间戳重复必须先升序去重，否则 setData 抛 "data must be asc ordered"。
 */
(function () {
  "use strict";

  /* ---------- 主题表（DeepSeek 规格，CR-2026-10-28 §1）----------
   * 红涨绿跌色相在两主题下恒定（红 H=0° / 绿 H≈152°），暗色只提亮；
   * 紫系在暗色下提亮一档，与 night-mode.js 的 ECharts 映射保持一致，
   * 保证引擎开关来回切换时视觉无跳变。 */
  var THEME_LIGHT = {
    background: "#FFFFFF",
    textColor: "#6F6879",
    grid: "rgba(103,80,164,0.10)",
    crosshair: "#8B7FBE",
    crosshairLabelBg: "#6750A4",
    border: "#E4DFEE",
    volume: "#B7A6E8",
    up: "#C93A3A",
    down: "#1E8E5A",
    histUp: "#C93A3A",
    histDown: "#1E8E5A",
    dif: "#6750A4",
    dea: "#E8A33D",
    threshold: "#8B7FBE",
    line: "#6750A4",
  };
  var THEME_DARK = {
    background: "#2E236C",
    textColor: "#C8ACD6",
    grid: "rgba(200,172,214,0.12)",
    crosshair: "#A99BD8",
    crosshairLabelBg: "#7E60BF",
    border: "#433D8B",
    volume: "#C8ACD6",
    up: "#FF7A7A",
    down: "#4FD69A",
    histUp: "#FF7A7A",
    histDown: "#4FD69A",
    dif: "#9B84D8",
    dea: "#E8A33D",
    threshold: "#A78BE0",
    line: "#9B84D8",
  };
  // 暗色下需要提亮的紫系线色（其余 overlay 循环色 #E8A33D/#2A9D8F 两主题一致）
  var DARK_LINE_MAP = { "#6750A4": "#9B84D8", "#8B7FBE": "#A78BE0" };

  function theme(dark) {
    return dark ? THEME_DARK : THEME_LIGHT;
  }
  // 因子/均线线色按主题映射（ECharts 路径用 QREFactorLayout.COLORS 原值）
  function lineColor(hex, dark) {
    if (!dark) return hex;
    return DARK_LINE_MAP[hex] || hex;
  }

  /* ---------- 归一化原语 ---------- */

  // 有限数或 null：NaN/Infinity/undefined/'' 一律 null（与 lab_result.json_safe 同语义）
  function num(v) {
    var n = Number(v);
    return (v == null || v === "" || !isFinite(n)) ? null : n;
  }

  // 日期升序去重：保留每个日期的**最后**一次出现（后写覆盖，与 DB upsert 语义一致），
  // 返回 [{date, index}] 按 date 升序。LWC 要求 setData 的数据严格升序。
  function orderedDates(dates) {
    var byDate = {};
    var order = [];
    (dates || []).forEach(function (d, i) {
      var key = String(d == null ? "" : d);
      if (!key) return;
      if (byDate[key] == null) {
        byDate[key] = { date: key, index: i };
        order.push(key);
      } else {
        byDate[key].index = i;  // 重复日期：后出现者覆盖
      }
    });
    order.sort();
    return order.map(function (k) { return byDate[k]; });
  }

  // 按有序日期取某序列的值；非有限 → {time} 空点（LWC 不接受 null）
  function points(values, entries) {
    return entries.map(function (e) {
      var v = num((values || [])[e.index]);
      return v == null ? { time: e.date } : { time: e.date, value: v };
    });
  }

  /* ---------- 序列构造 ---------- */

  // K 线：ohlc 合同序 [open, close, low, high] → LWC {open, high, low, close}
  function toCandles(kline) {
    var entries = orderedDates((kline || {}).dates);
    var ohlc = (kline || {}).ohlc || [];
    return entries.map(function (e) {
      var k = ohlc[e.index];
      var o = k ? num(k[0]) : null;
      var c = k ? num(k[1]) : null;
      var l = k ? num(k[2]) : null;
      var h = k ? num(k[3]) : null;
      if (o == null || c == null || l == null || h == null) return { time: e.date };
      return { time: e.date, open: o, high: h, low: l, close: c };
    });
  }

  // 成交量：histogram，单色不随涨跌分支（对齐原 ECharts 的 #B7A6E8 口径）
  function toVolume(kline) {
    return points((kline || {}).vols, orderedDates((kline || {}).dates));
  }

  // 均线 / 因子线：line series 数据
  function toLineSeries(values, dates) {
    return points(values, orderedDates(dates));
  }

  // MACD 柱等 histogram：逐点 color，正红负绿（零值按正柱）
  function toHistogram(values, dates) {
    var t = theme(false);
    return points(values, orderedDates(dates)).map(function (p) {
      if (p.value == null) return p;
      return { time: p.time, value: p.value, color: p.value >= 0 ? t.histUp : t.histDown };
    });
  }

  // 买卖点 marker：红买绿卖；买入 belowBar、卖出 aboveBar；按日期升序
  function toMarkers(orders, t) {
    var th = t || theme(false);
    var seen = {};
    var out = [];
    (orders || []).forEach(function (o) {
      var d = String((o || {}).trade_date == null ? "" : o.trade_date);
      if (!d || seen[d]) return;  // 同一根 K 线只保留第一个 marker
      seen[d] = true;
      var buy = (o || {}).side === "buy";
      out.push({
        time: d,
        position: buy ? "belowBar" : "aboveBar",
        shape: buy ? "arrowUp" : "arrowDown",
        color: buy ? th.up : th.down,
        size: 2,
        text: "",
      });
    });
    out.sort(function (a, b) { return a.time < b.time ? -1 : (a.time > b.time ? 1 : 0); });
    return out;
  }

  // 阈值线：挂该 pane 第一条 line series（无 line 时由调用方挂蜡烛 series）
  function thresholdLines(pane) {
    var th = (pane && pane.thresholds) || [];
    return th.map(function (v) {
      var n = num(v);
      return n == null ? null : {
        price: n,
        color: theme(false).threshold,
        lineWidth: 1,
        lineStyle: 2,          // dashed
        axisLabelVisible: true,
        title: n.toFixed(2),
      };
    }).filter(function (x) { return x != null; });
  }

  // pane 是否有 line series（决定阈值线挂哪条）
  function firstLineSeries(pane) {
    var s = ((pane || {}).series || []).filter(function (x) { return x.type !== "bar"; });
    return s.length ? s[0] : null;
  }

  /* ---------- 高度（与 replay.js::klineHeightForPanes 同源） ---------- */
  function klineHeight(paneCount) {
    var n = Math.max(0, Math.floor(Number(paneCount) || 0));
    return n > 0 ? 420 + n * 160 : 460;
  }

  window.QRELwcAdapter = {
    THEME: THEME_LIGHT,
    THEME_DARK: THEME_DARK,
    theme: theme,
    lineColor: lineColor,
    num: num,
    orderedDates: orderedDates,
    toCandles: toCandles,
    toVolume: toVolume,
    toLineSeries: toLineSeries,
    toHistogram: toHistogram,
    toMarkers: toMarkers,
    thresholdLines: thresholdLines,
    firstLineSeries: firstLineSeries,
    klineHeight: klineHeight,
  };
})();
