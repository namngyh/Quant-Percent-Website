/* Application wiring.

   The rail opens exactly one panel at a time, and clicking the open one closes
   it: three columns of controls competing for attention was the thing that
   made this hard to read. */

(() => {
  const el = {
    symbol: document.getElementById('symbol'),
    timeframes: document.getElementById('timeframes'),
    limit: document.getElementById('limit'),
    status: document.getElementById('status'),
    loading: document.getElementById('loading'),
    chartMain: document.getElementById('chart-main'),
    panes: document.getElementById('panes'),
    chartStack: document.querySelector('.charts-stack'),
    panelHost: document.getElementById('panel-host'),
    runBacktest: document.getElementById('run-backtest'),
    runOptimize: document.getElementById('run-optimize'),
    startPaper: document.getElementById('start-paper'),
    importFile: document.getElementById('import-file'),
    runWalkForward: document.getElementById('run-walkforward'),
    runMonteCarlo: document.getElementById('run-montecarlo'),
    runCompare: document.getElementById('run-compare'),
    compareList: document.getElementById('compare-list'),
    openReport: document.getElementById('open-report'),
    drawBar: document.getElementById('draw-bar'),
    chartType: document.getElementById('chart-type'),
    chartTypeMenu: document.getElementById('chart-type-menu'),
    modeToggle: document.getElementById('mode-toggle'),
    layout: document.getElementById('layout'),
    price: document.getElementById('price'),
    priceBlock: document.getElementById('price-block'),
    priceChange: document.getElementById('price-change'),
    chartTools: document.getElementById('chart-tools'),
    toggleMarkers: document.getElementById('toggle-markers'),
    clearMarkers: document.getElementById('clear-markers'),
    exportCsv: document.getElementById('export-csv'),
    formatDialog: document.getElementById('format-dialog'),
    formatBody: document.getElementById('format-body'),
    formatClose: document.getElementById('format-close'),
    formatDownload: document.getElementById('format-download'),
    formatCopy: document.getElementById('format-copy'),
    formatFoot: document.querySelector('.dialog-foot'),
    starSymbol: document.getElementById('star-symbol'),
    starStrategy: document.getElementById('star-strategy'),
    infoStrategy: document.getElementById('info-strategy'),
  };

  const state = { symbol: null, timeframe: null, limit: 2000 };

  // Previous rendered price, for the ticker's up/down colour. Declared with the
  // rest of the module state rather than beside `showPrice`, because
  // `loadCandles` calls that before the ticker's own section is reached.
  let lastPrice = null;
  /* How many bars the chart is holding. Kept here rather than read from the
     selector, because after panning left the chart holds more than the
     selector ever asked for and the two numbers stop agreeing. The old status
     line showed the selector's value beside the selector itself — the same
     number twice, and the wrong one once history had loaded. */
  let loadedBars = 0;

  /* The loaded bar count lives on the symbol picker, not in the status line.

     The status line is for things that need words, and `onLiveCandle` clears
     it on every tick for exactly that reason. With realtime now on from the
     start, a count written there is wiped by the first tick — it would flash
     once after every history page and never be readable. On the picker it is
     always available and takes no space in a bar the user asked to have less
     in it. */
  function showLoadedBars() {
    if (!el.symbol) return;
    el.symbol.title = t('status.bars', { n: loadedBars.toLocaleString(I18n.locale()) });
  }

  const INTRADAY = new Set(['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h']);

  /* The status line, remembered as a thunk rather than as text.
   *
   * Switching language has to re-render it, and by then the numbers that went
   * into the sentence are long out of scope. Keeping the closure means the
   * line rebuilds itself in the new language from the same values, instead of
   * needing every call site to hand its arguments over for storage. */
  let lastStatus = null;

  function setStatus(message, kind = '') {
    lastStatus = null;
    el.status.textContent = message;
    el.status.className = `status ${kind}`;
  }

  /** Set a status that can rebuild itself when the language changes. */
  function setStatusLive(build, kind = '') {
    lastStatus = { build, kind };
    el.status.textContent = build();
    el.status.className = `status ${kind}`;
  }

  function refreshStatus() {
    if (lastStatus) {
      el.status.textContent = lastStatus.build();
      el.status.className = `status ${lastStatus.kind}`;
    }
  }

  function toast(message, bad = false) {
    const node = document.createElement('div');
    node.className = `toast${bad ? ' bad' : ''}`;
    node.textContent = message;
    document.body.appendChild(node);
    setTimeout(() => node.remove(), bad ? 5000 : 3200);
  }

  // ---------- Data ----------

  async function loadCandles() {
    Session.patch({ symbol: state.symbol, timeframe: state.timeframe });
    MultiChart.syncActive();
    const cell = MultiChart.activeCell;
    const manager = ChartHub.active;
    const drawings = DrawingHub.active;
    const loading = cell?.loading || el.loading;
    const { symbol, timeframe, limit } = state;
    const requested = `${symbol}|${timeframe}`;
    const token = {};
    const owner = cell || manager;
    owner.loadToken = token;
    const current = () => owner.loadToken === token && !cell?.destroyed;
    const isActive = () => current() && ChartHub.active === manager;
    loading.hidden = false;
    try {
      const data = await API.candles({
        symbol, timeframe, limit,
      });

      // A switch changes the toolbar's target, never this request's owner.
      // A token also distinguishes two requests for the same market/frame.
      if (!current()) return;

      if (!data.count) {
        // Drop the drawings too, or lines from the previous timeframe linger
        // over an empty chart. The active list stays, so they redraw when data
        // for this series arrives.
        manager.clearAll();
        manager.clearTradeMarkers();
        manager.setCandles([], [], { timeVisible: false, key: null });
        drawings.load(requested);
        if (isActive()) {
          loadedBars = 0;
          setStatusLive(() => t('status.noData'), 'error');
          hidePrice();
        }
        return;
      }

      manager.setCandles(data.candles, data.volumes, {
        timeVisible: INTRADAY.has(timeframe),
        key: requested,
      });

      /* Subscribe as soon as the chart is showing the new series, and before
         anything that can fail.

         This used to sit after `await Indicators.recomputeAll()`. A recompute
         that threw took the rest of the function with it, so the socket stayed
         subscribed to the previous symbol while the chart held the new one —
         and the header price then tracked an instrument nobody had selected.
         Nothing between here and the end of the function is a precondition for
         receiving live data. */
      if (isActive()) Live.subscribe(symbol, timeframe);
      // A different series has its own history; the previous "nothing older"
      // answer says nothing about this one.
      if (cell) cell.exhausted = false;
      // Shapes are notes about one series. Showing a trend line drawn on BTC
      // 1h over VIC daily would be worse than not showing it at all.
      drawings.load(requested);

      // The symbol and the timeframe are already selected two controls to the
      // left, and the price now has a readout of its own, so the status line
      // is left for the one thing neither of those shows.
      const last = data.candles[data.candles.length - 1];
      if (isActive()) {
        loadedBars = data.count;
        showLoadedBars();
        warnIfDataIncomplete(requested);
        announceCorporateActions(requested, data.corporate_actions);
        warnIfWarrant(symbol);
        showPrice(last.close);
      }

      manager.clearTradeMarkers();

      /* One broken indicator must not cost the chart everything after it.

         `recomputeAll` runs user-supplied Python through the API; a plugin
         that raises is a normal event, not an exceptional one. Letting it
         propagate skipped the trade markers, the subscription and the
         catch-up, and reported the whole load as failed. */
      try {
        if (cell) await computeCellIndicators(cell);
        else await Indicators.recomputeAll();
      } catch (err) {
        toast(L(`Không tính được chỉ báo: ${err.message}`,
                `Could not compute indicators: ${err.message}`), 'bad');
      }
      if (!isActive()) return;
      drawPaperMarkers();
      drawPositionLines();

      // Fill any gap left while the app was closed, then redraw including it.
      if (await catchUpIfBehind(data, { symbol, timeframe, loading, isActive }) && isActive()) {
        await loadCandles();
      }
    } catch (err) {
      if (isActive()) setStatus(err.message, 'error');
    } finally {
      if (current()) loading.hidden = true;
    }
  }

  async function computeIndicator(instanceId, instance, cell = MultiChart.activeCell) {
    const manager = cell?.manager || ChartHub.active;
    const panes = cell?.panes || el.panes;
    const { symbol, timeframe } = cell?.ws || state;
    const key = `${symbol}|${timeframe}`;
    const loadToken = cell?.loadToken;
    const params = { ...instance.params };
    const token = {};
    instance.computeToken = token;
    const result = await API.compute({
      indicatorId: instance.spec.id,
      symbol,
      timeframe,
      params,
      /* As many bars as the chart holds, not the load size. After panning
         left the chart holds more than `state.limit`, and an indicator
         computed over the original 2 000 left the older stretch bare. */
      limit: Math.max(state.limit, manager.barCount),
    });
    const instances = !cell || MultiChart.activeCell === cell ? Indicators.active : cell.indicators;
    if (cell?.destroyed || cell?.loadToken !== loadToken || manager.seriesKey !== key
        || instances.get(instanceId) !== instance || instance.computeToken !== token
        || JSON.stringify(instance.params) !== JSON.stringify(params)) return;
    // The backend tags each output with the pane it belongs in, so one call
    // handles overlays, panels, and indicators that mix the two.
    manager.draw(instanceId, result, panes);
  }

  // ---------- Live ----------

  let recomputeTimer = null;


  // Named `liveState`, not `state`: destructuring it as `state` would shadow
  // the module-level state object and make a later edit here quietly wrong.
  let lastLiveState = 'offline';

  function setLiveState({ state: liveState }) {
    lastLiveState = liveState;
    Workspace.setConnection(liveState);
    // Keep the header connection badge and the quote's freshness in sync.

    // A stale price is worse than no price: it looks current.
    if (liveState !== 'live' && liveState !== 'connecting') hidePrice();
  }

  /* The live price, and whether the last tick moved up or down.
   *
   * Compared against the previous *rendered* price rather than the candle's
   * open: within one forming candle the open never changes, so colouring
   * against it would freeze the ticker green or red for a whole bar instead of
   * flickering with each trade. An unchanged price keeps the previous colour:
   * a tick that repeats the last price is not a reversal. */
  function showPrice(value) {
    if (!Number.isFinite(value)) return;
    el.price.textContent = value.toLocaleString('en-US', {
      minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
    if (lastPrice !== null && value !== lastPrice) {
      el.price.classList.toggle('up', value > lastPrice);
      el.price.classList.toggle('down', value < lastPrice);
    }

    /* Change against the opening price of the window on screen.

       Read from the chart rather than remembered in a variable of our own.
       A remembered anchor drifts out of step with the candles the moment
       anything goes wrong: a load that throws leaves the previous
       instrument's opening price in place while live ticks keep arriving, and
       the header then reports Bitcoin against a Vietnamese index — measured
       once at +3 993%. Paging older bars in moves the window's start too, and
       a remembered value would not know. Derived from the data on screen, the
       number cannot disagree with what is beside it. */
    const anchor = ChartManager.firstClose;
    if (el.priceChange && anchor > 0) {
      const delta = (value / anchor - 1) * 100;
      el.priceChange.textContent = `${delta >= 0 ? '+' : ''}${delta.toFixed(2)}%`;
      el.priceChange.classList.toggle('up', delta > 0);
      el.priceChange.classList.toggle('down', delta < 0);
    }

    el.priceBlock.hidden = false;
    lastPrice = value;
  }

  /* ---------- History paging ----------

     Panning left loads more of the past instead of stopping at whatever the
     bar-count box happened to say. The box still exists for the working view,
     where "give me exactly 5 000 bars" is a real thing to want before running
     a backtest, but nobody should have to set it just to look further back.

     `HISTORY_PAGE` is a page rather than the whole history because the point
     is to keep the pan smooth: a page arrives in about the time one flick
     takes, and the next flick asks for the next one. */
  const HISTORY_PAGE = 1000;
  /* Page older bars into one chart.

     Every chart in the grid has its own pager. The active one reads the app's
     state and recomputes through the indicator panel; any other recomputes its
     own indicator set. `exhausted` lives on the cell: one market running out of
     history says nothing about another. */
  async function pageCell(cell, oldestSeconds) {
    if (cell.exhausted) return;
    const isActive = MultiChart.activeCell === cell;
    const symbol = isActive ? state.symbol : cell.ws.symbol;
    const timeframe = isActive ? state.timeframe : cell.ws.timeframe;
    const key = `${symbol}|${timeframe}`;
    try {
      const data = await API.candlesBefore({ symbol, timeframe, before: oldestSeconds, limit: HISTORY_PAGE });
      if (key !== cell.manager.seriesKey) return;
      const added = cell.manager.prependCandles(data.candles, data.volumes, key);
      if (!added) {
        // Nothing older: stop asking, or a scroll becomes a request storm.
        cell.exhausted = true;
        return;
      }
      if (MultiChart.activeCell === cell) {
        loadedBars = cell.manager.barCount;
        showLoadedBars();
        await Indicators.recomputeAll();
      } else {
        await computeCellIndicators(cell);
      }
    } catch (err) {
      cell.exhausted = true;
      toast(L(`Không nạp thêm được lịch sử: ${err.message}`,
              `Could not load more history: ${err.message}`), 'bad');
    }
  }

  /* Two or four markets at once.

     The working chart stays where it is with all its tools; the extra panes
     are candles for comparison. Picking a market for a pane reuses the same
     symbol list the main picker shows, so there is one catalogue rather than
     two that can disagree. */
  function setupMultiChart() {
    const grid = document.getElementById('chart-grid');
    if (!grid) return;

    MultiChart.init({
      grid,
      workUnit: document.getElementById('work-unit'),
      current: () => ({
        symbol: state.symbol,
        timeframe: state.timeframe,
        indicators: Indicators.snapshot(),
      }),
      timeframes: (symbol) => allowedTimeframes(symbol),
      describe: (list) => Indicators.describe(list),
      exportIndicators: () => Indicators.exportState(),
      beforeDeactivate: () => Indicators.flushPending(),
      configure: configureCell,
      loadCell,
      activated: onCellActivated,
      onDrawingsChange: renderDrawBar,
      setActiveSymbol: (symbol) => {
        el.symbol.value = symbol;
        el.symbol.dispatchEvent(new Event('change', { bubbles: true }));
      },
      setActiveTimeframe: (tf) => {
        [...el.timeframes.children].find((b) => b.textContent.trim() === tf)?.click();
      },
      onResize: () => ChartManager.refreshSize(),
    });

    const markLayout = (chosen) => {
      // Buttons only: the grid itself carries `data-layout`.
      for (const b of document.querySelectorAll('button[data-layout]')) {
        b.classList.toggle('active', Number(b.dataset.layout) === chosen);
      }
      ChartManager.refreshSize();
    };

    for (const button of document.querySelectorAll('button[data-layout]')) {
      button.addEventListener('click', () => {
        markLayout(MultiChart.setLayout(Number(button.dataset.layout)));
      });
    }

    // The layout, each chart's market, frame and indicators, and the sizes.
    markLayout(MultiChart.restore(Session.saved.multi));
  }

  /** Handlers every chart needs, whichever cell it lives in. */
  function configureCell(cell) {
    cell.manager.onNeedHistory = (oldest) => pageCell(cell, oldest);
    cell.manager.onLevelDragged = onLevelDragged;
    cell.manager.onPositionClose = closePaperPosition;
    cell.manager.onMarkersChanged = (count, visible) => {
      if (MultiChart.activeCell === cell) paintMarkerTools(count, visible);
    };
    cell.manager.onSeriesChanged = (series) => cell.drawings?.setSeries(series);
    // A new chart is drawn the way the others are.
    if (cell.manager !== ChartHub.active && ChartHub.active.priceType) {
      cell.manager.setPriceType(ChartHub.active.priceType);
    }
  }

  /* Load a chart that is not the working one: its series, its drawings, its
     indicators. Only this chart changes. */
  async function loadCell(cell) {
    const { symbol, timeframe } = cell.ws;
    const key = `${symbol}|${timeframe}`;
    const token = {};
    cell.loadToken = token;
    const current = () => cell.loadToken === token && !cell.destroyed;
    cell.exhausted = false;
    cell.loading.hidden = false;
    try {
      const data = await API.candles({ symbol, timeframe, limit: state.limit });
      if (!current()) return;
      cell.manager.clearAll();
      cell.manager.clearTradeMarkers();
      cell.manager.setCandles(data.candles || [], data.volumes || [], {
        timeVisible: INTRADAY.has(timeframe),
        key: data.count ? key : null,
      });
      cell.drawings.load(key);
      cell.loading.hidden = true;

      await loadWorkingView();                 // the indicator catalogue
      if (!current()) return;
      cell.indicators = Indicators.buildState(cell.ws.indicators || []);
      if (MultiChart.activeCell === cell) Indicators.importState(cell.indicators);
      await computeCellIndicators(cell);
    } catch (err) {
      if (current()) {
        toast(L(`Không nạp được ${symbol}: ${err.message}`, `Could not load ${symbol}: ${err.message}`), true);
      }
    } finally {
      if (current()) cell.loading.hidden = true;
    }
  }

  async function computeCellIndicators(cell) {
    const instances = MultiChart.activeCell === cell ? Indicators.active : cell.indicators;
    await Promise.all([...instances].map(async ([instanceId, instance]) => {
      try {
        await computeIndicator(instanceId, instance, cell);
        instance.error = null;
      } catch (err) {
        instance.error = err.message;
      }
    }));
    if (MultiChart.activeCell === cell) Indicators.rerender();
  }

  /* The working chart is now this one. Point everything at it — the symbol
     and timeframe controls, the indicator list, the price, the drawing bar,
     the live feed — and change nothing on any chart. */
  function onCellActivated(cell) {
    state.symbol = cell.ws.symbol;
    state.timeframe = cell.ws.timeframe;
    el.symbol.value = state.symbol;
    loadedBars = cell.manager.barCount;
    showLoadedBars();
    refreshStars();
    Paper.refreshManualButton();
    buildTimeframeButtons();
    Markets.refreshTimeframeNote();
    Indicators.importState(cell.indicators);

    cell.chartMain.appendChild(el.chartTools);
    paintMarkerTools(cell.manager.markerCount, cell.manager.markersVisible);
    renderChartTypeMenu();
    renderDrawBar();

    hidePrice();
    if (cell.manager.lastClose !== null) showPrice(cell.manager.lastClose);
    Live.subscribe(state.symbol, state.timeframe);
    catchUpLive(cell);

    drawPaperMarkers();
    drawPositionLines();
    Session.patch({ symbol: state.symbol, timeframe: state.timeframe, indicators: Indicators.snapshot() });
  }

  /* Bars the chart missed while it was not the one receiving the live feed.
     Applied through the same update path a live candle takes, so nothing is
     re-drawn from scratch and the view stays where it is. */
  async function catchUpLive(cell) {
    const key = cell.manager.seriesKey;
    if (!key) return;
    /* Only the bars it could have missed: the time since its last bar, in
       bars, plus two for the forming one. A click on a chart that was active a
       moment ago asks for three bars, not three hundred. */
    const frameSeconds = state.timeframe === '1d' ? 86400 : (FRAME_MINUTES[state.timeframe] || 60) * 60;
    const lastUtc = (cell.manager.lastCandleTime() ?? 0) - 7 * 3600;
    const missed = Math.ceil(Math.max(0, Date.now() / 1000 - lastUtc) / frameSeconds);
    const limit = Math.min(1000, Math.max(3, missed + 2));
    try {
      const data = await API.candles({ symbol: state.symbol, timeframe: state.timeframe, limit });
      if (cell.manager.seriesKey !== key) return;
      (data.candles || []).forEach((c, n) => {
        cell.manager.updateCandle({
          time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
          volume: data.volumes?.[n]?.value ?? 0,
        }, key);
      });
      if (MultiChart.activeCell === cell && cell.manager.lastClose !== null) {
        showPrice(cell.manager.lastClose);
      }
    } catch {
      // The live feed fills the gap on its next bar anyway.
    }
  }

  /* Say when the minute data behind this chart is not what it looks like.

     A chart draws whatever bars exist and looks equally confident either way,
     so a session the pipeline half-missed and a symbol that only trades for
     six minutes a day both render as a normal-looking series — and a backtest
     over either returns a number with no hint attached. Measured on the real
     data: 2026-07-27 cost every Vietnamese symbol a quarter to a third of its
     bars at once, and A32 prints a median of one bar per session.

     Only raised for intraday frames. Daily bars come from a different table
     that these outages never touched. */
  /* A restated series says so, once per series.

     The prices on screen are no longer the ones in the database: a split was
     taken out of them so the history is on today's scale (§3.6). That is a
     change the reader has to be told about, because it is exactly what makes
     the chart disagree with a broker's raw one. */
  const actionsSeen = new Set();

  function announceCorporateActions(key, events) {
    if (!events?.length || actionsSeen.has(key)) return;
    actionsSeen.add(key);
    const worst = events.reduce((a, b) => (Math.abs(b.ratio - 1) > Math.abs(a.ratio - 1) ? b : a));
    const when = new Date(worst.open_time + Settings.tzOffsetSeconds() * 1000)
      .toISOString().slice(0, 10);
    const name = worst.label ? ` (${worst.label})` : '';
    toast(L(
      `Đã điều chỉnh ${events.length} sự kiện chia tách/cổ tức cổ phiếu trong chuỗi này; `
      + `lớn nhất ngày ${when}, tỷ lệ ${worst.ratio.toFixed(2)}${name}. `
      + 'Giá cũ được đưa về thang giá hôm nay, giá mới nhất giữ nguyên.',
      `${events.length} split/stock-dividend event(s) taken out of this series; `
      + `the largest on ${when}, ratio ${worst.ratio.toFixed(2)}${name}. `
      + 'Older prices are restated onto today\'s scale; the newest are untouched.'));
  }

  /* A covered warrant is not a small share.

     It decays against a strike and then expires, so a long backtest on one is
     measuring a wasting asset and, past expiry, an instrument that no longer
     exists. Measured over 120 sessions: CMWG2524 went from 1.21 to 0.01, a 99%
     fall with no corporate action behind it. The platform lists them because
     they are real series worth looking at — and says this before anyone reads
     a backtest of one as if it were a share. */
  const warrantsSeen = new Set();

  function warnIfWarrant(symbol) {
    const bare = String(symbol || '').replace(/^VN:/i, '').toUpperCase();
    if (!/^C[A-Z]{3}\d{4}$/.test(bare) || warrantsSeen.has(bare)) return;
    warrantsSeen.add(bare);
    toast(L(
      `${bare} là chứng quyền: giá hao mòn theo thời gian so với giá thực hiện và `
      + 'hết hiệu lực khi đáo hạn. Các giả định của backtest ở đây là giả định cổ '
      + 'phiếu, nên kết quả dài hơn vài tuần trên chứng quyền không đọc như kết quả cổ phiếu.',
      `${bare} is a covered warrant: it decays against its strike and expires. `
      + 'The backtest assumptions here are equity assumptions, so a result running '
      + 'longer than a few weeks on a warrant does not read like an equity result.'));
  }

  const coverageSeen = new Set();

  /* Coverage is fetched for every VN symbol, on any timeframe.

     It used to be fetched only on intraday frames, because only the warning
     needed it. The same reading now decides which timeframe buttons exist, so
     a symbol opened on the daily chart has to be measured too — otherwise its
     minute frames stay on offer purely because nobody looked. */
  async function warnIfDataIncomplete(key) {
    const symbol = state.symbol;
    if (!symbol.startsWith('VN:')) return;
    if (coverageSeen.has(symbol)) return;
    coverageSeen.add(symbol);

    let report;
    try {
      report = await API.vnCoverage(symbol);
    } catch {
      coverageSeen.delete(symbol);   // let a later load try again
      return;   // coverage is a courtesy; never let it break a chart load
    }

    // The bar count decides which frames are worth offering, and that holds
    // whether or not the user has moved on since.
    if (typeof report.median_bars === 'number') {
      const before = sessionBars.get(symbol);
      sessionBars.set(symbol, report.median_bars);
      if (before !== report.median_bars && symbol === state.symbol) {
        buildTimeframeButtons();
      }
    }

    /* The warning itself is only about minute data, so it stays on intraday
       frames — and only once per symbol, since 5m and 15m are built from the
       same bars and repeating it would tell one truth as if it were several. */
    if (!INTRADAY.has(state.timeframe)) return;
    if (key !== `${symbol}|${state.timeframe}`) return;

    if (report.thin) {
      toast(L(`${report.symbol} chỉ khớp lệnh khoảng ${report.median_bars} phút mỗi phiên, `
              + 'nên khung phút gần như không có gì để đọc. Dùng khung ngày sẽ đúng hơn.',
              `${report.symbol} only trades for about ${report.median_bars} minutes a `
              + 'session, so intraday frames have little to show. Daily is the honest frame '
              + 'for it.'), true);
      return;
    }

    const gaps = report.gaps || [];
    if (!gaps.length) return;

    const worst = gaps[0];
    const when = new Date(worst.date).toLocaleDateString();
    toast(L(`Dữ liệu phút thiếu ở ${gaps.length} phiên gần đây — nặng nhất ${when} `
            + `(${worst.bars}/${worst.expected} nến, thiếu ${worst.missing_pct.toFixed(0)}%). `
            + 'Backtest qua các phiên đó sẽ tính trên dữ liệu khuyết.',
            `Minute data is short on ${gaps.length} recent session(s) — worst ${when} `
            + `(${worst.bars}/${worst.expected} bars, ${worst.missing_pct.toFixed(0)}% missing). `
            + 'A backtest crossing those runs on incomplete data.'), true);
  }

  /* Say so when the running server predates the code on disk.

     Frontend files are read from disk per request and are never stale. Python
     is imported once, so a backend edit does nothing until the process
     restarts — and the way that surfaces is genuinely misleading: a new
     endpoint 404s, the router falls through to a path parameter, and
     `/api/paper/summary` comes back as "unknown paper session: summary". The
     message blames a session, and the session is not the problem. */
  async function warnIfServerStale() {
    let health;
    try {
      health = await API.health();
    } catch {
      return;   // the backend is unreachable; that has its own message
    }
    if (!health?.stale) return;
    setStatus(L('Server đang chạy code cũ — hãy khởi động lại',
                'The server is running older code — restart it'), 'error');
    toast(L('Server đang chạy code cũ hơn mã nguồn trên đĩa. '
            + 'Hãy tắt và chạy lại run.py, nếu không các tính năng mới sẽ báo lỗi 404.',
            'The server is running code older than the source on disk. Stop it and '
            + 'run run.py again, or new features will fail with 404s.'), 'bad');
  }

  /* ---------- Drawing tools ----------

     A vertical strip down the left edge of the chart, which is where every
     charting package puts it, so the muscle memory transfers.

     Each glyph is an inline SVG rather than a character: the shapes here are
     geometric (a line at an angle, a rectangle, a ladder of Fib levels) and no
     font has them. Twelve <path> strings is less to maintain than an icon
     font, and they inherit colour from the button. */
  const DRAW_ICONS = {
    cursor: '<path d="M4 2l7 16 2-6 6-2z"/>',
    trend: '<path d="M3 17L17 5"/><circle cx="4" cy="17" r="1.6"/><circle cx="16" cy="5" r="1.6"/>',
    horizontal: '<path d="M2 10h16"/><circle cx="10" cy="10" r="1.6"/>',
    ray: '<path d="M4 10h14"/><circle cx="4" cy="10" r="1.6"/>',
    vertical: '<path d="M10 2v16"/><circle cx="10" cy="10" r="1.6"/>',
    rect: '<rect x="3" y="5" width="14" height="10" rx="1"/>',
    fib: '<path d="M3 4h14M3 8h14M3 12h14M3 16h14"/>',
    text: '<path d="M4 4h12M10 4v13"/>',
    measure: '<path d="M3 13L17 6"/><path d="M3 13v3M17 6v3"/>',
  };

  function drawGlyph(id) {
    return `<svg viewBox="0 0 20 20" aria-hidden="true" fill="none"
      stroke="currentColor" stroke-width="1.6" stroke-linecap="round"
      stroke-linejoin="round">${DRAW_ICONS[id] || ''}</svg>`;
  }

  function renderDrawBar() {
    if (!el.drawBar) return;
    const tools = Drawings.tools.map((t) => `
      <button type="button" class="draw-btn${Drawings.tool === t.id ? ' active' : ''}"
              data-draw-tool="${t.id}" title="${escapeAttr(t.label())}"
              aria-label="${escapeAttr(t.label())}"
              aria-pressed="${Drawings.tool === t.id}">${drawGlyph(t.id)}</button>`).join('');

    // The toggles and the two destructive actions are separated from the
    // tools: picking a tool and wiping every drawing should not be adjacent
    // buttons that look alike.
    const toggle = (key, on, glyph) => `
      <button type="button" class="draw-btn${on ? ' on' : ''}" data-draw-toggle="${key}"
              title="${escapeAttr(t(`draw.${key}`))}"
              aria-label="${escapeAttr(t(`draw.${key}`))}"
              aria-pressed="${on}">${glyph}</button>`;

    el.drawBar.innerHTML = `
      <div class="draw-group">${tools}</div>
      <div class="draw-group">
        ${toggle('magnet', Drawings.magnet,
          drawGlyph('') .replace('></svg>',
            '><path d="M6 4v6a4 4 0 008 0V4"/><path d="M4 4h4M12 4h4"/></svg>'))}
        ${toggle('lock', Drawings.locked,
          drawGlyph('').replace('></svg>',
            '><rect x="5" y="9" width="10" height="7" rx="1"/><path d="M7.5 9V7a2.5 2.5 0 015 0v2"/></svg>'))}
        ${toggle('hide', !Drawings.visible,
          drawGlyph('').replace('></svg>',
            '><path d="M2 10s3-5 8-5 8 5 8 5-3 5-8 5-8-5-8-5z"/><circle cx="10" cy="10" r="2"/></svg>'))}
      </div>
      <div class="draw-group">
        <button type="button" class="draw-btn" data-draw-action="remove"
                title="${escapeAttr(Drawings.hasSelection
                  ? t('draw.remove') : t('draw.pick'))}"
                aria-label="${escapeAttr(t('draw.remove'))}"
                ${Drawings.hasSelection ? '' : 'disabled'}>${
          drawGlyph('').replace('></svg>',
            '><path d="M6 6l8 8M14 6l-8 8"/><circle cx="10" cy="10" r="7.5"/></svg>')}</button>
        <button type="button" class="draw-btn" data-draw-action="undo"
                title="${escapeAttr(t('draw.undo'))}" aria-label="${escapeAttr(t('draw.undo'))}"
                ${Drawings.count ? '' : 'disabled'}>${
          drawGlyph('').replace('></svg>', '><path d="M4 9h9a4 4 0 010 8H8"/><path d="M7 5L3 9l4 4"/></svg>')}</button>
        <button type="button" class="draw-btn danger" data-draw-action="clear"
                title="${escapeAttr(t('draw.clear'))}" aria-label="${escapeAttr(t('draw.clear'))}"
                ${Drawings.count ? '' : 'disabled'}>${
          drawGlyph('').replace('></svg>', '><path d="M5 6h10M8 6V4h4v2M6 6l1 10h6l1-10"/></svg>')}</button>
      </div>`;
  }

  function setupDrawings() {
    if (!el.drawBar) return;
    Drawings.init({
      chart: ChartManager.chart,
      series: ChartManager.priceSeries,
      host: el.chartMain,
      manager: ChartHub.active,
      onChange: renderDrawBar,
    });
    renderDrawBar();

    el.drawBar.addEventListener('click', (event) => {
      const tool = event.target.closest('[data-draw-tool]');
      if (tool) { Drawings.setTool(tool.dataset.drawTool); return; }

      const toggle = event.target.closest('[data-draw-toggle]');
      if (toggle) {
        const key = toggle.dataset.drawToggle;
        if (key === 'magnet') Drawings.setMagnet(!Drawings.magnet);
        if (key === 'lock') Drawings.setLocked(!Drawings.locked);
        if (key === 'hide') Drawings.setVisible(!Drawings.visible);
        return;
      }

      const action = event.target.closest('[data-draw-action]');
      if (!action) return;
      if (action.dataset.drawAction === 'remove') Drawings.removeSelected();
      if (action.dataset.drawAction === 'undo') Drawings.undo();
      if (action.dataset.drawAction === 'clear') {
        // Wiping every shape on the series is not undoable, so it asks.
        if (window.confirm(L('Xoá toàn bộ hình vẽ trên biểu đồ này?',
                             'Remove every drawing on this chart?'))) Drawings.clear();
      }
    });

    I18n.onChange(renderDrawBar);
  }

  /* ---------- Chart shape ----------

     Twelve ways to draw the same price. The choice is remembered per browser
     rather than per symbol: it is a reading preference, not a property of the
     instrument, and having it change under you when you switch symbol would be
     the opposite of a preference. */
  const CHART_TYPE_KEY = 'qp.chartType';

  // The labels are ours, not user input, but they go through the same escape
  // as anything else built into a template: a helper that is only correct for
  // the strings you happen to pass it is not a helper.
  const escapeAttr = (v) => String(v ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );

  function renderChartTypeMenu() {
    if (!el.chartTypeMenu) return;
    const current = ChartManager.priceType;
    el.chartTypeMenu.innerHTML = ChartTypes.list.map((t) => `
      <button type="button" role="menuitemradio" class="ct-item${
        t.id === current ? ' active' : ''}" data-chart-type="${t.id}"
        aria-checked="${t.id === current}">
        <span class="ct-icon ct-icon-${t.icon}" aria-hidden="true"></span>
        <span>${escapeAttr(t.label())}</span>
      </button>`).join('');
    /* Icon only, with the name as its tooltip.

       The name was on the button and the top bar had no room for it — at
       1400px it was already clipped mid-word, which is worse than no label
       because a half-word looks like a rendering fault. The menu spells every
       shape out; the button only has to say which one is on. */
    el.chartType.innerHTML =
      `<span class="ct-icon ct-icon-${ChartTypes.icon(current)}" aria-hidden="true"></span>`;
    el.chartType.title = ChartTypes.label(current);
    el.chartType.setAttribute('aria-label', ChartTypes.label(current));
  }

  /* Put the menu under its button in viewport coordinates.

     It is `position: fixed` because its ancestor scrolls and would otherwise
     clip it (see .ct-menu in styles.css), and fixed elements do not inherit a
     position from the DOM — so the button's rectangle has to be measured and
     applied here. Flipped to the right edge when it would run off screen,
     since the button sits well to the right on narrow windows. */
  function placeChartTypeMenu() {
    const rect = el.chartType.getBoundingClientRect();
    const menu = el.chartTypeMenu;
    menu.style.top = `${rect.bottom + 6}px`;
    // Measure the width while it is still hidden by making it briefly
    // visible-but-transparent, or offsetWidth reads 0 and every menu lands
    // flush against the left edge of the button.
    menu.style.left = '0px';
    menu.hidden = false;
    const width = menu.offsetWidth;
    menu.hidden = true;
    const room = document.documentElement.clientWidth - 8;
    menu.style.left = `${Math.max(8, Math.min(rect.left, room - width))}px`;
  }

  function closeChartTypeMenu() {
    if (!el.chartTypeMenu || el.chartTypeMenu.hidden) return;
    el.chartTypeMenu.hidden = true;
    el.chartType.setAttribute('aria-expanded', 'false');
  }

  function chooseChartType(id) {
    ChartManager.setPriceType(id);
    try { localStorage.setItem(CHART_TYPE_KEY, id); } catch { /* private mode */ }
    renderChartTypeMenu();
    closeChartTypeMenu();
    // Indicator panes are drawn against the price series, and the price series
    // was just replaced.
    Indicators.recomputeAll();
  }

  function setupChartType() {
    if (!el.chartType) return;
    let saved = null;
    try { saved = localStorage.getItem(CHART_TYPE_KEY); } catch { /* ignore */ }
    if (saved && ChartTypes.has(saved)) ChartManager.setPriceType(saved);
    renderChartTypeMenu();

    el.chartType.addEventListener('click', (event) => {
      event.stopPropagation();
      const opening = el.chartTypeMenu.hidden;
      if (opening) placeChartTypeMenu();
      el.chartTypeMenu.hidden = !opening;
      el.chartType.setAttribute('aria-expanded', String(opening));
    });
    el.chartTypeMenu.addEventListener('click', (event) => {
      const item = event.target.closest('[data-chart-type]');
      if (item) chooseChartType(item.dataset.chartType);
    });
    // Clicking anywhere else, or Escape, puts it away.
    document.addEventListener('click', closeChartTypeMenu);
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') closeChartTypeMenu();
    });
    I18n.onChange(renderChartTypeMenu);
  }

  /* ---------- View mode ----------

     The app opens on the overview: one line, no panels, nothing to configure.
     That is the question someone has before they have any other question —
     what has this thing been doing — and it costs one request to answer.

     The working view is everything else, and everything it needs is fetched
     the first time it is opened rather than at start-up. Measured on a warm
     server, that took the indicator catalogue and the strategy list off the
     path to the first candle entirely. */
  let workingViewLoaded = null;

  function loadWorkingView() {
    if (workingViewLoaded) return workingViewLoaded;
    workingViewLoaded = (async () => {
      const [catalog] = await Promise.all([API.catalog(), Strategy.load()]);
      Indicators.setCatalog(catalog);
      renderComparePicker();
      restoreWorkingState();
    })().catch((err) => {
      // Let the next attempt try again rather than leaving the panels empty
      // for the rest of the session.
      workingViewLoaded = null;
      toast(`Không nạp được chỉ báo và chiến lược: ${err.message}`, 'bad');
    });
    return workingViewLoaded;
  }

  /* Indicators and the strategy come back once, the first time their
     catalogues exist. Later openings of the working view find them already on
     the chart; restoring again would stack a second copy of every indicator. */
  let workingStateRestored = false;

  function restoreWorkingState() {
    if (workingStateRestored) return;
    workingStateRestored = true;
    if (!Indicators.active.size) Indicators.restore(Session.saved.indicators);
    Strategy.restore(Session.saved.strategy);
  }

  function setViewMode(next) {
    const mode = ChartManager.setMode(next);
    document.body.dataset.mode = mode;
    Session.patch({ mode });
    MultiChart.setMode(mode);
    // Reflected in the URL so a working session can be bookmarked or reloaded
    // straight back into the working view instead of via the overview.
    const hash = mode === 'trading' ? '#trade' : '';
    if (window.location.hash !== hash) {
      history.replaceState(null, '', window.location.pathname + hash);
    }
    if (el.modeToggle) {
      el.modeToggle.textContent = mode === 'overview' ? t('top.trade') : t('top.overview');
      el.modeToggle.classList.toggle('btn-primary', mode === 'overview');
    }
    if (mode === 'trading') loadWorkingView();

    /* Resize first, then frame. Switching mode shows or hides the rail and
       the panel, so the chart's box changes width — measured, 775px in the
       working view against 1161px in the overview — and the library derives
       bar spacing from the width it currently knows about. A fit computed
       before the resize is a fit for a box that no longer exists. */
    requestAnimationFrame(() => {
      ChartManager.refreshSize();
      if (mode === 'trading') ChartManager.focusRecent();
      else ChartManager.fitAll();
    });
  }

  function hidePrice() {
    el.priceBlock.hidden = true;
    el.price.classList.remove('up', 'down');
    el.priceChange?.classList.remove('up', 'down');
    lastPrice = null;
  }

  function onLiveCandle(candle) {
    // The chart checks this against the series it is holding and drops the
    // candle if they disagree, so a stale subscription cannot repaint it.
    const key = `${candle.symbol}|${candle.timeframe}`;
    if (ChartManager.seriesKey && key !== ChartManager.seriesKey) return;

    ChartManager.updateCandle({
      time: Math.floor(candle.open_time / 1000),
      open: candle.open, high: candle.high, low: candle.low,
      close: candle.close, volume: candle.volume,
    }, key);
    showPrice(candle.close);
    // The status line is for things that need words. The price is not one.
    setStatus('');
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

  /* Minute bars a symbol typically prints in one session, from the coverage
     endpoint. Cached per symbol because the answer barely moves. */
  const sessionBars = new Map();

  const FRAME_MINUTES = { '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
                          '1h': 60, '2h': 120, '4h': 240, '6h': 360,
                          '8h': 480, '12h': 720 };

  // Below this many bars per session a frame has nothing to show.
  const MIN_BARS_PER_SESSION = 4;

  /* Which timeframes this symbol can actually fill.

     Offering every frame for every symbol produced menus of buttons that
     mostly drew near-empty charts: A32 prints a median of one minute bar per
     session, so its "5m" was a single candle a day presented as an intraday
     series. A frame is offered when the symbol's own minute density would
     fill it. Daily is always offered — it comes from a different table and
     does not depend on minute coverage at all. */
  function allowedTimeframes(symbol) {
    const all = timeframesFor(symbol);
    if (!symbolHasIntraday(symbol)) return all.filter((tf) => tf === '1d');

    const perSession = sessionBars.get(symbol);
    if (perSession === undefined) return all;   // not measured yet; offer all

    return all.filter((tf) => {
      if (tf === '1d') return true;
      const minutes = FRAME_MINUTES[tf];
      if (!minutes) return true;
      return perSession / minutes >= MIN_BARS_PER_SESSION;
    });
  }

  /* Crypto symbols come with the config, so this costs nothing and runs before
     the first paint. The Vietnamese list does not: it is a database query over
     the Tailscale VPN, measured at 2.11 s with the VPN up, and much worse with
     it down where it has to time out first. It used to be awaited here, which
     meant nobody saw a chart until it came back — for a list that is only read
     when the symbol dropdown is opened. */
  function loadCryptoSymbols(config) {
    markets.crypto = config.markets?.find((m) => m.id === 'crypto') || {
      symbols: config.symbols, timeframes: config.timeframes,
    };
    symbolGroups = [
      { label: 'Crypto · Binance', options: markets.crypto.symbols.map((s) => ({ id: s, text: s })) },
    ];
    rebuildSymbolOptions();
  }

  /** Fetch the VN names and merge them into the picker when they arrive. */
  async function loadVnSymbols() {
    const groups = [...symbolGroups];
    try {
      const vn = await API.vnSymbols();
      markets.vn = {
        timeframes: vn.timeframes,
        index: new Map(vn.symbols.map((s) => [s.id, s])),
      };
      // Now the real frames for a VN symbol are known; if the one on screen is
      // not among them after all, switch and reload rather than chart nothing.
      if (isVN(state.symbol)) {
        const before = state.timeframe;
        buildTimeframeButtons();
        if (state.timeframe !== before) loadCandles();
      }

      const label = (s) => `${s.symbol}${s.name && s.name !== s.symbol ? ' · ' + s.name : ''}`;

      /* Grouped by what the instrument IS, not by whether it has minute bars.
         With 1,700 names the old two-group split was a wall of tickers: gold,
         a bank stock and a sector index sat in one list because they happened
         to share a data resolution, which is the one thing nobody picks a
         symbol by. Ordered so the small, distinct families come first — the
         1,500 equities are the haystack, and putting them on top buries
         everything else. Not labelled "HOSE" anywhere: the database has no
         exchange column, and HNX and UPCOM names sit among the HOSE ones. */
      const FAMILIES = [
        ['commodity', () => L('Hàng hoá & kim loại', 'Commodities & metals')],
        ['crypto', () => L('Tiền mã hoá', 'Crypto')],
        ['fx', () => L('Ngoại hối', 'Foreign exchange')],
        ['index_global', () => L('Chỉ số quốc tế', 'Global indices')],
        ['index_vn', () => L('Chỉ số Việt Nam', 'Vietnam indices')],
        ['futures_vn', () => L('Phái sinh Việt Nam', 'Vietnam futures')],
        ['index_sector', () => L('Chỉ số ngành', 'Sector indices')],
        ['fund', () => L('Quỹ ETF', 'ETFs')],
        ['warrant', () => L('Chứng quyền', 'Covered warrants')],
        ['equity', () => L('Cổ phiếu Việt Nam', 'Vietnam equities')],
      ];

      for (const [assetClass, groupLabel] of FAMILIES) {
        const members = vn.symbols.filter((s) => s.asset_class === assetClass);
        if (!members.length) continue;
        groups.push({
          label: `${groupLabel()} (${members.length})`,
          options: members.map((s) => ({ id: s.id, text: label(s) })),
        });
      }

      // A class the backend knows about but this list has not been taught yet
      // still has to reach the picker, or new data silently disappears.
      const placed = new Set(FAMILIES.map(([c]) => c));
      const rest = vn.symbols.filter((s) => !placed.has(s.asset_class));
      if (rest.length) {
        groups.push({
          label: L(`Khác (${rest.length})`, `Other (${rest.length})`),
          options: rest.map((s) => ({ id: s.id, text: label(s) })),
        });
      }
    } catch (err) {
      markets.vn = null;
      // Not fatal, and not silent either: say why the VN names are missing.
      // This now arrives after the chart is already up, which is the point —
      // a VPN that is off should cost the user a message, not a blank screen.
      setStatus(t('status.vnDown', { msg: err.message }), 'error');
      return;
    }

    symbolGroups = groups;
    rebuildSymbolOptions();
    // The multi-market picker and the comparison panes offer the same
    // catalogue as the chart's, filled from the same groups rather than each
    // fetching its own copy that can disagree with the others.
    Markets.setOptions(symbolGroups);
    MultiChart.setOptions(symbolGroups);
    // The picker may have been rebuilt from a favourite in the meantime.
    if (el.symbol.value !== state.symbol) el.symbol.value = state.symbol;
  }

  let symbolGroups = [];

  /** Render the picker, lifting starred symbols into a group of their own. */
  function rebuildSymbolOptions() {
    const chosen = el.symbol.value || state.symbol;
    const all = symbolGroups.flatMap((g) => g.options);
    const starredIds = new Set(Favourites.list('symbol'));
    const starred = all.filter((o) => starredIds.has(o.id));

    const groups = starred.length
      ? [{ label: `★ Đánh dấu (${starred.length})`, options: starred }, ...symbolGroups]
      : symbolGroups;

    el.symbol.innerHTML = groups
      .map(
        (g) =>
          `<optgroup label="${g.label}">` +
          g.options.map((o) => `<option value="${o.id}">${o.text}</option>`).join('') +
          '</optgroup>',
      )
      .join('');

    if (chosen) el.symbol.value = chosen;
  }



  // ---------- Catching up ----------
  //
  // The local crypto store only advances while this app is running, so after
  // the laptop has been shut a day it is a day behind. Closing that gap is
  // mechanical (the backfill already resumes from the newest stored bar) so
  // it happens on load rather than waiting for someone to notice the hole.
  // The Vietnam database is read live and is never behind.

  /* There is no size threshold any more.

     It used to stop above 5,000 bars and tell the user to press "Cập nhật dữ
     liệu". That button is gone, so the threshold now has nowhere to send
     anyone: it would just refuse to fill the gap and name a control that does
     not exist. A long catch-up is slow, not dangerous, and the status line
     says while it runs. */
  let catchingUp = false;

  async function catchUpIfBehind(data, { symbol, timeframe, loading, isActive }) {
    if (catchingUp || !data.can_backfill || !data.bars_behind) return false;

    catchingUp = true;
    /* The wait is shown as the loading mark, not as a sentence.

       "Đang bù 1 234 nến còn thiếu…" followed by "Đã tự bù 1 234 nến" narrated
       the plumbing to someone who only wanted the chart. Nam called it
       unprofessional, and it is: how many rows a backfill fetched is not a
       thing a reader acts on. The mark says "wait" and nothing else. */
    loading.hidden = false;
    try {
      const report = await API.backfill({
        symbols: [symbol],
        timeframes: [timeframe],
      });
      return report.total_rows > 0;
    } catch (err) {
      if (isActive()) setStatus(L(`Không bù được dữ liệu: ${err.message}`,
                  `Could not fill the missing bars: ${err.message}`), 'error');
      return false;
    } finally {
      catchingUp = false;
    }
  }

  // ---------- Trade markers ----------
  //
  // Backtests and paper sessions draw on the same candles, so whichever was
  // asked for last owns them rather than the two fighting over the chart.

  let markerSource = 'backtest';

  function drawPaperMarkers() {
    if (markerSource !== 'paper') return;

    const session = (Paper.sessions || []).find(
      (s) => s.symbol === state.symbol && s.timeframe === state.timeframe,
    );
    if (!session) {
      ChartManager.clearTradeMarkers();
      return;
    }

    // A running session usually holds a position: an entry with no exit yet.
    // Without it a live session looks like it had never traded.
    const open = session.position !== 0 && session.entry_time
      ? { side: session.position, entry_time: session.entry_time }
      : null;
    ChartManager.setTradeMarkers(session.trades || [], open);
  }

  /* Horizontal lines for the open position, which the arrows cannot give.

     An arrow marks where a trade started. Someone holding a position wants to
     know where it stands against the levels that will close it, and that is a
     line across the chart at a price, not a marker three hundred bars back.

     Unlike the markers, this does NOT wait for the Paper panel to be open.
     Markers are history and belong to whatever the user last ran; an open
     position is the present, and hiding it behind a panel means placing an
     order and then seeing nothing on the chart you placed it from. */
  /* How much is on, in units the reader recognises.

     Whole contracts when the contract model is running, and the account-unit
     quantity otherwise. It used to print the raw number to six decimals
     ("SHORT 5.130797"), which is neither a contract count nor a readable size
     — and on a future it is the fractional figure the contract model exists to
     replace. */
  function positionSize(session) {
    if (Number.isFinite(session.contracts)) {
      return `${Fmt.number(session.contracts, 0)} ${
        L('HĐ', session.contracts === 1 ? 'contract' : 'contracts')}`;
    }
    const quantity = Math.abs(Number(session.quantity) || 0);
    return Fmt.number(quantity, quantity >= 1 ? 2 : 6);
  }

  function drawPositionLines() {
    const session = (Paper.sessions || []).find(
      (s) => s.symbol === state.symbol && s.timeframe === state.timeframe
             && s.active && s.position !== 0,
    );
    if (!session) {
      ChartManager.clearPositionLines();
      paperLevelSession = null;
      return;
    }
    ChartManager.setPositionLines({
      side: session.position,
      entry: session.entry_price,
      stop: session.stop_loss,
      target: session.take_profit,
      entryTime: session.entry_time,
      // A magnitude: the snapshot keeps direction in `position`, and the chart
      // takes the sign from `side` above (charts.js, signedQuantity).
      quantity: Math.abs(Number(session.quantity) || 0),
      unit: Paper.currencyFor(session.symbol),
      label: `${session.position > 0 ? 'LONG' : 'SHORT'} ${positionSize(session)}`,
    });
    paperLevelSession = session.id;
  }

  // Which session the lines on the chart belong to, so a drag amends that one.
  let paperLevelSession = null;

  /* A stop or target moved, created or removed on the chart (charts.js).

     Sent once, on release. `price` is null when a level was dropped back onto
     the entry line. Only the dragged level changes; the other goes as the
     server has it. A refusal puts the lines back where the server still has
     them rather than leaving the chart showing a level that was never
     accepted. */
  function bindLevelDrag() {
    ChartManager.onLevelDragged = onLevelDragged;
    ChartManager.onPositionClose = closePaperPosition;
  }

  /* The close button on the position chip. The same action as "Đóng vị thế"
     on the ticket, placed where the position is being watched. Locked while
     the order is in flight, so a double click cannot send two. */
  let closingPosition = false;
  async function closePaperPosition() {
    const session = (Paper.sessions || []).find((s) => s.id === paperLevelSession);
    if (!session || closingPosition) return;
    closingPosition = true;
    try {
      const result = await API.paperOrder(session.id, 'close');
      Paper.apply(result.snapshot);
      drawPaperMarkers();
      drawPositionLines();
      toast(L('Đã đóng vị thế', 'Position closed'));
    } catch (err) {
      toast(tp(err.detail?.message) || err.message, true);
    } finally {
      closingPosition = false;
    }
  }

  /* A session in the Paper panel opens its own chart in the working cell: its
     symbol, its timeframe, and its position lines or closed trades. The layout
     and the open panel stay as they are. */
  function openPaperSession(session) {
    markerSource = 'paper';
    if (session.symbol === state.symbol && session.timeframe === state.timeframe) {
      drawPaperMarkers();
      drawPositionLines();
      return;
    }
    if (session.symbol === state.symbol) {
      const button = [...el.timeframes.children].find((b) => b.textContent.trim() === session.timeframe);
      if (button) button.click();
      return;
    }
    if (![...el.symbol.options].some((o) => o.value === session.symbol)) {
      toast(L(`${session.symbol} chưa có trong danh sách mã; thử lại khi danh sách tải xong.`,
              `${session.symbol} is not in the symbol list yet; try again once it has loaded.`), true);
      return;
    }
    // Frame first: the symbol handler keeps it when the market offers it, so
    // the chart loads once rather than twice.
    state.timeframe = session.timeframe;
    el.symbol.value = session.symbol;
    el.symbol.dispatchEvent(new Event('change', { bubbles: true }));
  }

  async function onLevelDragged(which, price) {
    if (!paperLevelSession) return;
    const session = (Paper.sessions || []).find((s) => s.id === paperLevelSession);
    if (!session) return;

    const exits = {
      stopLoss: which === 'stop' ? price : (session.stop_loss ?? null),
      takeProfit: which === 'target' ? price : (session.take_profit ?? null),
    };
    const name = which === 'stop' ? L('cắt lỗ', 'stop') : L('chốt lời', 'target');
    const at = price === null ? '' : price.toLocaleString('en-US', { maximumFractionDigits: 2 });
    try {
      await API.paperExits(session.id, exits);
      await Paper.refresh();
      drawPositionLines();
      toast(price === null
        ? L(`Đã gỡ ${name}`, `Removed the ${name}`)
        : L(`Đã đặt ${name} ở ${at}`, `Set the ${name} at ${at}`));
    } catch (err) {
      // A refusal carries {code, message:{vi,en}}: show the text, never match on it (§2.4).
      toast(tp(err.detail?.message) || err.message, true);
      drawPaperMarkers();
      drawPositionLines();
    }
  }


  /* The marker controls appear only once something has drawn markers, and go
     away when nothing has. A permanently visible "hide markers" button on an
     empty chart is a control for a state that does not exist. */
  function paintMarkerTools(count, visible) {
    el.chartTools.hidden = count === 0;
    el.toggleMarkers.textContent = t('chart.markers', { n: count });
    el.toggleMarkers.classList.toggle('off', !visible);
    el.toggleMarkers.title = t(visible ? 'chart.hideMarkers' : 'chart.showMarkers');
  }

  function setupMarkerControls() {
    ChartManager.onMarkersChanged = paintMarkerTools;

    el.toggleMarkers.addEventListener('click', () => {
      const visible = ChartManager.toggleMarkers();
      toast(t(visible ? 'chart.markersShown' : 'chart.markersHidden'));
    });

    el.clearMarkers.addEventListener('click', () => {
      ChartManager.clearTradeMarkers();
      // Otherwise the next paper refresh redraws what was just cleared.
      markerSource = 'none';
      toast(t('chart.markersGone'));
    });
  }


  // ---------- Plugin format help ----------
  //
  // Imported files must match a shape, and teammates who did not build this
  // have no way to know it. The template is shown where the import button is,
  // and can be downloaded as a working file to edit rather than retyped.

  const TEMPLATES = {
    indicator: {
      title: 'Định dạng chỉ báo',
      filename: 'chi_bao_mau.py',
      intro:
        'File cần đúng hai thứ: một dict <code>INDICATOR</code> mô tả chỉ báo, ' +
        'và một hàm <code>calculate(df, params)</code> trả về giá trị. ' +
        'Không cần import gì ngoài thư viện bạn dùng.',
      notes: [
        ['<code>type</code>', '<code>"overlay"</code> nếu cùng thang giá (EMA, Bollinger); <code>"panel"</code> nếu khác thang (RSI, MACD)'],
        ['<code>params</code>', 'Mỗi tham số thành một thanh trượt. Kiểu: <code>int</code>, <code>float</code>, <code>bool</code>'],
        ['<code>outputs</code>', 'Mỗi phần tử là một đường vẽ. <code>key</code> phải khớp key trả về'],
        ['<code>df</code>', 'DataFrame có <code>open, high, low, close, volume</code>, index là thời gian UTC'],
        ['Trả về', 'dict <code>{key: Series}</code>, hoặc một Series / DataFrame'],
      ],
      code: `"""Chỉ báo mẫu: copy file này, đổi tên rồi sửa logic."""

INDICATOR = {
    "name": "Kênh giá của tôi",
    "type": "overlay",          # "overlay" đè lên nến | "panel" khung riêng
    "category": "custom",
    "description": "Kênh cao/thấp N nến.",
    "params": {
        "length": {"type": "int", "default": 20, "min": 2, "max": 200,
                   "label": "Số nến"},
        "show_mid": {"type": "bool", "default": True, "label": "Vẽ đường giữa"},
    },
    "outputs": [
        {"key": "upper", "label": "Trên",  "color": "#12805c"},
        {"key": "mid",   "label": "Giữa",  "color": "#949ca6"},
        {"key": "lower", "label": "Dưới",  "color": "#c8372d"},
    ],
}


def calculate(df, params):
    n = params["length"]
    upper = df["high"].rolling(n).max()
    lower = df["low"].rolling(n).min()
    mid = (upper + lower) / 2
    if not params["show_mid"]:
        mid = mid * float("nan")
    return {"upper": upper, "mid": mid, "lower": lower}
`,
    },
    strategy: {
      title: 'Định dạng chiến lược',
      filename: 'chien_luoc_mau.py',
      intro:
        'File cần một dict <code>STRATEGY</code> và một hàm ' +
        '<code>signals(df, params)</code> trả về Series gồm <code>1</code> (long), ' +
        '<code>-1</code> (short) hoặc <code>0</code> (đứng ngoài) cho mỗi nến.',
      notes: [
        ['<code>side</code>', '<code>"long"</code>, <code>"short"</code> hoặc <code>"both"</code>: tín hiệu ngược chiều sẽ bị bỏ'],
        ['Trả về', '<code>pd.Series</code> cùng độ dài với <code>df</code>, giá trị 1 / -1 / 0'],
        ['Nhân quả', 'Giá trị tại nến <em>i</em> chỉ được dùng dữ liệu tới lúc nến <em>i</em> đóng'],
        ['Khớp lệnh', 'Engine khớp ở <strong>giá mở nến kế tiếp</strong>, nên bạn không thể vô tình dùng giá chưa xảy ra'],
        ['Khởi động', 'Đặt 0 cho khoảng đầu khi chỉ báo chưa đủ dữ liệu'],
      ],
      code: `"""Chiến lược mẫu: copy file này, đổi tên rồi sửa logic."""

import pandas as pd

STRATEGY = {
    "name": "Vượt đỉnh N nến",
    "side": "both",             # "long" | "short" | "both"
    "description": "Mua khi vượt đỉnh, bán khi thủng đáy.",
    "params": {
        "lookback": {"type": "int", "default": 20, "min": 5, "max": 200,
                     "label": "Số nến nhìn lại"},
    },
}


def signals(df, params):
    n = params["lookback"]
    # shift(1): đỉnh/đáy của N nến TRƯỚC, không tính nến hiện tại.
    highest = df["high"].rolling(n).max().shift(1)
    lowest = df["low"].rolling(n).min().shift(1)

    out = pd.Series(0, index=df.index, dtype="int8")
    out[df["close"] > highest] = 1
    out[df["close"] < lowest] = -1

    out.iloc[:n] = 0            # cửa sổ khởi động: đứng ngoài
    return out
`,
    },
  };

  let currentTemplate = null;

  function showFormatHelp(kind) {
    const tpl = TEMPLATES[kind];
    if (!tpl) return;
    currentTemplate = tpl;

    el.formatFoot.hidden = false;
    document.getElementById('format-title').textContent = tpl.title;
    el.formatBody.innerHTML =
      `<p class="hint">${tpl.intro}</p>` +
      `<pre class="code-block"><code>${tpl.code
        .replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c])}</code></pre>` +
      '<table class="data-table format-notes"><tbody>' +
      tpl.notes.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('') +
      '</tbody></table>' +
      '<p class="hint">Nếu file sai định dạng, nền tảng từ chối kèm lý do và ' +
      '<strong>không ghi vào đĩa</strong>: thư mục của bạn không bao giờ lẫn file hỏng.</p>';

    el.formatDialog.hidden = false;
  }

  /* The gear: one box for how the platform reads and what a derivative costs.
     Controls write through as they change (settings.js), so this only has to
     open the box and apply what came back.

     A timezone change rebuilds the series, because the offset is baked into
     each point when the chart is fed; the grid, the separators and the profit
     mode are applied where they show without refetching anything. */
  let shownTimezone = null;

  function applySettings() {
    const badge = document.querySelector('.tz-badge');
    if (badge) badge.textContent = Settings.timezoneLabel();
    ChartManager.applyDisplay();
    Strategy.refreshView();
    Paper.refresh();
    const timezone = Settings.all().display.timezone;
    const moved = shownTimezone !== null && shownTimezone !== timezone;
    shownTimezone = timezone;
    if (moved) loadCandles();
  }

  function setupTeamModels() {
    const dialog = document.getElementById('team-dialog');
    if (!dialog) return;
    Team.init({ root: document.getElementById('team-body'), onToast: toast });
    const close = () => { dialog.hidden = true; };
    document.getElementById('team-open')?.addEventListener('click', () => {
      dialog.hidden = false;
      Team.open();
    });
    document.getElementById('team-close')?.addEventListener('click', close);
    dialog.addEventListener('click', (event) => {
      if (event.target === dialog) close();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !dialog.hidden) close();
    });
  }

  function setupSettings() {
    const dialog = document.getElementById('settings-dialog');
    const body = document.getElementById('settings-body');
    const close = () => { dialog.hidden = true; };
    document.getElementById('settings-open')?.addEventListener('click', () => {
      Settings.panel(body);
      dialog.hidden = false;
    });
    document.getElementById('settings-close')?.addEventListener('click', close);
    dialog?.addEventListener('click', (event) => {
      if (event.target === dialog) close();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && dialog && !dialog.hidden) close();
    });
    document.getElementById('settings-reset')?.addEventListener('click', () => {
      Settings.reset();
      Settings.panel(body);
    });
    applySettings();
    Settings.subscribe(applySettings);
  }

  function setupFormatHelp() {
    for (const btn of document.querySelectorAll('[data-format-help]')) {
      btn.addEventListener('click', () => showFormatHelp(btn.dataset.formatHelp));
    }
    el.formatClose.addEventListener('click', () => { el.formatDialog.hidden = true; });
    el.formatDialog.addEventListener('click', (e) => {
      if (e.target === el.formatDialog) el.formatDialog.hidden = true;
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') el.formatDialog.hidden = true;
    });

    el.formatDownload.addEventListener('click', () => {
      if (!currentTemplate) return;
      const blob = new Blob([currentTemplate.code], { type: 'text/x-python;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = currentTemplate.filename;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast(`Đã tải ${currentTemplate.filename}`);
    });

    el.formatCopy.addEventListener('click', async () => {
      if (!currentTemplate) return;
      try {
        await navigator.clipboard.writeText(currentTemplate.code);
        toast('Đã sao chép mã mẫu');
      } catch {
        toast('Trình duyệt chặn sao chép, hãy dùng nút Tải file mẫu.', true);
      }
    });
  }

  // ---------- Compare picker ----------

  function renderComparePicker() {
    const specs = Strategy.catalog || [];
    if (!specs.length) {
      el.compareList.innerHTML = '<p class="empty">Chưa có chiến lược nào.</p>';
      return;
    }
    el.compareList.innerHTML = specs
      .map(
        (s) => `<label class="compare-item">
          <input type="checkbox" data-compare="${s.id}" checked />
          <span>${s.name}</span>
        </label>`,
      )
      .join('');
  }


  // ---------- Explaining an indicator or strategy ----------
  //
  // Every entry carries its own explanation from the backend: a curated
  // Vietnamese one where we wrote it, the library docstring otherwise, and for
  // a plugin the file's own docstring (which is the only place the author
  // could have put it.

  function explain(spec) {
    if (!spec) return;
    currentTemplate = null;                 // this dialog has nothing to download

    const help = spec.help || {};
    const esc = (v) => String(v ?? '').replace(
      /[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' })[c]);

    let html = '';
    if (help.what) {
      html += `<div class="help-section">
        <div class="help-label">Đo cái gì</div>
        <p class="help-text">${esc(help.what)}</p></div>`;
    }
    if (help.how) {
      html += `<div class="help-section">
        <div class="help-label">Đọc thế nào</div>
        <p class="help-text">${esc(help.how)}</p></div>`;
    }
    if (help.watch) {
      html += `<div class="help-section watch">
        <div class="help-label">Cần lưu ý</div>
        <p class="help-text">${esc(help.watch)}</p></div>`;
    }
    if (!html) {
      html = '<p class="empty">Chỉ báo này chưa có mô tả.</p>';
    }

    if (spec.params?.length) {
      html += '<div class="help-section"><div class="help-label">Tham số</div>' +
        '<table class="data-table help-params"><tbody>' +
        spec.params.map((prm) => {
          const range = prm.min !== null && prm.max !== null
            ? ` (${prm.min}–${prm.max})` : '';
          return `<tr><td>${esc(prm.name)}</td><td>${esc(prm.label)} (mặc định
            <strong>${esc(prm.default)}</strong>${range}</td></tr>`;
        }).join('') +
        '</tbody></table></div>';
    }

    if (spec.outputs?.length) {
      html += `<div class="help-section"><div class="help-label">Đường vẽ</div>
        <p class="help-text">${spec.outputs.map((o) => esc(o.label)).join(' · ')}</p></div>`;
    }

    const origin = {
      curated: 'Mô tả do nền tảng viết.',
      docstring: 'Lấy từ tài liệu gốc của thư viện hoặc của file.',
      none: '',
    }[help.source] || '';
    if (origin) html += `<div class="help-source">${origin}</div>`;

    document.getElementById('format-title').textContent = spec.name;
    el.formatBody.innerHTML = html;
    el.formatFoot.hidden = true;            // nothing to download or copy here
    el.formatDialog.hidden = false;
  }

  // ---------- Stars ----------

  function refreshStars() {
    const symbolOn = Favourites.has('symbol', state.symbol);
    el.starSymbol.textContent = symbolOn ? '★' : '☆';
    el.starSymbol.classList.toggle('on', symbolOn);

    const strategyId = document.getElementById('strategy-select').value;
    const strategyOn = Favourites.has('strategy', strategyId);
    el.starStrategy.textContent = strategyOn ? '★' : '☆';
    el.starStrategy.classList.toggle('on', strategyOn);
  }

  function setupStars() {
    el.starSymbol.addEventListener('click', () => {
      Favourites.toggle('symbol', state.symbol);
      refreshStars();
      rebuildSymbolOptions();               // starred symbols move to the top
    });

    el.starStrategy.addEventListener('click', () => {
      Favourites.toggle('strategy', document.getElementById('strategy-select').value);
      refreshStars();
    });

    el.infoStrategy.addEventListener('click', () => {
      const id = document.getElementById('strategy-select').value;
      explain((Strategy.catalog || []).find((s) => s.id === id));
    });
  }

  // ---------- Notifications ----------

  async function setupNotify() {
    const label = document.getElementById('notify-status');
    const tokenInput = document.getElementById('notify-token');
    const chatInput = document.getElementById('notify-chat');
    const saveButton = document.getElementById('notify-save');
    const testButton = document.getElementById('notify-test');
    const clearButton = document.getElementById('notify-clear');

    Explain.define('notify.telegram', {
      title: 'Thông báo Telegram',
      what: 'Mỗi khi một phiên paper trading vào lệnh, đóng lệnh hoặc bị thanh lý, nền tảng gửi một tin nhắn tới chat của bạn.',
      how: '1. Nhắn cho @BotFather trên Telegram, gõ /newbot, đặt tên: nó trả về một token dạng 123456789:AA…\n'
        + '2. Nhắn một câu bất kỳ cho chính bot vừa tạo.\n'
        + '3. Mở https://api.telegram.org/bot<TOKEN>/getUpdates và lấy giá trị message.chat.id.\n'
        + '4. Dán cả hai vào đây rồi bấm Lưu.',
      watch: 'Nút Lưu chỉ kiểm tra được token có hợp lệ hay không. Chat id sai vẫn qua được bước đó mà không tin nào tới nơi, nên sau khi lưu hãy bấm "Gửi tin thử" một lần.',
      source: 'Token được ghi vào .env trên máy này. WhatsApp không có ở đây vì nó đòi tài khoản Business, xét duyệt mẫu tin và một nhà cung cấp trung gian.',
    });

    /** Paint the panel from a status payload. */
    function apply(status) {
      // The token box is a password field that never receives the real token:
      // the server only ever returns a masked form, so the placeholder shows
      // what is stored and an empty box means "leave it alone".
      tokenInput.value = '';
      tokenInput.placeholder = status.bot_token_masked || '123456789:AA…';
      chatInput.value = status.chat_id || '';

      if (status.reachable) {
        label.innerHTML = t('tg.on', { bot: status.bot_username });
      } else {
        label.textContent = status.message || t('tg.off');
      }
      clearButton.disabled = !status.bot_token_masked;
    }

    async function refresh() {
      try {
        apply(await API.notifyStatus());
      } catch (err) {
        label.textContent = err.message;
      }
    }

    await refresh();

    saveButton.addEventListener('click', () =>
      withButton(saveButton, t('tg.saving'), async () => {
        const token = tokenInput.value.trim();
        const chatId = chatInput.value.trim();
        if (!token) {
          toast(t('tg.needToken'), true);
          return;
        }
        if (!chatId) {
          toast(t('tg.needChat'), true);
          return;
        }
        apply(await API.notifySave({ botToken: token, chatId }));
        toast(t('tg.saved'));
      }));

    testButton.addEventListener('click', () =>
      withButton(testButton, t('tg.sending'), async () => {
        await API.notifyTest();
        toast(t('tg.sent'));
      }));

    clearButton.addEventListener('click', () =>
      withButton(clearButton, t('tg.clearing'), async () => {
        apply(await API.notifyClear());
        toast(t('tg.cleared'));
      }));
  }

  /* The language switch.
   *
   * Static markup is rewritten by `I18n.apply`. Anything a module rendered
   * into innerHTML is not (the dictionary lookup already happened) so each
   * panel redraws itself. Panels with nothing on screen redraw to the same
   * empty state, which costs nothing and keeps this list honest: every panel
   * is here, so a new one is not silently left in the old language.
   */
  function setupLanguage() {
    const paint = () => {
      for (const button of document.querySelectorAll('.lang-btn')) {
        button.classList.toggle('active', button.dataset.lang === I18n.lang);
        button.setAttribute('aria-pressed', String(button.dataset.lang === I18n.lang));
      }
    };

    for (const button of document.querySelectorAll('.lang-btn')) {
      button.addEventListener('click', () => I18n.set(button.dataset.lang));
    }

    I18n.onChange(() => {
      paint();
      refreshStatus();
      setLiveState({ state: lastLiveState });
      Indicators.rerender?.();
      Strategy.rerender?.();
      Paper.rerender?.();
      Validation.rerender?.();
      Report.rerender?.();
      Portfolio.rerender?.();
      ChartManager.refreshSize();
    });

    paint();
  }


  // ---------- Navigation ----------

  /** Open a panel. `toggle` is for the rail, where clicking the open one closes
      it; everything else (a sub-tab, a finished backtest) only ever opens. */
  function openPanel(name, { toggle = false } = {}) {
    const host = el.panelHost;
    const current = document.querySelector('.rail-btn.active')?.dataset.panel;

    if (toggle && current === name && !host.classList.contains('collapsed')) {
      host.classList.add('collapsed');      // clicking the open one closes it
      for (const btn of document.querySelectorAll('.rail-btn')) btn.classList.remove('active');
      ChartManager.refreshSize();           // the chart just gained the space
      Session.patch({ panel: null });
      return;
    }
    Session.patch({ panel: name });

    host.classList.remove('collapsed');
    for (const btn of document.querySelectorAll('.rail-btn')) {
      btn.classList.toggle('active', btn.dataset.panel === name);
    }
    for (const panel of document.querySelectorAll('.panel')) {
      panel.classList.toggle('active', panel.dataset.panel === name);
    }
    ChartManager.refreshSize();

    if (name === 'paper') {
      markerSource = 'paper';
      Paper.refresh().then(() => { drawPaperMarkers(); drawPositionLines(); });
    }
  }

  function setupNavigation() {
    for (const btn of document.querySelectorAll('.rail-btn')) {
      btn.addEventListener('click', () => openPanel(btn.dataset.panel, { toggle: true }));
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
    let allowed = allowedTimeframes(state.symbol);

    /* Before the Vietnamese catalogue arrives every VN symbol looks daily-only
       (`timeframesFor` has nothing else to offer yet). Clamping then threw a
       restored session's 15m back to 1d on every reload. Until the catalogue
       says otherwise, the chosen frame is trusted; `loadVnSymbols` rebuilds
       these buttons when it lands and corrects a frame that truly is absent. */
    if (isVN(state.symbol) && !markets.vn && state.timeframe && !allowed.includes(state.timeframe)) {
      allowed = [...allowed, state.timeframe];
    }

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
        // A new timeframe is a new series, so the percentage restarts with it.
        hidePrice();
        // The multi-market run follows the chart, so its note must follow too.
        Markets.refreshTimeframeNote();
        for (const b of el.timeframes.children) b.classList.toggle('active', b === button);
        loadCandles();
      });
      el.timeframes.appendChild(button);
    }
  }

  async function withButton(button, label, work) {
    const original = button.textContent;
    const cell = MultiChart.activeCell;
    const loading = cell?.loading || el.loading;
    const loadToken = cell?.loadToken;
    button.disabled = true;
    button.textContent = label;
    loading.hidden = false;
    try {
      await work();
    } catch (err) {
      toast(err.message, true);
    } finally {
      button.disabled = false;
      button.textContent = original;
      if (cell?.loadToken === loadToken) loading.hidden = true;
    }
  }

  // ---------- Boot ----------

  // ---------- Splash ----------
  //
  // It covers the gap before the chart has data. Each boot step names itself,
  // so a slow first load reads as progress rather than a stalled animation.

  const splash = document.getElementById('splash');
  const bootedAt = Date.now();

  function splashSay(message) {
    // Logo-only splash screen: ignore loading status texts
  }

  function dismissSplash() {
    if (!splash) return;
    // Let the mark finish drawing even when the data arrives instantly;
    // a splash that flickers away mid-stroke looks like a glitch.
    const elapsed = Date.now() - bootedAt;
    /* Long enough for the animation to finish rather than be interrupted.

       The mark draws for 0.78s, the name fades in at 0.72s, the bar appears at
       0.85s and the credit at 1.05s — so at 1 250 ms the last element was
       still fading in as the whole screen began to leave. Boot now takes about
       100 ms of that (the slow requests moved off the critical path), which
       means the splash is almost always waiting anyway; waiting for the right
       length is free. */
    const wait = Math.max(0, 2100 - elapsed);
    setTimeout(() => {
      splash.classList.add('done');
      setTimeout(() => splash.remove(), 600);
    }, wait);
  }

  /* Resolves when the Vietnamese catalogue has arrived or failed. The splash
     waits on it (see the end of `start`). */
  let vnReady = Promise.resolve();

  /* How long the opening screen will wait for data before letting the user in
     anyway. The VN database sits behind a VPN; when the VPN is off its request
     can take the backend's full timeout to fail, and a splash that never
     leaves is worse than an app that opens and says what is missing. */
  const SPLASH_CAP_MS = 20000;

  async function start() {
    // Language first: everything below reads from the dictionary, and a panel
    // built before the language is known would render in the wrong one and
    // only correct itself on the next redraw.
    I18n.init();
    setupLanguage();
    Workspace.init();
    // Then the popover: every panel emits (i) buttons, and they are inert
    // until it is listening.
    Explain.init();
    Report.init({ onToast: toast });
    PaperDash.init({ onToast: toast });
    Editor.init({
      onToast: toast,
      // Refresh the saved plugin's catalogue through the same path as import.
      onSaved: async (report) => {
        if (report.kind === 'indicator') Indicators.setCatalog(await API.catalog());
        else await Strategy.load();
      },
    });
    for (const button of document.querySelectorAll('[data-write]')) {
      button.addEventListener('click', () => Editor.open({ kind: button.dataset.write }));
    }
    Markets.init({
      elements: {
        add: document.getElementById('mm-add'),
        addCurrent: document.getElementById('mm-add-current'),
        chosen: document.getElementById('mm-chosen'),
        run: document.getElementById('run-markets'),
        note: document.getElementById('mm-timeframe-note'),
        output: document.getElementById('markets-output'),
      },
      context: () => ({ symbol: state.symbol, timeframe: state.timeframe }),
      withButton,
      onToast: toast,
      onShowOutput: () => showResults('markets'),
    });
    setupMarkerControls();
    ChartManager.init(el.chartMain);
    // History paging is wired per chart when the grid adopts this one
    // (configureCell).
    // Dividers change the chart's box, so the charts re-measure on every drag.
    Resizer.init({ onChange: () => ChartManager.refreshSize() });
    setupNavigation();
    setupImport();
    setupFormatHelp();
    setupSettings();
    setupTeamModels();
    setupStars();
    setupNotify();
    /* Telegram settings open as a dialog now (see index.html): they are a
       global notification setting, not part of a paper session. */
    const notifyDialog = document.getElementById('notify-dialog');
    document.getElementById('notify-open')?.addEventListener('click', () => {
      notifyDialog.hidden = false;
    });
    document.getElementById('notify-close')?.addEventListener('click', () => {
      notifyDialog.hidden = true;
    });
    notifyDialog?.addEventListener('click', (event) => {
      if (event.target === notifyDialog) notifyDialog.hidden = true;
    });

    Portfolio.init({
      elements: {
        rows: document.getElementById('pf-rows'),
        add: document.getElementById('pf-add'),
        cash: document.getElementById('pf-cash'),
        horizon: document.getElementById('pf-horizon'),
        lookback: document.getElementById('pf-lookback'),
        run: document.getElementById('pf-run'),
        paper: document.getElementById('pf-paper'),
        count: document.getElementById('pf-count'),
        message: document.getElementById('pf-message'),
        datalist: document.getElementById('pf-symbols'),
      },
      onToast: toast,
      withButton,
    });

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
      onExplain: explain,
      onChange: () => {
        Session.patch({ indicators: Indicators.snapshot() });
        MultiChart.syncActive();
      },
      onNotice: (message) => toast(message),
    });

    Strategy.init({
      onChange: () => {
        const snap = Strategy.snapshot();
        if (snap) Session.patch({ strategy: snap });
        // The Optimise, Monte Carlo and Statistics panels name the strategy
        // they will run, since it is chosen in a different panel.
        for (const node of document.querySelectorAll('[data-strategy-name]')) {
          node.textContent = Strategy.selected?.name || '—';
        }
      },
      elements: {
        select: document.getElementById('strategy-select'),
        desc: document.getElementById('strategy-desc'),
        count: document.getElementById('strategy-count'),
        errors: document.getElementById('strategy-errors'),
        params: document.getElementById('strategy-params'),
        sweep: document.getElementById('sweep-ranges'),
        metric: document.getElementById('opt-metric'),
        // The backtest window, shared by every run the strategy panel starts.
        startDate: document.getElementById('bt-start'),
        endDate: document.getElementById('bt-end'),
        periodNote: document.getElementById('bt-period-note'),
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
      context: () => ({ ...state, manager: ChartHub.active, cell: MultiChart.activeCell,
        loadToken: MultiChart.activeCell?.loadToken }),
      onSelect: refreshStars,
      onResult: (result, ctx) => {
        if (ctx.cell?.destroyed || ctx.cell?.loadToken !== ctx.loadToken
            || ctx.manager.seriesKey !== `${ctx.symbol}|${ctx.timeframe}`) return;
        if (ChartHub.active === ctx.manager) markerSource = 'backtest';
        ctx.manager.setTradeMarkers(result.trades);
      },
    });

    Paper.init({
      elements: {
        list: document.getElementById('paper-sessions'),
        refresh: document.getElementById('refresh-paper'),
        startManual: document.getElementById('start-manual'),
        dash: document.getElementById('paper-dash'),
        // A hand-traded session opens on whatever the chart is showing.
        context: () => ({ symbol: state.symbol, timeframe: state.timeframe }),
        onOpenSession: openPaperSession,
        // The settings dialog: a paper session's costs are its own, not the
        // backtest panel's, and they are frozen once the session starts.
        settings: {
          root: document.getElementById('paper-settings'),
          close: document.getElementById('paper-settings-close'),
          preset: document.getElementById('ps-preset'),
          currency: document.getElementById('ps-currency'),
          capital: document.getElementById('ps-capital'),
          size: document.getElementById('ps-size'),
          leverage: document.getElementById('ps-leverage'),
          fee: document.getElementById('ps-fee'),
          slippage: document.getElementById('ps-slippage'),
          summary: document.getElementById('ps-summary'),
          warning: document.getElementById('ps-warning'),
          start: document.getElementById('ps-start'),
          copy: document.getElementById('ps-copy'),
        },
        // "Lấy từ backtest" copies whatever the backtest panel currently holds.
        backtestExecution: () => Strategy.execution(),
      },
      onToast: toast,
    });

    Validation.init({
      elements: {
        strategySelect: document.getElementById('strategy-select'),
        metric: document.getElementById('opt-metric'),
        trainBars: document.getElementById('wf-train'),
        testBars: document.getElementById('wf-test'),
        purgeBars: document.getElementById('wf-purge'),
        foldMode: document.getElementById('wf-fold-mode'),
        simulations: document.getElementById('mc-sims'),
        output: document.getElementById('validation-output'), mcOutput: document.getElementById('mc-output'),
        stats: document.getElementById('stats-output'),
      },
      context: () => ({ ...state }),
      execution: () => Strategy.execution(),
      period: () => Strategy.period(),
      catalog: () => Strategy.catalog,
      onToast: toast,
    });

    Live.init({
      onCandle: onLiveCandle,
      onCandleClose: onLiveCandleClose,
      onPluginsChanged,
      onStatus: setLiveState,
      onPaperUpdate: (session) => {
        Paper.apply(session);
        drawPaperMarkers();
      drawPositionLines();
      },
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
      splashSay('Đang đọc cấu hình…');
      const config = await API.config();
      // The last session's series, when there was one.
      state.symbol = Session.saved.symbol || config.default_symbol;
      state.timeframe = Session.saved.timeframe || config.default_timeframe;
      state.limit = Number(el.limit.value);

      loadCryptoSymbols(config);
      el.symbol.value = state.symbol;
      SymbolPicker.attach(el.symbol);
      // The manual-trading button names the market on screen. It was only
      // refreshed on a symbol *change*, so at start-up it sat disabled reading
      // "pick a market first" with BTCUSDT already on the chart.
      Paper.refreshManualButton();
      SymbolPicker.attach(document.getElementById('mm-add'), {
        placeholder: () => L('Thêm thị trường…', 'Add a market…'),
      });
      buildTimeframeButtons();

      /* Everything below this line used to be awaited one after another before
         the first candle was drawn. Measured on a warm server: the VN symbol
         list alone was 2.11 s of it, for a list nobody has asked to see yet.

         Now the chart is the only thing on the critical path. The indicator
         catalogue and strategy list are fetched together rather than in
         sequence, and the VN names and paper sessions arrive whenever they
         arrive — each one merges into a screen that is already usable. */
      refreshStars();
      vnReady = loadVnSymbols();
      // An open position has to appear on the chart at start-up, not only
      // after someone opens the Paper panel.
      Paper.refresh().then(drawPositionLines);
      warnIfServerStale();
    } catch (err) {
      dismissSplash();
      setStatus(t('status.noBackend', { msg: err.message }), 'error');
      toast(t('status.noBackend', { msg: err.message }), 'bad');
      return;
    }

    el.symbol.addEventListener('change', () => {
      state.symbol = el.symbol.value;
      // The percentage is measured from the first price of the *current*
      // instrument. Without this it would keep the previous symbol's anchor
      // and report BTC's move as a percentage of a VN equity's price.
      hidePrice();
      refreshStars();
      // The paper button follows the chart, so it always names this market.
      Paper.refreshManualButton();
      buildTimeframeButtons();      // markets differ in what they offer
      loadCandles();
    });
    el.limit.addEventListener('change', () => { state.limit = Number(el.limit.value); loadCandles(); });
    setupChartType();
    setupDrawings();
    bindLevelDrag();
    setupMultiChart();
    el.modeToggle?.addEventListener('click', () => {
      setViewMode(ChartManager.mode === 'overview' ? 'trading' : 'overview');
    });

    /* Clicking the overview chart opens the detail of that market.

       The button in the header does the same thing, but reaching for a button
       to say "show me this properly" is not the gesture people have — they
       click the thing itself. Only in overview: in the working view a click on
       the chart belongs to the chart.

       A drag is not a click. The browser fires `click` after any
       press-move-release on the same element, so panning the overview into the
       past ended with the view jumping into the working mode — the gesture
       that loads history and the gesture that leaves the page were the same
       event. Press and release have to land within a few pixels of each other,
       which is what separates "I pointed at this" from "I dragged this". */
    let pressAt = null;
    el.chartStack?.addEventListener('pointerdown', (event) => {
      pressAt = { x: event.clientX, y: event.clientY };
    });
    el.chartStack?.addEventListener('pointerup', (event) => {
      if (ChartManager.mode !== 'overview' || !pressAt) { pressAt = null; return; }
      const moved = Math.hypot(event.clientX - pressAt.x, event.clientY - pressAt.y);
      pressAt = null;
      // 5px covers the wobble of a deliberate click; a pan is tens of pixels.
      if (moved <= 5) setViewMode('trading');
    });
    el.chartStack?.addEventListener('pointercancel', () => { pressAt = null; });

    el.runBacktest.addEventListener('click', () =>
      withButton(el.runBacktest, 'Đang chạy…', async () => {
        await Strategy.runBacktest();
        showResults('summary');
      }));

    el.runWalkForward.addEventListener('click', () =>
      withButton(el.runWalkForward, 'Đang chạy…', async () => {
        await Validation.runWalkForward(Strategy.sweepRanges());
        showResults('validation');
      }));

    el.runMonteCarlo.addEventListener('click', () =>
      withButton(el.runMonteCarlo, 'Đang mô phỏng…', async () => {
        await Validation.runMonteCarlo(Strategy.currentParams());
        openPanel('montecarlo');
      }));

    el.runCompare.addEventListener('click', () =>
      withButton(el.runCompare, 'Đang so sánh…', async () => {
        const entries = [...el.compareList.querySelectorAll('[data-compare]:checked')]
          .map((box) => ({ strategy_id: box.dataset.compare }));
        if (!entries.length) {
          toast('Chọn ít nhất một chiến lược.', true);
          return;
        }
        await Validation.runCompare(entries);
        showResults('validation');
      }));

    document.getElementById('run-stats-series').addEventListener('click', (e) =>
      withButton(e.currentTarget, 'Đang tính…', async () => {
        await Validation.runSeriesStats();
        openPanel('stats');
      }));

    document.getElementById('run-stats-strategy').addEventListener('click', (e) =>
      withButton(e.currentTarget, 'Đang tính…', async () => {
        await Validation.runStrategyStats(Strategy.currentParams());
        openPanel('stats');
      }));

    // The report is fetched on demand rather than with every backtest: it is
    // roughly a hundred times the payload, and most runs are never opened.
    el.openReport.addEventListener('click', () =>
      withButton(el.openReport, t('rp.building'), async () => {
        const strategy = Strategy.selected;
        if (!strategy) {
          toast(t('rp.pickStrategy'), true);
          return;
        }
        Report.open(await API.report({
          strategyId: strategy.id,
          symbol: state.symbol,
          timeframe: state.timeframe,
          limit: state.limit,
          params: Strategy.currentParams(),
          execution: Strategy.execution(),
        }));
      }));

    el.exportCsv.addEventListener('click', () => Validation.exportTrades(Strategy.lastResult));

    el.runOptimize.addEventListener('click', () =>
      withButton(el.runOptimize, 'Đang quét…', async () => {
        const result = await Strategy.runOptimize();
        if (result) openPanel('optimize');
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
        markerSource = 'paper';
        openPanel('paper');
        drawPaperMarkers();
      drawPositionLines();
        toast('Đã bắt đầu phiên paper trading');
      }));

    // Overview first: the chart is the only thing that had to be fetched to
    // get here, and it is the only thing on screen until the user asks for
    // more.
    const reopenTrading = window.location.hash === '#trade' || Session.saved.mode === 'trading';
    setViewMode(reopenTrading ? 'trading' : 'overview');
    // The panel that was open comes back open; none means the rail stays shut.
    if (reopenTrading && Session.saved.panel) openPanel(Session.saved.panel);

    /* Realtime is on from the start, for whatever symbol is open.

       It used to be off until the toggle was pressed, so the platform opened
       showing a chart that had quietly stopped at whenever the last session
       ended. A chart that is not updating and does not look any different from
       one that is, is worse than no chart. Both markets are covered: Binance
       pushes, the HOSE database is polled. */
    Live.setEnabled(true);

    /* The opening screen leaves when the data is in, not when a timer says.

       It used to leave as soon as the first chart had drawn, while the
       Vietnamese catalogue, the indicator and strategy catalogues and a
       restored session were still arriving — so the app appeared, then
       reshuffled itself as each of those landed. Nam asked for the splash to
       stay until the database has loaded. Capped, because a VPN that is off
       must not keep the door shut forever. */
    const ready = Promise.allSettled([
      loadCandles(),
      vnReady,
      ChartManager.mode === 'trading' ? loadWorkingView() : null,
    ]);
    await Promise.race([ready, new Promise((resolve) => setTimeout(resolve, SPLASH_CAP_MS))]);
    dismissSplash();
  }

  start();
})();
