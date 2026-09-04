/* The full backtest report, in a window of its own.
 *
 * The results panel beside the chart answers "did it make money". This answers
 * "why", and that needs more room than a 344px column: a monthly return table,
 * long and short broken out side by side, excursion scatter, classification
 * metrics. So it opens centred over the page, and closes back to exactly the
 * chart you were looking at.
 *
 * Charts here are hand-drawn SVG rather than the chart library. Lightweight
 * Charts is built for price series on a time axis with crosshairs and panning;
 * a static drawdown ribbon or a scatter of 88 trades wants none of that, and
 * an SVG string costs nothing to throw away when the tab changes.
 */

const Report = (() => {
  let host = null;
  let data = null;
  let activeTab = 'overview';
  let onToast = () => {};

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

  // ---------- formatting ----------

  const nf = (value, digits = 2) =>
    Number.isFinite(value) ? value.toFixed(digits) : '—';

  const pct = (value, digits = 2) =>
    Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(digits)}%` : '—';

  /** Unsigned percent, for quantities that have no direction (exposure, win rate). */
  const upct = (value, digits = 1) =>
    Number.isFinite(value) ? `${value.toFixed(digits)}%` : '—';

  const money = (value) =>
    Number.isFinite(value)
      ? value.toLocaleString('vi-VN', { maximumFractionDigits: 0 })
      : '—';

  const ratio = (value) => {
    if (!Number.isFinite(value)) return value === Infinity ? '∞' : '—';
    return value.toFixed(2);
  };

  const cls = (value) => (value > 0 ? 'pos' : value < 0 ? 'neg' : '');

  const MONTHS = ['T1', 'T2', 'T3', 'T4', 'T5', 'T6',
                  'T7', 'T8', 'T9', 'T10', 'T11', 'T12'];

  // ---------- small chart primitives ----------

  /** Map a series of {t, v} onto an SVG path in a fixed 1000×H viewBox. */
  function pathFor(points, height, minimum, maximum) {
    if (!points.length) return '';
    const span = maximum - minimum || 1;
    return points.map((p, i) => {
      const x = (i / Math.max(points.length - 1, 1)) * 1000;
      const y = height - ((p.v - minimum) / span) * height;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  /** Equity against buy-and-hold, on one axis because both start at the same capital. */
  function equityChart(report) {
    const equity = report.charts.equity;
    const hold = report.charts.buy_hold;
    if (!equity.length) return '';

    const all = [...equity.map((p) => p.v), ...hold.map((p) => p.v)];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const H = 220;

    const start = new Date((equity[0].t + 7 * 3600) * 1000);
    const end = new Date((equity[equity.length - 1].t + 7 * 3600) * 1000);
    const day = (d) => d.toISOString().slice(0, 10);

    return `<div class="rp-chart">
      <div class="rp-chart-head">
        <span class="rp-legend"><i style="background:var(--accent)"></i>Chiến lược</span>
        <span class="rp-legend"><i style="background:var(--text-faint)"></i>Mua và giữ</span>
      </div>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
           aria-label="Đường vốn so với mua và giữ">
        <path d="${pathFor(hold, H, min, max)}" fill="none"
              stroke="var(--text-faint)" stroke-width="2" vector-effect="non-scaling-stroke"/>
        <path d="${pathFor(equity, H, min, max)}" fill="none"
              stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="rp-axis"><span>${day(start)}</span>
        <span>${money(min)} – ${money(max)}</span><span>${day(end)}</span></div>
    </div>`;
  }

  /** Drawdown as a filled ribbon hanging from zero — it is always negative. */
  function drawdownChart(report) {
    const series = report.charts.drawdown;
    if (!series.length) return '';
    const worst = Math.min(...series.map((p) => p.v), -1);
    const H = 140;
    const area = pathFor(series, H, worst, 0);
    return `<div class="rp-chart">
      <div class="rp-chart-head"><span class="rp-legend">
        <i style="background:var(--down)"></i>Sụt giảm từ đỉnh</span></div>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
           aria-label="Sụt giảm theo thời gian">
        <path d="${area} L1000,0 L0,0 Z" fill="var(--down-soft)" stroke="none"/>
        <path d="${area}" fill="none" stroke="var(--down)" stroke-width="1.5"
              vector-effect="non-scaling-stroke"/>
      </svg>
      <div class="rp-axis"><span>0%</span><span>đáy ${nf(worst)}%</span></div>
    </div>`;
  }

  /** Trade-return histogram, zero line marked so the split is visible. */
  function histogram(bins) {
    if (!bins?.length) return '<p class="empty">Chưa đủ lệnh để vẽ phân phối.</p>';
    const peak = Math.max(...bins.map((b) => b.count), 1);
    const width = 1000 / bins.length;
    return `<div class="rp-chart">
      <svg viewBox="0 0 1000 160" preserveAspectRatio="none" class="rp-svg" role="img"
           aria-label="Phân phối lợi suất từng lệnh">
        ${bins.map((b, i) => {
          const h = (b.count / peak) * 150;
          const colour = b.to <= 0 ? 'var(--down)' : 'var(--up)';
          return `<rect x="${(i * width).toFixed(1)}" y="${(160 - h).toFixed(1)}"
            width="${(width - 1).toFixed(1)}" height="${h.toFixed(1)}" fill="${colour}"
            opacity="0.75"><title>${nf(b.from)}% … ${nf(b.to)}%: ${b.count} lệnh</title></rect>`;
        }).join('')}
      </svg>
      <div class="rp-axis"><span>${nf(bins[0].from)}%</span>
        <span>lợi suất mỗi lệnh, theo % ký quỹ</span>
        <span>${nf(bins[bins.length - 1].to)}%</span></div>
    </div>`;
  }

  /** MAE against outcome: the picture that says where a stop can go. */
  function excursionScatter(points) {
    if (!points?.length) return '<p class="empty">Chưa có lệnh nào.</p>';
    const maxMae = Math.min(...points.map((p) => p.mae), -0.01);
    const maxRet = Math.max(...points.map((p) => Math.abs(p.ret)), 0.01);
    const H = 260;
    return `<div class="rp-chart">
      <svg viewBox="0 0 1000 ${H}" class="rp-svg tall" role="img"
           aria-label="Lỗ tạm thời sâu nhất so với kết quả cuối cùng">
        <line x1="0" y1="${H / 2}" x2="1000" y2="${H / 2}"
              stroke="var(--border)" stroke-width="1"/>
        ${points.map((p) => {
          const x = (p.mae / maxMae) * 980 + 10;
          const y = H / 2 - (p.ret / maxRet) * (H / 2 - 10);
          return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5"
            fill="${p.win ? 'var(--up)' : 'var(--down)'}" opacity="0.6">
            <title>${p.side === 'long' ? 'Mua' : 'Bán'} · MAE ${nf(p.mae)}% → kết quả ${pct(p.ret)}</title>
          </circle>`;
        }).join('')}
      </svg>
      <div class="rp-axis"><span>MAE 0%</span>
        <span>trục ngang: lỗ tạm thời sâu nhất · trục dọc: kết quả cuối</span>
        <span>${nf(maxMae)}%</span></div>
    </div>`;
  }

  // ---------- building blocks ----------

  function card(label, value, explain, klass = '', sub = '') {
    const info = !explain
      ? ''
      : explain.startsWith('<') ? explain
        : Explain.button(explain, { title: `Giải thích ${label}` });
    return `<div class="metric">
      <div class="metric-label">${esc(label)} ${info}</div>
      <div class="metric-value ${klass}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  const row = (label, value, explain, klass = '') => {
    const info = explain ? Explain.button(explain, { title: `Giải thích ${label}` }) : '';
    return `<tr><td>${esc(label)} ${info}</td>
      <td class="${klass}">${value}</td></tr>`;
  };

  // ---------- tabs ----------

  function overviewTab(r) {
    const o = r.overview;
    const risk = r.risk;
    const beat = o.vs_buy_hold_pct >= 0;

    let html = '';
    if (o.ruined) {
      html += `<div class="callout bad"><strong>Tài khoản đã cháy.</strong>
        Vốn chạm 0 và mô phỏng dừng lại tại đó. Mọi con số bên dưới chỉ mô tả
        quãng đường tới lúc đó.</div>`;
    }
    html += `<div class="callout ${beat ? 'good' : 'warn'}">
      <strong>${beat ? 'Thắng mua-và-giữ' : 'Thua mua-và-giữ'} ${pct(o.vs_buy_hold_pct)}.</strong>
      Chiến lược ${pct(o.net_profit_pct)} so với ${pct(o.buy_hold_pct)} của việc chỉ
      mua ở nến đầu rồi giữ tới nến cuối, trên đúng cùng giai đoạn và cùng chi phí vào lệnh.</div>`;

    html += '<div class="metrics">';
    html += card('Lãi ròng', money(o.net_profit), 'm.total_return',
      cls(o.net_profit), pct(o.net_profit_pct));
    html += card('CAR', pct(o.car_pct), 'm.cagr', cls(o.car_pct),
      `mua-và-giữ ${pct(o.buy_hold_car_pct)}`);
    html += card('RAR', pct(o.rar_pct),
      Explain.inline({
        title: 'RAR — lợi suất đã hiệu chỉnh theo phơi nhiễm',
        what: 'CAR chia cho tỷ lệ thời gian thực sự có vị thế.',
        rows: [['CAR', pct(o.car_pct)], ['Phơi nhiễm', upct(o.exposure_pct)],
               ['RAR', pct(o.rar_pct)]],
        how: 'Vốn đứng ngoài thị trường không chịu rủi ro thị trường. Một hệ thống chỉ nắm giữ 20% thời gian mà đạt cùng lợi nhuận với mua-và-giữ đang tạo ra lợi suất gấp năm lần trên phần vốn thực sự chịu rủi ro — và phần vốn còn lại rảnh để làm việc khác.',
        watch: 'Phơi nhiễm rất thấp thường đi kèm rất ít lệnh, và khi đó mọi thống kê đều mỏng. Xem số lệnh trước khi đọc con số này.',
      }),
      cls(o.rar_pct), `phơi nhiễm ${upct(o.exposure_pct)}`);
    html += card('Sụt giảm tối đa', upct(risk.max_drawdown_pct), 'm.max_dd', 'neg',
      money(risk.max_drawdown_value));
    html += card('CAR/MDD', ratio(risk.car_mdd), 'm.car_mdd',
      risk.car_mdd >= 1 ? 'pos' : '', 'lợi nhuận trên mỗi % sụt giảm');
    html += card('Sharpe', ratio(risk.sharpe), 'm.sharpe', cls(risk.sharpe),
      `Sortino ${ratio(risk.sortino)}`);
    html += '</div>';

    html += equityChart(r);

    html += `<table class="data-table rp-table"><tbody>
      ${row('Vốn ban đầu', money(o.initial_capital))}
      ${row('Vốn cuối kỳ', money(o.final_equity), '', cls(o.net_profit))}
      ${row('Số nến', o.bars.toLocaleString('vi-VN'))}
      ${row('Số nến có vị thế', `${o.bars_in_market.toLocaleString('vi-VN')} (${upct(o.exposure_pct)})`, 'm.exposure')}
      ${row('Độ dài giai đoạn', `${nf(o.years)} năm`)}
      ${row('Khung thời gian', esc(o.timeframe))}
    </tbody></table>`;

    if (o.years < 1) {
      html += `<p class="table-note">Giai đoạn ngắn hơn một năm, nên CAR và RAR
        đang ngoại suy từ ${nf(o.years * 12, 1)} tháng dữ liệu. Đọc lãi ròng
        thay vì đọc chúng.</p>`;
    }
    return html;
  }

  function tradesTab(r) {
    const t = r.trades;
    const s = r.streaks;

    // Long and short side by side. Plenty of "two-way" strategies turn out to
    // make all their money on one side, and a combined table hides it.
    const columns = [['Tất cả', t.all], ['Mua', t.long], ['Bán', t.short]];
    const line = (label, pick, explain, klass = () => '') => {
      const info = explain ? Explain.button(explain, { title: `Giải thích ${label}` }) : '';
      return `<tr><td>${esc(label)} ${info}</td>` +
        columns.map(([, block]) => {
          if (!block.count) return '<td class="muted">—</td>';
          const value = pick(block);
          return `<td class="${klass(block)}">${value}</td>`;
        }).join('') + '</tr>';
    };

    let html = '';
    if (t.long.count && t.short.count) {
      const oneSided = t.long.net_profit > 0 !== t.short.net_profit > 0;
      if (oneSided) {
        const good = t.long.net_profit > 0 ? 'mua' : 'bán';
        const bad = good === 'mua' ? 'bán' : 'mua';
        html += `<div class="callout warn"><strong>Chỉ một chiều có lãi.</strong>
          Chiều ${good} lãi ${money(Math.abs(t[good === 'mua' ? 'long' : 'short'].net_profit))},
          chiều ${bad} lỗ ${money(Math.abs(t[bad === 'mua' ? 'long' : 'short'].net_profit))}.
          Bỏ hẳn chiều ${bad} có thể cho kết quả tốt hơn — nhưng hãy kiểm chứng
          bằng walk-forward, vì đây cũng có thể chỉ là đặc điểm của đúng giai đoạn này.</div>`;
      }
    }
    if (t.all.best_trade_share_pct > 40) {
      html += `<div class="callout warn"><strong>Một lệnh chiếm
        ${upct(t.all.best_trade_share_pct, 0)} tổng lãi.</strong>
        Hệ số lợi nhuận ${ratio(t.all.profit_factor)} đang mô tả một lần may
        chứ không mô tả chiến lược. Bỏ lệnh đó ra thì phần còn lại trông rất khác.</div>`;
    }

    html += `<table class="data-table rp-table"><thead><tr><th>Chỉ số</th>
      ${columns.map(([name]) => `<th>${name}</th>`).join('')}</tr></thead><tbody>
      ${line('Số lệnh', (b) => b.count)}
      ${line('Thắng / thua', (b) => `${b.wins} / ${b.losses}`)}
      ${line('Tỷ lệ thắng', (b) => upct(b.win_rate_pct), 'm.win_rate',
        (b) => (b.win_rate_pct >= 50 ? 'pos' : ''))}
      ${line('Lãi ròng', (b) => money(b.net_profit), '', (b) => cls(b.net_profit))}
      ${line('Hệ số lợi nhuận', (b) => ratio(b.profit_factor), 'm.profit_factor',
        (b) => (b.profit_factor >= 1 ? 'pos' : 'neg'))}
      ${line('Kỳ vọng/lệnh', (b) => money(b.expectancy), 'm.expectancy',
        (b) => cls(b.expectancy))}
      ${line('Tỷ lệ lãi/lỗ', (b) => ratio(b.payoff_ratio), 'm.payoff')}
      ${line('Lãi TB (lệnh thắng)', (b) => money(b.avg_win), '', () => 'pos')}
      ${line('Lỗ TB (lệnh thua)', (b) => money(b.avg_loss), '', () => 'neg')}
      ${line('Lệnh lãi lớn nhất', (b) => money(b.largest_win), '', () => 'pos')}
      ${line('Lệnh lỗ lớn nhất', (b) => money(b.largest_loss), '', () => 'neg')}
      ${line('Số nến giữ TB', (b) => nf(b.avg_bars_held, 1))}
      ${line('Nến giữ TB · thắng', (b) => nf(b.avg_bars_win, 1))}
      ${line('Nến giữ TB · thua', (b) => nf(b.avg_bars_loss, 1))}
    </tbody></table>`;

    html += `<div class="metrics" style="margin-top:14px">
      ${card('Chuỗi thắng dài nhất', s.max_consecutive_wins, 'm.consecutive', 'pos')}
      ${card('Chuỗi thua dài nhất', s.max_consecutive_losses, 'm.consecutive', 'neg')}
      ${card('Số lần thanh lý', r.risk.liquidations, 'm.liquidation',
        r.risk.liquidations ? 'neg' : '')}
      ${card('Lệnh lớn nhất / tổng lãi', upct(t.all.best_trade_share_pct, 0), '',
        t.all.best_trade_share_pct > 40 ? 'neg' : '')}
    </div>
    <p class="table-note">${esc(s.note)}</p>`;
    return html;
  }

  function riskTab(r) {
    const risk = r.risk;
    const k = risk.k_ratio;

    let html = '<div class="metrics">';
    html += card('Sụt giảm tối đa', upct(risk.max_drawdown_pct), 'm.max_dd', 'neg');
    html += card('Chỉ số Ulcer', nf(risk.ulcer_index), 'm.ulcer', '',
      `UPI ${ratio(risk.ulcer_performance_index)}`);
    html += card('CAR/MDD', ratio(risk.car_mdd), 'm.car_mdd',
      risk.car_mdd >= 1 ? 'pos' : '');
    html += card('Hệ số phục hồi', ratio(risk.recovery_factor), 'm.recovery');
    html += card('Hệ số K', k.value === null ? '—' : nf(k.value, 3), 'm.k_ratio', '',
      'độ đều của tăng trưởng');
    html += card('Biến động (năm)', upct(risk.volatility_annual_pct), '', '',
      `Sharpe ${ratio(risk.sharpe)}`);
    html += '</div>';

    html += drawdownChart(r);

    html += `<table class="data-table rp-table"><tbody>
      ${row('Sụt giảm tối đa (tiền)', money(risk.max_drawdown_value), '', 'neg')}
      ${row('Sụt giảm sâu nhất trong một lệnh', upct(risk.max_trade_drawdown_pct), 'm.mae', 'neg')}
      ${row('Thời gian dưới đỉnh', `${upct(risk.bars_underwater_pct)} số nến`)}
      ${row('Chuỗi dưới đỉnh dài nhất', `${risk.longest_underwater_bars.toLocaleString('vi-VN')} nến`)}
      ${row('Sortino', ratio(risk.sortino), 'm.sortino')}
    </tbody></table>`;

    if (k.note) html += `<p class="table-note">Hệ số K: ${esc(k.note)}</p>`;
    html += `<p class="table-note">Sụt giảm trong quá khứ là <strong>cận dưới</strong>,
      không phải cận trên. Một giai đoạn dài hơn gần như luôn chứa một đợt sụt sâu hơn
      đợt tệ nhất ở đây — hãy lấy con số này làm mức tối thiểu phải chịu được, không
      phải mức tối đa sẽ gặp.</p>`;
    return html;
  }

  function periodTab(r) {
    const p = r.periodic;
    if (!p.monthly.length) return '<p class="empty">Giai đoạn quá ngắn để chia theo tháng.</p>';

    // Year × month grid: this is where a strategy that only worked during one
    // rally stops being able to hide.
    const years = [...new Set(p.monthly.map((m) => m.year))].sort();
    const lookup = new Map(p.monthly.map((m) => [`${m.year}-${m.month}`, m.return_pct]));
    const annual = new Map(p.annual.map((a) => [a.year, a.return_pct]));

    // Colour scale anchored on the largest absolute monthly move, so a calm
    // strategy is not painted as dramatically as a violent one.
    const scale = Math.max(
      ...p.monthly.map((m) => Math.abs(m.return_pct)), 1,
    );
    const shade = (value) => {
      if (value === undefined) return '';
      const alpha = Math.min(Math.abs(value) / scale, 1) * 0.55;
      const colour = value >= 0 ? '18,128,92' : '200,55,45';
      return `background:rgba(${colour},${alpha.toFixed(3)})`;
    };

    let html = `<div class="metrics">
      ${card('Tháng có lãi', upct(p.positive_month_pct, 0), '',
        p.positive_month_pct >= 50 ? 'pos' : 'neg',
        `${p.positive_months}/${p.total_months} tháng`)}
      ${card('Tháng tốt nhất', pct(p.best_month_pct), '', 'pos')}
      ${card('Tháng tệ nhất', pct(p.worst_month_pct), '', 'neg')}
    </div>`;

    html += `<div class="rp-scroll"><table class="data-table rp-months">
      <thead><tr><th>Năm</th>${MONTHS.map((m) => `<th>${m}</th>`).join('')}
      <th>Cả năm</th></tr></thead><tbody>`;
    for (const year of years) {
      html += `<tr><td>${year}</td>`;
      for (let month = 1; month <= 12; month++) {
        const value = lookup.get(`${year}-${month}`);
        html += value === undefined
          ? '<td class="muted">·</td>'
          : `<td style="${shade(value)}">${nf(value, 1)}</td>`;
      }
      const total = annual.get(year);
      html += `<td class="${cls(total ?? 0)}"><strong>${total === undefined ? '—' : nf(total, 1)}</strong></td></tr>`;
    }
    html += '</tbody></table></div>';
    html += `<p class="table-note">Chia kỳ theo ${esc(p.timezone)}, đúng múi giờ
      hiển thị trên biểu đồ. Lợi suất tháng đầu tiên tính từ vốn ban đầu.
      Nếu gần như toàn bộ lợi nhuận nằm trong hai hoặc ba ô, chiến lược này bắt
      được một đợt sóng chứ chưa chắc có lợi thế lặp lại được.</p>`;
    return html;
  }

  function distributionTab(r) {
    const e = r.excursions;
    let html = '<div class="field-group-title">Phân phối lợi suất từng lệnh</div>';
    html += histogram(r.charts.trade_returns);

    if (!e.count) return html;

    html += '<div class="field-group-title">Lỗ tạm thời sâu nhất (MAE) so với kết quả</div>';
    html += excursionScatter(e.points);

    html += `<table class="data-table rp-table"><thead><tr>
      <th>Nhóm lệnh</th><th>MAE trung bình</th><th>MAE trung vị</th>
      <th>MFE trung bình</th></tr></thead><tbody>
      <tr><td>Lệnh thắng ${Explain.button('m.mae', { title: 'Giải thích MAE' })}</td>
        <td class="neg">${nf(e.mae_winners.mean)}%</td>
        <td class="neg">${nf(e.mae_winners.median)}%</td>
        <td class="pos">${nf(e.mfe_winners.mean)}%</td></tr>
      <tr><td>Lệnh thua ${Explain.button('m.mfe', { title: 'Giải thích MFE' })}</td>
        <td class="neg">${nf(e.mae_losers.mean)}%</td>
        <td class="neg">${nf(e.mae_losers.median)}%</td>
        <td class="pos">${nf(e.mfe_losers.mean)}%</td></tr>
    </tbody></table>`;

    html += `<div class="callout"><strong>Đặt dừng lỗ ở đâu.</strong>
      ${esc(e.stop_note)} Ở đây lệnh thắng trung bình chìm
      ${nf(Math.abs(e.mae_winners.mean))}% trước khi có lãi, nên một mức dừng chặt
      hơn thế sẽ cắt chính chúng.</div>`;
    html += `<div class="callout"><strong>Có nên chốt lãi không.</strong>
      ${esc(e.target_note)} Ở đây lệnh thua trung bình từng xanh
      ${nf(e.mfe_losers.mean)}%.</div>`;
    return html;
  }

  function mlTab(r) {
    const m = r.ml;
    if (m.error) {
      return `<div class="callout warn">${esc(m.error)}</div>
        <p class="table-note">Phần này chấm tín hiệu như một bộ phân loại hướng
        của nến kế tiếp. Nó cần đủ số nến vừa có vị thế vừa có nến sau biến động.</p>`;
    }

    const c = m.confusion;
    let html = `<div class="callout ${m.beats_baseline ? 'good' : 'warn'}">
      <strong>${m.beats_baseline ? 'Vượt đường cơ sở' : 'Chưa vượt đường cơ sở'}.</strong>
      ${esc(m.conclusion)}</div>`;

    html += '<div class="metrics">';
    html += card('Độ chính xác', upct(m.accuracy * 100), 'ml.accuracy',
      m.beats_baseline ? 'pos' : '', `${m.n_scored.toLocaleString('vi-VN')} nến được chấm`);
    html += card('Đường cơ sở', upct(m.baseline_accuracy * 100), 'ml.baseline', '',
      'luôn đoán lớp phổ biến hơn');
    html += card('Chênh lệch', `${m.edge_pct >= 0 ? '+' : ''}${nf(m.edge_pct)} đpt`,
      Explain.inline({
        title: 'Chênh lệch so với đường cơ sở',
        what: 'Độ chính xác trừ đi độ chính xác của quy tắc ngây thơ nhất, tính bằng điểm phần trăm.',
        rows: [['Độ chính xác', upct(m.accuracy * 100)],
               ['Đường cơ sở', upct(m.baseline_accuracy * 100)],
               ['p (nhị thức, một phía)', Explain.pFormat(m.binomial_p)]],
        how: m.conclusion,
        assumptions: m.assumptions,
      }),
      cls(m.edge_pct), `p = ${Explain.pFormat(m.binomial_p)}`);
    html += card('MCC', nf(m.mcc, 3), 'ml.mcc', cls(m.mcc), '0 = đoán mò');
    html += '</div>';

    html += `<table class="data-table rp-table"><thead><tr>
      <th>Chiều</th><th>Precision</th><th>Recall</th><th>F1</th></tr></thead><tbody>
      <tr><td>Mua ${Explain.button('ml.precision', { title: 'Giải thích precision' })}</td>
        <td>${upct(m.precision_long * 100)}</td><td>${upct(m.recall_long * 100)}</td>
        <td>${upct(m.f1_long * 100)}</td></tr>
      <tr><td>Bán ${Explain.button('ml.recall', { title: 'Giải thích recall' })}</td>
        <td>${upct(m.precision_short * 100)}</td><td>${upct(m.recall_short * 100)}</td>
        <td>${upct(m.f1_short * 100)}</td></tr>
    </tbody></table>`;

    html += `<div class="field-group-title">Ma trận nhầm lẫn
      ${Explain.button('ml.confusion', { title: 'Giải thích ma trận nhầm lẫn' })}</div>
      <table class="data-table rp-table"><thead><tr><th></th>
        <th>Thực tế tăng</th><th>Thực tế giảm</th></tr></thead><tbody>
        <tr><td>Đoán tăng</td><td class="pos">${c.true_up_pred_up}</td>
          <td class="neg">${c.true_down_pred_up}</td></tr>
        <tr><td>Đoán giảm</td><td class="neg">${c.true_up_pred_down}</td>
          <td class="pos">${c.true_down_pred_down}</td></tr>
      </tbody></table>`;

    if (m.probability) {
      const p = m.probability;
      html += `<div class="field-group-title">Hiệu chuẩn xác suất</div>
        <div class="metrics">
          ${card('ROC-AUC', p.roc_auc === null ? '—' : nf(p.roc_auc, 3), 'ml.auc',
            p.roc_auc > 0.5 ? 'pos' : 'neg', '0,5 = vô dụng')}
          ${card('Brier', nf(p.brier, 4), 'ml.brier', '', 'càng nhỏ càng tốt')}
          ${card('Log-loss', nf(p.log_loss, 4), 'ml.logloss')}
        </div>`;
      if (p.calibration?.length) {
        html += `<table class="data-table rp-table"><thead><tr>
          <th>Xác suất dự báo</th><th>Tần suất thực tế</th><th>Số nến</th>
          </tr></thead><tbody>` + p.calibration.map((b) => `<tr>
            <td>${upct(b.predicted * 100)}</td>
            <td class="${Math.abs(b.predicted - b.observed) < 0.05 ? 'pos' : 'neg'}">${upct(b.observed * 100)}</td>
            <td class="muted">${b.count}</td></tr>`).join('') + '</tbody></table>';
        html += `<p class="table-note">Mô hình hiệu chuẩn tốt thì hai cột đầu bám sát
          nhau: khi nó nói 70%, kết quả đúng khoảng 70% số lần đó.</p>`;
      }
      html += `<p class="table-note">${esc(p.note)}</p>`;
    } else {
      html += `<p class="table-note">Chiến lược này không công bố xác suất, nên không
        chấm được phần hiệu chuẩn. Để có phần đó, hãy gán
        <code>df["ml_probability"]</code> trong hàm <code>signals()</code>.</p>`;
    }

    html += `<p class="table-note">${esc(m.note)} ${esc(m.assumptions)}</p>`;
    return html;
  }

  const TABS = [
    ['overview', 'Tổng quan', overviewTab],
    ['trades', 'Lệnh', tradesTab],
    ['risk', 'Rủi ro', riskTab],
    ['period', 'Theo kỳ', periodTab],
    ['dist', 'Phân phối', distributionTab],
    ['ml', 'Học máy', mlTab],
  ];

  // ---------- window ----------

  function paint() {
    if (!host || !data) return;
    const body = host.querySelector('.rp-body');
    const tab = TABS.find(([id]) => id === activeTab) || TABS[0];
    try {
      body.innerHTML = tab[2](data);
    } catch (err) {
      body.innerHTML = `<div class="callout bad">Không dựng được tab này: ${esc(err.message)}</div>`;
      console.error(err);
    }
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.classList.toggle('active', button.dataset.tab === activeTab);
      button.setAttribute('aria-selected', String(button.dataset.tab === activeTab));
    }
    body.scrollTop = 0;
  }

  function close() {
    host?.remove();
    host = null;
    document.removeEventListener('keydown', onKey, true);
  }

  function onKey(event) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      close();
    }
  }

  function open(report) {
    data = report;
    close();

    host = document.createElement('div');
    host.className = 'rp-backdrop';
    host.innerHTML = `
      <div class="rp-window" role="dialog" aria-modal="true" aria-labelledby="rp-title">
        <div class="rp-head">
          <div>
            <h2 id="rp-title">${esc(report.strategy_name || report.strategy_id)}</h2>
            <div class="rp-sub">${esc(report.symbol || '')} ${esc(report.overview.timeframe)}
              · ${report.overview.bars.toLocaleString('vi-VN')} nến
              · ${report.trades.all.count} lệnh</div>
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
    // Clicking the dark area outside the window closes it; clicking inside
    // must not, which is why this checks the target rather than using capture.
    host.addEventListener('click', (event) => {
      if (event.target === host) close();
    });
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.addEventListener('click', () => {
        activeTab = button.dataset.tab;
        paint();
      });
    }
    document.addEventListener('keydown', onKey, true);

    paint();
    host.querySelector('.rp-close').focus();
  }

  function init(config) {
    onToast = config?.onToast || (() => {});
  }

  return { init, open, close };
})();
