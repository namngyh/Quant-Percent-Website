/* Indicator catalog UI and the list of active indicator instances.

   The same indicator can be added more than once (EMA 20 alongside EMA 50), so
   each addition gets its own instance id and its own parameter values. */

const Indicators = (() => {
  let catalog = [];
  let elements = {};
  let onCompute = async () => {};
  let onRemove = () => {};
  let onExplain = () => {};

  /** instanceId -> { spec, params, error } */
  const active = new Map();
  let onChange = () => {};
  let counter = 0;

  const debounceTimers = new Map();

  function debounce(key, fn, delay = 160) {
    clearTimeout(debounceTimers.get(key));
    debounceTimers.set(key, setTimeout(fn, delay));
  }

  // ---------- Catalog ----------

  function setCatalog(data) {
    catalog = data.indicators || [];
    elements.count.textContent = String(catalog.length);
    renderPluginErrors(data.plugin_errors || []);
    renderCatalog();
  }

  function renderPluginErrors(errors) {
    const box = elements.pluginErrors;
    if (!errors.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.innerHTML = errors
      .map((e) => `<div>⚠ ${escapeHtml(e.file)}: ${escapeHtml(e.error)}</div>`)
      .join('');
  }

  // Category names the user has opened by hand this session.
  const openGroups = new Set();

  function renderCatalog() {
    const query = elements.search.value.trim().toLowerCase();
    const matches = query
      ? catalog.filter(
          (s) =>
            s.id.toLowerCase().includes(query) ||
            s.name.toLowerCase().includes(query) ||
            s.category.toLowerCase().includes(query),
        )
      : catalog;

    const activeIds = new Set([...active.values()].map((i) => i.spec.id));

    const groups = new Map();
    // Starred indicators get their own group at the top, so the handful you
    // actually use are not buried among 189.
    const { starred, rest } = Favourites.sort('indicator', matches);
    if (starred.length) groups.set(L('★ đánh dấu', '★ favourites'), starred);

    for (const spec of rest) {
      const key = spec.source === 'plugin'
        ? L('của bạn (python)', 'yours (python)')
        : spec.category;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(spec);
    }

    if (!groups.size) {
      elements.catalog.innerHTML = `<p class="empty">${escapeHtml(L(
        'Không tìm thấy chỉ báo nào.', 'No indicator matches.'))}</p>`;
      return;
    }

    /* Groups collapse.

       All eleven categories used to render open at once: 190 rows, measured at
       6,280px of content in a 667px panel — eight screens of scrolling to
       reach anything not near the top, which is what made this panel the
       hardest one to use. A group opens when there is a reason to look inside
       it: a search is running, it holds something already on the chart, it is
       the favourites group, or the user opened it themselves. */
    let html = '';
    for (const [group, specs] of groups) {
      const holdsActive = specs.some((spec) => activeIds.has(spec.id));
      const open = query || holdsActive || group.startsWith('★') || openGroups.has(group);
      html += `<details class="cat-group"${open ? ' open' : ''} data-group="${escapeHtml(group)}">`
        + `<summary class="cat-group-name"><span>${escapeHtml(group)}</span>`
        + `<span class="cat-count">${specs.length}</span></summary>`;
      for (const spec of specs) {
        const on = activeIds.has(spec.id) ? ' on' : '';
        const plugin = spec.source === 'plugin' ? ' plugin' : '';
        html +=
          `<div class="cat-item${on}${plugin}" data-id="${escapeHtml(spec.id)}" title="${escapeHtml(spec.description || spec.name)}">` +
          Favourites.button('indicator', spec.id, { size: 'star-sm' }) +
          `<span class="cat-item-name">${escapeHtml(spec.name)}</span>` +
          `<span class="cat-item-kind">${spec.kind === 'overlay' ? 'overlay' : 'panel'}</span>` +
          `<button class="info-btn" data-info="${escapeHtml(spec.id)}" title="${
            escapeHtml(t('ind.explain'))}">i</button>` +
          `</div>`;
      }
      html += '</details>';
    }
    elements.catalog.innerHTML = html;

    // Remember what the user opened, so a repaint (starring, adding, typing)
    // does not fold the group they are working in shut under them.
    for (const node of elements.catalog.querySelectorAll('.cat-group')) {
      node.addEventListener('toggle', () => {
        if (node.open) openGroups.add(node.dataset.group);
        else openGroups.delete(node.dataset.group);
      });
    }

    for (const node of elements.catalog.querySelectorAll('.cat-item')) {
      node.addEventListener('click', () => add(node.dataset.id));
    }
    for (const btn of elements.catalog.querySelectorAll('[data-info]')) {
      btn.addEventListener('click', (event) => {
        event.stopPropagation();     // explaining an indicator must not add it
        onExplain(catalog.find((s) => s.id === btn.dataset.info));
      });
    }
    Favourites.bind(elements.catalog, renderCatalog);
  }

  // ---------- Active instances ----------

  /* `initial` carries tuned parameters back in when a session is restored.
     Only names the spec still declares are taken: a stored value for a
     parameter the plugin has since dropped would be sent to code that no
     longer expects it. */
  function add(indicatorId, initial = null) {
    const spec = catalog.find((s) => s.id === indicatorId);
    if (!spec) return;

    counter += 1;
    const instanceId = `${spec.id}#${counter}`;
    const params = {};
    for (const p of spec.params) {
      const kept = initial && Object.prototype.hasOwnProperty.call(initial, p.name)
        ? initial[p.name] : undefined;
      params[p.name] = kept === undefined ? p.default : kept;
    }

    active.set(instanceId, { spec, params, error: null });
    renderActive();
    renderCatalog();
    compute(instanceId);
    onChange();
  }

  /** What is on the chart, in a form that survives a reload. */
  function snapshot() {
    return [...active.values()].map((i) => ({ id: i.spec.id, params: { ...i.params } }));
  }

  /** Put a snapshot back. Entries the catalogue no longer has are skipped. */
  function restore(list) {
    if (!Array.isArray(list)) return;
    for (const entry of list) {
      if (entry && catalog.some((s) => s.id === entry.id)) add(entry.id, entry.params);
    }
  }

  function remove(instanceId) {
    active.delete(instanceId);
    onRemove(instanceId);
    renderActive();
    renderCatalog();
    onChange();
  }

  function clearAll() {
    for (const id of [...active.keys()]) onRemove(id);
    active.clear();
    renderActive();
    renderCatalog();
    onChange();
  }

  async function compute(instanceId) {
    const instance = active.get(instanceId);
    if (!instance) return;
    try {
      await onCompute(instanceId, instance);
      instance.error = null;
    } catch (err) {
      instance.error = err.message;
    }
    renderActive();
  }

  /* Recompute every active indicator, one pass at a time.
   *
   * The live stream fires this on every candle close. Without a guard, a pass
   * that outlives its bar overlaps the next one, and on a 1-minute chart with
   * an ML plugin refitting scikit-learn over a few thousand bars that means a
   * growing pile of concurrent requests, each one slower than the last because
   * they are all competing for the same backend. The panes then sit stale for
   * as long as the pile takes to drain.
   *
   * So: at most one pass in flight. A close that arrives during a pass sets a
   * flag instead of starting a second, and exactly one more pass runs when the
   * current one finishes — the newest data, computed once. */
  let running = null;
  let queued = false;

  async function recomputeAll() {
    if (running) {
      queued = true;
      return running;
    }

    running = (async () => {
      try {
        do {
          queued = false;
          await Promise.all([...active.keys()].map((id) => compute(id)));
        } while (queued);
      } finally {
        running = null;
      }
    })();

    return running;
  }

  function renderActive() {
    if (!active.size) {
      elements.active.innerHTML = `<p class="empty">${escapeHtml(L(
        'Chưa có chỉ báo nào. Chọn từ danh sách bên trên.',
        'No indicators yet. Pick one from the list above.'))}</p>`;
      return;
    }

    let html = '';
    for (const [instanceId, { spec, params, error }] of active) {
      const color = spec.outputs?.[0]?.color || '#1c2f5e';
      html += `<div class="active-item" data-instance="${escapeHtml(instanceId)}">`;
      html += `<div class="active-head">
          <span class="swatch" style="background:${escapeHtml(color)}"></span>
          <span class="active-name">${escapeHtml(spec.name)}</span>
          <span class="active-kind">${spec.kind}</span>
          <button class="info-btn" data-info-active="${escapeHtml(spec.id)}" title="${
            escapeHtml(t('ind.explain'))}">i</button>
          <button class="btn btn-ghost btn-sm active-remove" data-remove="${escapeHtml(instanceId)}">✕</button>
        </div>`;

      if (spec.params.length) {
        html += '<div class="params">';
        for (const p of spec.params) {
          const value = params[p.name];
          html += '<div class="param">';
          html += `<span class="param-label" title="${escapeHtml(p.label)}">${escapeHtml(p.label)}</span>`;
          if (p.type === 'bool') {
            html += `<input type="checkbox" data-param="${escapeHtml(p.name)}" ${value ? 'checked' : ''} />`;
            html += '<span class="param-value"></span>';
          } else {
            const min = p.min ?? 1;
            const max = p.max ?? 200;
            const step = p.step ?? (p.type === 'int' ? 1 : 0.1);
            html += `<input type="range" data-param="${escapeHtml(p.name)}" min="${min}" max="${max}" step="${step}" value="${value}" />`;
            html += `<span class="param-value" data-value-for="${escapeHtml(p.name)}">${value}</span>`;
          }
          html += '</div>';
        }
        html += '</div>';
      }

      if (error) html += `<div class="active-error">${escapeHtml(error)}</div>`;
      html += '</div>';
    }
    elements.active.innerHTML = html;
    bindActiveEvents();
  }

  function bindActiveEvents() {
    for (const btn of elements.active.querySelectorAll('[data-remove]')) {
      btn.addEventListener('click', () => remove(btn.dataset.remove));
    }
    for (const btn of elements.active.querySelectorAll('[data-info-active]')) {
      btn.addEventListener('click', () =>
        onExplain(catalog.find((s) => s.id === btn.dataset.infoActive)));
    }

    for (const input of elements.active.querySelectorAll('[data-param]')) {
      const item = input.closest('.active-item');
      const instanceId = item.dataset.instance;
      const paramName = input.dataset.param;

      input.addEventListener('input', () => {
        const instance = active.get(instanceId);
        if (!instance) return;

        const value = input.type === 'checkbox' ? input.checked : Number(input.value);
        instance.params[paramName] = value;

        // Update the readout immediately; recompute on a short debounce so
        // dragging a slider doesn't fire a request per pixel.
        const readout = item.querySelector(`[data-value-for="${paramName}"]`);
        if (readout) readout.textContent = String(value);

        debounce(instanceId, () => compute(instanceId));
        onChange();
      });
    }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  }

  function init(config) {
    elements = config.elements;
    onChange = config.onChange || (() => {});
    onCompute = config.onCompute;
    onRemove = config.onRemove;
    onExplain = config.onExplain || (() => {});
    elements.search.addEventListener('input', () => debounce('search', renderCatalog, 120));
    elements.clearAll.addEventListener('click', clearAll);
  }

  /** Redraw from current state: used when the language changes. */
  function rerender() {
    renderCatalog();
    renderActive();
  }

  return { init, setCatalog, recomputeAll, clearAll, active, rerender, snapshot, restore };
})();
