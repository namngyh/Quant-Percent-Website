/* Does the validation panel actually render?
 *
 * Every other test in this directory checks a number. None of them checks that
 * the number reaches the screen, and that is where the worst bug of this
 * project so far lived: the statistics panel called `.startsWith()` on a
 * bilingual `{vi, en}` object, the request returned 200, the console stayed
 * silent, and the panel printed nothing useful. Nothing automated noticed.
 *
 * This drives the real Validation module under jsdom with only the network
 * stubbed, renders each panel in both languages, and fails on "[object
 * Object]", "undefined", "NaN", "null" and "Infinity" reaching the text, on a
 * panel rendering empty, and on the new content being absent.
 *
 *   npm install --no-save jsdom
 *   .venv/Scripts/python.exe tests/render_payloads.py     # writes the fixtures
 *   NODE_PATH=./node_modules node tests/test_render.js
 *
 * The fixtures come from the real engine on a synthetic random walk, so this
 * needs no database and no running server.
 */
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const ROOT = process.cwd();
const FIXTURES = path.join(ROOT, 'tests');
const payloads = JSON.parse(fs.readFileSync(path.join(FIXTURES, 'render_payloads.json'), 'utf8'));

const dom = new JSDOM(fs.readFileSync(path.join(ROOT, 'frontend/index.html'), 'utf8'),
  { url: 'http://localhost/', runScripts: 'outside-only' });
const { window } = dom;
global.window = window;
global.document = window.document;

/* One eval for all four files plus the stub: each file declares its module
   with `const`, and separate evals do not share a lexical scope. */
const sources = ['i18n.js', 'settings.js', 'explain.js', 'api.js', 'validation.js', 'strategy.js',
  'paper.js', 'report.js', 'portfolio.js']
  .map((f) => fs.readFileSync(path.join(ROOT, 'frontend/js', f), 'utf8'));
let nextPayload = null;
window.eval(sources.join(String.fromCharCode(10, 59, 10)) + `
  ;window.I18n = I18n; window.Explain = Explain; window.Validation = Validation;
  window.Settings = Settings; window.Fmt = Fmt;
  window.Strategy = Strategy; window.Paper = Paper; window.Report = Report; window.Portfolio = Portfolio;
  window.API = API;
  // Only the network is stubbed; everything downstream is the real module.
  API.walkForward = (a) => window.__wf(a);
  API.monteCarlo = (a) => window.__mc(a);
`);
window.__wf = async () => nextPayload;
window.__mc = async () => nextPayload;

const $ = (id) => window.document.getElementById(id);
window.Validation.init({
  elements: {
    strategySelect: { value: 'example_ema_cross' },
    metric: { value: 'sharpe' },
    trainBars: $('wf-train'), testBars: $('wf-test'),
    purgeBars: $('wf-purge'), foldMode: $('wf-fold-mode'),
    simulations: $('mc-sims'),
    output: $('validation-output'), stats: $('stats-output'),
  },
  context: () => ({ symbol: 'BTCUSDT', timeframe: '1h', limit: 6000 }),
  execution: () => ({}),
  catalog: () => [],
  onToast: () => {},
});

const BAD = [
  ['[object Object]', /\[object Object\]/],
  ['undefined',       /(^|[>\s])undefined([<\s.,%]|$)/],
  ['NaN',             /(^|[>\s(])NaN([<\s.,%)]|$)/],
  ['null',            /(^|[>\s])null([<\s.,%]|$)/],
  ['Infinity',        /Infinity/],
];

let failures = 0;
async function render(label, kind, payload) {
  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    nextPayload = payload;
    $('validation-output').innerHTML = '';
    try {
      if (kind === 'wf') await window.Validation.runWalkForward([]);
      else await window.Validation.runMonteCarlo({});
    } catch (err) {
      console.log(`  FAIL  ${label} [${lang}] threw: ${err.message}`);
      failures++; continue;
    }
    const html = $('validation-output').innerHTML;
    if (!html.trim()) { console.log(`  FAIL  ${label} [${lang}] rendered nothing`); failures++; continue; }
    const text = $('validation-output').textContent;
    const hits = BAD.filter(([, re]) => re.test(text)).map(([n]) => n);
    if (hits.length) {
      console.log(`  FAIL  ${label} [${lang}] printed: ${hits.join(', ')}`);
      for (const [, re] of BAD) {
        const m = text.match(new RegExp('.{0,60}' + re.source + '.{0,60}'));
        if (m) console.log(`          ...${m[0].replace(/\s+/g, ' ')}...`);
      }
      failures++; continue;
    }
    console.log(`  PASS  ${label} [${lang}]  ${text.length} chars`);
  }
}

