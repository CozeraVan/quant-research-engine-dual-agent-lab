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

  function plan(factors, states) {
    factors = factors || [];
    states = states || {};
    var used = {}, groups = [];

    // 预索引全部因子键（col/name 小写），供"s 信号线对"探测 sibling
    var allKeys = {};
    factors.forEach(function (f) {
      if (f.col) allKeys[String(f.col).toLowerCase()] = true;
      if (f.name) allKeys[String(f.name).toLowerCase()] = true;
    });

    // 1) 家族归组：MACD/PPO/PVO 三元组、KDJ、STOCH、AROON、VORTEX、s 信号线对
    var buckets = {};
    factors.forEach(function (f, i) {
      if (isOverlay(f)) return;  // overlay 优先，不进家族
      var r = familyOf(f, allKeys);
      if (!r) return;
      var bkey = r.fam === "triple" ? (r.base + "_" + r.suffix) : r.gkey;
      if (!buckets[bkey]) buckets[bkey] = { key: bkey, fam: r.fam, label: r.label, roles: {}, order: i };
      if (!buckets[bkey].roles[r.role]) buckets[bkey].roles[r.role] = { f: f, idx: i };
    });
    Object.keys(buckets).forEach(function (bkey) {
      var b = buckets[bkey];
      if (b.fam === "triple") {
        if (!(b.roles.dif && b.roles.dea)) return;  // 只有单线不成组，落到独立面板
        ["dif", "dea", "hist"].forEach(function (r) { if (b.roles[r]) used[b.roles[r].idx] = true; });
        groups.push({ key: bkey, label: b.label, kind: "macd", roles: b.roles,
                      defaultState: "pane", allowed: ["pane", "hidden"], order: b.order });
      } else {
        var members = Object.keys(b.roles).map(function (r) { return b.roles[r]; });
        if (members.length < 2) return;  // 单线不成组
        members.forEach(function (mb) { used[mb.idx] = true; });
        groups.push({ key: bkey, label: b.label, kind: "family", members: members,
                      defaultState: "pane", allowed: ["pane", "hidden"], order: b.order });
      }
    });

    // 2) overlay 启发式；3) 其余独立面板
    factors.forEach(function (f, i) {
      if (used[i]) return;
      var disp = f.display || null;  // display 元数据接口预留（本期后端不下发）
      var kind = (disp && disp.chart_type) || (isOverlay(f) ? "overlay" : "pane");
      var key = fkey(f) || ("f" + i);
      if (kind === "overlay") {
        groups.push({ key: key, label: f.name, kind: "overlay", member: { f: f, idx: i },
                      defaultState: "overlay", allowed: ["overlay", "pane", "hidden"], order: i });
      } else {
        groups.push({ key: key, label: f.name, kind: "pane", member: { f: f, idx: i },
                      defaultState: "pane", allowed: ["pane", "hidden"], order: i });
      }
    });
    groups.sort(function (a, b) { return a.order - b.order; });

    var chips = [], overlays = [], panes = [], oi = 0;
    groups.forEach(function (g) {
      var st = g.allowed.indexOf(states[g.key]) >= 0 ? states[g.key] : g.defaultState;
      chips.push({ key: g.key, label: g.label, kind: g.kind, state: st, states: g.allowed });
      if (st === "hidden") return;
      if (st === "overlay") {
        overlays.push({ f: g.member.f, name: g.member.f.name, color: COLORS.overlay[oi++ % COLORS.overlay.length] });
        return;
      }
      if (g.kind === "macd") {
        var series = [];
        if (g.roles.dif) series.push({ name: "DIF", type: "line", values: g.roles.dif.f.values, color: COLORS.dif });
        if (g.roles.dea) series.push({ name: "DEA", type: "line", values: g.roles.dea.f.values, color: COLORS.dea });
        if (g.roles.hist) series.push({ name: "HIST", type: "bar", values: g.roles.hist.f.values, hist: true });
        var ths = [];
        ["dif", "dea", "hist"].forEach(function (r) {
          var f = g.roles[r] && g.roles[r].f;
          if (f && f.thresholds) ths = ths.concat(f.thresholds);
        });
        panes.push({ key: g.key, name: g.label, thresholds: ths, series: series });
      } else if (g.kind === "family") {
        var ci = 0, fseries = [], fths = [];
        g.members.forEach(function (mb) {
          if (mb.f.thresholds) fths = fths.concat(mb.f.thresholds);
          fseries.push({ name: mb.f.name, type: "line", values: mb.f.values,
                         color: COLORS.multi[ci++ % COLORS.multi.length] });
        });
        panes.push({ key: g.key, name: g.label, thresholds: fths, series: fseries });
      } else {
        var f = g.member.f;
        panes.push({ key: g.key, name: f.name, thresholds: f.thresholds || [],
                     series: [{ name: f.name, type: "line", values: f.values, color: COLORS.pane }] });
      }
    });
    return { chips: chips, overlays: overlays, panes: panes, paneCount: panes.length };
  }

  window.QREFactorLayout = { plan: plan, COLORS: COLORS };
})();
