/* Paper trading panel: the sessions running forward on live data.

   A session keeps trading with the browser closed, so this panel is a view of
   server state rather than the thing that owns it: everything here reads from
   /api/paper and pushes actions back. */

const Paper = (() => {
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

  function positionPill(s) {
    if (s.position > 0) return '<span class="pill long">LONG</span>';
    if (s.position < 0) return '<span class="pill short">SHORT</span>';
    return '<span class="pill flat">ĐỨNG NGOÀI</span>';
  }

  function render() {
    if (!sessions.length) {
      elements.list.innerHTML =
        '<p class="empty">Chưa có phiên nào. Mở tab <strong>Chiến lược</strong>, ' +
        'chọn chiến lược rồi bấm <strong>Chạy paper trading</strong>.</p>';
      return;
    }

    elements.list.innerHTML = sessions
      .map((s) => {
        const pnl = s.equity - s.config.initial_capital;
        const open = s.position !== 0;
        return `<div class="paper-card ${s.active ? '' : 'stopped'}">
          <div class="paper-card-head">
            <div>
              <div class="paper-name">${esc(s.strategy_id)}</div>
              <div class="paper-series">${esc(s.symbol)} · ${esc(s.timeframe)} · ${s.bars_seen} nến</div>
            </div>
            <div class="paper-actions">
              <span class="pill ${s.active ? 'running' : 'stopped'}">${s.active ? 'ĐANG CHẠY' : 'ĐÃ DỪNG'}</span>
              <button class="btn btn-quiet btn-sm" data-paper-toggle="${esc(s.id)}">${s.active ? 'Dừng' : 'Chạy lại'}</button>
              <button class="btn btn-quiet btn-sm btn-danger" data-paper-delete="${esc(s.id)}">✕</button>
            </div>
          </div>

          <div class="paper-body">
            <div class="paper-stat">
              <div class="paper-stat-label">Vốn</div>
              <div class="paper-stat-value ${sign(pnl)}">${money(s.equity)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">Lợi nhuận</div>
              <div class="paper-stat-value ${sign(s.return_pct)}">${pct(s.return_pct)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">Vị thế</div>
              <div class="paper-stat-value">${positionPill(s)}</div>
            </div>
            <div class="paper-stat">
              <div class="paper-stat-label">${open ? 'Lãi/lỗ mở' : 'Đã đóng'}</div>
              <div class="paper-stat-value ${open ? sign(s.unrealized_pnl) : ''}">${
                open ? money(s.unrealized_pnl) : `${s.num_trades} lệnh`
              }</div>
            </div>
            ${
              open
                ? `<div class="paper-note">Vào ${money(s.entry_price)} · khối lượng ${s.quantity.toFixed(6)} · giá hiện tại ${money(s.last_price)}</div>`
                : ''
            }
            <div class="paper-note">
              ${s.num_trades} lệnh · thắng ${s.win_rate_pct.toFixed(0)}% ·
              đã thực hiện ${money(s.realized_pnl)} · nến cuối ${ago(s.last_closed_time)}
            </div>
            ${
              s.pending_signal !== s.position
                ? `<div class="paper-note">Chờ khớp ở nến kế tiếp: <strong>${
                    s.pending_signal > 0 ? 'MUA' : s.pending_signal < 0 ? 'BÁN' : 'ĐÓNG'
                  }</strong></div>`
                : ''
            }
          </div>
        </div>`;
      })
      .join('');

    bind();
  }

  function bind() {
    for (const btn of elements.list.querySelectorAll('[data-paper-toggle]')) {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.paperToggle;
        const session = sessions.find((s) => s.id === id);
        btn.disabled = true;
        try {
          const updated = session.active ? await API.paperStop(id) : await API.paperResume(id);
          apply(updated);
          onToast(updated.active ? 'Đã chạy lại phiên' : 'Đã dừng phiên');
        } catch (err) {
          onToast(err.message, true);
        }
      });
    }

    for (const btn of elements.list.querySelectorAll('[data-paper-delete]')) {
      btn.addEventListener('click', async () => {
        const id = btn.dataset.paperDelete;
        // Deleting throws away the whole trade history, so make it deliberate.
        if (!window.confirm('Xóa phiên này? Toàn bộ lịch sử lệnh sẽ mất.')) return;
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

  function init(config) {
    elements = config.elements;
    onToast = config.onToast;
    elements.refresh.addEventListener('click', refresh);
    bindSettings();
  }

  return { init, refresh, start, apply, rerender: render,
           openSettings, settingsValues,
           get sessions() { return sessions; } };
})();
