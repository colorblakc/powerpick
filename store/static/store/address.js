/* Structured Indian address: the State choice fills the City list from india-cities.json.
   Without JavaScript (or if the file fails to load) City stays a text input with a datalist. */
(function () {
  var roots = document.querySelectorAll('[data-address-form]');
  if (!roots.length) return;
  var OTHER = '__other__';
  var cache = null;

  function load(url) {
    if (!cache) cache = fetch(url, { credentials: 'same-origin' }).then(function (r) { if (!r.ok) throw 0; return r.json(); });
    return cache;
  }

  function enhance(root, cities) {
    var state = root.querySelector('[data-addr-state]');
    var input = root.querySelector('[data-addr-city]');
    if (!state || !input || input.dataset.enhanced) return;
    input.dataset.enhanced = '1';
    var list = document.getElementById(input.getAttribute('list'));
    if (list) list.remove();
    input.removeAttribute('list');

    var required = input.required;
    var id = input.id;
    var select = document.createElement('select');
    select.id = id;
    ['aria-describedby', 'aria-invalid'].forEach(function (a) { if (input.hasAttribute(a)) select.setAttribute(a, input.getAttribute(a)); });
    select.setAttribute('autocomplete', 'address-level2');
    select.required = required;
    input.id = id + '_other';
    input.setAttribute('aria-label', 'City name');
    input.placeholder = 'Type your city';
    input.parentNode.insertBefore(select, input);

    function option(value, text, extra) {
      var o = document.createElement('option');
      o.value = value; o.textContent = text;
      if (extra) o.disabled = true;
      return o;
    }
    function showOther(on) {
      input.hidden = !on;
      input.required = on && required;
    }
    function fill(keep) {
      var names = cities[state.value] || [];
      var current = keep;
      select.innerHTML = '';
      if (!state.value) {
        select.appendChild(option('', 'Choose a state first'));
        select.disabled = true;
        showOther(false);
        input.value = '';
        return;
      }
      select.disabled = false;
      select.appendChild(option('', 'Select city'));
      names.forEach(function (n) { select.appendChild(option(n, n)); });
      select.appendChild(option(OTHER, 'Other city'));
      if (current && names.indexOf(current) > -1) { select.value = current; showOther(false); input.value = current; }
      else if (current) { select.value = OTHER; showOther(true); input.value = current; }
      else { select.value = ''; showOther(false); input.value = ''; }
    }

    fill(input.value.trim());
    state.addEventListener('change', function () {
      var typedOther = select.value === OTHER ? input.value : '';
      fill(typedOther);
    });
    select.addEventListener('change', function () {
      if (select.value === OTHER) { input.value = ''; showOther(true); input.focus(); }
      else { input.value = select.value; showOther(false); }
    });
    var form = root.closest('form');
    if (form) form.addEventListener('submit', function () {
      if (select.value && select.value !== OTHER) input.value = select.value;
    });
  }

  roots.forEach(function (root) {
    var pin = root.querySelector('[autocomplete=postal-code]');
    if (pin) pin.addEventListener('input', function () { pin.value = pin.value.replace(/\D/g, '').slice(0, 6); });
  });

  roots.forEach(function (root) {
    load(root.dataset.citiesUrl).then(function (cities) { enhance(root, cities); }).catch(function () {});
  });
})();
