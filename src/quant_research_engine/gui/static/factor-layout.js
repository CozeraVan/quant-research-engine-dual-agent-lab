/* QREFactorLayout 因子图表 TV 风格分组布局（CR-2026-10-20）
 * SaaS 个股页（symbol.html 静态 + K 线重播）与 8081 lab 个股页（lab_symbol.html）
 * 共用同一份分组逻辑，防两处漂移。
 *
 * plan(factors, states) → { chips, overlays, panes, paneCount }
 *   factors: [{name, col?, values, thresholds?}]（col 为真实因子列名，旧产物缺省时按 name 启发式）
 *   states:  {chipKey: 'overlay'|'pane'|'hidden'}（缺省走默认态；非法值回落默认态）
 *   chips:    [{key, label, kind, state, states}] 供 chip 行渲染与三态循环
 *   overlays: [{f, name, color}] 叠加到 K 线主图（grid0，共用价格轴）
 *   panes:    [{key, name, thresholds, series:[{name,type:'line'|'bar',values,color,hist?}]}]
 *
 * 分组规则（display 元数据接口预留：panel.display 存在时优先，本期纯启发式）：
 *   - 表类别含 overlap（pandas-ta 口径）或 ema/ma/sma/kama/boll 轨道系等 → overlay 主图；
 *   - MACD/PPO/PVO 三元组（base/bases/baseh 同参数后缀，或 dif/dea/hist 别名）→
 *     合并单面板（至少 DIF+DEA 才合并；HIST 可选，柱正红负绿与 K 线涨跌同色）；
 *   - KDJ/STOCH/STOCHRSI/AROON/VORTEX 及通用"s 信号线对"（tsi/tsis 等）→ 多线单面板；
 *   - 其余 → 每因子一个独立面板（保留 thresholds markLine）。
 * 状态机：overlay 类 chip 三态循环 overlay→pane→hidden；MACD/普通面板 chip
 * 只循环 pane→hidden（量纲与价格不同，叠加无意义）。
 */
