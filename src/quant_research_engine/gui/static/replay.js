/* QREReplay 回测重播引擎组件（CR-2026-10-04 切片1；saas 与 lab 共享静态目录，
 * 切片2 个股页复用同一组件）。
 *
 * 设计红线：
 * - 全量数据内存持有，每帧只把 [0, cursor] 截断喂 ECharts——未来数据天然不可见；
 * - setOption 走 rAF 节流（~16ms 帧预算）；
 * - 时序口径：信号日 T（成交日前一交易日，浅色标记）与成交日 T+1（实心标记）相隔呈现；
 * - 空仓快进：跳到下一个「有事件或持仓数变化」的交易日。
 *
 * 用法：
 *   const rp = QREReplay.attach(mountEl, {
 *     dates: [...],                     // 交易日主轴（以净值序列为准）
 *     series: [{id, name, color, dashed, data:[...], grid}],   // 全量序列
 *     events: [{date, kind:'entry'|'exit', label, symbol, pnl}], // 成交事件（按日归箱）
 *     roundTrips: [{symbol, entry_date, exit_date, net_return}], // 指标/持仓用
 *     metricsEl, eventsEl,              // 指标面板 / 事件流容器（可选）
 *     staticMetrics: {total_ret},       // 静态报告值（末帧一致性校验用，可选）
 *     onFrame(cursor),                  // 帧回调（可选）
 *   });
 */
