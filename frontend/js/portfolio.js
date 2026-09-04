/* Quant Portfolio — ported from quantpercent.com.
 *
 * The form lives in the side panel because it is a list of short fields; the
 * result opens in the report window because it is not. A weight-against-risk
 * comparison only works when both bars are on screen at once, and 344px cannot
 * hold that plus a five-column position table.
 *
 * The one number this page exists for is risk contribution. A reader already
 * knows what share of their money is in each name. What they cannot see is
 * that a quarter of the money can be most of the risk — so that gap is stated
 * in a sentence, drawn as a paired bar, and sorted to the top of the table,
 * rather than left to be noticed.
 */

const Portfolio = (() => {
  let elements = {};
  let onToast = () => {};
  let known = new Map();
  let rows = [];
  let nextId = 1;
  let lastResult = null;

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

  const nf = (value, digits = 2) =>
    Number.isFinite(value) ? value.toFixed(digits) : '—';
  const pct = (value, digits = 2) =>
    Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%` : '—';
  const upct = (value, digits = 1) =>
    Number.isFinite(value) ? `${value.toFixed(digits)}%` : '—';
  const cls = (value) => (value > 0 ? 'pos' : value < 0 ? 'neg' : '');

  /** Money in dong, abbreviated — 563.240.000 does not read at a glance. */
  function dong(value) {
    if (!Number.isFinite(value)) return '—';
    const magnitude = Math.abs(value);
    if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)} tỷ`;
    if (magnitude >= 1e6) return `${(value / 1e6).toFixed(1)} tr`;
    return value.toLocaleString('vi-VN', { maximumFractionDigits: 0 });
  }

  /* VN keyboards produce "1.000", "1,000" and "1 000" for the same number, and
     rejecting any of them reads as the form being broken. */
  function parseNumber(raw) {
    const cleaned = String(raw ?? '').replace(/[\s.,]/g, '');
    if (cleaned === '') return null;
    const value = Number(cleaned);
    return Number.isFinite(value) ? value : null;
  }

  // ---------- the entry form ----------

  const blankRow = () => ({ id: nextId++, symbol: '', quantity: '', costBasis: '' });

  function renderRows() {
    elements.rows.innerHTML = rows.map((row) => {
      const code = row.symbol.trim().toUpperCase();
      const hit = known.get(code);
      // Only warn about an unknown code once the symbol list has loaded;
      // before that, everything would look unknown.
      const note = !code ? ''
        : hit ? `<span class="pf-name">${esc(hit.name)}</span>`
          : known.size ? '<span class="pf-warn">không có mã này trên sàn</span>' : '';

      return `<div class="pf-row" data-row="${row.id}">
        <div class="pf-row-head">
          <input class="pf-symbol" list="pf-symbols" value="${esc(row.symbol)}"
                 placeholder="FPT" autocomplete="off" spellcheck="false" />
          <button class="pf-remove" title="Bỏ mã này" aria-label="Bỏ mã này">✕</button>
        </div>
        ${note}
        <div class="pf-row-fields">
          <label><span>Số lượng</span>
            <input class="pf-quantity" inputmode="numeric" value="${esc(row.quantity)}"
                   placeholder="1.000" /></label>
          <label><span>Giá vốn/cổ</span>
            <input class="pf-cost" inputmode="numeric" value="${esc(row.costBasis)}"
                   placeholder="không bắt buộc" /></label>
        </div>
      </div>`;
    }).join('');

    elements.count.textContent = `${rows.filter((r) => r.symbol.trim()).length} mã`;
  }

  function bindRows() {
    elements.rows.addEventListener('input', (event) => {
      const container = event.target.closest('.pf-row');
      if (!container) return;
      const row = rows.find((r) => r.id === Number(container.dataset.row));
      if (!row) return;

      if (event.target.classList.contains('pf-symbol')) {
        row.symbol = event.target.value;
        // Repaint only the name hint: a full re-render would steal focus and
        // drop the caret while the user is still typing the ticker.
        const code = row.symbol.trim().toUpperCase();
        const hit = known.get(code);
        let note = container.querySelector('.pf-name, .pf-warn');
        const text = !code ? '' : hit ? hit.name : (known.size ? 'không có mã này trên sàn' : '');
        const klass = hit ? 'pf-name' : 'pf-warn';
        if (!text) {
          note?.remove();
        } else {
          if (!note) {
            note = document.createElement('span');
            container.querySelector('.pf-row-head').after(note);
          }
          note.className = klass;
          note.textContent = text;
        }
        elements.count.textContent =
          `${rows.filter((r) => r.symbol.trim()).length} mã`;
      } else if (event.target.classList.contains('pf-quantity')) {
        row.quantity = event.target.value;
      } else if (event.target.classList.contains('pf-cost')) {
        row.costBasis = event.target.value;
      }
    });

    elements.rows.addEventListener('click', (event) => {
      if (!event.target.classList.contains('pf-remove')) return;
      const container = event.target.closest('.pf-row');
      // Never remove the last row: an empty list has no affordance to start again.
      if (rows.length <= 1) {
        rows = [blankRow()];
      } else {
        rows = rows.filter((r) => r.id !== Number(container.dataset.row));
      }
      renderRows();
    });

    elements.add.addEventListener('click', () => {
      rows.push(blankRow());
      renderRows();
      elements.rows.querySelector('.pf-row:last-child .pf-symbol')?.focus();
    });
  }

  function collect() {
    const holdings = [];
    const seen = new Set();
    for (const row of rows) {
      const symbol = row.symbol.trim().toUpperCase();
      if (!symbol) continue;

      const quantity = parseNumber(row.quantity);
      if (quantity === null || quantity <= 0) {
        throw new Error(`${symbol}: thiếu số lượng, hoặc số lượng không hợp lệ.`);
      }
      if (seen.has(symbol)) throw new Error(`${symbol} bị nhập hai lần.`);
      seen.add(symbol);

      const costBasis = parseNumber(row.costBasis);
      holdings.push({
        symbol,
        quantity,
        cost_basis: costBasis !== null && costBasis > 0 ? costBasis : null,
      });
    }
    if (!holdings.length) throw new Error('Chưa nhập mã nào.');
    return holdings;
  }

  // ---------- result window ----------

  /** Two bars side by side: share of money, share of risk. */
  function riskBars(positions) {
    const scale = Math.max(
      ...positions.map((p) => Math.max(p.weight_pct, p.risk_contribution_pct)), 1,
    );
    return `<div class="pf-bars">
      <div class="rp-chart-head">
        <span class="rp-legend"><i style="background:var(--text-faint)"></i>Phần tiền</span>
        <span class="rp-legend"><i style="background:var(--accent)"></i>Phần rủi ro</span>
      </div>
      ${positions.map((p) => `
        <div class="pf-bar-row">
          <span class="pf-bar-label">${esc(p.symbol)}</span>
          <div class="pf-bar-track">
            <div class="pf-bar weight" style="width:${(p.weight_pct / scale * 100).toFixed(1)}%"></div>
            <div class="pf-bar risk" style="width:${(p.risk_contribution_pct / scale * 100).toFixed(1)}%"></div>
          </div>
          <span class="pf-bar-value ${cls(p.risk_gap_pct)}">${pct(p.risk_gap_pct, 1)}</span>
        </div>`).join('')}
      <p class="table-note">Cột phải là khoảng cách giữa phần rủi ro và phần tiền.
      Dương nghĩa là vị thế đó gánh nhiều rủi ro hơn mức cỡ của nó gợi ý — vì nó
      biến động mạnh hơn, hoặc vì nó đi cùng chiều với phần còn lại, hoặc cả hai.</p>
    </div>`;
  }

  function overviewTab(d) {
    let html = '';
    for (const note of d.notes || []) {
      html += `<div class="callout">${esc(note)}</div>`;
    }

    html += '<div class="metrics">';
    html += metric('Tổng giá trị', dong(d.total_value), '', '',
      `${dong(d.invested_value)} cổ phiếu · ${upct(d.cash_weight_pct)} tiền mặt`);
    html += metric('Lãi/lỗ',
      d.profit === null ? 'không có' : dong(d.profit), '',
      d.profit === null ? '' : cls(d.profit),
      d.profit === null
        ? 'cần giá vốn của mọi mã'
        : pct(d.profit_pct));
    html += metric('Mức rủi ro', esc(d.risk_state),
      Explain.inline({
        title: 'Mức rủi ro',
        what: 'Xếp hạng dựa trên biến động năm và sụt giảm sâu nhất đã xảy ra.',
        rows: [['Biến động (năm)', upct(d.volatility_pct)],
               ['Sụt giảm tối đa', upct(d.max_drawdown_pct)]],
        how: 'Thấp dưới 15% biến động; trung bình tới 25%; đáng chú ý tới 35%; trên đó là cao.',
        watch: 'Đo trên cửa sổ quá khứ đã chọn. Một giai đoạn yên bình cho xếp hạng thấp ngay trước khi thị trường đổi chế độ.',
      }),
      d.risk_state === 'cao' ? 'neg' : '',
      `biến động ${upct(d.volatility_pct)}`);
    html += metric('Beta', d.beta === null ? '—' : nf(d.beta), 'p.beta', '',
      d.beta === null ? 'không đủ phiên chung'
        : d.beta > 1 ? `mạnh hơn VN-Index ${upct((d.beta - 1) * 100)}`
          : `nhẹ hơn VN-Index ${upct((1 - d.beta) * 100)}`);
    html += metric('VaR 95% (1 phiên)', upct(d.var_95_pct), 'p.var', 'neg',
      `CVaR ${upct(d.cvar_95_pct)}`);
    html += metric('Sụt giảm tối đa', upct(d.max_drawdown_pct), 'm.max_dd', 'neg',
      `trong ${d.observations} phiên`);
    html += '</div>';

    html += '<div class="field-group-title">Phần tiền so với phần rủi ro</div>';
    html += riskBars(d.positions);
    return html;
  }

  function positionsTab(d) {
    return `<table class="data-table rp-table"><thead><tr>
      <th>Mã</th><th>Giá</th><th>Giá trị</th><th>Tiền</th>
      <th>Rủi ro ${Explain.button('p.risk_contribution', { title: 'Giải thích đóng góp rủi ro' })}</th>
      <th>Chênh</th><th>Biến động</th><th>Beta</th><th>Lãi/lỗ</th>
      </tr></thead><tbody>` +
      d.positions.map((p) => `<tr>
        <td><strong>${esc(p.symbol)}</strong></td>
        <td>${p.price.toLocaleString('vi-VN')}</td>
        <td>${dong(p.market_value)}</td>
        <td>${upct(p.weight_pct)}</td>
        <td>${upct(p.risk_contribution_pct)}</td>
        <td class="${cls(p.risk_gap_pct)}">${pct(p.risk_gap_pct, 1)}</td>
        <td>${upct(p.volatility_pct)}</td>
        <td>${p.beta === null ? '—' : nf(p.beta)}</td>
        <td class="${p.profit === null ? 'muted' : cls(p.profit)}">
          ${p.profit === null ? '—' : pct(p.profit_pct, 1)}</td>
      </tr>`).join('') +
      `</tbody></table>
      <p class="table-note">Sắp xếp theo phần rủi ro, không theo phần tiền — đó là
      thứ tự quan trọng hơn. Giá là giá đóng cửa phiên ${esc(d.last_session)},
      quy về đồng (feed niêm yết theo nghìn đồng).</p>`;
  }

  function diversificationTab(d) {
    const c = d.concentration;
    let html = `<div class="callout ${c.effective_bets < c.positions * 0.5 ? 'warn' : ''}">
      Danh mục có <strong>${c.positions} mã</strong> nhưng chỉ tương đương
      <strong>${nf(c.effective_bets)} cược độc lập</strong> sau khi trừ đi phần
      tương quan. Tương quan trung bình giữa các cặp là ${nf(c.average_correlation, 3)}.</div>`;

    html += '<div class="metrics">';
    html += metric('Số mã', c.positions, '', '', `lớn nhất ${upct(c.largest_weight_pct)}`);
    html += metric('Số mã hiệu dụng', nf(c.effective_assets), 'p.herfindahl', '',
      `HHI ${nf(c.herfindahl, 3)}`);
    html += metric('Số cược độc lập', nf(c.effective_bets), 'p.effective_bets',
      c.effective_bets < c.positions * 0.5 ? 'neg' : 'pos');
    html += metric('Tương quan TB', nf(c.average_correlation, 3), 'p.correlation');
    html += metric('Ba mã lớn nhất', upct(c.top_three_weight_pct), '',
      c.top_three_weight_pct > 70 ? 'neg' : '');
    html += metric('Cặp giống nhau nhất',
      c.max_pair ? nf(c.max_pair_correlation, 3) : '—', '', '',
      c.max_pair ? c.max_pair.join(' · ') : '');
    html += '</div>';

    html += `<p class="table-note">Số mã hiệu dụng chỉ đếm tiền: mười mã đều nhau
      cho 10, mười mã mà một mã chiếm 80% cho khoảng 1,5. Số cược độc lập đi xa hơn
      và trừ cả phần tương quan — mười mã cùng ngành với tương quan 0,7 hành xử như
      khoảng ba cược, không phải mười.</p>
      <p class="table-note">Hiệp phương sai dùng co rút Ledoit–Wolf
      ${Explain.button('p.shrinkage', { title: 'Giải thích co rút' })}, cường độ
      ${upct(d.shrinkage_intensity * 100)} trên ${d.observations} phiên chung
      (${esc(d.first_session)} → ${esc(d.last_session)}).</p>`;
    return html;
  }

  function forwardTab(d) {
    const f = d.forward;
    if (!f.available) {
      return `<div class="callout warn">${esc(f.reason)}</div>`;
    }

    const worst = Math.max(...f.drawdown_probabilities.map((b) => b.probability_pct), 1);
    let html = `<div class="callout"><strong>Mô phỏng ${f.horizon_days} phiên tới</strong>
      bằng ${f.paths.toLocaleString('vi-VN')} đường đi, lấy mẫu theo khối
      ${nf(f.block_length, 0)} phiên từ chính ${f.observations} phiên lịch sử của
      danh mục này. Lấy theo khối chứ không lấy từng ngày độc lập, để giữ lại hiện
      tượng biến động gom cụm — nếu bỏ nó, xác suất của những đợt sụt sâu bị đánh
      giá thấp một cách có hệ thống.</div>`;

    html += '<div class="metrics">';
    html += metric('Lợi suất kỳ vọng', pct(f.expected_return_pct), '',
      cls(f.expected_return_pct), `trung vị ${pct(f.median_return_pct)}`);
    html += metric('Khoảng 90%',
      `${nf(f.p05_pct)}% … ${nf(f.p95_pct)}%`, '', '', '5% tệ nhất tới 5% tốt nhất');
    html += metric('Xác suất lỗ', upct(f.prob_loss_pct, 0), '',
      f.prob_loss_pct > 50 ? 'neg' : '');
    html += metric('Sụt giảm trung vị', upct(f.median_max_drawdown_pct), 'm.max_dd', 'neg',
      'trong kỳ mô phỏng');
    html += '</div>';

    html += `<div class="field-group-title">Xác suất chạm mỗi mức sụt giảm</div>
      <table class="data-table rp-table"><thead><tr>
        <th>Mức giảm của danh mục</th><th>Xác suất</th><th></th>
      </tr></thead><tbody>` +
      f.drawdown_probabilities.map((b) => `<tr>
        <td>${upct(b.threshold_pct, 0)}</td>
        <td>${upct(b.probability_pct, 0)}</td>
        <td><div class="pf-bar-track slim"><div class="pf-bar risk"
          style="width:${(b.probability_pct / worst * 100).toFixed(1)}%"></div></div></td>
      </tr>`).join('') + '</tbody></table>';

    html += `<div class="callout warn"><strong>Giới hạn của mô phỏng này.</strong>
      ${esc(f.caveat)}</div>`;
    return html;
  }

  function metric(label, value, explain, klass = '', sub = '') {
    const info = !explain ? ''
      : explain.startsWith('<') ? explain
        : Explain.button(explain, { title: `Giải thích ${label}` });
    return `<div class="metric">
      <div class="metric-label">${esc(label)} ${info}</div>
      <div class="metric-value ${klass}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  const TABS = [
    ['overview', 'Tổng quan', overviewTab],
    ['positions', 'Từng mã', positionsTab],
    ['diversification', 'Đa dạng hoá', diversificationTab],
    ['forward', 'Dự phóng', forwardTab],
  ];

  let host = null;
  let activeTab = 'overview';

  function close() {
    host?.remove();
    host = null;
    document.removeEventListener('keydown', onKey, true);
  }

  function onKey(event) {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
  }

  function paint() {
    const body = host.querySelector('.rp-body');
    const tab = TABS.find(([id]) => id === activeTab) || TABS[0];
    try {
      body.innerHTML = tab[2](lastResult);
    } catch (err) {
      body.innerHTML = `<div class="callout bad">Không dựng được tab: ${esc(err.message)}</div>`;
      console.error(err);
    }
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.classList.toggle('active', button.dataset.tab === activeTab);
    }
    body.scrollTop = 0;
  }

  function show(result) {
    lastResult = result;
    close();
    activeTab = 'overview';

    host = document.createElement('div');
    host.className = 'rp-backdrop';
    host.innerHTML = `<div class="rp-window" role="dialog" aria-modal="true"
        aria-labelledby="pf-title">
      <div class="rp-head">
        <div>
          <h2 id="pf-title">Quant Portfolio</h2>
          <div class="rp-sub">${result.positions.length} mã ·
            ${dong(result.total_value)} đồng ·
            ${result.observations} phiên chung
            (${esc(result.first_session)} → ${esc(result.last_session)})</div>
        </div>
        <button class="btn btn-quiet btn-sm rp-close" aria-label="Đóng">✕</button>
      </div>
      <div class="rp-tabs" role="tablist">
        ${TABS.map(([id, label]) =>
          `<button class="rp-tab" data-tab="${id}" role="tab">${label}</button>`).join('')}
      </div>
      <div class="rp-body"></div>
    </div>`;

    document.body.appendChild(host);
    host.querySelector('.rp-close').addEventListener('click', close);
    host.addEventListener('click', (event) => { if (event.target === host) close(); });
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.addEventListener('click', () => {
        activeTab = button.dataset.tab;
        paint();
      });
    }
    document.addEventListener('keydown', onKey, true);
    paint();
  }

  // ---------- wiring ----------

  async function loadSymbols() {
    try {
      const payload = await API.vnSymbols();
      const list = payload.symbols || payload;
      known = new Map(list.map((r) => [r.symbol, { name: r.name || r.symbol }]));
      elements.datalist.innerHTML = list
        .map((r) => `<option value="${esc(r.symbol)}">${esc(r.name || '')}</option>`)
        .join('');
      elements.message.textContent =
        `${known.size} mã trên sàn, sẵn sàng.`;
    } catch (err) {
      // The VPN being off is by far the likeliest cause, and the message the
      // backend already produces says so — so it is passed straight through.
      elements.message.textContent = err.message;
    }
  }

  async function run() {
    let holdings;
    try {
      holdings = collect();
    } catch (err) {
      onToast(err.message, true);
      return;
    }

    const result = await API.portfolioAnalyze({
      holdings,
      cash: parseNumber(elements.cash.value) ?? 0,
      horizonDays: Number(elements.horizon.value) || 63,
      lookbackDays: Number(elements.lookback.value) || 252,
    });
    show(result);
  }

  function init(config) {
    elements = config.elements;
    onToast = config.onToast || (() => {});

    Explain.define('pf.about', {
      title: 'Quant Portfolio',
      what: 'Đo rủi ro thật của một danh mục cổ phiếu Việt Nam đã nhập, dựa trên lịch sử giá của chính các mã đó.',
      how: 'Con số quan trọng nhất là đóng góp rủi ro. Bạn đã biết mỗi mã chiếm bao nhiêu phần trăm tiền; điều bạn không thấy là một mã chiếm 25% tiền có thể chiếm 45% rủi ro, vì nó vừa biến động mạnh hơn vừa đi cùng chiều với phần còn lại.',
      watch: 'Không có gì ở đây đến từ một mô hình dự báo. Tất cả là số học trên lợi suất đã quan sát được, cộng một mô phỏng bootstrap lấy mẫu lại chính những phiên đó. Không có mã nào được lưu lại sau khi phân tích xong.',
      source: 'Chuyển từ tính năng Quant Portfolio của quantpercent.com. Phần tỷ trọng theo ngành bị bỏ vì tài khoản đọc chỉ thấy schema `api`; phần dự phóng được thay bằng bootstrap tự tính thay vì mượn kết quả một mô hình không kiểm chứng được ở đây.',
    });
    Explain.define('pf.lookback', {
      title: 'Cửa sổ đo',
      what: 'Số phiên lịch sử dùng để đo biến động, tương quan và beta.',
      how: 'Một năm giao dịch (252 phiên) là mặc định. Cửa sổ ngắn hơn phản ứng nhanh hơn với chế độ thị trường hiện tại, nhưng ước lượng tương quan từ ít quan sát hơn nên nhiễu hơn.',
      watch: 'Chỉ những phiên mà MỌI mã đều giao dịch mới được dùng. Một mã mới lên sàn sẽ kéo số phiên chung xuống cho cả danh mục.',
    });
    Explain.define('pf.horizon', {
      title: 'Kỳ dự phóng',
      what: 'Mô phỏng nhìn về phía trước bao nhiêu phiên giao dịch.',
      how: '21 / 63 / 126 / 252 phiên tương ứng 1 tháng, 3 tháng, 6 tháng và 1 năm.',
      watch: 'Kỳ càng dài thì mô phỏng càng phụ thuộc vào giả định rằng chế độ thị trường trong cửa sổ quá khứ còn tiếp tục. Với kỳ một năm, đó là một giả định lớn.',
    });

    rows = [blankRow(), blankRow()];
    renderRows();
    bindRows();

    elements.run.addEventListener('click', () => config.withButton(
      elements.run, 'Đang phân tích…', run,
    ));

    loadSymbols();
  }

  return { init, show, close, get last() { return lastResult; } };
})();
