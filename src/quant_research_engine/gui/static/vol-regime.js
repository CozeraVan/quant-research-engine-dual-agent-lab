/* ============================================================================
   QRE-VOL-REGIME —— 波动率状态的唯一文案来源（job.html / lab_result.html 共用）
   ----------------------------------------------------------------------------
   为什么单独一个文件：原先两个模板各写一段 volTxt 拼字符串，一处用 data-tip、
   一处用 .opt 灰字，且都直接打印 `当前波动状态 mid` 这样的英文枚举值。文案一旦
   分叉就再也对不齐，所以收敛到这里，模板只负责把结果塞进 DOM。

   输入是 `build_lab_risk_view()` 的 `volatility` 视图：
     { ewma_annual, garch_annual, regime_counts, latest_regime, regime_thresholds }
   其中 regime_thresholds = { low_below, high_at_or_above }（年化波动率切点，
   由 risk/report.py 按样本 1/3、2/3 分位换算得到）。旧产物没有这个字段，
   describe() 必须优雅退化成只报状态，不能出现 undefined/NaN/null。
   ============================================================================ */
(function (root) {
  'use strict';

  var LABELS = { low: '低波动', mid: '中波动', high: '高波动' };

  function label(key) {
    return LABELS[key] || '';
  }

  function pct(x) {
    return (x * 100).toFixed(1) + '%';
  }

  function num(x) {
    return typeof x === 'number' && isFinite(x);
  }

  // 当前状态一句话：有阈值就把三档边界讲清楚，没有就只说状态
  function describe(vol) {
    if (!vol || !vol.latest_regime) return '';
    var state = label(vol.latest_regime);
    if (!state) return '';
    var th = vol.regime_thresholds;
    var lo = th && num(th.low_below) ? th.low_below : null;
    var hi = th && num(th.high_at_or_above) ? th.high_at_or_above : null;
    if (lo === null || hi === null) return '当前：' + state;
    return '当前：' + state + '（年化 ' + pct(lo) + '–' + pct(hi) + ' 为中档；≥' +
      pct(hi) + ' 为高，<' + pct(lo) + ' 为低）';
  }

  // 悬停说明：各口径数值 + 三档样本天数
  function tipText(vol) {
    if (!vol) return '';
    var out = [];
    if (num(vol.ewma_annual)) out.push('EWMA 年化波动 ' + pct(vol.ewma_annual));
    if (num(vol.garch_annual)) out.push('GARCH 年化波动 ' + pct(vol.garch_annual));
    if (vol.latest_regime && label(vol.latest_regime)) {
      out.push('当前状态 ' + label(vol.latest_regime));
    }
    var rc = vol.regime_counts;
    if (rc) {
      var parts = [];
      ['low', 'mid', 'high'].forEach(function (k) {
        if (num(rc[k])) parts.push(label(k) + ' ' + rc[k]);
      });
      if (parts.length) out.push('样本天数：' + parts.join(' / '));
    }
    return out.join('；');
  }

  root.QREVolRegime = { label: label, describe: describe, tipText: tipText };
})(typeof window !== 'undefined' ? window : this);