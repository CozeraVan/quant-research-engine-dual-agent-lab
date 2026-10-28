/* ============================================================================
   QRE-EQUITY-CHART —— 收益曲线（策略 / 各基准 / 买入持有 / 回撤）的唯一构造来源
   ----------------------------------------------------------------------------
   为什么单独一个文件：job.html 与 symbol.html 原先各自内联一份 ECharts 组件，
   前者只有「策略 + 单基准 + 回撤」，后者是「策略净值(元) + 买入持有% + 各基准%
   + 双 y 轴」，同一张图两套口径、配色与网格参数，且 symbol 的基准曲线全部同色。
   现在曲线数据（归一化收益率、回撤）与图表选项都收敛到这里，模板只负责把结果
   塞进 DOM / 交给 QREReplay。纯函数，不碰 DOM，便于 Node 单测。

   口径（与 risk/performance.py 及页面原有实现一致）：
     · toPct(values)     以首个非 null 有限值为基 → (v/base-1)*100，基为 0/非有限
                         时全为 null（不制造 Infinity），null 原位保留。
     · drawdownPct(vals) 按净值历史最高点算 v/peak-1（≤0），非正值/缺失为 null。
     · benchPct(closes)  等同 toPct（基准指数用收盘价归一化）。

   配色（12 号 UI 规范：策略紫，禁蓝/橙）：
     策略/买入持有 #6750A4；回撤 #d43030；各基准沿用书里的固定色。
   ============================================================================ */
