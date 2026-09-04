/* Application wiring.

   The rail opens exactly one panel at a time, and clicking the open one closes
   it — three columns of controls competing for attention was the thing that
   made this hard to read. */

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
    panelHost: document.getElementById('panel-host'),
    runBacktest: document.getElementById('run-backtest'),
    runOptimize: document.getElementById('run-optimize'),
    startPaper: document.getElementById('start-paper'),
    liveToggle: document.getElementById('live-toggle'),
    liveDot: document.getElementById('live-dot'),
    liveLabel: document.getElementById('live-label'),
    importFile: document.getElementById('import-file'),
  };

  const state = { symbol: null, timeframe: null, limit: 2000 };

  const INTRADAY = new Set(['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h']);

  function setStatus(message, kind = '') {
    el.status.textContent = message;
    el.status.className = `status ${kind}`;
  }

  const setLoading = (on) => { el.loading.hidden = !on; };

  function toast(message, bad = false) {
    const node = document.createElement('div');
    node.className = `toast${bad ? ' bad' : ''}`;
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), bad ? 5000 : 3200);
  }

  // ---------- Data ----------

  async function loadCandles() {
    setLoading(true);
    try {
      const data = await API.candles({
        symbol: state.symbol, timeframe: state.timeframe, limit: state.limit,
      });

      if (!data.count) {
        // Drop the drawings too, or lines from the previous timeframe linger
        // over an empty chart. The active list stays, so they redraw when data
        // for this series arrives.
        ChartManager.clearAll();
        ChartManager.clearTradeMarkers();
        ChartManager.setCandles([], [], { timeVisible: false });
        setStatus(`${state.symbol} ${state.timeframe} — chưa có dữ liệu`, 'error');
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

      ChartManager.clearTradeMarkers();
      await Indicators.recomputeAll();
      if (!isVN(state.symbol)) Live.subscribe(state.symbol, state.timeframe);
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
    // handles overlays, panels, and indicators that mix the two.
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
      live: 'Đang chạy', connecting: 'Đang nối…', offline: 'Mất kết nối', error: 'Lỗi',
    }[liveState] || 'Realtime';
  }

  function onLiveCandle(candle) {
    ChartManager.updateCandle({
      time: Math.floor(candle.open_time / 1000),
      open: candle.open, high: candle.high, low: candle.low,
      close: candle.close, volume: candle.volume,
    });
    const price = candle.close.toLocaleString('en-US', { maximumFractionDigits: 2 });
    setStatus(`${state.symbol} ${state.timeframe} · live · ${price}`);
  }

  function onLiveCandleClose() {
    // Indicators are recomputed when a candle settles, not on every tick: a
    // value on an unfinished bar is not a reading of anything.
    clearTimeout(recomputeTimer);
    recomputeTimer = setTimeout(() => Indicators.recomputeAll(), 500);
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


  // ---------- Markets ----------
  //
  // Two sources: Binance crypto in the local store, and the team's HOSE
  // database over the VPN. A `VN:` prefix on the symbol is what routes a
  // request, so the market a symbol belongs to is readable from the symbol.

  const markets = { crypto: null, vn: null };

  const isVN = (symbol) => String(symbol || '').startsWith('VN:');

  function timeframesFor(symbol) {
    if (isVN(symbol)) return markets.vn?.timeframes || ['1d'];
    return markets.crypto?.timeframes || ['1h'];
  }

  /** Symbols without minute bars can only be charted daily. */
  function symbolHasIntraday(symbol) {
    if (!isVN(symbol)) return true;
    const entry = markets.vn?.index?.get(symbol);
    return entry ? entry.has_intraday : true;
  }

  function allowedTimeframes(symbol) {
    const all = timeframesFor(symbol);
    return symbolHasIntraday(symbol) ? all : all.filter((tf) => tf === '1d');
  }

  async function loadSymbolOptions(config) {
    markets.crypto = config.markets?.find((m) => m.id === 'crypto') || {
      symbols: config.symbols, timeframes: config.timeframes,
    };

    const groups = [
      { label: 'Crypto · Binance', options: markets.crypto.symbols.map((s) => ({ id: s, text: s })) },
    ];

    // Best effort: the VN list lives behind the VPN, and the app must still
    // work on crypto when that is off.
    try {
      const vn = await API.vnSymbols();
      markets.vn = {
        timeframes: vn.timeframes,
        index: new Map(vn.symbols.map((s) => [s.id, s])),
      };

      const withMinutes = vn.symbols.filter((s) => s.has_intraday);
      const dailyOnly = vn.symbols.filter((s) => !s.has_intraday);
      const label = (s) => `${s.symbol}${s.name && s.name !== s.symbol ? ' · ' + s.name : ''}`;

      if (withMinutes.length) {
        groups.push({
          label: `Việt Nam · HOSE — có nến phút (${withMinutes.length})`,
          options: withMinutes.map((s) => ({ id: s.id, text: label(s) })),
        });
      }
      if (dailyOnly.length) {
        groups.push({
          label: `Việt Nam · HOSE — chỉ nến ngày (${dailyOnly.length})`,
          options: dailyOnly.map((s) => ({ id: s.id, text: label(s) })),
        });
      }
    } catch (err) {
      markets.vn = null;
      // Not fatal, and not silent either: say why the VN names are missing.
      setStatus(`Thị trường VN không khả dụng: ${err.message}`, 'error');
    }

    el.symbol.innerHTML = groups
      .map(
        (g) =>
          `<optgroup label="${g.label}">` +
          g.options.map((o) => `<option value="${o.id}">${o.text}</option>`).join('') +
          '</optgroup>',
      )
      .join('');
  }

  /** Live and backfill are Binance-only; say so rather than failing on click. */
  function applyMarketCapabilities() {
    const vn = isVN(state.symbol);

    el.backfill.disabled = vn;
    el.backfill.title = vn
      ? 'Dữ liệu VN đến từ database của team và chỉ đọc — không cần backfill.'
      : 'Kéo nến mới nhất từ Binance';

    el.liveToggle.disabled = vn;
    el.liveToggle.title = vn
      ? 'Thị trường VN chưa có luồng realtime; tải lại để thấy nến mới.'
      : 'Bật/tắt nến realtime';

    if (vn && Live.enabled) Live.setEnabled(false);
  }

  // ---------- Navigation ----------

  function openPanel(name) {
    const host = el.panelHost;
    const current = document.querySelector('.rail-btn.active')?.dataset.panel;

    if (current === name && !host.classList.contains('collapsed')) {
      host.classList.add('collapsed');      // clicking the open one closes it
      return;
    }

    host.classList.remove('collapsed');
    for (const btn of document.querySelectorAll('.rail-btn')) {
      btn.classList.toggle('active', btn.dataset.panel === name);
    }
    for (const panel of document.querySelectorAll('.panel')) {
      panel.classList.toggle('active', panel.dataset.panel === name);
    }
    if (name === 'paper') Paper.refresh();
  }

  function setupNavigation() {
    for (const btn of document.querySelectorAll('.rail-btn')) {
      btn.addEventListener('click', () => openPanel(btn.dataset.panel));
    }

    for (const tab of document.querySelectorAll('[data-subtab]')) {
      tab.addEventListener('click', () => {
        for (const t of document.querySelectorAll('[data-subtab]')) {
          t.classList.toggle('active', t === tab);
        }
        for (const p of document.querySelectorAll('[data-subpanel]')) {
          p.classList.toggle('active', p.dataset.subpanel === tab.dataset.subtab);
        }
      });
    }

    for (const tab of document.querySelectorAll('[data-restab]')) {
      tab.addEventListener('click', () => showResults(tab.dataset.restab));
    }
  }

  function showResults(which) {
    openPanel('results');
    for (const t of document.querySelectorAll('[data-restab]')) {
      t.classList.toggle('active', t.dataset.restab === which);
    }
    for (const p of document.querySelectorAll('[data-respanel]')) {
      p.classList.toggle('active', p.dataset.respanel === which);
    }
  }

  // ---------- Import ----------

  let importKind = null;

  function setupImport() {
    for (const btn of document.querySelectorAll('[data-import]')) {
      btn.addEventListener('click', () => {
        importKind = btn.dataset.import;
        el.importFile.value = '';        // so re-picking the same file fires
        el.importFile.click();
      });
    }

    el.importFile.addEventListener('change', async () => {
      const file = el.importFile.files?.[0];
      if (!file) return;

      try {
        const content = await file.text();
        let result;
        try {
          result = await API.importPlugin({ filename: file.name, content });
        } catch (err) {
          // 409 means the name is taken; offer to replace rather than making
          // the user rename the file outside the app.
          if (!/đã tồn tại/.test(err.message)) throw err;
          if (!window.confirm(`${err.message}\n\nGhi đè file cũ?`)) return;
          result = await API.importPlugin({ filename: file.name, content, overwrite: true });
        }

        toast(`Đã nhập ${result.spec.name} → ${result.path}`);
        // Hot-reload will also fire from the file watcher; refreshing here
        // means the list updates even if the watcher is unavailable.
        if (result.kind === 'indicator') Indicators.setCatalog(await API.catalog());
        else await Strategy.load();
      } catch (err) {
        toast(err.message, true);
      }
    });
  }

  // ---------- Controls ----------

  function buildTimeframeButtons() {
    const allowed = allowedTimeframes(state.symbol);

    // Keep the current timeframe if this symbol has it; otherwise fall back to
    // one it does, rather than charting a frame that will come back empty.
    if (!allowed.includes(state.timeframe)) {
      state.timeframe = allowed.includes('1d') ? '1d' : allowed[allowed.length - 1];
    }

    el.timeframes.innerHTML = '';
    for (const tf of allowed) {
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
        symbols: [state.symbol], timeframes: [state.timeframe],
      });
      const failed = report.series.filter((s) => s.error);
      if (failed.length) setStatus(`Lỗi: ${failed[0].error}`, 'error');
      else toast(`Đã thêm ${report.total_rows.toLocaleString('vi-VN')} nến`);
      await loadCandles();
    } catch (err) {
      setStatus(err.message, 'error');
    } finally {
      el.backfill.disabled = false;
      setLoading(false);
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
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = original;
      setLoading(false);
    }
  }

  // ---------- Boot ----------

  async function start() {
    ChartManager.init(el.chartMain);
    setupNavigation();
    setupImport();

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
        size: document.getElementById('exec-size'),      // % of equity per trade
        leverage: document.getElementById('exec-leverage'),
        fee: document.getElementById('exec-fee'),
        slippage: document.getElementById('exec-slippage'),
      },
      context: () => ({ ...state }),
      onResult: (result) => ChartManager.setTradeMarkers(result.trades),
    });

    Paper.init({
      elements: {
        list: document.getElementById('paper-sessions'),
        refresh: document.getElementById('refresh-paper'),
      },
      onToast: toast,
    });

    Live.init({
      onCandle: onLiveCandle,
      onCandleClose: onLiveCandleClose,
      onPluginsChanged,
      onStatus: setLiveState,
      onPaperUpdate: (session) => Paper.apply(session),
      onPaperEvent: (sessionId, event) => {
        if (event.type === 'entry') {
          toast(`Paper: vào ${event.side === 'long' ? 'LONG' : 'SHORT'} @ ${event.price.toFixed(2)}`);
        } else if (event.type === 'exit') {
          toast(`Paper: đóng lệnh, P&L ${event.trade.pnl.toFixed(2)}`);
        } else if (event.type === 'liquidation') {
          toast('Paper: bị thanh lý', true);
        }
      },
    });

    try {
      const config = await API.config();
      state.symbol = config.default_symbol;
      state.timeframe = config.default_timeframe;
      state.limit = Number(el.limit.value);

      await loadSymbolOptions(config);
      el.symbol.value = state.symbol;
      buildTimeframeButtons();
      applyMarketCapabilities();

      Indicators.setCatalog(await API.catalog());
      await Strategy.load();
      await Paper.refresh();
    } catch (err) {
      setStatus(`Không kết nối được backend: ${err.message}`, 'error');
      return;
    }

    el.symbol.addEventListener('change', () => {
      state.symbol = el.symbol.value;
      buildTimeframeButtons();      // markets differ in what they offer
      applyMarketCapabilities();
      loadCandles();
    });
    el.limit.addEventListener('change', () => { state.limit = Number(el.limit.value); loadCandles(); });
    el.backfill.addEventListener('click', runBackfill);

    el.liveToggle.addEventListener('click', () => {
      const turningOn = !Live.enabled;
      Live.setEnabled(turningOn);
      if (turningOn) Live.subscribe(state.symbol, state.timeframe);
    });

    el.runBacktest.addEventListener('click', () =>
      withButton(el.runBacktest, 'Đang chạy…', async () => {
        await Strategy.runBacktest();
        showResults('summary');
      }));

    el.runOptimize.addEventListener('click', () =>
      withButton(el.runOptimize, 'Đang quét…', async () => {
        const result = await Strategy.runOptimize();
        if (result) showResults('optimize');
      }));

    el.startPaper.addEventListener('click', () =>
      withButton(el.startPaper, 'Đang khởi động…', async () => {
        const session = await Strategy.startPaper();
        if (!session) return;
        // A paper session needs the live feed to make progress, so turn it on
        // rather than leaving the session silently stalled.
        if (!Live.enabled) {
          Live.setEnabled(true);
          Live.subscribe(state.symbol, state.timeframe);
        }
        openPanel('paper');
        toast('Đã bắt đầu phiên paper trading');
      }));

    await loadCandles();
  }

  start();
})();
