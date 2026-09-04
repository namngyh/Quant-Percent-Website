/* Chart management: the main candle chart plus one synchronized pane per
   panel-type indicator.

   Lightweight Charts v4 has no native multi-pane support, so each panel
   indicator gets its own chart instance and the instances are kept in lockstep
   by mirroring the time scale and crosshair between them. */

const ChartManager = (() => {
  const THEME = {
    layout: {
      background: { color: '#0d1117' },
      textColor: '#8b949e',
      fontSize: 11,
      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
    },
    grid: {
      vertLines: { color: '#161b22' },
      horzLines: { color: '#161b22' },
    },
    rightPriceScale: { borderColor: '#21262d' },
    timeScale: { borderColor: '#21262d' },
    crosshair: {
      mode: 0, // free-moving crosshair
      vertLine: { color: '#3d444d', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
      horzLine: { color: '#3d444d', width: 1, style: 3, labelBackgroundColor: '#2962ff' },
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

  function init(container) {
    mainChart = LightweightCharts.createChart(container, {
      ...THEME,
      autoSize: true,
    });

    candleSeries = mainChart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      borderUpColor: '#26a69a',
      borderDownColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
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

    syncFrom(mainChart);
    return mainChart;
  }

  function setCandles(candles, volumes, { timeVisible }) {
    for (const chart of allCharts()) {
      chart.applyOptions({ timeScale: { ...THEME.timeScale, timeVisible, secondsVisible: false } });
    }
    candleSeries.setData(candles);
    volumeSeries.setData(
      volumes.map((v) => ({
        time: v.time,
        value: v.value,
        color: v.up ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
      })),
    );
    mainChart.timeScale().fitContent();
  }

  /** Convert {times, values[key]} into the {time, value} pairs the chart wants. */
  function toPoints(times, values) {
    const points = [];
    for (let i = 0; i < times.length; i += 1) {
      const value = values[i];
      if (value === null || value === undefined) continue; // gap: skip, don't zero
      points.push({ time: times[i], value });
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
      autoSize: true,
      timeScale: { ...THEME.timeScale, visible: false },
    });

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


  /* Entry and exit markers for a backtest, drawn on the candles. */
  function setTradeMarkers(trades) {
    const markers = [];
    for (const t of trades) {
      const isLong = t.side === 'long';
      markers.push({
        time: t.entry_time,
        position: isLong ? 'belowBar' : 'aboveBar',
        color: isLong ? '#26a69a' : '#ef5350',
        shape: isLong ? 'arrowUp' : 'arrowDown',
        text: isLong ? 'L' : 'S',
      });
      markers.push({
        time: t.exit_time,
        position: isLong ? 'aboveBar' : 'belowBar',
        color: t.exit_reason === 'liquidation' ? '#f85149' : '#6e7681',
        shape: 'circle',
        text: t.exit_reason === 'liquidation' ? 'LIQ' : '',
      });
    }
    // Markers must be sorted by time or the library drops them silently.
    markers.sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(markers);
  }

  function clearTradeMarkers() {
    if (candleSeries) candleSeries.setMarkers([]);
  }

  return { init, setCandles, drawOverlay, drawPane, remove, clearAll, setTradeMarkers, clearTradeMarkers };
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
        background: { color: '#0a0e14' },
        textColor: '#6e7681',
        fontSize: 10,
        fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      },
      grid: {
        vertLines: { color: 'rgba(33,38,45,0.5)' },
        horzLines: { color: 'rgba(33,38,45,0.5)' },
      },
      rightPriceScale: { borderColor: '#21262d' },
      timeScale: { borderColor: '#21262d', timeVisible: true, secondsVisible: false },
      crosshair: { mode: 0 },
      autoSize: true,
    });

    series = chart.addAreaSeries({
      lineColor: '#2962ff',
      topColor: 'rgba(41,98,255,0.28)',
      bottomColor: 'rgba(41,98,255,0.02)',
      lineWidth: 2,
      priceLineVisible: false,
    });

    // Starting capital, so being under water is visible at a glance.
    baseline = chart.addLineSeries({
      color: '#3d444d',
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
      points.push({ time: times[i], value: equity[i] });
      flat.push({ time: times[i], value: initialCapital });
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
