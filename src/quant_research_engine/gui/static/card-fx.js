/* QRE-SAAS-CARD-FX（CR-2026-10-28）：全站卡片「磨砂玻璃 + 光标跟随光斑 + 轻微 3D 倾斜」。
 *
 * 设计约束（与 lab-theme.css 的同名注释一一对应）：
 * 1. 性能：全站只有一个 pointermove 委托监听（挂在 document），rAF 节流；
 *    每帧只写当前悬停卡的 CSS 自定义属性 --mx/--my（光斑位置 %）与 --rx/--ry
 *    （倾斜量，度），不做逐卡监听、不逐帧写多个样式属性。
 * 2. 图表卡不倾斜：含 <canvas> 的卡片（收益曲线 / K 线 / 热力图 / 重播）只加光斑，
 *    不挂 transform——rotateX/rotateY 会让画布发糊、文字发虚。
 * 3. 嵌套卡不重复：closest 命中内层卡时向上爬到最外层玻璃卡，只驱动最外层，
 *    避免 transform 叠加与光斑重叠（小卡自有 hover 位移，也不参与倾斜）。
 * 4. 跟手与复原：指针移动中加 .fx-live 关掉 transition（跟手）；移出时移除
 *    .fx-live 并把变量归零，transition 生效 → 平滑复原。
 * 5. reduced-motion：直接跳过，不写任何变量，CSS 侧同时隐藏光斑与过渡。
 */
