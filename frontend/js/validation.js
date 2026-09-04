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
      execution: execution(),
    });
    lastResult = { kind: 'walk-forward', data: result };
    renderWalkForward(result);
    return result;
  }

  function renderWalkForward(result) {
    const s = result.summary;
    let html = '';

    // With only a fold or two, the averages are one or two numbers wearing a
    // statistic's clothing. Say so before any verdict is drawn from them.
    const thin = s.total_folds < 3;
    if (thin) {
      const need = result.settings.train_bars + result.settings.test_bars * 3;
      html += `<div class="callout warn"><strong>Chỉ ${s.total_folds} vòng — chưa kết luận được.</strong>
        Cần ít nhất 3–5 vòng thì trung bình mới có nghĩa. Tăng số nến lên
        khoảng ${need.toLocaleString('vi-VN')}, hoặc giảm cửa sổ huấn luyện/kiểm tra.</div>`;
    }

    if (s.overfit_warning && !thin) {
      html += `<div class="callout bad"><strong>Chiến lược không sống sót ngoài mẫu.</strong>
        Trong mẫu trung bình ${pct(s.is_mean_return_pct)}/vòng, nhưng ngoài mẫu
        ${pct(s.oos_mean_return_pct)}/vòng. Tham số đang khớp với nhiễu của quá khứ,
        không phải với thị trường.</div>`;
    } else if (s.degradation_pct > 5 && !thin) {
      html += `<div class="callout warn">Ngoài mẫu kém trong mẫu
        <strong>${s.degradation_pct.toFixed(1)} điểm %</strong>. Chênh lệch này chính là
        cái giá của việc chọn tham số bằng hậu nghiệm.</div>`;
    } else if (!thin) {
      html += `<div class="callout good">Ngoài mẫu bám sát trong mẫu (chênh
        ${s.degradation_pct.toFixed(1)} điểm %). Đây là dấu hiệu tốt.</div>`;
    }

    html += '<div class="metrics">';
    html += card('Ngoài mẫu · tổng', pct(s.oos_total_return_pct), sign(s.oos_total_return_pct),
      `${money(s.oos_final_equity)} cuối kỳ`);
    html += card('Ngoài mẫu · TB/vòng', pct(s.oos_mean_return_pct), sign(s.oos_mean_return_pct),
      `trung vị ${pct(s.oos_median_return_pct)}`);
    html += card('Trong mẫu · TB/vòng', pct(s.is_mean_return_pct), sign(s.is_mean_return_pct));
    html += card('Suy giảm', `${s.degradation_pct >= 0 ? '−' : '+'}${Math.abs(s.degradation_pct).toFixed(1)} đ%`,
      s.degradation_pct > 0 ? 'neg' : 'pos', 'trong mẫu → ngoài mẫu');
    html += card('Sụt giảm tối đa', `-${s.oos_max_drawdown_pct.toFixed(1)}%`, 'neg', 'trên đường vốn ngoài mẫu');
    html += card('Vòng có lãi', `${s.profitable_folds}/${s.total_folds}`,
      s.consistency_pct >= 50 ? 'pos' : 'neg', `${s.consistency_pct.toFixed(0)}% số vòng`);
    html += '</div>';

    const names = Object.keys(result.folds[0]?.params || {});
    html += '<table class="data-table"><thead><tr><th>Vòng</th>';
    for (const n of names) html += `<th>${esc(n)}</th>`;
    html += '<th>Trong mẫu</th><th>Ngoài mẫu</th><th>MaxDD</th><th>Lệnh</th><th>Từ</th></tr></thead><tbody>';
    for (const f of result.folds) {
      const oos = f.out_of_sample;
      html += `<tr><td>${f.fold}</td>`;
      for (const n of names) html += `<td>${esc(f.params[n])}</td>`;
      html += `<td class="${sign(f.in_sample.return_pct)}">${f.in_sample.return_pct.toFixed(1)}%</td>`;
      html += `<td class="${sign(oos.return_pct)}">${oos.return_pct.toFixed(1)}%</td>`;
      html += `<td class="neg">-${oos.max_drawdown_pct.toFixed(1)}%</td>`;
      html += `<td class="muted">${oos.num_trades}</td>`;
      html += `<td class="muted">${vnTime(f.test_from)}</td></tr>`;
    }
    html += '</tbody></table>';
    html += `<p class="table-note">Mỗi vòng tối ưu trên ${result.settings.train_bars} nến rồi
      áp nguyên tham số đó lên ${result.settings.test_bars} nến kế tiếp — chưa từng thấy trước đó.
      Chỉ cột "Ngoài mẫu" là ước lượng trung thực.</p>`;

    elements.output.innerHTML = html;
  }

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
    });
    lastResult = { kind: 'monte-carlo', data: result };
    renderMonteCarlo(result);
    return result;
  }

  function renderMonteCarlo(r) {
    const ret = r.return_pct;
    const dd = r.max_drawdown_pct;
    let html = '';

    if (r.probability_of_loss_pct > 45) {
      html += `<div class="callout warn"><strong>Gần như tung đồng xu.</strong>
        ${r.probability_of_loss_pct.toFixed(0)}% số kịch bản kết thúc thua lỗ. Kết quả đơn lẻ
        ${pct(r.actual_return_pct)} không nói lên nhiều điều.</div>`;
    }
    if (r.probability_of_ruin_pct > 1) {
      html += `<div class="callout bad"><strong>${r.probability_of_ruin_pct.toFixed(1)}% kịch bản
        mất trên 90% vốn.</strong> Hạ đòn bẩy hoặc giảm % vốn mỗi lệnh.</div>`;
    }

    html += '<div class="metrics">';
    html += card('Kết quả thực tế', pct(r.actual_return_pct), sign(r.actual_return_pct),
      `${r.trades_resampled} lệnh, ${r.simulations.toLocaleString('vi-VN')} mô phỏng`);
    html += card('Trung vị (p50)', pct(ret.p50), sign(ret.p50));
    html += card('Kém (p5)', pct(ret.p5), 'neg', '1 trong 20 tệ hơn mức này');
    html += card('Tốt (p95)', pct(ret.p95), 'pos', '1 trong 20 tốt hơn mức này');
    html += card('Xác suất lỗ', `${r.probability_of_loss_pct.toFixed(1)}%`,
      r.probability_of_loss_pct > 50 ? 'neg' : '');
    html += card('Sụt giảm p95', `-${dd.p95.toFixed(1)}%`, 'neg',
      `thực tế -${r.actual_max_drawdown_pct.toFixed(1)}%`);
    html += '</div>';

    html += '<table class="data-table"><thead><tr><th>Phân vị</th><th>Lợi nhuận</th><th>Sụt giảm tối đa</th></tr></thead><tbody>';
    for (const p of ['p5', 'p25', 'p50', 'p75', 'p95']) {
      html += `<tr><td>${p}</td>
        <td class="${sign(ret[p])}">${pct(ret[p])}</td>
        <td class="neg">-${dd[p].toFixed(1)}%</td></tr>`;
    }
    html += '</tbody></table>';
    html += `<p class="table-note">Lấy lại chính các lệnh của chiến lược, xáo thứ tự
      ${r.simulations.toLocaleString('vi-VN')} lần. Cái thay đổi là may rủi, cái giữ nguyên là
      lợi thế của chiến lược — nên dải này cho biết kết quả thật nằm ở đâu trong vùng hợp lý.</p>`;

    elements.output.innerHTML = html;
  }

  // ---------- Compare ----------

  async function runCompare(entries) {
    const ctx = context();
    const result = await API.compareStrategies({
      entries,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      execution: execution(),
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
      html += `<div class="callout warn"><strong>Không chiến lược nào vượt mua-và-giữ</strong>
        (${pct(bh)} trên cùng khoảng thời gian). Chỉ mua rồi giữ đã tốt hơn tất cả.</div>`;
    }
    if (result.failures.length) {
      html += `<div class="callout bad">${result.failures.length} chiến lược lỗi:
        ${esc(result.failures.map((f) => f.strategy_id).join(', '))}</div>`;
    }

    html += `<table class="data-table"><thead><tr>
      <th>Chiến lược</th><th>Lợi nhuận</th><th>vs mua-giữ</th><th>Sharpe</th>
      <th>MaxDD</th><th>Thắng</th><th>PF</th><th>Lệnh</th></tr></thead><tbody>`;

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
    html += `<tr class="muted"><td>Mua và giữ</td>
      <td class="${sign(bh)}">${bh.toFixed(1)}%</td>
      <td>—</td><td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>`;
    html += '</tbody></table>';
    html += `<p class="table-note">Cùng ${result.bars.toLocaleString('vi-VN')} nến,
      cùng phí và trượt giá, cùng khoảng thời gian — nếu khác nhau thì bảng này đo
      cách cài đặt chứ không đo chiến lược.</p>`;

    elements.output.innerHTML = html;
  }


  // ---------- Statistics ----------
  //
  // Every test the backend runs arrives in the same envelope: name, H0, H1,
  // statistic, raw p, FDR-adjusted p, conclusion and assumptions. So the panel
  // renders one table for all of them rather than a bespoke row per test, and
  // each row carries an (i) that opens the full annotation. The table shows
  // both p columns side by side on purpose — the gap between them is the whole
  // point of running a family of tests at once.

  const P_FMT = (p) => (Explain ? Explain.pFormat(p) : String(p));

  /** One row of the test table, with its (i) wired to the test's own text. */
  function testRow(test) {
    if (!test) return '';
    if (test.unavailable) {
      return `<tr class="muted"><td>${esc(test.name)}</td>
        <td colspan="3">${esc(test.unavailable)}</td>
        <td class="muted">không chạy được</td></tr>`;
    }
    if (test.p_value === null || test.p_value === undefined) return '';

    const adjusted = test.p_adjusted ?? test.p_value;
    const rejected = test.reject_adjusted ?? test.reject;
    // The conclusion sentence is long by design; the table shows the decision
    // and the (i) shows the sentence.
    const decision = rejected ? 'Bác bỏ H₀' : 'Không bác bỏ';
    const info = Explain.inline(Explain.fromTest(test), { title: `Giải thích ${test.name}` });

    return `<tr>
      <td>${esc(test.name)} ${info}</td>
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
          <th>Kiểm định</th><th>Thống kê</th><th>p thô</th>
          <th>p hiệu chỉnh</th><th>Quyết định ở α = 0,05</th>
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
        : Explain.button(explain, { title: `Giải thích ${label}` });
    return `<div class="metric">
      <div class="metric-label">${esc(label)} ${info}</div>
      <div class="metric-value ${cls}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function verdictCallout(verdict, tone) {
    if (!verdict) return '';
    let html = `<div class="callout ${tone}"><strong>${esc(verdict.headline)}</strong>
      ${verdict.detail ? ` ${esc(verdict.detail)}` : ''}</div>`;
    for (const note of verdict.notes || []) {
      html += `<div class="callout">${esc(note)}</div>`;
    }
    return html;
  }

  function familyNote(family) {
    if (!family || !family.n_tests) return '';
    return `<p class="table-note">${esc(family.note || '')}
      ${family.n_significant_raw !== undefined
        ? `Trước hiệu chỉnh: ${family.n_significant_raw}/${family.n_tests} kiểm định có ý nghĩa;
           sau hiệu chỉnh: ${family.n_significant_adjusted}/${family.n_tests}.`
        : ''}</p>`;
  }

  async function runSeriesStats() {
    const ctx = context();
    const result = await API.statsSeries({
      symbol: ctx.symbol, timeframe: ctx.timeframe, limit: ctx.limit,
    });
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
    const structured = r.verdict?.headline?.startsWith('Có cấu trúc');
    let html = verdictCallout(r.verdict, structured ? 'good' : 'warn');

    html += '<div class="metrics">';
    if (m.n) {
      html += cardX('Độ nhọn thừa', num(m.kurtosis_excess),
        Explain.inline({
          title: 'Độ nhọn thừa',
          what: 'Đo độ dày của đuôi phân phối so với phân phối chuẩn. Chuẩn = 0.',
          rows: [
            ['Giá trị', num(m.kurtosis_excess)],
            ['Sai số chuẩn', num(m.kurtosis_se, 3)],
            ['z', num(m.kurtosis_z)],
          ],
          how: m.kurtosis_significant
            ? 'Lệch khỏi 0 quá 1,96 sai số chuẩn, nên đây là độ nhọn thật chứ không phải nhiễu lấy mẫu.'
            : 'Chưa lệch khỏi 0 quá 1,96 sai số chuẩn — với cỡ mẫu này, không kết luận được là đuôi dày hơn chuẩn.',
          watch: 'Độ nhọn cao nghĩa là các cú sốc lớn xảy ra thường xuyên hơn nhiều so với giả định chuẩn. Mọi ước lượng rủi ro dựa trên độ lệch chuẩn đều thấp hơn thực tế.',
        }),
        m.kurtosis_significant && m.kurtosis_excess > 1 ? 'neg' : '',
        `SE ${num(m.kurtosis_se, 3)} · ${m.kurtosis_significant ? 'có ý nghĩa' : 'không có ý nghĩa'}`);

      html += cardX('Độ lệch', num(m.skew, 3),
        Explain.inline({
          title: 'Độ lệch',
          what: 'Đo tính bất đối xứng của phân phối lợi suất. Chuẩn = 0.',
          rows: [['Giá trị', num(m.skew, 3)], ['Sai số chuẩn', num(m.skew_se, 3)], ['z', num(m.skew_z)]],
          how: m.skew < 0
            ? 'Âm: đuôi trái dày hơn — các phiên giảm cực đoan sâu hơn các phiên tăng cực đoan.'
            : 'Dương: đuôi phải dày hơn.',
          assumptions: 'Sai số chuẩn tính theo công thức Cramér dưới giả thuyết phân phối chuẩn. Một độ lệch nhỏ hơn 1,96 lần sai số chuẩn không phân biệt được với 0.',
        }),
        '', `SE ${num(m.skew_se, 3)}`);
    }

    if (tail.n) {
      html += cardX('VaR 95%', `${num(tail.var_95_pct)}%`, 'p.var', 'neg',
        `KTC ${num(tail.var_95_ci_low_pct)}…${num(tail.var_95_ci_high_pct)}%`);
      html += cardX('CVaR 95%', `${num(tail.cvar_95_pct)}%`, 'p.cvar', 'neg',
        `${tail.tail_n_95} quan sát đuôi`);
      html += cardX('CVaR 99%', `${num(tail.cvar_99_pct)}%`,
        Explain.inline({
          title: 'CVaR 99% — và vì sao phải cẩn thận',
          what: 'Mức lỗ trung bình trong 1% số nến tệ nhất.',
          rows: [['Giá trị', `${num(tail.cvar_99_pct)}%`], ['Số quan sát đuôi', tail.tail_n_99]],
          watch: tail.tail_reliable_99
            ? 'Đủ quan sát để ước lượng tạm ổn định.'
            : `Chỉ ${tail.tail_n_99} quan sát đỡ con số này. Nó hiện ra với hai chữ số thập phân như mọi con số khác, nhưng nó không đáng tin như vậy — hãy coi là chỉ dấu.`,
        }),
        tail.tail_reliable_99 ? 'neg' : '',
        `${tail.tail_n_99} quan sát${tail.tail_reliable_99 ? '' : ' — quá ít'}`);
    }

    if (r.hurst?.statistic !== undefined && r.hurst.statistic !== null) {
      html += cardX('Hurst', num(r.hurst.statistic, 3),
        Explain.inline(Explain.fromTest(r.hurst)), '',
        r.hurst.reading || '');
    }
    if (r.variance_ratio?.per_period) {
      const q2 = r.variance_ratio.per_period[0];
      html += cardX('Tỷ số phương sai (q=2)', num(q2?.variance_ratio, 3),
        Explain.inline(Explain.fromTest(r.variance_ratio)), '', q2?.reading || '');
    }
    html += '</div>';

    // The full family, in one table, with both p columns.
    html += testTable([
      auto.ljung_box, auto.arch_lm,
      r.variance_ratio, r.hurst,
      stationary.adf_price, stationary.adf_return, stationary.kpss_return,
      norm.jarque_bera, norm.dagostino,
    ], 'Toàn bộ họ kiểm định');
    html += familyNote(r.multiple_testing);

    // Variance ratio detail: one row per horizon, with both z statistics so
    // the difference between them is visible rather than asserted.
    const vr = r.variance_ratio?.per_period;
    if (vr?.length) {
      html += `<div class="field-group-title">Tỷ số phương sai theo kỳ hạn</div>
        <table class="data-table"><thead><tr>
          <th>q</th><th>VR(q)</th><th>z đồng nhất</th><th>z bền</th><th>Đọc là</th>
        </tr></thead><tbody>` +
        vr.map((p) => `<tr>
          <td>${p.period}</td>
          <td>${num(p.variance_ratio, 3)}</td>
          <td class="muted">${num(p.z_homoskedastic)}</td>
          <td class="${Math.abs(p.z_heteroskedastic ?? 0) > 1.96 ? 'pos' : ''}">${num(p.z_heteroskedastic)}</td>
          <td>${esc(p.reading)}</td></tr>`).join('') +
        `</tbody></table>
        <p class="table-note">Cột <strong>z bền</strong> là cột để đọc: nó không giả định
        phương sai cố định theo thời gian, còn cột <strong>z đồng nhất</strong> thì có — và
        kiểm định ARCH ở bảng trên hầu như luôn bác bỏ giả định đó. Kết luận chung lấy từ
        thống kê Chow–Denning trên toàn bộ tập kỳ hạn, không phải từ kỳ hạn có p nhỏ nhất.</p>`;
    }

    html += `<p class="table-note">Trên ${(r.bars || 0).toLocaleString('vi-VN')} nến
      ${esc(r.symbol || '')} ${esc(r.timeframe || '')}, lợi suất log.
      Mức ý nghĩa α = 0,05, hiệu chỉnh đa kiểm định Benjamini–Hochberg.</p>`;

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

    const good = r.verdict?.headline === 'Lợi thế đứng vững qua kiểm định';
    let html = verdictCallout(r.verdict, good ? 'good' : 'warn');

    html += '<div class="metrics">';
    html += cardX('Lợi suất TB/lệnh',
      `${inf.mean_return_pct >= 0 ? '+' : ''}${num(inf.mean_return_pct, 3)}%`,
      'm.expectancy', sign(inf.mean_return_pct), `${inf.n_trades} lệnh`);

    const perm = inf.sign_permutation;
    if (perm) {
      html += cardX('p hoán vị (phi tham số)', P_FMT(perm.p_adjusted ?? perm.p_value),
        Explain.inline(Explain.fromTest(perm)),
        (perm.reject_adjusted ?? perm.reject) ? 'pos' : 'neg',
        'đã hiệu chỉnh đa kiểm định');
    }
    if (boot) {
      html += cardX('KTC 95% bootstrap',
        `${num(boot.ci95_low_pct)}…${num(boot.ci95_high_pct)}%`,
        Explain.inline({
          title: boot.name,
          what: 'Khoảng tin cậy cho lợi suất trung bình mỗi lệnh, không giả định phân phối.',
          rows: [
            ['Trung bình', `${num(boot.mean_pct, 3)}%`],
            ['Cận dưới', `${num(boot.ci95_low_pct, 3)}%`],
            ['Cận trên', `${num(boot.ci95_high_pct, 3)}%`],
            ['Số lần lấy mẫu lại', boot.n_resamples],
          ],
          how: boot.note,
          assumptions: 'BCa hiệu chỉnh cả độ chệch lẫn độ lệch của phân phối bootstrap. Vẫn giả định các lệnh độc lập với nhau.',
        }),
        boot.excludes_zero ? 'pos' : 'neg',
        boot.excludes_zero ? 'không chứa 0' : 'vẫn chứa 0');
    }
    if (power.power !== undefined) {
      html += cardX('Lực kiểm định', `${(power.power * 100).toFixed(0)}%`,
        Explain.inline({
          title: power.name,
          what: 'Xác suất phát hiện được lợi thế, nếu lợi thế thật đúng bằng mức quan sát được.',
          rows: [
            ['Cỡ ảnh hưởng (d)', num(power.effect_size_cohens_d, 3)],
            ['Số lệnh hiện có', power.n],
            ['Cần cho lực 80%', power.n_required_for_80pct ?? '—'],
          ],
          how: power.reading,
          assumptions: power.assumptions,
        }),
        power.adequate ? 'pos' : 'neg',
        power.n_required_for_80pct ? `cần ${power.n_required_for_80pct} lệnh cho 80%` : '');
    }
    if (sharpe && !sharpe.error) {
      html += cardX('PSR', `${(sharpe.psr * 100).toFixed(1)}%`,
        Explain.inline({
          title: 'PSR — Sharpe theo xác suất',
          what: 'Xác suất Sharpe thật lớn hơn 0, có tính tới độ lệch và độ nhọn của lợi suất.',
          rows: [
            ['Sharpe (năm)', num(sharpe.sharpe_annualised)],
            ['Độ lệch', num(sharpe.skew, 3)],
            ['Độ nhọn', num(sharpe.kurtosis)],
            ['Số quan sát', sharpe.n_observations],
            ['MinTRL', sharpe.min_track_record_length ?? '—'],
          ],
          how: sharpe.conclusion,
          assumptions: sharpe.assumptions,
        }),
        sharpe.psr_significant ? 'pos' : 'neg',
        `Sharpe ${num(sharpe.sharpe_annualised)}`);

      html += cardX('DSR (khử phồng)', `${(sharpe.deflated_sharpe_ratio * 100).toFixed(1)}%`,
        Explain.inline({
          title: 'DSR — Sharpe khử phồng',
          what: `Như PSR, nhưng so với ngưỡng mà ${sharpe.n_trials} lần thử tham số tự nó đã tạo ra được.`,
          rows: [
            ['Số lần thử', sharpe.n_trials],
            ['Ngưỡng Sharpe kỳ vọng', num(sharpe.deflation_threshold_sharpe, 4)],
            ['DSR', `${(sharpe.deflated_sharpe_ratio * 100).toFixed(1)}%`],
          ],
          how: sharpe.n_trials > 1
            ? sharpe.conclusion
            : 'Chưa chạy tối ưu nên số lần thử tính là 1, và DSR bằng PSR. Sau khi quét tham số, hãy chạy lại kiểm định này để thấy ngưỡng thật.',
          watch: 'Đây là con số quan trọng nhất khi tham số đến từ một lần quét. Chọn tổ hợp tốt nhất trong 2 000 tổ hợp là chọn cực đại của 2 000 biến ngẫu nhiên — Sharpe của nó cao hơn Sharpe thật kể cả khi không tổ hợp nào có lợi thế.',
          assumptions: sharpe.assumptions,
        }),
        sharpe.dsr_significant ? 'pos' : 'neg',
        `${sharpe.n_trials} lần thử tham số`);
    }
    html += '</div>';

    html += testTable([inf.t_test, inf.wilcoxon, inf.sign_permutation],
      'Kiểm định lợi thế — ba cách hỏi cùng một câu');
    html += familyNote(r.multiple_testing);

    html += `<p class="table-note">Ba kiểm định trên đo cùng một thứ với những giả định khác
      nhau. Nếu chúng cho kết luận khác nhau thì bản thân điều đó là thông tin: kết luận đang
      phụ thuộc vào giả định chứ không phải vào dữ liệu, và kiểm định hoán vị — vốn gần như
      không giả định gì — là cái đáng tin nhất.</p>`;

    if (sharpe?.min_track_record_length) {
      html += `<p class="table-note">Độ dài lịch sử tối thiểu để Sharpe này đạt mức tin cậy
        95% là <strong>${sharpe.min_track_record_length.toLocaleString('vi-VN')}</strong> nến;
        hiện có ${sharpe.n_observations.toLocaleString('vi-VN')}
        ${sharpe.sufficient_history ? '— đủ.' : '— chưa đủ.'}</p>`;
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
        onToast(`Đã tải ${all.length} lệnh của ${source.results.length} chiến lược`);
        return;
      }
    } else if (lastResult?.kind === 'walk-forward') {
      trades = source.trades;
      label = `${source.strategy_id} (ngoài mẫu)`;
    } else if (fallback?.trades?.length) {
      trades = fallback.trades;
      label = fallback.name || fallback.id || 'backtest';
    }

    if (!trades?.length) {
      onToast('Chưa có lệnh nào để xuất — chạy backtest trước.', true);
      return;
    }
    download(`lenh-${stamp}.csv`, tradesToCsv(trades, label));
    onToast(`Đã tải ${trades.length} lệnh ra CSV`);
  }

  function exportChart() {
    const canvas = ChartManager.screenshot();
    if (!canvas) {
      onToast('Không chụp được biểu đồ.', true);
      return;
    }
    canvas.toBlob((blob) => {
      if (!blob) {
        onToast('Không chụp được biểu đồ.', true);
        return;
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bieu-do-${new Date().toISOString().slice(0, 10)}.png`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      onToast('Đã tải biểu đồ ra PNG');
    }, 'image/png');
  }

  function init(config) {
    elements = config.elements;
    context = config.context;
    execution = config.execution;
    catalog = config.catalog;
    onToast = config.onToast;
  }

  return {
    init, runWalkForward, runMonteCarlo, runCompare,
    runSeriesStats, runStrategyStats,
    exportTrades, exportChart,
    get last() { return lastResult; },
  };
})();
