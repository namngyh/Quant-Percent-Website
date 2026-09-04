/* Application wiring: loads config, candles, indicators and strategies, then
   keeps the charts in step with the controls. */

(() => {
  const el = {
    symbol: document.getElementById('symbol'),
    timeframes: document.getElementById('timeframes'),
    limit: document.getElementById('limit'),
    backfill: document.getElementById('backfill'),
    status: document.getElementById('status'),
    loading: document.getElementById('loading'),
    chartMain: document.getElementById('chart-main'),
    panes: document.getElementById('panes'),
    results: document.getElementById('results'),
    closeResults: document.getElementById('close-results'),
    runBacktest: document.getElementById('run-backtest'),
    runOptimize: document.getElementById('run-optimize'),
    liveToggle: document.getElementById('live-toggle'),
    liveDot: document.getElementById('live-dot'),
    liveLabel: document.getElementById('live-label'),
  };

  const state = {
    symbol: null,
    timeframe: null,
    limit: 2000,
  };

  // Timeframes at or below this show a time (not just a date) on the axis.
  const INTRADAY = new Set(['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h']);

  function setStatus(message, kind = '') {
    el.status.textContent = message;
    el.status.className = `status ${kind}`;
  }

  function setLoading(on) {
    el.loading.hidden = !on;
  }

  // ---------- Data loading ----------

  async function loadCandles() {
    setLoading(true);
    try {
      const data = await API.candles({
        symbol: state.symbol,
        timeframe: state.timeframe,
        limit: state.limit,
      });

      if (!data.count) {
        // Drop the drawings too, or lines computed from the previous timeframe
        // would linger over an empty chart. The active list is left intact, so
        // they redraw as soon as this series has data.
        ChartManager.clearAll();
        ChartManager.clearTradeMarkers();
        ChartManager.setCandles([], [], { timeVisible: false });
        setStatus(`${state.symbol} ${state.timeframe} — chưa có dữ liệu, bấm "Cập nhật dữ liệu"`, 'error');
        return;
      }

      ChartManager.setCandles(data.candles, data.volumes, {
        timeVisible: INTRADAY.has(state.timeframe),
      });

      const last = data.candles[data.candles.length - 1];
      setStatus(
        `${state.symbol} ${state.timeframe} · ${data.count.toLocaleString('vi-VN')} nến · ` +
          `${last.close.toLocaleString('en-US', { maximumFractionDigits: 2 })}`,
      );

      // Anything drawn from the previous series is stale now.
      ChartManager.clearTradeMarkers();
      await Indicators.recomputeAll();

      // Point the live feed at whatever we are now looking at.
      Live.subscribe(state.symbol, state.timeframe);
    } catch (err) {
      setStatus(err.message, 'error');
    } finally {
      setLoading(false);
    }
  }

  async function computeIndicator(instanceId, instance) {
    const result = await API.compute({
      indicatorId: instance.spec.id,
      symbol: state.symbol,
      timeframe: state.timeframe,
      params: instance.params,
      limit: state.limit,
    });

    // The backend tags each output with the pane it belongs in, so one call
    // handles pure overlays, pure panels, and the mixed case.
    ChartManager.draw(instanceId, result, el.panes);
  }


  // ---------- Live ----------

  let recomputeTimer = null;

  // Named `liveState`, not `state`: destructuring it as `state` would shadow
  // the module-level state object and make a later edit here quietly wrong.
  function setLiveState({ state: liveState }) {
    const dot = { live: 'live', connecting: 'connecting', offline: 'offline' }[liveState] || '';
    el.liveDot.className = `live-dot ${dot}`;
    el.liveToggle.classList.toggle('on', liveState === 'live' || liveState === 'connecting');
    el.liveLabel.textContent = {
      live: 'Đang chạy',
      connecting: 'Đang nối…',
      offline: 'Mất kết nối',
      error: 'Lỗi',
    }[liveState] || 'Realtime';
  }

  function onLiveCandle(candle) {
    ChartManager.updateCandle({
      time: Math.floor(candle.open_time / 1000),
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
      volume: candle.volume,
    });

    const price = candle.close.toLocaleString('en-US', { maximumFractionDigits: 2 });
    setStatus(`${state.symbol} ${state.timeframe} · live · ${price}`);
  }

  function onLiveCandleClose() {
    // Indicators only mean anything on settled candles, so they are recomputed
    // when one closes rather than on every tick. The debounce covers the case
    // where several closes land together after a reconnect.
    clearTimeout(recomputeTimer);
    recomputeTimer = setTimeout(() => Indicators.recomputeAll(), 500);
  }

  function toast(message) {
    const node = document.createElement('div');
    node.className = 'toast';
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), 3200);
  }

  async function onPluginsChanged(kind) {
    try {
      if (kind === 'strategies') {
        await Strategy.load();
        toast('Đã nạp lại chiến lược từ file');
      } else {
        Indicators.setCatalog(await API.catalog());
        await Indicators.recomputeAll();
        toast('Đã nạp lại chỉ báo từ file');
      }
    } catch (err) {
      setStatus(err.message, 'error');
    }
  }

  // ---------- Controls ----------

  function buildTimeframeButtons(timeframes) {
    el.timeframes.innerHTML = '';
    for (const tf of timeframes) {
      const button = document.createElement('button');
      button.className = `tf-btn${tf === state.timeframe ? ' active' : ''}`;
      button.textContent = tf;
      button.addEventListener('click', () => {
        if (state.timeframe === tf) return;
        state.timeframe = tf;
        for (const b of el.timeframes.children) b.classList.toggle('active', b === button);
        loadCandles();
      });
      el.timeframes.appendChild(button);
    }
  }

  async function runBackfill() {
    el.backfill.disabled = true;
    setStatus('Đang tải dữ liệu từ Binance…', 'busy');
    setLoading(true);
    try {
      const report = await API.backfill({
        symbols: [state.symbol],
        timeframes: [state.timeframe],
      });
      const failed = report.series.filter((s) => s.error);
      if (failed.length) {
        setStatus(`Lỗi: ${failed[0].error}`, 'error');
      } else {
        setStatus(`Đã thêm ${report.total_rows.toLocaleString('vi-VN')} nến`);
      }
      await loadCandles();
    } catch (err) {
      setStatus(err.message, 'error');
    } finally {
      el.backfill.disabled = false;
      setLoading(false);
    }
  }

  function setupTabs() {
    for (const tab of document.querySelectorAll('.tab')) {
      tab.addEventListener('click', () => {
        for (const t of document.querySelectorAll('.tab')) {
          t.classList.toggle('active', t === tab);
        }
        for (const panel of document.querySelectorAll('.tab-panel')) {
          panel.classList.toggle('active', panel.dataset.panel === tab.dataset.tab);
        }
      });
    }

    for (const rtab of document.querySelectorAll('.rtab')) {
      rtab.addEventListener('click', () => {
        for (const t of document.querySelectorAll('.rtab')) {
          t.classList.toggle('active', t === rtab);
        }
        for (const panel of document.querySelectorAll('.rpanel')) {
          panel.classList.toggle('active', panel.dataset.rpanel === rtab.dataset.rtab);
        }
      });
    }
  }

  function showResults(tab) {
    el.results.hidden = false;
    if (!tab) return;
    for (const t of document.querySelectorAll('.rtab')) {
      t.classList.toggle('active', t.dataset.rtab === tab);
    }
    for (const panel of document.querySelectorAll('.rpanel')) {
      panel.classList.toggle('active', panel.dataset.rpanel === tab);
    }
  }

  async function withButton(button, label, work) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = label;
    setLoading(true);
    try {
      await work();
    } catch (err) {
      setStatus(err.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = original;
      setLoading(false);
    }
  }

  // ---------- Boot ----------

  async function start() {
    ChartManager.init(el.chartMain);
    setupTabs();

    Indicators.init({
      elements: {
        catalog: document.getElementById('catalog'),
        active: document.getElementById('active'),
        search: document.getElementById('search'),
        count: document.getElementById('catalog-count'),
        pluginErrors: document.getElementById('plugin-errors'),
        clearAll: document.getElementById('clear-all'),
      },
      onCompute: computeIndicator,
      onRemove: (instanceId) => ChartManager.remove(instanceId),
    });

    Strategy.init({
      elements: {
        select: document.getElementById('strategy-select'),
        desc: document.getElementById('strategy-desc'),
        count: document.getElementById('strategy-count'),
        errors: document.getElementById('strategy-errors'),
        params: document.getElementById('strategy-params'),
        sweep: document.getElementById('sweep-ranges'),
        metric: document.getElementById('opt-metric'),
        mode: document.getElementById('opt-mode'),
        samples: document.getElementById('opt-samples'),
        samplesRow: document.getElementById('opt-samples-row'),
        sweepSize: document.getElementById('sweep-size'),
        metrics: document.getElementById('metrics'),
        trades: document.getElementById('trades'),
        optimize: document.getElementById('optimize-results'),
        equityChart: document.getElementById('equity-chart'),
        capital: document.getElementById('exec-capital'),
        size: document.getElementById('exec-size'),   // % of equity per trade
        leverage: document.getElementById('exec-leverage'),
        fee: document.getElementById('exec-fee'),
        slippage: document.getElementById('exec-slippage'),
      },
      context: () => ({ ...state }),
      onResult: (result) => ChartManager.setTradeMarkers(result.trades),
    });

    Live.init({
      onCandle: onLiveCandle,
      onCandleClose: onLiveCandleClose,
      onPluginsChanged,
      onStatus: setLiveState,
    });

    try {
      const config = await API.config();

      state.symbol = config.default_symbol;
      state.timeframe = config.default_timeframe;
      state.limit = Number(el.limit.value);

      el.symbol.innerHTML = config.symbols
        .map((s) => `<option value="${s}">${s}</option>`)
        .join('');
      el.symbol.value = state.symbol;
      buildTimeframeButtons(config.timeframes);

      Indicators.setCatalog(await API.catalog());
      await Strategy.load();
    } catch (err) {
      setStatus(`Không kết nối được backend: ${err.message}`, 'error');
      return;
    }

    el.symbol.addEventListener('change', () => {
      state.symbol = el.symbol.value;
      loadCandles();
    });
    el.limit.addEventListener('change', () => {
      state.limit = Number(el.limit.value);
      loadCandles();
    });
    el.backfill.addEventListener('click', runBackfill);
    el.liveToggle.addEventListener('click', () => {
      const turningOn = !Live.enabled;
      Live.setEnabled(turningOn);
      if (turningOn) Live.subscribe(state.symbol, state.timeframe);
    });
    el.closeResults.addEventListener('click', () => {
      el.results.hidden = true;
      ChartManager.clearTradeMarkers();
    });

    el.runBacktest.addEventListener('click', () =>
      withButton(el.runBacktest, 'Đang chạy…', async () => {
        showResults('summary');
        await Strategy.runBacktest();
      }),
    );

    el.runOptimize.addEventListener('click', () =>
      withButton(el.runOptimize, 'Đang quét…', async () => {
        showResults('optimize');
        await Strategy.runOptimize();
      }),
    );

    await loadCandles();
  }

  start();
})();
