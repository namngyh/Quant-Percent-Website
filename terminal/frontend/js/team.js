/* The team's own models, beside what this platform computes.
 *
 * Four views in the market database publish a forecast on VNINDEX, the record
 * of what it forecast before, a correlation network over VN30, and the
 * ingestion log. They are a second opinion arrived at by another method, which
 * is worth reading next to a backtest — as long as the differences are on
 * screen, because two numbers sharing a window read as comparable whether or
 * not they are.
 *
 * Every figure here is the team's, except the scoring: the team's own
 * `actual_value` column is empty on every row, so each past forecast is scored
 * against this platform's VNINDEX closes and the panel says so.
 */
const Team = (() => {
  let root = null;
  let onToast = () => {};

  function esc(value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  }

  const num = (v, digits = 2) => (Number.isFinite(v) ? Fmt.number(v, digits, digits) : '—');
  const pct = (v, digits = 2) => (Number.isFinite(v) ? Fmt.pct(v, digits) : '—');
  const upct = (v, digits = 1) => (Number.isFinite(v) ? Fmt.upct(v, digits) : '—');

  const when = (ms) => (Number.isFinite(ms)
    ? new Date(ms + Settings.tzOffsetSeconds() * 1000).toISOString().slice(0, 16).replace('T', ' ')
    : '—');

  // Remarks are not shown; failures below are.
  const notes = () => '';

  const failed = (block) => (block && block.error
    ? `<div class="callout warn">${esc(tp(block.error))}</div>` : '');

  /* The forecast itself: one card per horizon, and the band beside the point.

     The point estimate alone is the half of this a reader remembers, so the
     90% interval sits on the same card: a band 700 points wide is the model
     saying it does not know, and that is the more useful half. */
  function forecast(block) {
    if (!block || block.error) return failed(block);
    const items = block.items || [];
    if (!items.length) {
      return `<p class="empty">${esc(L('Chưa có dự báo nào.', 'No forecast published yet.'))}</p>`;
    }
    const cards = items.map((item) => `
      <div class="stat-card">
        <div class="stat-label">${esc(item.symbol)} · ${esc(L(
          `${item.horizon} phiên`, `${item.horizon} sessions`))}</div>
        <div class="stat-value">${num(item.forecast_value, 1)}</div>
        <div class="stat-sub">${esc(L('Thay đổi', 'Change'))} ${pct(item.forecast_return_pct)}
          · ${esc(L('Xác suất tăng', 'P(up)'))} ${upct(item.probability_up_pct)}</div>
        <div class="stat-sub">${esc(L(
          `Khoảng ${Math.round((item.interval_level || 0) * 100)}%`,
          `${Math.round((item.interval_level || 0) * 100)}% band`))}
          ${num(item.interval_lower, 0)} – ${num(item.interval_upper, 0)}</div>
      </div>`).join('');
    const head = items[0];
    return `
      <div class="stat-cards">${cards}</div>
      <p class="hint">${esc(L(
        `Mô hình ${head.model_id || ''} ${head.model_version || ''}, trạng thái ${head.status || '—'}; `
        + `dữ liệu tới ${when(head.data_as_of)}, chạy lúc ${when(head.generated_at)}.`,
        `Model ${head.model_id || ''} ${head.model_version || ''}, status ${head.status || '—'}; `
        + `data to ${when(head.data_as_of)}, run at ${when(head.generated_at)}.`))}</p>
      ${notes(block.notes)}`;
  }

  /* The record. A hit rate on seventeen forecasts carries an error bar wide
     enough to swallow the difference from a coin toss, so the error is printed
     next to it rather than left for the reader to work out (§2.6). */
  function scoring(block) {
    if (!block || block.error) return failed(block);
    const rows = (block.horizons || []).map((row) => `
      <tr>
        <td>${esc(L(`${row.horizon} phiên`, `${row.horizon} sessions`))}</td>
        <td>${row.scored} / ${row.forecasts}</td>
        <td>${upct(row.mean_abs_error_pct)}</td>
        <td class="${row.bias_pct > 0 ? 'pos' : row.bias_pct < 0 ? 'neg' : ''}">${pct(row.bias_pct)}</td>
        <td>${upct(row.interval_hit_pct, 0)}</td>
        <td>${Number.isFinite(row.directional_hit_pct)
          ? `${upct(row.directional_hit_pct, 1)} ± ${upct(row.directional_error_pct, 1)}`
          : '—'}</td>
      </tr>`).join('');

    return `
      <div class="table-scroll"><table class="data-table">
        <thead><tr>
          <th>${esc(L('Tầm dự báo', 'Horizon'))}</th>
          <th>${esc(L('Đã chấm / tổng', 'Scored / made'))}</th>
          <th>${esc(L('Sai số tuyệt đối', 'Mean abs. error'))}</th>
          <th>${esc(L('Lệch hệ thống', 'Bias'))}</th>
          <th>${esc(L('Trúng khoảng', 'Interval hit'))}</th>
          <th>${esc(L('Đúng hướng', 'Direction hit'))}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div>
      ${notes(block.notes)}`;
  }

  /* The network. Nodes and edges are the graph's own words for "which names
     move together"; the panel keeps the strongest of each rather than all 30
     and 84, which do not fit anywhere useful. */
  function network(block) {
    if (!block || block.error) return failed(block);
    if (!block.available) {
      return `<p class="empty">${esc(L('Chưa có ảnh chụp mạng.', 'No network snapshot yet.'))}</p>`;
    }
    const nodes = (block.nodes || []).map((n) => `
      <tr><td>${esc(n.id)}</td><td>${num(n.pagerank, 4)}</td>
      <td class="${n.return_20d_pct > 0 ? 'pos' : n.return_20d_pct < 0 ? 'neg' : ''}">${pct(n.return_20d_pct, 1)}</td>
      <td>${upct(n.volatility_20d_pct, 1)}</td><td>${esc(n.community ?? '—')}</td></tr>`).join('');
    const edges = (block.edges || []).map((e) => `
      <tr><td>${esc(e.source)} — ${esc(e.target)}</td>
      <td class="${e.weight < 0 ? 'neg' : ''}">${num(e.weight, 3)}</td>
      <td>${num(e.stability, 2)}</td></tr>`).join('');
    const communities = (block.communities || [])
      .map((c) => `${esc(L(`Nhóm ${c.id}`, `Group ${c.id}`))} (${c.size}): ${esc((c.members || []).join(', '))}`)
      .join('<br>');

    return `
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-label">${esc(L('Điểm căng thẳng', 'Stress score'))} ${esc(block.index_name || '')}</div>
          <div class="stat-value">${num(block.stress_score, 2)}</div>
          <div class="stat-sub">${esc(block.stress_label || '')} · ${esc(L(
            'bách phân vị', 'percentile'))} ${upct(block.stress_percentile_pct, 1)}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${esc(L('Đồ thị', 'Graph'))}</div>
          <div class="stat-value">${block.node_count} / ${block.edge_count}</div>
          <div class="stat-sub">${esc(L('mã / cạnh, cửa sổ', 'names / edges, window'))} ${
            block.graph_window ?? '—'} ${esc(L('phiên', 'sessions'))}</div>
        </div>
      </div>
      <div class="field-group-title">${esc(L('Mã trung tâm nhất', 'Most central names'))}</div>
      <div class="table-scroll"><table class="data-table">
        <thead><tr><th>${esc(L('Mã', 'Symbol'))}</th><th>PageRank</th>
        <th>${esc(L('20 phiên', '20 sessions'))}</th><th>${esc(L('Biến động', 'Volatility'))}</th>
        <th>${esc(L('Nhóm', 'Group'))}</th></tr></thead>
        <tbody>${nodes}</tbody></table></div>
      <div class="field-group-title">${esc(L('Cặp gắn kết nhất', 'Strongest pairs'))}</div>
      <div class="table-scroll"><table class="data-table">
        <thead><tr><th>${esc(L('Cặp', 'Pair'))}</th><th>${esc(L('Trọng số', 'Weight'))}</th>
        <th>${esc(L('Độ ổn định', 'Stability'))}</th></tr></thead>
        <tbody>${edges}</tbody></table></div>
      ${communities ? `<p class="hint">${communities}</p>` : ''}
      ${notes(block.notes)}`;
  }

  /* The ingestion log, under its own name. It counts socket drops, and the
     count of drops has no fixed relationship to missing candles — most of them
     land outside the session, where there is nothing to miss. */
  function pipeline(block) {
    if (!block || block.error) return failed(block);
    const recent = (block.recent || []).slice(0, 8).map((row) => `
      <tr><td>${esc(row.symbol)}</td><td>${when(row.disconnected_at)}</td>
      <td>${Number.isFinite(row.seconds) ? `${num(row.seconds, 0)}s`
        : esc(L('chưa ghi nhận nối lại', 'no reconnect recorded'))}</td>
      <td>${row.in_session ? esc(L('trong phiên', 'in session')) : esc(L('ngoài phiên', 'outside'))}</td></tr>`).join('');

    return `
      <div class="stat-cards">
        <div class="stat-card">
          <div class="stat-label">${esc(L('Lần rớt kết nối', 'Disconnects'))}</div>
          <div class="stat-value">${block.total}</div>
          <div class="stat-sub">${esc(L('trong phiên', 'in session'))} ${block.in_session}
            · ${esc(L('dài hơn 1 phút', 'over a minute'))} ${block.longer_than_a_minute}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">${esc(L('Chưa ghi nhận nối lại', 'No reconnect recorded'))}</div>
          <div class="stat-value">${block.unclosed}</div>
          <div class="stat-sub">${esc(L(
            'không đồng nghĩa luồng đang chết', 'not the same as a dead feed'))}</div>
        </div>
      </div>
      <div class="table-scroll"><table class="data-table">
        <thead><tr><th>${esc(L('Mã', 'Symbol'))}</th><th>${esc(L('Lúc rớt', 'Dropped at'))}</th>
        <th>${esc(L('Kéo dài', 'Lasted'))}</th><th>${esc(L('Giờ', 'When'))}</th></tr></thead>
        <tbody>${recent}</tbody></table></div>
      ${notes(block.notes)}`;
  }

  function render(payload) {
    return `
      <section class="set-group">
        <h3>${esc(L('Dự báo VNINDEX', 'VNINDEX forecast'))}</h3>
        ${forecast(payload.forecast)}
      </section>
      <section class="set-group">
        <h3>${esc(L('Dự báo trước đó đã đúng tới đâu', 'How the past forecasts did'))}</h3>
        ${scoring(payload.scoring)}
      </section>
      <section class="set-group">
        <h3>${esc(L('Cấu trúc thị trường VN30', 'VN30 market structure'))}</h3>
        ${network(payload.network)}
      </section>
      <section class="set-group">
        <h3>${esc(L('Đường dữ liệu', 'Data pipeline'))}</h3>
        ${pipeline(payload.pipeline)}
      </section>`;
  }

  async function open() {
    if (!root) return;
    root.innerHTML = `<p class="empty">${esc(L('Đang đọc…', 'Reading…'))}</p>`;
    try {
      root.innerHTML = render(await API.teamModels());
    } catch (err) {
      /* The whole window is a second opinion, so it fails as one: it says what
         went wrong and nothing else on screen is affected. */
      root.innerHTML = `<div class="callout warn">${esc(L(
        `Không đọc được mô hình của team: ${err.message}. Thường là VPN chưa bật.`,
        `Could not read the team's models: ${err.message}. Usually the VPN is off.`))}</div>`;
      onToast(L('Không đọc được mô hình của team.', "Could not read the team's models."), true);
    }
  }

  function init(config) {
    root = config.root;
    onToast = config.onToast || (() => {});
  }

  return { init, open, render };
})();
