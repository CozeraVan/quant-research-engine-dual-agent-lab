/* 夜间模式（QRE-SAAS-NIGHT）：主题切换 + ECharts 随主题改色。
   浅色为默认外观，本文件在浅色下不改变任何既有配色。 */
(function () {
  'use strict';

  var THEME_KEY = 'qre-theme';
  var META_LIGHT = '#4A3C78';
  var META_DARK = '#17153B';
  var charts = [];

  var mq = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;

  function storedTheme() {
    try {
      var v = window.localStorage.getItem(THEME_KEY);
      return v === 'dark' || v === 'light' ? v : null;
    } catch (e) {
      return null;
    }
  }

  function systemTheme() {
    return mq && mq.matches ? 'dark' : 'light';
  }

  function resolvedTheme() {
    var t = document.documentElement.dataset.theme;
    if (t === 'dark' || t === 'light') return t;
    return storedTheme() || systemTheme();
  }

  function setMeta(theme) {
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'dark' ? META_DARK : META_LIGHT);
  }

  function setButtonState(theme) {
    var label = theme === 'dark' ? '日间模式' : '夜间模式';
    var btns = document.querySelectorAll('.tt-btn');
    for (var i = 0; i < btns.length; i++) {
      btns[i].textContent = label;
      btns[i].setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
      btns[i].setAttribute('aria-label', label + '（切换配色）');
    }
  }

  function apply(theme) {
    var t = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = t;
    setMeta(t);
    setButtonState(t);
    document.dispatchEvent(new CustomEvent('qre:themechange', { detail: { theme: t } }));
    return t;
  }

  function set(theme) {
    var t = theme === 'dark' ? 'dark' : 'light';
    try { window.localStorage.setItem(THEME_KEY, t); } catch (e) {}
    return apply(t);
  }

  function toggle() {
    return set(resolvedTheme() === 'dark' ? 'light' : 'dark');
  }

  // ---- ECharts：主题中性色 ----
  function neutralLayer(dark) {
    var axis = dark ? {
      axisLabel: { color: '#C8ACD6' },
      axisLine: { lineStyle: { color: '#433D8B' } },
      splitLine: { lineStyle: { color: '#433D8B' } },
      nameTextStyle: { color: '#C8ACD6' }
    } : {
      axisLabel: { color: '#6E7079' },
      axisLine: { lineStyle: { color: '#6E7079' } },
      splitLine: { lineStyle: { color: '#E0E6F1' } },
      nameTextStyle: { color: '#6E7079' }
    };
    return {
      backgroundColor: 'transparent',
      textStyle: { color: dark ? '#F1EDF8' : '#333' },
      legend: { textStyle: { color: dark ? '#F1EDF8' : '#333' } },
      tooltip: dark ? {
        backgroundColor: '#2E236C',
        borderColor: '#433D8B',
        textStyle: { color: '#F1EDF8' }
      } : {
        backgroundColor: 'rgba(50,50,50,.7)',
        borderColor: '#333',
        textStyle: { color: '#fff' }
      },
      xAxis: axis,
      yAxis: axis
    };
  }

  function hasKey(o, k) {
    return Object.prototype.hasOwnProperty.call(o, k);
  }

  // 深合并：补丁优先；数组逐个元素递归；不修改入参
  function mergePatch(value, patch) {
    if (Array.isArray(value)) {
      return value.map(function (item) {
        return item && typeof item === 'object' ? mergePatch(item, patch) : item;
      });
    }
    if (!value || typeof value !== 'object') return patch;
    var out = {};
    var k;
    for (k in value) {
      if (hasKey(value, k)) out[k] = value[k];
    }
    for (k in patch) {
      if (!hasKey(patch, k)) continue;
      if (
        out[k] && typeof out[k] === 'object' && !Array.isArray(out[k]) &&
        patch[k] && typeof patch[k] === 'object' && !Array.isArray(patch[k])
      ) {
        out[k] = mergePatch(out[k], patch[k]);
      } else {
        out[k] = patch[k];
      }
    }
    return out;
  }

  // 只处理 option 中已存在的组件（不给无图例的图添图例），组件内部缺键则补齐
  function applyNeutral(obj, dark) {
    if (!obj || typeof obj !== 'object') return obj;
    var n = neutralLayer(dark);
    var out = {};
    var k;
    for (k in obj) {
      if (hasKey(obj, k)) out[k] = obj[k];
    }
    var parts = ['textStyle', 'legend', 'tooltip', 'xAxis', 'yAxis'];
    for (var i = 0; i < parts.length; i++) {
      var key = parts[i];
      if (!hasKey(obj, key) || obj[key] === null || obj[key] === undefined) continue;
      out[key] = mergePatch(obj[key], n[key]);
    }
    out.backgroundColor = n.backgroundColor;
    return out;
  }

  // ---- ECharts：系列色随主题翻译 ----
  var COLOR_KEYS = { color: 1, color0: 1, borderColor: 1, borderColor0: 1 };
  var MAP_DARK = {};
  var MAP_LIGHT = {};

  function addPair(lightVals, darkVal) {
    for (var i = 0; i < lightVals.length; i++) MAP_DARK[lightVals[i]] = darkVal;
    MAP_LIGHT[darkVal] = lightVals[0];
  }

  addPair(['#6750a4'], '#9b84d8');
  addPair(['#8b7fbe'], '#a78be0');
  addPair(['#b7a6e8'], '#c8acd6');
  addPair(['#d9d2ea'], '#5b5390');
  addPair(['#9a93a6'], '#8e86a0');
  addPair(['#d43030', '#c93a3a'], '#ff7a7a');
  addPair(['#8b0000'], '#ff9999');
  addPair(['#1e8e5a', '#1a9e4b'], '#4fd69a');
  addPair(['#2563eb'], '#6ea8ff');
  addPair(['#241f2e'], '#f1edf8');

  function translateWalk(node, map) {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      for (var i = 0; i < node.length; i++) translateWalk(node[i], map);
      return;
    }
    var keys = Object.keys(node);
    for (var j = 0; j < keys.length; j++) {
      var k = keys[j];
      if (k === 'data' || k === 'dataset') continue;
      var v = node[k];
      if (typeof v === 'string') {
        if (COLOR_KEYS[k]) {
          var hit = map[v.toLowerCase()];
          if (hit) node[k] = hit;
        }
      } else if (v && typeof v === 'object') {
        translateWalk(v, map);
      }
    }
  }

  function repaint() {
    var dark = resolvedTheme() === 'dark';
    var alive = [];
    for (var i = 0; i < charts.length; i++) {
      var chart = charts[i];
      if (!chart || typeof chart.isDisposed !== 'function' || chart.isDisposed()) continue;
      alive.push(chart);
      try {
        var opt = chart.getOption();
        if (!opt || typeof opt !== 'object') continue;
        var next = applyNeutral(opt, dark);
        translateWalk(next, dark ? MAP_DARK : MAP_LIGHT);
        chart.__qreOrigSetOption(next, { notMerge: true });
      } catch (e) { /* 单图失败不影响其余图表与主题 */ }
    }
    charts = alive;
  }

  function themeChart(chart) {
    if (!chart || typeof chart.setOption !== 'function') return chart;
    if (!chart.__qreThemed) {
      chart.__qreOrigSetOption = chart.setOption.bind(chart);
      chart.setOption = function (option, notMerge, lazyUpdate) {
        var opt = option;
        try {
          if (opt && typeof opt === 'object' && !Array.isArray(opt) && resolvedTheme() === 'dark') {
            opt = applyNeutral(opt, true);
          }
        } catch (e) {
          opt = option;
        }
        return chart.__qreOrigSetOption(opt, notMerge, lazyUpdate);
      };
      chart.__qreThemed = true;
    }
    charts.push(chart);
    return chart;
  }

  // ---- 交互绑定 ----
  document.addEventListener('qre:themechange', repaint);

  document.addEventListener('click', function (ev) {
    var el = ev.target;
    while (el && el !== document.body) {
      if (el.classList && el.classList.contains('tt-btn')) {
        ev.preventDefault();
        toggle();
        return;
      }
      el = el.parentNode;
    }
  });

  if (mq) {
    var onScheme = function () {
      if (!storedTheme()) apply(systemTheme());
    };
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onScheme);
    else if (typeof mq.addListener === 'function') mq.addListener(onScheme);
  }

  function mountFallbackButton() {
    if (document.querySelector('.tt-btn') || !document.body) return;
    var btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tt-btn tt-float';
    btn.setAttribute('aria-pressed', 'false');
    document.body.appendChild(btn);
    setButtonState(resolvedTheme());
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountFallbackButton);
  } else {
    mountFallbackButton();
  }

  window.QRETheme = {
    current: resolvedTheme,
    set: set,
    toggle: toggle,
    themeChart: themeChart
  };

  apply(resolvedTheme());
})();