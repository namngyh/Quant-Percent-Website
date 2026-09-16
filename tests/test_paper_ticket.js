const fs = require('node:fs');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const tick = () => new Promise(r => setImmediate(r));
(async () => {
  const dom = new JSDOM('<body><div id="list"></div><button id="refresh"></button></body>',
    { url: 'http://localhost', runScripts: 'outside-only' });
  const w = dom.window;
  w.CSS = { escape: s => s };
  w.eval(['i18n', 'settings', 'api', 'paper'].map(f => fs.readFileSync(`frontend/js/${f}.js`, 'utf8')).join('\n')
    + '\nwindow.Paper=Paper; window.API=API; window.I18n=I18n;');
  const list = w.document.getElementById('list');
  let filled = null, resolveOrder, payload, calls = 0;
  w.Paper.init({ elements: { list, refresh: w.document.getElementById('refresh'), onOrderFilled: s => { filled = s.id; } }, onToast() {} });
  const s = { id: 'ticket', symbol: 'BTCUSDT', timeframe: '1m', active: true,
    strategy_id: 'manual', is_manual: true, position: 1, quantity: .5, entry_price: 75000,
    last_price: 76000, equity: 10000, unrealized_pnl: 500, realized_pnl: 0, return_pct: 5,
    num_trades: 0, win_rate_pct: 0, pending_signal: 1, trades: [],
    config: { initial_capital: 10000, leverage: 2, size_pct: .7, fee: .0004, slippage: .0002 } };
  w.Paper.apply(s);
  const get = name => list.querySelector(`[data-${name}]`);
  assert.match(list.querySelector('.pp-figures').textContent, /USDT/);
  assert.match(list.querySelector('.pp-figures').textContent, /0.5 BTC/);
  assert.match(get('order').textContent, /USDT/);
  console.log('PASS account, price and quantity units');
  get('leverage').value = '8'; get('leverage').dispatchEvent(new w.Event('input')); get('leverage').focus();
  get('target').value = '70000'; get('target').dispatchEvent(new w.Event('input'));
  w.Paper.apply({ ...s, last_price: 76001 });
  assert.equal(get('leverage').value, '8'); assert.equal(get('target').value, '70000');
  assert.equal(w.document.activeElement, get('leverage'));
  console.log('PASS realtime preserves draft values and focus');
  w.fetch = async (url, options) => {
    payload = JSON.parse(options.body); calls++;
    return new Promise(r => { resolveOrder = result => r({ ok: true, json: async () => result }); });
  };
  list.querySelector('[data-order="short"]').click(); await tick();
  assert.equal(payload.leverage, 8); assert.equal(payload.size_pct, .7); assert.equal(payload.take_profit, 70000);
  w.Paper.apply(s);
  list.querySelector('[data-order="short"]').click();
  assert.equal(calls, 1); assert.equal(get('leverage').disabled, true);
  resolveOrder({ snapshot: { ...s, position: -1, config: { ...s.config, leverage: 8 } }, events: [{ type: 'entry', side: 'short', price: 76001 }] });
  await tick(); await tick();
  assert.equal(filled, 'ticket'); assert.equal(get('leverage').value, '8');
  assert.equal(get('leverage').disabled, false);
  console.log('PASS order sends leverage, locks across ticks and notifies chart immediately');
  w.fetch = async () => ({ ok: false, status: 422, json: async () => ({ detail: 'Refused' }) });
  list.querySelector('[data-order="long"]').click(); await tick(); await tick();
  assert.equal(get('leverage').disabled, false);
  assert.equal(list.querySelector('[data-order="short"]').disabled, true);
  console.log('PASS refusal restores the correct enabled controls');
  w.I18n.set('en'); w.Paper.rerender();
  assert.match(list.textContent, /Leverage/);
  console.log('PASS bilingual ticket');
  dom.window.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
