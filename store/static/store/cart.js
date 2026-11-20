/* Cart behaviour for every page.
   1. Any add-to-cart form (action ends in /cart/<id>/ with action=add) submits through fetch, updates the
      masthead count and shows a toast. If anything goes wrong it falls back to a normal form submit.
   2. On the cart page, quantity steppers and Remove update through fetch with totals and an aria-live message.
   Without JavaScript every form still posts normally and the server redirects back. */
(function () {
  "use strict";

  var CART_PATH = /\/cart\/\d+\/$/;
  var DEBOUNCE = 450;

  function money(value) {
    var n = Number(value);
    return isFinite(n) ? n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : value;
  }

  function qs(selector, root) { return (root || document).querySelector(selector); }
  function qsa(selector, root) { return Array.prototype.slice.call((root || document).querySelectorAll(selector)); }

  // ---- Shared pieces: masthead count, toasts, live region ---------------------------------------------------

  function setMastheadCount(count) {
    var tag = qs(".cart-tag");
    if (!tag) return;
    var badge = qs("b", tag);
    if (badge) badge.textContent = count;
    tag.setAttribute("aria-label", "Cart, " + count + " item" + (count === 1 ? "" : "s"));
  }

  function svgIcon(id, small) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", small ? "i i--sm" : "i");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(ns, "use");
    use.setAttribute("href", "#" + id);
    svg.appendChild(use);
    return svg;
  }

  function toast(message, kind) {
    var holder = qs(".toasts");
    if (!holder) {
      holder = document.createElement("div");
      holder.className = "toasts";
      holder.setAttribute("role", "region");
      holder.setAttribute("aria-label", "Notifications");
      var main = qs("main");
      document.body.insertBefore(holder, main || document.body.firstChild);
    }
    var item = document.createElement("p");
    item.className = "toast toast--" + kind;
    item.setAttribute("role", kind === "error" ? "alert" : "status");
    item.appendChild(svgIcon(kind === "success" ? "i-check" : kind === "error" ? "i-alert" : "i-info"));
    var text = document.createElement("span");
    text.textContent = message;
    item.appendChild(text);
    var close = document.createElement("button");
    close.type = "button";
    close.setAttribute("aria-label", "Dismiss");
    close.appendChild(svgIcon("i-x", true));
    item.appendChild(close);
    holder.appendChild(item);
    while (qsa(".toast", holder).length > 3) holder.removeChild(holder.firstElementChild);
    function leave() {
      item.classList.add("is-leaving");
      setTimeout(function () { if (item.parentNode) item.parentNode.removeChild(item); }, 200);
    }
    close.addEventListener("click", leave);
    if (kind !== "error") setTimeout(leave, 4500);
  }

  var live = null;
  function announce(message) {
    live = live || qs("#cart-live");
    if (!live) return;
    live.textContent = "";
    setTimeout(function () { live.textContent = message; }, 40);
  }

  // ---- Talking to change_cart ---------------------------------------------------------------------------------

  // Resolves with the parsed JSON reply, or rejects when the server answered with anything else
  // (a login page, a CSRF failure, a network error). Callers then fall back to a normal submit.
  function sendCart(url, data, signal) {
    return fetch(url, {
      method: "POST", body: data, signal: signal, credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", "Accept": "application/json" }
    }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") < 0) throw new Error("not json");
      return response.json();
    });
  }

  function nativeSubmit(form, submitter) {
    form.dataset.nativeSubmit = "1";
    if (form.requestSubmit) { form.requestSubmit(submitter && submitter.form === form ? submitter : undefined); return; }
    if (submitter && submitter.name) {
      var hidden = document.createElement("input");
      hidden.type = "hidden"; hidden.name = submitter.name; hidden.value = submitter.value;
      form.appendChild(hidden);
    }
    form.submit();
  }

  function formDataFor(form, submitter) {
    var data = new FormData(form);
    if (submitter && submitter.name) data.set(submitter.name, submitter.value);
    return data;
  }

  function stopBusy(form) {
    qsa("button.is-loading", form).forEach(function (button) {
      button.classList.remove("is-loading");
      button.removeAttribute("aria-busy");
    });
  }

  // ---- 1. Add to cart from any page ---------------------------------------------------------------------------

  function addToCart(form, submitter) {
    var data = formDataFor(form, submitter);
    var busyButton = submitter || qs("button[type=submit], button:not([type])", form);
    if (busyButton) { busyButton.classList.add("is-loading"); busyButton.setAttribute("aria-busy", "true"); }
    sendCart(form.getAttribute("action"), data).then(function (reply) {
      if (typeof reply.count === "number") setMastheadCount(reply.count);
      if (reply.ok && window.PPMotion) window.PPMotion.added(busyButton);
      toast(reply.message || (reply.ok ? "Added to your cart" : "That could not be added"), reply.ok ? "success" : "error");
      document.dispatchEvent(new CustomEvent("cart:changed", { detail: reply }));
    }).catch(function () {
      nativeSubmit(form, submitter);
    }).then(function () {
      if (busyButton) { busyButton.classList.remove("is-loading"); busyButton.removeAttribute("aria-busy"); }
    });
  }

  // ---- 2. Cart page -------------------------------------------------------------------------------------------

  var page = qs("[data-cart-page]");

  function setTotals(reply) {
    qsa("[data-total]").forEach(function (node) { var next = "₹" + money(reply.total); if (node.textContent !== next && window.PPMotion) window.PPMotion.tick(node); node.textContent = next; });
    qsa("[data-count]").forEach(function (node) { node.textContent = reply.count; });
    var sub = qs("[data-cart-sub]");
    if (sub) sub.textContent = reply.count + " item" + (reply.count === 1 ? "" : "s") + ". Check quantities, then continue to checkout.";
  }

  function refreshCta() {
    var blocked = qsa(".cart-line[data-blocked='1']").length > 0;
    qsa("[data-cta='ready']").forEach(function (node) { node.hidden = blocked; });
    qsa("[data-cta='blocked']").forEach(function (node) { node.hidden = !blocked; });
  }

  function showEmpty() {
    var layout = qs("[data-cart-layout]");
    var template = qs("#cart-empty-tpl");
    if (!layout || !template) { window.location.reload(); return; }
    layout.parentNode.replaceChild(template.content.cloneNode(true), layout);
    var steps = qs(".steps", page);
    if (steps) steps.parentNode.removeChild(steps);
    var sub = qs("[data-cart-sub]");
    if (sub) sub.parentNode.removeChild(sub);
    var heading = qs("#cart-heading");
    if (heading) heading.focus();
  }

  function removeLine(line) {
    var next = line.nextElementSibling || line.previousElementSibling;
    line.parentNode.removeChild(line);
    if (!qs(".cart-line")) { showEmpty(); return; }
    var target = next && qs(".cart-remove", next);
    if (target) target.focus();
  }

  function applyLine(line, reply) {
    var input = qs(".qty input", line);
    if (reply.quantity === 0) { removeLine(line); return; }
    line.dataset.quantity = reply.quantity;
    var lineTotal = qs("[data-line-total]", line);
    if (lineTotal.textContent !== "₹" + money(reply.line_total) && window.PPMotion) window.PPMotion.tick(lineTotal);
    lineTotal.textContent = "₹" + money(reply.line_total);
    if (input) {
      input.max = String(Math.max(reply.quantity, reply.stock));
      input.value = reply.quantity;
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    var stillBlocked = !reply.available || reply.quantity > reply.stock;
    line.dataset.blocked = stillBlocked ? "1" : "0";
    if (!stillBlocked) {
      line.classList.remove("is-blocked");
      qsa(".cart-warn", line).forEach(function (node) { node.parentNode.removeChild(node); });
    }
  }

  function sendLine(line, form, data, submitter) {
    // A newer change to the same line cancels the request still in flight, so replies cannot arrive out of order.
    if (line.__controller) line.__controller.abort();
    var controller = window.AbortController ? new AbortController() : null;
    line.__controller = controller;
    line.classList.add("is-updating");
    line.setAttribute("aria-busy", "true");
    var confirmed = parseInt(line.dataset.quantity, 10);
    sendCart(form.getAttribute("action"), data, controller && controller.signal).then(function (reply) {
      if (line.__controller !== controller) return;
      setMastheadCount(reply.count);
      setTotals(reply);
      var input = qs(".qty input", line);
      if (reply.ok) {
        applyLine(line, reply);
        refreshCta();
      } else {
        if (input) { input.value = confirmed; input.dispatchEvent(new Event("change", { bubbles: true })); }
        toast(reply.message, "error");
      }
      announce(reply.message + (reply.ok ? ". Cart total ₹" + money(reply.total) + ", " + reply.count + " item" + (reply.count === 1 ? "" : "s") + "." : ""));
    }).catch(function (error) {
      if (error && error.name === "AbortError") return;
      // The server could not be reached or answered with a page. Let it handle this change the normal way.
      nativeSubmit(form, submitter);
    }).then(function () {
      if (line.__controller === controller) {
        line.__controller = null;
        line.classList.remove("is-updating");
        line.removeAttribute("aria-busy");
      }
      stopBusy(form);
    });
  }

  function submitLine(form, submitter) {
    var line = form.closest(".cart-line");
    if (!line) return;
    clearTimeout(line.__timer);
    var data = formDataFor(form, submitter);
    if (!data.get("action")) data.set("action", "set");
    sendLine(line, form, data, submitter);
  }

  if (page) {
    qsa(".cart-line").forEach(function (line) {
      var form = qs(".cart-controls", line);
      var input = qs(".qty input", line);
      if (!input || !form) return;
      input.addEventListener("change", function () {
        var value = parseInt(input.value, 10);
        if (!value || value < 1) { input.value = line.dataset.quantity; return; }
        if (String(value) === line.dataset.quantity) return;
        clearTimeout(line.__timer);
        line.__timer = setTimeout(function () {
          var data = new FormData(form);
          data.set("action", "set");
          sendLine(line, form, data, qs(".cart-update", form));
        }, DEBOUNCE);
      });
    });
  }

  // ---- Submit routing (capture phase so it runs before shell.js adds its own loading state) -------------------

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement) || event.defaultPrevented) return;
    if (form.dataset.nativeSubmit) { delete form.dataset.nativeSubmit; return; }
    if (!window.fetch || !window.FormData) return;
    var path = "";
    try { path = new URL(form.getAttribute("action") || "", window.location.href).pathname; } catch (error) { return; }
    if (!CART_PATH.test(path)) return;
    var submitter = event.submitter || null;
    if (form.hasAttribute("data-cart-form") && page) {
      event.preventDefault();
      event.stopPropagation();
      submitLine(form, submitter);
      return;
    }
    var data = formDataFor(form, submitter);
    if (data.get("action") !== "add") return;
    event.preventDefault();
    event.stopPropagation();
    addToCart(form, submitter);
  }, true);

  // Coming back through the back button can restore a button that was still showing its spinner.
  window.addEventListener("pageshow", function (event) {
    if (event.persisted) qsa("button.is-loading").forEach(function (button) { button.classList.remove("is-loading"); button.removeAttribute("aria-busy"); });
  });

  // A form can ask for focus on load, for example a checkout error summary.
  var autofocus = qs("[data-autofocus]");
  if (autofocus) autofocus.focus();
})();
