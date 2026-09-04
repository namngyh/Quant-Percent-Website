/* Starred symbols, indicators and strategies.

   Kept in localStorage rather than on the server: this is one person's view of
   one machine, it should survive a reload, and it should never be something
   that can fail because a request did. */

const Favourites = (() => {
  const KEY = 'qp.favourites.v1';
  const KINDS = ['symbol', 'indicator', 'strategy'];

  let store = { symbol: [], indicator: [], strategy: [] };
  const listeners = new Set();

  function load() {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || '{}');
      for (const kind of KINDS) {
        store[kind] = Array.isArray(raw[kind]) ? raw[kind] : [];
      }
    } catch {
      // Corrupt or blocked storage is not worth failing over; start empty.
      store = { symbol: [], indicator: [], strategy: [] };
    }
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify(store));
    } catch {
      // Private browsing, or storage disabled. The stars still work for this
      // session; they just will not come back.
    }
  }

  const has = (kind, id) => store[kind]?.includes(id) ?? false;
  const list = (kind) => [...(store[kind] || [])];

  function toggle(kind, id) {
    if (!KINDS.includes(kind)) return false;
    const items = store[kind];
    const at = items.indexOf(id);
    if (at >= 0) items.splice(at, 1);
    else items.unshift(id);      // newest first, so a fresh star is easy to find
    save();
    for (const fn of listeners) fn(kind, id, at < 0);
    return at < 0;
  }

  /** Starred entries first, everything else in its original order. */
  function sort(kind, items, idOf = (x) => x.id) {
    const starred = [];
    const rest = [];
    for (const item of items) (has(kind, idOf(item)) ? starred : rest).push(item);
    return { starred, rest };
  }

  function onChange(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  /** The star control itself, so every list renders an identical one. */
  function button(kind, id, { size = '' } = {}) {
    const on = has(kind, id);
    return (
      `<button class="star${on ? ' on' : ''}${size ? ' ' + size : ''}" ` +
      `data-star-kind="${kind}" data-star-id="${String(id).replace(/"/g, '&quot;')}" ` +
      `title="${on ? 'Bỏ đánh dấu' : 'Đánh dấu sao'}" aria-pressed="${on}">` +
      `${on ? '★' : '☆'}</button>`
    );
  }

  /** Wire every star inside a container. Returns nothing; re-render on change. */
  function bind(container, afterToggle) {
    for (const btn of container.querySelectorAll('[data-star-kind]')) {
      btn.addEventListener('click', (event) => {
        event.stopPropagation();     // a star on a row must not also select it
        toggle(btn.dataset.starKind, btn.dataset.starId);
        if (afterToggle) afterToggle();
      });
    }
  }

  load();
  return { has, list, toggle, sort, onChange, button, bind };
})();
