/* Storefront browse behaviour: filter drawer, sort auto-submit, wishlist hearts and add to cart without a reload.
   Every control also works as a plain form post, so nothing here is required. */
(function () {
  "use strict";

  // Filters: a disclosure popover (a bottom sheet on phones). Escape, the close button and an outside click shut it.
  var box = document.querySelector("[data-filter-box]");
  if (box) {
    var summary = box.querySelector("summary");
    var shut = function (focus) {
      if (!box.open) return;
      var done = function () { if (focus) summary.focus(); };
      if (window.PPMotion) window.PPMotion.closeDetails(box, done); else { box.open = false; done(); }
    };
    summary.addEventListener("click", function (e) { if (box.open && window.PPMotion && !window.PPMotion.reduced()) { e.preventDefault(); shut(false); } });
    box.addEventListener("toggle", function () {
      document.documentElement.classList.toggle("has-sheet", box.open && window.matchMedia("(max-width: 720px)").matches);
      if (box.open) { var first = box.querySelector(".filter-form select, .filter-form input:not([type=hidden])"); if (first) first.focus({ preventScroll: true }); }
    });
    box.addEventListener("keydown", function (e) { if (e.key === "Escape") shut(true); });
    var close = box.querySelector("[data-filter-close]");
    if (close) close.addEventListener("click", function () { shut(true); });
    document.addEventListener("click", function (e) { if (box.open && !box.querySelector(".filter-panel").contains(e.target) && !summary.contains(e.target)) shut(false); });
  }

  // The toolbar sticks under the masthead and gains a hairline once stuck.
  var bar = document.querySelector("[data-bar]");
  if (bar) {
    var head = document.querySelector("[data-mast]");
    var place = function () {
      var top = 0;
      if (head && getComputedStyle(head).position === "sticky") top = head.getBoundingClientRect().height;
      bar.style.setProperty("--bar-top", top + "px");
      bar.classList.toggle("is-stuck", bar.getBoundingClientRect().top <= top + 1 && window.scrollY > 0);
    };
    place();
    window.addEventListener("scroll", place, { passive: true });
    window.addEventListener("resize", place);
  }

  // Filter, sort, category and page changes dim the grid while the next page loads.
  var results = document.querySelector("[data-results]");
  var dim = function () { if (results) results.classList.add("is-loading"); };
  window.addEventListener("pageshow", function () { if (results) results.classList.remove("is-loading"); });
  var filters = document.getElementById("filters");
  if (filters) filters.addEventListener("submit", dim);
  document.querySelectorAll(".pills a, .chips a, .chip-clear, .pager a").forEach(function (a) { a.addEventListener("click", function (e) { if (!e.metaKey && !e.ctrlKey && !e.shiftKey) dim(); }); });

  // Changing the sort order applies it straight away.
  document.querySelectorAll("select[data-autosubmit]").forEach(function (select) {
    select.addEventListener("change", function () { if (select.form) { dim(); select.form.submit(); } });
  });

  // Small status toast that reuses the shell's toast styling.
  function say(text, kind) {
    var region = document.querySelector(".toasts");
    if (!region) {
      region = document.createElement("div");
      region.className = "toasts";
      region.setAttribute("role", "region");
      region.setAttribute("aria-label", "Notifications");
      document.body.appendChild(region);
    }
    var toast = document.createElement("p");
    toast.className = "toast toast--" + (kind || "success");
    toast.setAttribute("role", "status");
    toast.textContent = text;
    region.appendChild(toast);
    setTimeout(function () {
      toast.classList.add("is-leaving");
      setTimeout(function () { toast.remove(); }, 300);
    }, 3500);
  }

  function post(form) {
    return fetch(form.getAttribute("action"), {
      method: "POST",
      body: new FormData(form),
      credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", "Accept": "application/json" }
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) { return { status: response.status, data: data }; });
    });
  }

  function setCount(selector, count, label) {
    document.querySelectorAll(selector).forEach(function (el) {
      el.textContent = count;
      if (selector === "[data-wishlist-count]") el.hidden = !count;
      var link = el.closest("a");
      if (link && label) link.setAttribute("aria-label", label(count));
    });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    // cart.js (registered first) already handled this add-to-cart submit.
    if (event.defaultPrevented || !window.fetch || !form.matches) return;

    if (form.matches("[data-wish-form]")) {
      event.preventDefault();
      var heart = form.querySelector(".wish-btn");
      heart.classList.add("is-loading");
      post(form).then(function (result) {
        heart.classList.remove("is-loading");
        if (result.status === 401 && result.data.login) { window.location.href = result.data.login; return; }
        if (!result.data.ok) { say(result.data.message || "Could not update your wishlist. Try again.", "error"); return; }
        heart.setAttribute("aria-pressed", result.data.wishlisted ? "true" : "false");
        setCount("[data-wishlist-count]", result.data.count, function (n) { return "Wishlist, " + n + " saved"; });
        say(result.data.message, "success");
      }).catch(function () { heart.classList.remove("is-loading"); form.submit(); });
      return;
    }

    if (form.matches("[data-cart-form]")) {
      event.preventDefault();
      var button = form.querySelector("button[type=submit]");
      var label = button.querySelector("span");
      var original = label.textContent;
      button.disabled = true;
      post(form).then(function (result) {
        button.disabled = false;
        if (!result.data || (!result.data.ok && !result.data.message)) {
          // The server answered with a page, not JSON: the item was handled, so show the page's own message.
          window.location.reload();
          return;
        }
        if (!result.data.ok) { say(result.data.message, "error"); return; }
        setCount(".cart-tag b", result.data.count, null);
        var tag = document.querySelector(".cart-tag");
        if (tag) tag.setAttribute("aria-label", "Cart, " + result.data.count + " item" + (result.data.count === 1 ? "" : "s"));
        label.textContent = "Added to cart";
        say(result.data.message || "Added to your cart.", "success");
        setTimeout(function () { label.textContent = original; }, 1800);
      }).catch(function () { button.disabled = false; form.submit(); });
    }
  }, true);
})();
