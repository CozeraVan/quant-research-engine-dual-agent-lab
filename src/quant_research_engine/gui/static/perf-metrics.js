/**
 * perf-metrics.js — 风险调整收益指标与持股周期（纯函数共享层）
 *
 * QRE-PERF-METRICS-CONTRACT（2026-10-28）：
 * 前端算而不是后端算，是为了让**存量回测产物立即显示**——job 的 chart_data 快照里
 * 有 equity + benchmarks，symbol 的快照里有 kline + trades，都在手边，无需重跑。
 * （本地 run 产物已清空、ECS 无行情库，后端补算对存量产物不可行。）
 *
 * 公式与 `src/quant_research_engine/risk/performance.py` 逐条对应，常量与
 * `src/quant_research_engine/risk/constants.py` 一致：
 *   ANNUALIZATION_FACTOR = 252、DEFAULT_RISK_FREE_RATE = 0.03
 * 改任何公式/常量必须同时改 Python 侧并让 tests/test_perf_metrics.py 通过
 * （该测试用 Python performance_summary 在同一序列上交叉验证本文件，容差 1e-9）。
 *
 * 口径声明（重要，勿"修正"）：
 *   本文件按**净值曲线差分**算指标，与页面曲线同源，用户可自行复算；
 *   后端 risk_report.json 的 performance 节按**引擎日收益序列**算，输入序列不同，
 *   两者数值可有差、方向应一致。这不是 bug，是两种口径，已在 24 号文档固化。
 *
 * 纯函数、不碰 DOM、不依赖任何全局；IIFE + typeof window 守卫，Node vm 可直接断言。
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) { module.exports = api; }
  if (root) { root.QREPerfMetrics = api; }
})(typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : null), function () {
  'use strict';

  // 与 risk/constants.py 对齐；test_perf_metrics.py 会读源码断言这两个数
  var ANN = 252;
  var RF = 0.03;

  function isNum(v) { return typeof v === 'number' && isFinite(v); }

  /** 简单日收益：v[i]/v[i-1] − 1。跳过 null / 非有限 / ≤0 的前值（除零与负净值无意义）。 */
  function dailyReturns(values) {
    var out = [];
    if (!values || !values.length) { return out; }
    for (var i = 1; i < values.length; i++) {
      var a = values[i - 1], b = values[i];
      if (!isNum(a) || !isNum(b) || a <= 0 || b <= 0) { continue; }
      out.push(b / a - 1);
    }
    return out;
  }

  /** 配对后逐位 dropna —— 对应 Python `_aligned`（DataFrame dropna）。 */
  function alignReturns(r, m) {
    var a = [], b = [];
    var n = Math.min((r || []).length, (m || []).length);
    for (var i = 0; i < n; i++) {
      if (isNum(r[i]) && isNum(m[i])) { a.push(r[i]); b.push(m[i]); }
    }
    return { r: a, m: b };
  }

  function mean(a) {
    if (!a.length) { return null; }
    var s = 0;
    for (var i = 0; i < a.length; i++) { s += a[i]; }
    return s / a.length;
  }

  /** 样本标准差 ddof=1 —— 对应 pandas `.std(ddof=1)` / numpy `std(ddof=1)`。 */
  function std(a) {
    if (!a || a.length < 2) { return null; }
    var mu = mean(a), s = 0;
    for (var i = 0; i < a.length; i++) { s += (a[i] - mu) * (a[i] - mu); }
    return Math.sqrt(s / (a.length - 1));
  }

  function cov(x, y) {
    var n = Math.min(x.length, y.length);
    if (n < 2) { return null; }
    var mx = mean(x.slice(0, n)), my = mean(y.slice(0, n)), s = 0;
    for (var i = 0; i < n; i++) { s += (x[i] - mx) * (y[i] - my); }
    return s / (n - 1);
  }

  /**
   * Sharpe = mean(r − rf/ann) / std(r, ddof=1) × √ann
   * 对应 `performance.sharpe_ratio`。
   */
  function sharpe(r, rf, ann) {
    rf = isNum(rf) ? rf : RF;
    ann = isNum(ann) ? ann : ANN;
    var s = std(r);
    if (s == null || s <= 0) { return null; }
    var dailyRf = rf / ann;
    var mu = mean(r.map(function (v) { return v - dailyRf; }));
    if (mu == null) { return null; }
    return mu / s * Math.sqrt(ann);
  }

  /** β = cov(r, m, ddof=1) / var(m, ddof=1) —— 对应 `performance.beta`（书1 Ch5 式 5.1）。 */
  function beta(r, m) {
    var p = alignReturns(r, m);
    if (p.r.length < 2) { return null; }
    var vm = std(p.m);
    if (vm == null || vm <= 0) { return null; }   // 基准方差 0（恒定基准）→ 不报错，返回 null
    var c = cov(p.r, p.m);
    if (c == null) { return null; }
    return c / (vm * vm);
  }

  /** IR = mean(r − m) / std(r − m, ddof=1) × √ann —— 对应 `performance.information_ratio`。 */
  function informationRatio(r, m, ann) {
    ann = isNum(ann) ? ann : ANN;
    var p = alignReturns(r, m);
    if (p.r.length < 2) { return null; }
    var active = p.r.map(function (v, i) { return v - p.m[i]; });
    var te = std(active);
    if (te == null || te <= 0) { return null; }
    return mean(active) / te * Math.sqrt(ann);
  }

  /**
   * Jensen's α：市场模型 (r − rf/ann) = α + β(m − rf/ann) + ε 的截距（式 5.5）。
   * 对应 `performance.jensens_alpha`；alpha_annual = alpha_daily × ann。
   */
  function jensensAlpha(r, m, rf, ann) {
    rf = isNum(rf) ? rf : RF;
    ann = isNum(ann) ? ann : ANN;
    var p = alignReturns(r, m);
    if (p.r.length < 2) { return null; }
    var dailyRf = rf / ann;
    var x = p.m.map(function (v) { return v - dailyRf; });
    var y = p.r.map(function (v) { return v - dailyRf; });
    var mx = mean(x), my = mean(y);
    if (mx == null || my == null) { return null; }
    var sxx = 0, sxy = 0;
    for (var i = 0; i < x.length; i++) { sxx += (x[i] - mx) * (x[i] - mx); sxy += (x[i] - mx) * (y[i] - my); }
    if (sxx <= 0) { return null; }   // 基准无波动 → 回归不成立
    var slope = sxy / sxx;           // = β（与 beta() 同源，仅截距不同）
    var intercept = my - slope * mx;
    return { alpha_daily: intercept, alpha_annual: intercept * ann, beta: slope };
  }

  /**
   * 主入口：由净值曲线 + 基准收盘序列算 α/β/IR/Sharpe。
   *
   * @param {Object} o
   * @param {number[]} o.equity   净值序列（与 dates 等长；null 允许）
   * @param {string[]} [o.dates]  日期序列（仅用于对齐校验，可省）
   * @param {Object}   o.benchmark {name, closes} 或 {dates, closes}
   * @returns {{sharpe:number|null, beta:number|null, ir:number|null,
   *            alpha_annual:number|null, n:number}|null}
   *          任何一步样本不足都返回对应项 null；整体无数据返回 null（调用方整块隐藏）。
   */
  function riskAdjusted(o) {
    o = o || {};
    var eq = dailyReturns(o.equity || []);
    if (eq.length < 2) { return null; }
    var b = o.benchmark || {};
    var bCloses = b.closes || [];
    var benchDates = b.dates || null;
    var bRet;
    if (benchDates && benchDates.length === bCloses.length) {
      // 基准自带日期：按 equity 日期对齐后再差分（个股页 kline 路径）
      var idx = {};
      for (var i = 0; i < benchDates.length; i++) { idx[benchDates[i]] = bCloses[i]; }
      var aligned = [];
      var dates = o.dates || [];
      for (var j = 0; j < dates.length; j++) {
        var v = idx[dates[j]];
        aligned.push(isNum(v) ? v : null);
      }
      bRet = dailyReturns(aligned);
    } else {
      // 基准与 equity 已同年份对齐（job 页 benchmarks 路径）：直接差分
      bRet = dailyReturns(bCloses);
    }
    if (!bRet.length) { return null; }
    var n = Math.min(eq.length, bRet.length);
    if (n < 2) { return null; }
    var r = eq.slice(eq.length - n), m = bRet.slice(bRet.length - n);
    var ja = jensensAlpha(r, m);
    return {
      sharpe: sharpe(r),
      beta: beta(r, m),
      ir: informationRatio(r, m),
      alpha_annual: ja ? ja.alpha_annual : null,
      n: n,
    };
  }

  /** 单笔交易持股周期（自然日）。缺字段 / 未平仓 / 非法日期 → null。 */
  function holdingDaysOf(t) {
    if (!t) { return null; }
    var a = t.entry_date, b = t.exit_date;
    if (!a || !b) { return null; }
    var d0 = Date.parse(String(a)), d1 = Date.parse(String(b));
    if (isNaN(d0) || isNaN(d1)) { return null; }
    var d = Math.round((d1 - d0) / 86400000);
    return d >= 0 ? d : null;
  }

  /**
   * 平均持股周期（自然日）。跳过缺字段 / 未平仓 / 非法日期的行；
   * 全部跳过返回 null（调用方显示「—」，不编 0）。
   */
  function avgHoldingDays(trades) {
    if (!trades || !trades.length) { return null; }
    var sum = 0, n = 0;
    for (var i = 0; i < trades.length; i++) {
      var d = holdingDaysOf(trades[i]);
      if (d == null) { continue; }
      sum += d;
      n += 1;
    }
    return n ? sum / n : null;
  }

  return {
    ANN: ANN,
    RF: RF,
    dailyReturns: dailyReturns,
    alignReturns: alignReturns,
    mean: mean,
    std: std,
    cov: cov,
    sharpe: sharpe,
    beta: beta,
    informationRatio: informationRatio,
    jensensAlpha: jensensAlpha,
    riskAdjusted: riskAdjusted,
    holdingDaysOf: holdingDaysOf,
    avgHoldingDays: avgHoldingDays,
  };
});
