/* QRE-SAAS-HELP-NAV-V2（CR-2026-10-28，V2 竞稿）
   使用说明页侧边栏的玻璃胶囊当前项指示器：单个绝对定位元素在 .help-jump 内滑动。

   与 V1 的差异（详见 CR 文内「V2 竞稿」节）：
   1. 位移不再手写 5 段 WAAPI 关键帧，改为 rAF 下的弹簧数值积分（半隐式欧拉）：
      角速度恒定、阻尼比随移动距离自适应，过冲量因此落在 3~6px 且不随距离暴涨；
      连点中断时从当前速度续滑，不会跳帧重来。
   2. 拉伸量由**速度在移动方向上的投影**直接导出（|投影|/VEL_REF 归一）：朝目标飞
      是拉伸，过冲回冲时投影转负、形变翻成压扁——「移动中拉长 / 到位回弹」是同一条
      物理量的两个相位，不是编排好的两帧。并按运动主轴做体积补偿（主轴形变、垂直
      主轴反向收窄），窄屏双列的水平移动方向与形变终于一致。
   3. 到位那一下另有一条闭式阻尼振荡（sin·e^{-ζωt}）补压扁：相位锁定在**实测的
      穿过目标时刻**，因此永远和胶囊真正落位对齐；幅度按移动距离给，短距移动也有
      清晰回弹，长距压得更狠，并自然带出一次小回冲。
   4. transform-origin 固定 center：体积补偿绕质心对称，不随方向切换。
   5. 首次出场用同一条闭式阶跃响应从 0.82 弹到 1，配合 opacity 过渡，不是硬跳。
   6. 滚动监听改 rAF 节流，避免每个 scroll 事件都强制布局。 */
