/* Strategy tab: parameters, execution costs, backtest and optimisation.

   The results panel deliberately shows buy-and-hold next to every return
   figure. A strategy that made 40% while simply holding made 120% has lost
   money in the only sense that matters, and that is easy to miss when the
   headline number is green. */

const Strategy = (() => {
  let catalog = [];
  let elements = {};
  let context = () => ({});
  let onResult = () => {};
  let current = null; // the selected spec
  let lastBacktest = null;
  let lastTrials = 1;
  let params = {};
  let sweep = {}; // paramName -> {enabled, start, stop, step}

  const money = (v) =>
    v.toLocaleString('en-US', { maximumFractionDigits: 0, minimumFractionDigits: 0 });
  const pct = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
  const num = (v, d = 2) => (Number.isFinite(v) ? v.toFixed(d) : '—');

  function esc(value) {
    return String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  }

  // ---------- Catalog ----------

  async function load() {
    const data = await API.strategies();
    catalog = data.strategies || [];
    elements.count.textContent = String(catalog.length);

    renderLoadErrors(data.load_errors || []);

    elements.select.innerHTML = catalog
      .map((s) => `<option value="${esc(s.id)}">${esc(s.name)}</option>`)
      .join('');

    elements.metric.innerHTML = (data.rankable_metrics || [])
      .map((m) => `<option value="${esc(m)}">${esc(METRIC_LABELS[m] || m)}</option>`)
      .join('');
    elements.metric.value = 'sharpe';

    if (catalog.length) select(catalog[0].id);
    else elements.params.innerHTML = '<p class="empty">Chưa có chiến lược nào.</p>';
  }

  function renderLoadErrors(errors) {
    const box = elements.errors;
    if (!errors.length) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.innerHTML = errors
      .map((e) => `<div>⚠ ${esc(e.file)}: ${esc(e.error)}</div>`)
      .join('');
  }

  function select(strategyId) {
    current = catalog.find((s) => s.id === strategyId) || null;
    if (!current) return;

    params = {};
    sweep = {};
    for (const p of current.params) {
      params[p.name] = p.default;
      if (p.type !== 'bool') {
        sweep[p.name] = {
          enabled: false,
          start: p.min ?? 1,
          stop: p.max ?? 100,
          step: p.type === 'int' ? 1 : 0.1,
        };
      }
    }

    elements.desc.textContent = current.description || '';
    renderParams();
    renderSweep();
  }

  function renderParams() {
    if (!current.params.length) {
      elements.params.innerHTML = '<p class="empty">Chiến lược này không có tham số.</p>';
      return;
    }

    elements.params.innerHTML = current.params
      .map((p) => {
        const value = params[p.name];
        if (p.type === 'bool') {
          return `<div class="param">
            <span class="param-label">${esc(p.label)}</span>
            <input type="checkbox" data-sparam="${esc(p.name)}" ${value ? 'checked' : ''} />
            <span class="param-value"></span>
          </div>`;
        }
        const step = p.step ?? (p.type === 'int' ? 1 : 0.1);
        return `<div class="param">
          <span class="param-label" title="${esc(p.label)}">${esc(p.label)}</span>
          <input type="range" data-sparam="${esc(p.name)}"
                 min="${p.min ?? 1}" max="${p.max ?? 200}" step="${step}" value="${value}" />
          <span class="param-value" data-svalue="${esc(p.name)}">${value}</span>
        </div>`;
      })
      .join('');

    for (const input of elements.params.querySelectorAll('[data-sparam]')) {
      input.addEventListener('input', () => {
        const name = input.dataset.sparam;
        const value = input.type === 'checkbox' ? input.checked : Number(input.value);
        params[name] = value;
        const readout = elements.params.querySelector(`[data-svalue="${name}"]`);
        if (readout) readout.textContent = String(value);
      });
    }
  }

  function renderSweep() {
    const names = Object.keys(sweep);
    if (!names.length) {
      elements.sweep.innerHTML = '<p class="empty">Không có tham số số học để quét.</p>';
      return;
    }

    let html = '<div class="sweep-head"><span></span><span>Tham số</span><span>Từ</span><span>Đến</span><span>Bước</span></div>';
    for (const name of names) {
      const s = sweep[name];
      const label = current.params.find((p) => p.name === name)?.label || name;
      html += `<div class="sweep-item">
        <input type="checkbox" data-sweep-on="${esc(name)}" ${s.enabled ? 'checked' : ''} />
        <span title="${esc(label)}">${esc(label)}</span>
        <input type="number" data-sweep="${esc(name)}" data-key="start" value="${s.start}" ${s.enabled ? '' : 'disabled'} />
        <input type="number" data-sweep="${esc(name)}" data-key="stop"  value="${s.stop}"  ${s.enabled ? '' : 'disabled'} />
        <input type="number" data-sweep="${esc(name)}" data-key="step"  value="${s.step}"  ${s.enabled ? '' : 'disabled'} />
      </div>`;
    }
    elements.sweep.innerHTML = html;

    for (const box of elements.sweep.querySelectorAll('[data-sweep-on]')) {
      box.addEventListener('change', () => {
        sweep[box.dataset.sweepOn].enabled = box.checked;
        renderSweep();
        scheduleSize();
      });
    }
    for (const input of elements.sweep.querySelectorAll('[data-sweep]')) {
      input.addEventListener('input', () => {
        sweep[input.dataset.sweep][input.dataset.key] = Number(input.value);
        scheduleSize();
      });
    }

    updateSize();
  }

  // ---------- Sweep size ----------
  //
  // Shown before the button is pressed, because the alternative is launching a
  // sweep and finding out from an error that it was never going to run. The
  // parameter space of a real strategy reaches millions of combinations very
  // quickly, and that should be visible while the ranges are being typed.

  let sizeTimer = null;

  function scheduleSize() {
    clearTimeout(sizeTimer);
    sizeTimer = setTimeout(updateSize, 250);
  }

  function enabledRanges() {
    return Object.entries(sweep)
      .filter(([, s]) => s.enabled)
      .map(([name, s]) => ({ name, start: s.start, stop: s.stop, step: s.step }));
  }

  function fmtDuration(seconds) {
    if (seconds < 60) return `${seconds.toFixed(0)} giây`;
    if (seconds < 3600) return `${(seconds / 60).toFixed(0)} phút`;
    return `${(seconds / 3600).toFixed(1)} giờ`;
  }

  async function updateSize() {
    const box = elements.sweepSize;
    if (!box) return;

    const ranges = enabledRanges();
    if (!ranges.length) {
      box.className = 'sweep-size';
      box.textContent = 'Chưa chọn tham số nào để quét.';
      return;
    }

    let info;
    try {
      info = await API.sweepSize({ ranges, bars: context().limit || 2000 });
    } catch (err) {
      box.className = 'sweep-size over';
      box.textContent = err.message;
      return;
    }

    const axes = info.per_axis.map((a) => `${a.name}×${a.values}`).join(' · ');
    const total = info.combinations.toLocaleString('vi-VN');

    if (elements.mode.value === 'random') {
      const samples = Math.min(Number(elements.samples.value) || 500, info.combinations);
      const seconds = (info.estimated_seconds / Math.max(info.combinations, 1)) * samples;
      const coverage = (samples / info.combinations) * 100;
      box.className = 'sweep-size';
      box.innerHTML =
        `Không gian <span class="big">${total}</span> tổ hợp — ${axes}<br>` +
        `Lấy <span class="big">${samples.toLocaleString('vi-VN')}</span> mẫu ` +
        `(${coverage < 0.01 ? '&lt;0,01' : coverage.toFixed(2)}%) ≈ ${fmtDuration(seconds)}`;
      return;
    }

    box.className = `sweep-size${info.exceeds_limit ? ' over' : ''}`;
    box.innerHTML =
      `<span class="big">${total}</span> tổ hợp — ${axes}<br>` +
      (info.exceeds_limit
        ? `Vượt giới hạn ${info.max_combinations.toLocaleString('vi-VN')}, ước tính ` +
          `${fmtDuration(info.estimated_seconds)}. Nới bước nhảy hoặc chuyển sang <strong>Ngẫu nhiên</strong>.`
        : `Ước tính ${fmtDuration(info.estimated_seconds)}`);
  }

  // ---------- Execution settings ----------

  function execution() {
    return {
      initial_capital: Number(elements.capital.value) || 10000,
      size_pct: (Number(elements.size.value) || 100) / 100,
      leverage: Number(elements.leverage.value) || 1,
      fee: (Number(elements.fee.value) || 0) / 100,
      slippage: (Number(elements.slippage.value) || 0) / 100,
    };
  }

  // ---------- Backtest ----------

  async function runBacktest() {
    if (!current) return null;
    const ctx = context();
    const result = await API.backtest({
      strategyId: current.id,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      params,
      execution: execution(),
    });
    lastBacktest = result;
    renderResult(result);
    onResult(result);
    return result;
  }

  const METRIC_LABELS = {
    sharpe: 'Sharpe',
    sortino: 'Sortino',
    total_return_pct: 'Tổng lợi nhuận',
    cagr_pct: 'CAGR',
    profit_factor: 'Profit factor',
    win_rate_pct: 'Tỷ lệ thắng',
    vs_buy_hold_pct: 'So với mua và giữ',
  };

  function metricCard(label, value, cls = '', sub = '') {
    return `<div class="metric">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value ${cls}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function renderResult(result) {
    const m = result.metrics;
    const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

    let html = '';

    if (m.ruined) {
      html += `<div class="callout bad"><strong>Cháy tài khoản.</strong>
        Vốn về 0 sau ${m.liquidations} lần bị thanh lý — hạ đòn bẩy hoặc giảm % vốn mỗi lệnh.</div>`;
    } else if (m.liquidations > 0) {
      html += `<div class="callout warn"><strong>${m.liquidations} lần bị thanh lý.</strong>
        Vị thế bị đóng cưỡng bức khi lỗ chạm mức ký quỹ.</div>`;
    }

    if (!m.ruined && m.vs_buy_hold_pct < 0) {
      html += `<div class="callout warn">Chiến lược <strong>thua mua-và-giữ ${Math.abs(m.vs_buy_hold_pct).toFixed(1)} điểm %</strong>
        trên cùng khoảng thời gian. Chỉ mua rồi giữ đã tốt hơn.</div>`;
    }

    if (m.num_trades < 10 && m.num_trades > 0) {
      html += `<div class="callout warn">Chỉ ${m.num_trades} lệnh — quá ít để kết luận gì.
        Kéo dài dữ liệu hoặc nới tham số.</div>`;
    }

    html += '<div class="metrics">';
    html += metricCard('Tổng lợi nhuận', pct(m.total_return_pct), sign(m.total_return_pct),
      `${money(m.initial_capital)} → ${money(m.final_equity)}`);
    html += metricCard('Mua và giữ', pct(m.buy_hold_return_pct), sign(m.buy_hold_return_pct),
      `chênh ${pct(m.vs_buy_hold_pct)}`);
    html += metricCard('CAGR', pct(m.cagr_pct), sign(m.cagr_pct));
    html += metricCard('Sụt giảm tối đa', `-${m.max_drawdown_pct.toFixed(2)}%`,
      m.max_drawdown_pct > 0 ? 'neg' : '');
    html += metricCard('Sharpe', num(m.sharpe), sign(m.sharpe));
    html += metricCard('Sortino', num(m.sortino), sign(m.sortino));
    html += metricCard('Số lệnh', String(m.num_trades), '',
      `${m.num_wins} thắng / ${m.num_losses} thua`);
    html += metricCard('Tỷ lệ thắng', `${m.win_rate_pct.toFixed(1)}%`);
    html += metricCard('Profit factor',
      Number.isFinite(m.profit_factor) ? num(m.profit_factor) : '∞',
      m.profit_factor > 1 ? 'pos' : 'neg');
    html += metricCard('Tỷ lệ nắm giữ', `${m.exposure_pct.toFixed(1)}%`, '',
      `${m.avg_bars_held.toFixed(0)} nến/lệnh`);
    html += metricCard('Lãi TB / lỗ TB',
      `${money(m.avg_win)} / ${money(m.avg_loss)}`);
    html += metricCard('Tốt nhất / tệ nhất',
      `${money(m.best_trade)} / ${money(m.worst_trade)}`);
    html += '</div>';

    elements.metrics.innerHTML = html;

    EquityChart.render(
      elements.equityChart,
      result.times,
      result.equity,
      m.initial_capital,
    );

    renderTrades(result.trades);
  }

  function renderTrades(trades) {
    if (!trades.length) {
      elements.trades.innerHTML = '<p class="empty">Không có lệnh nào.</p>';
      return;
    }

    const fmt = (ts) => new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ');

    let html = `<table class="data-table"><thead><tr>
      <th>Vào</th><th>Chiều</th><th>Giá vào</th><th>Giá ra</th>
      <th>Lãi/Lỗ</th><th>%</th><th>Nến</th><th>Kết thúc</th>
    </tr></thead><tbody>`;

    for (const t of trades) {
      const cls = t.pnl > 0 ? 'pos' : t.pnl < 0 ? 'neg' : 'muted';
      html += `<tr>
        <td class="muted">${fmt(t.entry_time)}</td>
        <td class="${t.side === 'long' ? 'pos' : 'neg'}">${t.side === 'long' ? 'LONG' : 'SHORT'}</td>
        <td>${t.entry_price.toFixed(2)}</td>
        <td>${t.exit_price.toFixed(2)}</td>
        <td class="${cls}">${money(t.pnl)}</td>
        <td class="${cls}">${t.return_pct.toFixed(1)}</td>
        <td class="muted">${t.bars_held}</td>
        <td class="muted">${t.exit_reason === 'liquidation' ? 'THANH LÝ' : t.exit_reason === 'end_of_data' ? 'hết dữ liệu' : 'tín hiệu'}</td>
      </tr>`;
    }
    html += '</tbody></table>';
    elements.trades.innerHTML = html;
  }

  // ---------- Optimisation ----------

  async function runOptimize() {
    if (!current) return null;

    const ranges = enabledRanges();

    if (!ranges.length) {
      elements.optimize.innerHTML =
        '<p class="empty">Chọn ít nhất một tham số để quét (tích ô bên trái).</p>';
      return null;
    }

    const ctx = context();
    const result = await API.optimize({
      strategyId: current.id,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      limit: ctx.limit,
      ranges,
      metric: elements.metric.value,
      mode: elements.mode.value,
      samples: Number(elements.samples.value) || 500,
      execution: execution(),
    });

    renderOptimize(result);
    return result;
  }

  function renderOptimize(result) {
    const s = result.summary;
    // Remembered for the deflated Sharpe ratio: a strategy whose parameters
    // were picked as the best of 2 000 sweeps has to clear a far higher bar
    // than one typed in by hand, and the statistics panel cannot know that
    // number unless the sweep tells it.
    lastTrials = s.combinations || 1;
    const rows = result.results;

    if (!rows.length) {
      elements.optimize.innerHTML = '<p class="empty">Không tổ hợp nào chạy được.</p>';
      return;
    }

    let html = '';

    if (s.overfit_warning) {
      html += `<div class="callout warn"><strong>Cẩn thận overfit.</strong>
        Chỉ ${s.profitable_pct.toFixed(0)}% tổ hợp có lãi, nhưng tổ hợp tốt nhất vượt trung vị
        ${s.best_z_score.toFixed(1)} độ lệch chuẩn. Dáng này thường là may mắn, không phải lợi thế thật.</div>`;
    }

    html += '<div class="metrics">';
    html += metricCard(
      s.mode === 'random' ? 'Số mẫu đã chạy' : 'Số tổ hợp',
      String(s.combinations),
      '',
      s.mode === 'random'
        ? `${s.coverage_pct < 0.01 ? '<0,01' : s.coverage_pct.toFixed(2)}% của ${s.space_size.toLocaleString('vi-VN')}`
        : (s.failed ? `${s.failed} lỗi` : ''),
    );
    html += metricCard('Có lãi', `${s.profitable_pct.toFixed(0)}%`,
      s.profitable_pct >= 50 ? 'pos' : 'neg', `${s.profitable}/${s.completed}`);
    html += metricCard('Trung vị lợi nhuận', pct(s.median_return_pct),
      s.median_return_pct > 0 ? 'pos' : 'neg');
    html += metricCard('Mua và giữ', pct(s.buy_hold_return_pct),
      s.buy_hold_return_pct > 0 ? 'pos' : 'neg');
    html += '</div>';

    const paramNames = Object.keys(rows[0].params);
    html += '<table class="data-table"><thead><tr>';
    for (const n of paramNames) html += `<th>${esc(n)}</th>`;
    html += `<th>${esc(METRIC_LABELS[s.metric] || s.metric)}</th>
      <th>Lợi nhuận</th><th>MaxDD</th><th>Thắng</th><th>Lệnh</th></tr></thead><tbody>`;

    rows.forEach((r, i) => {
      const m = r.metrics;
      html += `<tr class="${i === 0 ? 'best' : ''}">`;
      for (const n of paramNames) html += `<td>${esc(r.params[n])}</td>`;
      const score = m[s.metric];
      html += `<td class="${score > 0 ? 'pos' : 'neg'}">${
        Number.isFinite(score) ? score.toFixed(2) : '—'
      }</td>`;
      html += `<td class="${m.total_return_pct > 0 ? 'pos' : 'neg'}">${m.total_return_pct.toFixed(1)}%</td>`;
      html += `<td class="neg">-${m.max_drawdown_pct.toFixed(1)}%</td>`;
      html += `<td class="muted">${m.win_rate_pct.toFixed(0)}%</td>`;
      html += `<td class="muted">${m.num_trades}</td>`;
      html += '</tr>';
    });
    html += '</tbody></table>';

    html += `<p class="table-note">Hàng đầu là tổ hợp tốt nhất theo
      ${esc(METRIC_LABELS[s.metric] || s.metric)}. Nhấn một hàng để nạp tham số đó vào bảng bên trái.</p>`;

    elements.optimize.innerHTML = html;

    // Clicking a row loads those parameters, so a promising cell can be
    // inspected as a full backtest rather than trusted from the table.
    const bodyRows = elements.optimize.querySelectorAll('tbody tr');
    bodyRows.forEach((tr, i) => {
      tr.style.cursor = 'pointer';
      tr.addEventListener('click', () => {
        Object.assign(params, rows[i].params);
        renderParams();
        runBacktest().catch(() => {});
      });
    });
  }

  // ---------- Paper trading ----------

  async function startPaper() {
    if (!current) return null;
    const ctx = context();
    // The same strategy, parameters and cost settings the backtest just used,
    // so a session is directly comparable with the run that motivated it.
    return Paper.start({
      strategyId: current.id,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      params,
      execution: execution(),
    });
  }

  function init(config) {
    elements = config.elements;
    context = config.context;
    onResult = config.onResult;

    elements.select.addEventListener('change', () => {
      select(elements.select.value);
      if (config.onSelect) config.onSelect(elements.select.value);
    });

    elements.mode.addEventListener('change', () => {
      elements.samplesRow.hidden = elements.mode.value !== 'random';
      updateSize();
    });
    elements.samples.addEventListener('input', scheduleSize);
  }

  return {
    init, load, runBacktest, runOptimize, startPaper,
    // Exposed so validation and comparison reuse exactly the parameters and
    // costs the backtest just used, rather than assembling their own.
    execution,
    sweepRanges: enabledRanges,
    currentParams: () => ({ ...params }),
    get catalog() { return catalog; },
    get selected() { return current; },
    get lastResult() { return lastBacktest; },
    // How many parameter combinations were tried to reach the current values.
    get lastTrials() { return lastTrials; },
  };
})();
