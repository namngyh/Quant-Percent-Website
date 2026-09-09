/* Paper trading panel: the sessions running forward on live data.

   A session keeps trading with the browser closed, so this panel is a view of
   server state rather than the thing that owns it: everything here reads from
   /api/paper and pushes actions back. */

const Paper = (() => {
  // Matches MANUAL_STRATEGY_ID in backend/paper/engine.py: the sentinel that
  // marks a session with no strategy behind it.
  const MANUAL_STRATEGY = 'manual';

  let elements = {};
  let onToast = () => {};
  let sessions = [];
  // The request waiting on the settings dialog, if one is open.
  let pending = null;

  const money = (v) => v.toLocaleString('en-US', { maximumFractionDigits: 2 });
  const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

  function esc(value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  }

  function ago(seconds) {
    if (!seconds) return '—';
    const delta = Math.max(0, Math.floor(Date.now() / 1000) - seconds);
    if (delta < 60) return `${delta}s trước`;
    if (delta < 3600) return `${Math.floor(delta / 60)} phút trước`;
    if (delta < 86400) return `${Math.floor(delta / 3600)} giờ trước`;
    return `${Math.floor(delta / 86400)} ngày trước`;
  }

  async function refresh() {
    try {
      const data = await API.paperSessions();
      sessions = data.sessions || [];
      render();
    } catch (err) {
      onToast(err.message, true);
    }
  }

  /** Merge one session pushed over the live socket without a full refetch. */
  function apply(session) {
    const index = sessions.findIndex((s) => s.id === session.id);
    if (index >= 0) sessions[index] = session;
    else sessions.unshift(session);
    render();
  }

  /* A stable colour per symbol. Hashing the name rather than assigning from a
     list means BTCUSDT is the same colour in every session card, in every
     session, across reloads — which is the only thing that makes the badge
     worth having. The palette is fixed and readable against white text. */
  // Deliberately excludes the market green (#089981) and red (#f23645), and
  // anything close to them. This stylesheet's first rule is that green and red
  // mean direction and P&L and nothing else; a green badge beside a red P&L
  // figure is exactly the decorative use that rule exists to prevent.
  const BADGE_COLOURS = [
    '#2962ff', '#7b1fa2', '#0277bd', '#5e35b1', '#00838f',
    '#6d4c41', '#455a64', '#ad1457', '#283593', '#4e342e',
  ];

  function symbolBadge(symbol) {
    const name = String(symbol || '?');
    let hash = 0;
    for (let i = 0; i < name.length; i += 1) {
      hash = (hash * 31 + name.charCodeAt(i)) >>> 0;
    }
    const colour = BADGE_COLOURS[hash % BADGE_COLOURS.length];
    // Three characters is what fits legibly at 34px.
    const label = name.replace(/[^A-Za-z0-9]/g, '').slice(0, 3) || '?';
    return `<span class="sym-badge" style="background:${colour}"
      aria-hidden="true">${esc(label)}</span>`;
  }

  function positionPill(s) {
    if (s.position > 0) return '<span class="pill long">LONG</span>';
    if (s.position < 0) return '<span class="pill short">SHORT</span>';
    return `<span class="pill flat">${esc(L('ĐỨNG NGOÀI', 'FLAT'))}</span>`;
  }

  /* The trade ticket.

     Two buttons and a size box, sized and coloured the way an order pad is:
     buy on the left in green, sell on the right in red, the live price on both
     so you can see what you are about to pay. A manual order fills at that
     price immediately — there is no next-candle wait, because the user is
     acting on a number they can see (see backend/paper/engine.py).

     Buttons are disabled rather than hidden when an action is impossible, so
     the pad does not reshuffle under the pointer between two clicks. */
  function ticket(s) {
    if (!s.active) return '';
    const long = s.position > 0;
    const short = s.position < 0;
    const costPct = (s.config.fee * 2 + s.config.slippage * 2) * 100;

    return `<div class="ticket" data-ticket="${esc(s.id)}">
      <div class="ticket-row">
        <button class="ticket-btn buy ${long ? 'held' : ''}"
                data-order="long" data-session="${esc(s.id)}"
                ${long ? 'disabled' : ''}>
          <span class="ticket-verb">${esc(long ? L('ĐANG MUA', 'LONG') : L('MUA', 'BUY'))}</span>
          <span class="ticket-price">${money(s.last_price)}</span>
        </button>
        <button class="ticket-btn sell ${short ? 'held' : ''}"
                data-order="short" data-session="${esc(s.id)}"
                ${short ? 'disabled' : ''}>
          <span class="ticket-verb">${esc(short ? L('ĐANG BÁN', 'SHORT') : L('BÁN', 'SELL'))}</span>
          <span class="ticket-price">${money(s.last_price)}</span>
        </button>
      </div>
      <div class="ticket-row ticket-controls">
        <label class="ticket-size">
          <span>${esc(L('% vốn', '% equity'))}</span>
          <input type="number" min="1" max="100" step="1" value="${
            Math.round(s.config.size_pct * 100)}" data-size="${esc(s.id)}" />
        </label>
        <button class="btn btn-quiet btn-sm" data-order="close" data-session="${esc(s.id)}"
                ${s.position === 0 ? 'disabled' : ''}>${esc(L('Đóng vị thế', 'Close position'))}</button>
        ${s.manual_override ? `<button class="btn btn-quiet btn-sm"
          data-resume-strategy="${esc(s.id)}">${esc(L('Trả lại chiến lược', 'Back to strategy'))}</button>` : ''}
      </div>
      <div class="ticket-note">${esc(L(
        `Khớp ngay ở giá hiện tại. Mỗi vòng tốn ${costPct.toFixed(3)}% giá trị danh nghĩa.`,
        `Fills now at the live price. A round trip costs ${costPct.toFixed(3)}% of notional.`))}</div>
    </div>`;
  }

  function render() {
    if (!sessions.length) {
      elements.list.innerHTML = `<p class="empty">${L(
        'Chưa có phiên nào. Bấm <strong>Giao dịch tay</strong> ở trên để tự đặt lệnh, ' +
        'hoặc mở tab <strong>Chiến lược</strong> rồi bấm <strong>Chạy paper trading</strong>.',
        'No sessions yet. Press <strong>Manual trading</strong> above to place orders ' +
        'yourself, or open the <strong>Strategy</strong> tab and press ' +
        '<strong>Run paper trading</strong>.')}</p>`;
      return;
    }

    elements.list.innerHTML = sessions
      .map((s) => {
        const pnl = s.equity - s.config.initial_capital;
        const open = s.position !== 0;
        return `<div class="paper-card ${s.active ? '' : 'stopped'}">
          <div class="paper-card-head">
            ${symbolBadge(s.symbol)}
            <div>
              <div class="paper-name">${esc(s.is_manual
                ? L('Giao dịch tay', 'Manual trading') : s.strategy_id)}${
                s.manual_override
                  ? ` <span class="pill warn">${esc(L('CAN THIỆP TAY', 'MANUAL'))}</span>` : ''}</div>
              <div class="paper-series">${esc(s.symbol)} · ${esc(s.timeframe)} · ${
                L(`${s.bars_seen} nến`, `${s.bars_seen} bars`)}</div>
            </div>
            <div class="paper-actions">
              <span class="pill ${s.active ? 'running' : 'stopped'}">${
                esc(s.active ? L('ĐANG CHẠY', 'RUNNING') : L('ĐÃ DỪNG', 'STOPPED'))}</span>
              <button class="btn btn-quiet btn-sm" data-paper-toggle="${esc(s.id)}">${
                esc(s.active ? L('Dừng', 'Stop') : L('Chạy lại', 'Resume'))}</button>
              <button class="btn btn-quiet btn-sm btn-danger" data-paper-delete="${esc(s.id)}">✕</button>
            </div>
          </div>

          <div class="paper-body">
            <div class="paper-stat">
              <div class="paper-stat-label">${esc(L('Vốn', 'Equity'))}</div>
              <div class="paper-stat-value ${sign(pnl)}">${money(s.equity)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">${esc(L('Lợi nhuận', 'Return'))}</div>
              <div class="paper-stat-value ${sign(s.return_pct)}">${pct(s.return_pct)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">${esc(L('Vị thế', 'Position'))}</div>
              <div class="paper-stat-value">${positionPill(s)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">${esc(open
                ? L('Lãi/lỗ mở', 'Open P&L') : L('Đã đóng', 'Closed'))}</div>
              <div class="paper-stat-value ${open ? sign(s.unrealized_pnl) : ''}">${
                open ? money(s.unrealized_pnl)
                     : L(`${s.num_trades} lệnh`, `${s.num_trades} trades`)
              }</div>
            </div>
            ${
              open
                ? `<div class="paper-note">${esc(L(
                    `Vào ${money(s.entry_price)} · khối lượng ${s.quantity.toFixed(6)} · giá hiện tại ${money(s.last_price)}`,
                    `In at ${money(s.entry_price)} · size ${s.quantity.toFixed(6)} · now ${money(s.last_price)}`))}</div>`
                : ''
            }
            <div class="paper-note">${esc(L(
              `${s.num_trades} lệnh · thắng ${s.win_rate_pct.toFixed(0)}% · đã thực hiện ${money(s.realized_pnl)} · nến cuối ${ago(s.last_closed_time)}`,
              `${s.num_trades} trades · ${s.win_rate_pct.toFixed(0)}% won · realised ${money(s.realized_pnl)} · last bar ${ago(s.last_closed_time)}`))}</div>
            ${
              s.pending_signal !== s.position
                ? `<div class="paper-note">${esc(L('Chờ khớp ở nến kế tiếp: ',
                    'Waiting to fill at the next candle: '))}<strong>${esc(
                    s.pending_signal > 0 ? L('MUA', 'BUY')
                      : s.pending_signal < 0 ? L('BÁN', 'SELL') : L('ĐÓNG', 'CLOSE')
                  )}</strong></div>`
                : ''
            }
            ${ticket(s)}
          </div>
        </div>`;
      })
      .join('');

    bind();
  }

  function bind() {
    for (const btn of elements.list.querySelectorAll('[data-order]')) {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.session;
        const action = btn.dataset.order;
        const sizeInput = elements.list.querySelector(`[data-size="${CSS.escape(id)}"]`);
        const raw = Number(sizeInput?.value);
        // Omitted rather than guessed: the backend then uses the session's own
        // configured size, which is the honest default.
        const sizePct = Number.isFinite(raw) && raw > 0 ? Math.min(raw, 100) / 100 : undefined;

        // Every order button on this card locks while the fill is in flight.
        // Without it a double click books two fills and pays two sets of fees.
        const buttons = [...elements.list.querySelectorAll(
          `[data-session="${CSS.escape(id)}"]`)];
        for (const b of buttons) b.disabled = true;
        try {
          const result = await API.paperOrder(id, action, action === 'close' ? undefined : sizePct);
          apply(result.snapshot);
          const filled = (result.events || []).find((e) => e.type === 'entry');
          onToast(filled
            ? L(`Đã khớp ${filled.side === 'long' ? 'MUA' : 'BÁN'} ở ${money(filled.price)}`,
                `Filled ${filled.side === 'long' ? 'BUY' : 'SELL'} at ${money(filled.price)}`)
            : L('Đã đóng vị thế', 'Position closed'));
        } catch (err) {
          // The server sends {code, message:{vi,en}} for a refusal, so the
          // interface shows the text and never matches on it (§2.4).
          onToast(tp(err.detail?.message) || err.message, true);
          for (const b of buttons) b.disabled = false;
        }
      });
    }

    for (const btn of elements.list.querySelectorAll('[data-resume-strategy]')) {
      btn.addEventListener('click', async () => {
        btn.disabled = true;
        try {
          apply(await API.paperResumeStrategy(btn.dataset.resumeStrategy));
          onToast(L('Chiến lược điều khiển trở lại', 'The strategy is steering again'));
        } catch (err) {
          onToast(tp(err.detail?.message) || err.message, true);
          btn.disabled = false;
        }
      });
    }

    for (const btn of elements.list.querySelectorAll('[data-paper-toggle]')) {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.paperToggle;
        const session = sessions.find((s) => s.id === id);
        btn.disabled = true;
        try {
          const updated = session.active ? await API.paperStop(id) : await API.paperResume(id);
          apply(updated);
          onToast(updated.active ? L('Đã chạy lại phiên', 'Session resumed')
                                 : L('Đã dừng phiên', 'Session stopped'));
        } catch (err) {
          onToast(err.message, true);
        }
      });
    }

    for (const btn of elements.list.querySelectorAll('[data-paper-delete]')) {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.paperDelete;
        // Deleting throws away the whole trade history, so make it deliberate.
        if (!window.confirm(L('Xóa phiên này? Toàn bộ lịch sử lệnh sẽ mất.',
          'Delete this session? Its whole trade history goes with it.'))) return;
        try {
          await API.paperDelete(id);
          sessions = sessions.filter((s) => s.id !== id);
          render();
          onToast('Đã xóa phiên');
        } catch (err) {
          onToast(err.message, true);
        }
      });
    }
  }

  /* ---------- Settings ----------

     Paper sessions used to borrow the backtest's cost boxes. That meant one
     control served two purposes: dropping the fee to see how a backtest would
     look also set the fee for the next live session, and once a session was
     running there was nowhere to see what it had actually started with.

     A session freezes its costs at start — the server builds its own config
     object and keeps it — so editing anything here can never disturb a running
     session. The panel now says that rather than leaving it to be discovered.

     The presets are the TradingView idea: pick where you are trading and the
     commission fills itself in, instead of remembering that Binance futures
     taker is 0.04%. */

  const PRESETS = {
    binance_futures_taker: { fee: 0.04, slippage: 0.02, leverage: 1,
      label: () => 'Binance Futures — taker',
      note: () => L('Phí taker 0,04% mỗi chiều trên giá trị danh nghĩa.',
                    'Taker fee of 0.04% per side on notional.') },
    binance_futures_maker: { fee: 0.02, slippage: 0.02, leverage: 1,
      label: () => 'Binance Futures — maker',
      note: () => L('Phí maker 0,02%. Chỉ đúng nếu lệnh của bạn thật sự nằm chờ trên sổ; chiến lược vào lệnh ở giá mở nến kế tiếp thường là taker.',
                    'Maker fee of 0.02%. Only right if your order actually rests on the book; a strategy entering at the next bar’s open is usually a taker.') },
    binance_spot: { fee: 0.1, slippage: 0.02, leverage: 1,
      label: () => 'Binance Spot',
      note: () => L('Phí spot 0,1%. Spot không có đòn bẩy — hãy để đòn bẩy bằng 1.',
                    'Spot fee of 0.1%. Spot has no leverage — leave leverage at 1.') },
    hose: { fee: 0.15, slippage: 0.05, leverage: 1,
      label: () => 'HOSE',
      note: () => L('Phí môi giới ~0,15%. Chưa gồm thuế bán 0,1% và phí lưu ký, nên chi phí thật cao hơn con số này. Cổ phiếu Việt Nam cũng không cho bán khống.',
                    'Brokerage around 0.15%. This excludes the 0.1% sell tax and custody fees, so the real cost is higher. Vietnamese equities also cannot be sold short.') },
  };

  function settingsValues() {
    const el = elements.settings || {};
    return {
      initial_capital: Number(el.capital?.value) || 10000,
      size_pct: (Number(el.size?.value) || 100) / 100,
      leverage: Number(el.leverage?.value) || 1,
      fee: (Number(el.fee?.value) || 0) / 100,
      slippage: (Number(el.slippage?.value) || 0) / 100,
    };
  }

  /* Round-trip cost is what the user actually pays, and it is not the fee:
     fees land on both sides and slippage is always adverse (§3.1). Showing it
     as one number is the difference between "0.04%" and the 0.12% a trade
     really costs before it breaks even. */
  function settingsSummary() {
    const v = settingsValues();
    const roundTrip = (v.fee * 2 + v.slippage * 2) * 100;
    const notional = v.initial_capital * v.size_pct * v.leverage;
    const perTrade = notional * roundTrip / 100;
    return L(
      `Mỗi lệnh khứ hồi tốn <strong>${roundTrip.toFixed(3)}%</strong> giá trị danh nghĩa — phí hai chiều cộng trượt giá hai chiều. Với ${money(notional)} danh nghĩa, đó là <strong>${money(perTrade)}</strong> mỗi lệnh, tức chiến lược phải kiếm hơn ngần đó mới hoà vốn.`,
      `A round trip costs <strong>${roundTrip.toFixed(3)}%</strong> of notional — fees on both sides plus adverse slippage on both. On ${money(notional)} of notional that is <strong>${money(perTrade)}</strong> per trade, which the strategy has to beat before it breaks even.`);
  }

  function applyPreset(key) {
    const preset = PRESETS[key];
    const el = elements.settings || {};
    if (!preset || !el.fee) return;
    el.fee.value = preset.fee;
    el.slippage.value = preset.slippage;
    refreshSettings();
  }

  function refreshSettings() {
    const el = elements.settings || {};
    if (!el.summary) return;
    el.summary.innerHTML = settingsSummary();

    const key = el.preset?.value;
    const v = settingsValues();
    const notes = [];
    if (PRESETS[key]) notes.push(PRESETS[key].note());
    if (key === 'binance_spot' && v.leverage > 1) {
      notes.push(L('Bạn đang đặt đòn bẩy trên spot, sàn này không có đòn bẩy.',
                   'You have set leverage on spot, which does not offer it.'));
    }
    if (key === 'hose' && v.leverage > 1) {
      notes.push(L('Đòn bẩy trên HOSE là ký quỹ margin của công ty chứng khoán, cơ chế khác hẳn mô hình thanh lý trong nến mà engine dùng.',
                   'Leverage on HOSE is broker margin, which behaves quite differently from the intrabar liquidation model the engine uses.'));
    }
    if (v.leverage >= 10) {
      notes.push(L(`Ở đòn bẩy ${v.leverage}x, một biến động bất lợi ${(100 / v.leverage).toFixed(1)}% là đủ để thanh lý — và engine kiểm tra theo giá thấp nhất trong nến, không phải giá đóng cửa.`,
                   `At ${v.leverage}x, an adverse move of ${(100 / v.leverage).toFixed(1)}% is enough to liquidate — and the engine checks the bar's low, not its close.`));
    }
    el.warning.hidden = notes.length === 0;
    el.warning.textContent = notes.join(' ');
  }

  function openSettings(request) {
    pending = request;
    const el = elements.settings || {};
    if (!el.root) return start(request);   // dialog absent: behave as before
    refreshSettings();
    el.root.hidden = false;
    el.capital?.focus();
    return null;
  }

  function closeSettings() {
    pending = null;
    if (elements.settings?.root) elements.settings.root.hidden = true;
  }

  async function confirmSettings() {
    if (!pending) return;
    const request = { ...pending, execution: settingsValues() };
    closeSettings();
    try {
      await start(request);
      onToast(L('Đã bắt đầu phiên paper trading.', 'Paper session started.'));
    } catch (err) {
      onToast(err.message, true);
    }
  }

  function copyFromBacktest() {
    const from = elements.backtestExecution?.();
    const el = elements.settings || {};
    if (!from || !el.capital) return;
    el.capital.value = from.initial_capital;
    el.size.value = (from.size_pct * 100).toFixed(0);
    el.leverage.value = from.leverage;
    el.fee.value = (from.fee * 100).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
    el.slippage.value = (from.slippage * 100).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
    if (el.preset) el.preset.value = 'custom';
    refreshSettings();
  }

  function bindSettings() {
    const el = elements.settings;
    if (!el?.root) return;
    el.preset.addEventListener('change', () => applyPreset(el.preset.value));
    for (const field of ['capital', 'size', 'leverage', 'fee', 'slippage']) {
      el[field].addEventListener('input', () => {
        // Any hand edit means the numbers are no longer a preset.
        if (['fee', 'slippage'].includes(field)) el.preset.value = 'custom';
        refreshSettings();
      });
    }
    el.close.addEventListener('click', closeSettings);
    el.start.addEventListener('click', confirmSettings);
    el.copy.addEventListener('click', copyFromBacktest);
    el.root.addEventListener('click', (event) => {
      if (event.target === el.root) closeSettings();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !el.root.hidden) closeSettings();
    });

    Explain.define('ps.preset', () => ({
      title: L('Preset sàn', 'Venue preset'),
      what: L('Điền sẵn phí và trượt giá theo biểu phí công bố của từng sàn.',
              "Fills in fee and slippage from each venue's published schedule."),
      how: L('Chọn nơi bạn thật sự giao dịch thay vì phải nhớ rằng taker của Binance Futures là 0,04%. Sửa tay bất kỳ ô nào thì preset tự chuyển sang “Tự đặt”.',
             'Pick where you actually trade instead of remembering that Binance futures taker is 0.04%. Editing any field by hand switches the preset to "Custom".'),
      watch: L('Preset chỉ là phí công bố. Nó không gồm thuế, phí lưu ký, phí rút, hay bậc phí theo khối lượng. Riêng maker chỉ đúng nếu lệnh của bạn thật sự nằm chờ trên sổ — chiến lược ở đây vào lệnh ở giá mở nến kế tiếp, nên thực tế gần như luôn là taker.',
              'A preset is only the headline fee. It excludes taxes, custody, withdrawal charges and volume tiers. The maker rate in particular is only right if your order genuinely rests on the book — strategies here enter at the next bar’s open, so in practice they are almost always takers.'),
    }));
  }

  async function start({ strategyId, symbol, timeframe, params, execution }) {
    const session = await API.paperStart({ strategyId, symbol, timeframe, params, execution });
    apply(session);
    return session;
  }

  /* Open a hand-traded session on whatever the chart is showing. It goes
     through the same settings dialog as a strategy session, because the costs
     matter just as much when the orders are yours. */
  function startManual() {
    const ctx = elements.context?.() || {};
    return openSettings({
      strategyId: MANUAL_STRATEGY,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      params: {},
    });
  }

  function init(config) {
    elements = config.elements;
    onToast = config.onToast;
    elements.refresh.addEventListener('click', refresh);
    elements.startManual?.addEventListener('click', startManual);
    bindSettings();
  }

  return { init, refresh, start, apply, rerender: render,
           openSettings, settingsValues, startManual, ticket, symbolBadge,
           get sessions() { return sessions; } };
})();
