/* Paper trading panel: the sessions running forward on live data.

   A session keeps trading with the browser closed, so this panel is a view of
   server state rather than the thing that owns it: everything here reads from
   /api/paper and pushes actions back. */

const Paper = (() => {
  let elements = {};
  let onToast = () => {};
  let sessions = [];

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

  async function start({ strategyId, symbol, timeframe, params, execution }) {
    const session = await API.paperStart({ strategyId, symbol, timeframe, params, execution });
    apply(session);
    return session;
  }

  function init(config) {
    elements = config.elements;
    onToast = config.onToast;
    elements.refresh.addEventListener('click', refresh);
  }

  return { init, refresh, start, apply, rerender: render,
           get sessions() { return sessions; } };
})();
