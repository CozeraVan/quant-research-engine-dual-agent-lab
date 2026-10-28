/* QREPriceScale 专业价格轴格式化框架（TV_ROUND2 T2 · CR-2026-10-29）
 *
 * 背景：逆向侧 §4 样式规格表把「价格轴」列为与 TV 差距最大的单点——轴宽随位数跳动、
 * 精度由 ECharts 自动决定（同一根轴上 3 与 0.00 混排）、无末价标签、竖网格线干扰。
 * 本文件把这些规则收成**纯函数层**（Node vm 可测）+ ECharts 规格构造函数
 * （symbol.html 静态图与重播共用，防两处漂移）。
 *
 * 四条硬规则：
 * 1. priceScaleMode 0 普通 / 1 对数 / 2 百分比（以可见区间首根为基准）/ 3 指数化（首根=100）；
 * 2. 自动精度 = minMove 决定小数位数（A 股 0.01 → 2 位；数据比 minMove 更细时以数据为准）；
 * 3. 轴宽恒定：固定小数位 + 千分位 + 标签左对齐固定 margin + grid.right 按**全量数据**
 *    极值预算（不随可见窗口/缩放大幅跳动）；
 * 4. 刻度 1-2-5 密度（niceTicks 纯函数 + ECharts splitNumber）。
 *
 * 与 §4 规格表的偏差（有意决策，见 CR 文档）：
 * - 蜡烛涨跌色保持 A 股红涨绿跌（#C93A3A/#1E8E5A），未改用 TV 的 #26a69a/#ef5350；
 * - 画布/面板底色沿用项目主题 token（浅色默认、夜间模式自有深色），不硬编码 #131722；
 * - 网格线色由 night-mode.js 的主题层决定（深色下它优先于本文件取值）。
 */
