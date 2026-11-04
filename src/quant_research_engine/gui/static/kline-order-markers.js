/* QRE-KLINE-ORDER-MARKERS — 个股 K 线买卖点「圆环 + 文字」标记（T5）
 *
 * 设计口径（2026-11-04 用户定稿）：
 *   · 买点：红色圆环 +「买」字，标在 K 线下方；卖点：绿色圆环 +「卖」字，标在上方；
 *   · 圆环尺寸 28px（聚合组 34px），明显大于原 10px 三角，不遮挡蜡烛主体；
 *   · 信号密集时按当前 dataZoom 可见窗口分桶聚合；悬停由 valueFormatter 回查
 *     该圆环的单行摘要（单笔含数量/价/金额/费用拆分，聚合组含笔数/合计/日期范围）；
 *   · 颜色沿用 A 股红涨绿跌（#d43030 / #1a9e4b），与现有行情配色同源。
 *
 * 与页面解耦：本模块只接收 chart/series/data/dates 与重绘画线层的回调，
 * 不读写页面全局状态；缩放后由页面把聚合结果同步回 baseSeries。
 */
(function () {
  "use strict";

  function f2(v) {
    return (v == null || v === "") ? "—" : Number(v).toFixed(2);
  }

  function qty(v) {
    var n = Number(v);
    return isFinite(n) && n % 1 === 0 ? n.toFixed(0) : f2(n);
  }

  function sum(items, key) {
    return items.reduce(function (a, o) { return a + (Number(o[key]) || 0); }, 0);
  }

  // 轴触发（trigger:'axis'）会忽略 series 级 tooltip.formatter，只认 valueFormatter
  // （回调签名 valueFormatter(value, dataIndex)，且返回值按纯文本转义）。
  // 因此这里给每个圆环预生成单行摘要，悬停时由 dataIndex 回查。
  // 摘要不带「买入/卖出」前缀——轴 tooltip 已用 series 名单独占一行。
  function summaryOf(items) {
    if (items.length > 1) {
      var days = items.map(function (o) { return o.trade_date; }).sort();
      return "×" + items.length + " 笔 · 合计 " + qty(sum(items, "quantity")) +
        " 股 · 金额 " + f2(sum(items, "notional")) + " 元 · 费用 " + f2(sum(items, "cost")) +
        " 元 · " + days[0] + " ~ " + days[days.length - 1];
    }
    var o = items[0];
    return qty(o.quantity) + " 股 @ " + f2(o.price) + " 元 · 金额 " +
      f2(o.notional) + " 元 · 费用 " + f2(o.cost) + " 元（佣金 " + f2(o.commission) +
      " / 印花税 " + f2(o.stamp_tax) + " / 过户费 " + f2(o.transfer_fee) + "）";
  }

  function attach(chart, series, d, dates, redraw) {
    if (!chart || !series || !dates || !dates.length) return null;
    var idx = {}, low = {}, high = {};
    dates.forEach(function (dt, i) { idx[dt] = i; });
    ((d.kline || {}).ohlc || []).forEach(function (k, i) {
      low[dates[i]] = k[2];
      high[dates[i]] = k[3];
    });
    var markers = {};
    function seriesOf(side, color) {
      return {
        name: side === "buy" ? "买入" : "卖出", type: "scatter", xAxisIndex: 0, yAxisIndex: 0,
        data: [], symbol: "circle", z: 6,
        symbolSize: function (v, p) { return p.data.count > 1 ? 34 : 28; },
        symbolOffset: side === "buy" ? [0, 18] : [0, -18],
        itemStyle: { color: "transparent", borderColor: color, borderWidth: 2 },
        label: {
          show: true, position: "inside", color: color, fontSize: 12, fontWeight: 600,
          formatter: function (p) { return p.data.text; },
        },
        tooltip: {
          valueFormatter: function (v, i) {
            var d = markers[side].data[i];
            return d && d.summary ? d.summary : f2(v);
          },
        },
      };
    }
    markers.buy = seriesOf("buy", "#d43030");
    markers.sell = seriesOf("sell", "#1a9e4b");
    series.push(markers.buy, markers.sell);

    var refresh = function () {
      var opt = chart.getOption ? (chart.getOption() || {}) : {};
      var dz = (opt.dataZoom || [])[0];
      var a = 0, b = dates.length - 1;
      if (dz) {
        a = dz.startValue != null ? Number(dz.startValue)
          : (dz.start != null ? Math.floor(dates.length * dz.start / 100) : a);
        b = dz.endValue != null ? Number(dz.endValue)
          : (dz.end != null ? Math.ceil(dates.length * dz.end / 100) - 1 : b);
      }
      a = Math.max(0, Math.min(dates.length - 1, a));
      b = Math.max(a, Math.min(dates.length - 1, b));
      // 每个圆环约占 46px；桶宽随可见根数变化，缩得越近桶越窄，最终一单一标。
      var width = chart.getWidth ? chart.getWidth() : 900;
      var bucket = Math.max(1, Math.ceil((b - a + 1) / Math.max(4, Math.floor((width - 80) / 46))));
      ["buy", "sell"].forEach(function (side) {
        var slots = {};
        (d.orders || []).forEach(function (o) {
          if ((o.side === "buy") !== (side === "buy")) return;
          var i = idx[o.trade_date];
          if (i == null || i < a || i > b) return;
          var slot = Math.floor((i - a) / bucket);
          (slots[slot] = slots[slot] || { i: i, items: [] }).items.push(o);
        });
        markers[side].data = Object.keys(slots).map(function (k) {
          var g = slots[k], dt = dates[g.i], items = g.items;
          return {
            value: [dt, side === "buy" ? low[dt] : high[dt]],
            count: items.length,
            text: (side === "buy" ? "买" : "卖") + (items.length > 1 ? items.length : ""),
            summary: summaryOf(items),
          };
        });
      });
    };

    refresh();
    chart.on("dataZoom", function () {
      refresh();
      if (typeof redraw === "function") redraw();
    });
    return markers;
  }

  window.QREKlineOrderMarkers = { attach: attach };
})();
