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

  function clampPct(x) {
    if (!num(x)) return 0;
    if (x < 0) return 0;
    if (x > 100) return 100;
    return x;
  }

  /* 阈值标尺的几何（R4-2.5）。只出数值，格式化留给模板。
     ------------------------------------------------------------------------
     两种 mode：
       threshold —— 年化波动的绝对轴。三段轨 low:[0,lo) / mid:[lo,hi) / high:[hi,
                    domain]，domain 取 max(hi*1.5, peak*1.15)，即高波动边界之外
                    再留 50% 余量，同时保证最右侧游标不会顶到轴端。游标 xPct
                    是它在轴上的真实位置，读得出「离高波动边界还有多远」。
       relative  —— 旧产物没有 regime_thresholds，绝对轴失去参照：硬画成轴位置
                    会谎称某个口径「接近上限」，比不画更糟。降级成两口径的相对
                    长度对比，xPct 是「占较大者的百分比」，不是轴位置。
     无口径值也无阈值时返回 null，交给模板走空态。 */
  function gaugeModel(vol) {
    if (!vol) return null;
    var marksSrc = [];
    if (num(vol.ewma_annual)) marksSrc.push({ key: 'ewma', label: 'EWMA', value: vol.ewma_annual });
    if (num(vol.garch_annual)) marksSrc.push({ key: 'garch', label: 'GARCH', value: vol.garch_annual });
    var th = vol.regime_thresholds;
    var lo = th && num(th.low_below) ? th.low_below : null;
    var hi = th && num(th.high_at_or_above) ? th.high_at_or_above : null;
    var hasTh = lo !== null && hi !== null && lo > 0 && hi > lo;
    if (!marksSrc.length && !hasTh) return null;
    var peak = 0;
    marksSrc.forEach(function (m) { if (m.value > peak) peak = m.value; });

    if (hasTh) {
      var domain = Math.max(hi * 1.5, peak * 1.15);
      if (!num(domain) || domain <= 0) return null;
      var spans = [
        { key: 'low', from: 0, to: lo },
        { key: 'mid', from: lo, to: hi },
        { key: 'high', from: hi, to: domain },
      ];
      return {
        mode: 'threshold',
        domain: domain,
        segments: spans.map(function (s) {
          return { key: s.key, from: s.from, to: s.to,
                   leftPct: clampPct(s.from / domain * 100),
                   widthPct: clampPct((s.to - s.from) / domain * 100) };
        }),
        marks: marksSrc.map(function (m) {
          return { key: m.key, label: m.label, value: m.value,
                   xPct: clampPct(m.value / domain * 100) };
        }),
        ticks: [0, lo, hi, domain].map(function (v) {
          return { value: v, leftPct: clampPct(v / domain * 100) };
        }),
        degraded: false,
      };
    }

    if (!(peak > 0)) return null;
    return {
      mode: 'relative',
      domain: peak * 1.15,
      segments: [],
      marks: marksSrc.map(function (m) {
        return { key: m.key, label: m.label, value: m.value,
                 xPct: clampPct(m.value / peak * 100) };
      }),
      ticks: [],
      degraded: true,
    };
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

  root.QREVolRegime = {
    label: label,
    describe: describe,
    tipText: tipText,
    gaugeModel: gaugeModel,
  };
})(typeof window !== 'undefined' ? window : this);