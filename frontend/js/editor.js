/* Writing indicator and strategy code inside the platform.

   No editor library. This project has no build step and vendors only what it
   cannot do without, and a syntax-highlighting editor is a large dependency
   for a textarea that holds fifty lines of Python. What actually matters when
   writing a plugin is not colour: it is knowing the file parses, knowing which
   kind the platform thinks it is, and getting the failure in a place you can
   read. Those are all here.

   What this does NOT change is what the platform will run. Importing a .py
   file already executed user code with the same trust as any script on this
   machine; the editor only removes the trip through a separate program. Saving
   goes through the same validated import path, which loads the file from a
   scratch copy first, so a file that throws on import never reaches the folder
   the platform scans. */

const Editor = (() => {
  let host = null;
  let onToast = () => {};
  let onSaved = () => {};
  let state = { kind: 'indicator', filename: '', dirty: false };
  let checkTimer = null;

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

  /* Starter files, in whichever language the interface is in.

     These are the first thing a new plugin author reads, and they are the
     only place the contract is stated at the moment of writing it — so the
     comment about candle i using only information available when candle i
     closed lives here, not just in the docs nobody opens. */
  const TEMPLATE = () => ({
    indicator: L(
`"""Chỉ báo của bạn."""

INDICATOR = {
    "name": "Chỉ báo mới",
    "type": "overlay",            # overlay | panel
    "params": {
        "length": {"type": "int", "default": 20, "min": 2, "max": 400},
    },
    "outputs": [
        {"key": "value", "label": "Giá trị"},
    ],
}


def calculate(df, params):
    """df có open/high/low/close/volume. Trả về dict {key: Series}."""
    length = int(params["length"])
    return {"value": df["close"].rolling(length).mean()}
`,
`"""Your indicator."""

INDICATOR = {
    "name": "New indicator",
    "type": "overlay",            # overlay | panel
    "params": {
        "length": {"type": "int", "default": 20, "min": 2, "max": 400},
    },
    "outputs": [
        {"key": "value", "label": "Value"},
    ],
}


def calculate(df, params):
    """df has open/high/low/close/volume. Return a dict of {key: Series}."""
    length = int(params["length"])
    return {"value": df["close"].rolling(length).mean()}
`),
    strategy: L(
`"""Chiến lược của bạn."""

STRATEGY = {
    "name": "Chiến lược mới",
    "side": "both",               # long | short | both
    "params": {
        "length": {"type": "int", "default": 20, "min": 2, "max": 400},
    },
}


def signals(df, params):
    """Trả về Series 1 (mua) / -1 (bán) / 0 (đứng ngoài).

    Giá trị tại nến i chỉ được dùng thông tin tới khi nến i ĐÓNG — engine khớp
    ở giá mở nến i+1, nên bạn không thể vô tình giao dịch bằng tương lai.
    """
    length = int(params["length"])
    ma = df["close"].rolling(length).mean()
    return (df["close"] > ma).astype(int) - (df["close"] < ma).astype(int)
`,
`"""Your strategy."""

STRATEGY = {
    "name": "New strategy",
    "side": "both",               # long | short | both
    "params": {
        "length": {"type": "int", "default": 20, "min": 2, "max": 400},
    },
}


def signals(df, params):
    """Return a Series of 1 (long) / -1 (short) / 0 (flat).

    The value at bar i may only use information available when bar i CLOSED —
    the engine fills at the open of bar i+1, so you cannot trade the future by
    accident.
    """
    length = int(params["length"])
    ma = df["close"].rolling(length).mean()
    return (df["close"] > ma).astype(int) - (df["close"] < ma).astype(int)
`),
  });

  // ---------- open / close ----------

  async function open({ kind = 'indicator', filename = '' } = {}) {
    close();
    state = { kind, filename, dirty: false };

    host = document.createElement('div');
    host.className = 'dialog-backdrop';
    host.innerHTML = `
      <div class="dialog editor-dialog" role="dialog" aria-modal="true"
           aria-labelledby="ed-title">
        <div class="dialog-head">
          <h2 id="ed-title">${esc(t('ed.title'))}</h2>
          <button class="btn btn-quiet btn-sm" data-ed="close">✕</button>
        </div>

        <div class="editor-bar">
          <select data-ed="file"></select>
          <select data-ed="kind">
            <option value="indicator">${esc(t('ed.indicator'))}</option>
            <option value="strategy">${esc(t('ed.strategy'))}</option>
          </select>
          <input type="text" data-ed="name" spellcheck="false"
                 placeholder="ten_file.py" />
          <span class="editor-status" data-ed="status"></span>
        </div>

        <div class="editor-body">
          <div class="editor-gutter" data-ed="gutter"></div>
          <textarea class="editor-code" data-ed="code" spellcheck="false"
                    autocomplete="off" autocapitalize="off"
                    wrap="off"></textarea>
        </div>

        <div class="dialog-foot">
          <span class="hint" data-ed="path"></span>
          <button class="btn" data-ed="template">${esc(t('ed.template'))}</button>
          <button class="btn btn-primary" data-ed="save">${esc(t('ed.save'))}</button>
        </div>
      </div>`;
    document.body.appendChild(host);

    host.addEventListener('click', (event) => {
      if (event.target === host) confirmClose();
    });
    host.querySelector('[data-ed="close"]').addEventListener('click', confirmClose);
    host.querySelector('[data-ed="template"]').addEventListener('click', loadTemplate);
    host.querySelector('[data-ed="save"]').addEventListener('click', save);
    host.querySelector('[data-ed="kind"]').addEventListener('change', (e) => {
      state.kind = e.target.value;
      refreshFileList();
    });
    host.querySelector('[data-ed="file"]').addEventListener('change', (e) => {
      if (e.target.value) load(state.kind, e.target.value);
      else newFile();
    });

    const code = host.querySelector('[data-ed="code"]');
    code.addEventListener('input', () => {
      state.dirty = true;
      renderGutter();
      scheduleCheck();
    });
    code.addEventListener('scroll', () => {
      host.querySelector('[data-ed="gutter"]').scrollTop = code.scrollTop;
    });
    code.addEventListener('keydown', onCodeKey);

    document.addEventListener('keydown', onKey, true);
    host.querySelector('[data-ed="kind"]').value = kind;

    await refreshFileList();
    if (filename) await load(kind, filename);
    else newFile();
    code.focus();
  }

  function close() {
    host?.remove();
    host = null;
    clearTimeout(checkTimer);
    document.removeEventListener('keydown', onKey, true);
  }

  function confirmClose() {
    if (state.dirty
        && !window.confirm(t('ed.discard'))) return;
    close();
  }

  function onKey(event) {
    if (!host) return;
    if (event.key === 'Escape') { event.stopPropagation(); confirmClose(); }
    // Ctrl+S is the reflex for anyone who has written code; letting the
    // browser take it and offer "save page as" would be absurd here.
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') {
      event.preventDefault();
      save();
    }
  }

  /* Tab inserts four spaces rather than leaving the field.

     Python is indentation-sensitive, so a Tab key that moves focus makes the
     editor unusable for its only language. Shift+Tab dedents. */
  function onCodeKey(event) {
    if (event.key !== 'Tab') return;
    event.preventDefault();
    const area = event.target;
    const { selectionStart: from, selectionEnd: to, value } = area;

    if (event.shiftKey) {
      const lineStart = value.lastIndexOf('\n', from - 1) + 1;
      const indent = value.slice(lineStart, lineStart + 4);
      const drop = indent.startsWith('    ') ? 4 : indent.search(/\S/) === -1 ? indent.length : 0;
      if (!drop) return;
      area.value = value.slice(0, lineStart) + value.slice(lineStart + drop);
      area.selectionStart = area.selectionEnd = Math.max(lineStart, from - drop);
    } else {
      area.value = `${value.slice(0, from)}    ${value.slice(to)}`;
      area.selectionStart = area.selectionEnd = from + 4;
    }
    state.dirty = true;
    renderGutter();
    scheduleCheck();
  }

  // ---------- content ----------

  function codeArea() { return host?.querySelector('[data-ed="code"]'); }

  function newFile() {
    state.filename = '';
    host.querySelector('[data-ed="name"]').value = '';
    host.querySelector('[data-ed="file"]').value = '';
    loadTemplate();
  }

  function loadTemplate() {
    const pack = TEMPLATE();
    codeArea().value = pack[state.kind] || pack.indicator;
    state.dirty = true;
    renderGutter();
    scheduleCheck();
  }

  async function load(kind, filename) {
    try {
      const file = await API.pluginRead(kind, filename);
      codeArea().value = file.content;
      state.kind = kind;
      state.filename = file.filename;
      state.dirty = false;
      host.querySelector('[data-ed="name"]').value = file.filename;
      host.querySelector('[data-ed="path"]').textContent = file.path;
      renderGutter();
      scheduleCheck();
    } catch (err) {
      onToast(err.message, true);
    }
  }

  async function refreshFileList() {
    let listing;
    try {
      listing = await API.pluginFiles();
    } catch {
      return;                       // the editor still works for new files
    }
    const select = host.querySelector('[data-ed="file"]');
    const files = listing.files?.[state.kind] || [];
    select.innerHTML = `<option value="">${esc(t('ed.newFile'))}</option>`
      + files.map((f) => `<option value="${esc(f.filename)}">${esc(f.filename)}</option>`).join('');
    if (state.filename) select.value = state.filename;
  }

  function renderGutter() {
    const gutter = host?.querySelector('[data-ed="gutter"]');
    if (!gutter) return;
    const lines = codeArea().value.split('\n').length;
    gutter.innerHTML = Array.from({ length: lines }, (_, i) => `<span>${i + 1}</span>`).join('');
  }

  // ---------- checking ----------

  /* Parse as you type, but never execute as you type.

     /api/plugins/check stops at ast.parse: it says whether the source is valid
     Python and which kind it declares, without running a line of it. Running
     half-written code on every keystroke would be a genuinely bad idea — the
     execution happens once, on save, through the import path that loads from a
     scratch copy first. */
  function scheduleCheck() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(runCheck, 500);
  }

  async function runCheck() {
    const status = host?.querySelector('[data-ed="status"]');
    if (!status) return;
    let result;
    try {
      result = await API.pluginCheck(codeArea().value);
    } catch (err) {
      status.className = 'editor-status bad';
      status.textContent = err.message;
      return;
    }
    if (result.ok) {
      status.className = 'editor-status ok';
      status.textContent = t(result.kind === 'strategy' ? 'ed.okStrategy' : 'ed.okIndicator');
      // The kind is read from the source, not from the dropdown: the file
      // decides what it is, and a mismatch here would be a lie the save
      // would then contradict.
      host.querySelector('[data-ed="kind"]').value = result.kind;
      state.kind = result.kind;
    } else {
      status.className = 'editor-status bad';
      status.textContent = result.detail;
    }
  }

  // ---------- saving ----------

  async function save() {
    const name = host.querySelector('[data-ed="name"]').value.trim();
    if (!name) {
      onToast(t('ed.needName'), true);
      host.querySelector('[data-ed="name"]').focus();
      return;
    }

    const button = host.querySelector('[data-ed="save"]');
    const original = button.textContent;
    button.disabled = true;
    button.textContent = t('ed.saving');
    try {
      const report = await API.importPlugin({
        filename: name.endsWith('.py') ? name : `${name}.py`,
        content: codeArea().value,
        // Editing a file in place is a deliberate overwrite; refusing it would
        // mean the editor could only ever create.
        overwrite: true,
      });
      state.dirty = false;
      state.filename = report.filename;
      host.querySelector('[data-ed="path"]').textContent = report.path;
      onToast(t('ed.saved', { name: report.filename }));
      await refreshFileList();
      await onSaved(report);
    } catch (err) {
      onToast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = original;
    }
  }

  function init(config) {
    onToast = config?.onToast || (() => {});
    onSaved = config?.onSaved || (() => {});
  }

  return { init, open, close };
})();