(function () {
  'use strict';

  /* 位移弹簧：角速度恒定为 12.25 rad/s（时长稳定），阻尼比随移动距离在 0.62→0.80
     之间过渡——长距离更阻尼避免拉皮，短距离轻阻尼让回冲仍然可感知。 */
  var MOVE_OMEGA = 150;
  var MOVE_ZETA_NEAR = 0.62;   /* ≤60px 短距 */
  var MOVE_ZETA_FAR = 0.80;    /* ≥300px 长距 */
  var MOVE_ZETA_RANGE = 300;
  /* 到位压扁振荡：ω=40 rad/s（周期 166ms，首个极值在 41ms），ζ=0.32 保留一次回冲 */
  var BOUNCE = {stiffness: 1600, damping: 25.6, mass: 1};
  var IMPACT_MAX = 0.16;       /* 到位最大压扁量（2026-10-28 加强：与原 0.10 相比，
                               42px 胶囊的压扁从 4.2px 提到 6.7px，回弹可见） */
  var IMPACT_MIN = 0.5;        /* 轻落地也至少给一半幅度 */
  var IMPACT_MIN_DELTA = 12;   /* 位移小于该值不激发压扁，避免微动抖动 */
  var IMPACT_RANGE = 160;      /* 移动多远算「重落地」（原 200 时相邻项只吃 0.5 下限） */
  /* 首次出场：0.82 → 1，ζ=0.5 给一次 3% 的小过冲 */
  var ENTRANCE = {stiffness: 1156, damping: 34, mass: 1};
  var ENTRANCE_FROM = 0.82;
  var VEL_REF = 600;           /* px/s：达到该速度时拉伸拉满。
                               2026-10-28 用户反馈「没看见拉长特效」：原值 1500 而
                               实测峰值速度约 1000px/s，只能吃到 8% 形变（42px 胶囊
                               约 3.4px），肉眼不可见。改为 600 后典型速度即饱和。 */
  var DEFORM_MAX = 0.28;       /* 沿主轴的最大形变量（拉伸或压扁）。
                               2026-10-28 由 0.12 加强到 0.28：42px 胶囊拉长到 53.8px
                               （约 11.8px），是肉眼清晰可辨的量级。 */
  var SQUEEZE = 0.26;          /* 垂直主轴的体积补偿收窄比例（原 0.34 收窄过头，
                               抵消了拉长的视觉；0.26 保留体积感又不掩盖形变） */
  var MAX_STEP = 1 / 240;      /* 积分子步上限，大 dt 下仍稳定 */
  var FRAME_CAP = 0.064;       /* 单帧 dt 上限（切后台 / 掉帧） */
  var SETTLE_MS = 1500;        /* 兜底：超时直接吸附到目标 */
  var POS_EPS = 0.25, VEL_EPS = 2.5;
  var SCALE_EPS = 0.002;
  var TOP_OFFSET = 76;

  function clamp(value, lo, hi) {
    return value < lo ? lo : (value > hi ? hi : value);
  }

  function round(value, digits) {
    var factor = Math.pow(10, digits);
    return Math.round(value * factor) / factor;
  }

  function omegaOf(params) {
    return Math.sqrt(params.stiffness / params.mass);
  }

  function zetaOf(params) {
    return params.damping / (2 * Math.sqrt(params.stiffness * params.mass));
  }

  /* 纯函数：按位移量配弹簧参数（阻尼比自适应，角速度恒定）。 */
  function moveParams(distance) {
    var t = clamp(Math.abs(distance) / MOVE_ZETA_RANGE, 0, 1);
    var zeta = MOVE_ZETA_NEAR + (MOVE_ZETA_FAR - MOVE_ZETA_NEAR) * t;
    return {
      stiffness: MOVE_OMEGA,
      damping: 2 * zeta * Math.sqrt(MOVE_OMEGA),
      mass: 1
    };
  }

  /* 纯函数：半隐式（symplectic）欧拉推进一步，内部按 MAX_STEP 细分保证稳定。 */
  function springStep(value, velocity, target, params, dt) {
    var steps = Math.max(1, Math.ceil(dt / MAX_STEP));
    var h = dt / steps;
    var x = value;
    var v = velocity;
    for (var i = 0; i < steps; i++) {
      var a = (-params.stiffness * (x - target) - params.damping * v) / params.mass;
      v += a * h;
      x += v * h;
    }
    return {value: x, velocity: v};
  }

  /* 纯函数：闭式阻尼振荡，t<0 返回 0。从 0 起振（sin 起步），首个极值在
     π/(2ω_d)，之后按 e^{-ζωt} 衰减并自然带出一次反向回冲。 */
  function oscillate(t, amp, params) {
    if (!(t > 0) || !amp) return 0;
    var omega = omegaOf(params);
    var zeta = zetaOf(params);
    var wd = omega * Math.sqrt(Math.max(0, 1 - zeta * zeta));
    return amp * Math.sin(wd * t) * Math.exp(-zeta * omega * t);
  }

  /* 纯函数：闭式欠阻尼阶跃响应，t=0 时为 1、t→∞ 时收敛到 0（ζ<1 会过冲再收回）。 */
  function stepResponse(t, params) {
    if (!(t > 0)) return 1;
    var omega = omegaOf(params);
    var zeta = zetaOf(params);
    var wd = omega * Math.sqrt(Math.max(0, 1 - zeta * zeta));
    var decay = Math.exp(-zeta * omega * t);
    if (wd <= 0) return decay * (1 + zeta * omega * t);
    var ratio = zeta / Math.sqrt(Math.max(1e-9, 1 - zeta * zeta));
    return decay * (Math.cos(wd * t) + ratio * Math.sin(wd * t));
  }

  /* 纯函数：到位压扁量。按移动距离给（有下限、有上限），与速度投影叠加。 */
  function impactScale(distance, max) {
    var cap = typeof max === 'number' ? max : IMPACT_MAX;
    return -clamp(Math.abs(distance) / IMPACT_RANGE, IMPACT_MIN, 1) * cap;
  }

  /* 纯函数：飞行中的形变量。取速度在「移动方向」上的投影——朝目标飞是拉伸（正），
     到位后过冲回冲时投影转负、形变翻成压扁。幅度按 |投影|/VEL_REF 归一后截断。 */
  function deformScale(projectedVelocity, max) {
    var cap = typeof max === 'number' ? max : DEFORM_MAX;
    return clamp(projectedVelocity / VEL_REF, -1, 1) * cap;
  }

  /* 纯函数：形变量的绝对值（速度越高形变越大，与方向无关）。 */
  function stretchScale(velocity, max) {
    return Math.abs(deformScale(velocity, max));
  }

  /* 纯函数：位移主轴。竖向位移占优返回 'y'，否则 'x'（窄屏双列走 'x'）。 */
  function axisFor(dx, dy) {
    return Math.abs(dy) >= Math.abs(dx) ? 'y' : 'x';
  }

  /* 纯函数：沿主轴的形变量 + 体积补偿后的缩放对。静止时 (1, 1)。
     stretch ≥ 0（飞行中拉长），bounce ≤ 0（到位压扁），两者都沿主轴。 */
  function scaleFor(axis, projectedVelocity, bounce, max) {
    var along = deformScale(projectedVelocity, max) + (bounce || 0);
    var across = -along * SQUEEZE;
    var sx = 1;
    var sy = 1;
    if (axis === 'y') {
      sy = 1 + along;
      sx = 1 + across;
    } else {
      sx = 1 + along;
      sy = 1 + across;
    }
    return {sx: sx, sy: sy, axis: axis, along: along, across: across};
  }

  /* 纯函数：本帧是否穿过目标（用于到位压扁的激发判定）。 */
  function crossedTarget(before, after, goal) {
    if (before === after) return false;
    return (before < goal && after >= goal) || (before > goal && after <= goal);
  }

  function transformFor(geometry) {
    return 'translate3d(' + round(geometry.x, 2) + 'px,' + round(geometry.y, 2) + 'px,0)';
  }

  function now() {
    return window.performance && window.performance.now
      ? function () { return window.performance.now(); }
      : function () { return Date.now(); };
  }

  function init() {
    var nav = document.querySelector('.help-jump');
    if (!nav) return;

    var links = Array.prototype.slice.call(nav.querySelectorAll('a[href^="#"]'));
    var targets = links.map(function (link) {
      return document.getElementById(link.getAttribute('href').slice(1));
    });
    if (!links.length || !targets.some(Boolean)) return;

    var pill = nav.querySelector('.help-pill');
    if (!pill) {
      pill = document.createElement('span');
      pill.className = 'help-pill';
      nav.appendChild(pill);
    }
    pill.setAttribute('aria-hidden', 'true');

    var clock = now();
    var raf = window.requestAnimationFrame
      ? function (fn) {
          return window.requestAnimationFrame(function (ts) { fn(ts || clock()); });
        }
      : function (fn) { return setTimeout(function () { fn(clock()); }, 16); };
    var cancelRaf = window.cancelAnimationFrame
      ? function (id) { window.cancelAnimationFrame(id); }
      : function (id) { clearTimeout(id); };

    var reducedMotion = function () {
      return !!(window.matchMedia &&
        window.matchMedia('(prefers-reduced-motion: reduce)').matches);
    };

    /* 位移走弹簧积分；缩放由速度投影 + 到位振荡 + 出场响应直接算出，不再套弹簧，
       否则压扁会被跟随弹簧的延迟吃光。 */
    var state = {x: 0, y: 0, vx: 0, vy: 0, sx: 1, sy: 1};
    var target = {x: 0, y: 0, width: 0, height: 0};
    var axis = 'y';
    var moveSign = 1;
    var move = moveParams(0);
    var moveDelta = 0;
    var bounceAmp = 0;
    var bounceAt = -1;
    var bouncePending = false;
    var entranceFrom = 0;
    var entranceAt = -1;
    var placed = false;
    var activeIndex = -1;
    var rafId = 0;
    var lastTs = 0;
    var settleStart = 0;
    var visible = links.map(function () { return false; });
    var lockedIndex = -1;
    var lockTimer = null;
    var scrollScheduled = false;
    var resizeTimer = null;
    var ready = false;

    function geometryFor(index) {
      var el = links[index];
      return {
        x: el.offsetLeft, y: el.offsetTop,
        width: el.offsetWidth, height: el.offsetHeight
      };
    }

    function sameGeometry(a, b) {
      return a.x === b.x && a.y === b.y && a.width === b.width && a.height === b.height;
    }

    /* 形变：速度投影（拉伸/回冲压扁）+ 到位振荡 + 出场响应，一次算清并落盘 */
    function deform(nowMs) {
      var projected = (axis === 'y' ? state.vy : state.vx) * moveSign;
      var bounce = bounceAmp ? oscillate((nowMs - bounceAt) / 1000, bounceAmp, BOUNCE) : 0;
      var entrance = entranceFrom
        ? 1 + (entranceFrom - 1) * stepResponse((nowMs - entranceAt) / 1000, ENTRANCE)
        : 1;
      var pair = scaleFor(axis, projected, bounce);
      state.sx = pair.sx * entrance;
      state.sy = pair.sy * entrance;
    }

    function paint(nowMs) {
      deform(nowMs);
      pill.style.width = target.width + 'px';
      pill.style.height = target.height + 'px';
      pill.style.transform = transformFor({x: state.x, y: state.y}) +
        ' scaleX(' + round(state.sx, 4) + ') scaleY(' + round(state.sy, 4) + ')';
    }

    function atRest() {
      return Math.abs(state.x - target.x) < POS_EPS &&
             Math.abs(state.y - target.y) < POS_EPS &&
             Math.abs(state.vx) < VEL_EPS && Math.abs(state.vy) < VEL_EPS &&
             Math.abs(state.sx - 1) < SCALE_EPS && Math.abs(state.sy - 1) < SCALE_EPS;
    }

    function snap() {
      state.x = target.x;
      state.y = target.y;
      state.vx = 0;
      state.vy = 0;
      bounceAmp = 0;
      bounceAt = -1;
      bouncePending = false;
      entranceFrom = 0;
      entranceAt = -1;
    }

    function stopLoop() {
      if (rafId) { cancelRaf(rafId); rafId = 0; }
      lastTs = 0;
    }

    /* 一帧：位移弹簧推进；穿过目标那一帧记下时刻与压扁幅度（相位锁定真实落位） */
    function advance(dt, nowMs) {
      var beforeY = state.y;
      var beforeX = state.x;

      var moved = springStep(state.x, state.vx, target.x, move, dt);
      state.x = moved.value;
      state.vx = moved.velocity;
      moved = springStep(state.y, state.vy, target.y, move, dt);
      state.y = moved.value;
      state.vy = moved.velocity;

      if (bouncePending) {
        var hit = axis === 'y'
          ? crossedTarget(beforeY, state.y, target.y)
          : crossedTarget(beforeX, state.x, target.x);
        if (hit) {
          bounceAmp = impactScale(moveDelta);
          bounceAt = nowMs;
          bouncePending = false;
        }
      }
    }

    function tick(ts) {
      rafId = 0;
      if (!lastTs) lastTs = ts;
      var dt = (ts - lastTs) / 1000;
      lastTs = ts;
      if (!(dt > 0)) dt = 1 / 60;
      if (dt > FRAME_CAP) dt = FRAME_CAP;

      advance(dt, ts);
      paint(ts);
      if (atRest() || (settleStart && ts - settleStart > SETTLE_MS)) {
        snap();
        paint(ts);
        stopLoop();
        return;
      }
      rafId = raf(tick);
    }

    function startLoop() {
      if (rafId) return;
      if (reducedMotion()) {
        snap();
        paint(clock());
        return;
      }
      settleStart = clock();
      lastTs = 0;
      rafId = raf(tick);
    }

    function moveTo(geometry, options) {
      options = options || {};
      target = {x: geometry.x, y: geometry.y, width: geometry.width, height: geometry.height};
      pill.classList.add('is-on');

      if (!placed) {
        /* 首次出场：落在目标位，缩放从 ENTRANCE_FROM 弹到 1 */
        state.x = target.x;
        state.y = target.y;
        state.vx = 0;
        state.vy = 0;
        axis = 'y';
        moveSign = 1;
        move = moveParams(0);
        moveDelta = 0;
        bouncePending = false;
        if (reducedMotion()) {
          snap();
          paint(clock());
        } else {
          bounceAmp = 0;
          bounceAt = -1;
          entranceFrom = ENTRANCE_FROM;
          entranceAt = clock();
          paint(clock());
          startLoop();
        }
        placed = true;
        return;
      }

      bounceAmp = 0;
      bounceAt = -1;
      bouncePending = false;
      entranceFrom = 0;
      entranceAt = -1;

      if (options.instant || reducedMotion()) {
        snap();
        stopLoop();
        paint(clock());
        return;
      }

      var dx = target.x - state.x;
      var dy = target.y - state.y;
      axis = axisFor(dx, dy);
      moveSign = axis === 'y' ? (dy >= 0 ? 1 : -1) : (dx >= 0 ? 1 : -1);
      moveDelta = Math.abs(dx) + Math.abs(dy);
      move = moveParams(moveDelta);
      bouncePending = moveDelta > IMPACT_MIN_DELTA;
      paint(clock());
      startLoop();
    }

    function setActive(index, options) {
      if (index < 0 || index >= links.length) return;
      var previous = activeIndex;
      links.forEach(function (link, i) {
        if (i === index) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
      activeIndex = index;
      var geometry = geometryFor(index);
      if (previous === index && placed && sameGeometry(geometry, target)) return;
      moveTo(geometry, options);
    }

    function fallbackIndex() {
      var index = 0;
      for (var i = 0; i < targets.length; i++) {
        var el = targets[i];
        if (el && el.getBoundingClientRect().top - TOP_OFFSET <= 8) index = i;
      }
      return index;
    }

    function releaseLock() {
      /* 点击刚结束：若被点那一节仍在可视区内就保持它。否则滚到页面最底部时
         （末节标题被 scroll-margin 顶到阅读线以下、前一节仍压在阅读线上）
         高亮会在锁定结束后跳回上一节，看起来像点错了。 */
      var preferred = lockedIndex;
      lockedIndex = -1;
      lockTimer = null;
      sync(preferred);
    }

    function sync(preferred) {
      /* 点击锁定期间不响应 IO：平滑滚动途中各节不断进出可视区，若不锁会让胶囊
         目标被反复改写，出现来回抽动。 */
      if (!ready || lockedIndex !== -1) return;
      var index = -1;
      for (var i = 0; i < visible.length; i++) {
        if (visible[i]) { index = i; break; }
      }
      if (index === -1) index = fallbackIndex();
      if (preferred >= 0 && preferred < visible.length && visible[preferred]) {
        index = preferred;
      }
      setActive(index);
    }

    if (window.IntersectionObserver) {
      var observer = new window.IntersectionObserver(function (entries) {
        entries.forEach(function (entry) {
          var index = targets.indexOf(entry.target);
          if (index !== -1) visible[index] = entry.isIntersecting;
        });
        sync(-1);
      }, {rootMargin: '-76px 0px -58% 0px', threshold: 0});
      targets.forEach(function (section) {
        if (section) observer.observe(section);
      });
    }

    links.forEach(function (link, index) {
      link.addEventListener('click', function (event) {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (typeof event.button === 'number' && event.button !== 0) return;
        var id = link.getAttribute('href').slice(1);
        var el = document.getElementById(id);
        if (!el) return;
        event.preventDefault();
        lockedIndex = index;
        setActive(index);
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, '', '#' + id);
        }
        el.scrollIntoView({behavior: reducedMotion() ? 'auto' : 'smooth', block: 'start'});
        if (lockTimer) clearTimeout(lockTimer);
        lockTimer = setTimeout(releaseLock, 1500);
      });
    });

    window.addEventListener('scroll', function () {
      if (lockedIndex !== -1) {
        if (lockTimer) clearTimeout(lockTimer);
        lockTimer = setTimeout(releaseLock, 160);
        return;
      }
      if (scrollScheduled) return;
      scrollScheduled = true;
      raf(function () {
        scrollScheduled = false;
        sync(-1);
      });
    }, {passive: true});

    window.addEventListener('resize', function () {
      if (resizeTimer) clearTimeout(resizeTimer);
      resizeTimer = setTimeout(function () {
        if (activeIndex < 0) return;
        moveTo(geometryFor(activeIndex), {instant: true});
      }, 120);
    });

    if (document.fonts && document.fonts.ready && document.fonts.ready.then) {
      document.fonts.ready.then(function () {
        if (activeIndex < 0) return;
        moveTo(geometryFor(activeIndex), {instant: true});
      });
    }

    var initial = -1;
    var hashed = false;
    if (window.location && window.location.hash && window.location.hash.length > 1) {
      hashed = true;
      var hash = window.location.hash;
      for (var i = 0; i < links.length; i++) {
        if (links[i].getAttribute('href') === hash) { initial = i; break; }
      }
    }
    if (initial === -1) initial = fallbackIndex();
    setActive(initial);
    if (hashed) {
      /* 带 #hash 打开：锁定一段时间，避免浏览器原生回跳被初始 IO 回调覆盖 */
      lockedIndex = initial;
      if (lockTimer) clearTimeout(lockTimer);
      lockTimer = setTimeout(releaseLock, 1500);
    }
    setTimeout(function () { ready = true; }, 120);
  }

  window.QREHelpNav = {
    moveParams: moveParams,
    springStep: springStep,
    oscillate: oscillate,
    stepResponse: stepResponse,
    impactScale: impactScale,
    deformScale: deformScale,
    stretchScale: stretchScale,
    axisFor: axisFor,
    scaleFor: scaleFor,
    crossedTarget: crossedTarget,
    transformFor: transformFor,
    init: init
  };

  if (typeof document !== 'undefined' && document) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', init);
    } else {
      init();
    }
  }
})();
