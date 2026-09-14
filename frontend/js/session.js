/* What you were doing, kept across a reload.

   A research session is a stack of small choices — this symbol, that
   timeframe, three indicators with tuned lengths, a strategy with its
   parameters, a second market beside the first, the panel you had open. A
   reload that throws all of that away costs minutes to rebuild and, worse,
   invites rebuilding it slightly differently. Nam asked for none of it to be
   lost.

   One versioned object in localStorage, written a moment after the last
   change and again when the page is being left. It is a convenience of this
   browser, not a record: nothing here is sent anywhere, and a stored value the
   app no longer recognises (a symbol that left the catalogue, an indicator
   that was deleted) is simply skipped on restore rather than trusted. */

const Session = (() => {
  const KEY = 'qp.session.v1';
  const VERSION = 1;

  let data = {};
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (raw && raw.v === VERSION) data = raw;
  } catch {
    // Unreadable or blocked storage: start clean, the page still works.
    data = {};
  }

  // What the page opened with. Restores read this; later changes go to `data`
  // so a restore half-way through cannot read back its own partial writes.
  const saved = Object.freeze({ ...data });

  let timer = null;

  function write() {
    clearTimeout(timer);
    timer = null;
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...data, v: VERSION }));
    } catch {
      // Private mode or a full quota: this session still works, it just will
      // not survive the reload.
    }
  }

  function patch(part) {
    Object.assign(data, part);
    clearTimeout(timer);
    timer = setTimeout(write, 300);
  }

  // A reload inside the 300ms debounce would otherwise lose the last change.
  window.addEventListener('pagehide', write);
  window.addEventListener('beforeunload', write);

  return { saved, patch, flush: write, get current() { return { ...data }; } };
})();
