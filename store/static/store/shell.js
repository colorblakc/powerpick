/* Shell behaviour shared by every page: toasts, account menu, add-to-cart feedback, confirm prompts. */
(function () {
  "use strict";

  // Motion helpers shared with cart.js and the page scripts. Every effect is skipped under prefers-reduced-motion
  // (the CSS in motion.css also switches its keyframes off), and none of them is needed for the page to work.
  var reduceQuery = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reduced() { return !!(reduceQuery && reduceQuery.matches); }
  function replay(el, cls, ms) {
    if (!el || reduced()) return;
    el.classList.remove(cls);
    void el.offsetWidth; // forces a reflow so the animation restarts from the beginning
    el.classList.add(cls);
    clearTimeout(el.__mpTimer);
    el.__mpTimer = setTimeout(function () { el.classList.remove(cls); }, ms);
  }
  function closeDetails(details, after) {
    if (!details.open) return;
    if (reduced()) { details.open = false; if (after) after(); return; }
    details.classList.add("is-closing");
    setTimeout(function () {
      details.classList.remove("is-closing");
      details.open = false;
      if (after) after();
    }, 150);
  }
  function added(button) {
    if (!button || reduced() || button.classList.contains("is-added")) return;
    var ns = "http://www.w3.org/2000/svg";
    var check = document.createElementNS(ns, "svg");
    check.setAttribute("class", "i add-check");
    check.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(ns, "use");
    use.setAttribute("href", "#i-check");
    check.appendChild(use);
    button.appendChild(check);
    button.classList.add("is-added");
    setTimeout(function () {
      button.classList.remove("is-added");
      if (check.parentNode) check.parentNode.removeChild(check);
    }, 1500);
  }
  window.PPMotion = {
    reduced: reduced,
    replay: replay,
    closeDetails: closeDetails,
    added: added,
    tick: function (node) { replay(node, "is-ticking", 260); }
  };

  // Count badges bump when their number changes; hearts pop when they become pressed.
  if (window.MutationObserver) {
    var cartTag = document.querySelector(".cart-tag");
    var wishTag = document.querySelector(".wish-tag");
    var watch = function (tag) {
      if (!tag) return;
      var badge = tag.querySelector("b");
      var last = badge ? badge.textContent : "";
      new MutationObserver(function () {
        var now = badge.textContent;
        if (now !== last) { last = now; replay(tag, "is-bump", 800); }
      }).observe(badge, { childList: true, characterData: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
    };
    watch(cartTag); watch(wishTag);
    new MutationObserver(function (records) {
      records.forEach(function (record) {
        var node = record.target;
        if (node.getAttribute("aria-pressed") === "true" && record.oldValue !== "true" && node.querySelector(".i")) replay(node, "is-pop", 420);
      });
    }).observe(document.body, { attributes: true, attributeFilter: ["aria-pressed"], attributeOldValue: true, subtree: true });
  }

  // Toasts dismiss on click and fade after a few seconds (errors stay until dismissed).
  document.querySelectorAll(".toast").forEach(function (toast) {
    function leave() {
      toast.classList.add("is-leaving");
      setTimeout(function () { toast.remove(); }, 200);
    }
    var close = toast.querySelector("button");
    if (close) close.addEventListener("click", leave);
    if (!toast.classList.contains("toast--error")) setTimeout(leave, 6000);
  });

  // Menus (account, Shop): close on outside click or Escape; only one open at a time.
  var menus = Array.prototype.slice.call(document.querySelectorAll(".acct-menu, .shop-menu"));
  menus.forEach(function (menu) {
    menu.querySelector("summary").addEventListener("click", function (event) {
      if (menu.open && !reduced()) { event.preventDefault(); closeDetails(menu); }
    });
    menu.addEventListener("toggle", function () {
      if (menu.open) menus.forEach(function (other) { if (other !== menu) other.open = false; });
      if (menu.classList.contains("shop-menu")) document.documentElement.classList.toggle("shop-open", menu.open);
    });
  });
  document.addEventListener("click", function (event) {
    menus.forEach(function (menu) { if (menu.open && !menu.contains(event.target)) closeDetails(menu); });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    menus.forEach(function (menu) { if (menu.open) { closeDetails(menu); menu.querySelector("summary").focus(); } });
    if (mast && mast.classList.contains("is-searching")) setSearch(false, true);
  });

  // Masthead: measure its height for the menu and toasts, solidify on scroll, mobile search toggle.
  var mast = document.querySelector("[data-mast]");
  var island = mast && mast.querySelector(".mast-top");
  var toggle = mast && mast.querySelector(".search-toggle");
  function measure() {
    if (island) document.documentElement.style.setProperty("--mast-top-h", Math.round(island.getBoundingClientRect().bottom) + "px");
  }
  function setSearch(on, refocus) {
    mast.classList.toggle("is-searching", on);
    toggle.setAttribute("aria-expanded", on ? "true" : "false");
    measure();
    if (on) mast.querySelector(".mast-search input").focus();
    else if (refocus) toggle.focus();
  }
  if (mast) {
    if (toggle) {
      toggle.hidden = false;
      toggle.addEventListener("click", function () { setSearch(!mast.classList.contains("is-searching")); });
    }
    var onScroll = function () { mast.classList.toggle("is-stuck", window.scrollY > 24); };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", measure);
    onScroll(); measure();
  }

  // Forms marked data-confirm ask first; buttons in forms marked data-busy show a loading state.
  document.addEventListener("submit", function (event) {
    var form = event.target;
    var message = form.getAttribute("data-confirm");
    if (message && !window.confirm(message)) { event.preventDefault(); return; }
    var submit = form.querySelector("button[type=submit][data-busy], button[data-busy]:not([type])");
    if (submit && !event.defaultPrevented) {
      submit.classList.add("is-loading");
      submit.setAttribute("aria-busy", "true");
    }
  });

  // Quantity steppers: <div class="qty"> with [data-qty-minus], input, [data-qty-plus].
  document.querySelectorAll(".qty").forEach(function (box) {
    var input = box.querySelector("input");
    var minus = box.querySelector("[data-qty-minus]");
    var plus = box.querySelector("[data-qty-plus]");
    if (!input || !minus || !plus) return;
    var shown = null;
    function sync() {
      var min = parseInt(input.min || "1", 10), max = parseInt(input.max || "999", 10);
      var value = Math.min(Math.max(parseInt(input.value || String(min), 10) || min, min), max);
      input.value = value;
      if (shown !== null && value !== shown && input.animate && !reduced()) {
        input.animate([{ transform: "translateY(" + (value > shown ? 7 : -7) + "px)", opacity: 0.3 }, { transform: "none", opacity: 1 }], { duration: 200, easing: "cubic-bezier(.16, 1, .3, 1)" });
      }
      shown = value;
      minus.disabled = value <= min;
      plus.disabled = value >= max;
    }
    minus.addEventListener("click", function () { input.value = (parseInt(input.value, 10) || 1) - 1; sync(); input.dispatchEvent(new Event("change", { bubbles: true })); });
    plus.addEventListener("click", function () { input.value = (parseInt(input.value, 10) || 0) + 1; sync(); input.dispatchEvent(new Event("change", { bubbles: true })); });
    input.addEventListener("change", sync);
    sync();
  });
})();
