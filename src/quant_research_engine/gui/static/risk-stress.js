/* QRE-RISK-STRESS-TABLE — 个股 FRM 压力测试情景表（纯函数，无 DOM 依赖）
 *
 * 数据契约来自 worker 的 risk_report.stress.scenarios：
 *   { 情景名: { description, window: {start, end}, strategy_cumulative_return,
 *              strategy_peak_trough_drawdown, var, error? } }
 * 未覆盖窗口带 error（只有 description/error）；旧逻辑按累计收益过滤会把它们
 * 整条吞掉，这里改为显式列出「未覆盖窗口」，不再静默消失。
 *
 * 口径：累计收益保留符号（红涨绿跌）；最大回撤与 VaR 是损失，取负号并用 .neg。
 */
(function () {
  "use strict";

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
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

  window.QRESymbolDetail = { stressTable: stressTable };
})();
