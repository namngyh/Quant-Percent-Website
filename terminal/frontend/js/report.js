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

  const pct = (value, digits = 2) => Fmt.pct(value, digits);

  /** Unsigned percent, for quantities with no direction (exposure, win rate). */
  const upct = (value, digits = 1) =>
    Number.isFinite(value) ? `${value.toFixed(digits)}%` : '—';

  const money = (value) => Fmt.money(value, { digits: 0 });

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
    new Date((seconds + Settings.tzOffsetSeconds()) * 1000).toISOString().slice(0, 10);

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
      html += `<div class="callout bad">${esc(L(
        'Tài khoản cháy; các chỉ số chỉ tính đến thời điểm vốn về 0.',
        'Account wiped out; the figures cover the period up to the point equity reached zero.'))}</div>`;
    }
    if (!beat) {
      html += `<div class="callout warn">${esc(L(
        `Lợi nhuận thấp hơn mua và nắm giữ ${pct(o.vs_buy_hold_pct)} (chiến lược ${pct(o.net_profit_pct)}, mua và nắm giữ ${pct(o.buy_hold_pct)}).`,
        `Return is ${pct(o.vs_buy_hold_pct)} against buy-and-hold (strategy ${pct(o.net_profit_pct)}, buy-and-hold ${pct(o.buy_hold_pct)}).`))}</div>`;
    }

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
        '');
      html += card(L('Alpha (năm)', 'Alpha (annual)'), pct(b.alpha_annual_pct), '',
        cls(b.alpha_annual_pct),
        '');
      html += '</div>';
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
      html += `<div class="callout warn">${esc(L(
        `Giai đoạn dưới một năm: CAR và RAR là giá trị ngoại suy từ ${nf(o.years * 12, 1)} tháng dữ liệu.`,
        `Period under one year: CAR and RAR are extrapolated from ${nf(o.years * 12, 1)} months of data.`))}</div>`;
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
      html += `<div class="callout warn">${esc(L(
        `Chỉ chiều ${goodName} có lãi (${money(Math.abs(good.net_profit))}); chiều ${badName} lỗ ${money(Math.abs(bad.net_profit))}.`,
        `Only the ${goodName} side is profitable (${money(Math.abs(good.net_profit))}); the ${badName} side lost ${money(Math.abs(bad.net_profit))}.`))}</div>`;
    }
    if (t2.all.best_trade_share_pct > 40) {
      html += `<div class="callout warn">${esc(L(
        `Một lệnh chiếm ${upct(t2.all.best_trade_share_pct, 0)} tổng lãi; hệ số lợi nhuận ${ratio(t2.all.profit_factor)} phụ thuộc chủ yếu vào lệnh này.`,
        `One trade accounts for ${upct(t2.all.best_trade_share_pct, 0)} of gross profit; the profit factor of ${ratio(t2.all.profit_factor)} rests largely on it.`))}</div>`;
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
      ${line(L('Nến giữ lâu nhất', 'Longest hold'), (b) => nf(b.max_bars_held, 0))}
      ${line(L('Tổng số nến trong lệnh', 'Total bars in trades'),
        (b) => nf(b.total_bars_held, 0), barsHeldExplain())}
      ${line(L('Độ phân tán lợi suất', 'Return dispersion'),
        (b) => `${nf(b.std_dev_return_pct, 2)}%`, dispersionExplain())}
      ${line(L('Sụt giảm trong lệnh · tệ nhất', 'Worst intra-trade drawdown'),
        (b) => upct(b.max_trade_drawdown_pct), tradeDdExplain(), () => 'neg')}
      ${line(L('Sụt giảm trong lệnh · TB', 'Average intra-trade drawdown'),
        (b) => upct(b.avg_trade_drawdown_pct), tradeDdExplain(), () => 'neg')}
      ${line(L('Lời lớn nhất / lỗ lớn nhất', 'Largest win / largest loss'),
        (b) => (b.risk_reward_ratio === null ? '—' : ratio(b.risk_reward_ratio)))}
    </tbody></table>`;

    // How trades ended. A strategy whose positions mostly close because the
    // data ran out is not the strategy the metrics above describe.
    const reasons = t2.all.exit_reasons || {};
    const REASON = {
      signal: L('tín hiệu', 'signal'),
      liquidation: L('thanh lý', 'liquidation'),
      end_of_data: L('hết dữ liệu', 'end of data'),
    };
    if (Object.keys(reasons).length) {
      html += `<p class="table-note">${esc(L('Lý do đóng lệnh: ', 'Exit reasons: '))}${
        Object.entries(reasons)
          .map(([k, v]) => `${REASON[k] || k} ${v}`).join(' · ')}</p>`;
    }

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
    </div>`;

    html += title(L('Lãi lỗ cộng dồn theo thứ tự lệnh', 'Cumulative P&L in trade order'));
    html += sequenceChart(r);
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
    html += card('RAR/MDD', ratio(risk.rar_mdd), rarMddExplain(), risk.rar_mdd >= 1 ? 'pos' : '',
      L('đã trừ thời gian đứng ngoài', 'time out of the market removed'));
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
        'Đợt sụt giảm cuối chưa hồi phục tại thời điểm kết thúc giai đoạn.',
        'The final drawdown had not recovered by the end of the period.'))}</div>`;
    }
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

  const barsHeldExplain = () => Explain.inline({
    title: L('Số nến nắm giữ', 'Bars held'),
    what: L('Vốn bị khoá trong các vị thế tổng cộng bao lâu.',
            'How long capital was locked inside positions in total.'),
    how: L('Hai chiến lược cùng kỳ vọng mỗi lệnh nhưng một cái giữ 3 nến còn cái kia giữ 300 nến là hai sản phẩm khác hẳn nhau: cái sau khoá vốn lâu gấp trăm lần cho cùng một đồng lợi nhuận, và chịu rủi ro qua đêm gấp trăm lần.',
            'Two strategies with the same expectancy per trade but one holding 3 bars and the other 300 are quite different products: the second locks capital a hundred times longer for the same profit, and carries a hundred times the overnight risk.'),
    watch: L('Không phải thời gian phơi nhiễm của cả danh mục — một vị thế tại một thời điểm nên tổng số nến trong lệnh có thể nhỏ hơn nhiều so với số nến của kỳ kiểm tra. Cột "Phơi nhiễm" ở tab Tổng quan mới là tỷ lệ thời gian ở trong thị trường.',
             "Not portfolio exposure — one position at a time means total bars in trades can be far below the bars in the test period. The Exposure figure on the Overview tab is the share of time in the market."),
  });

  const dispersionExplain = () => Explain.inline({
    title: L('Độ phân tán lợi suất giữa các lệnh', 'Return dispersion across trades'),
    what: L('Độ lệch chuẩn lợi suất của từng lệnh, tính theo phần trăm ký quỹ.',
            'The standard deviation of per-trade return, as a percentage of margin committed.'),
    how: L('AmiBroker gọi cột này là Standard Error. Hai chiến lược cùng kỳ vọng nhưng độ phân tán gấp đôi thì cần khoảng gấp bốn số lệnh mới phân biệt được lợi thế thật với may mắn.',
            'AmiBroker calls this column Standard Error. Two strategies with the same expectancy but twice the dispersion need roughly four times as many trades before a real edge can be told from luck.'),
    watch: L('Theo phần trăm chứ không theo tiền, nên so được giữa các mức vốn khác nhau. Bản theo tiền là dòng "Sai số chuẩn của lãi TB" ngay trên.',
             'Expressed as a percentage rather than money, so it compares across capital levels. The money version is the standard-error row above.'),
  });

  const tradeDdExplain = () => Explain.inline({
    title: L('Sụt giảm trong một lệnh', 'Intra-trade drawdown'),
    what: L('Một lệnh đã đi ngược bao xa trước khi đóng, đo bằng MAE.',
            'How far a trade went against you before it closed, measured by MAE.'),
    how: L('Khác hẳn sụt giảm hệ thống: sụt giảm hệ thống nói tài khoản đã xuống bao nhiêu, còn con số này nói một lệnh đơn lẻ đã lỗ tạm bao nhiêu. Đây chính là mức mà một lệnh dừng lỗ sẽ cắt phải — đặt stop chặt hơn con số này nghĩa là cắt cả những lệnh cuối cùng vẫn có lãi.',
            'Quite different from system drawdown: system drawdown says how far the account fell, this says how far a single trade was underwater. It is exactly what a stop-loss would cut into — setting a stop tighter than this figure means cutting trades that went on to win.'),
    watch: L('Tính trên giá cao nhất/thấp nhất trong nến, gồm cả nến vào lệnh, vì lệnh khớp ở giá mở nến đó nên phần còn lại của nến thật sự diễn ra khi đã có vị thế.',
             "Computed on bar highs and lows including the entry bar, because the fill happens at that bar's open and the rest of its range genuinely occurs while the position is held."),
  });

  const rarMddExplain = () => Explain.inline({
    title: 'RAR/MDD',
    what: L('Lợi nhuận đã hiệu chỉnh theo thời gian ở trong thị trường, chia cho sụt giảm tối đa.',
            'Return adjusted for time in the market, divided by maximum drawdown.'),
    how: L('Giống CAR/MDD nhưng tử số đã chia cho tỷ lệ phơi nhiễm, nên một chiến lược chỉ vào lệnh 10% thời gian không bị phạt vì 90% còn lại đứng ngoài. Đọc cùng CAR/MDD: chênh lệch lớn giữa hai con số nghĩa là chiến lược đứng ngoài phần lớn thời gian.',
            'The same as CAR/MDD but with the numerator divided by exposure, so a strategy in the market only 10% of the time is not penalised for the other 90%. Read it alongside CAR/MDD: a large gap between them means the strategy sits out most of the time.'),
    watch: L('Thời gian đứng ngoài không phải là miễn phí trong thực tế — vốn vẫn bị giữ để sẵn sàng vào lệnh. RAR/MDD giả định phần vốn đó không có chi phí cơ hội.',
             'Time out of the market is not free in practice — the capital is still reserved to be ready. RAR/MDD assumes that capital has no opportunity cost.'),
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

    return html;
  }

  function mlTab(r) {
    const m = r.ml;
    // No block at all means the strategy publishes no probability, so there
    // is no model to evaluate. `visibleTabs` hides the tab in that case, but
    // this is a public entry point and reading `.error` off null is a crash
    // rather than a blank tab.
    if (!m) {
      return `<p class="empty">${esc(L(
        'Chiến lược này không xuất ra xác suất, nên không có mô hình để chấm. Tab này dành cho chiến lược học máy.',
        'This strategy publishes no probability, so there is no model to score. This tab is for machine-learning strategies.'))}</p>`;
    }
    if (m.error) {
      return `<div class="callout warn">${emph(esc(tp(m.error) || m.error))}</div>`;
    }

    const c = m.confusion;
    let html = m.beats_baseline ? '' : `<div class="callout warn">${esc(L(
      'Mô hình chưa vượt đường cơ sở.', 'The model does not beat the baseline.'))}</div>`;

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
    </div>`;

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
      }
    } else {
    }

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

  /* ---------- Risk management ----------

     The Risk tab above describes what happened. This one answers the question
     that description does not: given all that, how large should the position
     be? Everything here is derived from the strategy's own observed returns —
     there is no forecasting model anywhere in it. */

  function riskToolsTab(r) {
    const rt = r.risk_tools || {};
    const tail = rt.tail || {};
    const kel = rt.kelly || {};
    const bud = rt.budget || {};
    const lev = rt.leverage || {};

    let html = '';

    if (!tail.available) {
      html += `<div class="callout warn">${emph(esc(tp(tail.reason) || L(
        'Không đủ dữ liệu để đo rủi ro đuôi.',
        'Not enough data to measure tail risk.')))}</div>`;
    } else {
      html += `<div class="field-group-title">${esc(L(
        'Rủi ro đuôi', 'Tail risk'))} ${varCvarExplain(tail)}</div>`;
      html += `<table class="data-table stat-table"><thead><tr>
        <th>${esc(L('Mức tin cậy', 'Confidence'))}</th>
        <th>VaR</th><th>CVaR</th>
        <th>${esc(L('Khoảng tin cậy 95%', '95% interval'))}</th>
        <th>${esc(L('Cornish–Fisher', 'Cornish–Fisher'))}</th>
        <th>${esc(L('Số quan sát đuôi', 'Tail observations'))}</th>
        </tr></thead><tbody>`;
      for (const lv of tail.levels) {
        html += `<tr>
          <td>${lv.level_pct.toFixed(0)}%</td>
          <td class="neg">${lv.var_pct.toFixed(2)}%</td>
          <td class="neg">${lv.cvar_pct.toFixed(2)}%</td>
          <td class="muted">${lv.ci95_low_pct.toFixed(2)} … ${lv.ci95_high_pct.toFixed(2)}%</td>
          <td class="${lv.cornish_fisher_gap_pct < -0.01 ? 'neg' : 'muted'}">${
            lv.var_cornish_fisher_pct.toFixed(2)}%</td>
          <td class="${lv.thin_tail ? 'neg' : 'muted'}">${lv.tail_observations}${
            lv.thin_tail ? ' ⚠' : ''}</td>
        </tr>`;
      }
      html += '</tbody></table>';

      const thin = tail.levels.filter((lv) => lv.thin_tail);
      if (thin.length) {
        html += `<div class="callout warn">${emph(esc(tp(thin[0].note)))}</div>`;
      }
    }

    html += `<div class="field-group-title">${esc(L(
      'Cỡ vị thế', 'Position sizing'))}</div>`;
    html += '<div class="metrics">';
    if (kel.available) {
      html += card(L('Kelly', 'Kelly'), `${(kel.kelly_fraction * 100).toFixed(1)}%`,
        kellySizingExplain(kel), kel.kelly_fraction > 0 ? '' : 'neg',
        L(`tỷ lệ thắng ${(kel.win_rate * 100).toFixed(0)}%`,
          `win rate ${(kel.win_rate * 100).toFixed(0)}%`));
      html += card(L('Nửa Kelly', 'Half Kelly'),
        `${(kel.half_kelly_fraction * 100).toFixed(1)}%`, kellySizingExplain(kel), 'pos',
        L('mức thực dụng', 'the practical figure'));
    }
    if (bud.available) {
      html += card(L('Cỡ vị thế đề xuất', 'Suggested size'),
        `${bud.suggested_size_pct.toFixed(1)}%`, budgetExplain(bud),
        bud.capped ? 'neg' : 'pos',
        L(`cho ngân sách ${bud.budget_pct.toFixed(1)}%`,
          `for a ${bud.budget_pct.toFixed(1)}% budget`));
    }
    if (lev.available && lev.max_leverage_worst_bar) {
      html += card(L('Trần đòn bẩy', 'Leverage ceiling'),
        `${lev.max_leverage_worst_bar.toFixed(1)}x`, leverageExplain(lev), 'neg',
        L('theo nến tệ nhất đã gặp', 'from the worst bar seen'));
    }
    html += '</div>';

    if (bud.available && bud.capped) {
      html += `<div class="callout warn">${esc(L(
        `Ngân sách rủi ro ${bud.budget_pct.toFixed(1)}% đòi hỏi cỡ vị thế trên 100% vốn; đã giới hạn ở 100%.`,
        `A ${bud.budget_pct.toFixed(1)}% risk budget requires a position above 100% of equity; capped at 100%.`))}</div>`;
    }

    if (lev.available) {
      html += `<div class="field-group-title">${esc(L(
        'Đòn bẩy theo mức tin cậy', 'Leverage by confidence level'))}</div>`;
      html += `<table class="data-table stat-table"><thead><tr>
        <th>${esc(L('Mức tin cậy', 'Confidence'))}</th>
        <th>${esc(L('Biến động bất lợi', 'Adverse move'))}</th>
        <th>${esc(L('Đòn bẩy tối đa', 'Max leverage'))}</th>
        </tr></thead><tbody>`;
      for (const row2 of lev.levels) {
        html += `<tr><td>${row2.level_pct.toFixed(0)}%</td>
          <td class="neg">${row2.adverse_move_pct.toFixed(2)}%</td>
          <td>${row2.max_leverage === null ? '—' : `${row2.max_leverage.toFixed(1)}x`}</td></tr>`;
      }
      html += '</tbody></table>';
      html += `<div class="callout warn">${emph(esc(tp(lev.watch)))}</div>`;
    }

    html += marketRiskBlock();
    return html;
  }

  /* The team's own Monte Carlo read on VNINDEX, kept visibly apart from
     everything above it.

     Everything above measures the strategy the user just backtested. This
     measures the index, from a different model, on a different schedule. Two
     risk numbers on one screen invite the reader to treat them as comparable,
     so the heading says whose they are and the notes say what they cannot do. */
  let marketRisk = null;

  function marketRiskBlock() {
    if (!marketRisk?.available) return '';
    const latest = marketRisk.latest;
    const pct = (v, digits = 2) => (v === null || v === undefined ? '—' : `${v.toFixed(digits)}%`);

    let html = `<div class="field-group-title">${esc(L(
      'Rủi ro thị trường — mô hình của team (VNINDEX)',
      'Market risk — the team\'s model (VNINDEX)'))} ${marketRiskExplain()}</div>`;

    html += '<div class="stat-cards">';
    html += card(L('VaR 95%', 'VaR 95%'), pct(latest.var_95_pct), null, 'neg');
    html += card(L('ES 95%', 'ES 95%'), pct(latest.es_95_pct), null, 'neg');
    html += card(L('Biến động', 'Volatility'), pct(latest.volatility_pct), null, '');
    html += card(L('Sụt giảm hiện tại', 'Current drawdown'),
      pct(latest.current_drawdown_pct), null, 'neg',
      L(`60 phiên: ${pct(latest.rolling_drawdown_60d_pct)}`,
        `60 sessions: ${pct(latest.rolling_drawdown_60d_pct)}`));
    // The simulation error is printed beside the probability, not tucked away:
    // 51.39% from 10,000 paths carries ±0.50, so the last digit is noise.
    html += card(L('Xác suất giảm', 'Downside probability'),
      pct(latest.downside_probability_pct), null, '',
      latest.downside_sim_error_pct
        ? `± ${latest.downside_sim_error_pct.toFixed(2)} (${latest.mc_paths.toLocaleString()} ${
            L('đường', 'paths')})`
        : '');
    html += '</div>';

    if (marketRisk.distribution.length) {
      html += `<table class="data-table stat-table"><thead><tr>
        <th>${esc(L('Lỗ ít nhất', 'Loss of at least'))}</th>
        <th>${esc(L('Xác suất', 'Probability'))}</th>
        <th>${esc(L('Sai số mô phỏng', 'Simulation error'))}</th>
        </tr></thead><tbody>`;
      for (const row of marketRisk.distribution) {
        html += `<tr>
          <td class="neg">${row.loss_pct.toFixed(1)}%</td>
          <td>${row.probability_pct.toFixed(2)}%</td>
          <td class="muted">± ${row.sim_error_pct === null ? '—' : row.sim_error_pct.toFixed(2)}</td>
        </tr>`;
      }
      html += '</tbody></table>';
    }

    const gap = marketRisk.spacing_days;
    if (gap && gap.max > gap.median * 3) {
      html += `<div class="callout warn">${esc(L(
        `Dữ liệu gồm ${marketRisk.snapshots.length} ảnh chụp rời rạc; khoảng cách lớn nhất ${gap.max.toFixed(0)} ngày.`,
        `The data are ${marketRisk.snapshots.length} separate snapshots; the largest gap is ${gap.max.toFixed(0)} days.`))}</div>`;
    }
    return html;
  }

  const marketRiskExplain = () => Explain.inline({
    title: L('Rủi ro thị trường của team', 'The team\'s market risk model'),
    what: L('Mô phỏng Monte Carlo do pipeline của team chạy trên VNINDEX, không phải trên chiến lược của bạn. Đây là ý kiến thứ hai, độc lập với mọi con số phía trên.',
            'A Monte Carlo simulation the team\'s pipeline runs on VNINDEX, not on your strategy. A second opinion, independent of every number above it.'),
    how: L('Đọc cùng với bảng rủi ro đuôi phía trên: nếu chiến lược của bạn có CVaR nhẹ hơn thị trường thì đó là một lợi thế đáng nói, còn nếu nặng hơn thì bạn đang trả thêm rủi ro để lấy lợi nhuận.',
           'Read it against the tail-risk table above: a strategy with a lighter CVaR than the index has an edge worth naming, while a heavier one is paying extra risk for its return.'),
    watch: L('Ba giới hạn. Một, nó chỉ đo VNINDEX — không đo mã bạn đang xem. Hai, số đường mô phỏng không cố định giữa các lần chạy (10 000 và 40 000 đều xuất hiện), nên hai dòng in cùng số chữ số thập phân không mang cùng sai số; cột sai số mô phỏng nói ra điều đó. Ba, các ảnh chụp thưa và không đều, nên đừng nội suy giữa chúng.',
             'Three limits. One, it measures VNINDEX only — not the symbol you are looking at. Two, the path count is not constant between runs (both 10,000 and 40,000 appear), so two rows printed to the same decimals do not carry the same error; the simulation-error column says so. Three, the snapshots are sparse and irregular, so do not interpolate between them.'),
  });

  const varCvarExplain = (tail) => Explain.inline({
    title: L('VaR và CVaR', 'VaR and CVaR'),
    what: L('VaR là ngưỡng lỗ mà chỉ một tỷ lệ nhỏ số nến vượt qua. CVaR là mức lỗ trung bình khi đã vượt qua ngưỡng đó — tức là "khi mọi thứ tệ, tệ đến đâu".',
            'VaR is the loss threshold that only a small share of bars exceed. CVaR is the average loss once that threshold has been crossed — "when it goes bad, how bad".'),
    rows: [[L('Số nến', 'Bars'), String(tail.bars)]].concat(
      tail.levels.map((lv) => [
        `CVaR ${lv.level_pct.toFixed(0)}%`,
        `${lv.cvar_pct.toFixed(2)}% ±${lv.standard_error_pct.toFixed(2)} (${
          lv.tail_observations} ${L('quan sát', 'obs')})`])),
    how: L('CVaR luôn tệ hơn VaR, vì nó là trung bình của phần đuôi chứ không phải mép đuôi. Đọc CVaR để biết cần bao nhiêu vốn dự phòng; đọc VaR để biết ngưỡng nào bị vượt bao lâu một lần.',
            'CVaR is always worse than VaR, because it averages the tail rather than marking its edge. Read CVaR to size a buffer; read VaR to know how often a threshold is crossed.'),
    watch: L('CVaR 99% trên 2 000 nến là trung bình của 20 quan sát — khoảng tin cậy của nó rộng gấp gần ba lần CVaR 90%, dù hai con số in ra trông giống hệt nhau. Cột "số quan sát đuôi" là cột phải đọc trước. Ngoài ra CVaR lịch sử không bao giờ vượt quá cú lỗ tệ nhất đã xảy ra, nên trên một mẫu chưa gặp cú sập nào nó sẽ báo rằng cú sập không tồn tại; cột Cornish–Fisher tồn tại để bù đúng chỗ đó.',
             'CVaR at 99% on 2 000 bars is the mean of 20 observations — its confidence interval is nearly three times wider than the 90% figure, though the two print identically. The tail-observations column is the one to read first. Historical CVaR also can never exceed the worst loss already seen, so on a sample that has met no crash it reports that crashes do not exist; the Cornish–Fisher column exists to cover exactly that.'),
    source: 'Cornish & Fisher (1938); Rockafellar & Uryasev (2000).',
  });

  const kellySizingExplain = (kel) => Explain.inline({
    title: L('Phân số Kelly', 'Kelly fraction'),
    what: L('Tỷ lệ vốn đặt vào mỗi lệnh để tối đa hoá tốc độ tăng trưởng dài hạn.',
            'The share of capital per trade that maximises long-run growth rate.'),
    rows: [[L('Số lệnh', 'Trades'), String(kel.trades)],
           [L('Tỷ lệ thắng', 'Win rate'), `${(kel.win_rate * 100).toFixed(1)}%`],
           [L('Tỷ lệ lãi/lỗ', 'Payoff ratio'), kel.payoff_ratio.toFixed(2)],
           ['Kelly', `${(kel.kelly_fraction * 100).toFixed(1)}%`],
           [L('Nửa Kelly', 'Half Kelly'), `${(kel.half_kelly_fraction * 100).toFixed(1)}%`]],
    formula: 'f* = (p·b − q) / b',
    how: L('Tính trên lợi suất thật của từng lệnh so với vốn tại lúc mở lệnh, đúng đại lượng engine cộng dồn — không phải lãi lỗ chia cho vốn ban đầu.',
            "Computed from each trade's real return against the equity at the moment it opened, which is the quantity the engine compounds — not profit divided by starting capital."),
    watch: L('Kelly đầy đủ giả định lợi suất mỗi lệnh độc lập và phân phối không đổi; cả hai đều sai với chuỗi giao dịch thật. Nó còn được ước lượng trên chính mẫu đã sinh ra chiến lược nên thiên cao. Kelly đầy đủ đi kèm mức sụt giảm gần như không ai chịu nổi — nửa Kelly giữ khoảng 75% tốc độ tăng trưởng với một nửa biến động.',
             'Full Kelly assumes trade returns are independent and identically distributed; both are false for a real sequence. It is also estimated on the very sample the strategy came from, so it is biased high. Full Kelly comes with drawdowns almost nobody tolerates — half Kelly keeps roughly 75% of the growth rate at half the volatility.'),
  });

  const budgetExplain = (bud) => Explain.inline({
    title: L('Cỡ vị thế theo ngân sách rủi ro', 'Position size from a risk budget'),
    what: L('Chiều ngược của bảng CVaR: thay vì đo rủi ro của cỡ vị thế hiện tại, nó chọn cỡ vị thế cho một mức rủi ro cho trước.',
            'The inverse of the CVaR table: instead of measuring the risk of the current size, it picks a size for a stated level of risk.'),
    rows: [[L('Ngân sách', 'Budget'), `${bud.budget_pct.toFixed(2)}%`],
           [L('Mức tin cậy', 'Confidence'), `${bud.level_pct.toFixed(0)}%`],
           [L('CVaR đo được', 'Measured CVaR'), `${bud.measured_cvar_pct.toFixed(2)}%`],
           [L('Hệ số cỡ vị thế', 'Size multiplier'), `${bud.size_multiplier.toFixed(3)}x`],
           [L('Cỡ vị thế đề xuất', 'Suggested size'), `${bud.suggested_size_pct.toFixed(1)}%`]],
    how: L('Đọc là: "trong những phiên tệ nhất, tôi chấp nhận mất trung bình ngần này phần trăm vốn". Cỡ vị thế trả về là mức tạo ra đúng con số đó trên lịch sử đã đo.',
            'Read it as: "in the worst sessions I accept losing this much of capital on average". The size returned is the one that produces exactly that figure over the measured history.'),
    watch: L('Phép tỷ lệ tuyến tính đúng với ký quỹ và giá trị danh nghĩa nhưng KHÔNG đúng với thanh lý: vị thế lớn hơn làm khoảng cách tới giá thanh lý ngắn lại phi tuyến. Và nó giả định phân phối lợi suất tương lai giống quá khứ.',
             'The linear scaling is right for margin and notional but NOT for liquidation: a larger position shortens the distance to the liquidation price non-linearly. It also assumes the future return distribution matches the measured past.'),
  });

  const leverageExplain = (lev) => Explain.inline({
    title: L('Trần đòn bẩy', 'Leverage ceiling'),
    what: L('Mức đòn bẩy mà tại đó một nến xấu đủ sức chạm ngưỡng thanh lý.',
            'The leverage at which one bad bar is enough to reach liquidation.'),
    rows: [[L('Nến tệ nhất', 'Worst bar'), `${lev.worst_bar_pct.toFixed(2)}%`],
           [L('Hệ số an toàn', 'Safety factor'), lev.buffer.toFixed(2)]].concat(
      lev.levels.map((x) => [`${x.level_pct.toFixed(0)}%`,
        `${x.adverse_move_pct.toFixed(2)}% → ${
          x.max_leverage === null ? '—' : `${x.max_leverage.toFixed(1)}x`}`])),
    how: L('Với đòn bẩy L, một biến động bất lợi 1/L ăn hết ký quỹ. Bảng so 1/L với các phân vị đuôi đã quan sát, nên nó nói về những cú sốc đã thật sự xảy ra với chiến lược này.',
            'At leverage L, an adverse move of 1/L consumes the margin. The table compares 1/L against the observed tail quantiles, so it speaks about shocks that actually happened to this strategy.'),
    watch: L('Tính trên biến động theo giá đóng cửa. Thanh lý thật xét giá thấp nhất (mua) hoặc cao nhất (bán) TRONG nến, luôn xấu hơn giá đóng cửa — nên đây là trần trên, không phải mức an toàn.',
             'Computed on close-to-close moves. Real liquidation checks the bar’s low (long) or high (short) INSIDE the bar, which is always worse than the close — so this is an upper bound, not a safe level.'),
  });

  const TABS = [
    ['overview', 'rp.overview', overviewTab],
    ['trades', 'rp.trades', tradesTab],
    ['risk', 'rp.risk', riskTab],
    ['risktools', 'rp.riskTools', riskToolsTab],
    ['period', 'rp.period', periodTab],
    ['dist', 'rp.dist', distributionTab],
    ['ml', 'rp.ml', mlTab],
  ];

  // ---------- window ----------

  /* A tab whose payload is absent is not shown at all.

     The ML tab is built around a model's calibration, and a strategy that
     publishes no probability has none — the tab would be a page of dashes
     next to numbers the Overview already gives. Hiding it is more honest
     than rendering it empty. */
  function visibleTabs() {
    return TABS.filter(([id]) => id !== 'ml' || data?.ml);
  }

  function paint() {
    if (!host || !data) return;
    const body = host.querySelector('.rp-body');
    const available = visibleTabs();
    if (!available.some(([id]) => id === activeTab)) activeTab = available[0][0];
    const tab = available.find(([id]) => id === activeTab) || available[0];
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

  const tabMarkup = () => visibleTabs().map(([id, key]) =>
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
    loadMarketRisk();
  }

  /* Fetched after the window is already up, never before it.

     It is a second opinion on one tab; a report that would not open because
     the VPN is down, or because the team's risk view is empty, would be a
     worse report than one without it. Failure is silent for the same reason
     — there is nothing the reader is expected to do about it. */
  async function loadMarketRisk() {
    if (marketRisk !== null) return;      // one fetch per page load
    try {
      marketRisk = await API.vnRisk();
    } catch {
      marketRisk = { available: false };
      return;
    }
    if (host && activeTab === 'risktools') paint();
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

  return {
    init, open, close, rerender,
    // Exported for tests/test_render.js. Six tabs of several hundred numbers
    // each, read out of the payload by name: a metric the backend renames or
    // drops reaches the screen as "undefined" with no error anywhere, which is
    // exactly the failure this project has already shipped once.
    get tabs() { return TABS.map(([id, key]) => [id, key]); },
    // The tab strip is payload-dependent now, so the test needs to see what a
    // given report would actually offer rather than the full list.
    tabsFor(payload) {
      const held = data;
      data = payload;
      try { return visibleTabs().map(([id]) => id); } finally { data = held; }
    },
    renderTab(id, payload) {
      const entry = TABS.find(([tabId]) => tabId === id);
      if (!entry) throw new Error(`no such report tab: ${id}`);
      return entry[2](payload);
    },
    // Also for tests/test_render.js. The market-risk block arrives from its
    // own endpoint rather than from the report payload, so without a way to
    // set it the one part of that tab which talks about somebody else's model
    // would be the part nothing checks.
    setMarketRisk(value) { marketRisk = value; },
  };
})();
