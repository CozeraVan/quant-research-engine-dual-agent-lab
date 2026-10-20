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
 *   - ema/ma/sma/wma/dema/tema/boll 系 → overlay 主图；
 *   - macd_<P>/macds_<P>/macdh_<P> 同参数后缀（或别名 dif/dea/hist）→ 合并 MACD 面板
 *     （至少 DIF+DEA 才合并；HIST 可选，柱正红负绿与 K 线涨跌同色）；
 *   - 其余 → 每因子一个独立面板（保留 thresholds markLine）。
 * 状态机：overlay 类 chip 三态循环 overlay→pane→hidden；MACD/普通面板 chip
 * 只循环 pane→hidden（量纲与价格不同，叠加无意义）。
 */
(function () {
  "use strict";

  var OVERLAY_RE = /^(ema|ma|sma|wma|dema|tema)\d*$|^(boll|bb)_(upper|mid|lower)|^boll/i;
  var COLORS = {
    overlay: ["#E8A33D", "#2A9D8F", "#6750A4"],  // 均线循环色：橙/青/主紫
    pane: "#6750A4",                              // 因子副图线（同 UI 规范既有口径）
    dif: "#6750A4", dea: "#E8A33D",
    histUp: "#C93A3A", histDown: "#1E8E5A",       // 与 K 线涨跌同色
  };

  function fkey(f) { return f.col || f.name || ""; }

  // 识别 MACD 角色：列名形态 macd_<P>/macds_<P>/macdh_<P>；别名 dif/dea/hist 形态
  function macdRole(f) {
    var keys = [f.col || "", f.name || ""];
    for (var k = 0; k < keys.length; k++) {
      var low = String(keys[k]).toLowerCase();
      var m = /^(macd|macds|macdh)_(.+)$/.exec(low);
      if (m) return { role: m[1] === "macd" ? "dif" : (m[1] === "macds" ? "dea" : "hist"), suffix: m[2] };
      if (low === "macd" || low === "dif") return { role: "dif", suffix: "" };
      if (low === "macds" || low === "macd_signal" || low === "dea") return { role: "dea", suffix: "" };
      if (low === "macdh" || low === "hist" || low === "macd柱") return { role: "hist", suffix: "" };
    }
    return null;
  }

  function isOverlay(f) {
    return OVERLAY_RE.test(f.col || "") || OVERLAY_RE.test(f.name || "");
  }

  function plan(factors, states) {
    factors = factors || [];
    states = states || {};
    var used = {}, groups = [];

    // 1) MACD 三元组按参数后缀归组（至少 DIF+DEA 才合并，缺 HIST 只画双线）
    var buckets = {};
    factors.forEach(function (f, i) {
      var r = macdRole(f);
      if (!r) return;
      var bkey = "macd_" + r.suffix;
      if (!buckets[bkey]) buckets[bkey] = { key: bkey, roles: {}, order: i };
      if (!buckets[bkey].roles[r.role]) buckets[bkey].roles[r.role] = { f: f, idx: i };
    });
    Object.keys(buckets).forEach(function (bkey) {
      var b = buckets[bkey];
      if (!(b.roles.dif && b.roles.dea)) return;  // 只有单线不成组，落到独立面板
      ["dif", "dea", "hist"].forEach(function (r) { if (b.roles[r]) used[b.roles[r].idx] = true; });
      groups.push({ key: bkey, label: "MACD", kind: "macd", roles: b.roles,
                    defaultState: "pane", allowed: ["pane", "hidden"], order: b.order });
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
        panes.push({ key: g.key, name: "MACD", thresholds: ths, series: series });
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
