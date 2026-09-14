/* Two or four markets side by side.

   Deliberately NOT a second copy of ChartManager. That module owns one chart
   and everything hung off it — indicators, drawings, paper position lines,
   the marker store, the history pager. Making it multi-instance would mean
   threading an instance id through all of that, and every one of those
   features only makes sense on the chart you are actually working in.

   So the working chart stays where it is and keeps its whole toolset, and
   this band adds plain candle panes above it. "4" means four markets on
   screen: three panes here plus the working chart, not a 2x2 of equals. A
   quadrant grid would leave the working chart outside it and the fourth
   quadrant empty — which is exactly what it looked like, a hole rather than
   a layout. The chart you are working in should be the big one anyway.

   The panes are independent charts on purpose: two markets rarely share a
   session calendar (BTC runs all night, HOSE does not), so a shared time
   scale would either stretch one or crop the other. §3.3's alignment rule is
   about indicator panes under ONE price series, which is a different problem
   from this one. */

const MultiChart = (() => {
  let host = null;
  let layout = 1;                   // 1, 2 or 4 markets on screen
  let symbols = [];                 // extra symbols, one per cell beside the working chart
  let optionsHtml = '';             // the shared symbol catalogue, as <optgroup> markup
  let timeframe = '1h';
  const cells = new Map();          // cell index -> { chart, series, plot }

  /* Sizes the user dragged to. `null` height means the stylesheet's default
     share; `fractions` are the three columns of the "4" layout. Both are
     remembered with the rest of the session. */
  let heightPx = null;
  let fractions = [1, 1, 1];
  let rowHandle = null;
  let onResize = () => {};

  // Same axis face and greys as the working chart (charts.js), so a pane
  // beside it reads as part of one screen rather than a second widget.
  const THEME = {
    layout: {
      background: { color: '#ffffff' },
      textColor: '#72727a',
      fontSize: 11,
      fontFamily: "'Be Vietnam Pro', 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif",
    },
    grid: {
      vertLines: { visible: false },
      horzLines: { visible: false },
    },
    rightPriceScale: { borderColor: '#ececee' },
    timeScale: { borderColor: '#ececee', timeVisible: true, secondsVisible: false },
    crosshair: { mode: 0 },
    handleScale: { axisPressedMouseMove: { time: true, price: false } },
  };

  const CANDLES = {
    upColor: '#089981', downColor: '#f23645',
    borderUpColor: '#089981', borderDownColor: '#f23645',
    wickUpColor: '#089981', wickDownColor: '#f23645',
  };

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /** How many extra cells this layout needs beside the working chart. */
  const extraCells = () => Math.max(0, layout - 1);

  const blankOption = () => `<option value="">${esc(t('mc.choose'))}</option>`;

  /* ---------- the catalogue ----------

     Filled from the groups the main symbol picker already built, so there is
     one list of markets rather than two that drift apart. A <select> and not
     a prompt(): the catalogue is 1,728 entries deep and grouped by instrument
     family, which a text box cannot show — and a modal dialog blocks the page
     for as long as it is open, so nothing else can run while one is up. */
  function setOptions(groups) {
    optionsHtml = (groups || []).map((group) =>
      `<optgroup label="${esc(group.label)}">` +
      group.options.map((o) => `<option value="${esc(o.id)}">${esc(o.text)}</option>`).join('') +
      '</optgroup>').join('');

    if (!host) return;
    for (const select of host.querySelectorAll('.mc-pick')) {
      /* The market this cell holds, not whatever the <select> shows.

         A restored session mounts its panes before the Vietnamese catalogue
         has arrived, so `select.value = 'VN:VNINDEX'` finds no such option
         and silently stays empty. Re-reading that empty value here kept the
         pane charting VNINDEX under a blank name after every reload. */
      const chosen = symbols[Number(select.dataset.pick)] || select.value;
      select.innerHTML = blankOption() + optionsHtml;
      select.value = chosen || '';
    }
  }

  // ---------- layout ----------

  function setLayout(next) {
    layout = [1, 2, 4].includes(next) ? next : 1;
    // Trim the symbol list to fit. Padding it with the working chart's symbol
    // would show the same market twice, so spare cells stay empty until
    // something is chosen for them.
    symbols = symbols.slice(0, extraCells());
    build();
    return layout;
  }

  /** Draw the grid skeleton. Called on layout change only. */
  function build() {
    if (!host) return;
    teardown();
    host.hidden = layout === 1;
    host.dataset.layout = String(layout);
    if (layout === 1) {
      host.innerHTML = '';
      document.body.dataset.layout = '1';
      if (rowHandle) rowHandle.hidden = true;
      persist();
      return;
    }

    document.body.dataset.layout = String(layout);
    if (rowHandle) rowHandle.hidden = false;

    host.innerHTML = Array.from({ length: extraCells() }, (_, i) => `
      <div class="mc-cell" data-cell="${i}">
        <div class="mc-head">
          <span class="mc-badge" data-badge="${i}"></span>
          <select class="mc-pick" data-pick="${i}"
                  title="${esc(t('mc.choose'))}" aria-label="${esc(t('mc.choose'))}">
            ${blankOption()}${optionsHtml}
          </select>
        </div>
        <div class="mc-plot" data-plot="${i}"></div>
      </div>`).join('');

    for (const select of host.querySelectorAll('[data-pick]')) {
      const index = Number(select.dataset.pick);
      if (symbols[index]) select.value = symbols[index];
      select.addEventListener('change', () => setSymbolAt(index, select.value));
      // The same searchable list as the main picker: 1,728 markets are not
      // something to scroll through in a cell a few hundred pixels wide.
      if (typeof SymbolPicker !== 'undefined') {
        SymbolPicker.attach(select, { placeholder: () => t('mc.choose') });
      }
    }

    // Column dividers between the three panes of the "4" layout.
    if (layout === 4) {
      for (let i = 0; i < 2; i++) {
        const handle = document.createElement('div');
        handle.className = 'mc-col-handle';
        handle.setAttribute('role', 'separator');
        handle.setAttribute('aria-orientation', 'vertical');
        host.appendChild(handle);
        bindColumnHandle(handle, i);
      }
    }
    applySizes();
    persist();

    // Mount whatever survived the trim, one cell at a time.
    symbols.forEach((symbol, i) => { if (symbol) setSymbolAt(i, symbol); });
  }

  /* One cell changes, one cell is rebuilt.

     Re-rendering the whole band on every pick would tear down and refetch
     every other pane, and the in-flight loads of the panes being discarded
     would land on detached nodes. Touching one cell leaves the others still. */
  function setSymbolAt(index, symbol) {
    if (index < 0 || index >= extraCells()) return;
    const chosen = symbol ? String(symbol).trim() : '';
    symbols[index] = chosen || undefined;

    const select = host && host.querySelector(`[data-pick="${index}"]`);
    if (select && select.value !== chosen) select.value = chosen;

    const badge = host && host.querySelector(`[data-badge="${index}"]`);
    if (badge) badge.innerHTML = chosen ? Paper.symbolBadge(chosen) : '';

    dropCell(index);
    if (chosen) mount(index, chosen);
    persist();
  }

  // ---------- sizes ----------

  function applySizes() {
    if (!host) return;
    host.style.flexBasis = heightPx ? `${heightPx}px` : '';
    host.style.gridTemplateColumns = layout === 4
      ? fractions.map((f) => `${f.toFixed(4)}fr`).join(' ') : '';
    requestAnimationFrame(placeColumnHandles);
  }

  function placeColumnHandles() {
    if (!host) return;
    const cellNodes = host.querySelectorAll('.mc-cell');
    host.querySelectorAll('.mc-col-handle').forEach((handle, i) => {
      const cell = cellNodes[i];
      if (cell) handle.style.left = `${cell.offsetLeft + cell.offsetWidth - 5}px`;
    });
  }

  /* Shared drag plumbing: pointer capture on the document, a body class that
     pins the cursor for the whole gesture, and a save when the drag ends. */
  function drag(handle, axis, onMove, onReset) {
    handle.addEventListener('pointerdown', (event) => {
      event.preventDefault();
      const start = axis === 'x' ? event.clientX : event.clientY;
      const context = onMove.begin();
      document.body.classList.add('resizing', axis === 'x' ? 'resizing-x' : 'resizing-y');
      handle.classList.add('active');
      const move = (e) => {
        onMove.step(context, (axis === 'x' ? e.clientX : e.clientY) - start);
        applySizes();
        onResize();
      };
      const end = () => {
        document.removeEventListener('pointermove', move);
        document.removeEventListener('pointerup', end);
        document.body.classList.remove('resizing', 'resizing-x', 'resizing-y');
        handle.classList.remove('active');
        persist();
        onResize();
      };
      document.addEventListener('pointermove', move);
      document.addEventListener('pointerup', end);
    });
    // Double-click puts the default back, so a mis-drag is one gesture to undo.
    handle.addEventListener('dblclick', () => { onReset(); applySizes(); persist(); onResize(); });
  }

  function bindRowHandle() {
    if (!rowHandle) return;
    drag(rowHandle, 'y', {
      begin: () => ({
        height: host.getBoundingClientRect().height,
        room: host.parentElement.getBoundingClientRect().height,
      }),
      // The working chart keeps at least 220px: it is the one with the tools.
      step: (c, dy) => { heightPx = Math.round(Math.max(120, Math.min(c.room - 220, c.height + dy))); },
    }, () => { heightPx = null; });
  }

  function bindColumnHandle(handle, i) {
    drag(handle, 'x', {
      begin: () => ({
        width: host.getBoundingClientRect().width,
        start: fractions.slice(),
        sum: fractions.reduce((a, b) => a + b, 0),
      }),
      step: (c, dx) => {
        const pair = c.start[i] + c.start[i + 1];
        // Neither neighbour may shrink below 15% of the pair's width.
        const left = Math.max(pair * 0.15, Math.min(pair * 0.85, c.start[i] + (dx / c.width) * c.sum));
        fractions[i] = left;
        fractions[i + 1] = pair - left;
      },
    }, () => { fractions = [1, 1, 1]; });
  }

  // ---------- session ----------

  function persist() {
    if (typeof Session === 'undefined') return;
    Session.patch({
      multi: { layout, symbols: symbols.map((s) => s || null), height: heightPx, cols: fractions },
    });
  }

  /** Put a remembered layout back: sizes first, then panes, then markets. */
  function restore(snap) {
    if (!snap || ![1, 2, 4].includes(snap.layout)) return layout;
    heightPx = Number.isFinite(snap.height) ? snap.height : null;
    if (Array.isArray(snap.cols) && snap.cols.length === 3 && snap.cols.every((f) => f > 0)) {
      fractions = snap.cols.slice();
    }
    setLayout(snap.layout);
    (snap.symbols || []).forEach((symbol, i) => { if (symbol) setSymbolAt(i, symbol); });
    return layout;
  }

  function dropCell(index) {
    const held = cells.get(index);
    if (!held) return;
    try { held.chart.remove(); } catch { /* already gone */ }
    cells.delete(index);
  }

  function teardown() {
    for (const index of [...cells.keys()]) dropCell(index);
  }

  async function mount(index, symbol) {
    const plot = host.querySelector(`[data-plot="${index}"]`);
    if (!plot) return;
    plot.innerHTML = '';

    /* `autoSize`, not a width read once.

       The first version passed `plot.clientWidth` at creation. A pane created
       while the band was still being laid out got whatever width the cell had
       in that instant and kept it: picking a market in the "2" layout drew a
       chart about 1,060px wide inside a 1,750px cell, and nothing but a window
       resize ever corrected it. The library's own ResizeObserver tracks the
       cell for its whole life. */
    const chart = LightweightCharts.createChart(plot, { ...THEME, autoSize: true });
    const series = chart.addCandlestickSeries(CANDLES);
    cells.set(index, { chart, series, plot });

    // Comparison panes are a glance, not a workspace: a few hundred bars is
    // enough to see shape and costs a fraction of the main chart's request.
    const wanted = timeframe;
    try {
      const data = await API.candles({ symbol, timeframe: wanted, limit: 400 });
      // The user may have picked again, or changed timeframe, while this was
      // in the air. Anything but the current occupant of this cell is stale.
      if (cells.get(index)?.chart !== chart) return;
      if (symbols[index] !== symbol || timeframe !== wanted) return;
      series.setData((data.candles || []).map((c) => ({
        time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
      })));
      chart.timeScale().fitContent();
    } catch (err) {
      if (cells.get(index)?.chart !== chart) return;
      dropCell(index);
      plot.innerHTML = `<p class="empty">${esc(err.message)}</p>`;
    }
  }

  /* The timeframe follows the working chart, so a comparison is always
     like-for-like rather than a daily pane beside a minute one. */
  function setTimeframe(next) {
    if (timeframe === next) return;
    timeframe = next;
    symbols.forEach((symbol, i) => {
      dropCell(i);
      if (symbol) mount(i, symbol);
    });
  }

  // Kept for callers; `autoSize` already follows every resize on its own.
  function refreshSize() {}

  function init(config) {
    host = config.host;
    timeframe = config.timeframe || '1h';
    rowHandle = config.rowHandle || null;
    onResize = config.onResize || (() => {});
    bindRowHandle();
    if ('ResizeObserver' in window) new ResizeObserver(placeColumnHandles).observe(host);
  }

  return {
    init, setOptions, setLayout, setSymbolAt, setTimeframe, refreshSize, restore,
    get layout() { return layout; },
    get symbols() { return symbols.filter(Boolean); },
  };
})();
