/* Account pages: password show/hide, live password rule hints, error focus, print button.
   Every page works without this file; it only adds convenience. */
(function () {
  "use strict";

  // Show/hide toggles. The buttons ship hidden so a no-JS visitor never sees a dead control.
  document.querySelectorAll("[data-pw-toggle]").forEach(function (button) {
    var input = button.parentElement.querySelector("input");
    var text = button.querySelector("span");
    if (!input) return;
    button.hidden = false;
    button.addEventListener("click", function () {
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      button.setAttribute("aria-pressed", show ? "true" : "false");
      button.setAttribute("aria-label", (show ? "Hide " : "Show ") + (input.labels && input.labels[0] ? input.labels[0].firstChild.textContent.trim().toLowerCase() : "password"));
      if (text) text.textContent = show ? "Hide" : "Show";
    });
  });

  // Live rule hints. The server still checks everything, including common passwords.
  document.querySelectorAll("[data-password-form]").forEach(function (form) {
    var rules = form.querySelector("[data-pw-rules]");
    var first = form.querySelector("input[autocomplete=new-password]");
    var second = form.querySelectorAll("input[autocomplete=new-password]")[1];
    if (!rules || !first || !second) return;
    function mark(name, met, started) {
      var item = rules.querySelector('[data-rule="' + name + '"]');
      if (!item) return;
      item.classList.toggle("is-met", met);
      item.classList.toggle("is-open", started && !met);
      var state = item.querySelector("[data-state]");
      if (state) state.textContent = met ? " (met)" : started ? " (not met yet)" : "";
    }
    function check() {
      var value = first.value, again = second.value;
      var min = parseInt((rules.querySelector('[data-rule="length"]') || {}).dataset.min || "8", 10);
      var started = value.length > 0;
      mark("length", value.length >= min, started);
      mark("numeric", started && !/^\d+$/.test(value), started);
      mark("match", started && again.length > 0 && value === again, again.length > 0);
    }
    first.addEventListener("input", check);
    second.addEventListener("input", check);
    check();
  });

  // When the server sends the form back with errors, move focus to the summary so the problem is read first.
  var summary = document.querySelector("[data-error-summary]");
  if (summary) summary.focus({ preventScroll: false });

  // Print button on the receipt.
  document.querySelectorAll("[data-print]").forEach(function (button) {
    button.hidden = false;
    var fallback = document.querySelector("[data-print-fallback]");
    if (fallback) fallback.hidden = true;
    button.addEventListener("click", function () { window.print(); });
  });
})();
