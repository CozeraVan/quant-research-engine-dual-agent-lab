/* LabUI.waitMask 长等待模态遮罩组件（2026-10-04 首页长等待体验优化，用户批准）。
 *
 * 用途：NL 编译 / 运行回测等长等待期间锁定页面，防误点与重复提交。
 * 纪律：显示期间禁止 ESC 关闭、禁止点击背板关闭、页面交互全锁；
 * z-index 95（高于 .modal-mask 80 / cal-pop 60，低于 toast 99）；
 * 打磨规则同重播组件：focus-visible 紫环、0.2s 过渡、
 * prefers-reduced-motion 下 spinner 动画关闭（静态三点文案降级）。
 *
 * API：
 *   LabUI.waitMask.show({title, sub, buttons:[{label, primary, keepMask, onClick}]})
 *   LabUI.waitMask.update({title, sub, buttons})   // 部分字段可省略（沿用旧值）
 *   LabUI.waitMask.hide()
 *   LabUI.waitMask.isOpen()
 * buttons.onClick 返回 true 或按钮带 keepMask 时保持遮罩（如「继续等待」），否则自动 hide。
 */
(function () {
  "use strict";
  var maskEl = null, cardEl = null, spinEl = null, titleEl = null, subEl = null, btnRow = null;
  var state = { title: "", sub: "", buttons: [] };

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
    subEl = h("div", "wm-sub");
    btnRow = h("div", "wm-btns");
    cardEl.appendChild(spinEl);
    cardEl.appendChild(titleEl);
    cardEl.appendChild(subEl);
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
    ["title", "sub", "buttons"].forEach(function (k) {
      if (patch[k] !== undefined) state[k] = patch[k];
    });
    titleEl.textContent = state.title || "";
    subEl.textContent = state.sub || "";
    subEl.style.display = state.sub ? "" : "none";
    renderButtons();
  }

  window.LabUI = window.LabUI || {};
  LabUI.waitMask = {
    show: function (opts) {
      ensure();
      state = { title: "", sub: "", buttons: [] };
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