(function () {
  "use strict";

  // 均线/轨道类：列名多为 sma_5、ema_12、kama_10_2_30、bbl_20_2_0_2_0 等带下划线参数
  var OVERLAY_RE = /^(?:ema|ma|sma|wma|dema|tema|hma|kama|alma|rma|trima|jma|vidya|swma|fwma|pwma|sinwma|zl_ema|zlma)_?\d*$|^(?:bbl|bbm|bbu|dcl|dcm|dcu|kcl|kcb|kcu|kcbe|kcle|kcue|accbl|accbm|accbu|psarl|psars|supert)_|^(?:boll|bb)_(?:upper|mid|lower)|^boll|^(?:hl2|hlc3|ohlc4|wcp|vwap_d|midpoint_?\d*|midprice_?\d*)$/i;
  var COLORS = {
    overlay: ["#E8A33D", "#2A9D8F", "#6750A4"],  // 均线循环色：橙/青/主紫
    pane: "#6750A4",                              // 因子副图线（同 UI 规范既有口径）
    multi: ["#6750A4", "#E8A33D", "#2A9D8F"],     // 多线面板（KDJ/STOCH 等）循环色
    dif: "#6750A4", dea: "#E8A33D",
    histUp: "#C93A3A", histDown: "#1E8E5A",       // 与 K 线涨跌同色
  };

  function fkey(f) { return f.col || f.name || ""; }

  function isOverlay(f) {
    // 表类别是最稳信号：pandas-ta 口径 overlap 表即主图叠加指标
    var tbl = String(f.table || "").toLowerCase();
    if (tbl.indexOf("overlap") >= 0) return true;
    return OVERLAY_RE.test(f.col || "") || OVERLAY_RE.test(f.name || "");
  }

  // 多线面板家族识别：返回 {label, roles:[{f,idx,tag}]} 或 null。
  // 覆盖：MACD/PPO/PVO 三元组(带柱)、KDJ、STOCH/STOCHRSI、AROON、VORTEX，
  // 以及通用"s 信号线对"（tsi/tsis、rvgi/rvgis、fisher/fisherts 等）。
  function familyOf(f, allKeys) {
    var keys = [f.col || "", f.name || ""];
    for (var k = 0; k < keys.length; k++) {
      var low = String(keys[k]).toLowerCase(), m;
      // MACD 类别名：macd_dif / macd_dea / macd_signal / macd_hist / macd_histogram
      //（旧产物/部分策略会直接使用这些名字且无 display，必须与 macd/macds/macdh 同组合流）
      m = /^(macd|ppo|pvo)[\s_-](dif|dea|signal|hist|histogram)([\s_-].*)?$/.exec(low);
      if (m) {
        var roleAlias = m[2] === "dea" || m[2] === "signal" ? "dea"
          : (m[2] === "hist" || m[2] === "histogram" ? "hist" : "dif");
        var suffixAlias = m[3] ? String(m[3]).replace(/^[\s_-]+/, "") : "";
        return { fam: "triple", base: m[1], role: roleAlias, suffix: suffixAlias, label: m[1].toUpperCase() };
      }
      // MACD 类：macd/ppo/pvo + 可选 s/h + 参数后缀
      m = /^(macd|ppo|pvo)(s|h)?_(.+)$/.exec(low);
      if (m) return { fam: "triple", base: m[1], role: m[2] === "s" ? "dea" : (m[2] === "h" ? "hist" : "dif"), suffix: m[3], label: m[1].toUpperCase() };
      if (low === "macd" || low === "dif") return { fam: "triple", base: "macd", role: "dif", suffix: "", label: "MACD" };
      if (low === "macds" || low === "macd_signal" || low === "dea") return { fam: "triple", base: "macd", role: "dea", suffix: "", label: "MACD" };
      if (low === "macdh" || low === "hist" || low === "macd柱") return { fam: "triple", base: "macd", role: "hist", suffix: "", label: "MACD" };
      // KDJ：k_9_3 / d_9_3 / j_9_3
      m = /^([kdj])_(\d+(?:_\d+)*)$/.exec(low);
      if (m) return { fam: "lines", gkey: "kdj_" + m[2], role: m[1].toUpperCase(), label: "KDJ" };
      // STOCH / STOCHRSI：stochk_14_3_3 / stochrsid_14_14_3_3（h 为柱）
      m = /^stoch(rsi)?([kdh])_(.+)$/.exec(low);
      if (m) return { fam: "lines", gkey: "stoch" + (m[1] || "") + "_" + m[3], role: m[2] === "h" ? "hist" : m[2].toUpperCase(), label: m[1] ? "STOCHRSI" : "STOCH", histRole: m[2] === "h" };
      // AROON：aroond/aroond 同后缀（osc 保持独立面板）
      m = /^aroon([du])_(.+)$/.exec(low);
      if (m) return { fam: "lines", gkey: "aroon_" + m[2], role: m[1] === "u" ? "UP" : "DOWN", label: "AROON" };
      // VORTEX：vtxp/vtxm 同后缀
      m = /^vtx([pm])_(.+)$/.exec(low);
      if (m) return { fam: "lines", gkey: "vortex_" + m[2], role: m[1] === "p" ? "VI+" : "VI-", label: "VORTEX" };
      // 通用 s 信号线对：Xs_<P> 且 X_<P> 存在（tsi/tsis、rvgi/rvgis、fisher/fisherts…）
      m = /^([a-z]+?)s_(\d.*)$/.exec(low);
      if (m && m[1] !== "mac" && allKeys[m[1] + "_" + m[2]]) {
        return { fam: "lines", gkey: m[1] + "_" + m[2], role: "SIGNAL", label: m[1].toUpperCase(), suffix: m[2], base: m[1] };
      }
      m = /^([a-z]+)_(\d.*)$/.exec(low);
      if (m && allKeys[m[1] + "s_" + m[2]] && !OVERLAY_RE.test(low)) {
        return { fam: "lines", gkey: m[1] + "_" + m[2], role: "MAIN", label: m[1].toUpperCase(), suffix: m[2], base: m[1] };
      }
    }
    return null;
  }

  // 面板标签：合同 panel_id 前缀 → 人读组名（pane: 前缀为独立面板，用因子名）
  var PANEL_LABELS = {macd: "MACD", ppo: "PPO", pvo: "PVO", kdj: "KDJ", stoch: "STOCH",
    stochrsi: "STOCHRSI", aroon: "AROON", vortex: "VORTEX", tsi: "TSI", rvgi: "RVGI",
    fisher: "FISHER"};
  function panelLabel(panelId, f) {
    var prefix = String(panelId || "").split(":")[0];
    if (prefix === "pane") return f.name || fkey(f) || "";
    return PANEL_LABELS[prefix] || prefix.toUpperCase();
  }

  // QRE-FACTOR-DISPLAY-CONTRACT：plan 只消费注册表 display 合同；
  // 无 display 的旧数据走下方启发式回退（与 2026-10-20 版行为一致），
  // 显式属性永不被启发式覆盖。
  //
  // 第三参 paneOrder（CR-2026-10-28 指标设置与面板管理）：可选的副图排序键数组，
  // 元素为 group key。语义：
  //   - 缺省/空数组/null/非数组 → 完全按分组顺序（与旧行为逐字节一致）；
  //   - 列出的键按给定顺序前置，未列出的键保持相对顺序置后；
  //   - 未知键、非字符串、重复键一律忽略（去重），不得丢面板或重复；
  //   - 只影响 panes 顺序，不动 overlays / chips / paneCount。
  function plan(factors, states, paneOrder) {
    factors = factors || [];
    states = states || {};

    // 预索引全部因子键（旧启发式的"s 信号线对"探测用）
    var allKeys = {};
    factors.forEach(function (f) {
      if (f.col) allKeys[String(f.col).toLowerCase()] = true;
      if (f.name) allKeys[String(f.name).toLowerCase()] = true;
    });

    // 1) 归组：display 合同优先，旧数据才启发式
    var groups = [];   // {key, kind, label, order, members:[{f, role, seriesType, color, precision, order}]}
    var byKey = {};
    factors.forEach(function (f, i) {
      var disp = (f.display && f.display.chart_type) ? f.display : null;
      var kind, key, label, role, st, color, precision, order;
      if (disp) {
        kind = disp.chart_type === "overlay" ? "overlay" : "pane";
        if (kind === "overlay") {
          key = fkey(f) || ("f" + i);
          label = f.name || key;
        } else {
          key = String(disp.panel_id);
          label = panelLabel(disp.panel_id, f);
        }
        role = disp.role || "line";
        st = disp.series_type === "bar" ? "bar" : "line";
        color = disp.color || null;
        precision = typeof disp.precision === "number" ? disp.precision : null;
        order = typeof disp.render_order === "number" ? disp.render_order : 0;
      } else {
        // ---- 旧数据启发式回退（2026-10-20 原逻辑，逐行保留） ----
        if (isOverlay(f)) {
          kind = "overlay";
          key = fkey(f) || ("f" + i);
          label = f.name;
          role = "line"; st = "line"; color = null; precision = null; order = i;
        } else {
          var r = familyOf(f, allKeys);
          if (!r) {
            kind = "pane";
            key = fkey(f) || ("f" + i);
            label = f.name;
            role = "line"; st = "line"; color = null; precision = null; order = i;
          } else {
            kind = "pane";
            var bkey = r.fam === "triple" ? (r.base + "_" + r.suffix) : r.gkey;
            key = bkey;
            label = r.label;
            role = r.fam === "triple"
              ? (r.role === "dif" ? "main" : (r.role === "hist" ? "hist" : "signal"))
              : (r.role || "line");
            st = (r.fam === "triple" && r.role === "hist") ? "bar" : "line";
            color = null; precision = null; order = i;
          }
        }
      }
      var g = byKey[key];
      if (!g) {
        g = {key: key, kind: kind, label: label, order: order, members: []};
        byKey[key] = g;
        groups.push(g);
      }
      g.members.push({f: f, role: role, seriesType: st, color: color,
                      precision: precision, order: order});
    });
    groups.sort(function (a, b) {
      return (a.order - b.order) || (a.key < b.key ? -1 : (a.key > b.key ? 1 : 0));
    });

    // 2) 装配：chips / overlays / panes（overlay 组可被 chip 切到 pane）
    var chips = [], overlays = [], panes = [], oi = 0, mi = 0;
    groups.forEach(function (g) {
      var allowed = g.kind === "overlay" ? ["overlay", "pane", "hidden"] : ["pane", "hidden"];
      var st = allowed.indexOf(states[g.key]) >= 0 ? states[g.key]
        : (g.kind === "overlay" ? "overlay" : "pane");
      chips.push({key: g.key, label: g.label, kind: g.kind, state: st, states: allowed});
      if (st === "hidden") return;
      var members = g.members.slice().sort(function (a, b) { return a.order - b.order; });
      if (st === "overlay") {
        members.forEach(function (m) {
          overlays.push({f: m.f, name: m.f.name,
            color: m.color || COLORS.overlay[oi++ % COLORS.overlay.length]});
        });
        return;
      }
      // pane 渲染（含 overlay 组被切到 pane 的情形）
      var thresholds = [];
      var series = members.map(function (m) {
        if (m.f.thresholds) thresholds = thresholds.concat(m.f.thresholds);
        var sc = {
          name: m.f.name, type: m.seriesType === "bar" ? "bar" : "line",
          values: m.f.values,
          color: m.color || (m.seriesType === "bar" ? null : COLORS.pane),
        };
        if (m.seriesType === "bar") sc.hist = true;
        if (m.precision != null) sc.precision = m.precision;
        return sc;
      });
      // pane 级精度：display 合同给的首个非空 precision（QRE-PRICE-SCALE T2 副图轴用）
      var panePrecision = null;
      members.forEach(function (m) {
        if (panePrecision == null && m.precision != null) panePrecision = m.precision;
      });
      var pane = {key: g.key, name: g.label, thresholds: thresholds, series: series};
      if (panePrecision != null) pane.precision = panePrecision;
      panes.push(pane);
    });
    // paneOrder：副图排序（CR-2026-10-28）。缺省/非法输入保持分组顺序；
    // 列出的键前置（去重、忽略未知/非字符串），未列出的键保持相对顺序置后。
    if (Object.prototype.toString.call(paneOrder) === "[object Array]" && paneOrder.length) {
      var rank = {};
      paneOrder.forEach(function (k, i) {
        if (typeof k !== "string" || !k || rank[k] != null) return;
        rank[k] = i;
      });
      panes.sort(function (a, b) {
        var ra = rank[a.key], rb = rank[b.key];
        if (ra == null && rb == null) return 0;              // 都未列出：稳定保持原序
        if (ra == null) return 1;                            // 未列出置后
        if (rb == null) return -1;
        return ra - rb;
      });
    }
    return {chips: chips, overlays: overlays, panes: panes, paneCount: panes.length};
  }

  // ────────────────────────────────────────────────────────────────────────
  // QRE-KLINE-PANE-OPTION（T1，2026-10-29）：因子 pane → ECharts option 的唯一出口。
  //
  // 历史：symbol.html::renderKline、symbol.html::mountKlineReplay、
  // game.html::renderChart 三处各写一份 `2 + i` / `paneIndex + 2`，索引规则三倍
  // 维护；ECharts 的 yAxisIndex 是**全局 yAxis 数组下标**（不是 grid 内局部下标），
  // 一旦某个 pane 多插轴整体就错位——用户报的"MACD 的 dea/dif/hist 各自坐标系"
  // 正是这类错位的表现（TV_ROUND2 §3 判据证实本次是视觉错觉，但机制成立）。
  //
  // 硬规则：业务页不许再手写 pane 索引，一律走 panesToOption / paneSeries /
  // paneYAxes；索引用由本文件生成，并自带不变式校验（炸在开发期，不 silent 错位）。
  // ────────────────────────────────────────────────────────────────────────

  /** pane 布局（grid 位置/高度）。symbol.html::klineGridSpec 只是签名适配壳，
      真正实现只此一份（R3-1 收敛，原先两份逐行复制会漂移）。 */
  function paneGrids(paneCount, opts) {
    opts = opts || {};
    var showVol = opts.showVol !== false;
    var showFct = opts.showFct !== false;
    var n = paneCount || 0;
    var fOn = !!showFct && n > 0;
    var hide = { left: 16, right: 56, top: 0, height: 1 };
    var grids = [{ left: 16, right: 56, top: 30,
      height: fOn ? (showVol ? '42%' : '50%') : (showVol ? '58%' : '78%') }];
    if (!showVol) grids.push(Object.assign({}, hide));
    else if (fOn) grids.push({ left: 16, right: 56, top: '53%', height: '10%' });
    else grids.push({ left: 16, right: 56, top: '74%', height: '14%' });
    var fTop = (fOn && showVol) ? 66 : 58;
    var fBottom = 93;
    var step = n ? (fBottom - fTop) / n : 0;
    // R3-1（TV_ROUND3 §2）：恰好 1 个因子 pane 时高度 20.25% → 25%。
    // 原 20.25% 偏矮，MACD 的 HIST 自身跨度只占 pane 高 ~44%、DIF/DEA 占满 100%，
    // 矮面板把这点量程差放大成"三根线各用一把尺"的错觉（用户原始投诉）。
    // 多 pane 不动（step*0.75），避免互相挤压。
    var paneH = (n === 1) ? 25 : (step * 0.75);
    for (var i = 0; i < n; i++) {
      grids.push(fOn
        ? { left: 16, right: 56, top: (fTop + i * step) + '%', height: paneH + '%' }
        : Object.assign({}, hide));
    }
    return grids;
  }

  /** 时间轴只挂最后一个可见格（面板全关时上移到量/主图）。 */
  function axisLabelIndex(paneCount, opts) {
    opts = opts || {};
    var showVol = opts.showVol !== false;
    var showFct = opts.showFct !== false;
    var n = paneCount || 0;
    if (showFct && n > 0) return 1 + n;
    if (showVol) return 1;
    return 0;
  }

  /** 校验 pane 索引不变式：yAxis.length === grid.length 且逐 pane 一一对应。 */
  function _assertPaneInvariant(grid, yAxis, paneBase, panes) {
    var n = (panes || []).length;
    if (yAxis.length !== grid.length) {
      throw new Error('QRE-KLINE-PANE-OPTION: yAxis.length(' + yAxis.length
        + ') !== grid.length(' + grid.length + ')——pane 索引错位');
    }
    for (var i = 0; i < n; i++) {
      var ax = yAxis[paneBase + i];
      if (!ax || ax.gridIndex !== paneBase + i) {
        throw new Error('QRE-KLINE-PANE-OPTION: pane ' + i + ' 的 yAxis.gridIndex 应为 '
          + (paneBase + i) + '，实际 ' + (ax && ax.gridIndex));
      }
    }
  }

  /**
   * 因子 pane 的 yAxis 声明（索引内部生成）。
   * spec.paneAxisLabel(pane, i) → axisLabel 对象（QRE-PRICE-SCALE T2：副图轴同样
   * 走固定精度 + 恒定轴宽，修复"同一根轴 3 与 0.00 混排"）；返回 null 则不加。
   * @returns {Array} 长度 = panes.length，第 i 个的 gridIndex = paneBase + i
   */
  function paneYAxes(panes, spec) {
    spec = spec || {};
    var base = spec.paneBase == null ? 2 : spec.paneBase;
    var show = spec.showFct !== false;
    return (panes || []).map(function (p, i) {
      if (spec.style === 'replay') {
        // 重播规格：replay.js 消费 {name, pct, position, scale, formatter, axisLabel}
        var r = { name: p.name, pct: false, position: 'right', scale: true };
        if (spec.paneAxisLabel) {
          var al = spec.paneAxisLabel(p, i);
          if (al) r.axisLabel = al;
        }
        return r;
      }
      var ax = { type: 'value', gridIndex: base + i, show: show, scale: true,
               position: 'right', name: p.name, nameTextStyle: { fontSize: 10 } };
      if (spec.paneAxisLabel) {
        var al2 = spec.paneAxisLabel(p, i);
        if (al2) ax.axisLabel = al2;
      }
      return ax;
    });
  }

  /** pane 的 grid 下标序列（重播/游戏页只需要下标，不需要整套 ECharts option）。 */
  function paneGridIndex(paneCount, paneBase) {
    var base = paneBase == null ? 2 : paneBase;
    var out = [];
    for (var i = 0; i < (paneCount || 0); i++) out.push(base + i);
    return out;
  }

  /**
   * 因子 pane 的 series 声明（索引内部生成）。
   * @returns {Array} 每项 {name,type,xAxisIndex,yAxisIndex,data,...}
   */
  function paneSeries(panes, spec) {
    spec = spec || {};
    var base = spec.paneBase == null ? 2 : spec.paneBase;
    var up = (spec.histColors || {}).up || COLORS.histUp;
    var down = (spec.histColors || {}).down || COLORS.histDown;
    // R3-1（TV_ROUND3 §2）：HIST 家族 pane 的零基线。MACD/PPO/PVO 这类
    // 「正负柱 + 双线」面板，肉眼判断"是不是同一把尺"的唯一参照就是 0 位；
    // 没有零基线时 HIST 只占 pane 高 ~44%，用户据此认定三线各自坐标系。
    // silent 不吞鼠标事件；中性色与阈值线同色（不引新色相，浅/夜间均可读）。
    var zeroLine = { silent: true, symbol: 'none',
      lineStyle: { type: 'dashed', width: 1, color: '#8B7FBE' },
      data: [{ yAxis: 0 }] };
    var out = [];
    (panes || []).forEach(function (p, i) {
      var gi = base + i;
      var markLine = null;
      if (p.thresholds && p.thresholds.length) {
        markLine = { silent: true, symbol: 'none',
          lineStyle: { type: 'dashed', color: '#8B7FBE' },
          label: { formatter: function (pp) { return Number(pp.value).toFixed(2); }, fontSize: 10 },
          data: p.thresholds.map(function (v) { return { yAxis: v }; }) };
      }
      p.series.forEach(function (s) {
        var isHist = !!s.hist || s.type === 'bar';
        if (spec.style === 'replay') {
          // 重播规格：replay.js 把 s.grid 同时用作 xAxisIndex/yAxisIndex
          var cfg = { name: s.name, type: s.type || 'line', data: s.values, grid: gi,
                      color: s.color || '#6750A4', width: 1.2 };
          if (isHist) {
            cfg.color = undefined;
            // R3-1：带 hist 标记供调用方 markLineFor 分流（HIST→零基线 /
            // 价格系列→末价标签）；zeroBase 已被"窗口内归零"占用，不能复用
            cfg.hist = true;
            cfg.extra = { itemStyle: { color: function (pp) {
              return (Number(pp.value) >= 0 ? up : down); } } };
          }
          out.push(cfg);
          return;
        }
        if (isHist) {  // MACD 柱：正红负绿（与 K 线涨跌同色）
          out.push({ name: s.name, type: 'bar', xAxisIndex: gi, yAxisIndex: gi, data: s.values,
                     itemStyle: { color: function (pp) {
                       return (Number(pp.value) >= 0 ? up : down); } },
                     // R3-1：HIST 挂零基线（静态路径直接进 option）
                     markLine: zeroLine });
        } else {
          out.push({ name: s.name, type: 'line', xAxisIndex: gi, yAxisIndex: gi, data: s.values,
                     showSymbol: false, lineStyle: { width: 1.2 }, color: s.color, markLine: markLine });
          markLine = null;  // 阈值线只挂同面板第一条线，避免重复
        }
      });
    });
    return out;
  }

  /**
   * 主入口：因子 pane → 完整 ECharts option 的 grid/xAxis/yAxis/series。
   *
   * @param {Array}  spec.panes      plan().panes
   * @param {Object} spec            {
   *   paneBase: 2,                  // pane 前已有几个 grid（主图 + 量）
   *   grids: [...],                 // paneGrids() 生成
   *   dates: [...],                 // x 类目；缺省则不产 xAxis
   *   axisLabelIndex: 1+n,          // 时间轴挂哪个 grid
   *   showFct: true,
   *   headYAxes: [...],             // 前 paneBase 个 yAxis（主图/量），原样透传
   *   xAxisExtra: {},               // 合并进每个 xAxis
   *   histColors: {up, down}
   * }
   * @returns {{grid, xAxis, yAxis, series, paneBase}}
   */
  function panesToOption(panes, spec) {
    spec = spec || {};
    panes = panes || [];
    var base = spec.paneBase == null ? 2 : spec.paneBase;
    var grid = spec.grids || paneGrids(panes.length, spec);
    var yAxis = (spec.headYAxes || []).concat(paneYAxes(panes, spec));
    if (spec.style !== 'replay') _assertPaneInvariant(grid, yAxis, base, panes);
    var series = paneSeries(panes, spec);
    var xAxis = null;
    if (spec.dates) {
      var labelIdx = spec.axisLabelIndex == null ? axisLabelIndex(panes.length, spec) : spec.axisLabelIndex;
      xAxis = grid.map(function (g, i) {
        var ax = { type: 'category', data: spec.dates, gridIndex: i,
                   axisLabel: { show: i === labelIdx },
                   // QRE-PRICE-SCALE（T2）：只画水平网格线，类别轴不画竖线
                   splitLine: { show: false } };
        if (spec.xAxisExtra) Object.keys(spec.xAxisExtra).forEach(function (k) { ax[k] = spec.xAxisExtra[k]; });
        return ax;
      });
    }
    return { grid: grid, xAxis: xAxis, yAxis: yAxis, series: series, paneBase: base };
  }

  // ────────────────────────────────────────────────────────────────────────
  // QRE-KLINE-PARAM-GRID（T5，2026-10-29）：指标参数变体识别与切换。
  //
  // 背景：因子表是宽表，同一指标的多个参数组**已经算好入库**
  // （如 macd_12_26_9 / macd_15_35_10 / macd_24_52_18 / macd_6_13_5，
  //   rsi_2/6/7/9/12/14/21/24/28），只是 symbol 产物只下发策略用到的那组。
  // 前端因此只需要「切列」：识别 family + params，按用户选择过滤因子集合，
  // 再交给既有 plan() 归组。不重算、不连库、不改后端。
  //
  // 硬规则：
  // - 只有一个参数组（或没有参数化因子）时，applyParamChoices 必须**逐字节**
  //   返回入参（存量产物零影响）；
  // - 非法/未知选择一律忽略，不得丢面板；
  // - 不改复权口径：只切换预计算列，不重新计算任何值。
  // ────────────────────────────────────────────────────────────────────────

  // family 别名归一：sma 与 ma 同族；boll 的上中下轨道列同族
  var PARAM_FAMILY_ALIAS = { sma: "ma", bbl: "boll", bbm: "boll", bbu: "boll" };
  // MACD/PPO/PVO 三元组的旧列名（macd_dif / macd_dea / macd_hist，无参数后缀）
  var TRIPLE_ALIAS_RE = /^(macd|ppo|pvo)[\s_-](dif|dea|signal|hist|histogram)([\s_-].*)?$/;
  // 通用：<family>_<params>，params 是一到多组数字（rsi_14 / kdj_9_3 / boll_20_2）
  var PARAM_RE = /^([a-z][a-z0-9]*?)_(\d+(?:_\d+)*)$/;

  function _familyOf(raw) {
    var f = String(raw || "").toLowerCase();
    var alias = PARAM_FAMILY_ALIAS[f] || f;
    // MACD/PPO/PVO 三元组的 s/h 后缀（macds/macdh）归到主家族
    var m = /^(macd|ppo|pvo)(s|h)$/.exec(alias);
    if (m) return m[1];
    return alias;
  }

  /** 单个因子的 {family, params, role}；非参数化因子返回 null。 */
  function paramKeyOf(f) {
    var keys = [f && f.col, f && f.name];
    for (var i = 0; i < keys.length; i++) {
      var low = String(keys[i] || "").toLowerCase();
      if (!low) continue;
      var m = TRIPLE_ALIAS_RE.exec(low);
      if (m) {
        return { family: m[1], params: m[3] ? String(m[3]).replace(/^[\s_-]+/, "") : "",
                 role: "alias" };
      }
      m = PARAM_RE.exec(low);
      if (m) {
        var fam = _familyOf(m[1]);
        var params = m[2];
        // boll 轨道列的参数形如 20_2_0_2_0（多退一位 std），只取前两组
        if (fam === "boll") {
          var parts = params.split("_");
          params = parts.slice(0, 2).join("_");
        }
        return { family: fam, params: params, role: "param" };
      }
    }
    return null;
  }

  /**
   * 参数变体清单（按首次出现顺序）。
   * @returns {Array<{family, label, variants: Array<{params, label, cols, count}>}>}
   *   只有一个变体的家族也返回——由调用方决定是否展示（≥2 才值得给选择器）。
   */
  function paramVariants(factors) {
    factors = factors || [];
    var order = [], byFam = {};
    factors.forEach(function (f) {
      var k = paramKeyOf(f);
      if (!k) return;
      var fam = byFam[k.family];
      if (!fam) {
        fam = { family: k.family, label: k.family.toUpperCase(), variants: [], _seen: {} };
        byFam[k.family] = fam;
        order.push(fam);
      }
      var v = fam._seen[k.params];
      if (!v) {
        v = { params: k.params, label: k.params || "默认", cols: [], count: 0 };
        fam._seen[k.params] = v;
        fam.variants.push(v);
      }
      v.cols.push(f.col || f.name || "");
      v.count += 1;
    });
    order.forEach(function (fam) { delete fam._seen; });
    return order;
  }

  /**
   * 按用户选择过滤因子集合。choices = {family: params}。
   * 没有选择 / 选择非法 / 该家族只有一个变体 → 该家族全部保留。
   * 整体无选择时**原样返回入参对象**（逐字节不变）。
   */
  function applyParamChoices(factors, choices) {
    factors = factors || [];
    if (!choices || typeof choices !== "object") return factors;
    var fams = paramVariants(factors);
    if (!fams.length) return factors;
    var keep = null;
    fams.forEach(function (fam) {
      if (fam.variants.length < 2) return;          // 只有一个组：无需选择
      var want = choices[fam.family];
      if (typeof want !== "string" || !want) return;
      var hit = null;
      fam.variants.forEach(function (v) { if (v.params === want) hit = v; });
      if (!hit) return;                              // 未知参数：忽略
      if (!keep) keep = {};
      keep[fam.family] = {};
      hit.cols.forEach(function (c) { keep[fam.family][c] = true; });
    });
    if (!keep) return factors;
    return factors.filter(function (f) {
      var k = paramKeyOf(f);
      if (!k || !keep[k.family]) return true;       // 非参数化因子全部保留
      return !!keep[k.family][f.col || f.name || ""];
    });
  }

  window.QREFactorLayout = {
    plan: plan, COLORS: COLORS,
    paneGrids: paneGrids, axisLabelIndex: axisLabelIndex,
    paneYAxes: paneYAxes, paneSeries: paneSeries, panesToOption: panesToOption,
    paneGridIndex: paneGridIndex,
    assertPaneInvariant: _assertPaneInvariant,
    paramKeyOf: paramKeyOf, paramVariants: paramVariants,
    applyParamChoices: applyParamChoices,
  };
})();
