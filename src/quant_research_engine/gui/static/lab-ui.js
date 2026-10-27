/* QRE Lab 交互组件（仅 8081 lab 版模板引用）
   PCB 排线连接层 / 自绘日历（最大可选日 = 数据最近交易日）/ 预览栏
   规范：docs/agent/12_UI_STYLE_GUIDE.md */
(function () {
  "use strict";
  var LabUI = {};

  /* ==================== PCB 排线 ==================== */
  function pcbPath(x0, x1) {
    var y0 = 6, y1 = 50, mid1 = y0 + 12, mid2 = y1 - 12, dx = x1 - x0, ad = Math.abs(dx);
    if (ad < 1) return "M" + x0.toFixed(1) + "," + y0 + "V" + y1;
    if (ad <= (mid2 - mid1)) return "M" + x0.toFixed(1) + "," + y0 + "V" + mid1 + "L" + x1.toFixed(1) + "," + (mid1 + ad) + "V" + y1;
    var dir = dx > 0 ? 1 : -1;
    return "M" + x0.toFixed(1) + "," + y0 + "V" + mid1 + "H" + (x0 + dir * (ad - (mid2 - mid1))).toFixed(1) + "L" + x1.toFixed(1) + "," + mid2 + "V" + y1;
  }
  /* stage: 连接层容器（内含 svg）；cards: 三张入口卡（按序对应 data-entry-tab） */
  LabUI.layoutPCB = function (stage, cards) {
    if (!stage || !cards.length) return;
    var svg = stage.querySelector("svg");
    var sr = stage.getBoundingClientRect();
    if (sr.width < 10) return;
    var tx = sr.width / 2, html = "";
    cards.forEach(function (card) {
      var cr = card.getBoundingClientRect();
      var x0 = cr.left + cr.width / 2 - sr.left;
      var d = pcbPath(x0, tx);
      html += '<g class="pcb-item' + (card.classList.contains("selected") ? " lit" : "") + '">'
        + '<path class="trace-base" d="' + d + '"/>'
        + '<path class="trace-pulse" d="' + d + '" pathLength="300"/>'
        + '<circle class="pcb-pad" cx="' + x0.toFixed(1) + '" cy="6" r="4"/></g>';
    });
    html += '<circle class="pcb-pad-panel" cx="' + tx.toFixed(1) + '" cy="50" r="6"/>'
      + '<circle class="pcb-pad-core" cx="' + tx.toFixed(1) + '" cy="50" r="2.4"/>';
    svg.innerHTML = html;
  };
  LabUI.energizePCB = function (stage, cards) {
    LabUI.layoutPCB(stage, cards);
    var lit = stage.querySelector(".pcb-item.lit"), pad = stage.querySelector(".pcb-pad-panel");
    if (lit) { lit.classList.add("energize"); setTimeout(function () { lit.classList.remove("energize"); }, 550); }
    if (pad) { pad.classList.add("flash"); setTimeout(function () { pad.classList.remove("flash"); }, 550); }
  };

  /* ==================== 日历（禁未来函数：maxDate 之后含今天全禁） ==================== */
  /* 年→月→日钻取：点头部年月标题进入年份九宫格（12 年/页）→ 选年进月份视图 → 选月回日视图；
     Esc / 再点标题返回上一级；年/月格子超出 [minDate, maxDate] 范围置灰禁点。 */
  function isoD(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function parseD(s) { var p = (s || "").split("-"); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  /* opts: {pop, startInput, endInput, maxDate:'YYYY-MM-DD', minDate?:'YYYY-MM-DD', onChange} */
  LabUI.attachCalendar = function (opts) {
    var pop = opts.pop, sIn = opts.startInput, eIn = opts.endInput;
    var MAXD = parseD(opts.maxDate) || new Date();
    var MIND = parseD(opts.minDate) || null;
    var calMode = "start", calYM = null, view = "date", yearBase = null;
    var MONTHS = ["1 月", "2 月", "3 月", "4 月", "5 月", "6 月", "7 月", "8 月", "9 月", "10 月", "11 月", "12 月"];
    function clamp() {
      var s = parseD(sIn.value), e = parseD(eIn.value);
      if (e && e > MAXD) eIn.value = isoD(MAXD);
      if (s && s > MAXD) sIn.value = isoD(MAXD);
      if (MIND) {
        if (e && e < MIND) eIn.value = isoD(MIND);
        if (s && s < MIND) sIn.value = isoD(MIND);
      }
    }
    function isOpen() { return pop.style.display !== "none" && pop.style.display !== ""; }
    function navBtn(dis) { return dis ? " disabled style='opacity:.35;cursor:default'" : ""; }
    function headHtml(title, noPrev, noNext) {
      return '<div class="cal-head"><button class="cal-nav" data-nav="-1"' + navBtn(noPrev) + '>‹</button>'
        + '<button class="cal-title" type="button">' + title + '</button>'
        + '<button class="cal-nav" data-nav="1"' + navBtn(noNext) + '>›</button></div>';
    }
    function render() {
      if (!calYM) { calYM = parseD(sIn.value) || MAXD; calYM = new Date(calYM.getFullYear(), calYM.getMonth(), 1); }
      var y = calYM.getFullYear(), m = calYM.getMonth();
      var s = parseD(sIn.value), e = parseD(eIn.value);
      var html;
      if (view === "year") {
        /* 年份视图：12 年/页九宫格 */
        if (yearBase === null) yearBase = Math.floor(y / 12) * 12;
        var maxY = MAXD.getFullYear(), minY = MIND ? MIND.getFullYear() : null;
        var noNextY = yearBase + 12 > maxY, noPrevY = minY !== null && yearBase - 12 + 11 < minY;
        html = headHtml(yearBase + " – " + (yearBase + 11) + " 年", noPrevY, noNextY);
        html += '<div class="cal-grid cal-grid-ym">';
        for (var yy = yearBase; yy < yearBase + 12; yy++) {
          var ydis = yy > maxY || (minY !== null && yy < minY);
          var ycls = "cal-cell cal-year" + ((s && s.getFullYear() === yy) || (e && e.getFullYear() === yy) ? " sel" : "");
          html += '<button class="' + ycls + '" data-y="' + yy + '"' + (ydis ? " disabled" : "") + ">" + yy + "</button>";
        }
        html += "</div>" + footHtml();
      } else if (view === "month") {
        /* 月份视图：当年 12 个月 */
        var noNextM = new Date(y + 1, 0, 1) > MAXD, noPrevM = MIND && new Date(y, 0, 1) <= new Date(MIND.getFullYear(), MIND.getMonth(), 1);
        html = headHtml(y + " 年", noPrevM, noNextM);
        html += '<div class="cal-grid cal-grid-ym">';
        for (var mm = 0; mm < 12; mm++) {
          var mdis = new Date(y, mm, 1) > MAXD || (MIND && new Date(y, mm + 1, 0) < MIND);
          var msel = (s && s.getFullYear() === y && s.getMonth() === mm) || (e && e.getFullYear() === y && e.getMonth() === mm);
          html += '<button class="cal-cell cal-month' + (msel ? " sel" : "") + '" data-m="' + mm + '"' + (mdis ? " disabled" : "") + ">" + MONTHS[mm] + "</button>";
        }
        html += "</div>" + footHtml();
      } else {
        /* 日视图（原有逻辑） */
        var pad = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
        var noNext = (new Date(y, m + 1, 1)) > MAXD;
        var noPrev = MIND && new Date(y, m, 1) <= new Date(MIND.getFullYear(), MIND.getMonth(), 1);
        html = headHtml(y + " 年 " + (m + 1) + " 月", noPrev, noNext);
        html += '<div class="cal-grid">' + "一二三四五六日".split("").map(function (d) { return '<span class="cal-dow">' + d + "</span>"; }).join("");
        for (var i = 0; i < pad; i++) html += '<span class="cal-day pad"></span>';
        for (var d = 1; d <= days; d++) {
          var dt = new Date(y, m, d), cls = "cal-day", dis = dt > MAXD || (MIND && dt < MIND);
          if (s && dt.getTime() === s.getTime()) cls += " sel";
          if (e && dt.getTime() === e.getTime()) cls += " sel";
          if (s && e && dt > s && dt < e) cls += " in-range";
          html += '<button class="' + cls + '" data-d="' + isoD(dt) + '"' + (dis ? " disabled" : "") + ">" + d + "</button>";
        }
        html += "</div>" + footHtml();
      }
      pop.innerHTML = html;
      pop.querySelectorAll(".cal-nav").forEach(function (b) {
        b.addEventListener("click", function (ev) {
          ev.stopPropagation(); if (b.disabled) return;
          var dir = +b.dataset.nav;
          if (view === "year") { yearBase += dir * 12; calYM = new Date(yearBase, 0, 1); }
          else if (view === "month") calYM = new Date(y + dir, m, 1);
          else calYM = new Date(y, m + dir, 1);
          render();
        });
      });
      pop.querySelector(".cal-title").addEventListener("click", function (ev) {
        ev.stopPropagation();
        /* 点标题钻取：日→年、月→年；年视图再点返回日视图 */
        if (view === "date") { view = "year"; yearBase = Math.floor(y / 12) * 12; }
        else if (view === "month") { view = "year"; yearBase = Math.floor(y / 12) * 12; }
        else view = "date";
        render();
      });
      pop.querySelectorAll(".cal-year[data-y]").forEach(function (b) {
        b.addEventListener("click", function (ev) {
          ev.stopPropagation(); if (b.disabled) return;
          calYM = new Date(+b.dataset.y, calYM.getMonth(), 1); view = "month"; render();
        });
      });
      pop.querySelectorAll(".cal-month[data-m]").forEach(function (b) {
        b.addEventListener("click", function (ev) {
          ev.stopPropagation(); if (b.disabled) return;
          calYM = new Date(y, +b.dataset.m, 1); view = "date"; render();
        });
      });
      pop.querySelectorAll(".cal-day[data-d]").forEach(function (b) {
        b.addEventListener("click", function (ev) {
          ev.stopPropagation();
          var d = b.dataset.d;
          if (calMode === "start") { sIn.value = d; var e2 = parseD(eIn.value); if (e2 && parseD(d) > e2) eIn.value = d; }
          else { eIn.value = d; var s2 = parseD(sIn.value); if (s2 && parseD(d) < s2) sIn.value = d; }
          render();
          if (opts.onChange) opts.onChange();
        });
      });
    }
    function footHtml() {
      return '<div class="cal-foot">数据截至 ' + opts.maxDate + '（最近交易日），之后日期不可选<br>正在选择：'
        + (calMode === "start" ? "起始日" : "截止日") + "（点输入框切换）"
        + (view !== "date" ? "<br>Esc 或点标题返回上级" : "") + "</div>";
    }
    /* 键盘：日历打开时 Esc 逐级返回（年→月→日→关闭） */
    document.addEventListener("keydown", function (ev) {
      if (ev.key !== "Escape" || !isOpen()) return;
      ev.stopPropagation();
      if (view === "year") { view = "month"; render(); }
      else if (view === "month") { view = "date"; render(); }
      else pop.style.display = "none";
    });
    [sIn, eIn].forEach(function (inp, idx) {
      inp.readOnly = true;
      inp.classList.add("date-input");
      inp.addEventListener("click", function (ev) {
        ev.stopPropagation();
        clamp(); if (opts.onChange) opts.onChange();
        var mode = idx === 0 ? "start" : "end";
        if (isOpen() && calMode === mode) { pop.style.display = "none"; return; }
        calMode = mode; calYM = parseD(inp.value) || calYM; view = "date"; yearBase = null;
        pop.style.display = "block"; render();
      });
    });
    document.addEventListener("click", function (ev) {
      if (isOpen() && !pop.contains(ev.target)) pop.style.display = "none";
    });
    return { clamp: clamp, maxDate: MAXD, iso: isoD };
  };

  /* ==================== 运行流水线步骤态 ==================== */
  LabUI.pipeReset = function (root) {
    root.querySelectorAll(".pipe-step").forEach(function (st) {
      st.classList.remove("doing", "done", "fail");
      var s = st.querySelector(".pipe-st"); if (s) s.textContent = "";
    });
  };
  LabUI.pipeDoing = function (root, i) { var st = root.querySelector('#pipe-' + i); if (st) st.classList.add("doing"); };
  LabUI.pipeDone = function (root, i, txt) {
    var st = root.querySelector('#pipe-' + i); if (!st) return;
    st.classList.remove("doing"); st.classList.add("done");
    var s = st.querySelector(".pipe-st"); if (s && txt) s.textContent = txt;
  };
  LabUI.pipeFail = function (root, i, msg) {
    var st = root.querySelector('#pipe-' + i); if (st) { st.classList.remove("doing"); st.classList.add("fail"); }
    var err = root.querySelector(".pipe-err");
    if (err) { err.style.display = "block"; err.innerHTML = "<b>失败：</b>" + msg; }
  };

  /* ==================== 时间戳：UTC ISO → 浏览器本地时区 ==================== */
  /* 后端一律存 UTC（带 +00:00 偏移）；显示统一走此函数，输出 "YYYY-MM-DD HH:mm" 本地时间 */
  LabUI.fmtLocalTime = function (iso) {
    if (!iso) return "—";
    var d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    var p = function (n) { return ("0" + n).slice(-2); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate()) + " " + p(d.getHours()) + ":" + p(d.getMinutes());
  };

  /* ==================== 说明提示：事件委托，动态节点无需重新绑定 ==================== */
  LabUI.helpTips = function () {
    if (LabUI._helpTipsStarted) return;
    LabUI._helpTipsStarted = true;
    var pop = null, active = null, touchOpen = null, lastTouch = 0, tipId = "qre-help-tip";
    function targetOf(ev) {
      return ev.target && ev.target.closest ? ev.target.closest("[data-tip]") : null;
    }
    function textOf(el) { return el ? String(el.getAttribute("data-tip") || "").trim() : ""; }
    function hide() {
      if (active) active.removeAttribute("aria-describedby");
      active = null;
      touchOpen = null;
      if (pop) pop.style.display = "none";
    }
    function place(el) {
      var r = el.getBoundingClientRect(), vw = window.innerWidth || 320, vh = window.innerHeight || 640;
      pop.style.maxWidth = Math.min(300, vw - 24) + "px";
      pop.style.visibility = "hidden";
      var w = pop.offsetWidth || 0, h = pop.offsetHeight || 0;
      var left = Math.max(12, Math.min(r.left + r.width / 2 - w / 2, vw - w - 12));
      var top = r.bottom + 8;
      if (top + h > vh - 12 && r.top - h - 8 > 12) top = r.top - h - 8;
      pop.style.left = left + "px";
      pop.style.top = Math.max(12, top) + "px";
      pop.style.visibility = "visible";
    }
    function show(el) {
      var text = textOf(el);
      if (!text) { hide(); return; }
      if (!pop) {
        pop = document.createElement("div");
        pop.id = tipId;
        pop.className = "tip-pop";
        pop.setAttribute("role", "tooltip");
        document.body.appendChild(pop);
      }
      if (active && active !== el) active.removeAttribute("aria-describedby");
      active = el;
      pop.textContent = text;
      pop.style.display = "block";
      active.setAttribute("aria-describedby", tipId);
      place(active);
    }
    document.addEventListener("mouseover", function (ev) {
      if (Date.now() - lastTouch < 700) return;
      var el = targetOf(ev);
      if (el) show(el);
    });
    document.addEventListener("mouseout", function (ev) {
      if (Date.now() - lastTouch < 700) return;
      var el = targetOf(ev);
      if (!el) return;
      var next = ev.relatedTarget && ev.relatedTarget.closest ? ev.relatedTarget.closest("[data-tip]") : null;
      if (next !== el) hide();
    });
    document.addEventListener("focusin", function (ev) { var el = targetOf(ev); if (el) show(el); });
    document.addEventListener("focusout", function (ev) { if (targetOf(ev)) hide(); });
    document.addEventListener("pointerup", function (ev) {
      var el = targetOf(ev);
      if (ev.pointerType === "touch" || ev.pointerType === "pen") {
        lastTouch = Date.now();
        if (!el) { hide(); return; }
        if (touchOpen === el && pop && pop.style.display === "block") { hide(); return; }
        show(el);
        touchOpen = el;
      } else if (!el) hide();
    });
    document.addEventListener("keydown", function (ev) { if (ev.key === "Escape") hide(); });
    document.addEventListener("scroll", function () {
      if (!active) return;
      if (active.isConnected === false) { hide(); return; }
      place(active);
    }, true);
  };

  /* ==================== 持仓交易日（年化分母，2026-10-27） ==================== */
  /* 说明：equity_curve 的日期可能稀疏（停牌/无成交/数据缺口），不能把“条目数”当持仓
     天数，否则年化指数会爆表。这里按 entry→exit 的自然日并集计算，剔周末近似交易日；
     节假日未剔（前端无日历），但已足够避免 e+35 这类假值。可见区间外不计入。 */
  LabUI.tradingDaysHeldInRange = function (dates, dateIdx, trades, i0, i1) {
    if (!Array.isArray(dates) || !dates.length || !Array.isArray(trades) || !trades.length) return 0;
    var seen = {}, count = 0;
    function addDay(d) {
      var key = isoD(d);
      if (seen[key]) return;
      seen[key] = 1;
      var day = d.getDay();
      if (day !== 0 && day !== 6) count += 1;
    }
    trades.forEach(function (t) {
      if (!t || !t.entry_date) return;
      var a = dateIdx ? dateIdx[t.entry_date] : null;
      var b = t.exit_date && dateIdx ? dateIdx[t.exit_date] : null;
      if (a == null) return;
      if (b == null) b = a;
      if (b < a) { var tmp = a; a = b; b = tmp; }
      var s = dates[Math.max(a, i0)], e = dates[Math.min(b, i1)];
      if (!s || !e) return;
      var cur = parseD(s), end = parseD(e);
      if (!cur || !end) return;
      while (cur <= end) { addDay(cur); cur.setDate(cur.getDate() + 1); }
    });
    return count;
  };

  window.LabUI = LabUI;
})();
