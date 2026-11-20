/* Checkout: the payment choice changes the button wording and which payment marks are shown. */
(function () {
  var form = document.querySelector('.co-form');
  if (!form) return;
  var radios = form.querySelectorAll('input[data-method]');
  var label = form.querySelector('[data-submit-label]');
  var note = form.querySelector('[data-submit-note]');
  var strip = form.querySelector('[data-pay-online]');
  var total = form.querySelector('[name=expected_total]');
  var amount = '';
  try { amount = Number(total.value).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); } catch (e) {}
  function sync() {
    var cod = form.querySelector('input[data-method]:checked').value === 'COD';
    if (strip) strip.hidden = cod;
    if (label) label.textContent = cod ? 'Place order, pay ₹' + amount + ' on delivery' : 'Review and pay ₹' + amount;
    if (note) note.textContent = 'Prices and stock are checked again when you continue. ' +
      (cod ? 'Your order is confirmed straight away.' : 'You review the order on the next page before you pay.');
  }
  radios.forEach(function (r) { r.addEventListener('change', sync); });
  sync();
})();
