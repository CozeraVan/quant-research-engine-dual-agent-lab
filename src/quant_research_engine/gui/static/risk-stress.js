/* QRE-RISK-STRESS-TABLE — 个股 FRM 压力测试情景表（纯函数，无 DOM 依赖）
 *
 * 数据契约来自 worker 的 risk_report.stress.scenarios：
 *   { 情景名: { description, window: {start, end}, strategy_cumulative_return,
 *              strategy_peak_trough_drawdown, var, error? } }
 * 未覆盖窗口带 error（只有 description/error）；旧逻辑按累计收益过滤会把它们
 * 整条吞掉，这里改为显式列出「未覆盖窗口」，不再静默消失。
 *
 * 口径：累计收益保留符号（红涨绿跌）；最大回撤取负号，VaR/ES 按损失正数展示。
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function varEsReference(stress, pct) {
    var fmt = typeof pct === "function" ? pct : function (v) { return v == null ? "—" : String(v); };
    var ref = (stress && stress.var_es_reference) || {};
    if (ref.var == null && ref.es == null) return "";
    var confidence = Number(ref.confidence);
    var level = isFinite(confidence)
      ? Math.round((confidence <= 1 ? confidence * 100 : confidence)) + "%" : "—";
    var tip = ref.note || "当前 1 日 EWMA 参数法 VaR/ES，损失以正数展示。";
    return '<div class="metric-strip risk-reference-strip"><div class="metric-card">' +
      '<div class="m-label">' + esc(level) + ' VaR / ES（EWMA 参数法） ' +
      '<button type="button" class="tip-trigger" data-tip="' + esc(tip) +
      '" aria-label="VaR/ES 参考值说明">?</button></div>' +
      '<div class="m-value neg">' + fmt(ref.var) + " / " + fmt(ref.es) + "</div></div></div>";
  }

  function stressTable(stress, pct, cls) {
    var fmt = typeof pct === "function" ? pct : function (v) { return v == null ? "—" : String(v); };
    var klass = typeof cls === "function" ? cls : function () { return "flat"; };
    var sc = (stress && stress.scenarios) || {};
    var rows = Object.keys(sc).map(function (k) {
      return Object.assign({ name: k }, sc[k]);
    });
    var covered = rows.filter(function (x) {
      return !x.error && (x.strategy_cumulative_return != null ||
        x.strategy_peak_trough_drawdown != null || x.var != null);
    });
    var skipped = rows.filter(function (x) { return x.error; })
      .map(function (x) { return x.description || x.name; });
    if (!covered.length) {
      return '<div class="chart-empty">压力测试暂无可用情景' +
        (skipped.length ? "：" + esc(skipped.join("、")) + "（回测区间未覆盖这些窗口）" : "") +
        "</div>";
    }
    var body = covered.map(function (x) {
      var ret = x.strategy_cumulative_return;
      var dd = x.strategy_peak_trough_drawdown;
      var v = x.var;
      var win = x.window ? (x.window.start + " ~ " + x.window.end) : "—";
      return "<tr><td>" + esc(x.description || x.name) + "</td><td>" + esc(win) + "</td>" +
        '<td class="num ' + klass(ret) + '">' + fmt(ret) + "</td>" +
        '<td class="num ' + (dd == null ? "" : "neg") + '">' +
          (dd == null ? "—" : fmt(-Math.abs(dd))) + "</td>" +
        '<td class="num ' + (v == null ? "" : "neg") + '">' + fmt(v) + "</td></tr>";
    }).join("");
    var note = skipped.length
      ? '<p class="risk-stress-note">未覆盖窗口：' + esc(skipped.join("、")) +
        "（回测区间未覆盖，未参与统计）</p>"
      : "";
    return '<div class="table-wrap"><table class="detail-table risk-stress-table"><thead><tr>' +
      "<th>情景</th><th>窗口</th><th>累计收益</th><th>最大回撤</th><th>VaR（日）</th>" +
      "</tr></thead><tbody>" + body + "</tbody></table></div>" + note;
  }

  window.QRESymbolDetail = { stressTable: stressTable, varEsReference: varEsReference };
})();
