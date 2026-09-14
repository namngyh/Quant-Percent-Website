/* Strategy tab: parameters, execution costs, backtest and optimisation.

   The results panel deliberately shows buy-and-hold next to every return
   figure. A strategy that made 40% while simply holding made 120% has lost
   money in the only sense that matters, and that is easy to miss when the
   headline number is green. */

const Strategy = (() => {
  let catalog = [];
  let onChange = () => {};
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
    else elements.params.innerHTML = `<p class="empty">${esc(L(
      'Chưa có chiến lược nào.', 'No strategies yet.'))}</p>`;
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

  function select(strategyId, initial = null) {
    current = catalog.find((s) => s.id === strategyId) || null;
    if (!current) return;

    params = {};
    sweep = {};
    for (const p of current.params) {
      // A restored session brings its tuned values back; anything the
      // strategy no longer declares is left behind.
      const kept = initial && Object.prototype.hasOwnProperty.call(initial, p.name)
        ? initial[p.name] : undefined;
      params[p.name] = kept === undefined ? p.default : kept;
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
    onChange();
  }

  /** The chosen strategy and its parameters, for a reload to put back. */
  function snapshot() {
    return current ? { id: current.id, params: { ...params } } : null;
  }

  function restore(snap) {
    if (!snap || !catalog.some((s) => s.id === snap.id)) return;
    elements.select.value = snap.id;
    select(snap.id, snap.params);
  }

  function renderParams() {
    if (!current.params.length) {
      elements.params.innerHTML = `<p class="empty">${esc(L(
        'Chiến lược này không có tham số.', 'This strategy has no parameters.'))}</p>`;
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
        onChange();
      });
    }
  }

  function renderSweep() {
    const names = Object.keys(sweep);
    if (!names.length) {
      elements.sweep.innerHTML = `<p class="empty">${esc(L(
        'Không có tham số số học để quét.',
        'No numeric parameter to sweep.'))}</p>`;
      return;
    }

    let html = `<div class="sweep-head"><span></span>
      <span>${esc(L('Tham số', 'Parameter'))}</span>
      <span>${esc(L('Từ', 'From'))}</span>
      <span>${esc(L('Đến', 'To'))}</span>
      <span>${esc(L('Bước', 'Step'))}</span></div>`;
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
    if (seconds < 60) return L(`${seconds.toFixed(0)} giây`, `${seconds.toFixed(0)}s`);
    if (seconds < 3600) {
      return L(`${(seconds / 60).toFixed(0)} phút`, `${(seconds / 60).toFixed(0)} min`);
    }
    return L(`${(seconds / 3600).toFixed(1)} giờ`, `${(seconds / 3600).toFixed(1)} h`);
  }

  async function updateSize() {
    const box = elements.sweepSize;
    if (!box) return;

    const ranges = enabledRanges();
    if (!ranges.length) {
      box.className = 'sweep-size';
      box.textContent = L('Chưa chọn tham số nào để quét.',
                          'No parameter selected to sweep.');
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
        L(`Không gian <span class="big">${total}</span> tổ hợp: ${axes}<br>`,
          `A space of <span class="big">${total}</span> combinations: ${axes}<br>`) +
        L(`Lấy <span class="big">${samples.toLocaleString(I18n.locale())}</span> mẫu `,
          `Sampling <span class="big">${samples.toLocaleString(I18n.locale())}</span> of them `) +
        `(${coverage < 0.01 ? '&lt;0,01' : coverage.toFixed(2)}%) ≈ ${fmtDuration(seconds)}`;
      return;
    }

    box.className = `sweep-size${info.exceeds_limit ? ' over' : ''}`;
    box.innerHTML =
      L(`<span class="big">${total}</span> tổ hợp: ${axes}<br>`,
        `<span class="big">${total}</span> combinations: ${axes}<br>`) +
      (info.exceeds_limit
        ? L(`Vượt giới hạn ${info.max_combinations.toLocaleString(I18n.locale())}, ước tính `
            + `${fmtDuration(info.estimated_seconds)}. Nới bước nhảy hoặc chuyển sang <strong>Ngẫu nhiên</strong>.`,
            `Over the ${info.max_combinations.toLocaleString(I18n.locale())} limit, about `
            + `${fmtDuration(info.estimated_seconds)}. Widen the step or switch to <strong>Random</strong>.`)
        : L(`Ước tính ${fmtDuration(info.estimated_seconds)}`,
            `About ${fmtDuration(info.estimated_seconds)}`));
  }

  // ---------- Execution settings ----------

  /* The date window, as the API wants it: inclusive ISO instants, or nothing.

     The end date is pushed to the last second of the day rather than midnight,
     because a person choosing "to 30 June" means the whole of 30 June. Sent as
     midnight it would silently drop that day's bars, and a backtest quietly
     one day short is the kind of thing nobody notices. */
  function period() {
    const start = elements.startDate?.value;
    const end = elements.endDate?.value;
    return {
      start: start ? `${start}T00:00:00+00:00` : null,
      end: end ? `${end}T23:59:59+00:00` : null,
    };
  }

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
      period: period(),
    });
    lastBacktest = result;
    renderResult(result);
    onResult(result, ctx);
    return result;
  }

  const METRIC_LABELS = {
    sharpe: 'Sharpe',
    sortino: 'Sortino',
    total_return_pct: L('Tổng lợi nhuận', 'Total return'),
    cagr_pct: 'CAGR',
    profit_factor: 'Profit factor',
    win_rate_pct: L('Tỷ lệ thắng', 'Win rate'),
    vs_buy_hold_pct: L('So với mua và giữ', 'Against buy and hold'),
  };

  function metricCard(label, value, cls = '', sub = '', info = '') {
    return `<div class="metric">
      <div class="metric-label">${esc(label)}${info}</div>
      <div class="metric-value ${cls}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function renderResult(result) {
    const m = result.metrics;
    const sign = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

    let html = '';

    if (m.ruined) {
      html += `<div class="callout bad">${esc(L(
        `Cháy tài khoản. Vốn về 0 sau ${m.liquidations} lần bị thanh lý: hãy hạ đòn bẩy hoặc giảm % vốn mỗi lệnh.`,
        `Account wiped out. Equity reached zero after ${m.liquidations} liquidation(s): lower the leverage or the share of equity per trade.`))}</div>`;
    } else if (m.liquidations > 0) {
      html += `<div class="callout warn">${esc(L(
        `${m.liquidations} lần bị thanh lý. Vị thế bị đóng cưỡng bức khi lỗ chạm mức ký quỹ.`,
        `${m.liquidations} liquidation(s). The position was force-closed when the loss reached the margin.`))}</div>`;
    }

    if (!m.ruined && m.vs_buy_hold_pct < 0) {
      html += `<div class="callout warn">${esc(L(
        `Chiến lược thua mua-và-giữ ${Math.abs(m.vs_buy_hold_pct).toFixed(1)} điểm % trên cùng khoảng thời gian. Chỉ mua rồi giữ đã tốt hơn.`,
        `The strategy lost to buy-and-hold by ${Math.abs(m.vs_buy_hold_pct).toFixed(1)} points over the same window. Simply buying and holding did better.`))}</div>`;
    }

    if (m.num_trades < 10 && m.num_trades > 0) {
      html += `<div class="callout warn">${esc(L(
        `Chỉ ${m.num_trades} lệnh — quá ít để kết luận. Kéo dài dữ liệu hoặc nới tham số.`,
        `Only ${m.num_trades} trades — too few to conclude anything. Widen the data or loosen the parameters.`))}</div>`;
    }

    html += '<div class="metrics">';
    html += metricCard(L('Tổng lợi nhuận', 'Total return'),
      pct(m.total_return_pct), sign(m.total_return_pct),
      `${money(m.initial_capital)} → ${money(m.final_equity)}`);
    html += metricCard(L('Mua và giữ', 'Buy and hold'),
      pct(m.buy_hold_return_pct), sign(m.buy_hold_return_pct),
      L(`chênh ${pct(m.vs_buy_hold_pct)}`, `${pct(m.vs_buy_hold_pct)} difference`));
    html += metricCard('CAGR', pct(m.cagr_pct), sign(m.cagr_pct));
    html += metricCard(L('Sụt giảm tối đa', 'Max drawdown'),
      `-${m.max_drawdown_pct.toFixed(2)}%`,
      m.max_drawdown_pct > 0 ? 'neg' : '');
    html += metricCard('Sharpe', num(m.sharpe), sign(m.sharpe));
    html += metricCard('Sortino', num(m.sortino), sign(m.sortino));
    html += metricCard(L('Số lệnh', 'Trades'), String(m.num_trades), '',
      L(`${m.num_wins} thắng / ${m.num_losses} thua`,
        `${m.num_wins} won / ${m.num_losses} lost`));
    html += metricCard(L('Tỷ lệ thắng', 'Win rate'), `${m.win_rate_pct.toFixed(1)}%`);
    html += metricCard('Profit factor',
      Number.isFinite(m.profit_factor) ? num(m.profit_factor) : '∞',
      m.profit_factor > 1 ? 'pos' : 'neg');
    html += metricCard(L('Tỷ lệ nắm giữ', 'Exposure'), `${m.exposure_pct.toFixed(1)}%`, '',
      L(`${m.avg_bars_held.toFixed(0)} nến/lệnh`,
        `${m.avg_bars_held.toFixed(0)} bars per trade`));
    html += metricCard(L('Lãi TB / lỗ TB', 'Avg win / avg loss'),
      `${money(m.avg_win)} / ${money(m.avg_loss)}`);
    html += metricCard(L('Tốt nhất / tệ nhất', 'Best / worst'),
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
      elements.trades.innerHTML = `<p class="empty">${esc(L(
        'Không có lệnh nào.', 'No trades.'))}</p>`;
      return;
    }

    const fmt = (ts) => new Date(ts * 1000).toISOString().slice(0, 16).replace('T', ' ');

    let html = `<table class="data-table"><thead><tr>
      <th>${esc(L('Vào', 'In'))}</th>
      <th>${esc(L('Chiều', 'Side'))}</th>
      <th>${esc(L('Giá vào', 'Entry'))}</th>
      <th>${esc(L('Giá ra', 'Exit'))}</th>
      <th>${esc(L('Lãi/Lỗ', 'P&L'))}</th><th>%</th>
      <th>${esc(L('Nến', 'Bars'))}</th>
      <th>${esc(L('Kết thúc', 'Closed by'))}</th>
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
        <td class="muted">${esc(
          t.exit_reason === 'liquidation' ? L('THANH LÝ', 'LIQUIDATED')
            : t.exit_reason === 'end_of_data' ? L('hết dữ liệu', 'end of data')
            : L('tín hiệu', 'signal'))}</td>
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
        `<p class="empty">${esc(L(
          'Chọn ít nhất một tham số để quét (tích ô bên trái).',
          'Tick at least one parameter to sweep, on the left.'))}</p>`;
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
      period: period(),
    });

    renderOptimize(result);
    return result;
  }

  const robustnessExplain = (rb) => Explain.inline({
    title: L('Độ bền theo lân cận tham số', 'Parameter-neighbourhood robustness'),
    what: L('Tổ hợp thắng đứng trên một vùng tốt, hay đứng một mình trên một đỉnh nhọn.',
            'Whether the winning combination stands on a good region, or alone on a spike.'),
    rows: [[L('Kết luận', 'Verdict'), { plateau: L('Cao nguyên', 'Plateau'),
             ridge: L('Sườn dốc', 'Ridge'), spike: L('Đỉnh nhọn', 'Spike') }[rb.code]],
           [L('Số lân cận đã chạy', 'Neighbours run'),
            `${rb.neighbours_found}${rb.neighbours_missing
              ? ` (${rb.neighbours_missing} ${L('chưa chạy', 'not run')})` : ''}`],
           [L('Trung vị điểm lân cận', 'Neighbour median score'),
            rb.neighbour_median_score.toFixed(3)],
           [L('Bách phân vị trong lưới', 'Percentile within the grid'),
            rb.neighbour_median_percentile.toFixed(0)],
           [L('Điểm tổ hợp thắng', 'Winner score'), rb.winner_score.toFixed(3)]],
    how: L('Lợi thế thật suy giảm từ từ: đổi một tham số đúng một bước thì các ô ngay cạnh cũng phải thuộc nhóm dẫn đầu của lưới. Đỉnh nhọn thì ngược lại — xung quanh chỉ tầm thường, nghĩa là đúng bộ giá trị đó mới thắng, và một bộ giá trị chỉ thắng ở đúng một điểm thì đã khớp vào nhiễu của chính mẫu này.',
            'A real edge degrades gently: move one parameter by exactly one step and the adjacent cells should still be near the top of the grid. A spike is the opposite — its surroundings are ordinary, which means those exact values are what won, and a set of values that wins at exactly one point has fitted the noise in this sample.'),
    formula: L('bách phân vị của trung vị điểm lân cận trong phân phối điểm của cả lưới',
               "the percentile of the neighbours' median within the whole grid's score distribution"),
    watch: L('Chỉ xét lân cận cách một bước theo đúng một trục, không xét đường chéo. Ở chế độ ngẫu nhiên nhiều ô lân cận có thể chưa chạy — khi đó số lân cận tìm được nhỏ và kết luận yếu đi tương ứng. Bách phân vị lấy điểm giữa của khối đồng điểm; nếu lấy mép trên thì một lưới toàn ô bằng nhau sẽ báo mọi thứ đều ở nhóm dẫn đầu.',
             'Only neighbours one step away along exactly one axis count; diagonals do not. Under random mode many neighbouring cells may never have been run, in which case the neighbour count is small and the verdict is correspondingly weak. The percentile takes the midpoint of a tied block; taking its upper edge would report every cell of an all-equal grid as top of the distribution.'),
  });

  const deflatedExplain = (dfl) => Explain.inline({
    title: L('Sharpe đã khử phồng (DSR)', 'Deflated Sharpe ratio (DSR)'),
    what: L('Xác suất Sharpe thật của tổ hợp thắng lớn hơn 0, sau khi trừ đi phần cao lên chỉ vì đã thử rất nhiều tổ hợp.',
            "The probability that the winner's true Sharpe is above zero, after removing the part that is high merely because many combinations were tried."),
    rows: [[L('Số phép thử', 'Trials'), String(dfl.trials)],
           ['PSR', `${(dfl.psr * 100).toFixed(1)}%`],
           ['DSR', `${(dfl.deflated_sharpe_ratio * 100).toFixed(1)}%`],
           [L('Độ phân tán giữa các phép thử', 'Cross-trial dispersion'),
            dfl.cross_trial_dispersion.toFixed(3)]],
    how: L('Chọn ô tốt nhất của một lưới là chọn cực đại của ngần ấy biến ngẫu nhiên. DSR so Sharpe của tổ hợp thắng với kỳ vọng của cực đại đó, nên lưới càng lớn thì Sharpe càng phải cao mới qua được. Dưới 50% nghĩa là quét ngần này tổ hợp trên dữ liệu không có lợi thế nào cũng cho ra đúng con số đó.',
            'Picking the best cell of a grid picks the maximum of that many random variables. DSR compares the winner against the expected maximum, so a larger grid must produce a higher Sharpe to pass. Below 50% means sweeping this many combinations over data with no edge at all would produce the same number.'),
    source: 'Bailey & López de Prado (2014), "The Deflated Sharpe Ratio".',
    watch: L('Đại lượng khó nhất của công thức là độ phân tán Sharpe giữa các phép thử. Panel Thống kê không đo được nó từ một backtest đơn lẻ nên phải xấp xỉ bằng sai số chuẩn; ở đây nó được đo trực tiếp trên toàn bộ lưới. Đó là lý do DSR ở tab này thường thấp hơn — và đúng hơn.',
             "The hardest quantity in the formula is the cross-trial Sharpe dispersion. The Statistics panel cannot measure it from a single backtest and must approximate it with a standard error; here it is measured directly over the whole grid. That is why the DSR in this tab is usually lower — and more honest."),
  });

  function renderOptimize(result) {
    const s = result.summary;
    // Remembered for the deflated Sharpe ratio: a strategy whose parameters
    // were picked as the best of 2 000 sweeps has to clear a far higher bar
    // than one typed in by hand, and the statistics panel cannot know that
    // number unless the sweep tells it.
    lastTrials = s.combinations || 1;
    const rows = result.results;

    if (!rows.length) {
      elements.optimize.innerHTML = `<p class="empty">${esc(L(
        'Không tổ hợp nào chạy được.', 'No combination could run.'))}</p>`;
      return;
    }

    let html = '';

    if (s.overfit_warning) {
      html += `<div class="callout warn"><strong>${esc(L(
        'Cẩn thận overfit.', 'Watch for overfitting.'))}</strong> ${esc(L(
        `Chỉ ${s.profitable_pct.toFixed(0)}% tổ hợp có lãi, nhưng tổ hợp tốt nhất vượt trung vị ${s.best_z_score.toFixed(1)} độ lệch chuẩn. Dáng này thường là may mắn, không phải lợi thế thật.`,
        `Only ${s.profitable_pct.toFixed(0)}% of combinations made money, yet the best one sits ${s.best_z_score.toFixed(1)} standard deviations above the median. That shape is usually luck, not an edge.`))}</div>`;
    }

    html += '<div class="metrics">';
    html += metricCard(
      s.mode === 'random' ? L('Số mẫu đã chạy', 'Samples run') : L('Số tổ hợp', 'Combinations'),
      String(s.combinations),
      '',
      s.mode === 'random'
        ? L(`${s.coverage_pct < 0.01 ? '<0,01' : s.coverage_pct.toFixed(2)}% của ${
              s.space_size.toLocaleString(I18n.locale())}`,
            `${s.coverage_pct < 0.01 ? '<0.01' : s.coverage_pct.toFixed(2)}% of ${
              s.space_size.toLocaleString(I18n.locale())}`)
        : (s.failed ? L(`${s.failed} lỗi`, `${s.failed} failed`) : ''),
    );
    html += metricCard(L('Có lãi', 'Profitable'), `${s.profitable_pct.toFixed(0)}%`,
      s.profitable_pct >= 50 ? 'pos' : 'neg', `${s.profitable}/${s.completed}`);
    html += metricCard(L('Trung vị lợi nhuận', 'Median return'), pct(s.median_return_pct),
      s.median_return_pct > 0 ? 'pos' : 'neg');
    html += metricCard(L('Mua và giữ', 'Buy and hold'), pct(s.buy_hold_return_pct),
      s.buy_hold_return_pct > 0 ? 'pos' : 'neg');

    /* The ranked table cannot tell a genuine optimum from a lucky cell, and it
       cannot tell whether the winner's Sharpe beats the best of this many coin
       flips. These two cards are the whole point of running a sweep. */
    const rb = s.robustness || {};
    if (rb.available) {
      html += metricCard(L('Độ bền tham số', 'Parameter robustness'),
        { plateau: L('Cao nguyên', 'Plateau'), ridge: L('Sườn dốc', 'Ridge'),
          spike: L('Đỉnh nhọn', 'Spike') }[rb.code],
        rb.code === 'plateau' ? 'pos' : rb.code === 'spike' ? 'neg' : '',
        L(`lân cận ở bách phân vị ${rb.neighbour_median_percentile.toFixed(0)}`,
          `neighbours at percentile ${rb.neighbour_median_percentile.toFixed(0)}`),
        robustnessExplain(rb));
    }
    const dfl = s.deflated || {};
    if (dfl.available) {
      html += metricCard(L('Sharpe đã khử phồng', 'Deflated Sharpe'),
        `${(dfl.deflated_sharpe_ratio * 100).toFixed(1)}%`,
        dfl.code === 'survives' ? 'pos' : dfl.code === 'deflated_away' ? 'neg' : '',
        L(`sau ${dfl.trials} phép thử`, `after ${dfl.trials} trials`),
        deflatedExplain(dfl));
    }
    html += '</div>';

    for (const block of [rb, dfl]) {
      if (!block.available || !block.verdict) continue;
      const tone = (block.code === 'plateau' || block.code === 'survives') ? 'good' : 'warn';
      html += `<div class="callout ${tone}">${emph(esc(tp(block.verdict)))}</div>`;
    }

    const paramNames = Object.keys(rows[0].params);
    html += '<table class="data-table"><thead><tr>';
    for (const n of paramNames) html += `<th>${esc(n)}</th>`;
    html += `<th>${esc(METRIC_LABELS[s.metric] || s.metric)}</th>
      <th>${esc(L('Lợi nhuận', 'Return'))}</th><th>MaxDD</th>
      <th>${esc(L('Thắng', 'Win'))}</th>
      <th>${esc(L('Lệnh', 'Trades'))}</th></tr></thead><tbody>`;

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

    const metricLabel = METRIC_LABELS[s.metric] || s.metric;
    html += `<p class="table-note">${esc(L(
      `Hàng đầu là tổ hợp tốt nhất theo ${metricLabel}. Nhấn một hàng để nạp tham số đó vào bảng bên trái.`,
      `The top row is the best combination by ${metricLabel}. Click a row to load those parameters into the panel on the left.`))}</p>`;

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
    // Costs are chosen in the paper dialog rather than inherited from the
    // backtest panel: a paper session runs forward on live data for days, and
    // the fee it trades at should not change because someone was exploring a
    // backtest. The dialog opens pre-filled and can copy the backtest's values
    // deliberately, which is the difference that matters.
    return Paper.openSettings({
      strategyId: current.id,
      symbol: ctx.symbol,
      timeframe: ctx.timeframe,
      params,
    });
  }

  function init(config) {
    elements = config.elements;
    context = config.context;
    onResult = config.onResult;
    onChange = config.onChange || (() => {});

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
    init, load, runBacktest, runOptimize, startPaper, snapshot, restore,
    // Exported so tests/test_render.js can drive the optimiser panel without
    // standing up a server: the panel is where the sweep's two most important
    // verdicts are shown, and nothing else checks that they render.
    renderOptimize,
    // Exposed so validation and comparison reuse exactly the parameters and
    // costs the backtest just used, rather than assembling their own.
    execution,
    // Validation and the statistics panel run over the same window the
    // backtest does; a walk-forward on a different period than the backtest it
    // is validating would be answering a different question.
    period,
    sweepRanges: enabledRanges,
    currentParams: () => ({ ...params }),
    get catalog() { return catalog; },
    get selected() { return current; },
    get lastResult() { return lastBacktest; },
    // How many parameter combinations were tried to reach the current values.
    get lastTrials() { return lastTrials; },
    rerender: renderParams,
  };
})();
