/* LabUI.waitMask 长等待模态遮罩组件（2026-10-04 首页长等待体验优化，用户批准）。
 *
 * 用途：NL 编译 / 运行回测等长等待期间锁定页面，防误点与重复提交。
 * 纪律：显示期间禁止 ESC 关闭、禁止点击背板关闭、页面交互全锁；
 * z-index 95（高于 .modal-mask 80 / cal-pop 60，低于 toast 99）；
 * 打磨规则同重播组件：focus-visible 紫环、0.2s 过渡、
 * prefers-reduced-motion 下 spinner 动画关闭（静态三点文案降级）。
 *
 * API：
 *   LabUI.waitMask.show({title, sub, buttons:[{label, primary, keepMask, onClick}], meta})
 *   LabUI.waitMask.update({title, sub, buttons, meta})   // 部分字段可省略（沿用旧值）
 *   LabUI.waitMask.hide()
 *   LabUI.waitMask.isOpen()
 * buttons.onClick 返回 true 或按钮带 keepMask 时保持遮罩（如「继续等待」），否则自动 hide。
 *
 * 可访问性（QRE-SAAS-FIRST-SUCCESS-UX-001）：title/sub 挂 aria-live="polite"，
 * 状态变化（排队→执行中→离线提示）会被读屏播报；meta（如「已等待 N 秒」）是纯视觉
 * 行，不进 aria-live，避免轮询每秒刷新时反复朗读。
 */
(function () {
  "use strict";
  var maskEl = null, cardEl = null, spinEl = null, titleEl = null, subEl = null, btnRow = null, metaEl = null;
  var state = { title: "", sub: "", buttons: [], meta: "" };

  function h(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text != null) el.textContent = text;
    return el;
  }
  function ensure() {
    if (maskEl) return;
    maskEl = h("div", "wm-mask");
    maskEl.setAttribute("role", "dialog");
    maskEl.setAttribute("aria-modal", "true");
    maskEl.setAttribute("aria-label", "处理中，请稍候");
    cardEl = h("div", "wm-card");
    spinEl = h("div", "wm-spin");
    spinEl.setAttribute("aria-hidden", "true");
    titleEl = h("div", "wm-title");
    titleEl.setAttribute("aria-live", "polite");
    subEl = h("div", "wm-sub");
    subEl.setAttribute("aria-live", "polite");
    metaEl = h("div", "wm-meta");  // 秒数等视觉行：无 aria-live，不参与朗读
    metaEl.setAttribute("aria-hidden", "true");
    btnRow = h("div", "wm-btns");
    cardEl.appendChild(spinEl);
    cardEl.appendChild(titleEl);
    cardEl.appendChild(subEl);
    cardEl.appendChild(metaEl);
    cardEl.appendChild(btnRow);
    maskEl.appendChild(cardEl);
    // 背板点击不关闭（刻意）；ESC 不监听即不关（刻意）
    document.body.appendChild(maskEl);
  }
  function renderButtons() {
    btnRow.innerHTML = "";
    btnRow.style.display = state.buttons.length ? "" : "none";
    spinEl.style.display = state.buttons.length ? "none" : "";  // 有分流按钮时停转（等待语义交还用户）
    state.buttons.forEach(function (b) {
      var btn = h("button", "wm-btn" + (b.primary ? " primary" : ""), b.label);
      btn.addEventListener("click", function () {
        var ret = b.onClick ? b.onClick() : undefined;  // 先执行（keepMask 只是不关遮罩，不跳过动作）
        var keep = b.keepMask || ret === true;
        if (!keep) LabUI.waitMask.hide();
      });
      btnRow.appendChild(btn);
    });
  }
  function apply(patch) {
    ["title", "sub", "buttons", "meta"].forEach(function (k) {
      if (patch[k] !== undefined) state[k] = patch[k];
    });
    var title = state.title || "", sub = state.sub || "";
    // aria-live 降噪：文本没变就不碰 DOM——轮询每秒/每轮刷新不会重复播报同一句
    if (titleEl.textContent !== title) titleEl.textContent = title;
    if (subEl.textContent !== sub){
      subEl.textContent = sub;
      subEl.style.display = sub ? "" : "none";
    }
    // meta（秒数）是 aria-hidden 视觉行，照常更新
    metaEl.textContent = state.meta || "";
    metaEl.style.display = state.meta ? "" : "none";
    renderButtons();
  }

  window.LabUI = window.LabUI || {};
  LabUI.waitMask = {
    show: function (opts) {
      ensure();
      state = { title: "", sub: "", buttons: [], meta: "" };
      apply(opts || {});
      maskEl.classList.add("show");
      document.body.classList.add("wm-lock");  // 锁页面滚动（交互由遮罩物理拦截）
    },
    update: function (patch) { if (maskEl) apply(patch || {}); },
    hide: function () {
      if (!maskEl) return;
      maskEl.classList.remove("show");
      document.body.classList.remove("wm-lock");
    },
    isOpen: function () { return !!(maskEl && maskEl.classList.contains("show")); },
  };
})();
