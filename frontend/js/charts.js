/* Chart management: the main candle chart plus one synchronized pane per
   panel-type indicator.

   Lightweight Charts v4 has no native multi-pane support, so each panel
   indicator gets its own chart instance and the instances are kept in lockstep
   by mirroring the time scale and crosshair between them. */

// Shared by market charts and the backtest equity chart.
const CHART_FONT = "'Be Vietnam Pro', 'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif";

/* One chart per call. Each cell of the 1/2/4 layout owns one (multichart.js);
   `ChartManager`, below, always means the one the user is working on, so the
   rest of the app never has to know how many there are. */
function createChartManager() {
  /* Lightweight Charts renders its axis in UTC and v4 has no timezone option,
     so every timestamp is shifted by the display offset on the way in. Vietnam
     is UTC+7 all year: no daylight saving: so a fixed offset is exact, and a
     timezone library would buy nothing.

     Which offset is a setting (settings.js): Vietnam time by default, UTC for
     anyone reading the series as the backend stores it. Everything stored,
     compared and sent stays UTC; this offset exists only so the axis reads in
     the time the market actually traded. The series is redrawn when the
     setting changes — an axis that changed meaning while the candles did not
     would be two frames of reference on one screen. */
  const tzOffset = () => Settings.tzOffsetSeconds();

  const toChart = (epochSeconds) => epochSeconds + tzOffset();

  /* The axis speaks the interface's typeface, not a monospace one.

     A code face on the price scale made every label look like a debug
     readout, and it was a third family on a screen that otherwise has one.
     Be Vietnam Pro's figures are tabular when asked, so the scale's digits
     still line up column by column. Grid and borders are the same greys the
     stylesheet uses, so the plot does not read as a pasted-in widget. */
  /* No grid behind the candles by default (Nam, 2026-09-14) — the price axis
     and the crosshair already say where a value is — and a setting for anyone
     who reads a lattice faster. */
  function gridLines() {
    const visible = Settings.all().chart.grid;
    return { vertLines: { visible }, horzLines: { visible } };
  }

  const THEME = {
    layout: {
      background: { color: '#ffffff' },
      textColor: '#64738a',
      fontSize: 11,
      fontFamily: CHART_FONT,
    },
    // No grid behind the candles (Nam, 2026-09-14). The price axis and the
    // crosshair already say where a value is; the lattice was only noise.
    grid: gridLines(),
    rightPriceScale: { borderColor: '#ececee' },
    timeScale: { borderColor: '#ececee' },
    crosshair: {
      mode: 0, // free-moving crosshair
      vertLine: { color: '#9a9aa2', width: 1, style: 2, labelBackgroundColor: '#000000' },
      horzLine: { color: '#9a9aa2', width: 1, style: 2, labelBackgroundColor: '#000000' },
    },
  };

  let mainChart = null;
  let candleSeries = null;
  let volumeSeries = null;

  /** Overlay line series drawn on the main chart, keyed by instance id. */
  const overlays = new Map();
  /** Sub-pane charts, keyed by instance id. */
  const panes = new Map();

  let syncing = false; // guards the time-scale mirroring against feedback loops

  function allCharts() {
    return [mainChart, ...[...panes.values()].map((p) => p.chart)].filter(Boolean);
  }

  function syncFrom(source) {
    source.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (syncing || !range) return;
      syncing = true;
      for (const chart of allCharts()) {
        if (chart !== source) chart.timeScale().setVisibleLogicalRange(range);
      }
      syncing = false;
    });
  }

  /* Sizing is done here rather than with the library's `autoSize`.
     That option collapses the chart when its container is briefly 0 wide: a
     hidden panel, a minimised window: and does not always recover when the
     space comes back, leaving a chart stuck at a few pixels. Measuring the
     container ourselves and applying the size is deterministic. */
  const sizers = new Map();

  function trackSize(chart, container) {
    const apply = () => {
      const { width, height } = container.getBoundingClientRect();
      if (width > 0 && height > 0) chart.resize(width, height);
    };
    apply();

    const observer = new ResizeObserver(apply);
    observer.observe(container);
    sizers.set(chart, { observer, container });
    return observer;
  }

  function untrackSize(chart) {
    const entry = sizers.get(chart);
    if (entry) {
      entry.observer.disconnect();
      sizers.delete(chart);
    }
  }

  /* Re-measure every chart on demand.

     ResizeObserver is the primary mechanism but it is delivered on the
     rendering lifecycle, so a page that is not painting: a background tab, a
     hidden pane: never receives it and the chart stays at whatever size it
     last saw. Calling this after anything that changes the layout covers that
     without waiting for a frame. */
  function refreshSize() {
    for (const [chart, entry] of sizers) {
      const { width, height } = entry.container.getBoundingClientRect();
      if (width > 0 && height > 0) chart.resize(width, height);
    }
  }

  /* Colours for the overview area, kept next to each other because the fill
     has to be the line colour at low alpha or the gradient reads as a second
     series rather than as shading under the first. */
  const UP_TREND = {
    lineColor: '#089981',
    topColor: 'rgba(8, 153, 129, 0.28)',
    bottomColor: 'rgba(8, 153, 129, 0.02)',
    crosshairMarkerBackgroundColor: '#089981',
  };
  const DOWN_TREND = {
    lineColor: '#f23645',
    topColor: 'rgba(242, 54, 69, 0.28)',
    bottomColor: 'rgba(242, 54, 69, 0.02)',
    crosshairMarkerBackgroundColor: '#f23645',
  };

  let overviewSeries = null;
  let mode = 'overview';

  function paintOverview(colours) {
    if (overviewSeries) overviewSeries.applyOptions(colours);
  }

  /* Switch between the quote-page view and the working view.

     Overview is what the app opens on: one line, no volume, no indicator
     panes, nothing to configure. It answers "what has this thing been doing",
     which is the question someone has before they have any other question.
     Trading mode is everything else. */
  /* Put the newest bars on screen at a size you can actually read.

     The overview is meant to show a whole history at once, so its default
     range is every bar loaded. Carrying that into the working view means
     opening on two thousand candles compressed to a few pixels each — the
     first thing anyone does is zoom in, every time. A working chart opens
     where work happens: the recent end, at a candle width you can see.

     `bars` is a count rather than a zoom factor because the right amount of
     history is a number of bars, not a ratio: 180 candles is a readable
     screenful whether the series holds 500 of them or 20 000. */
  function focusRecent(bars = Settings.all().chart.bars) {
    if (!mainChart || !candleData.length) return;
    const scale = mainChart.timeScale();
    const last = candleData.length - 1;
    const span = Math.min(bars, candleData.length);
    scale.setVisibleLogicalRange({
      from: last - span + 1,
      // A little room past the last bar so the newest candle is not welded to
      // the right edge, which is where the price scale and its label sit.
      to: last + Math.max(4, Math.round(span * 0.04)),
    });
  }

  /** The whole loaded history, which is what the overview is for.

     Set as an explicit range rather than `fitContent()` so it matches the
     shape `focusRecent` uses, with the same small pad past the last bar: the
     two are the only two framings in the app and they should not be reached by
     two different mechanisms. */
  function fitAll() {
    if (!mainChart) return;
    if (!candleData.length) { mainChart.timeScale().fitContent(); return; }
    mainChart.timeScale().setVisibleLogicalRange({
      from: 0,
      to: candleData.length - 1 + Math.max(4, Math.round(candleData.length * 0.01)),
    });
  }

  function setMode(next) {
    if (next !== 'overview' && next !== 'trading') return mode;
    mode = next;
    const overview = mode === 'overview';

    candleSeries?.applyOptions({ visible: !overview });
    for (const s of extraSeries) s.applyOptions({ visible: !overview });
    volumeSeries?.applyOptions({ visible: !overview });
    overviewSeries?.applyOptions({ visible: overview });

    // Indicator panes and overlays belong to the working view only.
    for (const pane of panes.values()) {
      pane.element.hidden = overview;
    }
    for (const seriesList of overlays.values()) {
      for (const entry of seriesList) entry.series.applyOptions({ visible: !overview });
    }
    refreshSize();
    paintLevels();
    return mode;
  }

  function init(container) {
    mainChart = LightweightCharts.createChart(container, { ...THEME });

    /* Canvas text is measured with whatever face is loaded at the moment it
       is first drawn. The font is served locally and usually wins that race,
       but when it does not, the axis would keep the fallback's metrics for
       the whole session; re-applying the family once fonts settle re-measures
       it. */
    document.fonts?.ready.then(() => {
      for (const chart of allCharts()) {
        chart.applyOptions({ layout: { fontFamily: CHART_FONT } });
      }
    });
    trackSize(mainChart, container);

    buildPriceSeries(priceType);
    // Stop and target lines are dragged on the container, since the library
    // has no interactive price lines of its own.
    bindLevelDragging(container);

    volumeSeries = mainChart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '', // overlay scale, independent of the price axis
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.86, bottom: 0 },
    });

    /* The overview series: one line with a gradient under it, the shape a
       quote page uses. It lives on the same chart as the candles rather than
       on a chart of its own so that switching modes is a visibility change —
       no teardown, no refetch, and the time scale the user had scrolled to
       stays exactly where it was. */
    overviewSeries = mainChart.addAreaSeries({
      lineWidth: 2,
      priceLineVisible: false,
      crosshairMarkerBorderWidth: 2,
      visible: false,
    });
    paintOverview(UP_TREND);

    /* Panning left past the oldest bar asks for more history.

       Triggered on the *logical* range rather than on a pixel position,
       because the same gesture has to mean the same thing at every zoom level:
       "there are fewer than a screenful of bars left to the left of you".
       Lightweight Charts reports negative logical indices once the user pans
       past the start of the data, so `from < THRESHOLD` catches the approach
       rather than waiting for the wall. */
    mainChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (!range || !onNeedHistory || historyPending) return;
      const HEADROOM = 40;
      if (range.from > HEADROOM) return;
      const oldest = candleData.length ? candleData[0].time : null;
      if (oldest === null) return;
      historyPending = true;
      /* Chart time is shifted +7h for display (`toChart`); the API speaks UTC.
         Sending the shifted value asked for a page ending seven hours after the
         oldest bar actually held. The overlap was filtered out, so it looked
         harmless, but every page re-fetched bars the chart already had. */
      Promise.resolve(onNeedHistory(oldest - tzOffset()))
        .finally(() => { historyPending = false; });
    });

    // A window resize always reaches us, even when the observer does not.
    window.addEventListener('resize', refreshSize);

    syncFrom(mainChart);
    return mainChart;
  }

  /* The newest bar the price chart holds, in chart time.

     Indicator series are extended to reach it; see `reserveSlot`. */
  let lastBarTime = null;
  /* Which series the chart is currently holding, as "symbol|timeframe".

     The live socket already filters by series, but that filter is only as
     fresh as the last `Live.subscribe` call — and that call used to sit behind
     an await that could throw, leaving the socket subscribed to the previous
     symbol while the chart held the new one. Foreign candles then flowed
     straight into the price series: a VN index tick around 1 900 pushed into a
     Bitcoin series around 79 000. Checking here as well is defence at the
     layer that owns the data, and costs one string comparison per tick. */
  let seriesKey = null;
  /* Every candle currently on the chart, oldest first, so older pages can be
     prepended without refetching what is already drawn. Lightweight Charts has
     no "prepend" — setData replaces — so the series' own data has to be kept
     here to build the new array from. */
  let candleData = [];
  let volumeData = [];
  let onNeedHistory = null;

  /* Palette rotation across drawn instances.

     The backend hands out colours by output index *within* one indicator, so
     the first line of every indicator is the same blue: a chart with EMA, VWAP
     and a Bollinger mid was three blue lines. Each drawn instance takes the
     next offset into the same palette, so the second indicator starts where
     the first left off. Indicators that pick their own colours are left alone
     — `color_auto` says which is which.

     Kept in a Map keyed by instance so redrawing one (a parameter change,
     a recompute) does not renumber the others under it. */
  /* Navy only, alternating dark and light so neighbours still separate.
     Indicator lines are annotations on the price, and annotations are navy
     (Nam, 2026-09-14): no orange, purple or teal competing with the candles. */
  const PALETTE = [
    '#1c2f5e', '#5b7fc4', '#0b1633', '#8ea8dc',
    '#2f4a8a', '#b3c4e8', '#15244a', '#46659f',
  ];
  const instanceOffset = new Map();
  let nextOffset = 0;

  function colourFor(instanceId, output, outputIndex) {
    if (!output.color_auto) return output.color;
    if (!instanceOffset.has(instanceId)) {
      instanceOffset.set(instanceId, nextOffset);
      nextOffset += 1;
    }
    const base = instanceOffset.get(instanceId);
    return PALETTE[(base + outputIndex) % PALETTE.length];
  }
  let historyPending = false;

  /* ---------- Price series shape ----------

     The price is drawn by whichever series the chosen type builds, so
     `candleSeries` is no longer always a candlestick. Everything that touches
     it — markers, the last-value line, the live update — goes through it
     regardless, which is why the name stays: it is the price series, and it
     happens to be candles by default.

     `extraSeries` holds the ones a multi-series type adds (the HLC band's high
     and low lines). They are removed together when the type changes; leaving
     them behind is how a chart ends up with the ghost of a previous type
     drawn under the current one. */
  let priceType = 'candles';
  // Tells this chart's own drawing layer that the price series was replaced.
  let onSeriesChanged = null;
  let extraSeries = [];
  let applyPriceData = null;
  let updatePricePoint = null;

  function buildPriceSeries(typeId) {
    const built = ChartTypes.build(mainChart, typeId);
    candleSeries = built.series[0];
    extraSeries = built.series.slice(1);
    applyPriceData = built.apply;
    updatePricePoint = built.update;
    priceType = ChartTypes.has(typeId) ? typeId : 'candles';
  }

  /** Redraw the price in a different shape, keeping the view where it is. */
  function setPriceType(typeId) {
    if (!mainChart || !ChartTypes.has(typeId) || typeId === priceType) return priceType;

    // The visible range survives the swap: changing how the price is drawn is
    // not a reason to lose where the user had scrolled to.
    const scale = mainChart.timeScale();
    const range = scale.getVisibleLogicalRange();
    const keptMarkers = storedMarkers.slice();

    for (const s of [candleSeries, ...extraSeries]) {
      try { mainChart.removeSeries(s); } catch { /* already gone */ }
    }
    buildPriceSeries(typeId);
    if (candleData.length) applyPriceData(candleData);
    if (keptMarkers.length) applyMarkers();
    // Overview shares this chart, so it must not reappear in the working view.
    candleSeries.applyOptions({ visible: mode !== 'overview' });
    for (const s of extraSeries) s.applyOptions({ visible: mode !== 'overview' });
    // Drawings convert prices through the series, so they must be handed the
    // new one or every shape would stay anchored to a series that is gone.
    onSeriesChanged?.(candleSeries);
    if (range) scale.setVisibleLogicalRange(range);
    return priceType;
  }

  /* Is anything actually on screen?

     Nam has reported candles vanishing after a symbol switch, and three
     rounds of measurement failed to reproduce it (2026-09-17). Rather than
     keep guessing, the chart can now be asked, and there are two ways the
     answer can be "no":

       empty          the series holds no bars at all — a load that failed
       offPriceScale  bars exist, in the visible range, but the price axis is
                      somewhere else, which is what a frozen manual scale or a
                      bad autoscale looks like

     A third shape — bars present but scrolled out of view sideways — was
     measured and **cannot happen**: Lightweight Charts 4.2.3 silently refuses
     any visible range outside the data. Four attempts (500 bars past the end,
     5 past the end, 800 before the start, 5 before it) all left the range
     exactly where it was, so there is no branch for it here. */
  function diagnose() {
    if (!mainChart || !candleSeries) return null;
    const range = mainChart.timeScale().getVisibleLogicalRange();
    const bars = candleData.length;
    const last = bars ? candleData[bars - 1] : null;
    const y = last ? candleSeries.priceToCoordinate(last.close) : null;
    const height = mainChart.paneSize ? mainChart.paneSize().height : null;
    return {
      series: seriesKey,
      bars,
      from: range ? range.from : null,
      to: range ? range.to : null,
      autoScale: !!candleSeries.priceScale().options().autoScale,
      lastClose: last ? last.close : null,
      lastCloseY: Number.isFinite(y) ? y : null,
      height,
      empty: bars === 0,
      offPriceScale: !!(bars && Number.isFinite(y) && Number.isFinite(height)
                        && (y < 0 || y > height)),
    };
  }

  function applyDisplay() {
    for (const chart of allCharts()) chart.applyOptions({ grid: gridLines() });
  }

  function setCandles(candles, volumes, { timeVisible, key = null }) {
    seriesKey = key;
    for (const chart of allCharts()) {
      chart.applyOptions({ timeScale: { ...THEME.timeScale, timeVisible, secondsVisible: false } });
    }
    candleData = candles.map((c) => ({
      time: toChart(c.time),
      open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    applyPriceData(candleData);
    volumeData = volumes.map((v) => ({
      time: toChart(v.time),
      value: v.value,
      color: v.up ? 'rgba(18,128,92,0.28)' : 'rgba(200,55,45,0.28)',
    }));
    volumeSeries.setData(volumeData);

    /* The same closes as a line. Coloured by where the window ended against
       where it started, which is what a quote page's colour means — not the
       direction of the last tick, which is what the ticker in the header
       shows. The two are different questions and they are often opposite. */
    const line = candles.map((c) => ({ time: toChart(c.time), value: c.close }));
    overviewSeries?.setData(line);
    if (line.length > 1) {
      paintOverview(line[line.length - 1].value >= line[0].value ? UP_TREND : DOWN_TREND);
    }
    lastBarTime = candles.length ? toChart(candles[candles.length - 1].time) : null;

    /* Frame the new series the way the current mode wants it.

       This used to always fit the whole history, which is right for the
       overview and wrong for the working view: changing symbol there dropped
       you back to two thousand candles a few pixels wide, so the zoom had to
       be redone on every switch. The mode already knows which framing it
       wants; loading data should not override it. */
    /* A new series always starts with the price scale following its data.

       Dragging the plot vertically switches the scale to a manual range, and
       that range survived loading a different instrument: a scale frozen at
       75 000–80 000 from Bitcoin leaves a Vietnamese stock at 250 entirely
       off-screen, with only its volume (on its own scale) still visible —
       which is what "the candles disappeared after switching" looks like.
       A manual range is a choice about one series and ends with it. */
    mainChart.priceScale('right').applyOptions({ autoScale: true });

    if (mode === 'overview') mainChart.timeScale().fitContent();
    else focusRecent();
  }

  /** Convert {times, values[key]} into the points the chart wants.

     A missing value becomes a *whitespace* point: `{time}` with no value:
     rather than being dropped. The library reserves the slot and breaks the
     line there, which looks the same, but the series keeps one entry per
     candle.

     That matters because the sub-panes are separate charts kept in step by
     logical (index) range. Dropping the warm-up values left an indicator with
     1 445 points against 2 000 candles, so index 500 in the pane was a
     different bar from index 500 on the price chart and the panes drifted out
     of line: each ending short of the newest candle by a different amount. */
  function toPoints(times, values) {
    const points = [];
    for (let i = 0; i < times.length; i += 1) {
      const value = values[i];
      const time = toChart(times[i]);
      points.push(value === null || value === undefined ? { time } : { time, value });
    }
    return points;
  }

  function drawOverlay(instanceId, result) {
    removeOverlay(instanceId);
    const seriesList = [];

    result.outputs.forEach((output, i) => {
      const series = mainChart.addLineSeries({
        color: colourFor(instanceId, output, i),
        // Thinner than a candle body. An overlay sits on top of the price and
        // has to stay legible without hiding what it is drawn over.
        lineWidth: 1.5,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
      });
      const points = toPoints(result.times, result.values[output.key] || []);
      series.setData(points);
      seriesList.push({ series, points });
    });

    overlays.set(instanceId, seriesList);
    for (const entry of seriesList) reserveSlot(entry, lastBarTime);
  }

  /* Draw one indicator, splitting its outputs by the pane the backend assigned.

     An indicator is not always all-price or all-panel: Bollinger Bands puts
     three bands on the price axis and a bandwidth and percent somewhere else.
     Outputs marked "separate" go to their own pane so they cannot drag the
     price axis toward zero. */
  function draw(instanceId, result, paneContainer) {
    remove(instanceId);

    const onPrice = result.outputs.filter((o) => o.pane !== 'separate');
    const offScale = result.outputs.filter((o) => o.pane === 'separate');

    if (onPrice.length) {
      drawOverlay(instanceId, { ...result, outputs: onPrice });
    }
    if (offScale.length) {
      drawPane(instanceId, { ...result, outputs: offScale }, paneContainer);
    }
  }

  function removeOverlay(instanceId) {
    const seriesList = overlays.get(instanceId);
    if (!seriesList) return;
    for (const { series } of seriesList) mainChart.removeSeries(series);
    overlays.delete(instanceId);
  }

  function drawPane(instanceId, result, container) {
    removePane(instanceId);

    const element = document.createElement('div');
    element.className = 'chart-pane';

    const label = document.createElement('div');
    label.className = 'pane-label';
    label.textContent = result.name;
    element.appendChild(label);

    container.appendChild(element);

    const chart = LightweightCharts.createChart(element, {
      ...THEME,
      timeScale: { ...THEME.timeScale, visible: false },
    });
    trackSize(chart, element);

    const seriesList = [];
    result.outputs.forEach((output, i) => {
      const colour = colourFor(instanceId, output, i);
      const isHistogram = output.plot_type === 'histogram';
      const series = isHistogram
        ? chart.addHistogramSeries({ color: colour, priceLineVisible: false })
        : chart.addLineSeries({
            color: colour,
            lineWidth: 1.5,
            priceLineVisible: false,
            lastValueVisible: true,
          });
      let points = toPoints(result.times, result.values[output.key] || []);
      /* A histogram that crosses zero — MACD, momentum, most oscillators —
         reads far better split at the zero line than as one flat colour: the
         sign is the whole message, and a single colour makes the reader work
         it out from the geometry. Series that never cross zero (volume-like)
         keep the plain colour. */
      if (isHistogram) {
        const values = points.filter((pt) => pt.value !== undefined);
        const crossesZero = values.some((pt) => pt.value > 0)
          && values.some((pt) => pt.value < 0);
        if (crossesZero) {
          points = points.map((pt) => (pt.value === undefined ? pt : {
            ...pt,
            color: pt.value >= 0 ? 'rgba(8,153,129,0.55)' : 'rgba(242,54,69,0.55)',
          }));
        }
      }
      series.setData(points);
      seriesList.push({ series, points });
    });

    panes.set(instanceId, { chart, element, series: seriesList });
    // A recompute reads closed candles only, so a fresh pane is already a bar
    // or more behind the price chart the moment it is drawn.
    for (const entry of seriesList) reserveSlot(entry, lastBarTime);

    // Adopt the main chart's current zoom, then join the sync group.
    const range = mainChart.timeScale().getVisibleLogicalRange();
    if (range) chart.timeScale().setVisibleLogicalRange(range);
    syncFrom(chart);
  }

  function removePane(instanceId) {
    const pane = panes.get(instanceId);
    if (!pane) return;
    untrackSize(pane.chart);
    pane.chart.remove();
    pane.element.remove();
    panes.delete(instanceId);
  }

  function remove(instanceId) {
    removeOverlay(instanceId);
    removePane(instanceId);
  }

  function clearAll() {
    for (const id of [...overlays.keys()]) removeOverlay(id);
    for (const id of [...panes.keys()]) removePane(id);
  }


  /* Entry and exit markers, used by both backtests and paper sessions.

     `openPosition` marks a position a paper session is still holding: it has
     an entry but no exit yet, and leaving it off would make a running session
     look like it had never traded. */
  /* Markers are kept even while hidden. Hiding is a view setting: you toggle
     them off to read the price action underneath, then back on: so throwing
     the data away and asking the caller to re-run a backtest would be the
     wrong shape entirely. `clearTradeMarkers` is the one that forgets. */
  let storedMarkers = [];
  let markersVisible = true;

  function applyMarkers() {
    if (!candleSeries) return;
    candleSeries.setMarkers(markersVisible ? storedMarkers : []);
  }

  function setTradeMarkers(trades, openPosition = null) {
    const markers = [];

    for (const t of trades) {
      const isLong = t.side === 'long';
      markers.push({
        time: toChart(t.entry_time),
        position: isLong ? 'belowBar' : 'aboveBar',
        color: isLong ? '#12805c' : '#c8372d',
        shape: isLong ? 'arrowUp' : 'arrowDown',
        text: isLong ? 'L' : 'S',
      });
      markers.push({
        time: toChart(t.exit_time),
        position: isLong ? 'aboveBar' : 'belowBar',
        color: t.exit_reason === 'liquidation' ? '#c8372d' : '#949ca6',
        shape: 'circle',
        text: t.exit_reason === 'liquidation' ? 'LIQ' : '',
      });
    }

    if (openPosition && openPosition.entry_time) {
      const isLong = openPosition.side > 0;
      markers.push({
        time: toChart(openPosition.entry_time),
        position: isLong ? 'belowBar' : 'aboveBar',
        color: isLong ? '#12805c' : '#c8372d',
        shape: isLong ? 'arrowUp' : 'arrowDown',
        text: isLong ? 'LONG ●' : 'SHORT ●',
      });
    }

    // Markers must be sorted by time or the library drops them silently.
    markers.sort((a, b) => a.time - b.time);
    storedMarkers = markers;
    applyMarkers();
    onMarkersChanged(markerCount(), markersVisible);
  }

  /* ---------- Position lines: entry, stop and target ----------

     Markers say where a trade happened. A running position needs the other
     thing: where it is now relative to the levels that will close it. An arrow
     three hundred bars back does not answer "how far is my stop", and that is
     the question someone holding a position actually has.

     These are the library's own price lines, so they sit on the price scale
     with their value in the axis label and stay put through zoom and pan
     without any drawing code of ours. Dragging them is ours, because the
     library has no notion of a draggable line — see beginLevelDrag below. */
  let positionLines = { entry: null, stop: null, target: null };
  const NO_LEVELS = {
    side: 0, entry: null, stop: null, target: null, quantity: 0, label: '', unit: '', entryTime: null,
  };
  let levels = { ...NO_LEVELS };
  let onLevelDragged = null;
  // A drag in progress. A session pushed over the socket while the pointer is
  // down would rebuild the lines under it and drop the drag, so a redraw that
  // arrives meanwhile is held and applied on release.
  let levelDrag = null;
  let deferredLevels = null;

  const LEVEL_STYLE = {
    // The interface blue (Nam, 2026-09-15): the entry line marks a fact
    // about your own position, not a market direction, so it must not
    // borrow green or red. Two pixels keeps it apart from the grid. Its
    // label is the HTML chip below, which can hold a close button.
    entry: { color: '#3264e8', style: 0, title: '' },
    // Stop and target keep the market colours deliberately: a stop is the
    // losing side of the trade and a target the winning one, whichever way
    // the position points.
    stop: { color: '#f23645', style: 2, title: 'SL' },
    target: { color: '#089981', style: 2, title: 'TP' },
  };

  /* Money beside each line.

     The entry line carries the open P&L at the latest price and is refreshed
     on every live candle; a stop or target carries what the position would
     book if that level filled. Quantity is signed (negative for a short),
     exactly as the paper engine holds it, so `quantity × (price − entry)` is
     the number the server reports as unrealized P&L. Closing fees are not in
     it — the server charges them when the position closes — so a target's
     figure is before costs. */
  function signedAmount(value) {
    return `${value >= 0 ? '+' : '-'}${Math.abs(value).toLocaleString('en-US', {
      minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  /* The position's size, with its direction.

     The paper snapshot reports `quantity` as a magnitude and keeps the
     direction in `position`, so multiplying the raw number by the price move
     reads a short backwards: a short losing money showed a profit, its stop
     showed a gain and its target a loss (Nam, 2026-09-16). `side` is the field
     that carries direction, so the sign is taken from there and `quantity` is
     used only for how much. */
  function signedQuantity() {
    const size = Math.abs(Number(levels.quantity) || 0);
    return levels.side < 0 ? -size : size;
  }

  function levelTitle(key, price) {
    const quantity = signedQuantity();
    const pnl = Number.isFinite(price) && quantity && Number.isFinite(levels.entry)
      ? quantity * (price - levels.entry) : null;
    // Percent of the position's notional at entry: the price move, signed by side.
    const pct = pnl === null ? null : pnl / (Math.abs(quantity) * levels.entry) * 100;
    const points = pnl === null ? null
      : (price - levels.entry) * Math.sign(quantity);
    // Two decimals here whatever the setting says: this label sits on the
    // price axis, where a figure that changes width every tick is unreadable.
    const figure = pnl === null ? ''
      : Fmt.profit({ money: pnl, pct, points, unit: levels.unit, digits: 2, min: 2 });
    if (key !== 'entry') return figure ? `${LEVEL_STYLE[key].title} ${figure}` : LEVEL_STYLE[key].title;
    if (pnl === null) return levels.label;
    return `${levels.label}  ${figure}${
      Fmt.mode() === 'money' ? ` (${signedAmount(pct)}%)` : ''}`;
  }

  function latestClose() {
    return candleData.length ? candleData[candleData.length - 1].close : null;
  }

  const finiteOrNull = (value) => (Number.isFinite(value) ? value : null);

  function makeLevelLine(key, price) {
    if (!candleSeries || !Number.isFinite(price)) return null;
    return candleSeries.createPriceLine({
      price,
      color: LEVEL_STYLE[key].color,
      lineWidth: key === 'entry' ? 2 : 1,
      lineStyle: LEVEL_STYLE[key].style,
      axisLabelVisible: true,
      title: key === 'entry' ? '' : levelTitle(key, price),
    });
  }

  function removeLevelLine(key) {
    if (!positionLines[key]) return;
    try { candleSeries.removePriceLine(positionLines[key]); } catch { /* gone */ }
    positionLines[key] = null;
  }

  function clearPositionLines() {
    if (levelDrag) { deferredLevels = { side: 0 }; return; }
    for (const key of Object.keys(positionLines)) removeLevelLine(key);
    levels = { ...NO_LEVELS };
    stopWatchingLevels();
    paintLevels();
  }

  /** Draw the open position's entry and its exit levels, or clear them. */
  function setPositionLines(spec = {}) {
    if (levelDrag) { deferredLevels = spec; return; }
    const { side = 0, entry = null, stop = null, target = null,
            label = '', quantity = 0, unit = '', entryTime = null } = spec;
    clearPositionLines();
    if (!candleSeries || !side) return;
    levels = {
      side, entry, stop: finiteOrNull(stop), target: finiteOrNull(target),
      quantity: Number(quantity) || 0, label: label || (side > 0 ? 'LONG' : 'SHORT'), unit,
      entryTime: finiteOrNull(Number(entryTime)),
    };
    positionLines.entry = makeLevelLine('entry', entry);
    positionLines.stop = makeLevelLine('stop', levels.stop);
    positionLines.target = makeLevelLine('target', levels.target);
    paintLevels();
    watchLevels();
  }

  /** Keep the open P&L on the entry line in step with the price. */
  function refreshLevelTitles(price) {
    if (!levels.side || !Number.isFinite(price)) return;
    paintLevels();
  }

  /* Working the position on the chart.

     Lightweight Charts price lines are not interactive, so this works on the
     container. Three gestures, all on the lines themselves:

     - drag a stop or target to move it;
     - pull away from the entry line to create one. For a long, above the
       entry is the target and below it the stop; a short is the reverse. The
       side the pointer is on decides, so crossing back over the entry swaps
       which level is being set and puts the other back as it was;
     - drop a stop or target back onto the entry line to remove it.

     The entry never moves — it is a fact about a fill that already happened.
     The caller is told once, on release: an amendment per pixel would be a
     hundred requests per drag, and a release that changes nothing sends
     nothing. */
  const DRAG_GRAB_PX = 6;

  function levelY(price) {
    if (!Number.isFinite(price) || !candleSeries) return null;
    return candleSeries.priceToCoordinate(price);
  }

  function levelAt(y) {
    if (!levels.side) return null;
    // Exits first: a stop sitting right on the entry must still be movable.
    for (const key of ['stop', 'target', 'entry']) {
      const coord = levelY(levels[key]);
      if (coord !== null && Math.abs(coord - y) <= DRAG_GRAB_PX) return key;
    }
    return null;
  }

  /** Which exit a price would be for the open position. */
  function exitFor(price) {
    return (price > levels.entry) === (levels.side > 0) ? 'target' : 'stop';
  }

  /* A dragged level moves in the series' own price step, so what is sent is a
     price the axis could print (77912.34), not the pointer's float
     (1935.2365200241713 reached a stop-loss field before this). */
  function snapPrice(price) {
    const step = candleSeries?.options().priceFormat?.minMove || 0.01;
    const decimals = Math.max(0, Math.ceil(-Math.log10(step) - 1e-9));
    return Number((Math.round(price / step) * step).toFixed(decimals));
  }

  function placeLevel(key, price, title = null) {
    levels[key] = finiteOrNull(price);
    if (levels[key] === null) { removeLevelLine(key); return; }
    if (!positionLines[key]) positionLines[key] = makeLevelLine(key, price);
    positionLines[key]?.applyOptions({ price, title: title ?? levelTitle(key, price) });
    paintLevels();
  }

  /* The position as a trader reads it: a blue entry line carrying a chip
     (label, open P&L, a close button), a light green band between entry and
     target and a light red one between entry and stop. The bands start at the
     bar the position was opened on and run to the plot's right edge; before
     the entry there was no position to shade.

     Lightweight Charts has no filled-band primitive, so the bands are a canvas
     over the plot, repainted whenever the geometry can move: scroll, zoom,
     resize, a new candle, a drag. The canvas takes no pointer events, so
     panning and zooming reach the chart underneath. The chip is HTML because a
     price line's title is painted on the chart's own canvas and cannot hold a
     button. */
  const ZONE_ALPHA = { rest: 0.08, dragging: 0.15 };
  let levelOverlay = null;
  let onPositionClose = null;
  let lastZones = null;
  let levelWatch = null;
  let levelWatchTimer = null;
  let watchedMapping = '';

  function buildLevelOverlay(container) {
    const canvas = document.createElement('canvas');
    canvas.className = 'level-zones';
    const chip = document.createElement('div');
    chip.className = 'position-chip';
    chip.hidden = true;
    const label = document.createElement('span');
    const close = document.createElement('button');
    close.type = 'button';
    close.className = 'position-chip-close';
    close.textContent = '✕';
    close.addEventListener('click', (event) => {
      event.stopPropagation();
      onPositionClose?.();
    });
    chip.append(label, close);
    container.append(canvas, chip);
    const observer = new ResizeObserver(paintLevels);
    observer.observe(container);
    mainChart.timeScale().subscribeVisibleLogicalRangeChange(paintLevels);
    // The price axis can rescale while the time range stays put (autoscale on
    // a new extreme, a drag on the axis). The crosshair fires on every pointer
    // move over the plot, which is when such a change can be seen.
    mainChart.subscribeCrosshairMove(paintLevels);
    levelOverlay = { host: container, canvas, chip, label, close, observer };
  }

  /** x of the bar the position was opened on, in plot pixels. */
  function entryX() {
    if (!Number.isFinite(levels.entryTime) || !candleData.length) return 0;
    const t = toChart(levels.entryTime);
    if (t <= candleData[0].time) return 0;
    // A hand order fills between bar opens, so the band starts at the bar that
    // contains the fill: the last bar opening at or before it.
    let lo = 0;
    let hi = candleData.length - 1;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (candleData[mid].time <= t) lo = mid; else hi = mid - 1;
    }
    const x = mainChart.timeScale().logicalToCoordinate(lo);
    return x === null ? 0 : x;
  }

  /* Where the entry price lands, and how far one price unit is from it.

     Two numbers rather than one: a zoom centred exactly on the entry moves the
     scale without moving that price, and the stop and target bands would then
     be painted at the old scale. */
  function mappingSignature() {
    const at = levelY(levels.entry);
    if (at === null || !candleSeries) return '';
    return `${at}|${candleSeries.priceToCoordinate(levels.entry + 1)}`;
  }

  /* Repaint when the price mapping has actually moved.

     The overlay used to listen for a time-range change, a crosshair move over
     the plot, and a resize. A drag or a wheel on the price axis is none of
     those — the pointer never enters the plot and the time range stays put —
     so the line moved and its chip did not. Measured: 131px of drift after one
     squeeze of the axis (Nam, 2026-09-16). Autoscale jumping on a new extreme
     is the same class of change. */
  function syncLevels() {
    if (!levelOverlay || !levels.side) return;
    const signature = mappingSignature();
    if (signature === watchedMapping) return;
    watchedMapping = signature;
    paintLevels();
  }

  /* A frame loop while a position is on screen: a drag on the axis produces no
     event this overlay can hear, so the mapping is polled instead. It costs two
     coordinate lookups per frame, runs only while a position is drawn, and
     paints only when something moved. Pointer and wheel handlers call
     `syncLevels` too, so the overlay still follows where a frame loop does not
     run — a background tab, or headless Chrome. */
  function watchLevels() {
    if (levelWatchTimer === null) {
      /* The timer is not a duplicate of the frame loop: a background tab and
         headless Chrome do not run `requestAnimationFrame` at all, and the
         measurement of this fix was 131px of drift with the frame loop already
         in place. 80ms is the same fallback interval the chart handover uses
         (2026-09-18). Both paths go through `syncLevels`, which paints only
         when the mapping moved, so they cannot paint twice for one change. */
      levelWatchTimer = setInterval(syncLevels, 80);
    }
    if (levelWatch !== null || typeof requestAnimationFrame !== 'function') return;
    const tick = () => {
      if (!levelOverlay || !levels.side) { levelWatch = null; return; }
      syncLevels();
      levelWatch = requestAnimationFrame(tick);
    };
    levelWatch = requestAnimationFrame(tick);
  }

  function stopWatchingLevels() {
    if (levelWatch !== null && typeof cancelAnimationFrame === 'function') {
      cancelAnimationFrame(levelWatch);
    }
    clearInterval(levelWatchTimer);
    levelWatch = null;
    levelWatchTimer = null;
    watchedMapping = '';
  }

  function paintLevels() {
    if (!levelOverlay || !mainChart) return;
    const { host, canvas, chip, label, close } = levelOverlay;
    const box = host.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    const w = Math.round(box.width);
    const h = Math.round(box.height);
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
    }
    const ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    lastZones = null;

    const entryY = levels.side && mode !== 'overview' ? levelY(levels.entry) : null;
    if (entryY === null) {
      chip.hidden = true;
      return;
    }
    const plotWidth = mainChart.timeScale().width();
    const x0 = Math.min(Math.max(entryX(), 0), plotWidth);
    const alpha = levelDrag ? ZONE_ALPHA.dragging : ZONE_ALPHA.rest;
    const zones = { plotWidth };
    for (const [key, rgb] of [['target', '8, 153, 129'], ['stop', '242, 54, 69']]) {
      const y = levelY(levels[key]);
      if (y === null) continue;
      const top = Math.min(y, entryY);
      const height = Math.abs(y - entryY);
      ctx.fillStyle = `rgba(${rgb}, ${alpha})`;
      ctx.fillRect(x0, top, plotWidth - x0, height);
      zones[key] = { x: x0, y: top, width: plotWidth - x0, height, alpha };
    }

    label.textContent = levelTitle('entry', latestClose());
    const name = L('Đóng vị thế', 'Close position');
    close.title = name;
    close.setAttribute('aria-label', name);
    /* Against the price axis, at the right edge of the plot (Nam, 2026-09-16).
       It used to sit beside the entry bar, which put it straight over the
       candles between the entry and now — the part of the chart being read.
       The trade-off is the other way round: the right edge is where the newest
       bars are, so the chip can cover the last few. It is the lesser cost,
       because the library keeps blank space past the last bar and the newest
       price is also on the axis right behind it. */
    chip.hidden = entryY < 0 || entryY > h;
    const chipWidth = chip.offsetWidth;
    const left = Math.max(8, plotWidth - chipWidth - 8);
    chip.style.left = `${left}px`;
    chip.style.top = `${entryY}px`;
    zones.chip = { text: label.textContent, top: entryY, left, width: chipWidth, hidden: chip.hidden };
    lastZones = zones;
    watchedMapping = mappingSignature();
  }

  function bindLevelDragging(container) {
    buildLevelOverlay(container);
    // Dragging or scrolling the price axis happens inside this element but
    // outside the plot, so these two are the overlay's only events for it.
    container.addEventListener('wheel', syncLevels, { passive: true });
    container.addEventListener('pointerup', syncLevels);
    container.addEventListener('pointermove', (event) => {
      const y = offsetY(event);
      if (!levelDrag) {
        syncLevels();
        // The cursor is the only affordance these lines have, so it has to be
        // right: no grab handle, no tooltip, just the shape of the pointer.
        container.style.cursor = !event.target.closest?.('.position-chip') && levelAt(y) ? 'ns-resize' : '';
        return;
      }
      const raw = candleSeries.coordinateToPrice(y);
      if (!Number.isFinite(raw)) return;
      const price = snapPrice(raw);
      const entryY = levelY(levels.entry);
      const onEntry = entryY !== null && Math.abs(entryY - y) <= DRAG_GRAB_PX;
      const drag = levelDrag;

      if (drag.from === 'entry') {
        const key = exitFor(price);
        const other = key === 'stop' ? 'target' : 'stop';
        if (levels[other] !== drag.original[other]) placeLevel(other, drag.original[other]);
        if (onEntry) {
          // Still on the line: nothing is being set yet.
          if (drag.key) placeLevel(drag.key, drag.original[drag.key]);
          drag.key = null;
          return;
        }
        drag.key = key;
        placeLevel(key, price);
        return;
      }

      drag.remove = onEntry;
      placeLevel(drag.key, price, onEntry ? `${LEVEL_STYLE[drag.key].title} ✕` : null);
    });

    container.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      // The chip sits on the entry line; a press on it is a click, not a pull.
      if (event.target.closest?.('.position-chip')) return;
      const from = levelAt(offsetY(event));
      if (!from) return;
      levelDrag = {
        from, key: from === 'entry' ? null : from, remove: false,
        original: { stop: levels.stop, target: levels.target },
      };
      paintLevels();
      // Capture can be refused (a pen lifted mid-gesture); the drag still works.
      try { container.setPointerCapture(event.pointerId); } catch { /* not capturable */ }
      event.preventDefault();
      event.stopPropagation();
    }, true);

    const finish = (event) => {
      if (!levelDrag) return;
      const drag = levelDrag;
      levelDrag = null;
      try { container.releasePointerCapture(event.pointerId); } catch { /* already */ }
      container.style.cursor = '';
      paintLevels();

      const key = drag.key;
      const price = key && !drag.remove ? levels[key] : null;
      if (key && event.type !== 'pointercancel' && price !== drag.original[key]) {
        // The line stays where it was dropped; the caller redraws from the
        // server's answer, or puts it back if the amendment is refused.
        if (drag.remove) placeLevel(key, null);
        deferredLevels = null;
        onLevelDragged?.(key, price);
        return;
      }
      // Nothing to send: both exits go back exactly as they were.
      placeLevel('stop', drag.original.stop);
      placeLevel('target', drag.original.target);
      if (deferredLevels) {
        const spec = deferredLevels;
        deferredLevels = null;
        if (spec.side) setPositionLines(spec); else clearPositionLines();
      }
    };
    container.addEventListener('pointerup', finish);
    container.addEventListener('pointercancel', finish);
  }

  function offsetY(event) {
    const rect = event.currentTarget.getBoundingClientRect();
    return event.clientY - rect.top;
  }

  function clearTradeMarkers() {
    storedMarkers = [];
    applyMarkers();
    onMarkersChanged(0, markersVisible);
  }

  /** Show or hide without discarding. Returns the new visibility. */
  function setMarkersVisible(visible) {
    markersVisible = Boolean(visible);
    applyMarkers();
    onMarkersChanged(markerCount(), markersVisible);
    return markersVisible;
  }

  const toggleMarkers = () => setMarkersVisible(!markersVisible);

  /* Entries only. Every trade contributes an entry and an exit marker, and
     "37 markers" for 18 trades and one open position reads as a bug. */
  const markerCount = () =>
    storedMarkers.filter((m) => m.shape !== 'circle').length;

  let onMarkersChanged = () => {};


  /* Hold an indicator series level with the price chart, out to `time`.

     Missing bars are added as whitespace: nothing is drawn, because an
     indicator has no reading for a bar that is still forming and inventing one
     would be worse than a gap.

     It has to go through `setData`, not `update`. In Lightweight Charts 4.2.3
     a whitespace point passed to `update()` is silently discarded — the series
     keeps its old extent — while the same point inside a `setData` array does
     reserve an index slot. That asymmetry is not in the documentation and is
     the reason the first attempt at this fix changed nothing.

     `setData` is O(n), so this runs only when the newest bar actually advances,
     not on every tick of a forming candle. The points array is kept alongside
     each series precisely so that check is a comparison rather than a query. */
  function reserveSlot(entry, time) {
    if (time === null || time === undefined) return;
    const { series, points } = entry;
    if (points.length && points[points.length - 1].time >= time) return;

    points.push({ time });
    series.setData(points);
  }

  /* Live updates. Lightweight Charts replaces the last bar when update() is
     called with its timestamp and appends when the timestamp is newer, so the
     same call handles both a forming candle and the birth of a new one.

     Every indicator series is extended alongside the candles. Without that,
     the price chart grows with each new bar while the panes stay at whatever
     length the last recompute produced — and because the panes are separate
     charts kept in step by logical *index*, a price series k bars longer puts
     each pane's last point k slots to the left. Indicators are only recomputed
     when a candle closes, and a slow one (an ML plugin refitting over
     thousands of bars) or a failing one leaves that gap open indefinitely:
     what looks like a chart that occasionally drifts is really a chart that is
     always at least one bar out, and sometimes thirty. */
  function updateCandle(candle, key = null) {
    if (!candleSeries) return;

    // A candle for a series the chart is not showing is not this chart's
    // candle, whatever the socket thinks.
    if (key !== null && seriesKey !== null && key !== seriesKey) return;

    const time = toChart(candle.time);

    /* An older bar is dropped rather than applied.

       `series.update()` throws on a time before the newest point it holds, and
       that exception escapes the socket handler and kills the live feed for
       the rest of the session. Two markets with different clocks make this
       ordinary rather than exotic: the newest VN daily bar is hours behind the
       newest Bitcoin minute bar. */
    if (lastBarTime !== null && time < lastBarTime) return;

    // The overview line tracks the same forming bar, so switching modes mid
    // session never shows a line that stops short of the candles.
    overviewSeries?.update({ time, value: candle.close });

    /* Shaped by the type, not assumed to be a candle. A line series rejects
       an OHLC point outright, so sending one to every type would make the
       chart stop updating the moment anyone chose Line. */
    updatePricePoint(
      { time, open: candle.open, high: candle.high, low: candle.low, close: candle.close },
      candleData,
      priceType,
    );
    /* Keep the bars array in step with the rendered series, as volumeData
       below already is. Without it every reader of `candleData` was one live
       candle behind: measured, the position chip showed the previous price's
       P&L (tests/test_level_drag.html), and `lastClose` read the same stale
       bar. Stored after the update, because Heikin Ashi builds the current bar
       from the previous ones held here. */
    const bar = { time, open: candle.open, high: candle.high, low: candle.low, close: candle.close };
    const lastStored = candleData[candleData.length - 1];
    if (lastStored?.time === time) candleData[candleData.length - 1] = bar;
    else if (!lastStored || time > lastStored.time) candleData.push(bar);
    const volumePoint = {
      time,
      value: candle.volume,
      color: candle.close >= candle.open ? 'rgba(18,128,92,0.28)' : 'rgba(200,55,45,0.28)',
    };
    // Keep the backing array in step with the rendered series. History paging
    // calls setData from this array; otherwise it erases every live volume bar.
    const previousVolume = volumeData[volumeData.length - 1];
    if (previousVolume?.time === time) {
      volumeData[volumeData.length - 1] = volumePoint;
    } else {
      volumeData.push(volumePoint);
    }
    volumeSeries.update(volumePoint);
    refreshLevelTitles(candle.close);

    if (lastBarTime === null || time > lastBarTime) {
      lastBarTime = time;
      for (const seriesList of overlays.values()) {
        for (const entry of seriesList) reserveSlot(entry, time);
      }
      for (const pane of panes.values()) {
        for (const entry of pane.series) reserveSlot(entry, time);
      }
    }
  }

  /** Timestamp (epoch seconds) of the newest candle the chart holds. */
  function lastCandleTime() {
    if (!candleSeries) return null;
    const bar = candleSeries.dataByIndex(Number.MAX_SAFE_INTEGER, -1);
    return bar ? bar.time : null;
  }

  /** Remove this chart and everything it registered. */
  function destroy() {
    window.removeEventListener('resize', refreshSize);
    stopWatchingLevels();
    levelOverlay?.observer.disconnect();
    levelOverlay?.canvas.remove();
    levelOverlay?.chip.remove();
    levelOverlay = null;
    for (const id of [...panes.keys()]) removePane(id);
    for (const { observer } of sizers.values()) observer.disconnect();
    sizers.clear();
    try { mainChart?.remove(); } catch { /* already gone */ }
    mainChart = null;
    candleSeries = null;
  }

  /** A canvas of the price chart as drawn, for export. */
  function screenshot() {
    return mainChart ? mainChart.takeScreenshot() : null;
  }

  /* The invariant the sub-panes depend on: every series must span the same
     bars as the price chart.

     A pane is a separate chart kept in step by logical *index*, and a pane
     holding fewer bars cannot scroll as far right — the library clamps the
     range, and every bar on it slides right by the shortfall. Thirty bars
     short on a one-minute chart puts 12:50's reading underneath the 13:20
     candle, with nothing in the picture to say so. That has now caused two
     separate bugs, so it is worth being able to ask directly:

         ChartManager.alignment()      // { aligned: true, ... }

     Measured from the points arrays rather than from the library: whitespace
     holds an index slot but is not returned by `data()` or `dataByIndex()`, so
     asking the series would report a correctly aligned pane as empty. */
  function alignment() {
    const report = [];
    const check = (id, kind, entry) => report.push({
      id, kind, bars: entry.points.length,
      short: candleCount() - entry.points.length,
    });

    for (const [id, seriesList] of overlays) {
      for (const entry of seriesList) check(id, 'overlay', entry);
    }
    for (const [id, pane] of panes) {
      for (const entry of pane.series) check(id, 'pane', entry);
    }

    return {
      candles: candleCount(),
      series: report,
      aligned: report.every((r) => r.short === 0),
      offBy: report.filter((r) => r.short !== 0),
    };
  }

  /* Bars on the price chart. `data()` omits whitespace, but the candle series
     never holds any — every candle has values — so this is exact. */
  function candleCount() {
    return candleSeries ? candleSeries.data().length : 0;
  }

  /* Put an older page in front of what is already drawn.

     The visible range is captured and restored around the setData, because
     setData re-anchors the view and without this the chart would jump to the
     newly prepended start every time a page arrived — the pan would fight the
     user. Returns how many bars were actually added. */
  function prependCandles(candles, volumes, key = null) {
    if (!candleSeries || !candles?.length) return 0;

    /* Older bars for a different series are not this series' history.

       `setCandles` replaces everything, so a late response there is merely
       stale. This one *merges*, so a late response is corruption: a page of
       VN index bars around 1 900 prepended to a Bitcoin series around 79 000
       leaves one series holding both, the price scale spanning 0 to 100 000,
       and the window's opening price — taken from the first bar — belonging to
       the wrong instrument. That is what produced a +3 993% day. */
    if (key !== null && seriesKey !== null && key !== seriesKey) return 0;

    const known = new Set(candleData.map((c) => c.time));
    const older = candles
      .map((c) => ({
        time: toChart(c.time),
        open: c.open, high: c.high, low: c.low, close: c.close,
      }))
      .filter((c) => !known.has(c.time));
    if (!older.length) return 0;

    const knownVol = new Set(volumeData.map((v) => v.time));
    const olderVol = (volumes || [])
      .map((v) => ({
        time: toChart(v.time),
        value: v.value,
        color: v.up ? 'rgba(18,128,92,0.28)' : 'rgba(200,55,45,0.28)',
      }))
      .filter((v) => !knownVol.has(v.time));

    const scale = mainChart.timeScale();
    const before = scale.getVisibleLogicalRange();

    candleData = [...older, ...candleData];
    volumeData = [...olderVol, ...volumeData];
    applyPriceData(candleData);
    volumeSeries.setData(volumeData);
    overviewSeries?.setData(candleData.map((c) => ({ time: c.time, value: c.close })));

    // Everything shifted right by exactly the number of bars added.
    if (before) {
      scale.setVisibleLogicalRange({
        from: before.from + older.length,
        to: before.to + older.length,
      });
    }
    return older.length;
  }

  /* The bar covering a chart time, for the magnet. Nearest rather than exact:
     `coordinateToTime` returns a time on the scale, which between two bars is
     not any bar's own timestamp. */
  function barAt(time) {
    if (!candleData.length) return null;
    let best = null;
    let bestGap = Infinity;
    for (const bar of candleData) {
      const gap = Math.abs(bar.time - time);
      if (gap < bestGap) { bestGap = gap; best = bar; }
    }
    return best;
  }

  /** How many bars lie between two chart times, for the ruler. */
  function barsBetween(from, to) {
    if (!candleData.length) return null;
    const index = (t) => {
      let best = 0;
      let bestGap = Infinity;
      for (let i = 0; i < candleData.length; i += 1) {
        const gap = Math.abs(candleData[i].time - t);
        if (gap < bestGap) { bestGap = gap; best = i; }
      }
      return best;
    };
    return Math.abs(index(to) - index(from));
  }

  return { init, setCandles, setMode, prependCandles, focusRecent, fitAll,
           setPriceType, barAt, barsBetween,
           get seriesKey() { return seriesKey; },
           // The close of the oldest bar the chart is holding. The header's
           // percentage measures against this, so that it can never disagree
           // with the candles beside it.
           get firstClose() {
             return candleData.length ? candleData[0].close : null;
           },
           get chart() { return mainChart; },
           get priceSeries() { return candleSeries; },
           get volumeSeries() { return volumeSeries; },
           get priceType() { return priceType; },
           set onNeedHistory(fn) { onNeedHistory = fn || null; },
           get oldestTime() { return candleData.length ? candleData[0].time : null; },
           draw, drawOverlay, drawPane, remove, clearAll, alignment,
           get mode() { return mode; },
           setTradeMarkers, clearTradeMarkers, setMarkersVisible, toggleMarkers,
           setPositionLines, clearPositionLines,
           set onPositionClose(fn) { onPositionClose = fn || null; },
           // For probes: the bands and the chip as last painted.
           get levelZones() { return lastZones; },
           // For probes: the options of the entry, stop and target lines as drawn.
           get levelLines() {
             return Object.fromEntries(Object.entries(positionLines)
               .map(([key, line]) => [key, line ? line.options() : null]));
           },
           set onLevelDragged(fn) { onLevelDragged = fn || null; },
           get markerCount() { return markerCount(); },
           get markersVisible() { return markersVisible; },
           set onMarkersChanged(fn) { onMarkersChanged = fn || (() => {}); },
           updateCandle, lastCandleTime,
           screenshot, refreshSize, applyDisplay, diagnose, toChartTime: toChart,
           // Readable so a probe can check the grid setting reached the chart.
           get gridVisible() { return !!mainChart?.options().grid.vertLines.visible; },
           get timezoneLabel() { return Settings.timezoneLabel(); },
           destroy,
           get timeScale() { return mainChart ? mainChart.timeScale() : null; },
           get barCount() { return candleData.length; },
           get lastClose() { return candleData.length ? candleData[candleData.length - 1].close : null; },
           set onSeriesChanged(fn) { onSeriesChanged = fn || null; } };
}

/* The charts, and which one is being worked on.

   `ChartManager` is a stand-in for the active chart rather than a chart of its
   own: every `ChartManager.setCandles(...)`, `.draw(...)`, `.seriesKey` in the
   app reaches whichever cell is active at the moment of the call. The first
   chart exists from the start, so the stand-in is never empty. */
const ChartHub = (() => {
  let active = createChartManager();
  return {
    create: () => createChartManager(),
    get active() { return active; },
    setActive(manager) { if (manager) active = manager; },
  };
})();

const ChartManager = new Proxy({}, {
  get: (_, prop) => ChartHub.active[prop],
  set: (_, prop, value) => { ChartHub.active[prop] = value; return true; },
});

/* The equity curve, drawn in the results panel. Its own small chart rather
   than a pane of the price chart: equity is denominated in account currency
   and spans a different range, and it should stay readable while the price
   chart is scrolled or zoomed independently. */

const EquityChart = (() => {
  let chart = null;
  let series = null;
  let baseline = null;

  function ensure(container) {
    if (chart) return;

    chart = LightweightCharts.createChart(container, {
      layout: {
        background: { color: '#ffffff' },
        textColor: '#9a9aa2',
        fontSize: 10,
        fontFamily: CHART_FONT,
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { visible: false },
      },
      rightPriceScale: { borderColor: '#e2e5ea' },
      timeScale: { borderColor: '#e2e5ea', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });

    series = chart.addAreaSeries({
      lineColor: '#3264e8',
      topColor: 'rgba(50,100,232,0.18)',
      bottomColor: 'rgba(50,100,232,0.01)',
      lineWidth: 2,
      priceLineVisible: false,
    });

    // Own the sizing here too: the results panel is hidden most of the time,
    // which is exactly the case that leaves autoSize stuck at zero.
    const fit = () => {
      const { width, height } = container.getBoundingClientRect();
      if (width > 0 && height > 0) chart.resize(width, height);
    };
    fit();
    new ResizeObserver(fit).observe(container);

    // Starting capital, so being under water is visible at a glance.
    baseline = chart.addLineSeries({
      color: '#c3c9d1',
      lineWidth: 1,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
      crosshairMarkerVisible: false,
    });
  }

  function render(container, times, equity, initialCapital) {
    ensure(container);

    const points = [];
    const flat = [];
    let previousTime = null;

    for (let i = 0; i < times.length; i += 1) {
      // Lightweight Charts rejects duplicate or out-of-order timestamps.
      if (previousTime !== null && times[i] <= previousTime) continue;
      previousTime = times[i];
      // Same display offset as the price chart, so the two line up.
      points.push({ time: ChartManager.toChartTime(times[i]), value: equity[i] });
      flat.push({ time: ChartManager.toChartTime(times[i]), value: initialCapital });
    }

    series.setData(points);
    baseline.setData(flat);
    chart.timeScale().fitContent();
  }

  function clear() {
    if (series) series.setData([]);
    if (baseline) baseline.setData([]);
  }

  return { render, clear };
})();