(async () => {
  await render('walk-forward rolling',   'wf', payloads.wf_rolling);
  await render('walk-forward anchored',  'wf', payloads.wf_anchored);
  await render('walk-forward ratio',     'wf', payloads.wf_ratio);
  await render('walk-forward inverted',  'wf', payloads.wf_inverted);
  await render('monte carlo',            'mc', payloads.mc);

  // The three efficiency states must each produce their own wording.
  for (const [name, want] of [['wf_ratio', 'ratio'], ['wf_inverted', 'inverted'],
                              ['wf_rolling', 'no_is_edge']]) {
    window.I18n.set('en');
    nextPayload = payloads[name];
    await window.Validation.runWalkForward([]);
    const text = $('validation-output').textContent;
    const shown = /Inverted/.test(text) ? 'inverted'
      : /no in-sample edge for anything/.test(text) ? 'no_is_edge' : 'ratio';
    if (shown !== want) { console.log(`  FAIL  ${name}: card showed ${shown}, wanted ${want}`); failures++; }
    else console.log(`  PASS  ${name}: card shows ${want}`);
  }

  // Both explain entries must open, and must differ between languages.
  for (const id of ['wf.purge', 'wf.foldMode']) {
    window.I18n.set('vi'); const vi = window.Explain.get(id);
    window.I18n.set('en'); const en = window.Explain.get(id);
    if (!vi || !en) { console.log(`  FAIL  ${id}: no entry`); failures++; }
    else if (vi.what === en.what) { console.log(`  FAIL  ${id}: same text in both languages`); failures++; }
    else console.log(`  PASS  ${id}: bilingual entry resolves`);
  }

  /* "No NaN anywhere" would also pass on the old layout. These assert that the
     new content is actually on the page. */
  const present = async (label, kind, payload, lang, checks) => {
    window.I18n.set(lang);
    nextPayload = payload;
    if (kind === 'wf') await window.Validation.runWalkForward([]);
    else await window.Validation.runMonteCarlo({});
    const el = $('validation-output');
    for (const [what, test] of checks) {
      const ok = typeof test === 'string' && test.startsWith('sel:')
        ? el.querySelector(test.slice(4)) !== null
        : test instanceof RegExp ? test.test(el.textContent)
        : typeof test === 'function' ? test(el)
        : el.textContent.includes(test);
      if (ok) console.log(`  PASS  ${label}: ${what}`);
      else { console.log(`  FAIL  ${label}: ${what} missing`); failures++; }
    }
  };

  await present('wf anchored [en]', 'wf', payloads.wf_anchored, 'en', [
    ['in/out-of-sample bar',        'sel:.pf-bars .pf-bar.risk'],
    ['bar labels',                  'sel:.pf-bar-label'],
    ['parameter stability table',   'Coeff. of variation'],
    ['normalised fold column',      '(normalised)'],
    ['anchored named in the note',  /anchored \(expanding window\)/],
    ['purge named in the note',     /drops 200 purged bars/],
    ['both swept parameters as columns',
      (el) => /fast/.test(el.textContent) && /slow/.test(el.textContent)],
    ['one table row per fold',
      (el) => el.querySelectorAll('table.data-table tbody tr').length >=
              payloads.wf_anchored.folds.length],
  ]);

  await present('wf rolling [vi]', 'wf', payloads.wf_rolling, 'vi', [
    ['rolling named in the note',   /trượt \(cửa sổ cố định\)/],
    ['no purge clause when purge is 0', (el) => !/nến cách ly/.test(el.textContent)],
  ]);

  // renderOptimize writes into elements.optimize, so Strategy needs its wiring.
  window.Strategy.init({
    elements: {
      select: $('strategy-select'), mode: $('opt-mode'),
      samples: $('opt-samples'), samplesRow: $('opt-samples-row'),
      optimize: $('optimize-results'),
      // The real cost inputs, so execution() can be read as the app builds it.
      capital: $('exec-capital'), size: $('exec-size'), leverage: $('exec-leverage'),
      fee: $('exec-fee'), slippage: $('exec-slippage'),
    },
    context: () => ({ symbol: 'BTCUSDT', timeframe: '1h', limit: 6000 }),
    onResult: () => {},
  });

  const optimiser = async (lang, checks) => {
    window.I18n.set(lang);
    const el = $('optimize-results');
    el.innerHTML = '';
    try {
      window.Strategy.renderOptimize(payloads.opt);
    } catch (err) {
      console.log(`  FAIL  optimiser [${lang}] threw: ${err.message}`);
      failures++; return;
    }
    const text = el.textContent;
    const hits = BAD.filter(([, re]) => re.test(text)).map(([n2]) => n2);
    if (hits.length) {
      console.log(`  FAIL  optimiser [${lang}] printed: ${hits.join(', ')}`);
      failures++; return;
    }
    for (const [what, test] of checks) {
      const ok = typeof test === 'string' && test.startsWith('sel:')
        ? el.querySelector(test.slice(4)) !== null
        : test instanceof RegExp ? test.test(text) : text.includes(test);
      if (ok) console.log(`  PASS  optimiser [${lang}]: ${what}`);
      else { console.log(`  FAIL  optimiser [${lang}]: ${what} missing`); failures++; }
    }
  };
  await optimiser('vi', [
    ['thẻ độ bền tham số', 'Độ bền tham số'],
    ['thẻ Sharpe khử phồng', 'Sharpe đã khử phồng'],
    ['kết luận cao nguyên/sườn/đỉnh', /Cao nguyên|Sườn dốc|Đỉnh nhọn/],
    ['có nút giải thích', 'sel:.metric-label .info-btn'],
    ['có callout kết luận', 'sel:.callout'],
  ]);
  await optimiser('en', [
    ['robustness card', 'Parameter robustness'],
    ['deflated Sharpe card', 'Deflated Sharpe'],
    ['a verdict word', /Plateau|Ridge|Spike/],
    ['trial count named', /after \d+ trials/],
    ['table headers translated', 'Return'],
    ['no Vietnamese left in the panel', (() => true)()
      ? /^(?!.*Lợi nhuận).*$/s : /x/],
  ]);

  await present('monte carlo [en]', 'mc', payloads.mc, 'en', [
    ['fan chart',                   'sel:svg.mc-fan'],
    ['two-resampler section',       'Two resamplers'],
    ['block resampler named',       /[Bb]lock/],
    ['independent resampler named', /[Ii]ndependent|IID/],
    ['a probability carries its simulation error', /±|\+\/-/],
  ]);
  // ---------- Paper trading settings ----------

  const psel = (id) => window.document.getElementById(id);
  const openedSessions = [];
  window.Paper.init({
    elements: {
      list: psel('paper-sessions'), refresh: psel('refresh-paper'),
      onOpenSession: (session) => openedSessions.push(session.id),
      settings: {
        root: psel('paper-settings'), close: psel('paper-settings-close'),
        preset: psel('ps-preset'), capital: psel('ps-capital'),
        currency: psel('ps-currency'),
        size: psel('ps-size'), leverage: psel('ps-leverage'),
        fee: psel('ps-fee'), slippage: psel('ps-slippage'),
        summary: psel('ps-summary'), warning: psel('ps-warning'),
        start: psel('ps-start'), copy: psel('ps-copy'),
      },
      backtestExecution: () => ({ initial_capital: 25000, size_pct: 0.5,
                                  leverage: 3, fee: 0.0007, slippage: 0.0003 }),
    },
    onToast: () => {},
  });

  const expect = (what, ok) => {
    if (ok) console.log(`  PASS  paper settings: ${what}`);
    else { console.log(`  FAIL  paper settings: ${what}`); failures++; }
  };

  // Opening the dialog must not start a session.
  let started = false;
  window.API.paperStart = async () => { started = true; return { id: 'x' }; };
  window.Paper.openSettings({ strategyId: 'example_ema_cross', symbol: 'BTCUSDT',
                              timeframe: '1h', params: {} });
  expect('opening the dialog does not start a session', started === false);
  expect('the dialog becomes visible', psel('paper-settings').hidden === false);

  // The venue list follows the market the session will open on.
  expect('crypto offers the Binance venues',
         JSON.stringify(window.Paper.venuesFor('BTCUSDT'))
           === JSON.stringify(['binance_futures_taker', 'binance_futures_maker', 'binance_spot']));
  expect('a VN equity offers only HOSE',
         JSON.stringify(window.Paper.venuesFor('VN:VIC')) === JSON.stringify(['hose']));
  expect('a VN30F contract offers only the derivatives venue',
         JSON.stringify(window.Paper.venuesFor('VN:VN30F1M')) === JSON.stringify(['vn_derivatives']));
  expect('no Binance venue is offered for a VN contract',
         !window.Paper.venuesFor('VN:VN30F1M').some((v) => v.startsWith('binance')));

  // Opening on a VN contract must not leave a Binance venue selected.
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'VN:VN30F1M',
                              timeframe: '1m', params: {} });
  expect('opening on VN30F1M selects the derivatives venue',
         psel('ps-preset').value === 'vn_derivatives');
  expect('a single-venue market does not pretend to offer a choice',
         psel('ps-preset').disabled === true);
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'BTCUSDT',
                              timeframe: '1m', params: {} });
  expect('opening on crypto re-enables the choice',
         psel('ps-preset').disabled === false);

  // Hand-typed costs must not follow you into another market.
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'BTCUSDT',
                              timeframe: '1m', params: {} });
  psel('ps-fee').value = '0.99';
  psel('ps-fee').dispatchEvent(new window.Event('input'));
  expect('hand editing marks the venue custom', psel('ps-preset').value === 'custom');
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'VN:VIC',
                              timeframe: '1d', params: {} });
  expect('a different market does not inherit the previous custom costs',
         psel('ps-preset').value === 'hose' && Number(psel('ps-fee').value) === 0.15);

  // The account currency follows the venue.
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'BTCUSDT',
                              timeframe: '1m', params: {} });
  expect('a crypto account is denominated in USDT',
         psel('ps-currency').textContent === 'USDT');
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'VN:VIC',
                              timeframe: '1d', params: {} });
  expect('a HOSE account is denominated in VND',
         psel('ps-currency').textContent === 'VND');
  expect('currencyFor agrees with the dialog',
         window.Paper.currencyFor('VN:VN30F1M') === 'VND'
           && window.Paper.currencyFor('BTCUSDT') === 'USDT');

  // A venue preset fills the fee in. Back on crypto, where spot is offered.
  window.I18n.set('en');
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'BTCUSDT',
                              timeframe: '1m', params: {} });
  psel('ps-preset').value = 'binance_spot';
  psel('ps-preset').dispatchEvent(new window.Event('change'));
  expect('a preset sets the fee', Number(psel('ps-fee').value) === 0.1);
  expect('a preset explains itself', /Spot fee of 0\.1%/.test(psel('ps-warning').textContent));

  // The round-trip cost is what a trade really pays, not the headline fee.
  psel('ps-capital').value = '10000';
  psel('ps-size').value = '100';
  psel('ps-leverage').value = '1';
  psel('ps-fee').value = '0.04';
  psel('ps-slippage').value = '0.02';
  psel('ps-fee').dispatchEvent(new window.Event('input'));
  const summary = psel('ps-summary').textContent;
  expect('round-trip cost is shown, not just the fee', /0\.120%/.test(summary));
  expect('the cost is also given in money', /\b120\b/.test(summary));
  expect('hand editing a fee switches the preset to custom',
         psel('ps-preset').value === 'custom');

  // High leverage warns about the liquidation model the engine actually uses.
  psel('ps-leverage').value = '20';
  psel('ps-leverage').dispatchEvent(new window.Event('input'));
  expect('high leverage warns about intrabar liquidation',
         /5\.0%/.test(psel('ps-warning').textContent)
         && /low, not its close/.test(psel('ps-warning').textContent));

  // Copying from the backtest is deliberate, and marks the preset custom.
  psel('ps-copy').dispatchEvent(new window.Event('click'));
  expect('copy from backtest brings the capital across',
         Number(psel('ps-capital').value) === 25000);
  expect('copy from backtest converts the fee to a percentage',
         Math.abs(Number(psel('ps-fee').value) - 0.07) < 1e-9);

  // Starting sends exactly what the dialog shows, in engine units.
  let sent = null;
  window.API.paperStart = async (req) => { sent = req; return { id: 'x', status: 'running' }; };
  psel('ps-start').dispatchEvent(new window.Event('click'));
  await new Promise((r) => setTimeout(r, 0));
  expect('starting sends the dialog values, not the backtest panel values',
         sent && sent.execution.initial_capital === 25000
         && Math.abs(sent.execution.fee - 0.0007) < 1e-12
         && Math.abs(sent.execution.size_pct - 0.5) < 1e-12);
  expect('the dialog closes after starting', psel('paper-settings').hidden === true);

  // And the whole dialog is bilingual.
  // The venue list is filtered by symbol now, so reach HOSE the way a user
  // does: by opening the dialog on a HOSE symbol.
  window.I18n.set('vi');
  window.Paper.openSettings({ strategyId: 'manual', symbol: 'VN:VIC',
                              timeframe: '1d', params: {} });
  const vi = psel('ps-warning').textContent;
  window.I18n.set('en');
  psel('ps-preset').dispatchEvent(new window.Event('change'));
  expect('venue notes are bilingual', vi !== psel('ps-warning').textContent && vi.length > 0);
  expect('a HOSE session is told it cannot short',
         /cannot be sold short/.test(psel('ps-warning').textContent));

  // ---------- Report tabs ----------
  //
  // Six tabs, each a few hundred numbers, in two languages. Rendering them all
  // is the cheapest way to catch a metric the backend renamed or dropped:
  // report.js reads `b.avg_bars_win` and friends by name, and a missing key
  // reaches the screen as "undefined" with no error anywhere.

  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    for (const [id] of window.Report.tabs) {
      // The ML tab only has content for a strategy that scores probabilities,
      // so it is rendered from the report that has one. Reading it out of the
      // plain report would check the "no model here" notice instead of the
      // several dozen numbers this loop exists to check.
      const payload = id === 'ml' ? payloads.report_ml : payloads.report;
      let html;
      try {
        html = window.Report.renderTab(id, payload);
      } catch (err) {
        console.log(`  FAIL  report ${id} [${lang}] threw: ${err.message}`);
        failures++; continue;
      }
      const holder = window.document.createElement('div');
      holder.innerHTML = html;
      const text = holder.textContent;
      const hits = BAD.filter(([, re]) => re.test(text)).map(([nm]) => nm);
      if (hits.length) {
        console.log(`  FAIL  report ${id} [${lang}] printed: ${hits.join(', ')}`);
        for (const [, re] of BAD) {
          const m = text.match(new RegExp('.{0,70}' + re.source + '.{0,70}'));
          if (m) console.log(`          ...${m[0].replace(/\s+/g, ' ')}...`);
        }
        failures++; continue;
      }
      if (!text.trim()) {
        console.log(`  FAIL  report ${id} [${lang}] rendered empty`);
        failures++; continue;
      }
      console.log(`  PASS  report ${id} [${lang}]  ${text.length} chars`);
    }
  }

  /* The ML tab belongs to ML strategies only.
     Nam asked for that, and the reason it matters is that the previous
     behaviour did not look broken: a moving-average cross got a full tab of
     dashes and repeated Overview numbers, which reads as a result. */
  window.I18n.set('en');
  {
    const withMl = payloads.report_ml;
    const noMl = payloads.report;

    const shown = window.Report.tabsFor(withMl);
    const hidden = window.Report.tabsFor(noMl);

    if (shown.includes('ml')) console.log('  PASS  ML tab offered when the strategy scores probabilities');
    else { console.log('  FAIL  ML tab missing for an ML strategy'); failures++; }

    if (!hidden.includes('ml')) console.log('  PASS  ML tab withheld when there is no probability');
    else { console.log('  FAIL  ML tab still offered without a probability'); failures++; }

    // The other tabs must not disappear with it: gating one tab is not a
    // reason to lose the report.
    const lost = shown.filter((id) => id !== 'ml' && !hidden.includes(id));
    if (!lost.length) console.log(`  PASS  the other ${hidden.length} tabs survive the gating`);
    else { console.log(`  FAIL  gating the ML tab also dropped: ${lost.join(', ')}`); failures++; }

    // And rendering it anyway says why it is empty rather than throwing.
    try {
      const text = window.Report.renderTab('ml', noMl);
      if (/machine-learning/i.test(text)) console.log('  PASS  rendering the ML tab without a model explains itself');
      else { console.log('  FAIL  ML tab without a model gave no explanation'); failures++; }
    } catch (err) {
      console.log(`  FAIL  ML tab without a model threw: ${err.message}`);
      failures++;
    }
  }

  /* Portfolio performance tab: the 16 metrics Nam listed reach the screen,
     and every refusal is printed as its reason rather than a bare dash. */
  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    for (const [label, payload] of [['numbers', payloads.portfolio],
                                    ['refusals', payloads.portfolio_refusals]]) {
      let html;
      try { html = window.Portfolio.renderTab('performance', payload); } catch (err) {
        console.log(`  FAIL  portfolio performance ${label} [${lang}] threw: ${err.message}`);
        failures++; continue;
      }
      const holder = window.document.createElement('div');
      holder.innerHTML = html;
      const hits = BAD.filter(([, re]) => re.test(holder.textContent)).map(([n]) => n);
      if (hits.length) {
        console.log(`  FAIL  portfolio performance ${label} [${lang}] printed: ${hits.join(', ')}`);
        failures++;
      } else console.log(`  PASS  portfolio performance ${label} [${lang}]  ${holder.textContent.length} chars`);
    }
  }
  window.I18n.set('en');
  {
    const text = (payload) => {
      const holder = window.document.createElement('div');
      holder.innerHTML = window.Portfolio.renderTab('performance', payload);
      return holder.textContent;
    };
    const full = text(payloads.portfolio);
    for (const needle of ['CAGR', 'Sharpe', 'Sortino', 'Calmar', 'Information ratio',
      'Alpha', 'Beta', 'Upside capture', 'Downside capture', 'Skewness',
      'Excess kurtosis', 'Rolling Sharpe', 'Rolling volatility']) {
      if (full.includes(needle)) console.log(`  PASS  portfolio metric shown: ${needle}`);
      else { console.log(`  FAIL  portfolio metric missing: ${needle}`); failures++; }
    }
    const refused = text(payloads.portfolio_refusals);
    for (const [what, needle] of [
      ['Sortino refusal names its reason', 'no losing session in this window'],
      ['Calmar refusal names its reason', 'no real drawdown to divide by yet'],
      ['absent benchmark is said, not zeroed', 'not enough sessions shared with VN-Index'],
      ['short sample refuses the rolling window', 'A rolling window needs at least'],
      ['a series that never moves refuses the moments', 'the series does not move'],
    ]) {
      if (refused.includes(needle)) console.log(`  PASS  portfolio: ${what}`);
      else { console.log(`  FAIL  portfolio: ${what}`); failures++; }
    }
  }

  // The AmiBroker rows and the risk-management tab specifically.
  const ami = window.Report.renderTab('trades', payloads.report);
  for (const [what, needle] of [
    ['longest hold row', 'Longest hold'],
    ['total bars in trades row', 'Total bars in trades'],
    ['return dispersion row', 'Return dispersion'],
    ['intra-trade drawdown row', 'Worst intra-trade drawdown'],
    ['largest win / largest loss row', 'Largest win / largest loss'],
    ['exit reasons line', 'Exit reasons:'],
  ]) {
    if (ami.includes(needle)) console.log(`  PASS  AmiBroker rows: ${what}`);
    else { console.log(`  FAIL  AmiBroker rows: ${what} missing`); failures++; }
  }

  const rtool = window.Report.renderTab('risktools', payloads.report);
  for (const [what, needle] of [
    ['VaR/CVaR table', 'CVaR'],
    ['Cornish-Fisher column', 'Cornish'],
    ['tail observation count', 'Tail observations'],
    ['confidence interval column', '95% interval'],
    ['Kelly card', 'Kelly'],
    ['half Kelly card', 'Half Kelly'],
    ['suggested size card', 'Suggested size'],
    ['leverage ceiling card', 'Leverage ceiling'],
    ['leverage by level table', 'Adverse move'],
  ]) {
    if (rtool.includes(needle)) console.log(`  PASS  risk tools: ${what}`);
    else { console.log(`  FAIL  risk tools: ${what} missing`); failures++; }
  }

  // The team's own risk model, which arrives from a separate endpoint rather
  // than from the report payload.
  window.Report.setMarketRisk({
    available: true,
    symbol: 'VNINDEX',
    latest: {
      time: 1788940800000,
      var_95_pct: -9.353, es_95_pct: -11.796, volatility_pct: 17.972,
      current_drawdown_pct: -5.229, rolling_drawdown_60d_pct: -11.155,
      downside_probability_pct: 51.39, downside_sim_error_pct: 0.4998,
      risk_state: 'moderate', mc_paths: 10000,
    },
    snapshots: new Array(6).fill(null),
    distribution: [
      { loss_pct: -3, probability_pct: 75.26, sim_error_pct: 0.43 },
      { loss_pct: -10, probability_pct: 6.77, sim_error_pct: 0.25 },
    ],
    spacing_days: { median: 2, max: 29 },
  });
  const withRisk = window.Report.renderTab('risktools', payloads.report);
  for (const [what, needle] of [
    ['market risk heading names VNINDEX', 'VNINDEX'],
    ['VaR from the team model', '-9.35%'],
    ['simulation error beside the probability', '0.50'],
    ['path count stated', '10,000'],
    ['loss distribution row', '75.26%'],
    ['sparse-series warning', '29'],
  ]) {
    if (withRisk.includes(needle)) console.log(`  PASS  market risk: ${what}`);
    else { console.log(`  FAIL  market risk: ${what} missing`); failures++; }
  }

  // An absent or unreachable model must leave the rest of the tab intact
  // rather than taking the report down with it.
  window.Report.setMarketRisk({ available: false });
  const noRisk = window.Report.renderTab('risktools', payloads.report);
  if (!noRisk.includes('VNINDEX') && noRisk.includes('CVaR')) {
    console.log('  PASS  market risk: absent model degrades quietly');
  } else {
    console.log('  FAIL  market risk: absent model breaks the tab');
    failures++;
  }
  window.Report.setMarketRisk(null);

  // RAR/MDD sits next to CAR/MDD on the risk tab.
  const riskTabHtml = window.Report.renderTab('risk', payloads.report);
  if (riskTabHtml.includes('RAR/MDD')) console.log('  PASS  risk tab: RAR/MDD card');
  else { console.log('  FAIL  risk tab: RAR/MDD card missing'); failures++; }

  // ---------- Trade ticket ----------
  //
  // The one place a user's own money-shaped intention enters the system. A
  // ticket that renders the wrong price, or leaves Buy enabled while already
  // long, is worse than a wrong metric elsewhere.

  const fakeSession = (over) => Object.assign({
    id: 'sess1', strategy_id: 'manual', is_manual: true, manual_override: false,
    manual_orders: 0, symbol: 'BTCUSDT', timeframe: '1m', active: true,
    bars_seen: 42, position: 0, quantity: 0, entry_price: 0, entry_time: 0,
    last_price: 79616.01, last_closed_time: 1700000000, pending_signal: 0,
    realized_equity: 10000, unrealized_pnl: 0, equity: 10000, return_pct: 0,
    num_trades: 0, num_wins: 0, win_rate_pct: 0, realized_pnl: 0, trades: [],
    config: { initial_capital: 10000, size_pct: 1, leverage: 1,
              fee: 0.0004, slippage: 0.0002 },
  }, over);

  const tsay = (what, ok) => {
    if (ok) console.log(`  PASS  ticket: ${what}`);
    else { console.log(`  FAIL  ticket: ${what}`); failures++; }
  };

  window.I18n.set('en');
  let tk = window.Paper.ticket(fakeSession());
  tsay('shows the live price on both buttons',
       (tk.match(/79,616\.01/g) || []).length >= 2);
  tsay('buy and sell are both offered when flat',
       /data-order="long"/.test(tk) && /data-order="short"/.test(tk));
  tsay('close is disabled when there is no position',
       /data-order="close"[^>]*disabled/.test(tk));
  tsay('round-trip cost is stated on the ticket', /0\.120% of notional/.test(tk));

  tk = window.Paper.ticket(fakeSession({ position: 1 }));
  tsay('buy is disabled while already long', /data-order="long"[^>]*disabled/.test(tk));
  tsay('sell stays enabled while long, so a flip is one click',
       /data-order="short"(?![^>]*disabled)/.test(tk));
  tsay('close is enabled while holding',
       /data-order="close"(?![^>]*disabled)/.test(tk));

  tk = window.Paper.ticket(fakeSession({ position: -1 }));
  tsay('sell is disabled while already short', /data-order="short"[^>]*disabled/.test(tk));

  // Stop and target.
  tk = window.Paper.ticket(fakeSession());
  tsay('a flat ticket offers a stop and a target',
       /data-stop=/.test(tk) && /data-target=/.test(tk));
  tsay('a flat ticket does not offer to apply levels to nothing',
       !/data-apply-exits/.test(tk));

  tk = window.Paper.ticket(fakeSession({ position: 1, stop_loss: 78000, take_profit: 82000 }));
  tsay('an open position shows the levels it is carrying',
       /value="78000"/.test(tk) && /value="82000"/.test(tk));
  tsay('an open position can change them without reopening',
       /data-apply-exits/.test(tk));
  tsay('an unset level shows as empty, not as zero',
       /value=""/.test(window.Paper.ticket(fakeSession({ position: 1 }))));
  // A level dragged on the chart once reached this field as 1935.2365200241713.
  tk = window.Paper.ticket(fakeSession({ position: 1, stop_loss: 1935.2365200241713,
                                         take_profit: 0.123456789 }));
  tsay('a level with float noise shows to the cent',
       /value="1935\.24"/.test(tk) && /value="0\.123457"/.test(tk));

  tsay('a stopped session offers no ticket at all',
       window.Paper.ticket(fakeSession({ active: false })) === '');

  tk = window.Paper.ticket(fakeSession({ manual_override: true, is_manual: false,
                                         strategy_id: 'example_ema_cross' }));
  tsay('a strategy session under manual override offers to hand control back',
       /data-resume-strategy/.test(tk));
  tsay('a purely manual session does not offer that',
       !/data-resume-strategy/.test(window.Paper.ticket(fakeSession())));

  window.I18n.set('vi');
  const tkvi = window.Paper.ticket(fakeSession());
  tsay('the ticket is bilingual', /MUA/.test(tkvi) && /BÁN/.test(tkvi));

  // And nothing in it prints a placeholder.
  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    const holder = window.document.createElement('div');
    holder.innerHTML = window.Paper.ticket(fakeSession({ position: 1 }));
    const hits = BAD.filter(([, re]) => re.test(holder.textContent)).map(([nm]) => nm);
    tsay(`renders clean in ${lang}${hits.length ? ` (printed ${hits.join(', ')})` : ''}`,
         hits.length === 0);
  }

  // ---------- A session opens its chart ----------
  // A clean list: the settings checks above leave a stub session ({id:'x'},
  // no config) from their mocked start, which no real server ever returns.
  window.I18n.set('vi');
  window.API.paperSessions = async () => ({ sessions: [
    fakeSession({ id: 'open-me', position: 1, symbol: 'VN:VN30F1M', timeframe: '5m',
                  entry_price: 1939, quantity: 5, stop_loss: 1935, take_profit: 1944 }),
  ] });
  await window.Paper.refresh();
  const card = psel('paper-sessions').querySelector('[data-session-card="open-me"]');
  card.querySelector('.pp-title').click();
  tsay('clicking the session title opens its chart', openedSessions.join() === 'open-me');
  card.querySelector('.pp-fig').click();
  tsay('clicking its figures opens it too', openedSessions.length === 2);
  card.querySelector('input[data-stop]').click();
  tsay('clicking a field of its ticket does not', openedSessions.length === 2);
  card.querySelector('.pp-actions').click();
  tsay('clicking its action row does not', openedSessions.length === 2);

  // ---------- Contract model off ----------
  for (const [lang, word] of [['vi', 'hệ số nhân'], ['en', 'multiplier']]) {
    window.I18n.set(lang);
    tsay(`the results say the contract model is off [${lang}]`,
         window.Strategy.executionNote({ execution_model: 'contract_model_off' }).includes(word));
  }
  tsay('no note when the contract model ran or the symbol is linear',
       window.Strategy.executionNote({ execution_model: 'contract' }) === ''
         && window.Strategy.executionNote({ execution_model: 'linear' }) === '');
  window.I18n.set('vi');
  window.API.paperSessions = async () => ({ sessions: [
    fakeSession({ id: 'off', symbol: 'VN:VN30F1M', execution_model: 'contract_model_off' }),
  ] });
  await window.Paper.refresh();
  tsay('a paper session says the contract model is off',
       psel('paper-sessions').textContent.includes('hệ số nhân'));

  // ---------- A restated price series says so ----------
  for (const [lang, word] of [['vi', 'chia tách'], ['en', 'split']]) {
    window.I18n.set(lang);
    const note = window.Strategy.corporateNote({
      corporate_actions: [{ open_time: 0, ratio: 2, label: '2:1', kind: 'split' }],
    });
    tsay(`the results say the prices were adjusted [${lang}]`,
         note.includes(word) && note.includes('1'));
  }
  tsay('a series with no events says nothing',
       window.Strategy.corporateNote({ corporate_actions: [] }) === ''
         && window.Strategy.corporateNote({}) === '');
  window.I18n.set('vi');

  // ---------- Settings, and the one formatter ----------
  const S = window.Settings;
  const F = window.Fmt;
  S.reset();
  tsay('settings open at their documented defaults',
       S.all().display.profit === 'money' && S.all().display.timezone === 'vn'
         && S.all().display.decimals === 2);
  tsay('the timezone option is the only source of the display offset',
       S.tzOffsetSeconds() === 25200);
  S.patch({ display: { timezone: 'utc' } });
  tsay('UTC means no offset, and a patch keeps the settings it does not name',
       S.tzOffsetSeconds() === 0 && S.all().display.profit === 'money');
  S.patch({ display: { timezone: 'vn' } });

  let heard = 0;
  const unsubscribe = S.subscribe(() => { heard += 1; });
  S.patch({ chart: { grid: true } });
  unsubscribe();
  S.patch({ chart: { grid: false } });
  tsay('a subscriber hears the change it asked for and stops when told', heard === 1);

  // The contract block: nothing is guessed, so it travels only when complete.
  tsay('an incomplete contract block is not sent, and names what is missing',
       S.contractPayload() === null
         && S.contractMissing().join(',')
            === 'initial_margin_rate,maintenance_threshold,fee_per_contract');
  S.patch({ trading: { contract: {
    initial_margin_rate: 0.2, maintenance_threshold: 0.5, fee_per_contract: 20000 } } });
  tsay('a complete contract block goes out whole',
       S.contractMissing().length === 0
         && S.contractPayload().initial_margin_rate === 0.2
         && S.contractPayload().multiplier === 100000
         && S.contractPayload().fee_mode === 'per_contract');
  tsay('the strategy sends the contract block with its costs',
       window.Strategy.execution().contract.maintenance_threshold === 0.5);

  tsay('money, percent and points each read as themselves',
       F.money(1234567.5, { unit: 'VND' }) === '1,234,567.5 VND'
         && F.pct(3.769) === '+3.77%' && F.points(-10) === '-10');
  const figures = { money: 2940000, pct: 3.769, points: 10, unit: 'VND' };
  const shown = (mode) => { S.patch({ display: { profit: mode } }); return F.profit(figures); };
  tsay('the profit mode picks which figure is shown, and each carries its sign',
       shown('money') === '+2,940,000 VND' && shown('percent') === '+3.77%'
         && shown('points') === '+10');
  tsay('points fall back to money where there is no single instrument',
       F.profit({ money: 500, pct: 1, points: null, unit: 'USDT' }) === '+500 USDT');
  tsay('a balance is not a direction, so plain money stays unsigned',
       F.money(500, { unit: 'USDT' }) === '500 USDT');
  S.patch({ display: { profit: 'money', locale: 'vi-VN' } });
  tsay('the number format follows the chosen locale', F.number(1234.5).startsWith('1.234'));
  S.reset();

  // The panel writes straight through: a settings box with unsaved state is a
  // way to lose a change.
  window.Settings.panel(psel('settings-body'));
  const control = psel('settings-body').querySelector('[data-setting="display.profit"]');
  control.value = 'points';
  control.dispatchEvent(new window.Event('change', { bubbles: true }));
  tsay('changing a control writes the setting', S.all().display.profit === 'points');
  tsay('the panel says which contract settings are still missing',
       psel('settings-body').textContent.includes('ký quỹ'));
  S.reset();

  // ---------- Language purity ----------
  //
  // Every panel is bilingual by construction, but a string added in a hurry as
  // a bare Vietnamese literal renders identically in both languages and
  // nothing complains about it. Vietnamese carries diacritics that English
  // does not, so looking for them in the English render is an exact test.
  const VIET = /[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]/i;

  const pure = (label, html) => {
    const holder = window.document.createElement('div');
    holder.innerHTML = html;
    const bad = holder.textContent.split(/\s+/).filter((w) => VIET.test(w));
    if (!bad.length) { console.log(`  PASS  English is clean: ${label}`); return; }
    console.log(`  FAIL  Vietnamese leaked into English: ${label} -> ${
      [...new Set(bad)].slice(0, 10).join(' ')}`);
    failures++;
  };

  window.I18n.set('en');
  for (const [id] of window.Report.tabs) {
    pure(`report/${id}`,
         window.Report.renderTab(id, id === 'ml' ? payloads.report_ml : payloads.report));
  }
  pure('paper ticket', window.Paper.ticket(fakeSession({ position: 1 })));
  window.Settings.panel(psel('settings-body'));
  pure('settings panel', psel('settings-body').innerHTML);

  $('optimize-results').innerHTML = '';
  window.Strategy.renderOptimize(payloads.opt);
  pure('optimiser', $('optimize-results').innerHTML);

  nextPayload = payloads.wf_anchored;
  await window.Validation.runWalkForward([]);
  pure('walk-forward', $('validation-output').innerHTML);

  nextPayload = payloads.mc;
  await window.Validation.runMonteCarlo({});
  pure('monte carlo', $('validation-output').innerHTML);
  console.log(failures ? `\n${failures} failed` : '\nall render checks passed');
  process.exit(failures ? 1 : 0);
})();
