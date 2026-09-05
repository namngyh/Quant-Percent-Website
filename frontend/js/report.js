/* The full backtest report, in a window of its own.
 *
 * The results panel beside the chart answers "did it make money". This answers
 * "why", and that needs more room than a 344px column: a monthly return table,
 * long and short broken out side by side, an excursion scatter, classification
 * metrics. So it opens centred over the page, and closes back to exactly the
 * chart you were looking at.
 *
 * Charts here are hand-drawn SVG rather than the chart library. Lightweight
 * Charts is built for price series on a time axis with crosshairs and panning;
 * a static drawdown ribbon or a scatter of 88 trades wants none of that, and
 * an SVG string costs nothing to throw away when the tab changes.
 *
 * Text uses `L(vi, en)` inline rather than dictionary keys. Almost every string
 * here is a full sentence used exactly once, and a key for each would mean a
 * dictionary as long as this file whose two halves drift apart on the first
 * edit. Kept inline, the pair cannot be changed by halves.
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

  /** Unsigned percent, for quantities with no direction (exposure, win rate). */
  const upct = (value, digits = 1) =>
    Number.isFinite(value) ? `${value.toFixed(digits)}%` : '—';

  const money = (value) =>
    Number.isFinite(value)
      ? value.toLocaleString(I18n.locale(), { maximumFractionDigits: 0 })
      : '—';

  const ratio = (value) => {
    if (!Number.isFinite(value)) return value === Infinity ? '∞' : '—';
    return value.toFixed(2);
  };

  const cls = (value) => (value > 0 ? 'pos' : value < 0 ? 'neg' : '');

  const months = () => (I18n.lang === 'en'
    ? ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
       'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
    : ['T1', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'T8', 'T9', 'T10', 'T11', 'T12']);

  const day = (seconds) =>
    new Date((seconds + 7 * 3600) * 1000).toISOString().slice(0, 10);

  /** Bars into a human span, so "482 bars" also reads as "80 days". */
  function span(bars, timeframe) {
    const hours = { '1m': 1 / 60, '5m': 1 / 12, '15m': 0.25, '30m': 0.5, '1h': 1,
                    '2h': 2, '4h': 4, '6h': 6, '8h': 8, '12h': 12, '1d': 24,
                    '3d': 72, '1w': 168 }[timeframe];
    if (!hours || !Number.isFinite(bars)) return '';
    const days = bars * hours / 24;
    if (days < 1.5) return L(`${(days * 24).toFixed(0)} giờ`, `${(days * 24).toFixed(0)}h`);
    if (days < 60) return L(`${days.toFixed(0)} ngày`, `${days.toFixed(0)} days`);
    return L(`${(days / 30.44).toFixed(1)} tháng`, `${(days / 30.44).toFixed(1)} months`);
  }

  // ---------- chart primitives ----------

  /** Map a series of {t, v} onto an SVG path in a fixed 1000×H viewBox. */
  function pathFor(points, height, minimum, maximum) {
    if (!points.length) return '';
    const range = maximum - minimum || 1;
    return points.map((p, i) => {
      const x = (i / Math.max(points.length - 1, 1)) * 1000;
      const y = height - ((p.v - minimum) / range) * height;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
  }

  function chartFrame(inner, { legends = [], axis = [], tall = false } = {}) {
    return `<div class="rp-chart">
      ${legends.length ? `<div class="rp-chart-head">${legends.map(
        (l) => `<span class="rp-legend"><i style="background:${l.colour}"></i>${esc(l.label)}</span>`,
      ).join('')}</div>` : ''}
      ${inner.replace('class="rp-svg"', `class="rp-svg${tall ? ' tall' : ''}"`)}
      ${axis.length ? `<div class="rp-axis">${axis.map((a) => `<span>${esc(a)}</span>`).join('')}</div>` : ''}
    </div>`;
  }

  /** Equity against buy-and-hold, one axis because both start at the same capital. */
  function equityChart(report) {
    const equity = report.charts.equity;
    const hold = report.charts.buy_hold;
    if (!equity.length) return '';

    const all = [...equity.map((p) => p.v), ...hold.map((p) => p.v)];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const H = 220;

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(L('Đường vốn so với mua và giữ', 'Equity against buy and hold'))}">
        <path d="${pathFor(hold, H, min, max)}" fill="none"
              stroke="var(--text-faint)" stroke-width="2" vector-effect="non-scaling-stroke"/>
        <path d="${pathFor(equity, H, min, max)}" fill="none"
              stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg>`,
      {
        legends: [
          { colour: 'var(--accent)', label: L('Chiến lược', 'Strategy') },
          { colour: 'var(--text-faint)', label: L('Mua và giữ', 'Buy and hold') },
        ],
        axis: [day(equity[0].t), `${money(min)} – ${money(max)}`,
               day(equity[equity.length - 1].t)],
      },
    );
  }

  /** Drawdown as a filled ribbon hanging from zero: it is always negative. */
  function drawdownChart(report) {
    const series = report.charts.drawdown;
    if (!series.length) return '';
    const worst = Math.min(...series.map((p) => p.v), -1);
    const H = 140;
    const area = pathFor(series, H, worst, 0);

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(L('Sụt giảm theo thời gian', 'Drawdown over time'))}">
        <path d="${area} L1000,0 L0,0 Z" fill="var(--down-soft)" stroke="none"/>
        <path d="${area}" fill="none" stroke="var(--down)" stroke-width="1.5"
              vector-effect="non-scaling-stroke"/>
      </svg>`,
      {
        legends: [{ colour: 'var(--down)', label: L('Sụt giảm từ đỉnh', 'Drawdown from peak') }],
        axis: ['0%', L(`đáy ${nf(worst)}%`, `trough ${nf(worst)}%`)],
      },
    );
  }

  /* Rolling Sharpe. The single headline figure cannot tell a steady strategy
     from one that worked for two years and then stopped; this can, and the
     zero line is what the eye actually reads against. */
  function rollingSharpeChart(report) {
    const series = report.risk.rolling_sharpe;
    if (!series?.length) {
      return `<p class="empty">${esc(L(
        'Chưa đủ dữ liệu cho cửa sổ trượt: cần ít nhất hai lần độ dài cửa sổ.',
        'Not enough data for a rolling window: it needs at least twice the window length.',
      ))}</p>`;
    }

    const values = series.map((p) => p.v);
    const min = Math.min(...values, -0.5);
    const max = Math.max(...values, 0.5);
    const H = 180;
    const zeroY = H - ((0 - min) / (max - min || 1)) * H;

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(L('Sharpe trên cửa sổ trượt', 'Rolling Sharpe ratio'))}">
        <line x1="0" y1="${zeroY.toFixed(1)}" x2="1000" y2="${zeroY.toFixed(1)}"
              stroke="var(--border)" stroke-width="1" stroke-dasharray="4 4"/>
        <path d="${pathFor(series, H, min, max)}" fill="none"
              stroke="var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/>
      </svg>`,
      {
        legends: [{ colour: 'var(--accent)', label: L('Sharpe trượt', 'Rolling Sharpe') }],
        axis: [day(series[0].t), L(`${nf(min)} … ${nf(max)} · đường đứt là 0`,
                                   `${nf(min)} … ${nf(max)} · dashed line is zero`),
               day(series[series.length - 1].t)],
      },
    );
  }

  /** A histogram; `unit` labels the axis. */
  function histogram(bins, unit, label) {
    if (!bins?.length) {
      return `<p class="empty">${esc(L('Chưa đủ dữ liệu để vẽ phân phối.',
                                        'Not enough data to plot a distribution.'))}</p>`;
    }
    const peak = Math.max(...bins.map((b) => b.count), 1);
    const width = 1000 / bins.length;

    return chartFrame(
      `<svg viewBox="0 0 1000 160" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(label)}">
        ${bins.map((b, i) => {
          const h = (b.count / peak) * 150;
          const colour = b.to <= 0 ? 'var(--down)' : 'var(--up)';
          return `<rect x="${(i * width).toFixed(1)}" y="${(160 - h).toFixed(1)}"
            width="${Math.max(width - 1, 0.5).toFixed(1)}" height="${h.toFixed(1)}"
            fill="${colour}" opacity="0.75"><title>${nf(b.from)} … ${nf(b.to)}: ${b.count}</title></rect>`;
        }).join('')}
      </svg>`,
      { axis: [`${nf(bins[0].from)}%`, unit, `${nf(bins[bins.length - 1].to)}%`] },
    );
  }

  /* Cumulative P&L in trade order rather than in time. This is the picture that
     shows whether profit accumulated steadily or arrived in one step, and one
     step is what a single lucky trade looks like. */
  function sequenceChart(report) {
    const series = report.charts.trade_sequence;
    if (!series?.length) return '';
    const values = series.map((p) => p.v);
    const min = Math.min(...values, 0);
    const max = Math.max(...values, 0);
    const H = 170;
    const zeroY = H - ((0 - min) / (max - min || 1)) * H;
    const path = series.map((p, i) => {
      const x = (i / Math.max(series.length - 1, 1)) * 1000;
      const y = H - ((p.v - min) / (max - min || 1)) * H;
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(L('Lãi lỗ cộng dồn theo thứ tự lệnh',
                                 'Cumulative P&L in trade order'))}">
        <line x1="0" y1="${zeroY.toFixed(1)}" x2="1000" y2="${zeroY.toFixed(1)}"
              stroke="var(--border)" stroke-width="1" stroke-dasharray="4 4"/>
        <path d="${path}" fill="none" stroke="var(--accent)" stroke-width="2"
              vector-effect="non-scaling-stroke"/>
      </svg>`,
      {
        legends: [{ colour: 'var(--accent)', label: L('Lãi lỗ cộng dồn', 'Cumulative P&L') }],
        axis: [L('lệnh 1', 'trade 1'), `${money(min)} – ${money(max)}`,
               L(`lệnh ${series.length}`, `trade ${series.length}`)],
      },
    );
  }

  /** Annual returns as bars, so a year that broke the run is obvious. */
  function annualChart(rows) {
    if (!rows?.length) return '';
    const scale = Math.max(...rows.map((r) => Math.abs(r.return_pct)), 1);
    const width = 1000 / rows.length;
    const H = 150;

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg" role="img"
            aria-label="${esc(L('Lợi suất theo năm', 'Return by year'))}">
        <line x1="0" y1="${H / 2}" x2="1000" y2="${H / 2}" stroke="var(--border)" stroke-width="1"/>
        ${rows.map((r, i) => {
          const h = Math.abs(r.return_pct) / scale * (H / 2 - 8);
          const y = r.return_pct >= 0 ? H / 2 - h : H / 2;
          return `<rect x="${(i * width + width * 0.2).toFixed(1)}" y="${y.toFixed(1)}"
            width="${(width * 0.6).toFixed(1)}" height="${Math.max(h, 1).toFixed(1)}"
            fill="${r.return_pct >= 0 ? 'var(--up)' : 'var(--down)'}" opacity="0.8">
            <title>${r.year}: ${pct(r.return_pct)}</title></rect>`;
        }).join('')}
      </svg>`,
      { axis: rows.map((r) => `${r.year} ${nf(r.return_pct, 0)}%`) },
    );
  }

  /** MAE against outcome: the picture that says where a stop can go. */
  function excursionScatter(points) {
    if (!points?.length) {
      return `<p class="empty">${esc(L('Chưa có lệnh nào.', 'No trades yet.'))}</p>`;
    }
    const maxMae = Math.min(...points.map((p) => p.mae), -0.01);
    const maxRet = Math.max(...points.map((p) => Math.abs(p.ret)), 0.01);
    const H = 260;

    return chartFrame(
      `<svg viewBox="0 0 1000 ${H}" class="rp-svg" role="img"
            aria-label="${esc(L('Lỗ tạm thời sâu nhất so với kết quả cuối cùng',
                                 'Worst unrealised loss against final outcome'))}">
        <line x1="0" y1="${H / 2}" x2="1000" y2="${H / 2}" stroke="var(--border)" stroke-width="1"/>
        ${points.map((p) => {
          const x = (p.mae / maxMae) * 980 + 10;
          const y = H / 2 - (p.ret / maxRet) * (H / 2 - 10);
          const side = p.side === 'long' ? L('Mua', 'Long') : L('Bán', 'Short');
          return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="3.5"
            fill="${p.win ? 'var(--up)' : 'var(--down)'}" opacity="0.6">
            <title>${side} · MAE ${nf(p.mae)}% → ${pct(p.ret)}</title></circle>`;
        }).join('')}
      </svg>`,
      {
        axis: ['MAE 0%',
               L('ngang: lỗ tạm thời sâu nhất · dọc: kết quả cuối',
                 'x: worst unrealised loss · y: final outcome'),
               `${nf(maxMae)}%`],
        tall: true,
      },
    );
  }

  // ---------- building blocks ----------

  function card(label, value, explain, klass = '', sub = '') {
    const info = !explain ? ''
      : explain.startsWith('<') ? explain
        : Explain.button(explain, { title: `${L('Giải thích', 'Explain')} ${label}` });
    return `<div class="metric">
      <div class="metric-label">${esc(label)} ${info}</div>
      <div class="metric-value ${klass}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  const row = (label, value, explain, klass = '') => {
    const info = explain
      ? Explain.button(explain, { title: `${L('Giải thích', 'Explain')} ${label}` })
      : '';
    return `<tr><td>${esc(label)} ${info}</td><td class="${klass}">${value}</td></tr>`;
  };

  const title = (text, explain = '') =>
    `<div class="field-group-title">${esc(text)} ${explain}</div>`;

  // ================================================================ tabs

  function overviewTab(r) {
    const o = r.overview;
    const risk = r.risk;
    const b = r.benchmark;
    const beat = o.vs_buy_hold_pct >= 0;

    let html = '';
    if (o.ruined) {
      html += `<div class="callout bad"><strong>${esc(L(
        'Tài khoản đã cháy.', 'The account was wiped out.'))}</strong>
        ${esc(L(
          'Vốn chạm 0 và mô phỏng dừng lại tại đó. Mọi con số bên dưới chỉ mô tả quãng đường tới lúc đó.',
          'Equity hit zero and the simulation stopped there. Everything below describes only the road up to that point.'))}</div>`;
    }
    html += `<div class="callout ${beat ? 'good' : 'warn'}">
      <strong>${esc(L(
        `${beat ? 'Thắng' : 'Thua'} mua-và-giữ ${pct(o.vs_buy_hold_pct)}.`,
        `${beat ? 'Beat' : 'Lost to'} buy-and-hold by ${pct(o.vs_buy_hold_pct)}.`))}</strong>
      ${esc(L(
        `Chiến lược ${pct(o.net_profit_pct)} so với ${pct(o.buy_hold_pct)} của việc chỉ mua ở nến đầu rồi giữ tới nến cuối, trên đúng cùng giai đoạn và cùng chi phí vào lệnh.`,
        `The strategy returned ${pct(o.net_profit_pct)} against ${pct(o.buy_hold_pct)} for simply buying at the first bar and holding to the last, over the identical window and paying the same entry cost.`))}</div>`;

    html += '<div class="metrics">';
    html += card(L('Lãi ròng', 'Net profit'), money(o.net_profit), 'm.total_return',
      cls(o.net_profit), pct(o.net_profit_pct));
    html += card('CAR', pct(o.car_pct), 'm.cagr', cls(o.car_pct),
      L(`mua-và-giữ ${pct(o.buy_hold_car_pct)}`, `buy-and-hold ${pct(o.buy_hold_car_pct)}`));
    html += card('RAR', pct(o.rar_pct), rarExplain(o), cls(o.rar_pct),
      L(`phơi nhiễm ${upct(o.exposure_pct)}`, `${upct(o.exposure_pct)} exposure`));
    html += card(L('Sụt giảm tối đa', 'Max drawdown'), upct(risk.max_drawdown_pct),
      'm.max_dd', 'neg', money(risk.max_drawdown_value));
    html += card('CAR/MDD', ratio(risk.car_mdd), 'm.car_mdd',
      risk.car_mdd >= 1 ? 'pos' : '',
      L('lợi nhuận trên mỗi % sụt giảm', 'return per point of drawdown'));
    html += card('Sharpe', ratio(risk.sharpe), 'm.sharpe', cls(risk.sharpe),
      `Sortino ${ratio(risk.sortino)}`);
    html += '</div>';

    html += equityChart(r);

    if (b && b.beta !== null) {
      html += title(L('So với chính tài sản này', 'Against the asset itself'));
      html += '<div class="metrics">';
      html += card(L('Beta', 'Beta'), ratio(b.beta), betaExplain(b), '',
        L('so với mua-và-giữ', 'versus buy-and-hold'));
      html += card(L('Tương quan', 'Correlation'), ratio(b.correlation), '',
        Math.abs(b.correlation) < 0.3 ? 'pos' : '',
        L('thấp là tốt', 'lower is better'));
      html += card(L('Alpha (năm)', 'Alpha (annual)'), pct(b.alpha_annual_pct), '',
        cls(b.alpha_annual_pct),
        L('phần không giải thích được bằng beta', 'the part beta cannot explain'));
      html += '</div>';
      html += `<p class="table-note">${esc(tp(b.note) || b.note)}</p>`;
    }

    html += `<table class="data-table rp-table"><tbody>
      ${row(L('Vốn ban đầu', 'Initial capital'), money(o.initial_capital))}
      ${row(L('Vốn cuối kỳ', 'Final equity'), money(o.final_equity), '', cls(o.net_profit))}
      ${row(L('Số nến', 'Bars'), o.bars.toLocaleString(I18n.locale()))}
      ${row(L('Số nến có vị thế', 'Bars in the market'),
        `${o.bars_in_market.toLocaleString(I18n.locale())} (${upct(o.exposure_pct)})`, 'm.exposure')}
      ${row(L('Độ dài giai đoạn', 'Period length'),
        L(`${nf(o.years)} năm`, `${nf(o.years)} years`))}
      ${row(L('Khung thời gian', 'Timeframe'), esc(o.timeframe))}
    </tbody></table>`;

    if (o.years < 1) {
      html += `<p class="table-note">${esc(L(
        `Giai đoạn ngắn hơn một năm, nên CAR và RAR đang ngoại suy từ ${nf(o.years * 12, 1)} tháng dữ liệu. Đọc lãi ròng thay vì đọc chúng.`,
        `The period is under a year, so CAR and RAR extrapolate from ${nf(o.years * 12, 1)} months of data. Read net profit instead.`))}</p>`;
    }
    return html;
  }

  const rarExplain = (o) => Explain.inline({
    title: L('RAR: lợi suất đã hiệu chỉnh theo phơi nhiễm',
             'RAR: exposure-adjusted return'),
    what: L('CAR chia cho tỷ lệ thời gian thực sự có vị thế.',
            'CAR divided by the fraction of time actually holding a position.'),
    rows: [['CAR', pct(o.car_pct)],
           [L('Phơi nhiễm', 'Exposure'), upct(o.exposure_pct)],
           ['RAR', pct(o.rar_pct)]],
    how: L('Vốn đứng ngoài thị trường không chịu rủi ro thị trường. Một hệ thống chỉ nắm giữ 20% thời gian mà đạt cùng lợi nhuận với mua-và-giữ đang tạo ra lợi suất gấp năm lần trên phần vốn thực sự chịu rủi ro, và phần còn lại rảnh để làm việc khác.',
            'Capital out of the market carries no market risk. A system that holds for 20% of the time and matches buy-and-hold is earning five times the return on the capital actually at risk, and the rest is free to work elsewhere.'),
    watch: L('Phơi nhiễm rất thấp thường đi kèm rất ít lệnh, và khi đó mọi thống kê đều mỏng. Xem số lệnh trước khi đọc con số này.',
             'Very low exposure usually means very few trades, and every statistic is thin at that point. Check the trade count before reading this.'),
  });

  const betaExplain = (b) => Explain.inline({
    title: L('Beta so với mua-và-giữ', 'Beta against buy-and-hold'),
    what: L('Chiến lược nhận bao nhiêu phần dao động của chính tài sản nó giao dịch.',
            'How much of the underlying asset’s movement the strategy takes on.'),
    rows: [['Beta', ratio(b.beta)],
           [L('Tương quan', 'Correlation'), ratio(b.correlation)],
           [L('Alpha (năm)', 'Alpha (annual)'), pct(b.alpha_annual_pct)]],
    how: L('Beta gần 1 nghĩa là chiến lược gần như chỉ đang nắm giữ, và lợi nhuận của nó là lợi nhuận của thị trường. Beta gần 0 nghĩa là nó kiếm tiền từ nơi khác, đó mới là thứ đáng trả phí.',
            'A beta near 1 means the strategy is essentially just holding, and its return is the market’s return. A beta near 0 means it earns from somewhere else, which is the part worth paying for.'),
    watch: L('Beta ở đây so với CHÍNH tài sản này, không phải so với một chỉ số thị trường.',
             'This beta is against the traded asset itself, not against a market index.'),
  });

  function tradesTab(r) {
    const t2 = r.trades;
    const s = r.streaks;
    const columns = [[L('Tất cả', 'All'), t2.all], [L('Mua', 'Long'), t2.long],
                     [L('Bán', 'Short'), t2.short]];

    const line = (label, pick, explain, klass = () => '') => {
      const info = explain
        ? Explain.button(explain, { title: `${L('Giải thích', 'Explain')} ${label}` })
        : '';
      return `<tr><td>${esc(label)} ${info}</td>` +
        columns.map(([, block]) => (block.count
          ? `<td class="${klass(block)}">${pick(block)}</td>`
          : '<td class="muted">—</td>')).join('') + '</tr>';
    };

    let html = '';
    if (t2.long.count && t2.short.count &&
        (t2.long.net_profit > 0) !== (t2.short.net_profit > 0)) {
      const goodLong = t2.long.net_profit > 0;
      const good = goodLong ? t2.long : t2.short;
      const bad = goodLong ? t2.short : t2.long;
      const goodName = goodLong ? L('mua', 'long') : L('bán', 'short');
      const badName = goodLong ? L('bán', 'short') : L('mua', 'long');
      html += `<div class="callout warn"><strong>${esc(L(
        'Chỉ một chiều có lãi.', 'Only one side makes money.'))}</strong>
        ${esc(L(
          `Chiều ${goodName} lãi ${money(Math.abs(good.net_profit))}, chiều ${badName} lỗ ${money(Math.abs(bad.net_profit))}. Bỏ hẳn chiều ${badName} có thể cho kết quả tốt hơn, nhưng hãy kiểm chứng bằng walk-forward, vì đây cũng có thể chỉ là đặc điểm của đúng giai đoạn này.`,
          `The ${goodName} side made ${money(Math.abs(good.net_profit))} and the ${badName} side lost ${money(Math.abs(bad.net_profit))}. Dropping the ${badName} side may do better, but check it with walk-forward, because it may equally be a feature of this particular period.`))}</div>`;
    }
    if (t2.all.best_trade_share_pct > 40) {
      html += `<div class="callout warn"><strong>${esc(L(
        `Một lệnh chiếm ${upct(t2.all.best_trade_share_pct, 0)} tổng lãi.`,
        `One trade is ${upct(t2.all.best_trade_share_pct, 0)} of gross profit.`))}</strong>
        ${esc(L(
          `Hệ số lợi nhuận ${ratio(t2.all.profit_factor)} đang mô tả một lần may chứ không mô tả chiến lược. Bỏ lệnh đó ra thì phần còn lại trông rất khác.`,
          `A profit factor of ${ratio(t2.all.profit_factor)} is describing one lucky trade rather than the strategy. Take it out and what remains looks very different.`))}</div>`;
    }

    html += `<table class="data-table rp-table"><thead><tr>
      <th>${esc(L('Chỉ số', 'Metric'))}</th>
      ${columns.map(([name]) => `<th>${esc(name)}</th>`).join('')}</tr></thead><tbody>
      ${line(L('Số lệnh', 'Trades'), (b) => b.count)}
      ${line(L('Thắng / thua', 'Wins / losses'), (b) => `${b.wins} / ${b.losses}`)}
      ${line(L('Tỷ lệ thắng', 'Win rate'), (b) => upct(b.win_rate_pct), 'm.win_rate',
        (b) => (b.win_rate_pct >= 50 ? 'pos' : ''))}
      ${line(L('Lãi ròng', 'Net profit'), (b) => money(b.net_profit), '', (b) => cls(b.net_profit))}
      ${line(L('Hệ số lợi nhuận', 'Profit factor'), (b) => ratio(b.profit_factor),
        'm.profit_factor', (b) => (b.profit_factor >= 1 ? 'pos' : 'neg'))}
      ${line(L('Kỳ vọng/lệnh', 'Expectancy'), (b) => money(b.expectancy), 'm.expectancy',
        (b) => cls(b.expectancy))}
      ${line(L('Kỳ vọng theo R', 'Expectancy in R'), (b) => `${nf(b.expectancy_r)}R`,
        expectancyRExplain(), (b) => cls(b.expectancy_r))}
      ${line(L('Tỷ lệ lãi/lỗ', 'Payoff ratio'), (b) => ratio(b.payoff_ratio), 'm.payoff')}
      ${line(L('Kelly', 'Kelly'), (b) => upct(b.kelly_pct), kellyExplain(),
        (b) => (b.kelly_pct > 0 ? 'pos' : 'neg'))}
      ${line(L('Lãi TB (lệnh thắng)', 'Average win'), (b) => money(b.avg_win), '', () => 'pos')}
      ${line(L('Lỗ TB (lệnh thua)', 'Average loss'), (b) => money(b.avg_loss), '', () => 'neg')}
      ${line(L('Sai số chuẩn của lãi TB', 'Std. error of mean P&L'),
        (b) => `± ${money(b.profit_se)}`, seExplain())}
      ${line(L('Lệnh lãi lớn nhất', 'Largest win'), (b) => money(b.largest_win), '', () => 'pos')}
      ${line(L('Lệnh lỗ lớn nhất', 'Largest loss'), (b) => money(b.largest_loss), '', () => 'neg')}
      ${line(L('Số nến giữ TB', 'Average bars held'), (b) => nf(b.avg_bars_held, 1))}
      ${line(L('Nến giữ TB · thắng', 'Bars held · wins'), (b) => nf(b.avg_bars_win, 1))}
      ${line(L('Nến giữ TB · thua', 'Bars held · losses'), (b) => nf(b.avg_bars_loss, 1))}
    </tbody></table>`;

    html += `<div class="metrics" style="margin-top:14px">
      ${card(L('Chuỗi thắng dài nhất', 'Longest win streak'), s.max_consecutive_wins,
        'm.consecutive', 'pos')}
      ${card(L('Chuỗi thua dài nhất', 'Longest losing streak'), s.max_consecutive_losses,
        'm.consecutive', 'neg')}
      ${card(L('Số lần thanh lý', 'Liquidations'), r.risk.liquidations, 'm.liquidation',
        r.risk.liquidations ? 'neg' : '')}
      ${card(L('Lệnh lớn nhất / tổng lãi', 'Best trade share'),
        upct(t2.all.best_trade_share_pct, 0), '',
        t2.all.best_trade_share_pct > 40 ? 'neg' : '')}
    </div>
    <p class="table-note">${esc(tp(s.note) || s.note)}</p>`;

    html += title(L('Lãi lỗ cộng dồn theo thứ tự lệnh', 'Cumulative P&L in trade order'));
    html += sequenceChart(r);
    html += `<p class="table-note">${esc(L(
      'Trục ngang là thứ tự lệnh, không phải thời gian. Một đường đi lên đều đặn nghĩa là lợi nhuận rải khắp chuỗi; một bậc thang duy nhất nghĩa là gần như toàn bộ đến từ một lệnh, và phần còn lại đi ngang.',
      'The x-axis is trade order, not time. A steady climb means profit is spread across the sequence; a single step means almost all of it came from one trade and the rest went nowhere.'))}</p>`;
    return html;
  }

  const expectancyRExplain = () => Explain.inline({
    title: L('Kỳ vọng theo R', 'Expectancy in R'),
    what: L('Lãi trung bình mỗi lệnh, tính theo bội số của mức lỗ điển hình (R = lỗ trung bình).',
            'Average profit per trade, expressed as a multiple of the typical loss (R = average loss).'),
    formula: '(win% × avg win + loss% × avg loss) / |avg loss|',
    how: L('0.4R nghĩa là mỗi lệnh kiếm được 0.4 lần mức thua điển hình. Đây là cách duy nhất so sánh trực tiếp hai chiến lược có cỡ vị thế khác nhau.',
            '0.4R means each trade earns 0.4 times the typical loss. This is the only way to compare two strategies with different position sizes directly.'),
  });

  const kellyExplain = () => Explain.inline({
    title: L('Tỷ lệ Kelly', 'Kelly fraction'),
    what: L('Phần vốn tối đa hoá tăng trưởng dài hạn, theo tỷ lệ thắng và tỷ lệ lãi/lỗ quan sát được.',
            'The fraction of capital that maximises long-run growth, given the observed win rate and payoff ratio.'),
    formula: 'win% − (1 − win%) / payoff',
    how: L('Đây là TRẦN, không phải khuyến nghị: đặt cỡ vị thế trên mức này thì tăng trưởng kỳ vọng GIẢM, không tăng.',
            'This is a ceiling, not a recommendation: sizing above it makes expected growth fall, not rise.'),
    watch: L('Kelly tối đa hoá tăng trưởng mà hoàn toàn không quan tâm sụt giảm dọc đường, nên mức nó đưa ra thường không chịu nổi về mặt tâm lý. Phần lớn người dùng chọn một nửa Kelly hoặc ít hơn. Nó cũng ước lượng từ quá khứ, nên nếu tỷ lệ thắng giảm thì Kelly cũ trở thành quá lớn.',
             'Kelly maximises growth with no regard for the drawdowns along the way, so the level it gives is usually unbearable in practice. Most people use half-Kelly or less. It is also estimated from the past, so if the win rate falls the old Kelly becomes too large.'),
  });

  const seExplain = () => Explain.inline({
    title: L('Sai số chuẩn của lãi trung bình', 'Standard error of mean P&L'),
    what: L('Khoảng bất định quanh con số lãi trung bình mỗi lệnh.',
            'The uncertainty band around the average profit per trade.'),
    how: L('Nếu sai số chuẩn lớn hơn chính giá trị trung bình thì kỳ vọng quan sát được không phân biệt được với 0, dù bảng vẫn in ra một con số dương.',
            'If the standard error exceeds the mean itself, the observed expectancy is indistinguishable from zero, however positive the printed number looks.'),
  });

  function riskTab(r) {
    const risk = r.risk;
    const k = risk.k_ratio;
    const ra = risk.ratios || {};
    const gp = risk.gain_to_pain || {};
    const ep = risk.episodes || {};

    let html = '<div class="metrics">';
    html += card(L('Sụt giảm tối đa', 'Max drawdown'), upct(risk.max_drawdown_pct),
      'm.max_dd', 'neg');
    html += card(L('Sụt giảm điển hình', 'Typical drawdown'),
      upct(ep.median_depth_pct), typicalDdExplain(ep), '',
      L(`trung vị của ${ep.count || 0} đợt`, `median of ${ep.count || 0} episodes`));
    html += card(L('Chỉ số Ulcer', 'Ulcer index'), nf(risk.ulcer_index), 'm.ulcer', '',
      `UPI ${ratio(risk.ulcer_performance_index)}`);
    html += card('CAR/MDD', ratio(risk.car_mdd), 'm.car_mdd', risk.car_mdd >= 1 ? 'pos' : '');
    html += card('Sterling', ratio(risk.sterling), sterlingExplain(), '',
      L('dùng sụt giảm trung bình', 'uses the average drawdown'));
    html += card('Burke', ratio(risk.burke), burkeExplain(), '',
      L('phạt các đợt sâu mạnh hơn', 'penalises deep episodes harder'));
    html += '</div>';

    html += '<div class="metrics">';
    html += card('Omega', ratio(ra.omega), omegaExplain(), ra.omega > 1 ? 'pos' : 'neg');
    html += card(L('Gain-to-pain', 'Gain-to-pain'),
      gp.value === null || gp.value === undefined ? '—' : ratio(gp.value),
      gainPainExplain(gp), gp.value > 1 ? 'pos' : '',
      L(`trên ${gp.months || 0} tháng`, `over ${gp.months || 0} months`));
    html += card(L('Tỷ lệ đuôi', 'Tail ratio'), ratio(ra.tail_ratio), tailExplain(),
      ra.tail_ratio > 1 ? 'pos' : 'neg');
    html += card(L('Độ ổn định', 'Stability'), nf(ra.stability, 3), stabilityExplain(),
      ra.stability > 0.7 ? 'pos' : '', L('R² của đường vốn', 'R² of the equity line'));
    html += card(L('Hệ số K', 'K-ratio'), k?.value == null ? '—' : nf(k.value, 3),
      'm.k_ratio', '', L('độ đều của tăng trưởng', 'consistency of growth'));
    html += card(L('Biến động (năm)', 'Volatility (annual)'),
      upct(risk.volatility_annual_pct), '', '', `Sharpe ${ratio(risk.sharpe)}`);
    html += '</div>';

    html += title(L('Sụt giảm theo thời gian', 'Drawdown over time'));
    html += drawdownChart(r);

    html += title(L('Sharpe trên cửa sổ trượt', 'Rolling Sharpe'));
    html += rollingSharpeChart(r);
    html += `<p class="table-note">${esc(L(
      'Một Sharpe 1.2 cho toàn giai đoạn có thể là 2.5 trong hai năm đầu và −0.3 trong hai năm sau. Con số tổng hợp không phân biệt được điều đó với một chiến lược đều đặn; đường này thì có.',
      'A headline Sharpe of 1.2 can be 2.5 for two years and −0.3 for the next two. The single figure cannot tell that apart from a steady strategy; this line can.'))}</p>`;

    if (ep.worst?.length) {
      html += title(L('Năm đợt sụt giảm sâu nhất', 'The five deepest drawdowns'));
      html += `<table class="data-table rp-table"><thead><tr>
        <th>${esc(L('Bắt đầu', 'Started'))}</th><th>${esc(L('Độ sâu', 'Depth'))}</th>
        <th>${esc(L('Kéo dài', 'Length'))}</th><th>${esc(L('Hồi phục', 'Recovery'))}</th>
        </tr></thead><tbody>` +
        ep.worst.map((e) => `<tr>
          <td>${e.start_time ? day(e.start_time) : '—'}</td>
          <td class="neg">${upct(e.depth_pct)}</td>
          <td>${e.length_bars} ${esc(span(e.length_bars, r.overview.timeframe))}</td>
          <td class="${e.recovered ? '' : 'neg'}">${e.recovered
            ? `${e.recovery_bars} ${esc(span(e.recovery_bars, r.overview.timeframe))}`
            : esc(L('chưa hồi', 'not recovered'))}</td></tr>`).join('') +
        '</tbody></table>';
    }

    html += `<table class="data-table rp-table"><tbody>
      ${row(L('Sụt giảm tối đa (tiền)', 'Max drawdown (currency)'),
        money(risk.max_drawdown_value), '', 'neg')}
      ${row(L('Số đợt sụt giảm', 'Drawdown episodes'), ep.count ?? '—')}
      ${row(L('Sụt giảm trung bình', 'Average drawdown'), upct(ep.average_depth_pct), '', 'neg')}
      ${row(L('Thời gian hồi trung bình', 'Average recovery'),
        ep.average_recovery_bars == null ? '—'
          : `${nf(ep.average_recovery_bars, 0)} ${span(ep.average_recovery_bars, r.overview.timeframe)}`)}
      ${row(L('Hồi lâu nhất', 'Longest recovery'),
        ep.longest_recovery_bars == null ? '—'
          : `${ep.longest_recovery_bars} ${span(ep.longest_recovery_bars, r.overview.timeframe)}`)}
      ${row(L('Sụt sâu nhất trong một lệnh', 'Worst single-trade drawdown'),
        upct(risk.max_trade_drawdown_pct), 'm.mae', 'neg')}
      ${row(L('Thời gian dưới đỉnh', 'Time under water'),
        L(`${upct(risk.bars_underwater_pct)} số nến`, `${upct(risk.bars_underwater_pct)} of bars`))}
      ${row(L('Nến sinh lời', 'Winning bars'), upct(ra.positive_bars_pct))}
      ${row(L('Độ lệch lợi suất nến', 'Skew of bar returns'), nf(ra.skew, 3))}
      ${row(L('Độ nhọn lợi suất nến', 'Kurtosis of bar returns'), nf(ra.kurtosis, 2))}
      ${row('VaR 95%', upct(ra.var_95_pct), 'p.var', 'neg')}
      ${row('CVaR 95%', upct(ra.cvar_95_pct), 'p.cvar', 'neg')}
      ${row('Sortino', ratio(risk.sortino), 'm.sortino')}
    </tbody></table>`;

    if (ep.unrecovered) {
      html += `<div class="callout warn">${esc(L(
        'Giai đoạn kết thúc khi đường vốn vẫn còn dưới đỉnh, đợt sụt giảm cuối cùng chưa hồi. Nó không có thời gian hồi phục để báo cáo, và độ sâu của nó vẫn còn có thể sâu thêm.',
        'The period ends with equity still below its peak, the last drawdown never recovered. It has no recovery time to report, and its depth can still get worse.'))}</div>`;
    }
    if (k?.note) {
      html += `<p class="table-note">${esc(L('Hệ số K: ', 'K-ratio: '))}${esc(tp(k.note) || k.note)}</p>`;
    }
    html += `<p class="table-note">${esc(L(
      'Sụt giảm trong quá khứ là cận dưới, không phải cận trên. Một giai đoạn dài hơn gần như luôn chứa một đợt sâu hơn đợt tệ nhất ở đây, hãy lấy con số này làm mức tối thiểu phải chịu được, không phải mức tối đa sẽ gặp.',
      'Past drawdown is a floor, not a ceiling. A longer period almost always contains something deeper than the worst here: read this as the minimum you must be able to sit through, not the maximum you will meet.'))}</p>`;
    return html;
  }

  const typicalDdExplain = (ep) => Explain.inline({
    title: L('Sụt giảm điển hình', 'Typical drawdown'),
    what: L('Trung vị độ sâu của mọi đợt sụt giảm, không chỉ đợt sâu nhất.',
            'The median depth across every drawdown episode, not just the deepest.'),
    rows: [[L('Số đợt', 'Episodes'), ep.count ?? '—'],
           [L('Trung vị', 'Median'), upct(ep.median_depth_pct)],
           [L('Trung bình', 'Mean'), upct(ep.average_depth_pct)]],
    how: L('Sụt giảm tối đa là MỘT quan sát, thường là quan sát cực đoan nhất trong toàn bộ lịch sử. Trung vị nói cho bạn biết một đợt sụt bình thường sâu bao nhiêu, tức là thứ bạn sẽ gặp hầu hết các lần.',
            'Max drawdown is a single observation, usually the most extreme in the whole record. The median tells you how deep a normal drawdown is, which is what you will meet most of the time.'),
  });

  const sterlingExplain = () => Explain.inline({
    title: L('Tỷ số Sterling', 'Sterling ratio'),
    what: L('Tăng trưởng hằng năm chia cho độ sâu TRUNG BÌNH của các đợt sụt giảm.',
            'Annual growth divided by the average drawdown depth.'),
    how: L('Cùng ý tưởng với CAR/MDD nhưng mẫu số không phụ thuộc vào đúng một đợt tệ nhất, nên nó ổn định hơn giữa các giai đoạn.',
            'The same idea as CAR/MDD, but the denominator does not hinge on one worst episode, so it is steadier across periods.'),
  });

  const burkeExplain = () => Explain.inline({
    title: L('Tỷ số Burke', 'Burke ratio'),
    what: L('Tăng trưởng hằng năm chia căn bậc hai của tổng bình phương mọi đợt sụt giảm.',
            'Annual growth divided by the root of the sum of squared drawdowns.'),
    formula: 'CAR / √( Σ depth² )',
    how: L('Bình phương làm các đợt sâu nặng ký hơn nhiều so với các đợt nông, nên Burke phạt một tai nạn lớn mạnh hơn Sterling, trong khi vẫn dùng toàn bộ lịch sử chứ không chỉ một điểm.',
            'Squaring weights deep episodes far above shallow ones, so Burke punishes one large accident harder than Sterling does while still using the whole record rather than a single point.'),
  });

  const omegaExplain = () => Explain.inline({
    title: L('Tỷ số Omega', 'Omega ratio'),
    what: L('Tổng phần lợi suất dương chia tổng phần lợi suất âm, ở ngưỡng 0.',
            'The sum of gains divided by the sum of losses, at a threshold of zero.'),
    how: L('Trên 1.0 là có lãi. Khác Sharpe ở chỗ nó dùng toàn bộ phân phối chứ không chỉ trung bình và độ lệch chuẩn, nên nó không bỏ qua đuôi.',
            'Above 1.0 is profitable. Unlike Sharpe it uses the whole distribution rather than just the mean and standard deviation, so it does not ignore the tails.'),
  });

  const gainPainExplain = (gp) => Explain.inline({
    title: 'Gain-to-pain',
    what: L('Tổng lợi suất chia tổng độ lớn của các tháng lỗ.',
            'Total return divided by the summed magnitude of the losing months.'),
    rows: [[L('Số tháng', 'Months'), gp.months ?? '—']],
    how: tp(gp.note) || gp.note,
    watch: L('Tính trên lợi suất THÁNG. Áp cùng công thức lên dữ liệu theo nến cho một con số nhỏ hơn nhiều ở một thang hoàn toàn khác, và so nó với ngưỡng 1.0 là vô nghĩa.',
             'Computed on monthly returns. The same formula on bar data gives a much smaller number on a completely different scale, and comparing that to the 1.0 threshold is meaningless.'),
  });

  const tailExplain = () => Explain.inline({
    title: L('Tỷ lệ đuôi', 'Tail ratio'),
    what: L('Phân vị 95 chia độ lớn phân vị 5 của lợi suất theo nến.',
            'The 95th percentile divided by the magnitude of the 5th percentile of bar returns.'),
    how: L('Dưới 1 nghĩa là những nến tệ nhất tệ hơn những nến tốt nhất tốt, một hình dạng phân phối mà lợi nhuận trung bình dương vẫn có thể che giấu.',
            'Below 1 means the worst bars are worse than the best bars are good, a shape that a positive average return can still hide.'),
  });

  const stabilityExplain = () => Explain.inline({
    title: L('Độ ổn định', 'Stability'),
    what: L('R² của hồi quy tuyến tính lợi suất cộng dồn theo thời gian.',
            'The R² of a linear regression of cumulative return against time.'),
    how: L('1.0 là một đường thẳng hoàn hảo. 0.3 nghĩa là phần lớn chuyển động của đường vốn không phải xu hướng, mà là dao động quanh nó.',
            '1.0 is a perfectly straight line. 0.3 means most of the equity curve’s movement is not trend but noise around it.'),
    watch: L('Độ ổn định cao không có nghĩa là lãi, một đường thẳng đi xuống cũng cho R² gần 1.',
             'High stability does not mean profitable: a straight line going down also scores near 1.'),
  });

  function periodTab(r) {
    const p = r.periodic;
    if (!p.monthly.length) {
      return `<p class="empty">${esc(L('Giai đoạn quá ngắn để chia theo tháng.',
                                        'The period is too short to split by month.'))}</p>`;
    }

    const years = [...new Set(p.monthly.map((m) => m.year))].sort();
    const lookup = new Map(p.monthly.map((m) => [`${m.year}-${m.month}`, m.return_pct]));
    const annual = new Map(p.annual.map((a) => [a.year, a.return_pct]));
    const scale = Math.max(...p.monthly.map((m) => Math.abs(m.return_pct)), 1);
    const shade = (value) => {
      const alpha = Math.min(Math.abs(value) / scale, 1) * 0.55;
      const colour = value >= 0 ? '30,142,62' : '217,48,37';
      return `background:rgba(${colour},${alpha.toFixed(3)})`;
    };

    let html = `<div class="metrics">
      ${card(L('Tháng có lãi', 'Winning months'), upct(p.positive_month_pct, 0), '',
        p.positive_month_pct >= 50 ? 'pos' : 'neg',
        L(`${p.positive_months}/${p.total_months} tháng`,
          `${p.positive_months} of ${p.total_months}`))}
      ${card(L('Tháng tốt nhất', 'Best month'), pct(p.best_month_pct), '', 'pos')}
      ${card(L('Tháng tệ nhất', 'Worst month'), pct(p.worst_month_pct), '', 'neg')}
    </div>`;

    const M = months();
    html += `<div class="rp-scroll"><table class="data-table rp-months">
      <thead><tr><th>${esc(L('Năm', 'Year'))}</th>${M.map((m) => `<th>${m}</th>`).join('')}
      <th>${esc(L('Cả năm', 'Year'))}</th></tr></thead><tbody>`;
    for (const year of years) {
      html += `<tr><td>${year}</td>`;
      for (let month = 1; month <= 12; month++) {
        const value = lookup.get(`${year}-${month}`);
        html += value === undefined
          ? '<td class="muted">·</td>'
          : `<td style="${shade(value)}">${nf(value, 1)}</td>`;
      }
      const total = annual.get(year);
      html += `<td class="${cls(total ?? 0)}"><strong>${
        total === undefined ? '—' : nf(total, 1)}</strong></td></tr>`;
    }
    html += '</tbody></table></div>';

    if (p.annual.length) {
      html += title(L('Lợi suất theo năm', 'Return by year'));
      html += annualChart(p.annual);
    }

    html += `<p class="table-note">${esc(L(
      `Chia kỳ theo ${p.timezone}, đúng múi giờ hiển thị trên biểu đồ. Lợi suất tháng đầu tiên tính từ vốn ban đầu. Nếu gần như toàn bộ lợi nhuận nằm trong hai hoặc ba ô, chiến lược này bắt được một đợt sóng chứ chưa chắc có lợi thế lặp lại được.`,
      `Periods are split in ${p.timezone}, the same zone the chart shows. The first month is measured from initial capital. If nearly all the profit sits in two or three cells, this strategy caught one move rather than proving a repeatable edge.`))}</p>`;
    return html;
  }

  function distributionTab(r) {
    const e = r.excursions;
    let html = title(L('Phân phối lợi suất từng lệnh', 'Distribution of trade returns'));
    html += histogram(r.charts.trade_returns,
      L('lợi suất mỗi lệnh, theo % ký quỹ', 'return per trade, % of margin'),
      L('Phân phối lợi suất từng lệnh', 'Distribution of trade returns'));

    html += title(L('Phân phối lợi suất theo nến', 'Distribution of bar returns'));
    html += histogram(r.charts.bar_returns,
      L('lợi suất đường vốn mỗi nến (%)', 'equity return per bar (%)'),
      L('Phân phối lợi suất theo nến', 'Distribution of bar returns'));
    html += `<p class="table-note">${esc(L(
      `Độ lệch ${nf(r.risk.ratios?.skew, 2)} và độ nhọn ${nf(r.risk.ratios?.kurtosis, 1)} (phân phối chuẩn có cả hai bằng 0). Đuôi càng dày thì Sharpe càng đánh giá thấp rủi ro, vì Sharpe chỉ nhìn hai mô-men đầu.`,
      `Skew ${nf(r.risk.ratios?.skew, 2)} and kurtosis ${nf(r.risk.ratios?.kurtosis, 1)} (a normal distribution has both at zero). The fatter the tails, the more Sharpe understates the risk, because Sharpe only looks at the first two moments.`))}</p>`;

    if (!e.count) return html;

    html += title(L('Lỗ tạm thời sâu nhất (MAE) so với kết quả',
                    'Worst unrealised loss (MAE) against outcome'));
    html += excursionScatter(e.points);

    html += `<table class="data-table rp-table"><thead><tr>
      <th>${esc(L('Nhóm lệnh', 'Group'))}</th>
      <th>${esc(L('MAE trung bình', 'Mean MAE'))}</th>
      <th>${esc(L('MAE trung vị', 'Median MAE'))}</th>
      <th>${esc(L('MFE trung bình', 'Mean MFE'))}</th></tr></thead><tbody>
      <tr><td>${esc(L('Lệnh thắng', 'Winners'))} ${Explain.button('m.mae', { title: 'MAE' })}</td>
        <td class="neg">${nf(e.mae_winners.mean)}%</td>
        <td class="neg">${nf(e.mae_winners.median)}%</td>
        <td class="pos">${nf(e.mfe_winners.mean)}%</td></tr>
      <tr><td>${esc(L('Lệnh thua', 'Losers'))} ${Explain.button('m.mfe', { title: 'MFE' })}</td>
        <td class="neg">${nf(e.mae_losers.mean)}%</td>
        <td class="neg">${nf(e.mae_losers.median)}%</td>
        <td class="pos">${nf(e.mfe_losers.mean)}%</td></tr>
    </tbody></table>`;

    html += `<div class="callout"><strong>${esc(L('Đặt dừng lỗ ở đâu.', 'Where a stop can go.'))}</strong>
      ${esc(tp(e.stop_note) || e.stop_note)} ${esc(L(
        `Ở đây lệnh thắng trung bình chìm ${nf(Math.abs(e.mae_winners.mean))}% trước khi có lãi, nên một mức dừng chặt hơn thế sẽ cắt chính chúng.`,
        `Here the average winner went ${nf(Math.abs(e.mae_winners.mean))}% under water before it turned, so a stop tighter than that cuts the winners.`))}</div>`;
    html += `<div class="callout"><strong>${esc(L('Có nên chốt lãi không.', 'Whether to take profit.'))}</strong>
      ${esc(tp(e.target_note) || e.target_note)} ${esc(L(
        `Ở đây lệnh thua trung bình từng xanh ${nf(e.mfe_losers.mean)}%.`,
        `Here the average loser was ${nf(e.mfe_losers.mean)}% in profit at some point.`))}</div>`;
    return html;
  }

  function mlTab(r) {
    const m = r.ml;
    if (m.error) {
      return `<div class="callout warn">${esc(tp(m.error) || m.error)}</div>
        <p class="table-note">${esc(L(
          'Phần này chấm tín hiệu như một bộ phân loại hướng của nến kế tiếp. Nó cần đủ số nến vừa có vị thế vừa có nến sau biến động.',
          'This scores the signal as a classifier of the next bar’s direction. It needs enough bars that both hold a position and are followed by a bar that moved.'))}</p>`;
    }

    const c = m.confusion;
    let html = `<div class="callout ${m.beats_baseline ? 'good' : 'warn'}">
      <strong>${esc(m.beats_baseline
        ? L('Vượt đường cơ sở.', 'Beats the baseline.')
        : L('Chưa vượt đường cơ sở.', 'Does not beat the baseline.'))}</strong>
      ${esc(tp(m.conclusion) || m.conclusion)}</div>`;

    html += '<div class="metrics">';
    html += card(L('Độ chính xác', 'Accuracy'), upct(m.accuracy * 100), 'ml.accuracy',
      m.beats_baseline ? 'pos' : '',
      L(`${m.n_scored.toLocaleString(I18n.locale())} nến được chấm`,
        `${m.n_scored.toLocaleString(I18n.locale())} bars scored`));
    html += card(L('Đường cơ sở', 'Baseline'), upct(m.baseline_accuracy * 100), 'ml.baseline',
      '', L('luôn đoán lớp phổ biến hơn', 'always predict the majority class'));
    html += card(L('Chênh lệch', 'Edge'),
      `${m.edge_pct >= 0 ? '+' : ''}${nf(m.edge_pct)} ${L('đpt', 'pp')}`,
      edgeExplain(m), cls(m.edge_pct), `p = ${Explain.pFormat(m.binomial_p)}`);
    html += card(L('Độ chính xác cân bằng', 'Balanced accuracy'),
      upct(m.balanced_accuracy * 100), balancedExplain(),
      m.balanced_accuracy > 0.5 ? 'pos' : 'neg', L('50% = đoán mò', '50% = chance'));
    html += card('MCC', nf(m.mcc, 3), 'ml.mcc', cls(m.mcc), L('0 = đoán mò', '0 = chance'));
    html += card(L("Cohen's kappa", "Cohen's kappa"), nf(m.cohens_kappa, 3), kappaExplain(),
      cls(m.cohens_kappa), L('đã trừ phần đúng do may', 'chance agreement removed'));
    html += '</div>';

    html += title(L('Hệ số thông tin', 'Information coefficient'));
    html += `<div class="metrics">
      ${card('IC', nf(m.information_coefficient, 4), icExplain(m),
        cls(m.information_coefficient),
        `p = ${Explain.pFormat(m.ic_p_value)}`)}
      ${card(L('Độ phủ', 'Coverage'), upct(m.coverage_pct), '', '',
        L('phần nến có dự đoán', 'share of bars with a prediction'))}
    </div>
    <p class="table-note">${esc(L(
      'Độ chính xác coi mọi nến như nhau: đoán đúng một cú tăng 3% và một cú tăng 0.05% đều tính là một lần đúng. Hệ số thông tin thì tính cả độ lớn, nên nó là con số gần với tiền hơn. Trong quản lý quỹ định lượng, IC quanh 0.03 đã là một tín hiệu dùng được.',
      'Accuracy treats every bar alike: calling a 3% move and a 0.05% move both count as one hit. The information coefficient weights magnitude, so it is the number closer to money. In quantitative fund management an IC around 0.03 is already a usable signal.'))}</p>`;

    html += title(L('Theo từng chiều', 'By side'));
    html += `<table class="data-table rp-table"><thead><tr>
      <th>${esc(L('Chiều', 'Side'))}</th><th>Precision</th><th>Recall</th><th>F1</th>
      </tr></thead><tbody>
      <tr><td>${esc(L('Mua', 'Long'))} ${Explain.button('ml.precision', { title: 'Precision' })}</td>
        <td>${upct(m.precision_long * 100)}</td><td>${upct(m.recall_long * 100)}</td>
        <td>${upct(m.f1_long * 100)}</td></tr>
      <tr><td>${esc(L('Bán', 'Short'))} ${Explain.button('ml.recall', { title: 'Recall' })}</td>
        <td>${upct(m.precision_short * 100)}</td><td>${upct(m.recall_short * 100)}</td>
        <td>${upct(m.f1_short * 100)}</td></tr>
    </tbody></table>`;

    html += title(L('Ma trận nhầm lẫn', 'Confusion matrix'),
      Explain.button('ml.confusion', { title: L('Ma trận nhầm lẫn', 'Confusion matrix') }));
    html += `<table class="data-table rp-table"><thead><tr><th></th>
      <th>${esc(L('Thực tế tăng', 'Actually up'))}</th>
      <th>${esc(L('Thực tế giảm', 'Actually down'))}</th></tr></thead><tbody>
      <tr><td>${esc(L('Đoán tăng', 'Predicted up'))}</td>
        <td class="pos">${c.true_up_pred_up}</td><td class="neg">${c.true_down_pred_up}</td></tr>
      <tr><td>${esc(L('Đoán giảm', 'Predicted down'))}</td>
        <td class="neg">${c.true_up_pred_down}</td><td class="pos">${c.true_down_pred_down}</td></tr>
    </tbody></table>`;

    if (m.probability) {
      const p = m.probability;
      html += title(L('Hiệu chuẩn xác suất', 'Probability calibration'));
      html += `<div class="metrics">
        ${card('ROC-AUC', p.roc_auc === null ? '—' : nf(p.roc_auc, 3), 'ml.auc',
          p.roc_auc > 0.5 ? 'pos' : 'neg', L('0,5 = vô dụng', '0.5 = useless'))}
        ${card('Brier', nf(p.brier, 4), 'ml.brier', '',
          L('càng nhỏ càng tốt', 'lower is better'))}
        ${card('Log-loss', nf(p.log_loss, 4), 'ml.logloss')}
      </div>`;
      if (p.calibration?.length) {
        html += `<table class="data-table rp-table"><thead><tr>
          <th>${esc(L('Xác suất dự báo', 'Predicted probability'))}</th>
          <th>${esc(L('Tần suất thực tế', 'Observed frequency'))}</th>
          <th>${esc(L('Số nến', 'Bars'))}</th></tr></thead><tbody>` +
          p.calibration.map((b) => `<tr>
            <td>${upct(b.predicted * 100)}</td>
            <td class="${Math.abs(b.predicted - b.observed) < 0.05 ? 'pos' : 'neg'}">${upct(b.observed * 100)}</td>
            <td class="muted">${b.count}</td></tr>`).join('') + '</tbody></table>';
        html += `<p class="table-note">${esc(L(
          'Mô hình hiệu chuẩn tốt thì hai cột đầu bám sát nhau: khi nó nói 70%, kết quả đúng khoảng 70% số lần đó.',
          'A well-calibrated model keeps the first two columns close: when it says 70%, it is right about 70% of the time.'))}</p>`;
      }
      html += `<p class="table-note">${esc(tp(p.note) || p.note)}</p>`;
    } else {
      html += `<p class="table-note">${esc(L(
        'Chiến lược này không công bố xác suất, nên không chấm được phần hiệu chuẩn. Để có phần đó, hãy gán df["ml_probability"] trong hàm signals().',
        'This strategy publishes no probabilities, so calibration cannot be scored. To get it, assign df["ml_probability"] inside signals().'))}</p>`;
    }

    html += `<p class="table-note">${esc(tp(m.note) || m.note)} ${esc(tp(m.assumptions) || m.assumptions)}</p>`;
    return html;
  }

  const edgeExplain = (m) => Explain.inline({
    title: L('Chênh lệch so với đường cơ sở', 'Edge over the baseline'),
    what: L('Độ chính xác trừ đi độ chính xác của quy tắc ngây thơ nhất, tính bằng điểm phần trăm.',
            'Accuracy minus the accuracy of the most naive rule, in percentage points.'),
    rows: [[L('Độ chính xác', 'Accuracy'), upct(m.accuracy * 100)],
           [L('Đường cơ sở', 'Baseline'), upct(m.baseline_accuracy * 100)],
           [L('p (nhị thức, một phía)', 'p (binomial, one-sided)'), Explain.pFormat(m.binomial_p)]],
    how: tp(m.conclusion) || m.conclusion,
    assumptions: tp(m.assumptions) || m.assumptions,
  });

  const balancedExplain = () => Explain.inline({
    title: L('Độ chính xác cân bằng', 'Balanced accuracy'),
    what: L('Trung bình recall của hai lớp.', 'The mean of the two classes’ recall.'),
    how: L('Một mô hình luôn đoán lớp phổ biến chỉ đạt đúng 50% ở đây, dù độ chính xác thô của nó có cao đến đâu. Đó là lý do con số này đáng tin hơn khi hai lớp lệch nhau.',
            'A model that always predicts the majority class scores exactly 50% here, however high its raw accuracy. That is why this figure is more trustworthy when the classes are imbalanced.'),
  });

  const kappaExplain = () => Explain.inline({
    title: L("Cohen's kappa", "Cohen's kappa"),
    what: L('Mức đồng thuận giữa dự đoán và thực tế, sau khi trừ đi phần đồng thuận do may.',
            'Agreement between prediction and outcome after removing the agreement expected by chance.'),
    how: L('0 nghĩa là không hơn gì đoán mò. Với hai lớp lệch nhau, đây là con số trung thực hơn độ chính xác thô, vốn có thể cao chỉ vì đoán mãi một phía.',
            'Zero means no better than chance. With imbalanced classes this is more honest than raw accuracy, which can be high purely from always guessing one side.'),
  });

  const icExplain = (m) => Explain.inline({
    title: L('Hệ số thông tin (IC)', 'Information coefficient (IC)'),
    what: L('Tương quan hạng Spearman giữa vị thế đang giữ và lợi suất nến kế tiếp.',
            'The Spearman rank correlation between the position held and the next bar’s return.'),
    rows: [['IC', nf(m.information_coefficient, 4)],
           ['p', Explain.pFormat(m.ic_p_value)],
           [L('Số nến', 'Bars'), m.n_scored]],
    how: L('Khác độ chính xác ở chỗ nó tính cả độ lớn: đoán đúng một cú tăng 3% được tính nặng hơn đoán đúng một cú 0.05%. Trong quản lý quỹ định lượng, IC quanh 0.03 đã là tín hiệu dùng được, và 0.10 là rất mạnh.',
            'Unlike accuracy it weights magnitude: calling a 3% move counts for more than calling a 0.05% one. In quantitative fund management an IC around 0.03 is already usable and 0.10 is very strong.'),
    watch: L('Hạng Spearman nên một lệnh đúng cực lớn không kéo được cả con số lên, nhưng IC vẫn giả định các nến độc lập, vị thế giữ qua nhiều nến thì không.',
             'Spearman ranks, so one enormous correct call cannot drag the figure up on its own, but IC still assumes independent bars, and a position held across many bars is not.'),
  });

  const TABS = [
    ['overview', 'rp.overview', overviewTab],
    ['trades', 'rp.trades', tradesTab],
    ['risk', 'rp.risk', riskTab],
    ['period', 'rp.period', periodTab],
    ['dist', 'rp.dist', distributionTab],
    ['ml', 'rp.ml', mlTab],
  ];

  // ---------- window ----------

  function paint() {
    if (!host || !data) return;
    const body = host.querySelector('.rp-body');
    const tab = TABS.find(([id]) => id === activeTab) || TABS[0];
    try {
      body.innerHTML = tab[2](data);
    } catch (err) {
      body.innerHTML = `<div class="callout bad">${esc(L(
        'Không dựng được tab này: ', 'Could not build this tab: '))}${esc(err.message)}</div>`;
      console.error(err);
    }
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.classList.toggle('active', button.dataset.tab === activeTab);
      button.setAttribute('aria-selected', String(button.dataset.tab === activeTab));
    }
    body.scrollTop = 0;
  }

  function bindTabs() {
    for (const button of host.querySelectorAll('.rp-tab')) {
      button.addEventListener('click', () => {
        activeTab = button.dataset.tab;
        paint();
      });
    }
  }

  const tabMarkup = () => TABS.map(([id, key]) =>
    `<button class="rp-tab" data-tab="${id}" role="tab">${esc(t(key))}</button>`).join('');

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
              · ${esc(t('rp.bars', { n: report.overview.bars.toLocaleString(I18n.locale()) }))}
              · ${esc(t('rp.tradeCount', { n: report.trades.all.count }))}</div>
          </div>
          <button class="btn btn-quiet btn-sm rp-close" aria-label="${esc(t('rp.close'))}">✕</button>
        </div>
        <div class="rp-tabs" role="tablist">${tabMarkup()}</div>
        <div class="rp-body"></div>
      </div>`;

    document.body.appendChild(host);
    host.querySelector('.rp-close').addEventListener('click', close);
    // Clicking the dark area outside the window closes it; clicking inside must
    // not, which is why this checks the target rather than using capture.
    host.addEventListener('click', (event) => {
      if (event.target === host) close();
    });
    bindTabs();
    document.addEventListener('keydown', onKey, true);

    paint();
    host.querySelector('.rp-close').focus();
  }

  /** Repaint in the current language, if the window is open. */
  function rerender() {
    if (!host || !data) return;
    host.querySelector('.rp-tabs').innerHTML = tabMarkup();
    bindTabs();
    paint();
  }

  function init(config) {
    onToast = config?.onToast || (() => {});
  }

  return { init, open, close, rerender };
})();
