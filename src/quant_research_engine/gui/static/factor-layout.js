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
  function plan(factors, states) {
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
      panes.push({key: g.key, name: g.label, thresholds: thresholds, series: series});
    });
    return {chips: chips, overlays: overlays, panes: panes, paneCount: panes.length};
  }

  window.QREFactorLayout = { plan: plan, COLORS: COLORS };
})();
