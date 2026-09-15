/* One, two or four charts — each a complete chart that stays put.

   Nam's rule (2026-09-17/18): every cell does what the first does —
   indicators, strategy tests, drawings — with its own timeframe behind a gear
   and a caption under it; and clicking one chart must leave the others exactly
   as they are.

   The first design kept ONE full chart and moved it into whichever cell was
   clicked, leaving a lighter snapshot behind in the cell it left. Every click
   therefore swapped two charts for two different ones: the snapshot had no
   volume, no indicator panes, its own price-scale fit and its own framing, and
   the cell being entered reloaded its series. Clicking back and forth made the
   other chart "reset" or "zoom" on every click (Nam, 2026-09-18) — no amount
   of carrying ranges across could make two different charts look the same.

   Now each cell owns a real chart (`ChartHub.create()`), its own drawing layer
   (`DrawingHub.create()`), its own indicator set and its own history pager.
   Clicking a cell changes only which one the toolbar, the panels and the live
   feed are pointed at: `ChartHub.setActive` and `DrawingHub.setActive`, plus
   the app swapping the indicator list it shows. Nothing is torn down, moved,
   reloaded or re-framed, so there is nothing for the eye to see change.

   Limit, stated (§2.7): the live feed follows the active cell. A cell that is
   not active keeps its last bar until it is clicked, when the bars it missed
   are fetched and appended. */

