/* A symbol picker you can type into.

   The catalogue is 1,728 markets in nine families. A native <select> can only
   be scrolled, and finding VNM in it meant scrolling past every commodity,
   index and ETF first. This puts a searchable list in front of the same
   <select> rather than replacing it:

   * the <select> stays the source of truth. Every module that already reads
     `el.symbol.value`, sets it, rebuilds its options or listens for `change`
     keeps working unchanged, and so do the tests and probes that drive it;
   * picking an entry sets the value and dispatches `change`, exactly as a
     person using the native control would.

   Matching ignores Vietnamese diacritics and the `VN:` routing prefix, so
   "vingroup", "VIC" and "vic" all find VN:VIC, and exact code matches rank
   above names that merely contain the letters. */

const SymbolPicker = (() => {
  const attached = new WeakMap();
  let openFor = null;
  let shown = [];
  let cursor = 0;

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  // Diacritics off, đ to d, lower case: how people type a name in a hurry.
  const fold = (s) => String(s || '')
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/đ/g, 'd').replace(/Đ/g, 'D')
    .toLowerCase().trim();

  const pop = document.createElement('div');
  pop.className = 'sp-pop';
  pop.hidden = true;
  pop.innerHTML = `
    <input class="sp-search" type="search" autocomplete="off" spellcheck="false" />
    <div class="sp-list" role="listbox"></div>`;
  document.body.appendChild(pop);
  const search = pop.querySelector('.sp-search');
  const list = pop.querySelector('.sp-list');

  function readOptions(select) {
    const out = [];
    const seen = new Set();
    const push = (option, group) => {
      // The favourites group repeats entries from the families below it.
      if (!option.value || seen.has(option.value)) return;
      seen.add(option.value);
      out.push({ id: option.value, text: option.textContent.trim(), group });
    };
    for (const node of select.children) {
      if (node.tagName === 'OPTGROUP') {
        for (const option of node.children) push(option, node.label);
      } else if (node.tagName === 'OPTION') {
        push(node, '');
      }
    }
    return out;
  }

  function rank(item, query) {
    const code = fold(item.id.replace(/^VN:/, ''));
    const text = fold(item.text);
    if (code === query) return 0;
    if (code.startsWith(query)) return 1;
    if (text.startsWith(query)) return 2;
    if (code.includes(query)) return 3;
    if (text.includes(query)) return 4;
    return -1;
  }

  function render() {
    const select = openFor;
    if (!select) return;
    const query = fold(search.value);
    const items = readOptions(select);

    if (query) {
      shown = items
        .map((item) => ({ item, score: rank(item, query) }))
        .filter((x) => x.score >= 0)
        .sort((a, b) => a.score - b.score || a.item.id.length - b.item.id.length)
        .slice(0, 150)
        .map((x) => x.item);
    } else {
      shown = items;
    }

    const current = select.value;
    const at = shown.findIndex((item) => item.id === current);
    cursor = query ? 0 : Math.max(0, at);

    if (!shown.length) {
      list.innerHTML = `<div class="sp-empty">${esc(
        typeof L === 'function' ? L('Không tìm thấy mã nào.', 'No market matches.') : 'No market matches.')}</div>`;
      return;
    }

    let html = '';
    let group = null;
    shown.forEach((item, index) => {
      // Family headings only when browsing; a search result is one ranked list.
      if (!query && item.group !== group) {
        group = item.group;
        if (group) html += `<div class="sp-group">${esc(group)}</div>`;
      }
      const code = item.id.replace(/^VN:/, '');
      const name = item.text && item.text !== item.id && item.text !== code ? item.text : '';
      html += `<div class="sp-item${index === cursor ? ' active' : ''}" role="option"
                    data-index="${index}" aria-selected="${item.id === current}">
          <span class="sp-code">${esc(code)}</span>
          ${name ? `<span class="sp-name">${esc(name)}</span>` : ''}
        </div>`;
    });
    list.innerHTML = html;
    list.querySelector('.sp-item.active')?.scrollIntoView({ block: 'nearest' });
  }

  function moveCursor(step) {
    if (!shown.length) return;
    cursor = (cursor + step + shown.length) % shown.length;
    for (const node of list.querySelectorAll('.sp-item')) {
      node.classList.toggle('active', Number(node.dataset.index) === cursor);
    }
    list.querySelector('.sp-item.active')?.scrollIntoView({ block: 'nearest' });
  }

  function pick(index) {
    const select = openFor;
    const item = shown[index];
    close();
    if (!select || !item) return;
    if (select.value !== item.id) {
      select.value = item.id;
      select.dispatchEvent(new Event('change', { bubbles: true }));
    }
    attached.get(select)?.button.focus();
  }

  function open(select) {
    const entry = attached.get(select);
    if (!entry) return;
    openFor = select;
    search.value = '';
    search.placeholder = typeof L === 'function'
      ? L('Tìm mã hoặc tên…', 'Search code or name…') : 'Search…';
    pop.hidden = false;

    const rect = entry.button.getBoundingClientRect();
    const width = Math.max(rect.width, 340);
    const left = Math.min(rect.left, window.innerWidth - width - 8);
    pop.style.width = `${width}px`;
    pop.style.left = `${Math.max(8, left)}px`;
    pop.style.top = `${rect.bottom + 6}px`;
    pop.style.maxHeight = `${Math.max(220, window.innerHeight - rect.bottom - 24)}px`;
    entry.button.setAttribute('aria-expanded', 'true');

    render();
    search.focus();
  }

  function close() {
    if (!openFor) return;
    attached.get(openFor)?.button.setAttribute('aria-expanded', 'false');
    openFor = null;
    pop.hidden = true;
  }

  search.addEventListener('input', render);
  search.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowDown') { event.preventDefault(); moveCursor(1); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); moveCursor(-1); }
    else if (event.key === 'Enter') { event.preventDefault(); pick(cursor); }
    else if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'Tab') close();
  });
  list.addEventListener('mousedown', (event) => {
    const node = event.target.closest('.sp-item');
    if (!node) return;
    event.preventDefault();          // keep focus in the search box until picked
    pick(Number(node.dataset.index));
  });
  document.addEventListener('mousedown', (event) => {
    if (!openFor || pop.contains(event.target)) return;
    if (attached.get(openFor)?.button.contains(event.target)) return;
    close();
  });
  window.addEventListener('resize', close);

  function sync(select) {
    const entry = attached.get(select);
    if (!entry) return;
    const option = select.selectedOptions?.[0];
    const chosen = option && option.value;
    const label = chosen ? option.textContent.trim() : entry.placeholder();
    entry.label.textContent = label;
    entry.button.classList.toggle('empty', !chosen);
    entry.button.title = label;
  }

  /** Put a searchable picker in front of `select`. Safe to call twice. */
  function attach(select, { placeholder = () => '' } = {}) {
    if (!select || attached.has(select)) return;

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'sp-button';
    button.setAttribute('aria-haspopup', 'listbox');
    button.setAttribute('aria-expanded', 'false');
    const aria = select.getAttribute('aria-label');
    if (aria) button.setAttribute('aria-label', aria);
    button.innerHTML = '<span class="sp-label"></span>';
    const label = button.firstElementChild;

    select.classList.add('sp-native');
    select.tabIndex = -1;
    select.after(button);

    attached.set(select, {
      button,
      label,
      placeholder: typeof placeholder === 'function' ? placeholder : () => placeholder,
    });

    button.addEventListener('click', () => (openFor === select ? close() : open(select)));
    button.addEventListener('keydown', (event) => {
      // Typing on the closed button starts a search, the way a combobox does.
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
        open(select);
        search.value = event.key;
        render();
        event.preventDefault();
      } else if (event.key === 'ArrowDown') {
        open(select);
        event.preventDefault();
      }
    });

    select.addEventListener('change', () => sync(select));
    // Options are rebuilt wholesale when a catalogue arrives.
    new MutationObserver(() => sync(select)).observe(select, { childList: true, subtree: true });

    /* Programmatic `select.value = …` fires no event, and the app sets the
       value that way in several places (start-up, favourites, restoring a
       session). Wrapping the setter on this one element keeps the label true
       without asking every caller to remember a sync call. */
    const native = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value');
    Object.defineProperty(select, 'value', {
      configurable: true,
      get() { return native.get.call(this); },
      set(value) { native.set.call(this, value); sync(select); },
    });

    sync(select);
  }

  return { attach, sync, close };
})();
