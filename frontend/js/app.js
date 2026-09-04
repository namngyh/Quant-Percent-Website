/* Application wiring: loads config, candles and the indicator catalog, then
   keeps the chart in step with the controls. */

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
  };

  const state = {
    symbol: null,
    timeframe: null,
    limit: 2000,
    candleCount: 0,
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

      state.candleCount = data.count;

      if (!data.count) {
        // Drop the drawings too, or lines computed from the previous timeframe
        // would linger over an empty chart. The active list is left intact, so
        // they redraw as soon as this series has data.
        ChartManager.clearAll();
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

      await Indicators.recomputeAll();
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

    if (result.kind === 'overlay') {
      ChartManager.drawOverlay(instanceId, result);
    } else {
      ChartManager.drawPane(instanceId, result, el.panes);
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

  // ---------- Boot ----------

  async function start() {
    ChartManager.init(el.chartMain);

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

      const catalog = await API.catalog();
      Indicators.setCatalog(catalog);
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

    await loadCandles();
  }

  start();
})();
