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
    if (starred.length) groups.set('★ đánh dấu', starred);

    for (const spec of rest) {
      const key = spec.source === 'plugin' ? 'của bạn (python)' : spec.category;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(spec);
    }

    if (!groups.size) {
      elements.catalog.innerHTML = '<p class="empty">Không tìm thấy chỉ báo nào.</p>';
      return;
    }

    let html = '';
    for (const [group, specs] of groups) {
      html += `<div class="cat-group"><div class="cat-group-name">${escapeHtml(group)} · ${specs.length}</div>`;
      for (const spec of specs) {
        const on = activeIds.has(spec.id) ? ' on' : '';
        const plugin = spec.source === 'plugin' ? ' plugin' : '';
        html +=
          `<div class="cat-item${on}${plugin}" data-id="${escapeHtml(spec.id)}" title="${escapeHtml(spec.description || spec.name)}">` +
          Favourites.button('indicator', spec.id, { size: 'star-sm' }) +
          `<span class="cat-item-name">${escapeHtml(spec.name)}</span>` +
          `<span class="cat-item-kind">${spec.kind === 'overlay' ? 'overlay' : 'panel'}</span>` +
          `<button class="info-btn" data-info="${escapeHtml(spec.id)}" title="Giải thích chỉ báo">i</button>` +
          `</div>`;
      }
      html += '</div>';
    }
    elements.catalog.innerHTML = html;

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

  function add(indicatorId) {
    const spec = catalog.find((s) => s.id === indicatorId);
    if (!spec) return;

    counter += 1;
    const instanceId = `${spec.id}#${counter}`;
    const params = {};
    for (const p of spec.params) params[p.name] = p.default;

    active.set(instanceId, { spec, params, error: null });
    renderActive();
    renderCatalog();
    compute(instanceId);
  }

  function remove(instanceId) {
    active.delete(instanceId);
    onRemove(instanceId);
    renderActive();
    renderCatalog();
  }

  function clearAll() {
    for (const id of [...active.keys()]) onRemove(id);
    active.clear();
    renderActive();
    renderCatalog();
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

  async function recomputeAll() {
    await Promise.all([...active.keys()].map((id) => compute(id)));
  }

  function renderActive() {
    if (!active.size) {
      elements.active.innerHTML =
        '<p class="empty">Chưa có chỉ báo nào. Chọn từ danh sách bên trên.</p>';
      return;
    }

    let html = '';
    for (const [instanceId, { spec, params, error }] of active) {
      const color = spec.outputs?.[0]?.color || '#2962ff';
      html += `<div class="active-item" data-instance="${escapeHtml(instanceId)}">`;
      html += `<div class="active-head">
          <span class="swatch" style="background:${escapeHtml(color)}"></span>
          <span class="active-name">${escapeHtml(spec.name)}</span>
          <span class="active-kind">${spec.kind}</span>
          <button class="info-btn" data-info-active="${escapeHtml(spec.id)}" title="Giải thích chỉ báo">i</button>
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

  return { init, setCatalog, recomputeAll, clearAll, active, rerender };
})();
