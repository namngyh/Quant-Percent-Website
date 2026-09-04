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

  async function runSeriesStats() {
    const ctx = context();
    const result = await API.statsSeries({
      symbol: ctx.symbol, timeframe: ctx.timeframe, limit: ctx.limit,
    });
    renderSeriesStats(result);
    return result;
  }

  function renderSeriesStats(r) {
    const d = r.distribution;
    const s = r.stochastic;
    if (d.error) { elements.stats.innerHTML = `<p class="empty">${esc(d.error)}</p>`; return; }

    let html = '';

    // The headline finding, in words, before any table.
    const randomWalk = s.variance_ratio?.random_walk && !s.has_autocorrelation;
    if (randomWalk) {
      html += `<div class="callout warn"><strong>Chuỗi này gần như bước ngẫu nhiên.</strong>
        Không tìm thấy tự tương quan trong lợi suất (Ljung–Box p = ${s.ljungbox_p.toFixed(3)}),
        và tỷ số phương sai không bác bỏ được bước ngẫu nhiên. Chỉ báo dựa trên
        <em>hướng</em> giá quá khứ sẽ rất khó ăn thua ở đây.</div>`;
    }
    if (s.has_volatility_clustering) {
      html += `<div class="callout good"><strong>Biến động có gom cụm.</strong>
        Đây là cấu trúc thật và khai thác được — dù hướng giá khó dự đoán, thì
        <em>mức độ dao động</em> lại có quán tính.</div>`;
    }
    if (!d.is_normal) {
      html += `<div class="callout warn">Lợi suất <strong>không theo phân phối chuẩn</strong>
        (độ nhọn thừa ${d.kurtosis_excess.toFixed(1)}, chuẩn là 0). Đuôi dày hơn nhiều so với
        giả định chuẩn, nên Sharpe và mọi công thức giả định chuẩn đều
        <strong>đánh giá thấp rủi ro đuôi</strong>.</div>`;
    }

    html += '<div class="metrics">';
    html += card('Độ nhọn thừa', d.kurtosis_excess.toFixed(2), d.kurtosis_excess > 1 ? 'neg' : '',
      'chuẩn = 0');
    html += card('Độ lệch', d.skew.toFixed(3), '', d.skew < 0 ? 'đuôi trái dày hơn' : 'đuôi phải dày hơn');
    html += card('VaR 95%', `${d.var_95_pct.toFixed(2)}%`, 'neg', `CVaR ${d.cvar_95_pct.toFixed(2)}%`);
    html += card('VaR 99%', `${d.var_99_pct.toFixed(2)}%`, 'neg', `CVaR ${d.cvar_99_pct.toFixed(2)}%`);
    html += card('Hurst', Number.isFinite(s.hurst) ? s.hurst.toFixed(3) : '—', '', s.hurst_reading);
    html += card('Tỷ số phương sai',
      s.variance_ratio?.variance_ratio?.toFixed(3) ?? '—', '',
      s.variance_ratio?.random_walk ? 'không bác bỏ bước ngẫu nhiên' : 'khác bước ngẫu nhiên');
    html += '</div>';

    const row = (name, value, verdict, cls = '') =>
      `<tr><td>${esc(name)}</td><td>${value}</td><td class="${cls}">${esc(verdict)}</td></tr>`;

    html += '<table class="data-table"><thead><tr><th>Kiểm định</th><th>Giá trị</th><th>Kết luận</th></tr></thead><tbody>';
    html += row('Jarque–Bera (chuẩn)', `p = ${d.jarque_bera_p.toExponential(1)}`,
      d.is_normal ? 'phân phối chuẩn' : 'KHÔNG chuẩn', d.is_normal ? '' : 'neg');
    if (s.adf_price_p !== undefined) {
      html += row('ADF trên giá', `p = ${s.adf_price_p.toFixed(4)}`,
        s.adf_price_stationary ? 'dừng' : 'không dừng');
      html += row('ADF trên lợi suất', `p = ${s.adf_return_p.toExponential(1)}`,
        s.adf_return_stationary ? 'dừng' : 'không dừng',
        s.adf_return_stationary ? 'pos' : 'neg');
    }
    if (s.ljungbox_p !== undefined) {
      html += row(`Ljung–Box (${s.ljungbox_lags} độ trễ)`, `p = ${s.ljungbox_p.toFixed(4)}`,
        s.has_autocorrelation ? 'CÓ tự tương quan' : 'không có',
        s.has_autocorrelation ? 'pos' : '');
    }
    if (s.volatility_clustering_p !== undefined) {
      html += row('Ljung–Box trên |lợi suất|', `p = ${s.volatility_clustering_p.toExponential(1)}`,
        s.has_volatility_clustering ? 'CÓ gom cụm biến động' : 'không',
        s.has_volatility_clustering ? 'pos' : '');
    }
    if (s.variance_ratio?.z_score !== undefined) {
      html += row(`Tỷ số phương sai (q=${s.variance_ratio.period})`,
        `z = ${s.variance_ratio.z_score.toFixed(2)}`,
        s.variance_ratio.random_walk ? 'không bác bỏ bước ngẫu nhiên' : 'bác bỏ bước ngẫu nhiên');
    }
    html += '</tbody></table>';
    html += `<p class="table-note">Trên ${r.bars.toLocaleString('vi-VN')} nến
      ${esc(r.symbol || '')} ${esc(r.timeframe || '')}. Mức ý nghĩa 5%.</p>`;

    elements.stats.innerHTML = html;
  }

  async function runStrategyStats(params) {
    const ctx = context();
    const result = await API.statsStrategy({
      strategyId: elements.strategySelect.value,
      symbol: ctx.symbol, timeframe: ctx.timeframe, limit: ctx.limit,
      params, execution: execution(),
    });
    renderStrategyStats(result);
    return result;
  }

  function renderStrategyStats(r) {
    if (r.error) { elements.stats.innerHTML = `<p class="empty">${esc(r.error)}</p>`; return; }
    const inf = r.inference;
    const bay = r.bayesian;
    let html = '';

    if (inf.error) {
      html += `<div class="callout warn">${esc(inf.error)}</div>`;
    } else if (!inf.significant) {
      html += `<div class="callout warn"><strong>Lợi thế chưa có ý nghĩa thống kê.</strong>
        Lợi suất trung bình mỗi lệnh ${inf.mean_return_pct >= 0 ? '+' : ''}${inf.mean_return_pct.toFixed(3)}%,
        p = ${inf.p_value_one_sided.toFixed(3)} — không bác bỏ được giả thuyết
        "lợi thế bằng 0". Khoảng tin cậy 95% vẫn chứa số 0.</div>`;
    } else {
      html += `<div class="callout good"><strong>Lợi thế có ý nghĩa thống kê</strong>
        (p = ${inf.p_value_one_sided.toFixed(4)}). Vẫn nên chạy walk-forward:
        kiểm định này không biết tham số đã được chọn bằng hậu nghiệm hay chưa.</div>`;
    }
    if (inf.underpowered) {
      html += `<div class="callout warn">Chỉ ${inf.n_trades} lệnh — quá ít để kiểm định
        có sức mạnh. Kết luận nào rút ra ở đây cũng mong manh.</div>`;
    }

    html += '<div class="metrics">';
    if (!inf.error) {
      html += card('Lợi suất TB/lệnh', `${inf.mean_return_pct >= 0 ? '+' : ''}${inf.mean_return_pct.toFixed(3)}%`,
        sign(inf.mean_return_pct), `${inf.n_trades} lệnh`);
      html += card('p (một phía)', inf.p_value_one_sided.toFixed(4),
        inf.significant ? 'pos' : 'neg', inf.significant ? 'có ý nghĩa' : 'không có ý nghĩa');
      html += card('KTC 95%',
        `${inf.ci95_low_pct.toFixed(2)}% … ${inf.ci95_high_pct.toFixed(2)}%`, '',
        'chứa 0 nghĩa là chưa kết luận được');
    }
    html += card('Tỷ lệ thắng quan sát', `${bay.observed_win_rate_pct.toFixed(1)}%`, '',
      `${bay.wins} thắng / ${bay.losses} thua`);
    html += card('Bayes · khoảng tin 95%',
      `${bay.credible_95_low_pct.toFixed(1)}–${bay.credible_95_high_pct.toFixed(1)}%`, '',
      `rộng ${bay.credible_width_pct.toFixed(1)} điểm`);
    html += card('P(thắng thật > 50%)', `${bay.prob_better_than_coin_pct.toFixed(1)}%`,
      bay.prob_better_than_coin_pct > 50 ? 'pos' : 'neg');
    html += '</div>';

    html += `<p class="table-note">Hậu nghiệm Beta–Nhị thức với tiên nghiệm ${esc(bay.prior)}
      (phân phối đều — chưa giả định gì). Bề rộng khoảng tin cậy là thứ mà một con số
      tỷ lệ thắng đơn lẻ che mất: với ít lệnh, nó rộng đến mức gần như vô dụng.</p>`;

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
