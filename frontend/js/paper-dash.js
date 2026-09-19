/* Every paper session read as one account, in a window of its own.
 *
 * The side panel answers "how is this session doing" — one symbol, one
 * strategy, one balance. It cannot answer "how am I doing", because that spans
 * every session at once and there is nowhere in a 344px column to put it.
 *
 * Two things the numbers here are careful about, both inherited from
 * backend/paper/summary.py and repeated in the interface so a reader does not
 * have to go looking:
 *
 *   The equity curve has a point at each trade exit and nowhere else. Those
 *   are the only moments the balance is actually known, so the line is drawn
 *   stepped rather than smoothed — a smooth line between exits would trace a
 *   path the account never took.
 *
 *   Realised and unrealised sit in separate cards. One is settled and the
 *   other is a current opinion about a position still running, and adding them
 *   into a single figure is how an open drawdown gets hidden.
 */

const PaperDash = (() => {
  let host = null;
  let data = null;
  let onToast = () => {};
  let activeTab = 'equity';
  // Which currency's account is shown when sessions span more than one.
  let activeCurrency = null;
  let syncTimer = null;
  let syncing = false;
  let syncQueued = false;
  // The account being painted: its money is divided by `scale` for display.
  let view = { scale: 1, unit: '' };

  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));

  // Prices are shown as quoted; account money is shown in its currency, and a
  // VND account in millions, as the paper panel reads it.
  const money = (v) => Fmt.money(v, { digits: 2, min: 2 });
  const cash = (v) => `${Fmt.money(v / view.scale, { digits: 2, min: 2 })}${view.unit ? ` ${view.unit}` : ''}`;
  const pct = (v) => Fmt.pct(v);
  const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
  const when = (ts) => (ts
    ? new Date(ts * 1000).toLocaleString(I18n.locale(), {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    })
    : '—');

  // ---------- equity chart ----------

  /* Drawn as SVG rather than with the charting library.

     The library wants a container it can measure and owns its own lifecycle;
     this is a few dozen points inside a modal that opens and closes. An SVG
     with a viewBox scales to whatever width the modal has, needs no resize
     observer, and cannot be left behind when the window closes. */
  function equityChart(points, starting) {
    if (points.length < 2) {
      return `<p class="empty">${esc(L(
        'Chưa có lệnh nào đóng, nên chưa có đường vốn để vẽ.',
        'No trade has closed yet, so there is no equity curve to draw.'))}</p>`;
    }

    const W = 1000;
    const H = 220;
    const PAD = 8;
    const values = points.map((p) => p.equity);
    const lo = Math.min(...values, starting);
    const hi = Math.max(...values, starting);
    // A flat account would divide by zero, and a hairline at the top of an
    // empty box reads as a bug rather than as "nothing happened".
    const span = hi - lo || Math.max(hi * 0.01, 1);

    const x = (i) => (points.length === 1 ? W / 2 : (i / (points.length - 1)) * W);
    const y = (v) => PAD + (1 - (v - lo) / span) * (H - PAD * 2);

    // Stepped: hold the last balance until the next exit moves it.
    let path = `M ${x(0).toFixed(1)} ${y(values[0]).toFixed(1)}`;
    for (let i = 1; i < points.length; i += 1) {
      path += ` H ${x(i).toFixed(1)} V ${y(values[i]).toFixed(1)}`;
    }

    const last = values[values.length - 1];
    const up = last >= starting;
    const colour = up ? 'var(--up)' : 'var(--down)';
    const base = y(starting).toFixed(1);

    return `
      <div class="pd-chart">
        <svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img"
             aria-label="${esc(L('Đường vốn', 'Equity curve'))}">
          <path d="${path} V ${H} H ${x(0).toFixed(1)} Z" fill="${colour}" opacity="0.10"/>
          <path d="${path}" fill="none" stroke="${colour}" stroke-width="2"
                vector-effect="non-scaling-stroke"/>
          <line x1="0" y1="${base}" x2="${W}" y2="${base}" stroke="var(--text-faint)"
                stroke-width="1" stroke-dasharray="4 4" vector-effect="non-scaling-stroke"/>
        </svg>
        <div class="pd-axis">
          <span>${esc(when(points[0].time))}</span>
          <span class="muted">${esc(L('vốn ban đầu', 'starting capital'))} ${cash(starting)}</span>
          <span>${esc(when(points[points.length - 1].time))}</span>
        </div>
      </div>`;
  }

  // ---------- tabs ----------

  function equityTab(d) {
    let html = '<div class="metrics">';
    html += card(L('Tổng tài sản', 'Total equity'), cash(d.equity), sign(d.return_pct),
      L(`từ ${cash(d.starting_capital)}`, `from ${cash(d.starting_capital)}`));
    html += card(L('Lợi nhuận', 'Return'), pct(d.return_pct), sign(d.return_pct));
    // Kept apart on purpose: see the note at the top of this file.
    html += card(L('Đã chốt', 'Realised'), cash(d.realized_pnl), sign(d.realized_pnl),
      L(`${d.num_trades} lệnh đã đóng`, `${d.num_trades} closed trades`));
    html += card(L('Chưa chốt', 'Unrealised'), cash(d.unrealized_pnl), sign(d.unrealized_pnl),
      L(`${d.open_positions.length} vị thế đang mở`,
        `${d.open_positions.length} open positions`));
    html += card(L('Sụt giảm tối đa', 'Max drawdown'), `-${d.max_drawdown_pct.toFixed(2)}%`,
      d.max_drawdown_pct > 0 ? 'neg' : '',
      L('trên đường vốn đã chốt', 'on the realised curve'));
    html += card(L('Tỷ lệ thắng', 'Win rate'), `${d.win_rate_pct.toFixed(0)}%`,
      d.win_rate_pct >= 50 ? 'pos' : 'neg',
      `${d.num_wins}/${d.num_trades}`);
    html += '</div>';

    if (d.open_positions.length) {
      html += `<div class="field-group-title">${esc(L(
        'Vị thế đang mở', 'Open positions'))}</div>`;
      html += `<table class="data-table"><thead><tr>
        <th>${esc(L('Mã', 'Symbol'))}</th>
        <th>${esc(L('Chiều', 'Side'))}</th>
        <th>${esc(L('Giá vào', 'Entry'))}</th>
        <th>${esc(L('Hiện tại', 'Now'))}</th>
        <th>${esc(L('Cắt lỗ', 'Stop'))}</th>
        <th>${esc(L('Chốt lời', 'Target'))}</th>
        <th>${esc(L('Lãi/lỗ mở', 'Open P&L'))}</th>
        </tr></thead><tbody>` + d.open_positions.map((p) => `<tr>
          <td>${esc(p.symbol)} <span class="muted">${esc(p.timeframe)}</span></td>
          <td class="${p.side === 'long' ? 'pos' : 'neg'}">${
            p.side === 'long' ? 'LONG' : 'SHORT'}</td>
          <td>${money(p.entry_price)}</td>
          <td>${money(p.last_price)}</td>
          <td class="muted">${p.stop_loss ? money(p.stop_loss) : '—'}</td>
          <td class="muted">${p.take_profit ? money(p.take_profit) : '—'}</td>
          <td class="${sign(p.unrealized_pnl)}">${cash(p.unrealized_pnl)}</td>
        </tr>`).join('') + '</tbody></table>';
    }
    return html;
  }

  function balanceTab(d) {
    if (!d.balance_history?.length) {
      return `<p class="empty">${esc(L(
        'Chưa có lần kết toán nào.', 'No settlement has been recorded yet.'))}</p>`;
    }
    return `<div class="pd-section-head">
      <div><strong>${esc(L('Lịch sử số dư tài khoản', 'Account balance history'))}</strong>
      <p class="hint">${esc(L(
        'Lãi/lỗ giá và phí giao dịch được tách riêng; số dư sau đã trừ cả phí vào và phí ra.',
        'Price P&L and trading fees are separate; the ending balance deducts both entry and exit fees.'))}</p></div>
      <span class="badge">${d.balance_history.length}</span>
    </div>
    <table class="data-table pd-ledger"><thead><tr>
      <th>${esc(L('Thời gian', 'Time'))}</th>
      <th>${esc(L('Số dư trước kết toán', 'Balance before'))}</th>
      <th>${esc(L('Lãi/Lỗ đã thực hiện', 'Realised P&L'))}</th>
      <th>${esc(L('Phí giao dịch', 'Trading fees'))}</th>
      <th>${esc(L('Số dư sau kết toán', 'Balance after'))}</th>
      <th>${esc(L('Hành động', 'Action'))}</th>
      </tr></thead><tbody>${d.balance_history.map((row) => `<tr>
        <td class="muted">${esc(when(row.time))}</td>
        <td>${cash(row.balance_before)}</td>
        <td class="${sign(row.gross_pnl)}">${cash(row.gross_pnl)}</td>
        <td class="${row.fee > 0 ? 'neg' : 'muted'}">${row.fee > 0 ? `−${cash(row.fee)}` : cash(0)}</td>
        <td class="${sign(row.balance_after - row.balance_before)}">${cash(row.balance_after)}</td>
        <td><strong>${esc(row.side === 'long' ? L('Đóng LONG', 'Close LONG') : L('Đóng SHORT', 'Close SHORT'))}</strong>
          <span class="muted"> · ${esc(row.symbol)} · ${esc(reasonLabel(row.exit_reason))}</span></td>
      </tr>`).join('')}</tbody></table>`;
  }

  function analysisTab(d) {
    const factor = d.profit_factor == null ? '—' : Fmt.number(d.profit_factor, 2);
    const rr = d.avg_rr == null ? '—' : `${Fmt.number(d.avg_rr, 2)}R`;
    let html = '<div class="metrics pd-analysis">';
    html += card(L('Giao dịch lãi', 'Profitable trades'), `${d.win_rate_pct.toFixed(1)}%`,
      d.win_rate_pct >= 50 ? 'pos' : (d.num_trades ? 'neg' : ''),
      L(`${d.num_wins}/${d.num_trades} lệnh · ${cash(d.profitable_trades_pnl)}`,
        `${d.num_wins}/${d.num_trades} trades · ${cash(d.profitable_trades_pnl)}`));
    html += card(L('Hệ số lãi', 'Profit factor'), factor,
      d.profit_factor != null && d.profit_factor >= 1 ? 'pos' : (d.profit_factor != null ? 'neg' : ''),
      L('tổng lãi / tổng lỗ', 'gross profits / gross losses'));
    html += card(L('Kỳ vọng giao dịch', 'Trade expectancy'), cash(d.expectancy_money),
      sign(d.expectancy_money), pct(d.expectancy_pct));
    html += card(L('RR trung bình', 'Average RR'), rr,
      d.avg_rr != null && d.avg_rr >= 1 ? 'pos' : (d.avg_rr != null ? 'neg' : ''),
      L('lãi trung bình / lỗ trung bình', 'average win / average loss'));
    html += '</div>';
    html += `<div class="pd-section-head"><div><strong>${esc(L('Hiệu suất', 'Performance'))}</strong>
      <p class="hint">${esc(L('Tăng trưởng số dư sau mỗi lần kết toán, đã trừ phí.',
        'Balance growth after each settlement, net of fees.'))}</p></div>
      <span class="${sign(d.return_pct)}">${esc(pct(d.return_pct))}</span></div>`;
    html += equityChart(d.equity_curve, d.starting_capital);
    return html;
  }

  function tradesTab(d) {
    if (!d.trades.length) {
      return `<p class="empty">${esc(L(
        'Chưa có lệnh nào được đóng.', 'No trade has been closed yet.'))}</p>`;
    }
    return `<table class="data-table"><thead><tr>
      <th>${esc(L('Đóng lúc', 'Closed'))}</th>
      <th>${esc(L('Mã', 'Symbol'))}</th>
      <th>${esc(L('Chiều', 'Side'))}</th>
      <th>${esc(L('Vào', 'In'))}</th>
      <th>${esc(L('Ra', 'Out'))}</th>
      <th>${esc(L('Lãi/Lỗ ròng', 'Net P&L'))}</th>
      <th>${esc(L('Phí', 'Fees'))}</th>
      <th>%</th>
      <th>${esc(L('Lý do', 'Reason'))}</th>
      </tr></thead><tbody>` + d.trades.map((t) => `<tr>
        <td class="muted">${esc(when(t.exit_time))}</td>
        <td>${esc(t.symbol)}</td>
        <td class="${t.side === 'long' ? 'pos' : 'neg'}">${
          t.side === 'long' ? 'LONG' : 'SHORT'}</td>
        <td>${money(t.entry_price)}</td>
        <td>${money(t.exit_price)}</td>
        <td class="${sign(t.net_pnl ?? t.pnl)}">${cash(t.net_pnl ?? t.pnl)}</td>
        <td class="${t.fee > 0 ? 'neg' : 'muted'}">${t.fee > 0 ? `−${cash(t.fee)}` : cash(0)}</td>
        <td class="${sign(t.return_pct)}">${pct(t.return_pct)}</td>
        <td class="muted">${esc(reasonLabel(t.exit_reason))}</td>
      </tr>`).join('') + '</tbody></table>';
  }

  /* Exit reasons come from the engine as stable codes, so they are translated
     here rather than matched on prose (§2.4). */
  function reasonLabel(code) {
    return {
      manual: L('tay', 'manual'),
      signal: L('tín hiệu', 'signal'),
      liquidation: L('THANH LÝ', 'LIQUIDATED'),
      stop_loss: L('cắt lỗ', 'stop loss'),
      take_profit: L('chốt lời', 'take profit'),
      end_of_data: L('hết dữ liệu', 'end of data'),
    }[code] || code;
  }

  function symbolsTab(d) {
    if (!d.by_symbol.length) {
      return `<p class="empty">${esc(L('Chưa có lệnh nào.', 'No trades yet.'))}</p>`;
    }
    const worst = Math.max(...d.by_symbol.map((r) => Math.abs(r.pnl)), 1);
    return `<table class="data-table"><thead><tr>
      <th>${esc(L('Mã', 'Symbol'))}</th>
      <th>${esc(L('Lệnh', 'Trades'))}</th>
      <th>${esc(L('Thắng', 'Won'))}</th>
      <th>${esc(L('Lãi/Lỗ', 'P&L'))}</th>
      <th></th>
      </tr></thead><tbody>` + d.by_symbol.map((r) => `<tr>
        <td>${esc(r.symbol)}</td>
        <td class="muted">${r.trades}</td>
        <td class="muted">${r.win_rate_pct.toFixed(0)}%</td>
        <td class="${sign(r.pnl)}">${cash(r.pnl)}</td>
        <td style="width:34%">
          <div class="pd-bar"><span class="${sign(r.pnl)}"
            style="width:${(Math.abs(r.pnl) / worst * 100).toFixed(1)}%"></span></div>
        </td>
      </tr>`).join('') + '</tbody></table>';
  }

  const TABS = [
    ['equity', () => L('Tài khoản', 'Account'), equityTab],
    ['balance', () => L('Lịch sử số dư', 'Balance history'), balanceTab],
    ['analysis', () => L('Phân tích', 'Analysis'), analysisTab],
    ['trades', () => L('Lịch sử lệnh', 'Trade history'), tradesTab],
    ['symbols', () => L('Theo mã', 'By symbol'), symbolsTab],
  ];

  function card(label, value, cls = '', sub = '') {
    return `<div class="metric">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value ${cls}">${esc(value)}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function currencyView(currency) {
    if (currency === 'VND') return { scale: 1e6, unit: L('triệu VND', 'million VND'), label: 'VND' };
    if (currency === 'USDT') return { scale: 1, unit: 'USDT', label: 'USDT' };
    if (currency === 'units') return { scale: 1, unit: '', label: L('Đơn vị khác', 'Other units') };
    return { scale: 1, unit: '', label: '' };
  }

  // ---------- window ----------

  function paint() {
    if (!host || !data) return;
    if (!data.sessions) {
      host.querySelector('.pd-body').innerHTML =
        `<p class="empty">${emph(esc(tp(data.note)))}</p>`;
      return;
    }
    const count = host.querySelector('[data-pd-count]');
    if (count) count.textContent = L(
      `${data.sessions || 0} phiên`, `${data.sessions || 0} sessions`);
    const tab = TABS.find(([id]) => id === activeTab) || TABS[0];
    const accounts = data.accounts?.length ? data.accounts : [{ ...data, currency: '' }];
    const account = accounts.find((a) => a.currency === activeCurrency) || accounts[0];
    activeCurrency = account.currency;
    view = currencyView(account.currency);
    // One switch per currency: amounts in different currencies are never
    // added together, so each has its own account view.
    const switcher = accounts.length > 1
      ? `<span class="pd-currencies">${accounts.map((a) =>
        `<button class="rp-tab${a.currency === activeCurrency ? ' active' : ''}" data-pd-currency="${esc(a.currency)}">${
          esc(currencyView(a.currency).label)} · ${a.sessions}</button>`).join('')}</span>`
      : '';
    host.querySelector('.pd-tabs').innerHTML = TABS.map(([id, label]) =>
      `<button class="rp-tab${id === activeTab ? ' active' : ''}" data-pd-tab="${id}"
        role="tab">${esc(label())}</button>`).join('') + switcher;
    try {
      host.querySelector('.pd-body').innerHTML = tab[2](account);
    } catch (err) {
      host.querySelector('.pd-body').innerHTML =
        `<div class="callout warn">${esc(err.message)}</div>`;
    }
  }

  async function open() {
    close();
    try {
      data = await API.paperSummary();
    } catch (err) {
      onToast(err.message, true);
      return;
    }

    host = document.createElement('div');
    host.className = 'pd-backdrop';
    host.innerHTML = `
      <div class="pd-window" role="dialog" aria-modal="true" aria-labelledby="pd-title">
        <div class="pd-head">
          <h2 id="pd-title">${esc(L('Tài khoản giao dịch mô phỏng', 'Simulated trading account'))}</h2>
          <div class="pd-head-right">
            <span class="badge" data-pd-count>${esc(L(
              `${data.sessions || 0} phiên`, `${data.sessions || 0} sessions`))}</span>
            <button class="btn btn-quiet btn-sm" data-pd-close
              aria-label="${esc(t('a11y.close'))}">✕</button>
          </div>
        </div>
        <div class="pd-tabs" role="tablist"></div>
        <div class="pd-body"></div>
      </div>`;
    document.body.appendChild(host);
    paint();

    host.addEventListener('click', async (event) => {
      // Clicking the backdrop itself closes; clicking inside must not.
      if (event.target === host || event.target.closest('[data-pd-close]')) { close(); return; }
      const tab = event.target.closest('[data-pd-tab]');
      if (tab) { activeTab = tab.dataset.pdTab; paint(); return; }
      const currency = event.target.closest('[data-pd-currency]');
      if (currency) { activeCurrency = currency.dataset.pdCurrency; paint(); return; }
    });
    document.addEventListener('keydown', onKey);
  }

  function onKey(event) {
    if (event.key === 'Escape') close();
  }

  function close() {
    document.removeEventListener('keydown', onKey);
    host?.remove();
    host = null;
    clearTimeout(syncTimer);
    syncTimer = null;
    syncQueued = false;
  }

  async function refreshLive() {
    syncTimer = null;
    if (!host) return;
    if (syncing) { syncQueued = true; return; }
    const target = host;
    syncing = true;
    try {
      const latest = await API.paperSummary();
      if (host === target) {
        data = latest;
        paint();
      }
    } catch (err) {
      onToast(err.message, true);
    } finally {
      syncing = false;
      if (syncQueued && host) {
        syncQueued = false;
        syncTimer = setTimeout(refreshLive, 120);
      }
    }
  }

  /** Coalesce live ticks so the open dashboard stays current without flooding
      the summary endpoint when several simulated sessions share a feed. */
  function sync() {
    if (!host) return;
    if (syncing) { syncQueued = true; return; }
    if (syncTimer) return;
    syncTimer = setTimeout(refreshLive, 120);
  }

  function init(config) {
    onToast = config?.onToast || (() => {});
    I18n.onChange(() => { if (host) paint(); });
  }

  return { init, open, close, sync, get isOpen() { return host !== null; } };
})();