(function () {
  "use strict";

  var MODES = [
    { id: 0, key: "normal", label: "普通", short: "价格", tip: "普通价格" },
    { id: 1, key: "log", label: "对数", short: "对数", tip: "对数价格轴（等比例变动同高）" },
    { id: 2, key: "percent", label: "百分比", short: "百分",
      tip: "百分比：以可见区间第一根收盘为基准" },
    { id: 3, key: "indexed", label: "指数化", short: "指数",
      tip: "指数化：可见区间第一根收盘 = 100" },
  ];
  var MODE_LS_KEY = "qre.kline.priceScaleMode";
  // A 股最小变动价位：价格轴默认 minMove
  var DEFAULT_MIN_MOVE = 0.01;
  var CHAR_PX = 7.0;          // 11px 字号下数字/逗号/小数点的近似宽度（无 canvas 时兜底）
  var FONT_DEFAULT = "11px sans-serif";

  function modeOf(v) {
    var n = Math.floor(Number(v));
    return (isFinite(n) && n >= 0 && n < MODES.length) ? n : 0;
  }
  function modeMeta(v) { return MODES[modeOf(v)]; }

  /* ---------------- 精度：minMove → 小数位数 ---------------- */

  // minMove 的小数位数即轴精度（0.01→2、0.05→2、2.5→1、1→0）。
  // 用 decimalsOf 而非 log10：minMove > 1 且带小数时（如 2.5）log10 取整会得 0。
  function precisionFromMinMove(minMove) {
    var m = Number(minMove);
    if (!isFinite(m) || m <= 0) return null;
    return Math.max(0, Math.min(10, decimalsOf(m, 10)));
  }

  // 数值需要的小数位数（容忍二进制浮点尾差，如 0.30000000000000004 → 2）
  function decimalsOf(v, cap) {
    var n = Number(v);
    if (!isFinite(n)) return 0;
    var c = cap == null ? 8 : cap;
    for (var d = 0; d <= c; d++) {
      var f = Math.pow(10, d);
      var tol = Math.max(1e-9, Math.abs(n * f) * 1e-9);
      if (Math.abs(n * f - Math.round(n * f)) <= tol) return d;
    }
    return c;
  }

  function inferPrecision(values, cap) {
    var max = 0;
    (values || []).forEach(function (v) {
      if (v == null || v === "") return;
      var n = Number(v);
      if (!isFinite(n) || n === 0) return;
      var d = decimalsOf(v, cap == null ? 8 : cap);
      if (d > max) max = d;
    });
    var c = cap == null ? 6 : cap;
    return Math.min(max, c);
  }

  // 自动精度：**minMove 是权威**（任务书"自动精度 = minMove"）。qfq 复权价常带
  // 4~6 位小数，若让数据抬高精度，轴宽会随复权因子跳动——所以给了 minMove 就只认
  // minMove；只有未给 minMove（因子副图）时才按数据推断。
  function autoPrecision(minMove, values, cap) {
    var p = precisionFromMinMove(minMove);
    if (p != null) return p;
    return inferPrecision(values, cap);
  }

  /* ---------------- 1-2-5 刻度密度 ---------------- */

  function niceStep(min, max, target) {
    var lo = Number(min), hi = Number(max);
    if (!isFinite(lo) || !isFinite(hi)) return null;
    if (hi < lo) { var t = lo; lo = hi; hi = t; }
    if (!(hi > lo)) return null;
    var tgt = Math.max(2, Math.floor(Number(target) || 5));
    var step0 = (hi - lo) / tgt;
    if (!(step0 > 0)) return null;
    var mag = Math.pow(10, Math.floor(Math.log(step0) / Math.LN10));
    var norm = step0 / mag;
    var mult = norm <= 1 ? 1 : (norm <= 2 ? 2 : (norm <= 5 ? 5 : 10));
    return mult * mag;
  }

  // 1-2-5 阶梯刻度（只返回 [min,max] 内的刻度值，含端点对齐）
  function niceTicks(min, max, target) {
    var step = niceStep(min, max, target);
    if (step == null) return [];
    var lo = Number(min), hi = Number(max);
    if (hi < lo) { var t = lo; lo = hi; hi = t; }
    var out = [];
    var start = Math.ceil(lo / step - 1e-9) * step;
    for (var v = start; v <= hi + step * 1e-6; v += step) {
      var r = Math.abs(v) < step * 1e-6 ? 0 : Number(v.toFixed(12));
      out.push(r);
      if (out.length > 200) break;
    }
    return out;
  }

  /* ---------------- 值格式化（4 种模式 + 千分位） ---------------- */

  function groupThousands(intPart) {
    return String(intPart).replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  }

  function formatValue(v, o) {
    o = o || {};
    var n = Number(v);
    if (v == null || v === "" || !isFinite(n)) return "—";
    var mode = modeOf(o.mode);
    var precision = o.precision == null
      ? autoPrecision(o.minMove == null ? DEFAULT_MIN_MOVE : o.minMove, [n])
      : Math.max(0, Math.floor(Number(o.precision)));
    if (!isFinite(precision)) precision = 2;
    var base = typeof o.base === "function" ? Number(o.base()) : Number(o.base);
    var out;
    if (mode === 2) {
      if (!isFinite(base) || base === 0) return "—";
      out = ((n / base - 1) * 100).toFixed(precision) + "%";
    } else if (mode === 3) {
      if (!isFinite(base) || base === 0) return "—";
      out = (n / base * 100).toFixed(precision);
    } else {
      out = n.toFixed(precision);
    }
    if (o.thousands === false) return out;
    var neg = out.charAt(0) === "-";
    var body = neg ? out.slice(1) : out;
    var dot = body.indexOf(".");
    var ip = dot < 0 ? body : body.slice(0, dot);
    var rest = dot < 0 ? "" : body.slice(dot);
    return (neg ? "-" : "") + groupThousands(ip) + rest;
  }

  /* ---------------- 轴宽恒定 ---------------- */

  function _measureCtx() {
    try {
      var doc = (typeof document !== "undefined") ? document : null;
      if (!doc || !doc.createElement) return null;
      if (_measureCtx._ctx !== undefined) return _measureCtx._ctx || null;
      var cv = doc.createElement("canvas");
      var ctx = (cv.getContext && cv.getContext("2d")) || null;
      _measureCtx._ctx = ctx;
      return ctx;
    } catch (e) { return null; }
  }

  function measureTextPx(text, font) {
    var ctx = _measureCtx();
    if (!ctx) return null;
    try {
      ctx.font = font || FONT_DEFAULT;
      var w = ctx.measureText(String(text)).width;
      return (isFinite(w) && w > 0) ? w : null;
    } catch (e) { return null; }
  }

  // 标签长度上界：用数据极值组合格式化，覆盖任何可见窗口都能出现的最长标签
  function candidateLabels(values, o) {
    o = o || {};
    var nums = [];
    (values || []).forEach(function (v) {
      var n = Number(v);
      if (isFinite(n)) nums.push(n);
    });
    if (!nums.length) return ["—"];
    var mn = Math.min.apply(null, nums), mx = Math.max.apply(null, nums);
    var mode = modeOf(o.mode);
    var cands = [mn, mx, 0];
    if (mode === 2 || mode === 3) {
      // 百分比/指数化的基准未知（取可见区间首根）：用全局极值做保守上界
      cands = [mn, mx, 0, mn, mx];
    }
    var seen = {}, out = [];
    cands.forEach(function (v, i) {
      var opt = { mode: mode, precision: o.precision, minMove: o.minMove };
      if (mode === 2 || mode === 3) opt.base = (i % 2 === 0) ? mn : mx;
      else opt.base = o.base;
      var k = mode + "|" + opt.base + "|" + v;
      if (seen[k]) return;
      seen[k] = 1;
      out.push(formatValue(v, opt));
    });
    return out;
  }

  function labelsWidthPx(labels, font) {
    var maxPx = 0, maxChars = 0;
    (labels || []).forEach(function (t) {
      var s = String(t == null ? "" : t);
      if (s.length > maxChars) maxChars = s.length;
      var px = measureTextPx(s, font);
      if (px != null && px > maxPx) maxPx = px;
    });
    if (!maxPx) maxPx = maxChars * CHAR_PX;
    return { px: maxPx, chars: maxChars };
  }

  // 轴宽（px）：固定不随可见窗口跳动；上下界夹紧避免极端数据把画布吃光
  function axisWidthPx(values, o) {
    o = o || {};
    var w = labelsWidthPx(candidateLabels(values, o), o.font);
    var px = Math.ceil((w.px + 12) / 2) * 2;
    return Math.min(140, Math.max(40, px));
  }

  /* ---------------- ECharts 规格 ---------------- */

  // axisLabel：固定宽 + 固定小数位 + 千分位 + 左对齐固定 margin（TV 价格标尺排布）
  function axisLabelSpec(values, o) {
    o = o || {};
    var mode = modeOf(o.mode);
    var precision = o.precision == null
      ? autoPrecision(o.minMove == null ? DEFAULT_MIN_MOVE : o.minMove, values)
      : Math.max(0, Math.floor(Number(o.precision)));
    if (!isFinite(precision)) precision = 2;
    var width = axisWidthPx(values, {
      mode: mode, base: o.base, precision: precision, font: o.font, minMove: o.minMove,
    });
    var spec = {
      width: width,
      margin: o.margin == null ? 6 : o.margin,
      align: "left",
      overflow: "truncate",
      fontSize: o.fontSize == null ? 11 : o.fontSize,
      formatter: function (v) {
        return formatValue(v, {
          mode: mode, base: o.base, precision: precision, minMove: o.minMove,
        });
      },
    };
    if (o.color) spec.color = o.color;
    return spec;
  }

  // 主图价格轴（含「只画水平网格线」与 1-2-5 刻度密度）
  function priceAxisSpec(o) {
    o = o || {};
    var values = o.values || [];
    var mode = modeOf(o.mode);
    var log = mode === 1 && _allPositive(values);
    var precision = o.precision == null
      ? autoPrecision(o.minMove == null ? DEFAULT_MIN_MOVE : o.minMove, values)
      : Math.max(0, Math.floor(Number(o.precision)));
    var ax = {
      type: log ? "log" : "value",
      gridIndex: o.gridIndex == null ? 0 : o.gridIndex,
      position: "right",
      scale: !log,
      show: o.show !== false,
      splitNumber: o.splitNumber == null ? 5 : o.splitNumber,
      axisLabel: axisLabelSpec(values, {
        mode: log ? 0 : mode, base: o.base, precision: precision,
        font: o.font, color: o.labelColor, fontSize: o.labelFontSize,
      }),
      axisTick: { inside: true, length: 3, lineStyle: { color: o.tickColor } },
      axisLine: { lineStyle: { color: o.axisColor } },
      // 只画水平线，不画竖线（§4 规格表）
      splitLine: { show: true, lineStyle: { color: o.splitColor || "#E0E6F1", width: 1 } },
    };
    if (o.name) {
      ax.name = o.name;
      ax.nameTextStyle = o.nameTextStyle || { fontSize: 10 };
    }
    return ax;
  }

  function _allPositive(values) {
    var ok = false;
    for (var i = 0; i < (values || []).length; i++) {
      var n = Number(values[i]);
      if (!isFinite(n)) continue;
      if (n <= 0) return false;
      ok = true;
    }
    return ok;
  }

  // 末价标签：贴在右轴、带背景块，随轴自动移动（markLine 而非自建图元）
  function lastPriceMarkLine(value, o) {
    o = o || {};
    var n = Number(value);
    var color = o.color || "#6750A4";
    return {
      silent: true,
      symbol: "none",
      animation: false,
      lineStyle: { color: color, width: 1, type: "dashed" },
      label: {
        show: true,
        position: "end",
        distance: o.distance == null ? 6 : o.distance,
        backgroundColor: color,
        borderColor: o.borderColor || color,
        borderWidth: 0,
        color: o.labelColor || "#FFFFFF",
        padding: [2, 4],
        borderRadius: 2,
        fontSize: 11,
        formatter: function () {
          return formatValue(n, {
            mode: o.mode, base: o.base, precision: o.precision,
            minMove: o.minMove == null ? DEFAULT_MIN_MOVE : o.minMove,
          });
        },
      },
      data: [{ yAxis: n }],
    };
  }

  // 十字光标：1px 虚线 + 价格/时间标签带背景块
  function crosshairSpec(o) {
    o = o || {};
    var c = o.color || "#8B7FBE";
    var bg = o.labelBg || "#6750A4";
    return {
      link: o.link || [{ xAxisIndex: "all" }],
      label: {
        backgroundColor: bg,
        borderColor: o.labelBorder || bg,
        borderWidth: 0,
        color: o.labelColor || "#FFFFFF",
        padding: [3, 5],
        borderRadius: 2,
        fontSize: 11,
      },
      lineStyle: { type: "dashed", width: 1, color: c },
      crossStyle: { type: "dashed", width: 1, color: c },
    };
  }

  // 图例：左上单行，圆点 + 名称 + 当前值，可点击切换
  function legendSpec(o) {
    o = o || {};
    // textStyle.color 只在调用方显式给值时写入：传 undefined 会覆盖 ECharts 的
    // 主题默认色，导致图例文字 fillStyle 失效、整段不可见
    var textStyle = { fontSize: o.fontSize == null ? 11 : o.fontSize };
    if (o.textColor) textStyle.color = o.textColor;
    var spec = {
      data: o.data || [],
      top: o.top == null ? 0 : o.top,
      left: o.left == null ? 0 : o.left,
      icon: "circle",
      itemWidth: 8,
      itemHeight: 8,
      itemGap: o.itemGap == null ? 12 : o.itemGap,
      textStyle: textStyle,
      formatter: typeof o.formatter === "function" ? o.formatter : undefined,
    };
    if (o.selected) spec.selected = o.selected;
    if (o.type) spec.type = o.type;
    return spec;
  }

  // 类别轴：默认不画竖网格线（§4 规格表）；可用 extra 覆盖
  function categoryAxisSpec(o) {
    o = o || {};
    var ax = {
      type: "category",
      data: o.data || [],
      gridIndex: o.gridIndex == null ? 0 : o.gridIndex,
      splitLine: { show: false },
    };
    if (o.axisLabel) ax.axisLabel = o.axisLabel;
    if (o.extra) Object.keys(o.extra).forEach(function (k) { ax[k] = o.extra[k]; });
    return ax;
  }

  /* ---------------- 模式持久化 ---------------- */

  function readMode() {
    try {
      var v = (typeof localStorage !== "undefined") && localStorage.getItem(MODE_LS_KEY);
      return modeOf(v);
    } catch (e) { return 0; }
  }
  function setMode(v) {
    var m = modeOf(v);
    try {
      if (typeof localStorage !== "undefined") localStorage.setItem(MODE_LS_KEY, String(m));
    } catch (e) { /* 隐私模式：仅本次会话生效 */ }
    return m;
  }
  function nextMode(v) { return (modeOf(v) + 1) % MODES.length; }

  window.QREPriceScale = {
    MODES: MODES,
    MODE_LS_KEY: MODE_LS_KEY,
    DEFAULT_MIN_MOVE: DEFAULT_MIN_MOVE,
    modeOf: modeOf,
    modeMeta: modeMeta,
    nextMode: nextMode,
    precisionFromMinMove: precisionFromMinMove,
    decimalsOf: decimalsOf,
    inferPrecision: inferPrecision,
    autoPrecision: autoPrecision,
    niceStep: niceStep,
    niceTicks: niceTicks,
    formatValue: formatValue,
    measureTextPx: measureTextPx,
    labelsWidthPx: labelsWidthPx,
    candidateLabels: candidateLabels,
    axisWidthPx: axisWidthPx,
    axisLabelSpec: axisLabelSpec,
    priceAxisSpec: priceAxisSpec,
    lastPriceMarkLine: lastPriceMarkLine,
    crosshairSpec: crosshairSpec,
    legendSpec: legendSpec,
    categoryAxisSpec: categoryAxisSpec,
    readMode: readMode,
    setMode: setMode,
  };
})();
