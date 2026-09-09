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
const sources = ['i18n.js', 'explain.js', 'api.js', 'validation.js', 'strategy.js',
  'paper.js', 'report.js']
  .map((f) => fs.readFileSync(path.join(ROOT, 'frontend/js', f), 'utf8'));
let nextPayload = null;
window.eval(sources.join(String.fromCharCode(10, 59, 10)) + `
  ;window.I18n = I18n; window.Explain = Explain; window.Validation = Validation;
  window.Strategy = Strategy; window.Paper = Paper; window.Report = Report;
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
  window.Paper.init({
    elements: {
      list: psel('paper-sessions'), refresh: psel('refresh-paper'),
      settings: {
        root: psel('paper-settings'), close: psel('paper-settings-close'),
        preset: psel('ps-preset'), capital: psel('ps-capital'),
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

  // A venue preset fills the fee in.
  window.I18n.set('en');
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
  window.I18n.set('vi');
  psel('ps-preset').value = 'hose';
  psel('ps-preset').dispatchEvent(new window.Event('change'));
  const vi = psel('ps-warning').textContent;
  window.I18n.set('en');
  psel('ps-preset').dispatchEvent(new window.Event('change'));
  expect('venue notes are bilingual', vi !== psel('ps-warning').textContent && vi.length > 0);

  // ---------- Report tabs ----------
  //
  // Six tabs, each a few hundred numbers, in two languages. Rendering them all
  // is the cheapest way to catch a metric the backend renamed or dropped:
  // report.js reads `b.avg_bars_win` and friends by name, and a missing key
  // reaches the screen as "undefined" with no error anywhere.

  for (const lang of ['vi', 'en']) {
    window.I18n.set(lang);
    for (const [id] of window.Report.tabs) {
      let html;
      try {
        html = window.Report.renderTab(id, payloads.report);
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

  // The AmiBroker rows and the risk-management tab specifically.
  window.I18n.set('en');
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

  console.log(failures ? `\n${failures} failed` : '\nall render checks passed');
  process.exit(failures ? 1 : 0);
})();
