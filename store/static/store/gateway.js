/* Payment page state machine.
   States: ready, opening, waiting, verifying, success, failed, cancelled, pending, config (plus server-rendered
   closed and review). Razorpay collects card and UPI details in its own window; only its references reach Django.
   Django verifies the signature, amount, currency and capture status before it confirms anything.
   window.PowerPickPay.show(state, info) is exposed so each state can be reviewed without making a payment. */
(function () {
  "use strict";

  var root = document.getElementById("pay");
  if (!root) return;

  var STATES = ["ready", "opening", "waiting", "verifying", "success", "failed", "cancelled", "pending", "config"];
  var csrf = root.querySelector("[name=csrfmiddlewaretoken]");
  var state = root.dataset.state;
  var options = null;      // what the server gave us to open Razorpay with
  var checkout = null;     // the live Razorpay instance
  var lastError = null;    // the reason Razorpay gave for the last failed attempt
  var working = false;

  function panel(name) { return root.querySelector('[data-pay-state="' + name + '"]'); }
  function all(selector, scope) { return Array.prototype.slice.call((scope || root).querySelectorAll(selector)); }

  function show(next, info, quiet) {
    info = info || {};
    all("[data-pay-state]").forEach(function (node) { node.hidden = node.dataset.payState !== next; });
    var target = panel(next);
    if (!target) return;
    state = next;
    root.dataset.state = next;
    if (next === "failed") {
      target.querySelector("[data-fail-title]").textContent = info.title || "Payment did not go through";
      target.querySelector("[data-reason]").textContent = info.reason || "The payment could not be completed. You can try again.";
    }
    if (next === "pending") {
      if (info.reason) target.querySelector("[data-reason]").textContent = info.reason;
      target.querySelector("[data-retry-only]").hidden = !info.canRetry;
    }
    if (next === "verifying") {
      target.querySelector("[data-verify-title]").textContent = info.title || "Confirming with Razorpay";
    }
    if (next === "success") fillSuccess(target, info);
    var cancel = root.querySelector(".pay-cancel");
    if (cancel) cancel.hidden = ["opening", "waiting", "verifying", "success"].indexOf(next) >= 0;
    if (!quiet) {
      var heading = target.querySelector("h2");
      if (heading) heading.focus({ preventScroll: false });
    }
  }

  function fillSuccess(target, data) {
    if (data.order) all("[data-order-no]", target).forEach(function (node) { node.textContent = "#" + data.order; });
    if (data.reference) {
      all("[data-reference]", target).forEach(function (node) { node.textContent = data.reference; });
      var wrap = target.querySelector("[data-reference-wrap]");
      if (wrap) wrap.hidden = false;
    }
    if (data.order_url) all("[data-order-link]", target).forEach(function (node) { node.href = data.order_url; });
    if (data.receipt_url) all("[data-receipt-link]", target).forEach(function (node) { node.href = data.receipt_url; node.hidden = false; });
  }

  function PayError(message, code) {
    var error = new Error(message);
    error.code = code || "";
    return error;
  }

  function post(url, fields) {
    var body = new URLSearchParams(fields || {});
    body.set("csrfmiddlewaretoken", csrf ? csrf.value : "");
    return fetch(url, { method: "POST", body: body, credentials: "same-origin", headers: { "Accept": "application/json" } }).then(function (response) {
      var type = response.headers.get("Content-Type") || "";
      if (type.indexOf("application/json") < 0) throw PayError("Your session may have ended. Reload this page and sign in again.", "session");
      return response.json().then(function (data) {
        if (!response.ok) throw PayError(data.error || "Something went wrong. Please try again.", data.code);
        return data;
      });
    }, function () {
      throw PayError("We could not reach the server. Check your connection and try again.", "offline");
    });
  }

  function guard(event) { event.preventDefault(); event.returnValue = ""; }
  function lockPage(on) {
    window[on ? "addEventListener" : "removeEventListener"]("beforeunload", guard);
  }

  function reasonFrom(error) {
    var text = error && (error.description || error.reason);
    return text ? String(text) : "Razorpay could not complete the payment. You have not been charged for this attempt.";
  }

  // ---- Transitions --------------------------------------------------------------------------------------------

  function succeed(data) {
    lockPage(false);
    working = false;
    show("success", data);
  }

  function explain(error, fallbackTitle) {
    lockPage(false);
    working = false;
    if (error.code === "config") return show("config");
    if (error.code === "closed") { window.location.reload(); return; }
    if (error.code === "review" || error.code === "pending") return show("pending", { reason: error.message });
    show("failed", { title: fallbackTitle, reason: error.message });
  }

  function begin() {
    if (working) return;
    working = true;
    lastError = null;
    show("opening");
    lockPage(true);
    post(root.dataset.start).then(function (data) {
      if (data.paid) { succeed(data); return; }
      options = data;
      lockPage(false);
      open();
    }).catch(function (error) { explain(error, "Could not start the payment"); });
  }

  // Razorpay needs a literal colour, so read the action colour from the design tokens.
  function actionColour() {
    return getComputedStyle(document.documentElement).getPropertyValue("--blue").trim() || "#5B3DF5";
  }

  function open() {
    if (!window.Razorpay) {
      working = false;
      show("failed", { title: "Razorpay checkout did not load",
        reason: "The payment window could not load. Check your connection or any content blocker on this page, then retry." });
      return;
    }
    var settings = {
      key: options.key, order_id: options.order_id, amount: options.amount, currency: options.currency,
      name: options.name, description: options.description, prefill: options.prefill || {},
      theme: { color: actionColour() },
      modal: { confirm_close: true, ondismiss: onDismiss },
      // The server confirms the signature, amount and capture status before delivery is promised.
      handler: onPaid
    };
    checkout = new window.Razorpay(settings);
    checkout.on("payment.failed", function (response) { lastError = response && response.error; });
    show("waiting", null, true);
    checkout.open();
  }

  function onDismiss() {
    if (state === "verifying" || state === "success") return;
    working = false;
    if (lastError) {
      var reason = reasonFrom(lastError);
      // Record the failure on the server too, in case the payment is retried from another page.
      post(root.dataset.check).catch(function () {});
      show("failed", { reason: reason });
    } else {
      show("cancelled");
    }
  }

  function onPaid(response) {
    working = true;
    lastError = null;
    lockPage(true);
    show("verifying", { title: "Confirming with Razorpay" });
    post(root.dataset.verify, {
      razorpay_order_id: response.razorpay_order_id,
      razorpay_payment_id: response.razorpay_payment_id,
      razorpay_signature: response.razorpay_signature
    }).then(succeed).catch(function (error) {
      lockPage(false);
      working = false;
      if (error.code === "config") return show("config");
      show("pending", { reason: error.message + " If you were charged, do not pay again.", canRetry: false });
    });
  }

  function checkStatus() {
    if (working) return;
    working = true;
    lockPage(true);
    show("verifying", { title: "Checking the payment with Razorpay" });
    post(root.dataset.check).then(function (data) {
      if (data.paid) { succeed(data); return; }
      lockPage(false);
      working = false;
      if (data.status === "Failed") {
        show("failed", { reason: "Razorpay reports that the last attempt failed. You can try again with the same order." });
      } else {
        show("pending", { reason: "Razorpay has no confirmed payment for this order yet. If you just paid, wait a moment and check again. Otherwise you can retry.", canRetry: true });
      }
    }).catch(function (error) { explain(error, "Could not check the payment"); });
  }

  root.addEventListener("click", function (event) {
    var button = event.target.closest("[data-act]");
    if (!button || !root.contains(button)) return;
    var act = button.dataset.act;
    if (act === "pay" || act === "retry") begin();
    else if (act === "check") checkStatus();
    else if (act === "reopen") {
      if (checkout) { show("waiting", null, true); checkout.open(); } else begin();
    }
  });

  if (STATES.indexOf(state) >= 0) show(state, null, true);

  window.PowerPickPay = { show: show, get state() { return state; } };
})();