(function (root) {
  'use strict';

  var STRATEGY_COLOR = '#6750A4';
  var DD_COLOR = '#d43030';

  // 书里的基准固定色；未列出的 code 按 PALETTE 顺序循环取色
  var BENCH_COLORS = {
    '000001.SH': '#B7A6E8',  // 上证指数
    '000300.SH': '#2A9D8F',  // 沪深300
    '399001.SZ': '#E8A33D',  // 深证成指
    '000905.SH': '#4A3A78',  // 中证500
    '399006.SZ': '#9A93A6',  // 创业板指
    '000852.SH': '#6750A4'   // 中证1000
  };
  var PALETTE = ['#B7A6E8', '#2A9D8F', '#E8A33D', '#4A3A78', '#9A93A6', '#6750A4'];

  function isNum(x) {
    return typeof x === 'number' && isFinite(x);
  }

  function benchColor(code, idx) {
    if (code && BENCH_COLORS[code]) return BENCH_COLORS[code];
    var i = isNum(idx) ? idx : 0;
    return PALETTE[((i % PALETTE.length) + PALETTE.length) % PALETTE.length];
  }

  // 净值/价格序列 → 以首个有效值为 0 基点的累计收益率%
  function toPct(values) {
    var arr = Array.isArray(values) ? values : [];
    var base = null;
    for (var i = 0; i < arr.length; i++) {
      if (isNum(arr[i])) { base = arr[i]; break; }
    }
    if (!isNum(base) || base === 0) return arr.map(function () { return null; });
    return arr.map(function (v) {
      return isNum(v) ? (v / base - 1) * 100 : null;
    });
  }

  function benchPct(closes) {
    return toPct(closes);
  }

  // 回撤：相对历史最高点的跌幅（%），横轴序列里缺失值不参与也不更新峰值
  function drawdownPct(equity) {
    var arr = Array.isArray(equity) ? equity : [];
    var peak = null;
    return arr.map(function (v) {
      if (!isNum(v)) return null;
      if (peak === null || v > peak) peak = v;
      if (v <= 0 || !isNum(peak) || peak === 0) return null;
      return (v / peak - 1) * 100;
    });
  }

  function hasValue(arr) {
    return Array.isArray(arr) && arr.some(function (v) { return isNum(v); });
  }

  // benches 允许两种形态：对象 map（code → {name, closes|pct|values}）或数组
  // [{code, name, pct|values|closes}]；缺 name 时用 benchmarks 元数据补。
  function benchList(benches, benchmarks) {
    var out = [];
    var meta = benchmarks || {};
    function push(code, b, i) {
      b = b || {};
      var name = b.name || (meta[code] && meta[code].name) || code || ('基准' + (i + 1));
      var pct = Array.isArray(b.pct) ? b.pct
        : Array.isArray(b.values) ? toPct(b.values)
        : Array.isArray(b.closes) ? toPct(b.closes)
        : null;
      out.push({ code: code, name: name, pct: pct, color: benchColor(code, i) });
    }
    if (Array.isArray(benches)) {
      benches.forEach(function (b, i) { if (b) push(b.code || b.ts_code || '', b, i); });
    } else if (benches && typeof benches === 'object') {
      Object.keys(benches).forEach(function (code, i) { push(code, benches[code], i); });
    }
    return out;
  }

  // 图例开关：openCodes 为当前打开的基准 code；未指定时默认只留上证指数
  function legendSelectedFor(benches, openCodes) {
    var list = Array.isArray(benches) ? benches : benchList(benches || {}, null);
    var open;
    if (Array.isArray(openCodes)) {
      open = openCodes;
    } else {
      open = [];
      for (var i = 0; i < list.length; i++) {
        if (list[i].code === '000001.SH') { open = [list[i].code]; break; }
      }
      if (!open.length && list.length) open = [list[0].code];
    }
    var sel = {};
    list.forEach(function (b) {
      sel[b.name] = open.indexOf(b.code) >= 0;
    });
    return sel;
  }

  function gridsFor(hasDD) {
    return hasDD
      ? [{ left: 68, right: 20, top: 30, height: '52%' },
         { left: 68, right: 20, top: '70%', height: '16%' }]
      : [{ left: 68, right: 20, top: 30, height: '72%' }];
  }

  function xAxes(dates, hasDD) {
    var head = { type: 'category', data: dates || [], gridIndex: 0 };
    if (!hasDD) return [head];
    head.axisLabel = { show: false };
    return [head, { type: 'category', data: dates || [], gridIndex: 1 }];
  }

  function yAxes(hasDD) {
    var out = [{ type: 'value', gridIndex: 0, name: '累计收益率%',
                 axisLabel: { formatter: '{value}%' } }];
    if (hasDD) out.push({ type: 'value', gridIndex: 1, name: '回撤%', max: 0,
                          axisLabel: { formatter: '{value}%' } });
    return out;
  }

  function dataZoom(hasDD) {
    var idx = hasDD ? [0, 1] : [0];
    return [{ type: 'inside', xAxisIndex: idx },
            { type: 'slider', xAxisIndex: idx, bottom: 6, height: 22 }];
  }

  // 静态图：job（策略+各基准+回撤）与 symbol（再加买入持有）共用
  function option(o) {
    o = o || {};
    var benches = benchList(o.benches, o.benchmarks);
    var holdPct = Array.isArray(o.holdPct) ? o.holdPct : null;
    var dd = Array.isArray(o.drawdownPct) ? o.drawdownPct : null;
    var hasHold = hasValue(holdPct);
    var hasDD = hasValue(dd);
    var series = [{
      name: '策略', id: 'strategy', type: 'line', data: o.strategyPct || [],
      showSymbol: false, color: STRATEGY_COLOR, lineStyle: { width: 2 }
    }];
    benches.forEach(function (b) {
      if (!b.pct || !hasValue(b.pct)) return;
      series.push({
        name: b.name, id: 'bench:' + b.code, type: 'line', data: b.pct,
        showSymbol: false, color: b.color,
        lineStyle: { width: 1.2, type: 'dashed' }
      });
    });
    if (hasHold) series.push({
      name: '买入持有', id: 'hold', type: 'line', data: holdPct,
      showSymbol: false, color: STRATEGY_COLOR,
      lineStyle: { width: 1.2, type: 'dashed' }
    });
    if (hasDD) series.push({
      name: '回撤', id: 'dd', type: 'line', xAxisIndex: 1, yAxisIndex: 1, data: dd,
      showSymbol: false, areaStyle: { opacity: 0.3 },
      color: DD_COLOR, lineStyle: { width: 1 }
    });
    var legendData = series.map(function (s) { return s.name; });
    return {
      animation: false,
      tooltip: {
        trigger: 'axis', axisPointer: { link: [{ xAxisIndex: 'all' }] },
        valueFormatter: function (v) { return isNum(v) ? v.toFixed(2) + '%' : '—'; }
      },
      legend: {
        top: 0, data: legendData,
        selected: o.legendSelected || legendSelectedFor(benches, null)
      },
      grid: gridsFor(hasDD),
      xAxis: xAxes(o.dates, hasDD),
      yAxis: yAxes(hasDD),
      dataZoom: dataZoom(hasDD),
      series: series
    };
  }

  // 重播：QREReplay.attach 的 series/grids/yAxes 描述符（与静态图同色同网格）
  function replaySpec(o) {
    o = o || {};
    var benches = benchList(o.benches, o.benchmarks);
    var dd = Array.isArray(o.drawdownPct) ? o.drawdownPct : null;
    var hasDD = hasValue(dd);
    var series = [{
      name: '策略', id: 'strategy', color: STRATEGY_COLOR,
      data: o.strategyPct || [], raw: o.strategyRaw,
      grid: 0, mark: true, width: 2, zeroBase: true
    }];
    benches.forEach(function (b) {
      if (!b.pct || !hasValue(b.pct)) return;
      series.push({
        name: b.name, id: 'bench:' + b.code, color: b.color,
        dashed: true, data: b.pct, grid: 0, zeroBase: true
      });
    });
    if (hasDD) series.push({
      name: '回撤', id: 'dd', color: DD_COLOR, data: dd,
      grid: 1, area: true, width: 1
    });
    return {
      series: series,
      grids: gridsFor(hasDD),
      yAxes: yAxes(hasDD).map(function (y) {
        return y.max != null ? { name: y.name, max: y.max } : { name: y.name };
      }),
      hasDD: hasDD,
      legendSelected: legendSelectedFor(benches, o.openCodes)
    };
  }

  root.QREEquityChart = {
    BENCH_COLORS: BENCH_COLORS,
    STRATEGY_COLOR: STRATEGY_COLOR,
    DD_COLOR: DD_COLOR,
    toPct: toPct,
    drawdownPct: drawdownPct,
    benchPct: benchPct,
    benchColor: benchColor,
    legendSelectedFor: legendSelectedFor,
    option: option,
    replaySpec: replaySpec
  };
})(typeof window !== 'undefined' ? window : this);