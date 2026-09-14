/* One, two or four charts — every one of them a full chart.

   Nam's rule (2026-09-17): the second and fourth charts must do what the first
   does — indicators, strategy tests, drawings — each with its own timeframe
   behind a gear, and a short caption under it.

   How, without four copies of ChartManager.

   ChartManager owns one Lightweight chart and everything hung off it: indicator
   overlays and panes kept in index sync (§3.3), drawings, trade markers, paper
   position lines, the history pager, the live feed. Making all of that
   multi-instance would thread an instance id through every one of those
   features. Instead each cell holds a *workspace* — a symbol, a timeframe and
   the indicators with their parameters — and the full chart lives in whichever
   cell is active, the way a multi-chart layout in a charting package works: one
   chart has the focus, and the toolbar, the panels and the drawing rail act on
   it. Clicking another cell moves the working chart there and loads that
   cell's workspace into it; the cell it left keeps showing its own candles and
   indicators, drawn from the same compute endpoint.

   So everything the main chart can do, any cell can do the moment it is
   clicked, and nothing about indicators, strategies or drawings had to learn
   that there is more than one chart.

   The limit, stated rather than discovered (§2.7): only the active cell is
   live. The others are a snapshot taken when they were drawn — as far back as
   they have been panned, a page at a time — and are redrawn when their
   timeframe, symbol or indicators change. A strategy runs on the active cell. */

