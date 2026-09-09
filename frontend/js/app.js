/* Application wiring.

   The rail opens exactly one panel at a time, and clicking the open one closes
   it: three columns of controls competing for attention was the thing that
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
    runWalkForward: document.getElementById('run-walkforward'),
    runMonteCarlo: document.getElementById('run-montecarlo'),
    runCompare: document.getElementById('run-compare'),
    compareList: document.getElementById('compare-list'),
    openReport: document.getElementById('open-report'),
    price: document.getElementById('price'),
    chartTools: document.getElementById('chart-tools'),
    toggleMarkers: document.getElementById('toggle-markers'),
    clearMarkers: document.getElementById('clear-markers'),
    exportCsv: document.getElementById('export-csv'),
    exportPng: document.getElementById('export-png'),
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
        setStatusLive(() => t('status.noData'), 'error');
        hidePrice();
        return;
      }

      ChartManager.setCandles(data.candles, data.volumes, {
        timeVisible: INTRADAY.has(state.timeframe),
      });

      // The symbol and the timeframe are already selected two controls to the
      // left, and the price now has a readout of its own, so the status line
      // is left for the one thing neither of those shows.
      const last = data.candles[data.candles.length - 1];
      setStatusLive(() =>
        t('status.bars', { n: data.count.toLocaleString(I18n.locale()) }));
      showPrice(last.close);

      ChartManager.clearTradeMarkers();
      await Indicators.recomputeAll();
      drawPaperMarkers();
      Live.subscribe(state.symbol, state.timeframe);

      // Fill any gap left while the app was closed, then redraw including it.
      if (await catchUpIfBehind(data)) {
        await loadCandles();
      }
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
  let lastLiveState = 'offline';

  function setLiveState({ state: liveState }) {
    lastLiveState = liveState;
    const dot = { live: 'live', connecting: 'connecting', offline: 'offline' }[liveState] || '';
    el.liveDot.className = `live-dot ${dot}`;
    el.liveToggle.classList.toggle('on', liveState === 'live' || liveState === 'connecting');
    el.liveLabel.textContent = {
      live: t(isVN(state.symbol) ? 'live.watching' : 'live.running'),
      connecting: t('live.connecting'),
      offline: t('live.offline'),
      error: t('live.error'),
    }[liveState] || t('top.live');

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
    el.price.hidden = false;
    lastPrice = value;
  }

  function hidePrice() {
    el.price.hidden = true;
    el.price.classList.remove('up', 'down');
    lastPrice = null;
  }

  function onLiveCandle(candle) {
    ChartManager.updateCandle({
      time: Math.floor(candle.open_time / 1000),
      open: candle.open, high: candle.high, low: candle.low,
      close: candle.close, volume: candle.volume,
    });
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
          label: `Việt Nam · HOSE (có nến phút: ${withMinutes.length})`,
          options: withMinutes.map((s) => ({ id: s.id, text: label(s) })),
        });
      }
      if (dailyOnly.length) {
        groups.push({
          label: `Việt Nam · HOSE (chỉ nến ngày: ${dailyOnly.length})`,
          options: dailyOnly.map((s) => ({ id: s.id, text: label(s) })),
        });
      }
    } catch (err) {
      markets.vn = null;
      // Not fatal, and not silent either: say why the VN names are missing.
      setStatus(`Thị trường VN không khả dụng: ${err.message}`, 'error');
    }

    symbolGroups = groups;
    rebuildSymbolOptions();
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

  /** Live and backfill are Binance-only; say so rather than failing on click. */
  function applyMarketCapabilities() {
    const vn = isVN(state.symbol);

    el.backfill.disabled = vn;
    el.backfill.title = vn
      ? 'Dữ liệu VN đến từ database của team và chỉ đọc, không cần backfill.'
      : 'Kéo nến mới nhất từ Binance';

    // Live works for both markets, by different means: Binance pushes, the
    // HOSE database is polled. Nothing to disable here.
    el.liveToggle.disabled = false;
    el.liveToggle.title = vn
      ? 'Nến mới từ database của team, kiểm tra mỗi vài giây trong phiên'
      : 'Nến realtime từ Binance';
  }


  // ---------- Catching up ----------
  //
  // The local crypto store only advances while this app is running, so after
  // the laptop has been shut a day it is a day behind. Closing that gap is
  // mechanical (the backfill already resumes from the newest stored bar) so
  // it happens on load rather than waiting for someone to notice the hole.
  // The Vietnam database is read live and is never behind.

  const MAX_AUTO_CATCHUP_BARS = 5000;   // beyond this, ask rather than assume

  let catchingUp = false;

  async function catchUpIfBehind(data) {
    if (catchingUp || !data.can_backfill || !data.bars_behind) return false;

    if (data.bars_behind > MAX_AUTO_CATCHUP_BARS) {
      setStatus(
        `${state.symbol} ${state.timeframe}: thiếu ${data.bars_behind.toLocaleString('vi-VN')} nến, ` +
          'bấm "Cập nhật dữ liệu"',
        'busy',
      );
      return false;
    }

    catchingUp = true;
    try {
      setStatus(`Đang bù ${data.bars_behind.toLocaleString('vi-VN')} nến còn thiếu…`, 'busy');
      const report = await API.backfill({
        symbols: [state.symbol],
        timeframes: [state.timeframe],
      });
      if (report.total_rows > 0) {
        toast(`Đã tự bù ${report.total_rows.toLocaleString('vi-VN')} nến`);
        return true;
      }
      return false;
    } catch (err) {
      setStatus(`Không bù được dữ liệu: ${err.message}`, 'error');
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


  /* The marker controls appear only once something has drawn markers, and go
     away when nothing has. A permanently visible "hide markers" button on an
     empty chart is a control for a state that does not exist. */
  function setupMarkerControls() {
    ChartManager.onMarkersChanged = (count, visible) => {
      el.chartTools.hidden = count === 0;
      el.toggleMarkers.textContent = t('chart.markers', { n: count });
      el.toggleMarkers.classList.toggle('off', !visible);
      el.toggleMarkers.title = t(visible ? 'chart.hideMarkers' : 'chart.showMarkers');
    };

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
        label.innerHTML = `Đang bật qua <strong>@${status.bot_username}</strong>. `
          + 'Mỗi lần phiên paper vào hoặc đóng lệnh sẽ có tin nhắn.';
      } else {
        label.textContent = status.message || 'Chưa bật.';
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
      withButton(saveButton, 'Đang kiểm tra…', async () => {
        const token = tokenInput.value.trim();
        const chatId = chatInput.value.trim();
        if (!token) {
          toast('Dán bot token vào ô phía trên.', true);
          return;
        }
        if (!chatId) {
          toast('Thiếu chat id.', true);
          return;
        }
        apply(await API.notifySave({ botToken: token, chatId }));
        toast('Đã lưu. Bấm "Gửi tin thử" để chắc chắn chat id đúng.');
      }));

    testButton.addEventListener('click', () =>
      withButton(testButton, 'Đang gửi…', async () => {
        await API.notifyTest();
        toast('Đã gửi tin thử: kiểm tra Telegram');
      }));

    clearButton.addEventListener('click', () =>
      withButton(clearButton, 'Đang xoá…', async () => {
        apply(await API.notifyClear());
        toast('Đã xoá token khỏi máy.');
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
      ChartManager.refreshSize();           // the chart just gained the space
      return;
    }

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
      Paper.refresh().then(drawPaperMarkers);
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
    setStatusLive(() => t('status.loading'), 'busy');
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
    const wait = Math.max(0, 1250 - elapsed);
    setTimeout(() => {
      splash.classList.add('done');
      setTimeout(() => splash.remove(), 600);
    }, wait);
  }

  async function start() {
    // Language first: everything below reads from the dictionary, and a panel
    // built before the language is known would render in the wrong one and
    // only correct itself on the next redraw.
    I18n.init();
    setupLanguage();
    // Then the popover: every panel emits (i) buttons, and they are inert
    // until it is listening.
    Explain.init();
    Report.init({ onToast: toast });
    setupMarkerControls();
    ChartManager.init(el.chartMain);
    // Dividers change the chart's box, so the charts re-measure on every drag.
    Resizer.init({ onChange: () => ChartManager.refreshSize() });
    setupNavigation();
    setupImport();
    setupFormatHelp();
    setupStars();
    setupNotify();

    Portfolio.init({
      elements: {
        rows: document.getElementById('pf-rows'),
        add: document.getElementById('pf-add'),
        cash: document.getElementById('pf-cash'),
        horizon: document.getElementById('pf-horizon'),
        lookback: document.getElementById('pf-lookback'),
        run: document.getElementById('pf-run'),
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
      onSelect: refreshStars,
      onResult: (result) => {
        markerSource = 'backtest';
        ChartManager.setTradeMarkers(result.trades);
      },
    });

    Paper.init({
      elements: {
        list: document.getElementById('paper-sessions'),
        refresh: document.getElementById('refresh-paper'),
        // The settings dialog: a paper session's costs are its own, not the
        // backtest panel's, and they are frozen once the session starts.
        settings: {
          root: document.getElementById('paper-settings'),
          close: document.getElementById('paper-settings-close'),
          preset: document.getElementById('ps-preset'),
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
        output: document.getElementById('validation-output'),
        stats: document.getElementById('stats-output'),
      },
      context: () => ({ ...state }),
      execution: () => Strategy.execution(),
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
      state.symbol = config.default_symbol;
      state.timeframe = config.default_timeframe;
      state.limit = Number(el.limit.value);

      splashSay('Đang nạp danh mục mã…');
      await loadSymbolOptions(config);
      el.symbol.value = state.symbol;
      buildTimeframeButtons();
      applyMarketCapabilities();

      splashSay('Đang nạp chỉ báo và chiến lược…');
      Indicators.setCatalog(await API.catalog());
      await Strategy.load();
      renderComparePicker();
      refreshStars();
      await Paper.refresh();
    } catch (err) {
      dismissSplash();
      setStatus(`Không kết nối được backend: ${err.message}`, 'error');
      toast(`Không kết nối được backend: ${err.message}`, 'bad');
      return;
    }

    el.symbol.addEventListener('change', () => {
      state.symbol = el.symbol.value;
      refreshStars();
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

    el.runWalkForward.addEventListener('click', () =>
      withButton(el.runWalkForward, 'Đang chạy…', async () => {
        await Validation.runWalkForward(Strategy.sweepRanges());
        showResults('validation');
      }));

    el.runMonteCarlo.addEventListener('click', () =>
      withButton(el.runMonteCarlo, 'Đang mô phỏng…', async () => {
        await Validation.runMonteCarlo(Strategy.currentParams());
        showResults('validation');
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
        showResults('stats');
      }));

    document.getElementById('run-stats-strategy').addEventListener('click', (e) =>
      withButton(e.currentTarget, 'Đang tính…', async () => {
        await Validation.runStrategyStats(Strategy.currentParams());
        showResults('stats');
      }));

    // The report is fetched on demand rather than with every backtest: it is
    // roughly a hundred times the payload, and most runs are never opened.
    el.openReport.addEventListener('click', () =>
      withButton(el.openReport, 'Đang dựng…', async () => {
        const strategy = Strategy.selected;
        if (!strategy) {
          toast('Chọn một chiến lược ở tab Chiến lược trước.', true);
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
    el.exportPng.addEventListener('click', () => Validation.exportChart());

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
        markerSource = 'paper';
        openPanel('paper');
        drawPaperMarkers();
        toast('Đã bắt đầu phiên paper trading');
      }));

    await loadCandles();
    dismissSplash();
  }

  start();
})();
