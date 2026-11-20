/* Product page behaviour: add to cart without leaving the page, wishlist toggle, sticky buy bar, photo zoom, review helpers.
   Every control also works as a plain form post if this script or the fetch fails. */
(function () {
  "use strict";
  var body = document.body;

  function csrf(form) {
    var field = form.querySelector("input[name=csrfmiddlewaretoken]");
    return field ? field.value : "";
  }

  function post(form) {
    return fetch(form.getAttribute("action"), {
      method: "POST", credentials: "same-origin", body: new FormData(form),
      headers: { "X-Requested-With": "fetch", "X-CSRFToken": csrf(form), "Accept": "application/json" }
    }).then(function (res) {
      var type = res.headers.get("content-type") || "";
      if (type.indexOf("application/json") === -1) throw new Error("not-json");
      return res.json().then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
    });
  }

  // Add to cart
  var buy = document.getElementById("buy");
  var status = document.getElementById("buy-status");
  function say(text, bad) {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("is-error", !!bad);
  }
  if (buy && window.fetch) {
    buy.addEventListener("submit", function (event) {
      event.preventDefault();
      var buttons = document.querySelectorAll("#buy-submit, #buybar .btn");
      buttons.forEach(function (b) { b.classList.add("is-loading"); });
      post(buy).then(function (result) {
        var data = result.data;
        if (result.ok && data.ok) {
          say(data.message || "Added to your cart.");
          var tag = document.querySelector(".cart-tag");
          if (tag && typeof data.count !== "undefined") {
            var badge = tag.querySelector("b");
            if (badge) badge.textContent = data.count;
            tag.setAttribute("aria-label", "Cart, " + data.count + " item" + (data.count === 1 ? "" : "s"));
          }
          // Stock may now be fully in the basket; reload to show the capped quantity and the note.
          var input = buy.querySelector("input[name=quantity]");
          var added = input ? parseInt(input.value, 10) || 1 : 1;
          var max = input ? parseInt(input.max, 10) : 0;
          if (input && max && added >= max) { window.location.reload(); return; }
          if (input && max) { input.max = max - added; input.value = 1; input.dispatchEvent(new Event("change", { bubbles: true })); }
        } else {
          say((data && data.message) || "That quantity is not available. Choose a lower amount.", true);
        }
      }).catch(function () {
        buy.submit();
      }).then(function () {
        buttons.forEach(function (b) { b.classList.remove("is-loading"); b.removeAttribute("aria-busy"); });
      });
    });
  }

  // Wishlist toggle
  var wish = document.querySelector("form[data-wishlist]");
  if (wish && window.fetch) {
    wish.addEventListener("submit", function (event) {
      event.preventDefault();
      var btn = wish.querySelector("button");
      post(wish).then(function (result) {
        var d = result.data;
        if (result.status === 401 && d.login) { window.location.href = d.login; return; }
        if (!result.ok || d.ok === false) throw new Error("failed");
        var now = typeof d.wishlisted === "boolean" ? d.wishlisted : typeof d.saved === "boolean" ? d.saved : btn.getAttribute("aria-pressed") !== "true";
        btn.setAttribute("aria-pressed", now ? "true" : "false");
        btn.querySelector("[data-wish-label]").textContent = now ? "Saved to wishlist" : "Save to wishlist";
        if (d.message) say(d.message);
      }).catch(function () {
        wish.submit();
      }).then(function () { btn.classList.remove("is-loading"); btn.removeAttribute("aria-busy"); });
    });
  }

  // Sticky buy bar: on phones, show it once the main button scrolls away, and hide it again near the footer.
  var bar = document.getElementById("buybar");
  var trigger = document.getElementById("buy-submit");
  var foot = document.querySelector(".foot");
  var mast = document.querySelector(".mast"); // the sticky masthead hides whatever scrolls under it
  if (bar && trigger && "IntersectionObserver" in window) {
    var buttonSeen = true, footSeen = false;
    function update() {
      var on = !buttonSeen && !footSeen;
      bar.classList.toggle("is-on", on);
      body.classList.toggle("pd-bar-on", on);
      if (on) bar.removeAttribute("inert"); else bar.setAttribute("inert", "");
    }
    new IntersectionObserver(function (entries) {
      buttonSeen = entries[0].isIntersecting;
      update();
    }, { rootMargin: "-" + Math.round(mast ? mast.getBoundingClientRect().height : 56) + "px 0px 0px 0px" }).observe(trigger);
    if (foot) new IntersectionObserver(function (entries) { footSeen = entries[0].isIntersecting; update(); }).observe(foot);
  }

  // Photo zoom: hover with a mouse only; the pointer position sets the zoom origin.
  var photo = document.querySelector("[data-zoom]");
  if (photo && photo.querySelector("img") && window.matchMedia("(hover: hover) and (pointer: fine)").matches &&
      !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    photo.classList.add("is-zoom");
    photo.addEventListener("pointermove", function (event) {
      var box = photo.getBoundingClientRect();
      photo.style.setProperty("--zx", ((event.clientX - box.left) / box.width * 100) + "%");
      photo.style.setProperty("--zy", ((event.clientY - box.top) / box.height * 100) + "%");
    });
  }

  // Rating bars grow once when the reviews come into view.
  var dist = document.querySelector(".dist");
  if (dist && "IntersectionObserver" in window && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    dist.classList.add("is-armed");
    var seen = new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) { requestAnimationFrame(function () { dist.classList.add("is-in"); }); seen.disconnect(); }
    }, { threshold: 0.4 });
    seen.observe(dist);
  }

  // Review form: live character count, and focus the first problem after a failed post.
  var text = document.getElementById("rev-body");
  var count = document.querySelector("[data-count]");
  if (text && count) {
    var tick = function () { count.textContent = text.value.trim().length + " / 1000"; };
    text.addEventListener("input", tick); tick();
  }
  var form = document.querySelector(".rev-form[data-has-errors]");
  if (form) {
    var bad = form.querySelector("[aria-invalid=true], .rate.has-error input");
    var alertBox = document.getElementById("rev-errors");
    if (alertBox) alertBox.scrollIntoView({ block: "center" });
    if (bad) bad.focus({ preventScroll: true });
  }
})();
