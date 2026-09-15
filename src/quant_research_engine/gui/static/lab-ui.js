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
  function isoD(d) { return d.getFullYear() + "-" + ("0" + (d.getMonth() + 1)).slice(-2) + "-" + ("0" + d.getDate()).slice(-2); }
  function parseD(s) { var p = (s || "").split("-"); return p.length === 3 ? new Date(+p[0], +p[1] - 1, +p[2]) : null; }
  /* opts: {pop, startInput, endInput, maxDate:'YYYY-MM-DD', onChange} */
  LabUI.attachCalendar = function (opts) {
    var pop = opts.pop, sIn = opts.startInput, eIn = opts.endInput;
    var MAXD = parseD(opts.maxDate) || new Date();
    var calMode = "start", calYM = null;
    function clamp() {
      var s = parseD(sIn.value), e = parseD(eIn.value);
      if (e && e > MAXD) eIn.value = isoD(MAXD);
      if (s && s > MAXD) sIn.value = isoD(MAXD);
    }
    function render() {
      if (!calYM) { calYM = parseD(sIn.value) || MAXD; calYM = new Date(calYM.getFullYear(), calYM.getMonth(), 1); }
      var y = calYM.getFullYear(), m = calYM.getMonth();
      var s = parseD(sIn.value), e = parseD(eIn.value);
      var pad = (new Date(y, m, 1).getDay() + 6) % 7, days = new Date(y, m + 1, 0).getDate();
      var noNext = (new Date(y, m + 1, 1)) > MAXD;
      var html = '<div class="cal-head"><button class="cal-nav" data-nav="-1">‹</button><b>' + y + " 年 " + (m + 1) + ' 月</b><button class="cal-nav" data-nav="1"' + (noNext ? " disabled style='opacity:.35;cursor:default'" : "") + ">›</button></div>";
      html += '<div class="cal-grid">' + "一二三四五六日".split("").map(function (d) { return '<span class="cal-dow">' + d + "</span>"; }).join("");
      for (var i = 0; i < pad; i++) html += '<span class="cal-day pad"></span>';
      for (var d = 1; d <= days; d++) {
        var dt = new Date(y, m, d), cls = "cal-day", dis = dt > MAXD;
        if (s && dt.getTime() === s.getTime()) cls += " sel";
        if (e && dt.getTime() === e.getTime()) cls += " sel";
        if (s && e && dt > s && dt < e) cls += " in-range";
        html += '<button class="' + cls + '" data-d="' + isoD(dt) + '"' + (dis ? " disabled" : "") + ">" + d + "</button>";
      }
      html += '</div><div class="cal-foot">数据截至 ' + opts.maxDate + '（最近交易日），之后日期不可选<br>正在选择：' + (calMode === "start" ? "起始日" : "截止日") + "（点输入框切换）</div>";
      pop.innerHTML = html;
      pop.querySelectorAll(".cal-nav").forEach(function (b) {
        b.addEventListener("click", function (ev) {
          ev.stopPropagation(); if (b.disabled) return;
          calYM = new Date(y, m + (+b.dataset.nav), 1); render();
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
    [sIn, eIn].forEach(function (inp, idx) {
      inp.readOnly = true;
      inp.classList.add("date-input");
      inp.addEventListener("click", function (ev) {
        ev.stopPropagation();
        clamp(); if (opts.onChange) opts.onChange();
        var mode = idx === 0 ? "start" : "end";
        if (pop.style.display !== "none" && pop.style.display !== "" && calMode === mode) { pop.style.display = "none"; return; }
        calMode = mode; calYM = parseD(inp.value) || calYM;
        pop.style.display = "block"; render();
      });
    });
    document.addEventListener("click", function (ev) {
      if (pop.style.display === "block" && !pop.contains(ev.target)) pop.style.display = "none";
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

  window.LabUI = LabUI;
})();
