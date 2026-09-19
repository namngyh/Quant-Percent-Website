const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

const root = path.resolve(__dirname, '..');
const dom = new JSDOM('<!doctype html><body></body>', {
  url: 'http://localhost/', runScripts: 'outside-only', pretendToBeVisual: true,
});
const w = dom.window;
const source = ['frontend/js/i18n.js', 'frontend/js/settings.js',
  'frontend/js/api.js', 'frontend/js/paper-dash.js']
  .map((file) => fs.readFileSync(path.join(root, file), 'utf8')).join('\n');
w.eval(`${source}\nwindow.__PaperDash = PaperDash; window.__API = API;`);

const summary = {
  sessions: 1,
  accounts: [],
  currency: 'USDT', active_sessions: 1,
  starting_capital: 10000, equity: 10979, realized_pnl: 979,
  unrealized_pnl: 0, return_pct: 9.79,
  num_trades: 1, num_wins: 1, win_rate_pct: 100,
  avg_win: 979, avg_loss: 0, best_trade: 979, worst_trade: 979,
  profit_factor: null, profitable_trades_pnl: 979,
  expectancy_money: 979, expectancy_pct: 9.79, avg_rr: null,
  total_fees: 21, max_drawdown_pct: 0, max_drawdown_abs: 0,
  open_positions: [], by_symbol: [{ symbol: 'BTCUSDT', trades: 1, win_rate_pct: 100, pnl: 979 }],
  equity_curve: [{ time: 100, equity: 10000 }, { time: 200, equity: 10979 }],
  balance_history: [{ time: 200, balance_before: 10000, gross_pnl: 1000,
    entry_fee: 10, exit_fee: 11, fee: 21, net_pnl: 979,
    balance_after: 10979, symbol: 'BTCUSDT', side: 'long', exit_reason: 'manual' }],
  trades: [{ exit_time: 200, symbol: 'BTCUSDT', side: 'long', entry_price: 100,
    exit_price: 110, pnl: 989, net_pnl: 979, fee: 21,
    return_pct: 9.89, exit_reason: 'manual' }],
};
summary.accounts = [{ ...summary, accounts: undefined }];
w.__paperSummary = summary;
w.__API.paperSummary = async () => w.__paperSummary;
w.__PaperDash.init({ onToast: (message) => { throw new Error(message); } });

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
function check(name, condition) {
  if (!condition) throw new Error(`FAIL ${name}`);
  console.log(`PASS ${name}`);
}

(async () => {
  await w.__PaperDash.open();
  check('dashboard has no manual refresh button', !w.document.querySelector('[data-pd-refresh]'));
  check('renamed simulated account heading', /Tài khoản giao dịch mô phỏng/.test(w.document.body.textContent));

  const clickTab = (id) => w.document.querySelector(`[data-pd-tab="${id}"]`)
    .dispatchEvent(new w.MouseEvent('click', { bubbles: true }));

  clickTab('balance');
  const ledger = w.document.querySelector('.pd-body').textContent;
  check('balance history shows requested columns',
    /Số dư trước kết toán/.test(ledger) && /Số dư sau kết toán/.test(ledger)
      && /Lãi\/Lỗ đã thực hiện/.test(ledger) && /Phí giao dịch/.test(ledger)
      && /Hành động/.test(ledger));
  check('fees and action are visible', /21/.test(ledger) && /Đóng LONG/.test(ledger));

  clickTab('analysis');
  const analysis = w.document.querySelector('.pd-body').textContent;
  check('analysis shows all requested metrics',
    /Giao dịch lãi/.test(analysis) && /Hệ số lãi/.test(analysis)
      && /Kỳ vọng giao dịch/.test(analysis) && /RR trung bình/.test(analysis)
      && /Hiệu suất/.test(analysis));
  check('analysis renders a performance chart', Boolean(w.document.querySelector('.pd-chart svg')));

  w.__paperSummary = { ...summary, equity: 11111, return_pct: 11.11,
    accounts: [{ ...summary, equity: 11111, return_pct: 11.11, accounts: undefined }] };
  w.__PaperDash.sync();
  await wait(180);
  clickTab('equity');
  check('live sync repaints account without a button', /11,111\.00/.test(w.document.querySelector('.pd-body').textContent));
  w.__PaperDash.close();
})().catch((err) => {
  console.error(err.stack || err);
  process.exitCode = 1;
});