(function () {
  "use strict";

  var QREReplay = {};
  window.QREReplay = QREReplay;

  /* ---------- 纯逻辑核心（页面探针可断言） ---------- */

  function indexDates(dates) {
    var m = {};
    dates.forEach(function (d, i) { if (m[d] === undefined) m[d] = i; });
    return m;
  }

  // 事件按日归箱：{date: [ev,...]}；返回 {byDate, eventDays(sorted)}
  function binEvents(events) {
    var byDate = {}, days = [];
    (events || []).forEach(function (ev) {
      if (!byDate[ev.date]) { byDate[ev.date] = []; days.push(ev.date); }
      byDate[ev.date].push(ev);
    });
    days.sort();
    return { byDate: byDate, days: days };
  }

  // 持仓数序列：roundTrips 逐日展开（主轴索引），positions[i] = 当日持仓只数
  function positionCounts(dates, dateIdx, trips) {
    var n = dates.length, delta = new Array(n + 1).fill(0);
    (trips || []).forEach(function (t) {
      var a = dateIdx[t.entry_date], b = dateIdx[t.exit_date];
      if (a == null) return;
      if (b == null) b = n - 1;
      delta[a] += 1;
      delta[b + 1] -= 1;
    });
    var out = new Array(n).fill(0), cur = 0;
    for (var i = 0; i < n; i++) { cur += delta[i]; out[i] = cur; }
    return out;
  }

  // 空仓快进目标：cursor 之后第一个「有事件」或「持仓数与 cursor 不同」的交易日；
  // 没有则返回最后一帧索引。
  function nextEventfulCursor(cursor, eventDaysAfter, positions, n) {
    for (var i = cursor + 1; i < n; i++) {
      if (eventDaysAfter[i] || positions[i] !== positions[cursor]) return i;
    }
    return n - 1;
  }

  // 逐帧指标（对截断序列 O(n) 计算）
  function frameMetrics(dates, equity, positions, trips, cursor) {
    var n = dates.length, c = Math.max(0, Math.min(cursor, n - 1));
    var eq = equity || [];
    var first = null, last = null, peak = -Infinity, mdd = 0, peakIdx = -1;
    var rets = [];
    for (var i = 0; i <= c; i++) {
      var v = eq[i];
      if (v == null) continue;
      if (first == null) { first = v; peak = v; peakIdx = i; }
      if (i > 0 && eq[i - 1] != null && eq[i - 1] !== 0) rets.push(v / eq[i - 1] - 1);
      if (v > peak) { peak = v; peakIdx = i; }
      var ddv = v / peak - 1;
      if (ddv < mdd) mdd = ddv;
      last = v;
    }
    var totalRet = (first != null && last != null && first !== 0) ? last / first - 1 : null;
    var newPeak = peakIdx === c && c > 0;
    var sharpe = null;
    if (rets.length >= 2) {
      var mean = rets.reduce(function (a, b) { return a + b; }, 0) / rets.length;
      var varSum = rets.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / (rets.length - 1);
      var sd = Math.sqrt(varSum);
      sharpe = sd > 0 ? mean / sd * Math.sqrt(252) : null;
    }
    var dateC = dates[c];
    var closed = [], wins = [], losses = [];
    (trips || []).forEach(function (t) {
      if (t.exit_date && t.exit_date <= dateC && typeof t.net_return === "number") {
        closed.push(t);
        if (t.net_return >= 0) wins.push(t.net_return); else losses.push(t.net_return);
      }
    });
    var winRate = closed.length ? wins.length / closed.length : null;
    var plRatio = null;
    if (wins.length && losses.length) {
      var avgW = wins.reduce(function (a, b) { return a + b; }, 0) / wins.length;
      var avgL = Math.abs(losses.reduce(function (a, b) { return a + b; }, 0) / losses.length);
      plRatio = avgL > 0 ? avgW / avgL : null;
    }
    var held = 0;
    for (var j = 0; j <= c; j++) if (positions[j] > 0) held++;
    return {
      cursor: c, date: dateC,
      totalRet: totalRet, maxDD: mdd, newPeak: newPeak,
      sharpe: sharpe, winRate: winRate, plRatio: plRatio,
      closedTrips: closed.length,
      positions: positions[c], exposure: c >= 0 ? held / (c + 1) : null,
    };
  }

  // 可见窗口：右端固定在 cursor（含），左端回看 size 根。
  // 长序列只渲染窗口内数据（QRE-TV-CHART-A-FIX：4000 点全量逐帧重绘的卡顿根因）；
  // size <= 0 视为全量（start 恒为 0），窗口未满时自然从头开始。
  var DEFAULT_WINDOW = 240;
  function visibleWindow(cursor, n, size) {
    if (!(n > 0)) return { start: 0, end: 0 };
    var c = Math.max(0, Math.min(cursor, n - 1));
    var end = c + 1;
    var win = Math.max(0, Math.floor(size == null ? DEFAULT_WINDOW : Number(size) || 0));
    var start = win > 0 ? Math.max(0, end - win) : 0;
    return { start: start, end: end };
  }

  QREReplay.core = {
    indexDates: indexDates, binEvents: binEvents,
    positionCounts: positionCounts, nextEventfulCursor: nextEventfulCursor,
    frameMetrics: frameMetrics, visibleWindow: visibleWindow,
  };

  /* ---------- UI 装配 ---------- */

  function h(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function pct(v) { return v == null ? "—" : (v * 100).toFixed(2) + "%"; }
  function fnum(v, d) { return v == null ? "—" : Number(v).toFixed(d == null ? 2 : d); }

  /* 内联 SVG 图标（UI 打磨 2026-10-04：禁 emoji；图标+文字标签） */
  var ICONS = {
    play: "M8 5v14l11-7z",
    pause: "M6 5h4v14H6zM14 5h4v14h-4z",
    step: "M6 5l8 7-8 7V5zM15 5h3v14h-3z",
    skip: "M4 5l7 7-7 7V5zM12 5l7 7-7 7V5z",
  };
  function icon(name) {
    return '<svg class="rp-ic" viewBox="0 0 24 24" width="13" height="13" aria-hidden="true" focusable="false">' +
      '<path d="' + ICONS[name] + '" fill="currentColor"/></svg>';
  }

  QREReplay.attach = function (mountEl, opts) {
    var dates = opts.dates || [];
    var n = dates.length;
    var dateIdx = indexDates(dates);
    var bins = binEvents(opts.events);
    var positions = positionCounts(dates, dateIdx, opts.roundTrips);
    // 事件日布尔索引（快进用）
    var eventFlag = new Array(n).fill(false);
    bins.days.forEach(function (d) { var i = dateIdx[d]; if (i != null) eventFlag[i] = true; });

    var cursor = Math.max(0, Math.min(opts.initialCursor || 0, n - 1)), speed = 1, timer = null, playing = false;
    var seenEventDate = {};  // 事件流去重（弹入一次）

    /* DOM：控制条 */
    var bar = h("div", "rp-bar");
    var btnPlay = h("button", "rp-btn rp-play");
    btnPlay.setAttribute("aria-label", "播放 / 暂停");
    btnPlay.title = "播放 / 暂停";
    var btnStep = h("button", "rp-btn");
    btnStep.innerHTML = icon("step") + "<span>单步</span>";
    btnStep.title = "单步推进一帧";
    var speedSel = h("select", "rp-sel");
    speedSel.setAttribute("aria-label", "播放速度");
    speedSel.title = "播放速度（每帧追加 K 线根数）";
    [1, 2, 5, 10].forEach(function (v) {
      var o = h("option", null, v + "x"); o.value = v; speedSel.appendChild(o);
    });
    var startInput = h("input", "rp-date date-input");
    startInput.setAttribute("aria-label", "起始日");
    startInput.value = dates[0] || "";
    startInput.readOnly = true;
    var slider = h("input", "rp-slider");
    slider.type = "range"; slider.min = 0; slider.max = Math.max(0, n - 1); slider.value = 0;
    slider.setAttribute("aria-label", "重播进度");
    var btnSkip = h("button", "rp-btn");
    btnSkip.innerHTML = icon("skip") + "<span>空仓快进</span>";
    btnSkip.title = "跳到下一个有事件或持仓变化的交易日";
    var cur = h("span", "rp-cur", "");
    mountEl.appendChild(bar);

    /* 布局分组（2026-10-04 根因修复）：主控组 [播放/单步/速度] 永不折行（nowrap），
       辅助组 [起始日/快进] 允许折行——不依赖 flex-wrap 的宽度运气。
       （根因：base.html 全局 select{width:100%} 曾使速度档独占整行） */
    var groupMain = h("div", "rp-group rp-group-main");
    groupMain.appendChild(btnPlay); groupMain.appendChild(btnStep); groupMain.appendChild(speedSel);
    var groupAux = h("div", "rp-group rp-group-aux");
    groupAux.appendChild(h("span", "rp-lbl", "起始日"));
    groupAux.appendChild(startInput); groupAux.appendChild(btnSkip); groupAux.appendChild(cur);
    bar.appendChild(groupMain); bar.appendChild(groupAux);

    /* 图表容器：opts.chartEl 传入时接管既有容器（切片2/策略页接管模式），否则自建 */
    var ownChartEl = !opts.chartEl;
    var chartEl = opts.chartEl || h("div", "rp-chart");
    if (ownChartEl){
      if (opts.height) chartEl.style.height = opts.height + "px";  // 切片2：多副图加高
      mountEl.appendChild(chartEl);
    } else {
      // 接管：先销毁静态实例（避免旧 dataZoom/legend 残留与重播帧冲突），退出时由调用方重建
      var oldInst = echarts.getInstanceByDom(chartEl);
      if (oldInst) oldInst.dispose();
    }
    var chart = echarts.init(chartEl);
    if (window.QRETheme && QRETheme.themeChart) QRETheme.themeChart(chart);

    /* 进度条：从控制排移出，放在图表正下方一行（视觉上从属于图表；2026-10-04 布局调整） */
    var sliderRow = h("div", "rp-slider-row");
    sliderRow.appendChild(slider);
    if (opts.chartEl && chartEl.parentNode) {
      chartEl.parentNode.insertBefore(sliderRow, chartEl.nextSibling);
    } else {
      mountEl.appendChild(sliderRow);
    }

    var metricsEl = opts.metricsEl || null;
    var eventsEl = opts.eventsEl || null;

    /* 日历（复用 LabUI 组件；禁超主轴范围） */
    if (window.LabUI && LabUI.attachCalendar) {
      var pop = h("div", "rp-calpop");
      mountEl.appendChild(pop);
      LabUI.attachCalendar({
        pop: pop, startInput: startInput, endInput: h("input"),
        maxDate: dates[n - 1], minDate: dates[0],
        onChange: function () { seekDate(startInput.value); },
      });
      startInput.addEventListener("click", function () {
        pop.querySelector(".cal-pop") && pop.querySelector(".cal-pop").classList.add("show");
      });
    }

    /* 序列截断渲染（rAF 节流）：只渲染可见窗口 [start, cursor]，
       窗口外（含未来）数据不进 ECharts；指标仍按全量序列计算。 */
    var winSize = Math.max(1, Number(opts.windowSize) || DEFAULT_WINDOW);
    var viewStart = 0;
    var rafPending = false;
    function renderFrame() {
      if (rafPending) return;
      rafPending = true;
      requestAnimationFrame(function () {
        rafPending = false;
        var win = visibleWindow(cursor, n, winSize);
        viewStart = win.start;
        var s0 = win.start, c0 = win.end;
        var xData = dates.slice(s0, c0);
        var series = (opts.series || []).map(function (s) {
          var base = {
            name: s.name, id: s.id, type: s.type || "line",
            data: s.data.slice(s0, c0),
            showSymbol: false, color: s.color,
            lineStyle: { width: s.width || (s.dashed ? 1.5 : 2), type: s.dashed ? "dashed" : "solid" },
            areaStyle: s.area ? { opacity: 0.3 } : undefined,
            xAxisIndex: s.grid || 0, yAxisIndex: s.grid || 0,
            markPoint: s.mark ? markPoints(s) : undefined,
          };
          // 切片2：K线/成交量/散点等任意 ECharts series 透传（extra 覆盖默认键）
          return Object.assign(base, s.extra || {});
        });
        chart.setOption({
          animation: false,
          tooltip: { trigger: "axis", valueFormatter: function (v) { return v == null ? "—" : Number(v).toFixed(2) + "%"; } },
          legend: { top: 0, data: (opts.series || []).filter(function (s) { return !s.grid; }).map(function (s) { return s.name; }) },
          grid: opts.grids || [{ left: 55, right: 20, top: 30, height: "68%" }],
          xAxis: (opts.grids || [{}]).map(function (g, gi) {
            return { type: "category", data: xData, gridIndex: gi, axisLabel: { show: gi === (opts.grids || []).length - 1 } };
          }),
          yAxis: (opts.yAxes || [{ name: "累计收益率%" }]).map(function (y, yi) {
            // 默认按收益率口径加 %（切片1）；切片2 传 pct:false（价格/量/因子轴）
            return { type: "value", gridIndex: yi, name: y.name, max: y.max, scale: y.scale !== false,
                     axisLabel: y.pct === false ? undefined : { formatter: "{value}%" } };
          }),
          series: series,
        }, { replaceMerge: ["xAxis", "series"] });
        slider.value = cursor;
        cur.textContent = (cursor + 1) + " / " + n;
        var m = frameMetrics(dates, (opts.series || [])[0] ? (opts.series[0].raw || []) : [], positions, opts.roundTrips, cursor);
        renderMetrics(m);
        popEvents();
        if (opts.onFrame) opts.onFrame(cursor, m);
      });
    }

    // 事件标记：信号日 T（成交日前一交易日，空心浅色）+ 成交日 T+1（实心）。
    // ev.price 存在时以事件真实成交价定位（K线买卖点口径），否则用该帧序列值。
    // 只标记可见窗口内的事件（窗口外日期不在 xAxis 上，且不得泄露未来）。
    function markPoints(s) {
      var pts = [];
      function yAt(i) {
        var v = s.data[i];
        return Array.isArray(v) ? v[1] : v;  // K线 [o,c,l,h] 取收盘
      }
      bins.days.forEach(function (d) {
        var i = dateIdx[d];
        if (i == null || i > cursor || i < viewStart) return;
        bins.byDate[d].forEach(function (ev) {
          pts.push({
            coord: [d, (ev.price != null ? ev.price : yAt(i))],
            value: ev.kind === "entry" ? "入" : "出",
            itemStyle: { color: ev.kind === "entry" ? "#d43030" : "#1a9e4b" },
          });
          // 信号日 T = 成交日前一交易日（时序红线：相隔呈现，不神化策略时序）
          if (i > 0 && i - 1 >= viewStart && yAt(i - 1) != null) {
            pts.push({
              coord: [dates[i - 1], yAt(i - 1)], value: "信",
              symbol: "circle", symbolSize: 5,
              itemStyle: { color: "rgba(103,80,164,.45)" },
              label: { fontSize: 9, color: "rgba(103,80,164,.7)" },
            });
          }
        });
      });
      return { data: pts, symbol: "pin", symbolSize: 22, label: { fontSize: 10, color: "#fff" } };
    }

    /* 指标面板（QRE-SAAS-RESULT-UNDERSTANDING：盈亏比/暴露度/当前持仓带口径提示，
       复用 LabUI.helpTips 事件委托——桌面 hover / 键盘 focus / 移动 tap） */
    var lastPeakFlash = 0;
    function renderMetrics(m) {
      if (!metricsEl) return;
      var cards = [
        ["当前交易日", m.date || "—", "", ""],
        ["累计收益", pct(m.totalRet), m.totalRet == null ? "" : (m.totalRet >= 0 ? "pos" : "neg"), ""],
        ["最大回撤", pct(m.maxDD), "neg", ""],
        ["夏普比率", fnum(m.sharpe), "", ""],
        ["胜率·已平仓 " + m.closedTrips + " 笔", pct(m.winRate), "", ""],
        ["盈亏比", fnum(m.plRatio), "",
         "已平仓交易的平均盈利 ÷ 平均亏损（取绝对值）；>1 表示平均赚的比亏的多。只统计已平仓交易。"],
        ["当前持仓", m.positions + " 只", "", "当前帧持有的股票只数。"],
        ["暴露度", pct(m.exposure), "",
         "持仓暴露度：截至当前帧有持仓的交易日数 ÷ 已播放交易日数；同一日多笔持仓按 1 天计。"],
      ];
      metricsEl.innerHTML = cards.map(function (c) {
        return '<div class="metric-card"' + (c[3] ? ' tabindex="0" data-tip="' + c[3] + '"' : "") +
          '><div class="m-label">' + c[0] + "</div>" +
          '<div class="m-value ' + c[2] + '">' + c[1] + "</div></div>";
      }).join("");
      if (m.newPeak && Date.now() - lastPeakFlash > 800) {
        lastPeakFlash = Date.now();
        metricsEl.classList.add("rp-peak-flash");
        setTimeout(function () { metricsEl.classList.remove("rp-peak-flash"); }, 600);
      }
    }

    /* 事件流：按日弹入；同日同类 >5 聚合可展开。
       聚合口径（QRE-SAAS-REPLAY-BOUNDARIES）：头部按**去重标的**计「只」——
       同一标的同日常有多笔（分笔委托/同日往返），事件数大于标的数时披露
       「（M 笔）」，明细展开列全部事件，计数与可见文案一致。 */
    function evChipText(ev) {
      var s = ev.symbol || "";
      if (ev.qty != null) s += " " + ev.qty + " 股";
      if (ev.price != null) s += "@" + Number(ev.price).toFixed(2);
      if (ev.pnl != null) s += " " + pct(ev.pnl);
      return s;
    }
    function aggHead(label, list) {
      var seen = {}, symCount = 0;
      list.forEach(function (ev) {
        var k = ev.sym != null ? ev.sym : (ev.symbol || "");
        if (!seen[k]) { seen[k] = true; symCount += 1; }
      });
      var head = "当日" + label + " " + symCount + " 只";
      if (list.length > symCount) head += "（" + list.length + " 笔）";
      return head;
    }
    function popEvents() {
      if (!eventsEl) return;
      bins.days.forEach(function (d) {
        var i = dateIdx[d];
        if (i == null || i > cursor || seenEventDate[d]) return;
        seenEventDate[d] = true;
        var evs = bins.byDate[d];
        var row = h("div", "rp-ev-day rp-pop");
        row.appendChild(h("span", "rp-ev-date", d));
        [["entry", "入场", "#d43030"], ["exit", "出场", "#1a9e4b"]].forEach(function (pair) {
          var kind = pair[0], label = pair[1], color = pair[2];
          var list = evs.filter(function (e) { return e.kind === kind; });
          if (!list.length) return;
          if (list.length <= 5) {
            list.forEach(function (ev) {
              var chip = h("span", "rp-ev-chip", evChipText(ev));
              chip.style.borderColor = color;
              row.appendChild(chip);
            });
          } else {
            var head = aggHead(label, list);
            var agg = h("button", "rp-ev-chip rp-ev-agg", head + " ▸");
            agg.style.borderColor = color;
            agg.addEventListener("click", function () {
              if (agg._open) { agg.nextSibling.remove(); agg._open = false; agg.textContent = head + " ▸"; return; }
              var det = h("div", "rp-ev-det");
              list.forEach(function (ev) {
                det.appendChild(h("span", "rp-ev-chip", evChipText(ev)));
              });
              row.insertBefore(det, agg.nextSibling);
              agg._open = true;
              agg.textContent = head + " ▾";
            });
            row.appendChild(agg);
          }
        });
        eventsEl.insertBefore(row, eventsEl.firstChild);
      });
    }

    /* 播放控制 */
    function frame() {
      if (cursor >= n - 1) { pause(); return; }
      cursor = Math.min(n - 1, cursor + speed);
      renderFrame();
    }
    function setPlayBtn() {
      // 播放中状态切换即时生效，图标过渡由 CSS .rp-ic 处理
      btnPlay.innerHTML = icon(playing ? "pause" : "play") + "<span>" + (playing ? "暂停" : "播放") + "</span>";
    }
    function play() {
      if (playing || n <= 1) return;
      if (cursor >= n - 1) { cursor = 0; seenEventDate = {}; if (eventsEl) eventsEl.innerHTML = ""; }
      playing = true;
      setPlayBtn();
      timer = setInterval(frame, 120);
    }
    function pause() {
      playing = false;
      setPlayBtn();
      if (timer) { clearInterval(timer); timer = null; }
    }
    function seek(c) {
      cursor = Math.max(0, Math.min(c, n - 1));
      // 事件流整体重建（回退时清除未来弹入；前进/回退统一清空重弹，避免重复行）
      seenEventDate = {};
      if (eventsEl) eventsEl.innerHTML = "";
      renderFrame();
    }
    function seekDate(d) {
      var i = dateIdx[d];
      if (i == null) {
        // 选到非交易日：取其后第一个交易日
        for (var k = 0; k < n; k++) if (dates[k] >= d) { i = k; break; }
        if (i == null) i = n - 1;
      }
      pause(); seek(i);
    }

    btnPlay.addEventListener("click", function () { playing ? pause() : play(); });
    btnStep.addEventListener("click", function () { pause(); frame(); });
    speedSel.addEventListener("change", function () { speed = Number(speedSel.value); });
    slider.addEventListener("input", function () { pause(); seek(Number(slider.value)); });
    btnSkip.addEventListener("click", function () {
      pause();
      seek(nextEventfulCursor(cursor, eventFlag, positions, n));
    });
    // 自建容器才拥有窗口重排职责；接管模式下容器尺寸由宿主页面负责（避免与宿主双重绑定）
    var onWindowResize = function () { chart.resize(); };
    if (ownChartEl) window.addEventListener("resize", onWindowResize);

    setPlayBtn();
    renderFrame();

    return {
      play: play, pause: pause, seek: seek, seekDate: seekDate,
      skipFlat: function () { seek(nextEventfulCursor(cursor, eventFlag, positions, n)); },
      getCursor: function () { return cursor; },
      isPlaying: function () { return playing; },
      metrics: function () {
        return frameMetrics(dates, (opts.series || [])[0] ? (opts.series[0].raw || []) : [], positions, opts.roundTrips, cursor);
      },
      // keepDom=true（接管模式退出）：只撤控制条与日历，保留图表容器由调用方重建静态图
      destroy: function (keepDom) {
        pause();
        if (ownChartEl && window.removeEventListener) window.removeEventListener("resize", onWindowResize);
        chart.dispose();
        bar.remove();
        sliderRow.remove();
        var pop = mountEl.querySelector(".rp-calpop");
        if (pop) pop.remove();
        if (!keepDom) mountEl.innerHTML = "";
        else if (ownChartEl) chartEl.remove();
      },
    };
  };
})();
