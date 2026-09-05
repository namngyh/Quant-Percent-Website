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

  /* The backend grades risk with a Vietnamese word. Translating at the edge
     keeps that value a stable key the API can be tested against, rather than
     making the payload depend on who is looking at it. */
  const riskState = (state) => ({
    'thấp': L('thấp', 'low'),
    'trung bình': L('trung bình', 'moderate'),
    'đáng chú ý': L('đáng chú ý', 'elevated'),
    'cao': L('cao', 'high'),
  }[state] || state);

  /** Money in dong, abbreviated — 563.240.000 does not read at a glance. */
  function dong(value) {
    if (!Number.isFinite(value)) return '—';
    const magnitude = Math.abs(value);
    if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)}${L(' tỷ', 'bn')}`;
    if (magnitude >= 1e6) return `${(value / 1e6).toFixed(1)}${L(' tr', 'm')}`;
    return value.toLocaleString(I18n.locale(), { maximumFractionDigits: 0 });
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
          : known.size
            ? `<span class="pf-warn">${esc(t('pf.unknown'))}</span>` : '';

      return `<div class="pf-row" data-row="${row.id}">
        <div class="pf-row-head">
          <input class="pf-symbol" list="pf-symbols" value="${esc(row.symbol)}"
                 placeholder="FPT" autocomplete="off" spellcheck="false" />
          <button class="pf-remove" title="${esc(t('pf.remove'))}"
                  aria-label="${esc(t('pf.remove'))}">✕</button>
        </div>
        ${note}
        <div class="pf-row-fields">
          <label><span>${esc(t('pf.quantity'))}</span>
            <input class="pf-quantity" inputmode="numeric" value="${esc(row.quantity)}"
                   placeholder="1.000" /></label>
          <label><span>${esc(t('pf.costBasis'))}</span>
            <input class="pf-cost" inputmode="numeric" value="${esc(row.costBasis)}"
                   placeholder="${esc(t('pf.optional'))}" /></label>
        </div>
      </div>`;
    }).join('');

    elements.count.textContent =
      t('pf.symbolCount', { n: rows.filter((r) => r.symbol.trim()).length });
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
        const text = !code ? '' : hit ? hit.name : (known.size ? t('pf.unknown') : '');
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
          t('pf.symbolCount', { n: rows.filter((r) => r.symbol.trim()).length });
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

    document.querySelectorAll('.pf-quick-chip').forEach((chip) => {
      chip.addEventListener('click', () => {
        const sym = chip.dataset.sym;
        if (!sym) return;
        const code = sym.trim().toUpperCase();
        const existing = rows.find((r) => r.symbol.trim().toUpperCase() === code);
        if (existing) {
          elements.rows.querySelector(`.pf-row[data-row="${existing.id}"] .pf-quantity`)?.focus();
          return;
        }
        let targetRow = rows.find((r) => !r.symbol.trim());
        if (targetRow) {
          targetRow.symbol = code;
          if (!targetRow.quantity) targetRow.quantity = '1000';
        } else {
          targetRow = { id: nextId++, symbol: code, quantity: '1000', costBasis: '' };
          rows.push(targetRow);
        }
        renderRows();
        elements.rows.querySelector(`.pf-row[data-row="${targetRow.id}"] .pf-quantity`)?.focus();
      });
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
        throw new Error(t('pf.badQuantity', { sym: symbol }));
      }
      if (seen.has(symbol)) throw new Error(t('pf.duplicate', { sym: symbol }));
      seen.add(symbol);

      const costBasis = parseNumber(row.costBasis);
      holdings.push({
        symbol,
        quantity,
        cost_basis: costBasis !== null && costBasis > 0 ? costBasis : null,
      });
    }
    if (!holdings.length) throw new Error(t('pf.empty'));
    return holdings;
  }

  // ---------- result window & visual charts ----------

  const DONUT_PALETTE = [
    '#18181b', '#2563eb', '#10b981', '#f59e0b', '#8b5cf6',
    '#ec4899', '#06b6d4', '#6366f1', '#64748b', '#84cc16'
  ];

  function polarToCartesian(centerX, centerY, radius, angleInDegrees) {
    const angleInRadians = ((angleInDegrees - 90) * Math.PI) / 180.0;
    return {
      x: centerX + radius * Math.cos(angleInRadians),
      y: centerY + radius * Math.sin(angleInRadians),
    };
  }

  function donutSlicePath(cx, cy, rOuter, rInner, startAngle, endAngle) {
    const angleDiff = endAngle - startAngle;
    const effectiveEnd = angleDiff >= 360 ? startAngle + 359.99 : endAngle;
    const p1 = polarToCartesian(cx, cy, rOuter, startAngle);
    const p2 = polarToCartesian(cx, cy, rOuter, effectiveEnd);
    const p3 = polarToCartesian(cx, cy, rInner, effectiveEnd);
    const p4 = polarToCartesian(cx, cy, rInner, startAngle);
    const largeArc = angleDiff > 180 ? 1 : 0;
    return `M ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${p2.x.toFixed(2)} ${p2.y.toFixed(2)} L ${p3.x.toFixed(2)} ${p3.y.toFixed(2)} A ${rInner} ${rInner} 0 ${largeArc} 0 ${p4.x.toFixed(2)} ${p4.y.toFixed(2)} Z`;
  }

  function donutChart(d) {
    const items = [];
    if (d.cash > 0 && d.cash_weight_pct > 0.05) {
      items.push({
        label: L('Tiền mặt', 'Cash'),
        symbol: 'CASH',
        value: d.cash,
        pct: d.cash_weight_pct,
        color: '#71717a',
      });
    }
    (d.positions || []).forEach((p, idx) => {
      items.push({
        label: p.symbol,
        symbol: p.symbol,
        value: p.market_value,
        pct: p.weight_pct,
        color: DONUT_PALETTE[idx % DONUT_PALETTE.length],
      });
    });

    if (!items.length) return '';

    const cx = 110, cy = 110, rOuter = 85, rInner = 56;
    let currentAngle = 0;
    const slicesHtml = items.map((item) => {
      const sliceAngle = (item.pct / 100) * 360;
      const startAngle = currentAngle;
      const endAngle = currentAngle + sliceAngle;
      currentAngle = endAngle;
      const pathD = donutSlicePath(cx, cy, rOuter, rInner, startAngle, endAngle);
      return `<path class="pf-donut-slice" d="${pathD}" fill="${item.color}"
        data-sym="${esc(item.label)}" data-val="${dong(item.value)}" data-pct="${item.pct.toFixed(1)}%" />`;
    }).join('');

    const legendHtml = items.map((item) => `
      <div class="pf-legend-item" data-sym="${esc(item.label)}" data-val="${dong(item.value)}" data-pct="${item.pct.toFixed(1)}%">
        <span class="pf-legend-dot" style="background:${item.color}"></span>
        <span class="pf-legend-sym">${esc(item.label)}</span>
        <span class="pf-legend-pct">${item.pct.toFixed(1)}%</span>
      </div>
    `).join('');

    return `<div class="pf-visual-card">
      <div class="field-group-title" style="margin-bottom:12px">${esc(L('Phân bổ tài sản trong danh mục', 'Portfolio Asset Allocation'))}</div>
      <div class="pf-donut-layout">
        <svg class="pf-donut-svg" viewBox="0 0 220 220" id="pf-donut-svg">
          ${slicesHtml}
          <circle cx="${cx}" cy="${cy}" r="${rInner - 2}" fill="var(--surface)" />
          <text x="${cx}" y="${cy - 7}" text-anchor="middle" class="pf-donut-center-title" id="pf-donut-center-title">${esc(L('Tổng tài sản', 'Total Assets'))}</text>
          <text x="${cx}" y="${cy + 14}" text-anchor="middle" class="pf-donut-center-val" id="pf-donut-center-val">${dong(d.total_value)}</text>
        </svg>
        <div class="pf-legend-grid">${legendHtml}</div>
      </div>
    </div>`;
  }

  /** Two bars side by side: share of money, share of risk. */
  function riskBars(positions) {
    const scale = Math.max(
      ...positions.map((p) => Math.max(p.weight_pct, p.risk_contribution_pct)), 1,
    );
    return `<div class="pf-bars">
      <div class="rp-chart-head">
        <span class="rp-legend"><i style="background:var(--text-faint)"></i>${
          esc(L('Phần tiền (% Vốn)', 'Share of money'))}</span>
        <span class="rp-legend"><i style="background:var(--accent)"></i>${
          esc(L('Phần rủi ro (% Đóng góp)', 'Share of risk'))}</span>
      </div>
      ${positions.map((p) => {
        const gap = p.risk_gap_pct;
        const gapCls = gap > 5 ? 'alert' : gap < -5 ? 'safe' : 'neutral';
        const gapText = gap > 0 ? `+${gap.toFixed(1)}%` : `${gap.toFixed(1)}%`;
        return `
        <div class="pf-bar-row">
          <span class="pf-bar-badge">${esc(p.symbol)}</span>
          <div class="pf-bar-track">
            <div class="pf-bar weight" style="width:${(p.weight_pct / scale * 100).toFixed(1)}%" title="${esc(L('Tiền', 'Money'))}: ${p.weight_pct.toFixed(1)}%"></div>
            <div class="pf-bar risk" style="width:${(p.risk_contribution_pct / scale * 100).toFixed(1)}%" title="${esc(L('Rủi ro', 'Risk'))}: ${p.risk_contribution_pct.toFixed(1)}%"></div>
          </div>
          <span class="pf-bar-gap ${gapCls}" title="${esc(L('Chênh lệch rủi ro', 'Risk gap'))}">${gapText}</span>
        </div>`;
      }).join('')}
      <p class="table-note">${esc(L(
        'Cột phải là chênh lệch giữa phần rủi ro và phần tiền. Số dương (đỏ) nghĩa là vị thế đó gánh nhiều rủi ro hơn tỷ trọng vốn gợi ý — do biến động mạnh hơn hoặc tương quan cao với rổ còn lại.',
        'The right column is the gap between share of risk and share of money. Positive means the position carries more risk than its size suggests.'))}</p>
    </div>`;
  }

  function correlationHeatmap(d) {
    const c = d.concentration;
    const symbols = c.symbols || d.positions.map((p) => p.symbol);
    const matrix = c.correlation_matrix;
    if (!matrix || matrix.length < 2) return '';

    const headerTh = symbols.map((s) => `<th class="pf-heatmap-th">${esc(s)}</th>`).join('');
    const rowsHtml = matrix.map((row, i) => {
      const symA = symbols[i];
      const cells = row.map((r, j) => {
        const symB = symbols[j];
        if (i === j) {
          return `<td class="pf-heatmap-cell" style="background:var(--surface-3); color:var(--text); border:1px solid var(--border);" title="${esc(symA)}: 1.00">1.00</td>`;
        }
        let bg, col;
        if (r >= 0.7) {
          bg = `rgba(220, 38, 38, ${0.15 + (r - 0.7) * 1.5})`;
          col = '#dc2626';
        } else if (r >= 0.4) {
          bg = `rgba(217, 119, 6, ${0.12 + (r - 0.4) * 1.0})`;
          col = '#d97706';
        } else if (r >= 0) {
          bg = `rgba(16, 185, 129, ${0.10 + (0.4 - r) * 0.5})`;
          col = '#059669';
        } else {
          bg = 'rgba(16, 185, 129, 0.35)';
          col = '#047857';
        }
        return `<td class="pf-heatmap-cell" style="background:${bg}; color:${col};" title="${esc(L(`Tương quan giữa ${symA} và ${symB}: ${r.toFixed(3)}`, `Correlation ${symA} & ${symB}: ${r.toFixed(3)}`))}">${r.toFixed(2)}</td>`;
      }).join('');
      return `<tr><th class="pf-heatmap-th">${esc(symA)}</th>${cells}</tr>`;
    }).join('');

    return `<div class="pf-heatmap-wrap">
      <div class="pf-heatmap-head">
        <span class="pf-heatmap-title">${esc(L('Ma trận nhiệt tương quan giữa các cặp mã (Correlation Heatmap)', 'Pairwise Correlation Heatmap Matrix'))}</span>
        <div class="pf-heatmap-legend">
          <span>${esc(L('Phân tán tốt (< 0.4)', 'Well diversified'))}</span>
          <span class="pf-scale-bar"></span>
          <span>${esc(L('Tương quan cao (> 0.7)', 'High correlation'))}</span>
        </div>
      </div>
      <table class="pf-heatmap-table">
        <thead><tr><th></th>${headerTh}</tr></thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
  }

  function forwardCharts(f) {
    let html = '<div class="pf-forward-charts">';

    // 1. Fan chart if fan_steps is available
    if (f.fan_steps && f.fan_steps.length > 2) {
      const steps = f.fan_steps;
      const minVal = Math.min(...steps.map(s => s.p05), -5);
      const maxVal = Math.max(...steps.map(s => s.p95), 5);
      const range = (maxVal - minVal) || 1;
      const W = 600, H = 200, padL = 48, padR = 20, padT = 20, padB = 30;
      const plotW = W - padL - padR;
      const plotH = H - padT - padB;

      const getX = (idx) => padL + (idx / (steps.length - 1)) * plotW;
      const getY = (val) => padT + plotH - ((val - minVal) / range) * plotH;

      const pts90Top = steps.map((s, i) => `${getX(i).toFixed(1)},${getY(s.p95).toFixed(1)}`).join(' ');
      const pts90Bot = [...steps].reverse().map((s, i) => `${getX(steps.length - 1 - i).toFixed(1)},${getY(s.p05).toFixed(1)}`).join(' ');
      const poly90 = `${pts90Top} ${pts90Bot}`;

      const pts50Top = steps.map((s, i) => `${getX(i).toFixed(1)},${getY(s.p75).toFixed(1)}`).join(' ');
      const pts50Bot = [...steps].reverse().map((s, i) => `${getX(steps.length - 1 - i).toFixed(1)},${getY(s.p25).toFixed(1)}`).join(' ');
      const poly50 = `${pts50Top} ${pts50Bot}`;

      const medLine = steps.map((s, i) => `${getX(i).toFixed(1)},${getY(s.p50).toFixed(1)}`).join(' ');
      const zeroY = getY(0);

      html += `<div class="pf-visual-card">
        <div class="field-group-title" style="margin-bottom:8px">${esc(L('Mô phỏng đường đi danh mục tương lai (Monte Carlo Fan Chart)', 'Monte Carlo Trajectory Fan Chart'))}</div>
        <svg class="pf-fan-svg" viewBox="0 0 ${W} ${H}">
          ${zeroY >= padT && zeroY <= padT + plotH ? `<line x1="${padL}" y1="${zeroY}" x2="${W - padR}" y2="${zeroY}" stroke="var(--border)" stroke-dasharray="4,4" stroke-width="1.5" />` : ''}
          <polygon points="${poly90}" fill="rgba(31, 31, 31, 0.08)" />
          <polygon points="${poly50}" fill="rgba(31, 31, 31, 0.16)" />
          <polyline points="${medLine}" fill="none" stroke="var(--accent)" stroke-width="2.5" />
          <text x="${padL}" y="${padT + 10}" font-size="10" fill="var(--text-faint)" font-family="var(--mono)">+${maxVal.toFixed(1)}%</text>
          <text x="${padL}" y="${padT + plotH}" font-size="10" fill="var(--text-faint)" font-family="var(--mono)">${minVal.toFixed(1)}%</text>
          <text x="${padL}" y="${H - 10}" font-size="10" fill="var(--text-dim)">${esc(L('Phiên 1', 'Session 1'))}</text>
          <text x="${W - padR}" y="${H - 10}" text-anchor="end" font-size="10" fill="var(--text-dim)">${esc(L(`Phiên ${f.horizon_days}`, `Session ${f.horizon_days}`))}</text>
        </svg>
        <div class="rp-chart-head" style="margin-top:8px; justify-content:center">
          <span class="rp-legend"><i style="background:rgba(31, 31, 31, 0.15)"></i>${esc(L('Vùng 90% (P05–P95)', '90% Confidence Interval'))}</span>
          <span class="rp-legend"><i style="background:rgba(31, 31, 31, 0.32)"></i>${esc(L('Vùng 50% (P25–P75)', 'Interquartile 50%'))}</span>
          <span class="rp-legend"><i style="background:var(--accent); height:3px"></i>${esc(L('Đường trung vị (P50)', 'Median'))}</span>
        </div>
      </div>`;
    }

    // 2. Drawdown Probability Visual Bars
    const worst = Math.max(...f.drawdown_probabilities.map((b) => b.probability_pct), 1);
    html += `<div class="pf-visual-card">
      <div class="field-group-title" style="margin-bottom:10px">${esc(L('Phân phối xác suất sụt giảm (Drawdown Distribution)', 'Chance of Reaching Drawdown Levels'))}</div>
      <table class="data-table rp-table"><thead><tr>
        <th>${esc(L('Mức sụt giảm danh mục', 'Portfolio fall'))}</th>
        <th>${esc(L('Xác suất chạm', 'Probability'))}</th><th>${esc(L('Thước đo trực quan', 'Visual Probability Bar'))}</th>
      </tr></thead><tbody>` +
      f.drawdown_probabilities.map((b) => {
        const p = b.probability_pct;
        const color = p > 50 ? 'var(--down)' : p > 20 ? 'var(--warn)' : 'var(--text-dim)';
        return `<tr>
          <td><strong>${upct(b.threshold_pct, 0)}</strong></td>
          <td style="font-family:var(--mono); font-weight:600; color:${color}">${upct(p, 1)}</td>
          <td style="width:55%"><div class="pf-bar-track slim"><div class="pf-bar"
            style="width:${(p / worst * 100).toFixed(1)}%; background:${color}"></div></div></td>
        </tr>`;
      }).join('') + '</tbody></table></div>';

    html += '</div>';
    return html;
  }

  function overviewTab(d) {
    let html = '';
    for (const note of d.notes || []) {
      html += `<div class="callout">${esc(tp(note) || note)}</div>`;
    }

    html += '<div class="metrics">';
    html += metric(L('Tổng giá trị', 'Total value'), dong(d.total_value), '', '',
      L(`${dong(d.invested_value)} cổ phiếu · ${upct(d.cash_weight_pct)} tiền mặt`,
        `${dong(d.invested_value)} in shares · ${upct(d.cash_weight_pct)} cash`));
    html += metric(L('Lãi/lỗ', 'Profit'),
      d.profit === null ? t('common.notAvailable') : dong(d.profit), '',
      d.profit === null ? '' : cls(d.profit),
      d.profit === null
        ? L('cần giá vốn của mọi mã', 'needs a cost basis on every holding')
        : pct(d.profit_pct));
    html += metric(L('Mức rủi ro', 'Risk level'), esc(riskState(d.risk_state)),
      Explain.inline({
        title: L('Mức rủi ro', 'Risk level'),
        what: L('Xếp hạng dựa trên biến động năm và sụt giảm sâu nhất đã xảy ra.',
                'A grade based on annualised volatility and the deepest drawdown on record.'),
        rows: [[L('Biến động (năm)', 'Volatility (annual)'), upct(d.volatility_pct)],
               [L('Sụt giảm tối đa', 'Max drawdown'), upct(d.max_drawdown_pct)]],
        how: L('Thấp dưới 15% biến động; trung bình tới 25%; đáng chú ý tới 35%; trên đó là cao.',
                'Low below 15% volatility; moderate to 25%; elevated to 35%; high above that.'),
        watch: L('Đo trên cửa sổ quá khứ đã chọn. Một giai đoạn yên bình cho xếp hạng thấp ngay trước khi thị trường đổi chế độ.',
                 'Measured over the chosen past window. A calm stretch grades low right up to the moment the regime changes.'),
      }),
      d.risk_state === 'cao' ? 'neg' : '',
      L(`biến động ${upct(d.volatility_pct)}`, `${upct(d.volatility_pct)} volatility`));
    html += metric('Beta', d.beta === null ? '—' : nf(d.beta), 'p.beta', '',
      d.beta === null ? L('không đủ phiên chung', 'not enough shared sessions')
        : d.beta > 1
          ? L(`mạnh hơn VN-Index ${upct((d.beta - 1) * 100)}`,
              `${upct((d.beta - 1) * 100)} more than VN-Index`)
          : L(`nhẹ hơn VN-Index ${upct((1 - d.beta) * 100)}`,
              `${upct((1 - d.beta) * 100)} less than VN-Index`));
    html += metric(L('VaR 95% (1 phiên)', 'VaR 95% (one session)'), upct(d.var_95_pct),
      'p.var', 'neg', `CVaR ${upct(d.cvar_95_pct)}`);
    html += metric(L('Sụt giảm tối đa', 'Max drawdown'), upct(d.max_drawdown_pct),
      'm.max_dd', 'neg',
      L(`trong ${d.observations} phiên`, `over ${d.observations} sessions`));
    html += '</div>';

    // SVG Asset Allocation Donut Chart
    html += donutChart(d);

    // Paired Money vs Risk Bar Chart
    html += `<div class="field-group-title" style="margin-top:18px">${esc(L(
      'Tỷ trọng tiền so với đóng góp rủi ro', 'Share of money against share of risk'))}</div>`;
    html += riskBars(d.positions);
    return html;
  }

  function positionsTab(d) {
    return `<div class="pf-visual-card">
      <div class="field-group-title" style="margin-bottom:12px">${esc(L('Chi tiết từng vị thế trong danh mục', 'Holdings Breakdown'))}</div>
      <table class="data-table rp-table"><thead><tr>
        <th>${esc(L('Mã', 'Symbol'))}</th><th>${esc(L('Giá đóng cửa', 'Close Price'))}</th>
        <th>${esc(L('Giá trị', 'Market Value'))}</th><th>${esc(L('Tỷ trọng tiền', 'Money Weight'))}</th>
        <th>${esc(L('Đóng góp rủi ro', 'Risk Contribution'))} ${Explain.button('p.risk_contribution', {
          title: L('Giải thích đóng góp rủi ro', 'Explain risk contribution') })}</th>
        <th>${esc(L('Chênh lệch', 'Risk Gap'))}</th><th>${esc(L('Biến động/năm', 'Volatility'))}</th>
        <th>Beta</th><th>${esc(L('Lãi/lỗ', 'P&L'))}</th>
      </tr></thead><tbody>` +
      d.positions.map((p) => {
        const gap = p.risk_gap_pct;
        const gapCls = gap > 5 ? 'alert' : gap < -5 ? 'safe' : 'neutral';
        return `<tr>
          <td><span class="pf-bar-badge">${esc(p.symbol)}</span></td>
          <td style="font-family:var(--mono)">${p.price.toLocaleString(I18n.locale())} đ</td>
          <td style="font-family:var(--mono)">${dong(p.market_value)}</td>
          <td style="font-family:var(--mono)">${upct(p.weight_pct)}</td>
          <td style="font-family:var(--mono); font-weight:600">${upct(p.risk_contribution_pct)}</td>
          <td><span class="pf-bar-gap ${gapCls}">${pct(gap, 1)}</span></td>
          <td style="font-family:var(--mono)">${upct(p.volatility_pct)}</td>
          <td style="font-family:var(--mono)">${p.beta === null ? '—' : nf(p.beta)}</td>
          <td class="${p.profit === null ? 'muted' : cls(p.profit)}" style="font-family:var(--mono)">
            ${p.profit === null ? '—' : pct(p.profit_pct, 1)}</td>
        </tr>`;
      }).join('') +
      `</tbody></table>
      <p class="table-note">${esc(L(
        `Sắp xếp theo phần rủi ro, không theo phần tiền — đó là thứ tự quan trọng hơn. Giá là giá đóng cửa phiên ${d.last_session}, quy về đồng (feed niêm yết theo nghìn đồng).`,
        `Sorted by share of risk rather than share of money — that is the order that matters. Prices are the close of ${d.last_session}, converted to dong (the feed quotes in thousands).`))}</p>
    </div>`;
  }

  function diversificationTab(d) {
    const c = d.concentration;
    let html = `<div class="callout ${c.effective_bets < c.positions * 0.5 ? 'warn' : ''}">
      ${esc(L(
        `Danh mục có ${c.positions} mã nhưng chỉ tương đương ${nf(c.effective_bets)} cược độc lập sau khi trừ đi phần tương quan. Tương quan trung bình giữa các cặp là ${nf(c.average_correlation, 3)}.`,
        `The portfolio holds ${c.positions} names but amounts to only ${nf(c.effective_bets)} independent bets once correlation is taken out. The average pairwise correlation is ${nf(c.average_correlation, 3)}.`))}</div>`;

    html += '<div class="metrics">';
    html += metric(L('Số mã', 'Positions'), c.positions, '', '',
      L(`lớn nhất ${upct(c.largest_weight_pct)}`, `largest ${upct(c.largest_weight_pct)}`));
    html += metric(L('Số mã hiệu dụng', 'Effective assets'), nf(c.effective_assets),
      'p.herfindahl', '', `HHI ${nf(c.herfindahl, 3)}`);
    html += metric(L('Số cược độc lập', 'Effective bets'), nf(c.effective_bets),
      'p.effective_bets', c.effective_bets < c.positions * 0.5 ? 'neg' : 'pos');
    html += metric(L('Tương quan TB', 'Average correlation'),
      nf(c.average_correlation, 3), 'p.correlation');
    html += metric(L('Ba mã lớn nhất', 'Top three'), upct(c.top_three_weight_pct), '',
      c.top_three_weight_pct > 70 ? 'neg' : '');
    html += metric(L('Cặp giống nhau nhất', 'Closest pair'),
      c.max_pair ? nf(c.max_pair_correlation, 3) : '—', '', '',
      c.max_pair ? c.max_pair.join(' · ') : '');
    html += '</div>';

    // Interactive Correlation Heatmap Matrix
    html += correlationHeatmap(d);

    html += `<p class="table-note" style="margin-top:14px">${esc(L(
      'Số mã hiệu dụng chỉ đếm tiền: mười mã đều nhau cho 10, mười mã mà một mã chiếm 80% cho khoảng 1,5. Số cược độc lập đi xa hơn và trừ cả phần tương quan — mười mã cùng ngành với tương quan 0,7 hành xử như khoảng ba cược, không phải mười.',
      'Effective assets counts money only: ten equal names give 10, ten names where one holds 80% give about 1.5. Effective bets goes further and removes correlation — ten names in one sector correlated at 0.7 behave like about three bets, not ten.'))}</p>
      <p class="table-note">${esc(L('Hiệp phương sai dùng co rút Ledoit–Wolf',
        'Covariance uses Ledoit–Wolf shrinkage'))}
      ${Explain.button('p.shrinkage', { title: L('Giải thích co rút', 'Explain shrinkage') })},
      ${esc(L(
        `cường độ ${upct(d.shrinkage_intensity * 100)} trên ${d.observations} phiên chung (${d.first_session} → ${d.last_session}).`,
        `intensity ${upct(d.shrinkage_intensity * 100)} over ${d.observations} shared sessions (${d.first_session} → ${d.last_session}).`))}</p>`;
    return html;
  }

  function forwardTab(d) {
    const f = d.forward;
    if (!f.available) {
      return `<div class="callout warn">${esc(tp(f.reason) || f.reason)}</div>`;
    }

    const paths = f.paths.toLocaleString(I18n.locale());
    let html = `<div class="callout"><strong>${esc(L(
      `Mô phỏng ${f.horizon_days} phiên tới`,
      `Simulating the next ${f.horizon_days} sessions`))}</strong>
      ${esc(L(
        `bằng ${paths} đường đi, lấy mẫu theo khối ${nf(f.block_length, 0)} phiên từ chính ${f.observations} phiên lịch sử của danh mục này. Lấy theo khối chứ không lấy từng ngày độc lập, để giữ lại hiện tượng biến động gom cụm — nếu bỏ nó, xác suất của những đợt sụt sâu bị đánh giá thấp một cách có hệ thống.`,
        `over ${paths} paths, sampled in blocks of ${nf(f.block_length, 0)} sessions from this portfolio's own ${f.observations} sessions of history. Blocks rather than independent days, to keep volatility clustering — dropping it systematically understates the odds of a deep fall.`))}</div>`;

    html += '<div class="metrics">';
    html += metric(L('Lợi suất kỳ vọng', 'Expected return'), pct(f.expected_return_pct),
      '', cls(f.expected_return_pct),
      L(`trung vị ${pct(f.median_return_pct)}`, `median ${pct(f.median_return_pct)}`));
    html += metric(L('Khoảng 90%', '90% range'),
      `${nf(f.p05_pct)}% … ${nf(f.p95_pct)}%`, '', '',
      L('5% tệ nhất tới 5% tốt nhất', 'worst 5% to best 5%'));
    html += metric(L('Xác suất lỗ', 'Chance of a loss'), upct(f.prob_loss_pct, 0), '',
      f.prob_loss_pct > 50 ? 'neg' : '');
    html += metric(L('Sụt giảm trung vị', 'Median drawdown'),
      upct(f.median_max_drawdown_pct), 'm.max_dd', 'neg',
      L('trong kỳ mô phỏng', 'within the simulated period'));
    html += '</div>';

    // Interactive Forward Visual Charts (Fan Chart & Drawdown Distribution)
    html += forwardCharts(f);

    html += `<div class="callout warn" style="margin-top:14px"><strong>${esc(L(
      'Giới hạn của mô phỏng này.', 'What this simulation cannot do.'))}</strong>
      ${esc(tp(f.caveat) || f.caveat)}</div>`;
    return html;
  }

  function attachDonutInteractions() {
    if (!host) return;
    const centerTitle = host.querySelector('#pf-donut-center-title');
    const centerVal = host.querySelector('#pf-donut-center-val');
    if (!centerTitle || !centerVal || !lastResult) return;

    const defaultTitle = L('Tổng tài sản', 'Total Assets');
    const defaultVal = dong(lastResult.total_value);

    host.querySelectorAll('.pf-donut-slice, .pf-legend-item').forEach((item) => {
      item.addEventListener('mouseenter', () => {
        const sym = item.dataset.sym;
        const val = item.dataset.val;
        const pct = item.dataset.pct;
        if (sym && val) {
          centerTitle.textContent = sym;
          centerVal.textContent = `${val} (${pct})`;
        }
      });
      item.addEventListener('mouseleave', () => {
        centerTitle.textContent = defaultTitle;
        centerVal.textContent = defaultVal;
      });
    });
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
    ['overview', 'pfr.overview', overviewTab],
    ['positions', 'pfr.positions', positionsTab],
    ['diversification', 'pfr.diversification', diversificationTab],
    ['forward', 'pfr.forward', forwardTab],
  ];

  const tabMarkup = () => TABS.map(([id, key]) =>
    `<button class="rp-tab" data-tab="${id}" role="tab">${esc(t(key))}</button>`).join('');

  function bindTabs() {
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.addEventListener('click', () => {
        activeTab = button.dataset.tab;
        paint();
      });
    }
  }

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
      if (activeTab === 'overview') {
        attachDonutInteractions();
      }
    } catch (err) {
      body.innerHTML = `<div class="callout bad">${esc(L(
        'Không dựng được tab: ', 'Could not build this tab: '))}${esc(err.message)}</div>`;
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
          <div class="rp-sub">${esc(t('pf.symbolCount', { n: result.positions.length }))} ·
            ${dong(result.total_value)} ·
            ${esc(t('common.sessions', {
              n: result.observations,
              from: result.first_session,
              to: result.last_session,
            }))}</div>
        </div>
        <button class="btn btn-quiet btn-sm rp-close"
                aria-label="${esc(t('rp.close'))}">✕</button>
      </div>
      <div class="rp-tabs" role="tablist">${tabMarkup()}</div>
      <div class="rp-body"></div>
    </div>`;

    document.body.appendChild(host);
    host.querySelector('.rp-close').addEventListener('click', close);
    host.addEventListener('click', (event) => { if (event.target === host) close(); });
    bindTabs();
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
      elements.message.textContent = t('pf.ready', { n: known.size });
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

  /** Redraw the form, and the result window if it is open. */
  function rerender() {
    renderRows();
    if (!host || !lastResult) return;
    host.querySelector('.rp-tabs').innerHTML = tabMarkup();
    bindTabs();
    paint();
  }

  return { init, show, close, rerender, get last() { return lastResult; } };
})();
