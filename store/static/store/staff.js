/* Staff workspace behaviour: the mobile menu, filters that apply on change, product image preview
   and stock changes that save in place. Every one of these also works as a plain form without scripts. */
(function () {
  "use strict";

  // Chart bars grow in once, left to right (the stagger index feeds motion.css).
  document.querySelectorAll(".chart .bar").forEach(function (bar, index) { bar.style.setProperty("--i", index); });

  // Mobile menu: the rail slides down from the top, Escape and the backdrop close it.
  var rail = document.getElementById("staff-rail");
  var scrim = document.querySelector("[data-staff-scrim]");
  var opener = document.querySelector("[data-staff-open]");
  function setRail(open) {
    if (!rail) return;
    rail.classList.toggle("is-open", open);
    document.body.classList.toggle("rail-open", open);
    if (scrim) scrim.hidden = !open;
    if (opener) opener.setAttribute("aria-expanded", open ? "true" : "false");
    if (open) {
      var first = rail.querySelector("a[aria-current], a");
      if (first) first.focus();
    } else if (opener && document.activeElement && rail.contains(document.activeElement)) {
      opener.focus();
    }
  }
  if (opener) opener.addEventListener("click", function () { setRail(!rail.classList.contains("is-open")); });
  document.querySelectorAll("[data-staff-close]").forEach(function (button) {
    button.addEventListener("click", function () { setRail(false); });
  });
  if (scrim) scrim.addEventListener("click", function () { setRail(false); });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && rail && rail.classList.contains("is-open")) setRail(false);
  });
  if (window.matchMedia) {
    window.matchMedia("(min-width: 961px)").addEventListener("change", function (event) {
      if (event.matches) setRail(false);
    });
  }

  // Select filters apply as soon as they change; the Apply button stays for keyboard and no-script use.
  document.querySelectorAll("form.filters select, form.filters input[type=checkbox], form.filters input[type=date]").forEach(function (control) {
    control.addEventListener("change", function () { control.form.submit(); });
  });

  // Product image: show the chosen file before saving.
  var file = document.querySelector("[data-image-input]");
  var preview = document.querySelector("[data-image-preview]");
  if (file && preview) {
    file.addEventListener("change", function () {
      var chosen = file.files && file.files[0];
      if (!chosen) return;
      var big = chosen.size > 3000000;
      var okType = /^image\/(jpeg|png|webp)$/.test(chosen.type);
      var note = document.querySelector("[data-image-note]");
      if (note) note.textContent = big || !okType ? "Choose a JPEG, PNG or WebP under 3 MB." : chosen.name;
      if (big || !okType) { file.value = ""; return; }
      var img = preview.querySelector("img");
      if (!img) {
        preview.textContent = "";
        preview.classList.remove("is-empty");
        img = document.createElement("img");
        img.alt = "Preview of the chosen product image";
        preview.appendChild(img);
      }
      img.src = URL.createObjectURL(chosen);
    });
  }

  // Stock forms save in place: the row updates, no page reload, no lost scroll position.
  document.querySelectorAll("form[data-stock]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.fetch) return;
      event.preventDefault();
      var row = form.closest("[data-row]");
      var note = row && row.querySelector(".row-note");
      var button = form.querySelector("button");
      if (button) button.classList.add("is-loading");
      fetch(form.action, { method: "POST", body: new FormData(form), headers: { "X-Requested-With": "fetch" }, credentials: "same-origin" })
        .then(function (response) { return response.json(); })
        .then(function (data) {
          if (note) {
            note.textContent = data.message;
            note.className = "row-note " + (data.ok ? "is-ok" : "is-error");
            note.setAttribute("role", data.ok ? "status" : "alert");
          }
          if (data.ok && row) {
            var gauge = row.querySelector("[data-gauge]");
            if (gauge) gauge.innerHTML = data.gauge;
            var setter = row.querySelector("input[name=quantity]");
            if (setter) setter.value = data.stock;
            var adder = row.querySelector("input[name=add]");
            if (adder) adder.value = "";
          }
        })
        .catch(function () {
          if (note) { note.textContent = "Could not save. Check your connection and try again."; note.className = "row-note is-error"; }
        })
        .then(function () { if (button) button.classList.remove("is-loading"); });
    });
  });
})();
