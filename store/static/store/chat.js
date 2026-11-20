// Power Pick Assistant widget. Everything the model returns is rendered with DOM nodes and textContent,
// never innerHTML, so replies cannot inject markup. The widget is an enhancement: the launcher only
// appears once this script has run.
(() => {
  const root = document.getElementById('pp-help');
  if (!root) return;
  const path = location.pathname;
  if (path.startsWith('/staff/') || path.startsWith('/admin/')) return; // staff workspaces have no shopper chat

  const launch = root.querySelector('.pp-launch');
  const panel = root.querySelector('.pp-panel');
  const log = root.querySelector('.pp-log');
  const chipBox = root.querySelector('.pp-chips');
  const form = root.querySelector('.pp-form');
  const field = form.elements.question;
  const send = form.querySelector('.pp-send');
  const KEY = 'pp-chat-v1';
  const KEEP = 12;
  const calm = window.matchMedia('(prefers-reduced-motion: reduce)');

  const name = (root.dataset.name || '').trim();
  const signedIn = root.dataset.signedIn === '1';
  let messages = [];      // {role, content, products?, scripted?}
  let busy = false;
  let lastChips = null;   // suggestions from the latest reply

  // ---------- page context ----------
  function pageKind() {
    const view = root.dataset.view || '';
    if (view === 'detail' || /^\/products\/\d+\/?$/.test(path)) return 'product';
    if (view === 'cart' || path.startsWith('/cart')) return 'cart';
    if (view === 'checkout' || path.startsWith('/checkout')) return 'checkout';
    if (['orders', 'order_detail', 'history'].includes(view) || /^\/(orders|payment-history)/.test(path)) return 'orders';
    if (view === 'catalogue' || path.startsWith('/shop')) return 'shop';
    if (view === 'home' || path === '/') return 'home';
    return 'other';
  }
  const kind = pageKind();
  const CHIPS = {
    home: ['Which MCB for a light circuit?', 'Do you have a 32A MCB?', 'How do I pay for an order?'],
    shop: ['Which MCB for a light circuit?', 'Cheapest LED bulb?', 'Help me pick a wire size'],
    product: ['Is this in stock?', 'What rating do I need?', 'Show similar options'],
    cart: ['Is everything in my cart in stock?', 'How do I pay?', 'Can I change a quantity?'],
    checkout: ['How do I pay?', 'Is my payment safe?', 'What if payment fails?'],
    orders: ['Where is my last order?', 'How do I cancel an unpaid order?', 'Where is my receipt?'],
    other: ['Help me choose a product', 'How do I pay for an order?', 'How do I track an order?'],
  };
  function startChips() {
    const chips = (CHIPS[kind] || CHIPS.other).slice();
    if (signedIn && (kind === 'home' || kind === 'shop')) chips[2] = 'Where is my last order?';
    if (!signedIn) return chips.filter(c => !/my last order|my cart/i.test(c)).slice(0, 3);
    return chips.slice(0, 3);
  }
  if (kind === 'cart' || kind === 'checkout') root.classList.add('is-compact');

  // ---------- storage (sessionStorage may be unavailable) ----------
  function load() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(KEY) || '[]');
      if (Array.isArray(saved)) messages = saved.filter(m => m && (m.role === 'user' || m.role === 'assistant') && typeof m.content === 'string').slice(-KEEP);
    } catch (e) { messages = []; }
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(messages.slice(-KEEP))); } catch (e) { /* private mode: keep going */ }
  }

  // ---------- safe markdown-lite ----------
  const INLINE = /\*\*(.+?)\*\*|\[([^\]]{1,80})\]\((\/[^)\s]{0,200})\)/g;
  function inline(parent, text) {
    let last = 0, m;
    INLINE.lastIndex = 0;
    while ((m = INLINE.exec(text))) {
      if (m.index > last) parent.append(text.slice(last, m.index));
      if (m[1] !== undefined) {
        const strong = document.createElement('strong');
        strong.textContent = m[1];
        parent.append(strong);
      } else if (m[3].startsWith('/') && !m[3].startsWith('//')) {
        const a = document.createElement('a');
        a.href = m[3];
        a.textContent = m[2];
        parent.append(a);
      } else {
        parent.append(m[0]);
      }
      last = INLINE.lastIndex;
    }
    if (last < text.length) parent.append(text.slice(last));
  }
  function render(container, text) {
    let list = null, para = null;
    const flush = () => { list = null; para = null; };
    String(text).replace(/\r/g, '').split('\n').forEach(raw => {
      const line = raw.trim();
      if (!line) { flush(); return; }
      const bullet = line.match(/^[-*•]\s+(.*)$/);
      const number = line.match(/^\d+[.)]\s+(.*)$/);
      if (bullet || number) {
        const tag = bullet ? 'UL' : 'OL';
        if (!list || list.tagName !== tag) { list = document.createElement(tag.toLowerCase()); container.append(list); }
        para = null;
        const li = document.createElement('li');
        inline(li, (bullet || number)[1]);
        list.append(li);
      } else {
        list = null;
        if (!para) { para = document.createElement('p'); container.append(para); }
        else para.append(document.createElement('br'));
        inline(para, line);
      }
    });
  }

  // ---------- product mini-cards ----------
  function rupees(value) {
    const n = Number(value);
    return '₹' + (Number.isFinite(n) ? n.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : String(value));
  }
  function stockTag(stock) {
    const tag = document.createElement('span');
    const n = Number(stock) || 0;
    let tier = 'high', label = 'In stock';
    if (n <= 0) { tier = 'out'; label = 'Out of stock'; }
    else if (n <= 5) { tier = 'last'; label = 'Last ' + n; }
    else if (n <= 15) { tier = 'low'; label = 'Low · ' + n + ' left'; }
    tag.className = 'pp-stock pp-stock--' + tier;
    if (tier !== 'out') {
      const bars = document.createElement('span');
      bars.setAttribute('aria-hidden', 'true');
      for (let i = 0; i < 3; i++) bars.append(document.createElement('i'));
      tag.append(bars);
    }
    tag.append(label);
    return tag;
  }
  function safeUrl(url) { return typeof url === 'string' && url.startsWith('/') && !url.startsWith('//') ? url : '#'; }
  function cards(products) {
    const list = document.createElement('ul');
    list.className = 'pp-cards';
    list.setAttribute('aria-label', 'Products mentioned');
    products.slice(0, 4).forEach(p => {
      const li = document.createElement('li');
      const a = document.createElement('a');
      a.className = 'pp-card';
      a.href = safeUrl(p.url);
      let thumb;
      if (p.image && typeof p.image === 'string' && p.image.startsWith('/')) {
        thumb = document.createElement('img');
        thumb.className = 'pp-card-img';
        thumb.src = p.image;
        thumb.alt = '';
        thumb.width = 48; thumb.height = 48; thumb.loading = 'lazy';
        thumb.addEventListener('error', () => thumb.replaceWith(placeholder()));
      } else thumb = placeholder();
      const body = document.createElement('span');
      body.className = 'pp-card-body';
      const title = document.createElement('span');
      title.className = 'pp-card-name';
      title.textContent = p.name;
      const meta = document.createElement('span');
      meta.className = 'pp-card-meta';
      const price = document.createElement('span');
      price.className = 'pp-card-price';
      price.textContent = rupees(p.price);
      meta.append(price, stockTag(p.stock));
      body.append(title, meta);
      a.append(thumb, body);
      li.append(a);
      list.append(li);
    });
    return list;
  }
  function placeholder() {
    const box = document.createElement('span');
    box.className = 'pp-card-img';
    box.innerHTML = '<svg class="i" aria-hidden="true"><use href="#i-box-open"/></svg>'; // static markup only
    return box;
  }

  // ---------- mascot ----------
  const faceUrl = root.dataset.face || '';
  function avatar() {
    const img = document.createElement('img');
    img.className = 'pp-avatar';
    img.src = faceUrl;
    img.alt = '';
    img.width = 28; img.height = 28;
    return img;
  }
  function botRow() {
    const row = document.createElement('div');
    row.className = 'pp-msg pp-msg--bot';
    const body = document.createElement('div');
    body.className = 'pp-msg-body';
    row.append(avatar(), body);
    return {row, body};
  }

  // ---------- message rendering ----------
  function reveal(node, stick) {
    const behavior = calm.matches ? 'auto' : 'smooth';
    if (node.offsetHeight > log.clientHeight - 24 && !node.classList.contains('pp-msg--user')) log.scrollTo({top: node.offsetTop - 12, behavior});
    else if (stick) log.scrollTo({top: log.scrollHeight, behavior});
  }
  function addMessage(msg, stick = true) {
    const user = msg.role === 'user';
    let row, body;
    if (user) {
      row = document.createElement('div');
      row.className = 'pp-msg pp-msg--user';
      body = row;
    } else ({row, body} = botRow());
    const bubble = document.createElement('div');
    bubble.className = 'pp-bubble';
    if (user) bubble.textContent = msg.content;
    else render(bubble, msg.content);
    body.append(bubble);
    if (msg.products && msg.products.length) body.append(cards(msg.products));
    log.append(row);
    reveal(row, stick);
    return row;
  }
  function typing() {
    const {row, body} = botRow();
    const dots = document.createElement('div');
    dots.className = 'pp-typing';
    dots.setAttribute('role', 'status');
    dots.innerHTML = '<span class="pp-sr">Power Pick Assistant is typing</span><i></i><i></i><i></i>'; // static markup only
    body.append(dots);
    log.append(row);
    log.scrollTo({top: log.scrollHeight});
    return row;
  }
  function showChips(list) {
    chipBox.replaceChildren();
    (list || []).slice(0, 3).forEach(text => {
      const b = document.createElement('button');
      b.type = 'button';
      b.textContent = text;
      b.addEventListener('click', () => ask(text));
      chipBox.append(b);
    });
    chipBox.hidden = !chipBox.children.length;
    chipBox.classList.toggle('is-slim', messages.some(m => m.role === 'user'));
  }

  // ---------- greeting (scripted, no API call) ----------
  function greeting() {
    const h = new Date().getHours();
    const part = h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
    const hello = name ? part + ', ' + name + '.' : part + '.';
    return hello + ' I can help you find products, check stock and price, suggest the right rating for a job, and explain ordering, payment and tracking.\n\nWhat are you working on?';
  }
  function showGreeting() {
    const msg = {role: 'assistant', content: greeting(), scripted: true};
    messages = [msg];
    save();
    log.replaceChildren();
    addMessage(msg, false);
    lastChips = null;
    showChips(startChips());
  }
  function paint() {
    log.replaceChildren();
    messages.forEach(m => addMessage(m, false));
    log.scrollTop = log.scrollHeight;
    showChips(lastChips || startChips());
  }

  // ---------- open / close ----------
  function setOpen(open) {
    panel.hidden = !open;
    launch.hidden = open;
    launch.setAttribute('aria-expanded', String(open));
    if (open) {
      if (!messages.length) showGreeting(); else paint();
      keepClear();
      const touch = window.matchMedia('(pointer: coarse)').matches;
      (touch ? panel.querySelector('.pp-icon') : field).focus({preventScroll: true});
    } else {
      launch.focus({preventScroll: true});
    }
  }
  launch.addEventListener('click', () => setOpen(true));
  root.querySelector('[data-pp-close]').addEventListener('click', () => setOpen(false));
  root.querySelector('[data-pp-clear]').addEventListener('click', () => {
    if (busy) return;
    showGreeting();
    field.value = '';
    field.focus({preventScroll: true});
  });
  root.addEventListener('keydown', e => {
    if (e.key === 'Escape' && !panel.hidden) { e.stopPropagation(); setOpen(false); }
  });

  // Phones: size the sheet to the visible area so the on-screen keyboard never hides the composer.
  function keepClear() {
    const vv = window.visualViewport;
    if (!vv || panel.hidden) return;
    const keyboard = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
    root.style.setProperty('--pp-kb', keyboard + 'px');
    root.style.setProperty('--pp-sheet-h', vv.height + 'px');
  }
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', keepClear);
    window.visualViewport.addEventListener('scroll', keepClear);
  }

  // ---------- asking ----------
  function history(skipLast) {
    let real = messages.filter(m => !m.scripted);
    if (skipLast) real = real.slice(0, -1); // the question being retried is already stored
    return real.slice(-6).map(m => ({role: m.role, content: m.content.slice(0, 500)}));
  }
  function fail(question, text) {
    const {row, body} = botRow();
    const bubble = document.createElement('div');
    bubble.className = 'pp-bubble pp-bubble--error';
    const p = document.createElement('p');
    p.textContent = text;
    const retry = document.createElement('button');
    retry.type = 'button';
    retry.className = 'pp-retry';
    retry.innerHTML = '<svg class="i" aria-hidden="true"><use href="#i-refresh"/></svg>'; // static markup only
    retry.append('Retry');
    retry.addEventListener('click', () => { row.remove(); ask(question, true); });
    bubble.append(p, retry);
    body.append(bubble);
    log.append(row);
    reveal(row, true);
    retry.focus({preventScroll: true});
  }
  async function ask(text, isRetry = false) {
    text = (text || '').trim();
    if (busy || text.length < 2) return;
    busy = true;
    send.disabled = true;
    chipBox.hidden = true;
    const prior = history(isRetry);
    if (!isRetry) {
      const mine = {role: 'user', content: text};
      messages.push(mine);
      addMessage(mine);
      save();
    }
    const wait = typing();
    const body = new FormData();
    body.append('question', text);
    body.append('page', path);
    body.append('history', JSON.stringify(prior));
    body.append('csrfmiddlewaretoken', form.elements.csrfmiddlewaretoken.value);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 20000);
    try {
      const response = await fetch(root.dataset.askUrl || form.action, {
        method: 'POST', body, signal: controller.signal, credentials: 'same-origin',
        headers: {'X-Requested-With': 'fetch', 'Accept': 'application/json'},
      });
      let data = null;
      try { data = await response.json(); } catch (e) { data = null; }
      wait.remove();
      if (!data || typeof data.reply !== 'string') throw new Error('bad response');
      if (response.status >= 500) throw new Error('server error');
      const reply = {role: 'assistant', content: data.reply, products: Array.isArray(data.products) ? data.products.slice(0, 4) : []};
      messages.push(reply);
      save();
      lastChips = Array.isArray(data.suggestions) && data.suggestions.length ? data.suggestions : startChips();
      showChips(lastChips);   // before scrolling, so the log's final height is settled
      addMessage(reply);
    } catch (e) {
      wait.remove();
      showChips(lastChips || startChips());
      fail(text, controller.signal.aborted
        ? 'That took too long. Check your connection and try again.'
        : 'I could not reach the shop just now. Your question is saved; try again in a moment.');
    } finally {
      clearTimeout(timer);
      busy = false;
      send.disabled = false;
      if (!panel.hidden && !document.activeElement.classList.contains('pp-retry')) field.focus({preventScroll: true});
    }
  }

  form.addEventListener('submit', e => {
    e.preventDefault();
    const text = field.value;
    if (text.trim().length < 2) { field.focus(); return; }
    field.value = '';
    ask(text);
  });

  // The product page slides a buy bar up from the bottom edge on phones; lift the launcher clear of it.
  const buybar = document.getElementById('buybar');
  if (buybar) {
    const lift = () => {
      const on = buybar.classList.contains('is-on') && getComputedStyle(buybar).display !== 'none';
      root.style.setProperty('--chat-offset', on ? buybar.offsetHeight + 'px' : '0px');
    };
    new MutationObserver(lift).observe(buybar, {attributes: true, attributeFilter: ['class']});
    window.addEventListener('resize', lift);
    lift();
  }

  // Inline the mascot file into the launcher (the file stays the source of truth) so its eyes can blink and look.
  // Until it loads, or if it fails, the plain <img> in the template stays in place.
  const face = launch.querySelector('.pp-face');
  if (faceUrl && face && window.fetch) {
    fetch(faceUrl, {credentials: 'same-origin'}).then(r => r.ok ? r.text() : Promise.reject()).then(text => {
      const doc = new DOMParser().parseFromString(text, 'image/svg+xml');
      const svg = doc.documentElement;
      if (!svg || svg.nodeName.toLowerCase() !== 'svg' || doc.querySelector('parsererror') || doc.querySelector('script')) return;
      svg.removeAttribute('role');
      svg.removeAttribute('aria-label');
      svg.setAttribute('aria-hidden', 'true');
      svg.setAttribute('focusable', 'false');
      face.querySelector('img').replaceWith(document.importNode(svg, true));
      watchPointer(face.querySelector('.eyes'));
    }).catch(() => {});
  }
  // The eyes glance toward the pointer while the launcher is showing. Skipped for reduced motion.
  function watchPointer(eyes) {
    if (!eyes || calm.matches) return;
    let waiting = false;
    document.addEventListener('pointermove', e => {
      if (waiting || launch.hidden) return;
      waiting = true;
      requestAnimationFrame(() => {
        waiting = false;
        const box = launch.getBoundingClientRect();
        const dx = e.clientX - (box.left + 24), dy = e.clientY - (box.top + box.height / 2);
        const dist = Math.hypot(dx, dy) || 1, reach = Math.min(1, dist / 260) * 5;
        eyes.style.setProperty('--look-x', (dx / dist * reach).toFixed(2) + 'px');
        eyes.style.setProperty('--look-y', (dy / dist * reach * .7).toFixed(2) + 'px');
      });
    }, {passive: true});
  }

  load();
  launch.hidden = false;
})();