const MultiChart = (() => {
  const LAYOUTS = [1, 2, 4];

  let grid = null;
  let hooks = {};
  let layout = 1;
  let active = 0;
  let mode = 'trading';
  let cells = [];
  let optionsHtml = '';
  let colFr = [1, 1];
  let rowFr = [1, 1];
  let colHandle = null;
  let rowHandle = null;

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const GEAR = `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
    stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <circle cx="12" cy="12" r="3"/>
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3
      1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1
      a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1
      a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3
      H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1
      a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1
      a1.7 1.7 0 0 0-1.5 1z"/></svg>`;

  const LOADER = `<svg class="qp-loader" viewBox="0 0 100 100" aria-hidden="true">
    <rect x="17" y="13" width="25" height="25" /><rect x="58" y="62" width="25" height="25" />
    <path d="M19 81 L81 19" /></svg>`;

  // ---------------------------------------------------------------- workspaces

  const current = () => hooks.current();
  const indexOf = (cell) => cells.indexOf(cell);
  const wsOf = (cell) => (indexOf(cell) === active ? current() : cell.ws);

  /* A new cell opens on a market not already on screen, never on a blank: an
     empty cell has nothing to work on, and a second copy says nothing new. */
  function freshWorkspace() {
    const shown = new Set(cells.map((c) => wsOf(c)?.symbol));
    const candidates = ['VN:VNINDEX', 'VN:VN30F1M', 'VN:G-XAUUSD', 'BTCUSDT', 'VN:VIC', 'VN:FPT', 'ETHUSDT'];
    const symbol = candidates.find((s) => !shown.has(s)) || current().symbol;
    return { symbol, timeframe: fitTimeframe(symbol, current().timeframe), indicators: [] };
  }

  function fitTimeframe(symbol, wanted) {
    const frames = hooks.timeframes(symbol) || [];
    if (frames.includes(wanted)) return wanted;
    return frames.includes('1d') ? '1d' : (frames[frames.length - 1] || wanted);
  }

  // ---------------------------------------------------------------- cells

  /** The chrome around a chart: head with picker and gear, body, caption. */
  function shell(cell) {
    const el = document.createElement('div');
    el.className = 'cell';
    el.innerHTML = `
      <div class="cell-head">
        <span class="cell-badge"></span>
        <select class="cell-pick" aria-label="${esc(t('mc.choose'))}">
          <option value=""></option>${optionsHtml}
        </select>
        <span class="cell-frame"></span>
        <button type="button" class="cell-gear" aria-haspopup="menu" aria-expanded="false"
                title="${esc(L('Cài đặt biểu đồ', 'Chart settings'))}"
                aria-label="${esc(L('Cài đặt biểu đồ', 'Chart settings'))}">${GEAR}</button>
      </div>
      <div class="cell-body"></div>
      <div class="cell-caption"></div>`;
    cell.el = el;
    cell.body = el.querySelector('.cell-body');
    cell.caption = el.querySelector('.cell-caption');
    cell.badge = el.querySelector('.cell-badge');
    cell.select = el.querySelector('.cell-pick');
    cell.gear = el.querySelector('.cell-gear');
    cell.frame = el.querySelector('.cell-frame');

    cell.select.addEventListener('change', () => setCellSymbol(cell, cell.select.value));
    if (typeof SymbolPicker !== 'undefined') {
      SymbolPicker.attach(cell.select, { placeholder: () => t('mc.choose') });
    }
    cell.gear.addEventListener('click', (event) => {
      event.stopPropagation();
      if (menuFor === cell) closeMenu(); else openMenu(cell);
    });
    // Capture: the cell becomes the working one before the chart turns the
    // same press into a pan or a drawing — and the press then carries on into
    // that chart as normal, because nothing was moved out from under it.
    cell.body.addEventListener('pointerdown', () => {
      const i = indexOf(cell);
      if (i !== active) activate(i);
    }, { capture: true });
    return cell;
  }

  /** Cell 0 wraps the chart the app already built at start-up. */
  function adopt(workUnit) {
    const cell = shell({});
    cell.body.appendChild(workUnit);
    cell.chartMain = workUnit.querySelector('.chart-main');
    cell.panes = workUnit.querySelector('.panes');
    cell.loading = workUnit.querySelector('.loading');
    cell.manager = ChartHub.active;
    cell.drawings = DrawingHub.active;
    cell.ws = current();
    cell.indicators = new Map();
    cell.exhausted = false;
    hooks.configure(cell);
    return cell;
  }

  /** A new chart with its own series, drawings, indicators and pager. */
  function create(ws) {
    const cell = shell({});
    cell.body.innerHTML = `
      <div class="work-unit">
        <div class="chart-pane chart-main"></div>
        <div class="resize-handle resize-y" role="separator" aria-orientation="horizontal"></div>
        <div class="panes"></div>
        <div class="loading" role="status" aria-label="Loading" hidden>${LOADER}</div>
      </div>`;
    cell.chartMain = cell.body.querySelector('.chart-main');
    cell.panes = cell.body.querySelector('.panes');
    cell.loading = cell.body.querySelector('.loading');
    if (typeof Resizer !== 'undefined') Resizer.attachPanes(cell.body.querySelector('.resize-handle'));

    cell.ws = { symbol: ws.symbol, timeframe: ws.timeframe, indicators: ws.indicators || [] };
    cell.indicators = new Map();
    cell.exhausted = false;

    cell.manager = ChartHub.create();
    cell.manager.init(cell.chartMain);
    cell.manager.setMode('trading');
    cell.drawings = DrawingHub.create();
    cell.drawings.init({
      chart: cell.manager.chart,
      series: cell.manager.priceSeries,
      host: cell.chartMain,
      manager: cell.manager,
      onChange: () => { if (indexOf(cell) === active) hooks.onDrawingsChange?.(); },
    });
    cell.drawings.setActive(false);

    hooks.configure(cell);
    hooks.loadCell(cell);
    return cell;
  }

  function destroy(cell) {
    cell.destroyed = true;
    cell.loadToken = null;
    try { cell.drawings.destroy(); } catch { /* already gone */ }
    try { cell.manager.destroy(); } catch { /* already gone */ }
    cell.el.remove();
  }

  // ---------------------------------------------------------------- layout

  function setLayout(next) {
    if (!LAYOUTS.includes(next) || next === layout) return layout;
    const working = cells[active];
    working.ws = current();

    // The working chart keeps working: it moves to the front of the list (its
    // element is re-appended, the chart itself is untouched) instead of
    // disappearing with a cell the smaller layout does not have.
    if (active !== 0) {
      cells.splice(active, 1);
      cells.unshift(working);
      active = 0;
    }
    while (cells.length > next) destroy(cells.pop());
    layout = next;
    while (cells.length < next) cells.push(create(freshWorkspace()));
    build();
    return layout;
  }

  /** Arrange the existing cells. Elements are moved, charts never rebuilt. */
  function build() {
    if (!grid) return;
    closeMenu();
    grid.dataset.layout = String(layout);
    grid.replaceChildren(...cells.map((cell, i) => {
      cell.el.dataset.cell = String(i);
      cell.select.dataset.pick = String(i);
      cell.gear.dataset.gear = String(i);
      cell.body.dataset.body = String(i);
      cell.caption.dataset.caption = String(i);
      return cell.el;
    }));
    if (layout > 1) grid.appendChild(colHandle);
    if (layout === 4) grid.appendChild(rowHandle);
    paintAll();
    applySizes();
    persist();
    hooks.onResize();
    for (const cell of cells) cell.manager.refreshSize();
  }

  /* Point the toolbar, the panels and the live feed at cell `i`.

     This is the whole of a switch. No chart is created, destroyed, moved,
     reloaded or re-framed: the cell being left keeps its series, its zoom, its
     indicators and its drawings exactly as they were. */
  function activate(i) {
    if (mode === 'overview' || i === active || !cells[i]) return;
    closeMenu();
    const from = cells[active];
    const to = cells[i];

    hooks.beforeDeactivate?.();
    from.ws = current();
    from.indicators = hooks.exportIndicators();
    from.drawings.setActive(false);

    active = i;
    ChartHub.setActive(to.manager);
    DrawingHub.setActive(to.drawings);
    to.drawings.setActive(true);
    hooks.activated(to);

    paintAll();
    persist();
  }

  function setCellSymbol(cell, symbol) {
    if (!symbol) { paint(cell); return; }
    if (indexOf(cell) === active) {
      if (symbol !== current().symbol) hooks.setActiveSymbol(symbol);
      return;
    }
    if (cell.ws.symbol === symbol) return;
    cell.ws.symbol = symbol;
    cell.ws.timeframe = fitTimeframe(symbol, cell.ws.timeframe);
    cell.ws.indicators = snapshotOf(cell.indicators);
    hooks.loadCell(cell);            // this cell changed, so this cell loads
    paint(cell);
    persist();
  }

  function setCellTimeframe(cell, timeframe) {
    if (indexOf(cell) === active) {
      hooks.setActiveTimeframe(timeframe);
      return;
    }
    if (cell.ws.timeframe === timeframe) return;
    cell.ws.timeframe = timeframe;
    cell.ws.indicators = snapshotOf(cell.indicators);
    hooks.loadCell(cell);
    paint(cell);
    persist();
  }

  /** The app calls this whenever the working chart's series or indicators change. */
  function syncActive() {
    const cell = cells[active];
    if (!grid || !cell) return;
    cell.ws = current();
    cell.indicators = hooks.exportIndicators();
    paint(cell);
    persist();
  }

  /* Overview shows the working chart alone, full screen; the others are hidden
     by the stylesheet, not torn down, so the working view returns as it was. */
  function setMode(next) {
    mode = next;
    closeMenu();
    hooks.onResize?.();
  }

  const snapshotOf = (map) => [...(map || new Map()).values()]
    .map((entry) => ({ id: entry.spec.id, params: { ...entry.params } }));

  // ---------------------------------------------------------------- heads and captions

  function paint(cell) {
    const ws = wsOf(cell);
    if (!ws) return;
    const isActive = indexOf(cell) === active;
    cell.frame.textContent = ws.timeframe;
    cell.el.classList.toggle('active', isActive);
    cell.badge.innerHTML = ws.symbol ? Paper.symbolBadge(ws.symbol) : '';
    if (cell.select.value !== ws.symbol) cell.select.value = ws.symbol || '';
    const list = isActive ? ws.indicators : snapshotOf(cell.indicators);
    const names = hooks.describe(list && list.length ? list : (ws.indicators || []));
    cell.caption.textContent = [String(ws.symbol || '').replace(/^VN:/, ''), ws.timeframe, ...names]
      .filter(Boolean).join('  ·  ');
    cell.caption.title = cell.caption.textContent;
  }

  function paintAll() { cells.forEach(paint); }

  function setOptions(groups) {
    optionsHtml = (groups || []).map((group) =>
      `<optgroup label="${esc(group.label)}">` +
      group.options.map((o) => `<option value="${esc(o.id)}">${esc(o.text)}</option>`).join('') +
      '</optgroup>').join('');
    for (const cell of cells) {
      cell.select.innerHTML = `<option value=""></option>${optionsHtml}`;
      cell.select.value = wsOf(cell)?.symbol || '';
    }
  }

  // ---------------------------------------------------------------- gear menu

  const menu = document.createElement('div');
  menu.className = 'cell-menu';
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  document.body.appendChild(menu);
  let menuFor = null;

  function openMenu(cell) {
    closeMenu();
    const ws = wsOf(cell);
    if (!ws) return;
    menuFor = cell;
    const isActive = indexOf(cell) === active;
    const frames = hooks.timeframes(ws.symbol) || [];
    menu.innerHTML = `
      <div class="cell-menu-title">${esc(L('Khung thời gian', 'Timeframe'))}</div>
      <div class="cell-menu-frames">${frames.map((tf) => `
        <button type="button" role="menuitemradio" aria-checked="${tf === ws.timeframe}"
                class="cell-menu-tf${tf === ws.timeframe ? ' active' : ''}" data-tf="${esc(tf)}">${esc(tf)}</button>`).join('')}
      </div>
      ${isActive
        ? `<p class="cell-menu-note">${esc(L(
          'Chỉ báo, chiến lược và hình vẽ đang áp dụng lên biểu đồ này.',
          'Indicators, strategies and drawings apply to this chart.'))}</p>`
        : `<button type="button" class="btn btn-sm btn-block cell-menu-work" data-work>${esc(L(
          'Làm việc trên biểu đồ này', 'Work on this chart'))}</button>`}`;
    menu.hidden = false;
    cell.gear.setAttribute('aria-expanded', 'true');
    const rect = cell.gear.getBoundingClientRect();
    const width = menu.offsetWidth;
    menu.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
    menu.style.top = `${rect.bottom + 6}px`;
  }

  function closeMenu() {
    if (!menuFor) return;
    menuFor.gear.setAttribute('aria-expanded', 'false');
    menuFor = null;
    menu.hidden = true;
  }

  menu.addEventListener('click', (event) => {
    const cell = menuFor;
    const tf = event.target.closest('[data-tf]')?.dataset.tf;
    if (tf) { closeMenu(); setCellTimeframe(cell, tf); return; }
    if (event.target.closest('[data-work]')) { closeMenu(); activate(indexOf(cell)); }
  });
  document.addEventListener('mousedown', (event) => {
    if (!menuFor || menu.contains(event.target)) return;
    if (event.target.closest?.('.cell-gear')) return;
    closeMenu();
  });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape') closeMenu(); });

  // ---------------------------------------------------------------- sizes

  function applySizes() {
    if (!grid) return;
    grid.style.gridTemplateColumns = layout > 1 ? colFr.map((f) => `${f.toFixed(4)}fr`).join(' ') : '';
    grid.style.gridTemplateRows = layout === 4 ? rowFr.map((f) => `${f.toFixed(4)}fr`).join(' ') : '';
    requestAnimationFrame(placeHandles);
    setTimeout(placeHandles, 60);
  }

  function placeHandles() {
    const first = cells[0]?.el;
    if (!first || !grid) return;
    colHandle.style.left = `${first.offsetLeft + first.offsetWidth}px`;
    rowHandle.style.top = `${first.offsetTop + first.offsetHeight}px`;
  }

  /* Drag a divider. Both neighbours keep at least 20% of their pair; the
     cursor is pinned for the whole gesture; double-click restores the default. */
  function bindHandle(handle, axis) {
    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      const start = axis === 'x' ? event.clientX : event.clientY;
      const rect = grid.getBoundingClientRect();
      const size = axis === 'x' ? rect.width : rect.height;
      const fr = axis === 'x' ? colFr : rowFr;
      const from = fr.slice();
      const total = from[0] + from[1];
      document.body.classList.add('resizing', axis === 'x' ? 'resizing-x' : 'resizing-y');
      handle.classList.add('active');
      const move = (e) => {
        const delta = ((axis === 'x' ? e.clientX : e.clientY) - start) / size * total;
        const left = Math.max(total * 0.2, Math.min(total * 0.8, from[0] + delta));
        fr[0] = left;
        fr[1] = total - left;
        applySizes();
      };
      const end = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', end);
        document.body.classList.remove('resizing', 'resizing-x', 'resizing-y');
        handle.classList.remove('active');
        persist();
        hooks.onResize();
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', end);
    });
    handle.addEventListener('dblclick', () => {
      if (axis === 'x') colFr = [1, 1]; else rowFr = [1, 1];
      applySizes();
      persist();
      hooks.onResize();
    });
  }

  // ---------------------------------------------------------------- session

  function persist() {
    if (typeof Session === 'undefined' || !cells.length) return;
    const list = cells.map((cell, i) => {
      if (i === active) return current();
      return { symbol: cell.ws.symbol, timeframe: cell.ws.timeframe,
               indicators: cell.indicators.size ? snapshotOf(cell.indicators) : (cell.ws.indicators || []) };
    });
    Session.patch({ multi: { v: 3, layout, active, cells: list, cols: colFr, rows: rowFr } });
  }

  /* Put a remembered layout back. The working cell is the chart the app built
     from the session's own fields; every other cell is created and loads its
     own market, frame and indicators. */
  function restore(snap) {
    if (!snap || ![2, 3].includes(snap.v) || !LAYOUTS.includes(snap.layout) || !Array.isArray(snap.cells)) {
      return layout;
    }
    const saved = snap.cells
      .filter((c) => c && typeof c.symbol === 'string' && typeof c.timeframe === 'string')
      .map((c) => ({ symbol: c.symbol, timeframe: c.timeframe,
                     indicators: Array.isArray(c.indicators) ? c.indicators : [] }));
    if (saved.length !== snap.layout) return layout;

    const okFr = (f) => Array.isArray(f) && f.length === 2 && f.every((x) => x > 0);
    if (okFr(snap.cols)) colFr = snap.cols.slice();
    if (okFr(snap.rows)) rowFr = snap.rows.slice();

    const working = cells[0];
    const at = Math.min(Math.max(0, snap.active | 0), snap.layout - 1);
    layout = snap.layout;
    cells = saved.map((ws, i) => (i === at ? working : create(ws)));
    active = at;
    build();
    return layout;
  }

  // ---------------------------------------------------------------- wiring

  function init(config) {
    grid = config.grid;
    hooks = config;
    colHandle = document.createElement('div');
    colHandle.className = 'grid-handle grid-handle-col';
    colHandle.setAttribute('role', 'separator');
    colHandle.setAttribute('aria-orientation', 'vertical');
    rowHandle = document.createElement('div');
    rowHandle.className = 'grid-handle grid-handle-row';
    rowHandle.setAttribute('role', 'separator');
    rowHandle.setAttribute('aria-orientation', 'horizontal');
    bindHandle(colHandle, 'x');
    bindHandle(rowHandle, 'y');

    cells = [adopt(config.workUnit)];
    active = 0;
    layout = 1;
    build();
    if ('ResizeObserver' in window) new ResizeObserver(placeHandles).observe(grid);
  }

  return {
    init, setLayout, setOptions, setMode, syncActive, restore, activate,
    get layout() { return layout; },
    get active() { return active; },
    get activeCell() { return cells[active] || null; },
    // For probes: the chart a cell owns.
    managerAt: (i) => cells[i]?.manager || null,
    get cells() { return cells.map((cell) => wsOf(cell)); },
  };
})();
