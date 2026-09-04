/* Chart management: the main candle chart plus one synchronized pane per
   panel-type indicator.

   Lightweight Charts v4 has no native multi-pane support, so each panel
   indicator gets its own chart instance and the instances are kept in lockstep
   by mirroring the time scale and crosshair between them. */

const ChartManager = (() => {
  /* Lightweight Charts renders its axis in UTC and v4 has no timezone option,
     so every timestamp is shifted by the display offset on the way in. Vietnam
     is UTC+7 all year — no daylight saving — so a fixed offset is exact, and a
     timezone library would buy nothing.

     Everything stored, compared and sent by the backend stays UTC; this offset
     exists only so the axis reads in the time the market actually traded. */
  const TZ_OFFSET_SECONDS = 7 * 3600;
  const TZ_LABEL = 'GMT+7';

  const toChart = (epochSeconds) => epochSeconds + TZ_OFFSET_SECONDS;

  const THEME = {
    layout: {
      background: { color: '#ffffff' },
      textColor: '#5b646e',
      fontSize: 11,
      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
    },
    grid: {
      vertLines: { color: '#f0f2f5' },
      horzLines: { color: '#f0f2f5' },
    },
    rightPriceScale: { borderColor: '#e2e5ea' },
    timeScale: { borderColor: '#e2e5ea' },
    crosshair: {
      mode: 0, // free-moving crosshair
      vertLine: { color: '#a8b0ba', width: 1, style: 3, labelBackgroundColor: '#16191d' },
      horzLine: { color: '#a8b0ba', width: 1, style: 3, labelBackgroundColor: '#16191d' },
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
     That option collapses the chart when its container is briefly 0 wide — a
     hidden panel, a minimised window — and does not always recover when the
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
     rendering lifecycle, so a page that is not painting — a background tab, a
     hidden pane — never receives it and the chart stays at whatever size it
     last saw. Calling this after anything that changes the layout covers that
     without waiting for a frame. */
  function refreshSize() {
    for (const [chart, entry] of sizers) {
      const { width, height } = entry.container.getBoundingClientRect();
      if (width > 0 && height > 0) chart.resize(width, height);
    }
  }

  function init(container) {
    mainChart = LightweightCharts.createChart(container, { ...THEME });
    trackSize(mainChart, container);

    candleSeries = mainChart.addCandlestickSeries({
      upColor: '#12805c',
      downColor: '#c8372d',
      borderUpColor: '#12805c',
      borderDownColor: '#c8372d',
      wickUpColor: '#12805c',
      wickDownColor: '#c8372d',
    });

    volumeSeries = mainChart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '', // overlay scale, independent of the price axis
      lastValueVisible: false,
      priceLineVisible: false,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.86, bottom: 0 },
    });

    // A window resize always reaches us, even when the observer does not.
    window.addEventListener('resize', refreshSize);

    syncFrom(mainChart);
    return mainChart;
  }

  function setCandles(candles, volumes, { timeVisible }) {
    for (const chart of allCharts()) {
      chart.applyOptions({ timeScale: { ...THEME.timeScale, timeVisible, secondsVisible: false } });
    }
    candleSeries.setData(
      candles.map((c) => ({
        time: toChart(c.time),
        open: c.open, high: c.high, low: c.low, close: c.close,
      })),
    );
    volumeSeries.setData(
      volumes.map((v) => ({
        time: toChart(v.time),
        value: v.value,
        color: v.up ? 'rgba(18,128,92,0.28)' : 'rgba(200,55,45,0.28)',
      })),
    );
    mainChart.timeScale().fitContent();
  }

  /** Convert {times, values[key]} into the points the chart wants.

     A missing value becomes a *whitespace* point — `{time}` with no value —
     rather than being dropped. The library reserves the slot and breaks the
     line there, which looks the same, but the series keeps one entry per
     candle.

     That matters because the sub-panes are separate charts kept in step by
     logical (index) range. Dropping the warm-up values left an indicator with
     1 445 points against 2 000 candles, so index 500 in the pane was a
     different bar from index 500 on the price chart and the panes drifted out
     of line — each ending short of the newest candle by a different amount. */
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

    for (const output of result.outputs) {
      const series = mainChart.addLineSeries({
        color: output.color,
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: true,
      });
      series.setData(toPoints(result.times, result.values[output.key] || []));
      seriesList.push(series);
    }

    overlays.set(instanceId, seriesList);
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
    for (const series of seriesList) mainChart.removeSeries(series);
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

    for (const output of result.outputs) {
      const isHistogram = output.plot_type === 'histogram';
      const series = isHistogram
        ? chart.addHistogramSeries({ color: output.color, priceLineVisible: false })
        : chart.addLineSeries({
            color: output.color,
            lineWidth: 2,
            priceLineVisible: false,
            lastValueVisible: true,
          });
      series.setData(toPoints(result.times, result.values[output.key] || []));
    }

    panes.set(instanceId, { chart, element });

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
    candleSeries.setMarkers(markers);
  }

  function clearTradeMarkers() {
    if (candleSeries) candleSeries.setMarkers([]);
  }


  /* Live updates. Lightweight Charts replaces the last bar when update() is
     called with its timestamp, and appends when the timestamp is newer — so
     the same call handles both a forming candle and the birth of a new one. */
  function updateCandle(candle) {
    if (!candleSeries) return;
    candleSeries.update({
      time: toChart(candle.time),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    });
    volumeSeries.update({
      time: toChart(candle.time),
      value: candle.volume,
      color: candle.close >= candle.open ? 'rgba(18,128,92,0.28)' : 'rgba(200,55,45,0.28)',
    });
  }

  /** Timestamp (epoch seconds) of the newest candle the chart holds. */
  function lastCandleTime() {
    if (!candleSeries) return null;
    const bar = candleSeries.dataByIndex(Number.MAX_SAFE_INTEGER, -1);
    return bar ? bar.time : null;
  }

  /** A canvas of the price chart as drawn, for export. */
  function screenshot() {
    return mainChart ? mainChart.takeScreenshot() : null;
  }

  return { init, setCandles, draw, drawOverlay, drawPane, remove, clearAll,
           setTradeMarkers, clearTradeMarkers, updateCandle, lastCandleTime,
           screenshot, refreshSize, timezoneLabel: TZ_LABEL, toChartTime: toChart };
})();

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
        textColor: '#949ca6',
        fontSize: 10,
        fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      },
      grid: {
        vertLines: { color: '#f4f6f8' },
        horzLines: { color: '#f4f6f8' },
      },
      rightPriceScale: { borderColor: '#e2e5ea' },
      timeScale: { borderColor: '#e2e5ea', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
    });

    series = chart.addAreaSeries({
      lineColor: '#16191d',
      topColor: 'rgba(22,25,29,0.14)',
      bottomColor: 'rgba(22,25,29,0.01)',
      lineWidth: 2,
      priceLineVisible: false,
    });

    // Own the sizing here too — the results panel is hidden most of the time,
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
