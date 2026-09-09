/* Walk-forward validation, Monte Carlo, strategy comparison, and export.

   These share a panel because they answer one question between them: how much
   of a backtest number should be believed. Walk-forward removes hindsight,
   Monte Carlo puts a range around the result, and comparison says whether any
   of it beat the alternatives. */

const Validation = (() => {
  let elements = {};
  let context = () => ({});
  let execution = () => ({});
  let catalog = () => [];
  let onToast = () => {};
  // The date window the strategy panel is set to, so a validation run covers
  // the same period as the backtest it is validating.
  let period = () => ({});

  let lastResult = null;   // whatever was produced most recently, for export

  const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const num = (v, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '—');
  const money = (v) => v.toLocaleString('en-US', { maximumFractionDigits: 0 });
  const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

  function esc(value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  }

  const vnTime = (epochSeconds) =>
    new Date((epochSeconds + 7 * 3600) * 1000).toISOString().slice(0, 16).replace('T', ' ');

  function card(label, value, cls = '', sub = '') {
    return `<div class="metric">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value ${cls}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  // ---------- Walk-forward ----------

  async function runWalkForward(ranges) {
    const ctx = context();
    const result = await API.walkForward({
      strategyId: elements.strategySelect.value,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      ranges,
      metric: elements.metric.value,
      trainBars: Number(elements.trainBars.value) || 1000,
      testBars: Number(elements.testBars.value) || 250,
      purgeBars: Number(elements.purgeBars?.value) || 0,
      foldMode: elements.foldMode?.value || 'rolling',
      execution: execution(),
      period: period(),
    });
    lastResult = { kind: 'walk-forward', data: result };
    renderWalkForward(result);
    return result;
  }

  /* A small bar showing the in-sample rate against the out-of-sample one.
     Both are compounded to the test window's length, so the two bars are the
     same units and the gap between them is the whole point. */
  function degradationBar(s) {
    const scale = Math.max(Math.abs(s.is_mean_normalised_pct),
                           Math.abs(s.oos_mean_normalised_pct), 0.5);
    const width = (v) => `${Math.min(Math.abs(v) / scale * 100, 100).toFixed(1)}%`;
    const row = (label, value, klass) => `
      <div class="pf-bar-row">
        <span class="pf-bar-label">${esc(label)}</span>
        <div class="pf-bar-track"><div class="pf-bar ${klass}"
          style="width:${width(value)}"></div></div>
        <span class="pf-bar-value ${sign(value)}">${pct(value)}</span>
      </div>`;
    return `<div class="pf-bars">
      ${row(L('Trong mẫu', 'In sample'), s.is_mean_normalised_pct, 'weight')}
      ${row(L('Ngoài mẫu', 'Out of sample'), s.oos_mean_normalised_pct, 'risk')}
      <p class="table-note">${esc(tp(s.measured_on))}</p>
    </div>`;
  }

  function renderWalkForward(result) {
    const s = result.summary;
    const settings = result.settings;
    let html = '';

    // With only a fold or two, the averages are one or two numbers wearing a
    // statistic's clothing. Say so before any verdict is drawn from them.
    const thin = s.total_folds < 3;
    if (thin) {
      const need = settings.train_bars + settings.test_bars * 3;
      html += `<div class="callout warn"><strong>${esc(L(
        `Chỉ ${s.total_folds} vòng (chưa kết luận được).`,
        `Only ${s.total_folds} folds, which is not enough to conclude.`))}</strong>
        ${esc(L(
          `Cần ít nhất 3-5 vòng thì trung bình mới có nghĩa. Tăng số nến lên khoảng ${need.toLocaleString(I18n.locale())}, hoặc giảm cửa sổ huấn luyện/kiểm tra.`,
          `Three to five folds are needed before an average means anything. Raise the bar count to about ${need.toLocaleString(I18n.locale())}, or shorten the windows.`))}</div>`;
    }

    if (result.failed_folds?.length) {
      html += `<div class="callout warn"><strong>${esc(L(
        `${result.failed_folds.length} vòng không chạy được.`,
        `${result.failed_folds.length} folds could not run.`))}</strong>
        ${esc(result.failed_folds[0].error || L('Không tổ hợp nào cho điểm hữu hạn.',
                                                 'No combination produced a finite score.'))}</div>`;
    }

    if (s.overfit_warning && !thin) {
      html += `<div class="callout bad"><strong>${esc(L(
        'Chiến lược không sống sót ngoài mẫu.',
        'The strategy does not survive out of sample.'))}</strong>
        ${esc(L(
          `Trong mẫu ${pct(s.is_mean_normalised_pct)}/vòng, ngoài mẫu ${pct(s.oos_mean_normalised_pct)}/vòng, đo trên cùng độ dài cửa sổ. Tham số đang khớp với nhiễu của quá khứ, không phải với thị trường.`,
          `In sample ${pct(s.is_mean_normalised_pct)} per fold against ${pct(s.oos_mean_normalised_pct)} out of sample, measured over the same window length. The parameters are fitting past noise rather than the market.`))}</div>`;
    } else if (s.degradation_pct > 2 && !thin) {
      html += `<div class="callout warn">${esc(L(
        `Ngoài mẫu kém trong mẫu ${s.degradation_pct.toFixed(2)} điểm %. Chênh lệch này chính là cái giá của việc chọn tham số bằng hậu nghiệm.`,
        `Out of sample trails in sample by ${s.degradation_pct.toFixed(2)} points. That gap is the price of having chosen the parameters with hindsight.`))}</div>`;
    } else if (!thin) {
      html += `<div class="callout good">${esc(L(
        `Ngoài mẫu bám sát trong mẫu (chênh ${s.degradation_pct.toFixed(2)} điểm %). Đây là dấu hiệu tốt.`,
        `Out of sample tracks in sample closely (a gap of ${s.degradation_pct.toFixed(2)} points). That is a good sign.`))}</div>`;
    }

    html += '<div class="metrics">';
    html += cardX(L('Ngoài mẫu · tổng', 'Out of sample · total'),
      pct(s.oos_total_return_pct), '', sign(s.oos_total_return_pct),
      L(`${money(s.oos_final_equity)} cuối kỳ`, `${money(s.oos_final_equity)} final`));
    const wfe = wfeCard(s);
    html += cardX(L('Hiệu suất walk-forward', 'Walk-forward efficiency'),
      wfe.value, wfeExplain(s), wfe.tone, wfe.sub);
    html += cardX(L('Suy giảm', 'Degradation'),
      `${s.degradation_pct >= 0 ? '−' : '+'}${Math.abs(s.degradation_pct).toFixed(2)} ${L('đ%', 'pts')}`,
      degradationExplain(s), s.degradation_pct > 0 ? 'neg' : 'pos',
      L('đã chuẩn hoá độ dài cửa sổ', 'window length normalised'));
    html += cardX(L('Suy giảm Sharpe', 'Sharpe degradation'),
      num(s.degradation_sharpe), '', s.degradation_sharpe > 0 ? 'neg' : 'pos',
      L('không phụ thuộc thang đo', 'scale free'));
    html += cardX(L('Sụt giảm tối đa', 'Max drawdown'),
      `-${s.oos_max_drawdown_pct.toFixed(1)}%`, 'm.max_dd', 'neg',
      L('trên đường vốn ngoài mẫu', 'on the out-of-sample curve'));
    html += cardX(L('Vòng có lãi', 'Profitable folds'),
      `${s.profitable_folds}/${s.total_folds}`, '',
      s.consistency_pct >= 50 ? 'pos' : 'neg',
      L(`${s.consistency_pct.toFixed(0)}% số vòng`, `${s.consistency_pct.toFixed(0)}% of folds`));
    html += '</div>';

    html += `<div class="field-group-title">${esc(L(
      'Trong mẫu so với ngoài mẫu', 'In sample against out of sample'))}</div>`;
    html += degradationBar(s);

    // Parameter stability: a strategy with no stable optimum is fitting each
    // window rather than the market, and the fold table alone does not say so.
    const stability = result.stability;
    if (stability?.parameters?.length) {
      html += `<div class="field-group-title">${esc(L(
        'Độ ổn định tham số', 'Parameter stability'))} ${stabilityExplain()}</div>`;
      html += `<table class="data-table"><thead><tr>
        <th>${esc(L('Tham số', 'Parameter'))}</th>
        <th>${esc(L('Trung bình', 'Mean'))}</th>
        <th>${esc(L('Độ lệch', 'Std dev'))}</th>
        <th>${esc(L('Hệ số biến thiên', 'Coeff. of variation'))}</th>
        <th>${esc(L('Giá trị khác nhau', 'Distinct values'))}</th>
        </tr></thead><tbody>` +
        stability.parameters.map((p) => `<tr>
          <td>${esc(p.name)}</td>
          <td>${num(p.mean)}</td>
          <td>${num(p.std)}</td>
          <td class="${p.coefficient_of_variation > 0.5 ? 'neg' : 'pos'}">${num(p.coefficient_of_variation)}</td>
          <td class="muted">${p.distinct_values} / ${p.folds}</td>
        </tr>`).join('') + '</tbody></table>';
      if (stability.note) {
        html += `<div class="callout warn">${esc(tp(stability.note))}</div>`;
      }
    }

    const names = Object.keys(result.folds[0]?.params || {});
    html += `<div class="field-group-title">${esc(L('Từng vòng', 'Fold by fold'))}</div>`;
    html += `<table class="data-table"><thead><tr><th>${esc(L('Vòng', 'Fold'))}</th>`;
    for (const n of names) html += `<th>${esc(n)}</th>`;
    html += `<th>${esc(L('Trong mẫu', 'In sample'))}</th>
      <th>${esc(L('(đã chuẩn hoá)', '(normalised)'))}</th>
      <th>${esc(L('Ngoài mẫu', 'Out of sample'))}</th>
      <th>MaxDD</th><th>${esc(L('Lệnh', 'Trades'))}</th>
      <th>${esc(L('Từ', 'From'))}</th></tr></thead><tbody>`;
    for (const f of result.folds) {
      const oos = f.out_of_sample;
      html += `<tr><td>${f.fold}</td>`;
      for (const n of names) html += `<td>${esc(f.params[n])}</td>`;
      html += `<td class="${sign(f.in_sample.return_pct)} muted">${f.in_sample.return_pct.toFixed(1)}%</td>`;
      html += `<td class="${sign(f.in_sample.return_normalised_pct)}">${f.in_sample.return_normalised_pct.toFixed(1)}%</td>`;
      html += `<td class="${sign(oos.return_pct)}">${oos.return_pct.toFixed(1)}%</td>`;
      html += `<td class="neg">-${oos.max_drawdown_pct.toFixed(1)}%</td>`;
      html += `<td class="muted">${oos.num_trades}</td>`;
      html += `<td class="muted">${vnTime(f.test_from)}</td></tr>`;
    }
    html += '</tbody></table>';

    const modeLabel = settings.fold_mode === 'anchored'
      ? L('neo gốc (cửa sổ nở dần)', 'anchored (expanding window)')
      : L('trượt (cửa sổ cố định)', 'rolling (fixed window)');
    html += `<p class="table-note">${esc(L(
      `Chế độ ${modeLabel}. Mỗi vòng tối ưu trên ${settings.train_bars} nến${settings.purge_bars ? `, bỏ ${settings.purge_bars} nến cách ly` : ''}, rồi áp nguyên tham số đó lên ${settings.test_bars} nến kế tiếp. Chỉ cột "Ngoài mẫu" là ước lượng trung thực; cột "Trong mẫu" thô dài hơn nên cột đã chuẩn hoá mới là cột so sánh được.`,
      `Mode: ${modeLabel}. Each fold optimises over ${settings.train_bars} bars${settings.purge_bars ? `, drops ${settings.purge_bars} purged bars` : ''}, then applies those parameters unchanged to the next ${settings.test_bars}. Only the out-of-sample column is an honest estimate; the raw in-sample column covers a longer window, so the normalised one is the comparable figure.`))}</p>`;

    elements.output.innerHTML = html;
  }

  /* Walk-forward efficiency reads as "the share that survived" only when both
     sides are positive. The backend names the other two cases rather than
     leaving the interface to print a ratio under a label it does not fit. */
  function wfeCard(s) {
    switch (s.walk_forward_efficiency_code) {
      case 'inverted':
        return {
          value: L('Đảo chiều', 'Inverted'),
          tone: 'neg',
          sub: L('ngoài mẫu lỗ trong khi trong mẫu lãi',
                 'lost out of sample while making money in sample'),
        };
      case 'no_is_edge':
        return {
          value: '—',
          tone: 'neg',
          sub: L('trong mẫu không có lợi thế để mà sống sót',
                 'no in-sample edge for anything to survive'),
        };
      default:
        return {
          value: num(s.walk_forward_efficiency),
          tone: s.walk_forward_efficiency >= 0.5 ? 'pos' : 'neg',
          sub: L('phần lợi thế sống sót', 'share of the edge that survived'),
        };
    }
  }

  const wfeExplain = (s) => Explain.inline({
    title: L('Hiệu suất walk-forward', 'Walk-forward efficiency'),
    what: L('Phần lợi thế trong mẫu còn sống sót khi ra ngoài mẫu.',
            'The share of the in-sample edge that survives out of sample.'),
    rows: [[L('Trong mẫu', 'In sample'), pct(s.is_mean_normalised_pct)],
           [L('Ngoài mẫu', 'Out of sample'), pct(s.oos_mean_normalised_pct)],
           [L('Tỷ lệ', 'Ratio'),
            s.walk_forward_efficiency === null ? '—' : num(s.walk_forward_efficiency)],
           [L('Trạng thái', 'State'), {
             inverted: L('lợi thế đảo chiều', 'edge inverted'),
             no_is_edge: L('không có lợi thế trong mẫu', 'no in-sample edge'),
           }[s.walk_forward_efficiency_code] || L('tỷ lệ đọc được', 'readable ratio')]],
    how: L('Trên 0.5 là ngưỡng thông dụng cho một chiến lược đáng chạy thật: quá nửa lợi thế đo được trong mẫu vẫn còn khi gặp dữ liệu chưa thấy. Âm nghĩa là ngoài mẫu lỗ trong khi trong mẫu lãi.',
            'Above 0.5 is the conventional bar for a strategy worth trading: more than half the measured edge survives contact with unseen data. Negative means it lost money out of sample while making it in sample.'),
    watch: L('Tính từ trung bình các vòng, nên với ít vòng nó rất nhiễu. Dưới 3 vòng thì đừng đọc con số này. Khi trong mẫu gần bằng 0, tỷ lệ không có mẫu số đáng chia nên thẻ hiện một gạch ngang thay vì một con số lớn vô nghĩa.',
             'Computed from a fold average, so it is noisy when there are few folds. Below three folds, do not read it. When the in-sample rate is near zero the ratio has no denominator worth dividing by, so the card shows a dash instead of a large meaningless number.'),
  });

  const degradationExplain = (s) => Explain.inline({
    title: L('Suy giảm trong mẫu → ngoài mẫu', 'In-sample to out-of-sample degradation'),
    what: L('Khoảng cách giữa lợi nhuận trong mẫu và ngoài mẫu, sau khi quy cả hai về cùng độ dài cửa sổ.',
            'The gap between in-sample and out-of-sample return, after compounding both to the same window length.'),
    rows: [[L('Trong mẫu (chuẩn hoá)', 'In sample (normalised)'), pct(s.is_mean_normalised_pct)],
           [L('Ngoài mẫu', 'Out of sample'), pct(s.oos_mean_normalised_pct)],
           [L('Suy giảm', 'Degradation'), `${s.degradation_pct.toFixed(2)} ${L('đ%', 'pts')}`],
           [L('Suy giảm Sharpe', 'Sharpe degradation'), num(s.degradation_sharpe)]],
    how: L('Đây là cái giá của việc chọn tham số bằng hậu nghiệm. Càng gần 0 càng tốt; âm nghĩa là ngoài mẫu còn tốt hơn, thường là may.',
            'This is the price of choosing parameters with hindsight. Closer to zero is better; negative means out of sample did better, which is usually luck.'),
    watch: L('Con số này từng được đo bằng cách trừ thẳng hai lợi nhuận tổng, trong khi cửa sổ huấn luyện dài gấp bốn lần cửa sổ kiểm tra. Nó tăng theo độ dài cửa sổ chứ không theo mức overfit. Giờ cả hai vế đã quy về cùng độ dài.',
             'This figure used to subtract two raw totals while the training window was four times the test window, so it grew with window length rather than with overfitting. Both sides are now compounded to the same horizon.'),
  });

  const stabilityExplain = () => Explain.inline({
    title: L('Độ ổn định tham số', 'Parameter stability'),
    what: L('Tham số được chọn thay đổi bao nhiêu giữa các vòng.',
            'How much the chosen parameters move from one fold to the next.'),
    formula: L('hệ số biến thiên = độ lệch chuẩn / |trung bình|',
               'coefficient of variation = standard deviation / |mean|'),
    how: L('Chiến lược có điểm tối ưu thật thì mỗi vòng chọn ra giá trị gần nhau. Tham số nhảy loạn nghĩa là không có điểm tối ưu: mỗi vòng đang khớp vào đúng cửa sổ vừa nhìn thấy.',
            'A strategy with a genuine optimum picks similar values every fold. Parameters that jump around mean there is no optimum: each fold is fitting the window it just saw.'),
    watch: L('Trên 0.5 là dấu hiệu đáng lo, kể cả khi lợi nhuận ngoài mẫu vẫn dương: tham số tốt nhất của vòng cuối không có lý do gì để tốt ở vòng tiếp theo.',
             'Above 0.5 is a warning even when out-of-sample return is positive: the last fold’s best parameters have no reason to be good in the next one.'),
  });

  // ---------- Monte Carlo ----------

  async function runMonteCarlo(params) {
    const ctx = context();
    const result = await API.monteCarlo({
      strategyId: elements.strategySelect.value,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      params,
      simulations: Number(elements.simulations.value) || 1000,
      execution: execution(),
      period: period(),
    });
    lastResult = { kind: 'monte-carlo', data: result };
    renderMonteCarlo(result);
    return result;
  }

  /* The simulated outcomes as a fan, with the real result marked on it.
     A table of percentiles states the range; this shows the shape, and where
     history's single draw actually fell inside it. */
  function fanChart(method, actual, label) {
    const keys = ['p5', 'p25', 'p50', 'p75', 'p95'];
    const values = keys.map((k) => method.return_pct[k]);
    const all = [...values, actual];
    const min = Math.min(...all);
    const max = Math.max(...all);
    const span = max - min || 1;
    const x = (v) => ((v - min) / span) * 940 + 30;
    const H = 96;

    const band = (lo, hi, y, h, opacity) =>
      `<rect x="${x(lo).toFixed(1)}" y="${y}" width="${Math.max(x(hi) - x(lo), 1).toFixed(1)}"
        height="${h}" fill="var(--accent)" opacity="${opacity}" rx="3"/>`;

    return `<div class="rp-chart">
      <div class="rp-chart-head"><span class="rp-legend">
        <i style="background:var(--accent)"></i>${esc(label)}</span>
        <span class="rp-legend"><i style="background:var(--down)"></i>${
          esc(L('kết quả thật', 'the real result'))}</span></div>
      <svg viewBox="0 0 1000 ${H}" preserveAspectRatio="none" class="rp-svg mc-fan"
           role="img" aria-label="${esc(label)}">
        ${band(values[0], values[4], 34, 28, 0.18)}
        ${band(values[1], values[3], 34, 28, 0.34)}
        <line x1="${x(values[2]).toFixed(1)}" y1="28" x2="${x(values[2]).toFixed(1)}" y2="70"
              stroke="var(--accent)" stroke-width="2"/>
        <line x1="${x(actual).toFixed(1)}" y1="20" x2="${x(actual).toFixed(1)}" y2="78"
              stroke="var(--down)" stroke-width="2"/>
        <circle cx="${x(actual).toFixed(1)}" cy="20" r="4" fill="var(--down)"/>
      </svg>
      <div class="rp-axis">
        <span>${pct(min)}</span>
        <span>${esc(L('p5 - p25 - trung vị - p75 - p95', 'p5 - p25 - median - p75 - p95'))}</span>
        <span>${pct(max)}</span>
      </div>
    </div>`;
  }

  /** Probability of touching each drawdown level, under both resamplers. */
  function drawdownComparison(r) {
    const keys = ['p5', 'p25', 'p50', 'p75', 'p95'];
    const block = r.methods.block.max_drawdown_pct;
    const independent = r.methods.independent.max_drawdown_pct;
    const scale = Math.max(...keys.map((k) => Math.max(block[k], independent[k])), 1);
    const bar = (value, klass) =>
      `<div class="pf-bar-track slim"><div class="pf-bar ${klass}"
        style="width:${(value / scale * 100).toFixed(1)}%"></div></div>`;

    return `<table class="data-table"><thead><tr>
      <th>${esc(L('Phân vị', 'Percentile'))}</th>
      <th>${esc(L('Theo khối', 'Block'))}</th><th></th>
      <th>${esc(L('Độc lập', 'Independent'))}</th><th></th>
      </tr></thead><tbody>` +
      keys.map((k) => `<tr>
        <td>${k}</td>
        <td class="neg">-${block[k].toFixed(1)}%</td><td>${bar(block[k], 'risk')}</td>
        <td class="muted">-${independent[k].toFixed(1)}%</td><td>${bar(independent[k], 'weight')}</td>
      </tr>`).join('') + '</tbody></table>';
  }

  function renderMonteCarlo(r) {
    const block = r.methods.block;
    const ret = r.return_pct;
    const dd = r.max_drawdown_pct;
    let html = '';

    for (const note of r.notes || []) {
      html += `<div class="callout">${esc(tp(note))}</div>`;
    }

    if (r.probability_of_loss_pct > 45) {
      html += `<div class="callout warn"><strong>${esc(L(
        'Gần như tung đồng xu.', 'Close to a coin flip.'))}</strong>
        ${esc(L(
          `${r.probability_of_loss_pct.toFixed(0)}% số kịch bản kết thúc thua lỗ. Kết quả đơn lẻ ${pct(r.actual_return_pct)} không nói lên nhiều điều.`,
          `${r.probability_of_loss_pct.toFixed(0)}% of scenarios end in a loss. The single result of ${pct(r.actual_return_pct)} says little on its own.`))}</div>`;
    }
    if (r.probability_of_ruin_pct > 1) {
      const ruin = block.probability_of_ruin;
      html += `<div class="callout bad"><strong>${esc(L(
        `${ruin.pct.toFixed(1)}% kịch bản chạm mức mất ${(100 - r.ruin_threshold_pct).toFixed(0)}% vốn.`,
        `${ruin.pct.toFixed(1)}% of scenarios touch a ${(100 - r.ruin_threshold_pct).toFixed(0)}% loss of capital.`))}</strong>
        ${esc(L(
          `Khoảng tin cậy ${ruin.ci95_low_pct.toFixed(1)}-${ruin.ci95_high_pct.toFixed(1)}%. Đo dọc đường đi, nên một đường chạm đáy rồi hồi lại vẫn được tính là đã cháy. Hạ đòn bẩy hoặc giảm % vốn mỗi lệnh.`,
          `Confidence interval ${ruin.ci95_low_pct.toFixed(1)}-${ruin.ci95_high_pct.toFixed(1)}%. Measured along the path, so an account that hit bottom and recovered still counts as ruined. Cut the leverage or the size per trade.`))}</div>`;
    }

    html += '<div class="metrics">';
    html += cardX(L('Kết quả thực tế', 'The real result'), pct(r.actual_return_pct),
      percentileExplain(r), sign(r.actual_return_pct),
      L(`phân vị ${r.actual_percentile.toFixed(0)} của phân phối`,
        `${r.actual_percentile.toFixed(0)}th percentile of the distribution`));
    html += cardX(L('Trung vị (p50)', 'Median (p50)'), pct(ret.p50), '', sign(ret.p50),
      L('kỳ vọng hợp lý hơn', 'the more reasonable expectation'));
    html += cardX(L('Kém (p5)', 'Poor (p5)'), pct(ret.p5), '', 'neg',
      L('1 trong 20 tệ hơn mức này', '1 in 20 is worse than this'));
    html += cardX(L('Tốt (p95)', 'Good (p95)'), pct(ret.p95), '', 'pos',
      L('1 trong 20 tốt hơn mức này', '1 in 20 is better than this'));
    html += cardX(L('Xác suất lỗ', 'Chance of a loss'),
      `${r.probability_of_loss_pct.toFixed(1)}%`,
      probabilityExplain(block.probability_of_loss, r.simulations),
      r.probability_of_loss_pct > 50 ? 'neg' : '',
      L(`± ${block.probability_of_loss.standard_error_pct.toFixed(1)} điểm`,
        `± ${block.probability_of_loss.standard_error_pct.toFixed(1)} points`));
    html += cardX(L('Sụt giảm p95', 'Drawdown p95'), `-${dd.p95.toFixed(1)}%`,
      'm.max_dd', 'neg',
      L(`thực tế -${r.actual_max_drawdown_pct.toFixed(1)}%`,
        `real -${r.actual_max_drawdown_pct.toFixed(1)}%`));
    html += '</div>';

    html += `<div class="field-group-title">${esc(L(
      'Phân phối kết quả, và chỗ kết quả thật rơi vào',
      'The distribution, and where the real result landed'))}</div>`;
    html += fanChart(block, r.actual_return_pct,
      L('khoảng mô phỏng (theo khối)', 'simulated range (block)'));

    html += `<div class="field-group-title">${esc(L(
      'Hai cách lấy mẫu', 'Two resamplers'))} ${resamplerExplain(r)}</div>`;
    html += drawdownComparison(r);
    html += `<p class="table-note">${esc(L(
      `Lấy mẫu theo khối giữ nguyên các chuỗi thắng/thua liền nhau (khối trung bình ${r.block_length.toFixed(0)} lệnh); lấy mẫu độc lập rút từng lệnh riêng lẻ. Chênh lệch ở p95 là ${r.ordering_effect_pct >= 0 ? '+' : ''}${r.ordering_effect_pct.toFixed(1)} điểm, và đó chính là phần rủi ro đến từ TRẬT TỰ các lệnh chứ không từ bản thân các lệnh.`,
      `Block sampling keeps runs of consecutive trades together (average block ${r.block_length.toFixed(0)} trades); independent sampling draws each trade separately. The gap at p95 is ${r.ordering_effect_pct >= 0 ? '+' : ''}${r.ordering_effect_pct.toFixed(1)} points, and that is the part of the risk that comes from the ORDER of the trades rather than the trades themselves.`))}</p>`;

    html += `<div class="field-group-title">${esc(L('Bảng phân vị', 'Percentile table'))}</div>`;
    html += `<table class="data-table"><thead><tr>
      <th>${esc(L('Phân vị', 'Percentile'))}</th>
      <th>${esc(L('Lợi nhuận', 'Return'))}</th>
      <th>${esc(L('Sụt giảm tối đa', 'Max drawdown'))}</th></tr></thead><tbody>`;
    for (const p of ['p5', 'p25', 'p50', 'p75', 'p95']) {
      html += `<tr><td>${p}</td>
        <td class="${sign(ret[p])}">${pct(ret[p])}</td>
        <td class="neg">-${dd[p].toFixed(1)}%</td></tr>`;
    }
    html += '</tbody></table>';
    html += `<p class="table-note">${esc(L(
      `Lấy lại chính các lệnh của chiến lược, ${r.simulations.toLocaleString(I18n.locale())} lần, trên ${r.trades_resampled} lệnh. Cái thay đổi là may rủi, cái giữ nguyên là lợi thế của chiến lược. Đại lượng được lấy mẫu là phần thay đổi vốn thực tế của từng lệnh, nên cộng dồn tái tạo đúng đường vốn mà engine đã chạy.`,
      `The strategy's own trades, resampled ${r.simulations.toLocaleString(I18n.locale())} times over ${r.trades_resampled} trades. What varies is luck; what stays fixed is the edge. The quantity resampled is each trade's actual change in equity, so compounding reproduces exactly the curve the engine ran.`))}</p>`;

    elements.output.innerHTML = html;
  }

  const percentileExplain = (r) => Explain.inline({
    title: L('Kết quả thật nằm ở đâu trong phân phối',
             'Where the real result sits in the distribution'),
    what: L('Phần trăm số kịch bản mô phỏng cho kết quả kém hơn kết quả đã xảy ra.',
            'The share of simulated scenarios that came out worse than what actually happened.'),
    rows: [[L('Kết quả thật', 'Real result'), pct(r.actual_return_pct)],
           [L('Trung vị mô phỏng', 'Simulated median'), pct(r.return_pct.p50)],
           [L('Phân vị', 'Percentile'), r.actual_percentile.toFixed(0)]],
    how: L('Trên 80 nghĩa là lịch sử đã rút được một chuỗi thuận lợi từ chính các lệnh này, nên kỳ vọng hợp lý cho lần chạy tới gần trung vị hơn là gần con số backtest. Dưới 20 thì ngược lại.',
            'Above 80 means history drew a favourable sequence from these same trades, so a reasonable expectation for the next run is closer to the median than to the backtest figure. Below 20 is the reverse.'),
  });

  const probabilityExplain = (p, simulations) => Explain.inline({
    title: L('Xác suất, kèm sai số của việc mô phỏng',
             'A probability, with the error of having simulated it'),
    what: L('Một xác suất ước lượng từ số lần mô phỏng hữu hạn cũng là một ước lượng.',
            'A probability estimated from a finite number of runs is itself an estimate.'),
    rows: [[L('Ước lượng', 'Estimate'), `${p.pct.toFixed(2)}%`],
           [L('Sai số chuẩn', 'Standard error'), `${p.standard_error_pct.toFixed(2)}%`],
           [L('Khoảng tin cậy 95%', '95% interval'),
            `${p.ci95_low_pct.toFixed(2)} - ${p.ci95_high_pct.toFixed(2)}%`],
           [L('Số mô phỏng', 'Simulations'), simulations.toLocaleString(I18n.locale())]],
    how: L('Báo 3.2% từ 1 000 đường đi mà không nói nó là 3.2 ± 1.1 là mời người đọc tin vào một chữ số mà mô phỏng không đỡ nổi. Muốn hẹp khoảng lại thì tăng số mô phỏng.',
            'Reporting 3.2% off 1 000 paths without saying it is 3.2 plus or minus 1.1 invites the reader to trust a digit the simulation cannot support. Raise the simulation count to narrow it.'),
  });

  const resamplerExplain = (r) => Explain.inline({
    title: L('Vì sao chạy hai cách lấy mẫu', 'Why two resamplers run'),
    what: L('Lấy mẫu theo khối giữ các chuỗi lệnh liền nhau; lấy mẫu độc lập rút từng lệnh riêng.',
            'Block sampling keeps runs of consecutive trades; independent sampling draws each trade on its own.'),
    rows: [[L('Độ dài khối', 'Block length'), r.block_length.toFixed(0)],
           [L('Sụt giảm p95 · khối', 'Drawdown p95 · block'),
            `-${r.methods.block.max_drawdown_pct.p95.toFixed(1)}%`],
           [L('Sụt giảm p95 · độc lập', 'Drawdown p95 · independent'),
            `-${r.methods.independent.max_drawdown_pct.p95.toFixed(1)}%`],
           [L('Chênh lệch', 'Gap'), `${r.ordering_effect_pct.toFixed(1)} ${L('điểm', 'points')}`]],
    how: L('Kết quả các lệnh không độc lập với nhau: chiến lược theo xu hướng thắng thành chuỗi rồi thua thành chuỗi. Lấy mẫu độc lập tạo ra những chuỗi mà chiến lược không bao giờ sinh ra được, nên bản theo khối được lấy làm chuẩn.',
            'Trade outcomes are not independent: a trend follower wins in runs and loses in runs. Independent draws produce sequences the strategy could never generate, so the block figure is the headline.'),
    watch: L('Sai lệch của cách độc lập không có hướng cố định. Đo trên một chuỗi 10 thắng/10 thua lặp lại, nó cho sụt giảm p95 là 56.65% trong khi thực tế 24.72%; ở chuỗi khác nó lại thấp hơn. Vì thế chênh lệch giữa hai cách được báo ra thay vì bị giấu đi.',
             'The independent method\'s error has no fixed direction. On a repeating 10-win/10-loss pattern it put the p95 drawdown at 56.65% against a real 24.72%; on other sequences it lands lower. That is why the gap is reported rather than hidden.'),
  });

  // ---------- Compare ----------

  async function runCompare(entries) {
    const ctx = context();
    const result = await API.compareStrategies({
      entries,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      execution: execution(),
      period: period(),
    });
    lastResult = { kind: 'compare', data: result };
    renderCompare(result);
    return result;
  }

  function renderCompare(result) {
    const rows = [...result.results].sort(
      (a, b) => b.metrics.total_return_pct - a.metrics.total_return_pct,
    );
    const bh = result.buy_hold_return_pct;

    let html = '';
    if (!result.beat_buy_hold.length) {
      html += `<div class="callout warn">${esc(L(
        `Không chiến lược nào vượt mua-và-giữ (${pct(bh)} trên cùng khoảng thời gian). Chỉ mua rồi giữ đã tốt hơn tất cả.`,
        `No strategy beat buy-and-hold (${pct(bh)} over the same window). Simply buying and holding did better than all of them.`))}</div>`;
    }
    if (result.failures.length) {
      html += `<div class="callout bad">${esc(L(
        `${result.failures.length} chiến lược lỗi: `,
        `${result.failures.length} strategies failed: `))}${
        esc(result.failures.map((f) => f.strategy_id).join(', '))}</div>`;
    }

    html += `<table class="data-table"><thead><tr>
      <th>${esc(L('Chiến lược', 'Strategy'))}</th>
      <th>${esc(L('Lợi nhuận', 'Return'))}</th>
      <th>${esc(L('vs mua-giữ', 'vs hold'))}</th><th>Sharpe</th>
      <th>MaxDD</th><th>${esc(L('Thắng', 'Win'))}</th><th>PF</th>
      <th>${esc(L('Lệnh', 'Trades'))}</th></tr></thead><tbody>`;

    for (const [i, r] of rows.entries()) {
      const m = r.metrics;
      const vs = m.total_return_pct - bh;
      html += `<tr class="${i === 0 ? 'best' : ''}">
        <td>${esc(r.label)}</td>
        <td class="${sign(m.total_return_pct)}">${m.total_return_pct.toFixed(1)}%</td>
        <td class="${sign(vs)}">${vs >= 0 ? '+' : ''}${vs.toFixed(1)}</td>
        <td class="${sign(m.sharpe)}">${num(m.sharpe)}</td>
        <td class="neg">-${m.max_drawdown_pct.toFixed(1)}%</td>
        <td class="muted">${m.win_rate_pct.toFixed(0)}%</td>
        <td class="${m.profit_factor > 1 ? 'pos' : 'neg'}">${
          Number.isFinite(m.profit_factor) ? num(m.profit_factor) : '∞'
        }</td>
        <td class="muted">${m.num_trades}</td></tr>`;
    }
    html += `<tr class="muted"><td>${esc(L('Mua và giữ', 'Buy and hold'))}</td>
      <td class="${sign(bh)}">${bh.toFixed(1)}%</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>`;
    html += '</tbody></table>';
    html += `<p class="table-note">${esc(L(
      `Cùng ${result.bars.toLocaleString(I18n.locale())} nến, cùng phí và trượt giá, cùng khoảng thời gian — nếu khác nhau thì bảng này đo cách cài đặt chứ không đo chiến lược.`,
      `The same ${result.bars.toLocaleString(I18n.locale())} bars, the same fees and slippage, the same window — if any of those differed, this table would be measuring the settings rather than the strategies.`))}</p>`;

    elements.output.innerHTML = html;
  }


  // ---------- Statistics ----------
  //
  // Every test the backend runs arrives in the same envelope: name, H0, H1,
  // statistic, raw p, FDR-adjusted p, conclusion and assumptions. So the panel
  // renders one table for all of them rather than a bespoke row per test, and
  // each row carries an (i) that opens the full annotation. The table shows
  // both p columns side by side on purpose: the gap between them is the whole
  // point of running a family of tests at once.

  const P_FMT = (p) => (Explain ? Explain.pFormat(p) : String(p));

  /** One row of the test table, with its (i) wired to the test's own text. */
  function testRow(test) {
    if (!test) return '';
    if (test.unavailable) {
      return `<tr class="muted"><td>${esc(tp(test.name))}</td>
        <td colspan="3">${esc(tp(test.unavailable))}</td>
        <td class="muted">${esc(L('không chạy được', 'could not run'))}</td></tr>`;
    }
    if (test.p_value === null || test.p_value === undefined) return '';

    const adjusted = test.p_adjusted ?? test.p_value;
    const rejected = test.reject_adjusted ?? test.reject;
    // The conclusion sentence is long by design; the table shows the decision
    // and the (i) shows the sentence.
    const decision = rejected
      ? L('Bác bỏ H₀', 'Reject H₀')
      : L('Không bác bỏ', 'Do not reject');
    const info = Explain.inline(Explain.fromTest(test), {
      title: `${L('Giải thích', 'Explain')} ${tp(test.name)}`,
    });

    return `<tr>
      <td>${esc(tp(test.name))} ${info}</td>
      <td>${esc(Explain.fmt(test.statistic))}</td>
      <td>${esc(P_FMT(test.p_value))}</td>
      <td class="${rejected ? 'pos' : ''}">${esc(P_FMT(adjusted))}</td>
      <td class="${rejected ? 'pos' : 'muted'}">${esc(decision)}</td>
    </tr>`;
  }

  function testTable(tests, caption) {
    const rows = tests.map(testRow).filter(Boolean).join('');
    if (!rows) return '';
    return `${caption ? `<div class="field-group-title">${esc(caption)}</div>` : ''}
      <table class="data-table stat-table">
        <thead><tr>
          <th>${esc(L('Kiểm định', 'Test'))}</th>
          <th>${esc(L('Thống kê', 'Statistic'))}</th>
          <th>${esc(L('p thô', 'raw p'))}</th>
          <th>${esc(L('p hiệu chỉnh', 'adjusted p'))}</th>
          <th>${esc(L('Quyết định ở α = 0,05', 'Decision at α = 0.05'))}</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  /** A card whose label carries an (i).
   *
   * `explain` is either a glossary id or the markup `Explain.inline()` returns
   * for an entry built from live numbers. Both are common here, so both work.
   */
  function cardX(label, value, explain, cls = '', sub = '') {
    const info = !explain
      ? ''
      : explain.startsWith('<')
        ? explain
        : Explain.button(explain, { title: `${L('Giải thích', 'Explain')} ${label}` });
    return `<div class="metric">
      <div class="metric-label">${esc(label)} ${info}</div>
      <div class="metric-value ${cls}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function verdictCallout(verdict, tone) {
    if (!verdict) return '';
    let html = `<div class="callout ${tone}"><strong>${esc(tp(verdict.headline))}</strong>
      ${verdict.detail ? ` ${esc(tp(verdict.detail))}` : ''}</div>`;
    for (const note of verdict.notes || []) {
      html += `<div class="callout">${esc(tp(note))}</div>`;
    }
    return html;
  }

  function familyNote(family) {
    if (!family || !family.n_tests) return '';
    return `<p class="table-note">${esc(tp(family.note))}
      ${family.n_significant_raw !== undefined
        ? esc(L(
            `Trước hiệu chỉnh: ${family.n_significant_raw}/${family.n_tests} kiểm định có ý nghĩa; sau hiệu chỉnh: ${family.n_significant_adjusted}/${family.n_tests}.`,
            `Before adjustment: ${family.n_significant_raw} of ${family.n_tests} tests were significant; after: ${family.n_significant_adjusted} of ${family.n_tests}.`))
        : ''}</p>`;
  }

  async function runSeriesStats() {
    const ctx = context();
    const result = await API.statsSeries({
      symbol: ctx.symbol, timeframe: ctx.timeframe, limit: ctx.limit,
    });
    lastStats = { kind: 'series', data: result };
    renderSeriesStats(result);
    return result;
  }

  function renderSeriesStats(r) {
    if (r.error) { elements.stats.innerHTML = `<p class="empty">${esc(r.error)}</p>`; return; }

    const m = r.moments || {};
    const tail = r.tail || {};
    const stationary = r.stationarity || {};
    const auto = r.autocorrelation || {};
    const norm = r.normality || {};

    // The verdict is computed from the ADJUSTED p-values only, so it cannot
    // disagree with the table below it.
    const structured = r.verdict?.code === 'structured';
    let html = verdictCallout(r.verdict, structured ? 'good' : 'warn');

    html += '<div class="metrics">';
    if (m.n) {
      html += cardX(L('Độ nhọn thừa', 'Excess kurtosis'), num(m.kurtosis_excess),
        Explain.inline({
          title: L('Độ nhọn thừa', 'Excess kurtosis'),
          what: L('Đo độ dày của đuôi phân phối so với phân phối chuẩn. Chuẩn = 0.',
                  'How heavy the tails are against a normal distribution. Normal = 0.'),
          rows: [
            [L('Giá trị', 'Value'), num(m.kurtosis_excess)],
            [L('Sai số chuẩn', 'Standard error'), num(m.kurtosis_se, 3)],
            ['z', num(m.kurtosis_z)],
          ],
          how: m.kurtosis_significant
            ? L('Lệch khỏi 0 quá 1,96 sai số chuẩn, nên đây là độ nhọn thật chứ không phải nhiễu lấy mẫu.',
                'More than 1.96 standard errors from zero, so this is real kurtosis rather than sampling noise.')
            : L('Chưa lệch khỏi 0 quá 1,96 sai số chuẩn: với cỡ mẫu này, không kết luận được là đuôi dày hơn chuẩn.',
                'Not yet 1.96 standard errors from zero: at this sample size, heavier-than-normal tails cannot be concluded.'),
          watch: L(
            'Độ nhọn cao nghĩa là các cú sốc lớn xảy ra thường xuyên hơn nhiều so với giả định chuẩn. Mọi ước lượng rủi ro dựa trên độ lệch chuẩn đều thấp hơn thực tế.',
            'High kurtosis means large shocks happen far more often than a normal assumption allows. Every risk estimate built on standard deviation is understated.'),
        }),
        m.kurtosis_significant && m.kurtosis_excess > 1 ? 'neg' : '',
        `SE ${num(m.kurtosis_se, 3)} · ${m.kurtosis_significant
          ? L('có ý nghĩa', 'significant') : L('không có ý nghĩa', 'not significant')}`);

      html += cardX(L('Độ lệch', 'Skewness'), num(m.skew, 3),
        Explain.inline({
          title: L('Độ lệch', 'Skewness'),
          what: L('Đo tính bất đối xứng của phân phối lợi suất. Chuẩn = 0.',
                  'How asymmetric the return distribution is. Normal = 0.'),
          rows: [[L('Giá trị', 'Value'), num(m.skew, 3)],
                 [L('Sai số chuẩn', 'Standard error'), num(m.skew_se, 3)],
                 ['z', num(m.skew_z)]],
          how: m.skew < 0
            ? L('Âm: đuôi trái dày hơn — các phiên giảm cực đoan sâu hơn các phiên tăng cực đoan.',
                'Negative: the left tail is heavier — extreme down sessions run deeper than extreme up ones.')
            : L('Dương: đuôi phải dày hơn.', 'Positive: the right tail is heavier.'),
          assumptions: L(
            'Sai số chuẩn tính theo công thức Cramér dưới giả thuyết phân phối chuẩn. Một độ lệch nhỏ hơn 1,96 lần sai số chuẩn không phân biệt được với 0.',
            "The standard error follows Cramér's formula under a normality assumption. A skew below 1.96 standard errors is indistinguishable from zero."),
        }),
        '', `SE ${num(m.skew_se, 3)}`);
    }

    if (tail.n) {
      html += cardX('VaR 95%', `${num(tail.var_95_pct)}%`, 'p.var', 'neg',
        L(`KTC ${num(tail.var_95_ci_low_pct)}…${num(tail.var_95_ci_high_pct)}%`,
          `CI ${num(tail.var_95_ci_low_pct)}…${num(tail.var_95_ci_high_pct)}%`));
      html += cardX('CVaR 95%', `${num(tail.cvar_95_pct)}%`, 'p.cvar', 'neg',
        L(`${tail.tail_n_95} quan sát đuôi`, `${tail.tail_n_95} tail observations`));
      html += cardX('CVaR 99%', `${num(tail.cvar_99_pct)}%`,
        Explain.inline({
          title: L('CVaR 99%: và vì sao phải cẩn thận',
                   'CVaR 99%, and why to be careful with it'),
          what: L('Mức lỗ trung bình trong 1% số nến tệ nhất.',
                  'The average loss across the worst 1% of bars.'),
          rows: [[L('Giá trị', 'Value'), `${num(tail.cvar_99_pct)}%`],
                 [L('Số quan sát đuôi', 'Tail observations'), tail.tail_n_99]],
          watch: tail.tail_reliable_99
            ? L('Đủ quan sát để ước lượng tạm ổn định.',
                'Enough observations for a reasonably stable estimate.')
            : L(`Chỉ ${tail.tail_n_99} quan sát đỡ con số này. Nó hiện ra với hai chữ số thập phân như mọi con số khác, nhưng nó không đáng tin như vậy — hãy coi là chỉ dấu.`,
                `Only ${tail.tail_n_99} observations carry this figure. It prints to two decimals like every other number here and is nowhere near that trustworthy — read it as an indication.`),
        }),
        tail.tail_reliable_99 ? 'neg' : '',
        L(`${tail.tail_n_99} quan sát${tail.tail_reliable_99 ? '' : ' (quá ít)'}`,
          `${tail.tail_n_99} observations${tail.tail_reliable_99 ? '' : ' (too few)'}`));
    }

    if (r.hurst?.statistic !== undefined && r.hurst.statistic !== null) {
      html += cardX('Hurst', num(r.hurst.statistic, 3),
        Explain.inline(Explain.fromTest(r.hurst)), '',
        tp(r.hurst.reading));
    }
    if (r.variance_ratio?.per_period) {
      const q2 = r.variance_ratio.per_period[0];
      html += cardX(L('Tỷ số phương sai (q=2)', 'Variance ratio (q=2)'),
        num(q2?.variance_ratio, 3),
        Explain.inline(Explain.fromTest(r.variance_ratio)), '', tp(q2?.reading));
    }
    html += '</div>';

    // The full family, in one table, with both p columns.
    html += testTable([
      auto.ljung_box, auto.arch_lm,
      r.variance_ratio, r.hurst,
      stationary.adf_price, stationary.adf_return, stationary.kpss_return,
      norm.jarque_bera, norm.dagostino,
    ], L('Toàn bộ họ kiểm định', 'The whole family of tests'));
    html += familyNote(r.multiple_testing);

    // Variance ratio detail: one row per horizon, with both z statistics so
    // the difference between them is visible rather than asserted.
    const vr = r.variance_ratio?.per_period;
    if (vr?.length) {
      html += `<div class="field-group-title">${esc(L(
        'Tỷ số phương sai theo kỳ hạn', 'Variance ratio by horizon'))}</div>
        <table class="data-table"><thead><tr>
          <th>q</th><th>VR(q)</th>
          <th>${esc(L('z đồng nhất', 'z homoskedastic'))}</th>
          <th>${esc(L('z bền', 'z robust'))}</th>
          <th>${esc(L('Đọc là', 'Reads as'))}</th>
        </tr></thead><tbody>` +
        vr.map((p) => `<tr>
          <td>${p.period}</td>
          <td>${num(p.variance_ratio, 3)}</td>
          <td class="muted">${num(p.z_homoskedastic)}</td>
          <td class="${Math.abs(p.z_heteroskedastic ?? 0) > 1.96 ? 'pos' : ''}">${num(p.z_heteroskedastic)}</td>
          <td>${esc(tp(p.reading))}</td></tr>`).join('') +
        `</tbody></table>
        <p class="table-note">${esc(L(
          'Cột z bền là cột để đọc: nó không giả định phương sai cố định theo thời gian, còn cột z đồng nhất thì có, và kiểm định ARCH ở bảng trên hầu như luôn bác bỏ giả định đó. Kết luận chung lấy từ thống kê Chow–Denning trên toàn bộ tập kỳ hạn, không phải từ kỳ hạn có p nhỏ nhất.',
          'The robust z is the column to read: it does not assume variance is constant over time, the homoskedastic one does, and the ARCH test above almost always rejects that assumption. The overall verdict comes from the Chow–Denning statistic across the whole set of horizons, not from whichever horizon had the smallest p.'))}</p>`;
    }

    html += `<p class="table-note">${esc(L(
      `Trên ${(r.bars || 0).toLocaleString(I18n.locale())} nến ${r.symbol || ''} ${r.timeframe || ''}, lợi suất log. Mức ý nghĩa α = 0,05, hiệu chỉnh đa kiểm định Benjamini–Hochberg.`,
      `Over ${(r.bars || 0).toLocaleString(I18n.locale())} ${r.symbol || ''} ${r.timeframe || ''} bars, on log returns. Significance α = 0.05, with a Benjamini–Hochberg correction for multiple testing.`))}</p>`;

    elements.stats.innerHTML = html;
  }

  async function runStrategyStats(params) {
    const ctx = context();
    const result = await API.statsStrategy({
      strategyId: elements.strategySelect.value,
      symbol: ctx.symbol, timeframe: ctx.timeframe, limit: ctx.limit,
      params, execution: execution(),
      // If the parameters came from a sweep, that sweep's size is what the
      // deflated Sharpe ratio has to discount. Typed-in parameters mean 1.
      nTrials: Strategy.lastTrials,
    });
    lastStats = { kind: 'strategy', data: result };
    renderStrategyStats(result);
    return result;
  }

  function renderStrategyStats(r) {
    if (r.error) { elements.stats.innerHTML = `<p class="empty">${esc(r.error)}</p>`; return; }

    const inf = r.inference || {};
    const sharpe = r.sharpe;
    const power = inf.power || {};
    const boot = inf.bootstrap_mean;

    if (inf.error) {
      elements.stats.innerHTML = `<div class="callout warn">${esc(inf.error)}</div>`;
      return;
    }

    const good = r.verdict?.code === 'robust';
    let html = verdictCallout(r.verdict, good ? 'good' : 'warn');

    html += '<div class="metrics">';
    html += cardX(L('Lợi suất TB/lệnh', 'Mean return per trade'),
      `${inf.mean_return_pct >= 0 ? '+' : ''}${num(inf.mean_return_pct, 3)}%`,
      'm.expectancy', sign(inf.mean_return_pct),
      L(`${inf.n_trades} lệnh`, `${inf.n_trades} trades`));

    const perm = inf.sign_permutation;
    if (perm) {
      html += cardX(L('p hoán vị (phi tham số)', 'Permutation p (non-parametric)'),
        P_FMT(perm.p_adjusted ?? perm.p_value),
        Explain.inline(Explain.fromTest(perm)),
        (perm.reject_adjusted ?? perm.reject) ? 'pos' : 'neg',
        L('đã hiệu chỉnh đa kiểm định', 'corrected for multiple testing'));
    }
    if (boot) {
      html += cardX('KTC 95% bootstrap',
        `${num(boot.ci95_low_pct)}…${num(boot.ci95_high_pct)}%`,
        Explain.inline({
          title: boot.name,
          what: L('Khoảng tin cậy cho lợi suất trung bình mỗi lệnh, không giả định phân phối.',
                  'A confidence interval for the mean return per trade, with no distributional assumption.'),
          rows: [
            [L('Trung bình', 'Mean'), `${num(boot.mean_pct, 3)}%`],
            [L('Cận dưới', 'Lower bound'), `${num(boot.ci95_low_pct, 3)}%`],
            [L('Cận trên', 'Upper bound'), `${num(boot.ci95_high_pct, 3)}%`],
            [L('Số lần lấy mẫu lại', 'Resamples'), boot.n_resamples],
          ],
          how: tp(boot.note),
          assumptions: L(
            'BCa hiệu chỉnh cả độ chệch lẫn độ lệch của phân phối bootstrap. Vẫn giả định các lệnh độc lập với nhau.',
            'BCa corrects for both the bias and the skew of the bootstrap distribution. It still assumes the trades are independent of each other.'),
        }),
        boot.excludes_zero ? 'pos' : 'neg',
        boot.excludes_zero ? L('không chứa 0', 'excludes zero')
                           : L('vẫn chứa 0', 'still contains zero'));
    }
    if (power.power !== undefined) {
      html += cardX(L('Lực kiểm định', 'Statistical power'),
        `${(power.power * 100).toFixed(0)}%`,
        Explain.inline({
          title: power.name,
          what: L('Xác suất phát hiện được lợi thế, nếu lợi thế thật đúng bằng mức quan sát được.',
                  'The probability of detecting an edge, if the true edge is exactly the observed one.'),
          rows: [
            [L('Cỡ ảnh hưởng (d)', "Effect size (Cohen's d)"),
             num(power.effect_size_cohens_d, 3)],
            [L('Số lệnh hiện có', 'Trades available'), power.n],
            [L('Cần cho lực 80%', 'Needed for 80% power'),
             power.n_required_for_80pct ?? '—'],
          ],
          how: tp(power.reading),
          assumptions: tp(power.assumptions),
        }),
        power.adequate ? 'pos' : 'neg',
        power.n_required_for_80pct
          ? L(`cần ${power.n_required_for_80pct} lệnh cho 80%`,
              `${power.n_required_for_80pct} trades needed for 80%`)
          : '');
    }
    if (sharpe && !sharpe.error) {
      html += cardX('PSR', `${(sharpe.psr * 100).toFixed(1)}%`,
        Explain.inline({
          title: L('PSR: Sharpe theo xác suất', 'PSR: probabilistic Sharpe ratio'),
          what: L('Xác suất Sharpe thật lớn hơn 0, có tính tới độ lệch và độ nhọn của lợi suất.',
                  'The probability that the true Sharpe is above zero, accounting for the skew and kurtosis of the returns.'),
          rows: [
            [L('Sharpe (năm)', 'Sharpe (annualised)'), num(sharpe.sharpe_annualised)],
            [L('Độ lệch', 'Skewness'), num(sharpe.skew, 3)],
            [L('Độ nhọn', 'Kurtosis'), num(sharpe.kurtosis)],
            [L('Số quan sát', 'Observations'), sharpe.n_observations],
            ['MinTRL', sharpe.min_track_record_length ?? '—'],
          ],
          how: tp(sharpe.conclusion),
          assumptions: tp(sharpe.assumptions),
        }),
        sharpe.psr_significant ? 'pos' : 'neg',
        `Sharpe ${num(sharpe.sharpe_annualised)}`);

      html += cardX(L('DSR (khử phồng)', 'DSR (deflated)'),
        `${(sharpe.deflated_sharpe_ratio * 100).toFixed(1)}%`,
        Explain.inline({
          title: L('DSR: Sharpe khử phồng', 'DSR: deflated Sharpe ratio'),
          what: L(
            `Như PSR, nhưng so với ngưỡng mà ${sharpe.n_trials} lần thử tham số tự nó đã tạo ra được.`,
            `Like PSR, but against the threshold that ${sharpe.n_trials} parameter trials produce on their own.`),
          rows: [
            [L('Số lần thử', 'Trials'), sharpe.n_trials],
            [L('Ngưỡng Sharpe kỳ vọng', 'Expected Sharpe threshold'),
             num(sharpe.deflation_threshold_sharpe, 4)],
            ['DSR', `${(sharpe.deflated_sharpe_ratio * 100).toFixed(1)}%`],
          ],
          how: sharpe.n_trials > 1
            ? tp(sharpe.conclusion)
            : L(
              'Chưa chạy tối ưu nên số lần thử tính là 1, và DSR bằng PSR. Sau khi quét tham số, hãy chạy lại kiểm định này để thấy ngưỡng thật.',
              'No optimisation has run, so the trial count is 1 and DSR equals PSR. Sweep the parameters, then run this test again to see the real threshold.'),
          watch: L(
            'Đây là con số quan trọng nhất khi tham số đến từ một lần quét. Chọn tổ hợp tốt nhất trong 2 000 tổ hợp là chọn cực đại của 2 000 biến ngẫu nhiên: Sharpe của nó cao hơn Sharpe thật kể cả khi không tổ hợp nào có lợi thế.',
            'This is the number that matters most when the parameters came from a sweep. Picking the best of 2,000 combinations is picking the maximum of 2,000 random variables: its Sharpe is higher than the true one even when no combination has any edge at all.'),
          assumptions: tp(sharpe.assumptions),
        }),
        sharpe.dsr_significant ? 'pos' : 'neg',
        L(`${sharpe.n_trials} lần thử tham số`,
          `${sharpe.n_trials} parameter trials`));
    }
    html += '</div>';

    html += testTable([inf.t_test, inf.wilcoxon, inf.sign_permutation],
      L('Kiểm định lợi thế: ba cách hỏi cùng một câu',
        'Testing the edge: three ways of asking the same question'));
    html += familyNote(r.multiple_testing);

    html += `<p class="table-note">${esc(L(
      'Ba kiểm định trên đo cùng một thứ với những giả định khác nhau. Nếu chúng cho kết luận khác nhau thì bản thân điều đó là thông tin: kết quả phụ thuộc vào giả định chứ không phải vào dữ liệu, và kiểm định hoán vị — vốn giả định ít nhất — là cái đáng tin nhất.',
      'The three tests above measure the same thing under different assumptions. If they disagree, that disagreement is itself information: the result depends on the assumptions rather than on the data, and the permutation test, which assumes least, is the one to trust.'))}</p>`;

    if (sharpe?.min_track_record_length) {
      html += `<p class="table-note">${esc(L(
        `Độ dài lịch sử tối thiểu để Sharpe này đạt mức tin cậy 95% là ${sharpe.min_track_record_length.toLocaleString(I18n.locale())} quan sát; hiện có ${sharpe.n_observations.toLocaleString(I18n.locale())}${sharpe.sufficient_history ? ' — đủ.' : ' — chưa đủ.'}`,
        `The minimum track record for this Sharpe to reach 95% confidence is ${sharpe.min_track_record_length.toLocaleString(I18n.locale())} observations; there are ${sharpe.n_observations.toLocaleString(I18n.locale())}${sharpe.sufficient_history ? ' — enough.' : ' — not yet enough.'}`))}</p>`;
    }

    elements.stats.innerHTML = html;
  }

  // ---------- Export ----------

  function download(filename, content, type = 'text/csv;charset=utf-8') {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    // Revoke on the next tick: doing it immediately can cancel the download.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function tradesToCsv(trades, label) {
    const header = [
      'so_thu_tu', 'chien_luoc', 'chieu', 'gio_vao_VN', 'gio_ra_VN',
      'gia_vao', 'gia_ra', 'khoi_luong', 'lai_lo', 'phan_tram', 'so_nen', 'ly_do_thoat',
    ];
    const lines = [header.join(',')];

    trades.forEach((t, i) => {
      lines.push([
        i + 1,
        `"${(label || '').replace(/"/g, '""')}"`,
        t.side,
        vnTime(t.entry_time),
        vnTime(t.exit_time),
        t.entry_price,
        t.exit_price,
        t.quantity,
        t.pnl.toFixed(2),
        (t.return_pct ?? 0).toFixed(2),
        t.bars_held ?? '',
        t.exit_reason,
      ].join(','));
    });
    // A BOM so Excel opens the Vietnamese headers as UTF-8 rather than mojibake.
    return '﻿' + lines.join('\n');
  }

  function exportTrades(fallback) {
    const stamp = new Date().toISOString().slice(0, 10);
    const source = lastResult?.data;

    let trades = null;
    let label = 'ket-qua';

    if (lastResult?.kind === 'compare') {
      // One file covering every strategy, with a column saying which is which.
      const all = source.results.flatMap((r) =>
        (r.trades || []).map((t) => ({ ...t, __label: r.label })),
      );
      if (all.length) {
        const header = tradesToCsv([], '').split('\n')[0];
        const body = source.results
          .flatMap((r) => tradesToCsv(r.trades || [], r.label).split('\n').slice(1))
          .filter(Boolean);
        download(`lenh-so-sanh-${stamp}.csv`, '﻿' + [header, ...body].join('\n'));
        onToast(L(`Đã tải ${all.length} lệnh của ${source.results.length} chiến lược`,
                `Exported ${all.length} trades from ${source.results.length} strategies`));
        return;
      }
    } else if (lastResult?.kind === 'walk-forward') {
      trades = source.trades;
      label = L(`${source.strategy_id} (ngoài mẫu)`,
                `${source.strategy_id} (out of sample)`);
    } else if (fallback?.trades?.length) {
      trades = fallback.trades;
      label = fallback.name || fallback.id || 'backtest';
    }

    if (!trades?.length) {
      onToast(L('Chưa có lệnh nào để xuất: hãy chạy backtest trước.',
                'No trades to export yet: run a backtest first.'), true);
      return;
    }
    download(`lenh-${stamp}.csv`, tradesToCsv(trades, label));
    onToast(L(`Đã tải ${trades.length} lệnh ra CSV`,
              `Exported ${trades.length} trades to CSV`));
  }

  function exportChart() {
    const canvas = ChartManager.screenshot();
    if (!canvas) {
      onToast(L('Không chụp được biểu đồ.', 'Could not capture the chart.'), true);
      return;
    }
    canvas.toBlob((blob) => {
      if (!blob) {
        onToast(L('Không chụp được biểu đồ.', 'Could not capture the chart.'), true);
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bieu-do-${new Date().toISOString().slice(0, 10)}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      onToast(L('Đã tải biểu đồ ra PNG', 'Chart saved as PNG'));
    }, 'image/png');
  }

  /* Redraw the statistics panel in the current language.
   *
   * Only the statistics output is re-rendered here, because it is the only
   * thing this module keeps enough state to rebuild: `lastStats` holds the
   * payload, and the payload carries both languages. Walk-forward and
   * comparison results are re-rendered by running them again: they are not
   * cached, and caching them purely to survive a language switch would be
   * paying for the wrong thing. */
  let lastStats = null;

  function rerender() {
    if (!lastStats) return;
    if (lastStats.kind === 'series') renderSeriesStats(lastStats.data);
    else renderStrategyStats(lastStats.data);
  }

  function init(config) {
    elements = config.elements;
    context = config.context;
    execution = config.execution;
    period = config.period || (() => ({}));
    catalog = config.catalog;
    onToast = config.onToast;

    Explain.define('wf.purge', () => ({
      title: L('Nến cách ly', 'Purged bars'),
      what: L(
        'Số nến bị vứt bỏ giữa cửa sổ huấn luyện và cửa sổ kiểm tra.',
        'Bars thrown away between the training window and the test window.'),
      how: L(
        'Nến cuối của cửa sổ huấn luyện và nến đầu của cửa sổ kiểm tra nằm sát ' +
        'nhau. Chỉ báo nào có cửa sổ nhìn lại — trung bình trượt 200 chẳng hạn — ' +
        'thì những nến đầu tiên ngoài mẫu vẫn còn mang thông tin của giai đoạn ' +
        'đã dùng để chọn tham số. Đặt số nến cách ly ít nhất bằng cửa sổ nhìn ' +
        'lại dài nhất của chiến lược thì phần chồng lấn đó biến mất.',
        'The last training bar and the first test bar sit next to each other. ' +
        'Any indicator with a lookback — a 200-bar moving average, say — leaves ' +
        'the first out-of-sample bars still carrying information from the ' +
        'period the parameters were chosen on. Setting purge to at least the ' +
        "strategy's longest lookback removes that overlap."),
      watch: L(
        'Mặc định là 0, tức là không cách ly. Với chiến lược có cửa sổ nhìn lại ' +
        'dài, kết quả ngoài mẫu ở mức 0 sẽ đẹp hơn sự thật.',
        'The default is 0, meaning no purge. For a strategy with a long ' +
        'lookback, out-of-sample results at 0 look better than the truth.'),
      source: 'López de Prado, Advances in Financial Machine Learning (2018), ch. 7.',
    }));
    Explain.define('wf.foldMode', () => ({
      title: L('Kiểu cửa sổ', 'Window type'),
      what: L(
        'Cửa sổ huấn luyện trượt theo thời gian, hay neo ở nến đầu tiên và dài dần ra.',
        'Whether the training window slides forward, or stays anchored at bar ' +
        'zero and grows.'),
      how: L(
        'Trượt: mỗi fold huấn luyện trên đúng số nến bạn đặt, cửa sổ dịch về ' +
        'phía trước. Neo gốc: fold nào cũng bắt đầu từ nến đầu tiên, nên fold ' +
        'sau có nhiều dữ liệu hơn fold trước — giống cách bạn thật sự tái tối ' +
        'ưu một chiến lược đang chạy.',
        'Rolling: every fold trains on exactly the number of bars you set, and ' +
        'the window moves forward. Anchored: every fold starts at bar zero, so ' +
        'later folds have more data than earlier ones — which is how you would ' +
        'actually re-optimise a strategy already running.'),
      watch: L(
        'Ở kiểu neo gốc, các fold không còn cùng độ dài huấn luyện, nên cột ' +
        '"trong mẫu" chỉ so được với nhau sau khi đã quy về cùng độ dài cửa sổ ' +
        'kiểm tra. Bảng dưới hiển thị cả số thô lẫn số đã quy đổi.',
        'Under anchored mode the folds no longer share a training length, so ' +
        'the in-sample column is only comparable after being compounded to the ' +
        'test window. The table below shows both the raw and the normalised ' +
        'figure.'),
    }));
  }

  return {
    init, runWalkForward, runMonteCarlo, runCompare,
    runSeriesStats, runStrategyStats,
    exportTrades, exportChart,
    rerender,
    get last() { return lastResult; },
  };
})();