(function () {
  'use strict';

  var TILT_MAX = 4;                                       // 倾斜上限（度），CSS clamp 同步兜底
  var CARD_SEL = '.card,.chart-box,.panel,.big-link,.metric,.metric-card,.entry-card';
  // 可倾斜卡族（CR-2026-10-28 收窄）：只对「并列小卡」与「新建策略三入口」倾斜——
  // .metric-card（总收益率/年化收益/超额收益/夏普、交易磨损五联卡、FRM 风险卡、
  // 区间策略收益条）与 .entry-card。装小卡的大卡（.card/.chart-box/.panel/.big-link）
  // 与图表卡恒不倾斜：大卡内是 ECharts/LWC 画布，rotateX/rotateY 会让画布发糊、
  // 文字发虚，且用户反馈「倾斜不应作用于所有 div」。CSS 侧同源规则双保险。
  var TILT_SEL = '.metric-card,.entry-card';   // 并列小卡 + 新建策略三入口

  function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

  /* 指针在卡片内的位置 → 光斑中心（百分比，越界钳制） */
  function spot(width, height, x, y) {
    return {
      mx: clamp(width > 0 ? (x / width) * 100 : 50, 0, 100),
      my: clamp(height > 0 ? (y / height) * 100 : 50, 0, 100),
    };
  }

  /* 指针在卡片内的位置 → 倾斜量（度）。光标所在边向内压（vanilla-tilt 同款手感）：
     右侧 → rotateY 正（右缘后退），下侧 → rotateX 负（下缘后退）。中心为 0，
     四角取到 ±TILT_MAX 极值，任何输入都钳制在 ±4 内。 */
  function tilt(width, height, x, y) {
    var nx = clamp(width > 0 ? (x / width) * 2 - 1 : 0, -1, 1);
    var ny = clamp(height > 0 ? (y / height) * 2 - 1 : 0, -1, 1);
    return {
      rx: clamp(nx * TILT_MAX, -TILT_MAX, TILT_MAX),
      ry: clamp(-ny * TILT_MAX, -TILT_MAX, TILT_MAX),
    };
  }

  /* 嵌套卡：向上爬到最外层玻璃卡（内层不重复驱动） */
  function outermost(card) {
    var cur = card;
    while (cur && cur.parentElement && cur.parentElement.closest) {
      var parent = cur.parentElement.closest(CARD_SEL);
      if (!parent) break;
      cur = parent;
    }
    return cur;
  }

  /* 可倾斜判定：不在可倾斜卡族内，或卡内已有 canvas（图表卡）→ 不挂 transform */
  function eligibleForTilt(card) {
    if (!card || !card.matches || !card.matches(TILT_SEL)) return false;
    return !card.querySelector('canvas');
  }

  function prefersReduced() {
    return !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  }

  /* state.card  = 光斑宿主（最外层玻璃卡；嵌套内层不重复亮）
     state.tilt  = 倾斜宿主（光标下的可倾斜小卡；与外层可能是同一个元素）
     两者解耦（CR-2026-10-28 用户反馈）：小卡包在 .chart-box 里时，光斑应由大卡
     统一负责（否则小卡的光斑会被大卡的玻璃底色截断），而倾斜必须落在小卡上——
     此前 outermost() 把两者都提到最外层，导致 .chart-box 内的 .metric-card
     （交易磨损五联卡、区间策略收益条、FRM 风险卡）既不亮也不倾。 */
  var state = { card: null, tilt: null, rect: null, trect: null, raf: 0, event: null,
                mx: '', my: '', rx: '', ry: '' };

  function reset() {
    var card = state.card, tilt = state.tilt;
    state.card = null; state.tilt = null;
    state.rect = null; state.trect = null;
    state.mx = state.my = state.rx = state.ry = '';
    if (tilt) {
      // 先恢复 transition 再归零变量：同一帧内「after」样式带 transition → 平滑复原
      tilt.classList.remove('fx-live');
      tilt.style.setProperty('--rx', '0');
      tilt.style.setProperty('--ry', '0');
      tilt.classList.remove('fx-tilt');
    }
    if (card) card.classList.remove('fx-on');
  }

  function enter(card, tiltEl) {
    reset();
    if (!card) return;
    state.card = card;
    state.rect = card.getBoundingClientRect();
    card.classList.add('fx-on');
    var tiltable = !!tiltEl && eligibleForTilt(tiltEl);
    if (tiltable) {
      state.tilt = tiltEl;
      state.trect = tiltEl.getBoundingClientRect();
      tiltEl.classList.add('fx-tilt', 'fx-live');
    }
  }

  function flush() {
    state.raf = 0;
    var e = state.event;
    state.event = null;
    if (!e) return;
    if (prefersReduced()) { reset(); return; }
    var target = e.target;
    // 光斑宿主：最外层玻璃卡（嵌套内层不重复亮）
    var hit = (target && target.closest) ? target.closest(CARD_SEL) : null;
    var card = hit ? outermost(hit) : null;
    // 倾斜宿主：光标正下方那张可倾斜小卡（不向上爬——爬上去就落到大卡上了）
    var tiltEl = (hit && hit.matches && hit.matches(TILT_SEL)) ? hit : null;
    if (card !== state.card || tiltEl !== state.tilt) enter(card, tiltEl);
    var el = state.card;
    if (!el) return;
    if (!state.rect) state.rect = el.getBoundingClientRect();
    var r = state.rect;
    var x = e.clientX - r.left;
    var y = e.clientY - r.top;
    var s = spot(r.width, r.height, x, y);
    // 只在取值变化时写属性：重复写相同值会白触发一次样式失效与重绘
    var mx = s.mx.toFixed(2) + '%';
    var my = s.my.toFixed(2) + '%';
    if (mx !== state.mx) { el.style.setProperty('--mx', mx); state.mx = mx; }
    if (my !== state.my) { el.style.setProperty('--my', my); state.my = my; }
    var t = state.tilt;
    if (t) {
      if (!state.trect) state.trect = t.getBoundingClientRect();
      var tr = state.trect;
      var ti = tilt(tr.width, tr.height, e.clientX - tr.left, e.clientY - tr.top);
      var rx = ti.rx.toFixed(2);
      var ry = ti.ry.toFixed(2);
      if (rx !== state.rx) { t.style.setProperty('--rx', rx); state.rx = rx; }
      if (ry !== state.ry) { t.style.setProperty('--ry', ry); state.ry = ry; }
    }
  }

  window.QRECardFx = {
    TILT_MAX: TILT_MAX,
    CARD_SEL: CARD_SEL,
    TILT_SEL: TILT_SEL,
    clamp: clamp,
    spot: spot,
    tilt: tilt,
    outermost: outermost,
    eligibleForTilt: eligibleForTilt,
  };

  if (typeof document === 'undefined' || !document.addEventListener) return;

  document.addEventListener('pointermove', function (e) {
    state.event = e;
    if (state.raf) return;
    state.raf = requestAnimationFrame(flush);
  }, { passive: true });

  // 指针离开文档 / 窗口失焦 / 触摸结束：立即复原
  document.addEventListener('pointerleave', reset);
  document.addEventListener('pointerup', reset);
  document.addEventListener('pointercancel', reset);
  window.addEventListener('blur', reset);
  // 滚动或缩放后卡片几何变化，缓存矩形作废（下一帧重读）
  window.addEventListener('scroll', function () { state.rect = null; }, { passive: true });
  window.addEventListener('resize', function () { state.rect = null; }, { passive: true });
})();
