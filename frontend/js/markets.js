/* One strategy, several markets.

   The table this produces is the part people ask for and the least useful
   part of the answer. Running a strategy over twenty symbols and keeping the
   best is a search, and a search's winner is flattered by the search itself —
   so the summary leads with how many markets worked and what the median did,
   and the winner's Sharpe is shown already deflated by the number of markets
   scanned. The backend computes all of it (backend/strategy/multi.py); this
   module's job is to not bury it under the ranking.

   The timeframe is deliberately not a control here. It follows the chart, so
   what gets tested is what is on screen — one less setting to disagree with
   what the user is looking at. */

const Markets = (() => {
  let elements = {};
  let onToast = () => {};
  let chosen = [];            // symbol ids, in the order they were added
  let lastResult = null;
  let showOutput = () => {};

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

  const num = (v, digits = 2) => Fmt.number(v, digits, digits);
  const pct = (v, digits = 2) => Fmt.upct(v, digits);
  const sign = (v) => (typeof v !== 'number' ? '' : v > 0 ? 'pos' : v < 0 ? 'neg' : '');

  function context() {
    return elements.context ? elements.context() : { symbol: null, timeframe: null };
  }

  // ---------- the chosen list ----------

  function add(symbol) {
    if (!symbol || chosen.includes(symbol)) return;
    chosen.push(symbol);
    renderChosen();
  }

  function remove(symbol) {
    chosen = chosen.filter((s) => s !== symbol);
    renderChosen();
  }

  function renderChosen() {
    if (!elements.chosen) return;
    elements.chosen.innerHTML = chosen.map((symbol) => `
      <span class="mm-chip">
        ${Paper.symbolBadge(symbol)}
        <span class="mm-chip-name">${esc(symbol)}</span>
        <button type="button" class="mm-chip-x" data-remove="${esc(symbol)}"
                title="${esc(t('mm.remove'))}" aria-label="${esc(t('mm.remove'))}">×</button>
      </span>`).join('');

    for (const button of elements.chosen.querySelectorAll('[data-remove]')) {
      button.addEventListener('click', () => remove(button.dataset.remove));
    }

    if (elements.run) {
      elements.run.disabled = chosen.length < 2;
      elements.run.textContent = t('mm.run', { n: chosen.length });
    }
    refreshTimeframeNote();
  }

  /** Say which timeframe will be used, since it is taken rather than chosen. */
  function refreshTimeframeNote() {
    if (!elements.note) return;
    const tf = context().timeframe;
    elements.note.textContent = tf ? t('mm.usingTimeframe', { tf }) : '';
  }

  /** Fill the add-a-market dropdown from whatever the picker already knows. */
  function setOptions(groups) {
    if (!elements.add) return;
    const current = elements.add.value;
    elements.add.innerHTML = '<option value=""></option>' + groups.map((group) =>
      `<optgroup label="${esc(group.label)}">` +
      group.options.map((o) => `<option value="${esc(o.id)}">${esc(o.text)}</option>`).join('') +
      '</optgroup>').join('');
    if (current) elements.add.value = current;
  }

  // ---------- running ----------

  async function run() {
    if (chosen.length < 2) return;
    const { timeframe } = context();

    /* Show where the answer will appear before asking for it.

       The run button lives in the Strategy panel and the table is drawn into
       the Results panel. Nothing switched between them, so a run that
       succeeded in three seconds looked exactly like a button that did
       nothing — the output was being written into a panel nobody could see.
       Measured: the endpoint returned 200 with all three markets while the
       screen stayed unchanged. */
    showOutput();

    elements.output.innerHTML = `<p class="empty">${esc(
      t('mm.running', { n: chosen.length }))}</p>`;

    try {
      lastResult = await API.backtestMarkets({
        strategyId: Strategy.selected?.id,
        symbols: chosen,
        timeframe,
        params: Strategy.currentParams(),
        execution: Strategy.execution(),
        ...Strategy.period(),
      });
    } catch (err) {
      elements.output.innerHTML =
        `<div class="callout bad">${esc(err.message)}</div>`;
      onToast(err.message, true);
      return;
    }
    render();
  }

  function render() {
    const r = lastResult;
    if (!r) return;

    if (!r.markets) {
      elements.output.innerHTML = `<div class="callout bad">${esc(
        tp(r.note) || '')}</div>${failedList(r)}`;
      return;
    }

    let html = '';

    /* Breadth first, deliberately above the table.

       "Best market returned 407%" and "three of six markets made money" are
       both true of the same run, and only the second one is a statement about
       the strategy. */
    html += '<div class="stat-cards">';
    html += card(t('mm.profitable'),
      `${r.profitable_markets ?? '—'}/${r.markets}`,
      r.profitable_markets > r.markets / 2 ? 'pos' : 'neg');
    html += card(t('mm.medianReturn'), pct(r.median_return_pct),
      sign(r.median_return_pct));
    html += card(t('mm.medianSharpe'), num(r.median_sharpe, 3),
      sign(r.median_sharpe));
    html += card(t('mm.best'), `${esc(r.best_symbol || '—')}`, '',
      pct(r.best_return_pct));
    html += '</div>';

    html += deflatedBlock(r);
    html += comparabilityBlock(r);

    html += `<table class="data-table stat-table"><thead><tr>
      <th>${esc(L('Thị trường', 'Market'))}</th>
      <th>${esc(L('Nến', 'Bars'))}</th>
      <th>Sharpe</th>
      <th>${esc(L('Lợi nhuận', 'Return'))}</th>
      <th>${esc(L('Sụt giảm', 'Drawdown'))}</th>
      <th>${esc(L('Lệnh', 'Trades'))}</th>
      <th>${esc(L('Thắng', 'Win rate'))}</th>
      </tr></thead><tbody>`;
    for (const row of r.rows) {
      const m = row.metrics || {};
      html += `<tr>
        <td>${Paper.symbolBadge(row.symbol)} ${esc(row.symbol)}</td>
        <td class="muted">${esc(String(row.bars ?? '—'))}</td>
        <td class="${sign(m.sharpe)}">${num(m.sharpe, 3)}</td>
        <td class="${sign(m.total_return_pct)}">${pct(m.total_return_pct)}</td>
        <td class="neg">${pct(m.max_drawdown_pct)}</td>
        <td class="muted">${esc(String(m.num_trades ?? '—'))}</td>
        <td class="muted">${pct(m.win_rate_pct, 0)}</td>
      </tr>`;
    }
    html += '</tbody></table>';
    html += failedList(r);

    elements.output.innerHTML = html;
  }

  function card(label, value, klass = '', sub = '') {
    return `<div class="metric">
      <div class="metric-label">${esc(label)}</div>
      <div class="metric-value ${klass}">${value}</div>
      ${sub ? `<div class="metric-sub">${esc(sub)}</div>` : ''}
    </div>`;
  }

  function deflatedBlock(r) {
    const d = r.deflated || {};
    if (!d.available) {
      return d.reason ? `<div class="callout">${emph(esc(tp(d.reason)))}</div>` : '';
    }
    const tests = d.tests || {};
    const dsr = tests.deflated_sharpe_ratio;
    const passed = tests.dsr_significant;
    return `<div class="callout ${passed ? '' : 'warn'}">
      <strong>${esc(L('Sharpe khử phồng', 'Deflated Sharpe'))}:</strong>
      ${typeof dsr === 'number' ? `${(dsr * 100).toFixed(1)}%` : '—'}
      ${passed ? '' : ` — ${esc(L('chưa đạt ngưỡng', 'below the threshold'))}`}
      <br>${emph(esc(tp(d.note)))}
    </div>`;
  }

  function comparabilityBlock(r) {
    const c = r.comparability || {};
    if (c.comparable || !c.note) return '';
    return `<div class="callout warn">${emph(esc(tp(c.note)))}</div>`;
  }

  function failedList(r) {
    if (!r.failed?.length) return '';
    return `<div class="callout warn"><strong>${esc(t('mm.failedMarkets'))}:</strong><br>` +
      // A market can fail with a {vi, en} pair (missing contract settings) or
      // with a plain message from the data layer.
      r.failed.map((f) => `${esc(f.symbol)} — ${esc(typeof f.error === 'object' ? tp(f.error) : f.error)}`).join('<br>') +
      '</div>';
  }

  // ---------- wiring ----------

  function init(config) {
    elements = config.elements || {};
    onToast = config.onToast || (() => {});
    showOutput = config.onShowOutput || (() => {});
    elements.context = config.context;

    elements.add?.addEventListener('change', () => {
      add(elements.add.value);
      elements.add.value = '';
    });
    elements.addCurrent?.addEventListener('click', () => {
      const { symbol } = context();
      if (symbol) add(symbol);
    });
    elements.run?.addEventListener('click', () =>
      config.withButton(elements.run, t('mm.running', { n: chosen.length }), run));

    I18n.onChange(() => { renderChosen(); if (lastResult) render(); });
    renderChosen();
  }

  return { init, setOptions, add, refreshTimeframeNote, get chosen() { return [...chosen]; } };
})();