const MultiChart = (() => {
  const PASSIVE_BARS = 600;
  // Older bars arrive a page at a time as a cell is panned left; there is no
  // ceiling on how far back it can go other than the data itself.
  const PAGE_BARS = 1000;
  const LAYOUTS = [1, 2, 4];

  let grid = null;
  let workUnit = null;
  let hooks = {};
  let layout = 1;
  let active = 0;
  let mode = 'trading';
  let cells = [];                      // [{ symbol, timeframe, indicators: [{ id, params }] }]
  const passive = new Map();           // cell index -> { chart, token }
  let optionsHtml = '';
  let colFr = [1, 1];
  let rowFr = [1, 1];
  let pendingSwitch = null;

  const THEME = {
    layout: {
      background: { color: '#ffffff' },
      textColor: '#72727a',
      fontSize: 11,
      fontFamily: "'Be Vietnam Pro', 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif",
    },
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    rightPriceScale: { borderColor: '#ececee' },
    timeScale: { borderColor: '#ececee', timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
  };

  const CANDLES = {
    upColor: '#089981', downColor: '#f23645',
    borderUpColor: '#089981', borderDownColor: '#f23645',
    wickUpColor: '#089981', wickDownColor: '#f23645',
  };

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

  const toChart = (t) => (typeof ChartManager !== 'undefined' ? ChartManager.toChartTime(t) : t);

  // ---------------------------------------------------------------- workspaces

  /** What the active cell holds right now, read from the app. */
  const current = () => hooks.current();
  const wsAt = (i) => (i === active ? current() : cells[i]);

  /* A new cell opens on a market not already on screen, never on a blank.
     An empty cell could not be clicked into — there is nothing to load into
     the working chart — and a copy of a market already shown says nothing. */
  function freshWorkspace() {
    const shown = new Set(cells.map((c) => c?.symbol).concat(current().symbol));
    const candidates = ['VN:VNINDEX', 'VN:VN30F1M', 'VN:G-XAUUSD', 'BTCUSDT', 'VN:VIC', 'VN:FPT', 'ETHUSDT'];
    const symbol = candidates.find((s) => !shown.has(s)) || current().symbol;
    return { symbol, timeframe: fitTimeframe(symbol, current().timeframe), indicators: [] };
  }

  function fitTimeframe(symbol, wanted) {
    const frames = hooks.timeframes(symbol) || [];
    if (frames.includes(wanted)) return wanted;
    return frames.includes('1d') ? '1d' : (frames[frames.length - 1] || wanted);
  }

  // ---------------------------------------------------------------- layout

  function setLayout(next) {
    if (!LAYOUTS.includes(next) || next === layout) return layout;
    cells[active] = current();

    // The working chart keeps working: it moves to the first cell rather than
    // disappearing with a cell that the smaller layout no longer has.
    if (active !== 0) {
      const [ws] = cells.splice(active, 1);
      cells.unshift(ws);
      active = 0;
    }
    cells = cells.slice(0, next);
    while (cells.length < next) cells.push(freshWorkspace());
    layout = next;
    build();
    return layout;
  }

  /** Draw the cells. The working chart's DOM is moved, never re-created. */
  function build() {
    if (!grid) return;
    closeMenu();
    for (const i of [...passive.keys()]) disposePassive(i);
    workUnit.classList.remove('pending');
    pendingSwitch = null;

    // Park the working chart outside the grid while the grid is rewritten, or
    // `innerHTML` would destroy the chart along with the cells.
    const parking = document.createDocumentFragment();
    parking.appendChild(workUnit);

    grid.dataset.layout = String(layout);
    grid.innerHTML = cells.map((_, i) => `
      <div class="cell" data-cell="${i}">
        <div class="cell-head">
          <span class="cell-badge" data-badge="${i}"></span>
          <select class="cell-pick" data-pick="${i}" aria-label="${esc(t('mc.choose'))}">
            <option value=""></option>${optionsHtml}
          </select>
          <button type="button" class="cell-gear" data-gear="${i}" aria-haspopup="menu"
                  aria-expanded="false" title="${esc(L('Cài đặt biểu đồ', 'Chart settings'))}"
                  aria-label="${esc(L('Cài đặt biểu đồ', 'Chart settings'))}">${GEAR}</button>
        </div>
        <div class="cell-body" data-body="${i}"></div>
        <div class="cell-caption" data-caption="${i}"></div>
      </div>`).join('')
      + (layout > 1 ? '<div class="grid-handle grid-handle-col" role="separator" aria-orientation="vertical"></div>' : '')
      + (layout === 4 ? '<div class="grid-handle grid-handle-row" role="separator" aria-orientation="horizontal"></div>' : '');

    grid.querySelector(`[data-body="${active}"]`).appendChild(workUnit);

    for (const cell of grid.querySelectorAll('.cell')) {
      const i = Number(cell.dataset.cell);
      const select = cell.querySelector('.cell-pick');
      select.value = wsAt(i)?.symbol || '';
      select.addEventListener('change', () => setCellSymbol(i, select.value));
      if (typeof SymbolPicker !== 'undefined') {
        SymbolPicker.attach(select, { placeholder: () => t('mc.choose') });
      }
      cell.querySelector('.cell-gear').addEventListener('click', (event) => {
        event.stopPropagation();
        if (menuFor === i) closeMenu(); else openMenu(i, event.currentTarget);
      });
      // Capture, so the click reaches us before the chart turns it into a pan.
      cell.querySelector('.cell-body').addEventListener('pointerdown', () => {
        if (i !== active) activate(i);
      }, { capture: true });
    }

    const col = grid.querySelector('.grid-handle-col');
    const row = grid.querySelector('.grid-handle-row');
    if (col) bindHandle(col, 'x');
    if (row) bindHandle(row, 'y');

    /* Every cell gets its snapshot now, the active one included (it sits
       under the working chart). Mounting it lazily made the first click away
       from the starting cell fetch that cell's candles, measured as one extra
       request on the first switch and none after. */
    cells.forEach((_, i) => mountPassive(i));
    paintAll();
    applySizes();
    persist();
    hooks.onResize();
  }

  /* Give the working chart to cell `i` — without reloading anything else.

     Two things used to flash on every click. The cell being left refetched
     and redrew its chart, and the cell being entered went blank while the
     working chart loaded into it. Now:

     * every cell keeps its own snapshot chart underneath, including the active
       one. The cell being left simply shows it again, and it is redrawn only
       if what the cell holds changed while it was the working chart (another
       symbol, frame or indicator);
     * the cell being entered keeps showing its snapshot until the working
       chart has the new series, and only then does the working chart appear
       over it. */
  function activate(i) {
    if (mode === 'overview' || i === active || !cells[i]) return;
    closeMenu();
    const leaving = active;
    const ws = current();
    cells[leaving] = ws;

    const kept = passive.get(leaving);
    if (!kept || kept.signature !== signature(ws)) mountPassive(leaving);

    workUnit.classList.add('pending');
    grid.querySelector(`[data-body="${i}"]`).appendChild(workUnit);
    active = i;
    const token = {};
    pendingSwitch = token;
    paintAll();
    persist();
    hooks.onResize();

    Promise.resolve(hooks.load(cells[i])).catch(() => {}).finally(() => {
      if (pendingSwitch !== token) return;
      pendingSwitch = null;
      workUnit.classList.remove('pending');
      hooks.onResize();
    });
  }

  function setCellSymbol(i, symbol) {
    if (!symbol) { paint(i); return; }
    if (i === active) {
      if (symbol !== current().symbol) hooks.setActiveSymbol(symbol);
      return;
    }
    const ws = cells[i];
    if (ws.symbol === symbol) return;
    ws.symbol = symbol;
    ws.timeframe = fitTimeframe(symbol, ws.timeframe);
    mountPassive(i);
    paint(i);
    persist();
  }

  function setCellTimeframe(i, timeframe) {
    if (i === active) {
      hooks.setActiveTimeframe(timeframe);
      return;
    }
    if (cells[i].timeframe === timeframe) return;
    cells[i].timeframe = timeframe;
    mountPassive(i);
    paint(i);
    persist();
  }

  /** The app calls this whenever the working chart's series or indicators change. */
  function syncActive() {
    if (!grid || !cells.length) return;
    cells[active] = current();
    paint(active);
    persist();
  }

  /* Overview shows the working chart alone, full screen; the other cells are
     hidden, not torn down, so returning to the working view finds the layout
     exactly as it was left (Nam, 2026-09-17). */
  function setMode(next) {
    mode = next;
    closeMenu();
    hooks.onResize?.();
  }

  // ---------------------------------------------------------------- passive cells

  function disposePassive(i) {
    const held = passive.get(i);
    if (!held) return;
    try { held.chart.remove(); } catch { /* already gone */ }
    held.plot.remove();
    passive.delete(i);
  }

  /** What a snapshot was drawn from; a different signature means redraw. */
  const signature = (ws) => JSON.stringify([ws?.symbol, ws?.timeframe, ws?.indicators || []]);

  async function mountPassive(i) {
    disposePassive(i);
    const ws = cells[i] ? { ...cells[i], indicators: [...(cells[i].indicators || [])] } : null;
    const body = grid?.querySelector(`[data-body="${i}"]`);
    if (!body || !ws?.symbol) return;
    body.querySelector('.cell-error')?.remove();

    // First in the cell, so the working chart (when it is here) sits on top.
    const plot = document.createElement('div');
    plot.className = 'cell-plot';
    body.prepend(plot);

    const chart = LightweightCharts.createChart(plot, { ...THEME, autoSize: true });
    const entry = {
      chart, plot, ws,
      candles: chart.addCandlestickSeries(CANDLES),
      lines: [],
      bars: [],
      signature: signature(ws),
      paging: false,
      exhausted: false,
    };
    passive.set(i, entry);
    const stale = () => passive.get(i) !== entry;

    try {
      const data = await API.candles({ symbol: ws.symbol, timeframe: ws.timeframe, limit: PASSIVE_BARS });
      if (stale()) return;
      entry.bars = data.candles || [];
      paintCandles(entry);
      await paintIndicators(entry);
      if (stale()) return;

      const n = entry.bars.length;
      if (n) chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 160), to: n + 3 });

      // Pan toward the oldest bar and the page before it loads, as on the
      // working chart.
      chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
        if (!range || range.from > 40 || entry.paging || entry.exhausted || stale()) return;
        pageBack(entry, stale);
      });
    } catch (err) {
      if (stale()) return;
      disposePassive(i);
      body.insertAdjacentHTML('afterbegin', `<p class="empty cell-error">${esc(err.message)}</p>`);
    }
  }

  function paintCandles(entry) {
    entry.candles.setData(entry.bars.map((c) => ({
      time: toChart(c.time), open: c.open, high: c.high, low: c.low, close: c.close,
    })));
  }

  /* Indicators the way the working chart draws them, in one chart: price
     outputs on the price scale, "separate" outputs (RSI, bandwidth…) on their
     own scale in the bottom quarter so they cannot drag the price axis toward
     zero. Computed over every bar the cell holds, so paging back extends them. */
  async function paintIndicators(entry) {
    const { chart, ws } = entry;
    const limit = Math.max(PASSIVE_BARS, entry.bars.length);
    const results = await Promise.all(ws.indicators.map((ind) => API.compute({
      indicatorId: ind.id, symbol: ws.symbol, timeframe: ws.timeframe, params: ind.params, limit,
    }).catch(() => null)));   // one plugin that raises must not blank the cell

    for (const series of entry.lines) {
      try { chart.removeSeries(series); } catch { /* chart gone */ }
    }
    entry.lines = [];

    let separate = false;
    results.forEach((result) => {
      if (!result) return;
      result.outputs.forEach((output) => {
        const own = output.pane === 'separate';
        separate = separate || own;
        const common = {
          color: output.color || '#1c2f5e',
          priceLineVisible: false,
          lastValueVisible: false,
          ...(own ? { priceScaleId: 'sub' } : {}),
        };
        const series = output.plot_type === 'histogram'
          ? chart.addHistogramSeries(common)
          : chart.addLineSeries({ ...common, lineWidth: 1.5, crosshairMarkerVisible: false });
        const values = result.values[output.key] || [];
        series.setData(result.times.map((time, n) => (
          values[n] === null || values[n] === undefined
            ? { time: toChart(time) } : { time: toChart(time), value: values[n] })));
        entry.lines.push(series);
      });
    });
    if (separate) {
      chart.priceScale('right').applyOptions({ scaleMargins: { top: 0.06, bottom: 0.32 } });
      chart.priceScale('sub').applyOptions({ scaleMargins: { top: 0.74, bottom: 0.02 } });
    }
  }

  async function pageBack(entry, stale) {
    const oldest = entry.bars[0]?.time;
    if (oldest === undefined) return;
    entry.paging = true;
    try {
      const data = await API.candlesBefore({
        symbol: entry.ws.symbol, timeframe: entry.ws.timeframe, before: oldest, limit: PAGE_BARS,
      });
      if (stale()) return;
      const older = (data.candles || []).filter((c) => c.time < oldest);
      if (!older.length) {
        entry.exhausted = true;          // nothing older: stop asking on every pan
        return;
      }
      const range = entry.chart.timeScale().getVisibleLogicalRange();
      entry.bars = [...older, ...entry.bars];
      paintCandles(entry);
      // Everything moved right by the bars added; keep the same bars in view.
      if (range) {
        entry.chart.timeScale().setVisibleLogicalRange({
          from: range.from + older.length, to: range.to + older.length,
        });
      }
      await paintIndicators(entry);
    } catch {
      entry.exhausted = true;
    } finally {
      entry.paging = false;
    }
  }

  // ---------------------------------------------------------------- heads and captions

  function paint(i) {
    const cell = grid?.querySelector(`[data-cell="${i}"]`);
    const ws = wsAt(i);
    if (!cell || !ws) return;
    cell.classList.toggle('active', i === active);

    const badge = cell.querySelector('.cell-badge');
    badge.innerHTML = ws.symbol ? Paper.symbolBadge(ws.symbol) : '';

    const select = cell.querySelector('.cell-pick');
    if (select.value !== ws.symbol) select.value = ws.symbol || '';

    const names = hooks.describe(ws.indicators || []);
    const parts = [String(ws.symbol || '').replace(/^VN:/, ''), ws.timeframe, ...names].filter(Boolean);
    const caption = cell.querySelector('.cell-caption');
    caption.textContent = parts.join('  ·  ');
    caption.title = caption.textContent;
  }

  function paintAll() {
    cells.forEach((_, i) => paint(i));
  }

  function setOptions(groups) {
    optionsHtml = (groups || []).map((group) =>
      `<optgroup label="${esc(group.label)}">` +
      group.options.map((o) => `<option value="${esc(o.id)}">${esc(o.text)}</option>`).join('') +
      '</optgroup>').join('');
    if (!grid) return;
    for (const select of grid.querySelectorAll('.cell-pick')) {
      const i = Number(select.dataset.pick);
      select.innerHTML = `<option value=""></option>${optionsHtml}`;
      select.value = wsAt(i)?.symbol || '';
    }
  }

  // ---------------------------------------------------------------- gear menu

  const menu = document.createElement('div');
  menu.className = 'cell-menu';
  menu.setAttribute('role', 'menu');
  menu.hidden = true;
  document.body.appendChild(menu);
  let menuFor = null;

  function openMenu(i, button) {
    closeMenu();
    const ws = wsAt(i);
    if (!ws) return;
    menuFor = i;
    const frames = hooks.timeframes(ws.symbol) || [];
    menu.innerHTML = `
      <div class="cell-menu-title">${esc(L('Khung thời gian', 'Timeframe'))}</div>
      <div class="cell-menu-frames">${frames.map((tf) => `
        <button type="button" role="menuitemradio" aria-checked="${tf === ws.timeframe}"
                class="cell-menu-tf${tf === ws.timeframe ? ' active' : ''}" data-tf="${esc(tf)}">${esc(tf)}</button>`).join('')}
      </div>
      ${i === active
        ? `<p class="cell-menu-note">${esc(L(
          'Chỉ báo, chiến lược và hình vẽ đang áp dụng lên biểu đồ này.',
          'Indicators, strategies and drawings apply to this chart.'))}</p>`
        : `<button type="button" class="btn btn-sm btn-block cell-menu-work" data-work>${esc(L(
          'Làm việc trên biểu đồ này', 'Work on this chart'))}</button>`}`;

    menu.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    const rect = button.getBoundingClientRect();
    const width = menu.offsetWidth;
    menu.style.left = `${Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8))}px`;
    menu.style.top = `${rect.bottom + 6}px`;
  }

  function closeMenu() {
    if (menuFor === null) return;
    grid?.querySelector(`[data-gear="${menuFor}"]`)?.setAttribute('aria-expanded', 'false');
    menuFor = null;
    menu.hidden = true;
  }

  menu.addEventListener('click', (event) => {
    const i = menuFor;
    const tf = event.target.closest('[data-tf]')?.dataset.tf;
    if (tf) { closeMenu(); setCellTimeframe(i, tf); return; }
    if (event.target.closest('[data-work]')) { closeMenu(); activate(i); }
  });
  document.addEventListener('mousedown', (event) => {
    if (menuFor === null || menu.contains(event.target)) return;
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
  }

  function placeHandles() {
    const first = grid?.querySelector('[data-cell="0"]');
    if (!first) return;
    const col = grid.querySelector('.grid-handle-col');
    const row = grid.querySelector('.grid-handle-row');
    if (col) col.style.left = `${first.offsetLeft + first.offsetWidth}px`;
    if (row) row.style.top = `${first.offsetTop + first.offsetHeight}px`;
  }

  /* Drag a divider. Both neighbours keep at least 20% of their pair, and the
     cursor is pinned for the whole gesture. Double-click puts the default back. */
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
    Session.patch({ multi: { v: 2, layout, active, cells, cols: colFr, rows: rowFr } });
  }

  /* Put a remembered layout back. The active cell's own series and indicators
     are restored by the app from the session's top-level fields, so its entry
     here is refreshed from the app rather than trusted. */
  function restore(snap) {
    if (!snap || snap.v !== 2 || !LAYOUTS.includes(snap.layout) || !Array.isArray(snap.cells)) {
      return layout;
    }
    const valid = snap.cells
      .filter((c) => c && typeof c.symbol === 'string' && typeof c.timeframe === 'string')
      .map((c) => ({ symbol: c.symbol, timeframe: c.timeframe,
                     indicators: Array.isArray(c.indicators) ? c.indicators : [] }));
    if (valid.length !== snap.layout) return layout;

    const okFr = (f) => Array.isArray(f) && f.length === 2 && f.every((x) => x > 0);
    if (okFr(snap.cols)) colFr = snap.cols.slice();
    if (okFr(snap.rows)) rowFr = snap.rows.slice();
    layout = snap.layout;
    cells = valid;
    active = Math.min(Math.max(0, snap.active | 0), layout - 1);
    const saved = cells[active];
    cells[active] = { ...current(), indicators: saved.indicators };
    build();
    return layout;
  }

  // ---------------------------------------------------------------- wiring

  function init(config) {
    grid = config.grid;
    workUnit = config.workUnit;
    hooks = config;
    cells = [current()];
    active = 0;
    layout = 1;
    build();
    if ('ResizeObserver' in window) new ResizeObserver(placeHandles).observe(grid);
  }

  return {
    init, setLayout, setOptions, setMode, syncActive, restore, activate,
    get layout() { return layout; },
    get active() { return active; },
    get cells() { return cells.map((c, i) => (i === active ? current() : c)); },
  };
})();
