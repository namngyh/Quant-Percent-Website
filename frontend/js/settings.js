/* Settings, and the one place a number is turned into text.
 *
 * Two things live here because they are the same decision seen from two sides.
 * `Settings` holds what the reader chose — profit in money, percent or points;
 * the separators; the timezone the axis reads in; the contract terms a
 * derivative is sized and charged by — and `Fmt` is the only code that applies
 * those choices to a figure. Eight copies of `money()` and `pct()` had grown
 * across the panels, each with its own rounding, so the same quantity read two
 * ways depending on which panel showed it.
 *
 * Nothing here is sent anywhere. It is one versioned object in this browser's
 * localStorage, and a stored value the app no longer recognises is dropped
 * rather than trusted, the same rule session.js follows.
 */
const Settings = (() => {
  const KEY = 'qp.settings.v1';
  const VERSION = 1;

  /* Vietnam is UTC+7 all year — no daylight saving — so a fixed offset is
     exact and a timezone library would buy nothing (see charts.js). */
  const VN_OFFSET_SECONDS = 7 * 3600;

  /* The contract values with no default are the ones an exchange and a broker
     set: the margin rate, the forced-close threshold and the fee. A guessed
     one is an invented cost sitting on the account, so the interface asks
     instead (part 1 design, 2026-09-15). */
  const defaults = () => ({
    display: { profit: 'money', locale: 'en-US', decimals: 2, timezone: 'vn' },
    chart: { grid: false, bars: 180 },
    trading: {
      contract: {
        sizing: 'margin',
        contracts: 1,
        multiplier: 100000,
        initial_margin_rate: null,
        maintenance_threshold: null,
        fee_mode: 'per_contract',
        fee_per_contract: null,
        fee_rate: null,
        slippage_points: 0,
      },
    },
  });

  let data = defaults();
  const listeners = new Set();

  /* Only keys the defaults declare survive a load: a stored tree from an older
     build cannot introduce a setting this code never reads, and a value of the
     wrong type falls back rather than reaching a formatter. */
  function graft(base, stored) {
    const out = {};
    for (const [key, fallback] of Object.entries(base)) {
      const value = stored ? stored[key] : undefined;
      if (fallback && typeof fallback === 'object') {
        out[key] = graft(fallback, value && typeof value === 'object' ? value : {});
      } else if (value === undefined) {
        out[key] = fallback;
      } else if (fallback !== null && value !== null && typeof value !== typeof fallback) {
        out[key] = fallback;
      } else {
        out[key] = value;
      }
    }
    return out;
  }

  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (raw && raw.v === VERSION) data = graft(defaults(), raw);
  } catch {
    // Blocked or unreadable storage: the defaults are a working application.
  }

  function save() {
    try {
      localStorage.setItem(KEY, JSON.stringify({ ...data, v: VERSION }));
    } catch {
      // Private mode or a full quota: this session still works, it just will
      // not remember the choice.
    }
  }

  function all() {
    return JSON.parse(JSON.stringify(data));
  }

  function assign(target, part) {
    for (const [key, value] of Object.entries(part)) {
      if (!(key in target)) continue;
      if (value && typeof value === 'object' && target[key] && typeof target[key] === 'object') {
        assign(target[key], value);
      } else {
        target[key] = value;
      }
    }
  }

  function notify() {
    for (const fn of [...listeners]) fn(all());
  }

  function patch(part) {
    assign(data, part);
    save();
    notify();
  }

  function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  function reset() {
    data = defaults();
    save();
    notify();
  }

  function feeField() {
    return data.trading.contract.fee_mode === 'per_contract' ? 'fee_per_contract' : 'fee_rate';
  }

  function contractMissing() {
    const c = data.trading.contract;
    const missing = [];
    if (c.initial_margin_rate === null) missing.push('initial_margin_rate');
    if (c.maintenance_threshold === null) missing.push('maintenance_threshold');
    if (c[feeField()] === null) missing.push(feeField());
    return missing;
  }

  /* Sent with a run only when it is complete. The backend refuses a partial
     block with `contract_settings_required`, and that refusal is meant as a
     safety net, not as this interface's normal path. */
  function contractPayload() {
    if (contractMissing().length) return null;
    const c = data.trading.contract;
    return {
      sizing: c.sizing,
      contracts: c.contracts,
      multiplier: c.multiplier,
      initial_margin_rate: c.initial_margin_rate,
      maintenance_threshold: c.maintenance_threshold,
      fee_mode: c.fee_mode,
      fee_per_contract: c.fee_per_contract === null ? 0 : c.fee_per_contract,
      fee_rate: c.fee_rate === null ? 0 : c.fee_rate,
      slippage_points: c.slippage_points,
    };
  }

  function tzOffsetSeconds() {
    return data.display.timezone === 'utc' ? 0 : VN_OFFSET_SECONDS;
  }

  function timezoneLabel() {
    return data.display.timezone === 'utc' ? 'UTC' : 'GMT+7';
  }

  // ---------- The panel ----------

  const esc = (value) => String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );

  const read = (path) => path.split('.').reduce((node, key) => node[key], data);

  function options(path, choices, type = 'text') {
    const current = read(path);
    return `<select data-setting="${path}" data-type="${type}">${choices.map(
      ([value, label]) => `<option value="${esc(value)}"${
        String(current) === String(value) ? ' selected' : ''}>${esc(label)}</option>`,
    ).join('')}</select>`;
  }

  function field(path, attrs = '') {
    const value = read(path);
    return `<input type="number" data-setting="${path}" data-type="number" ${attrs} value="${
      value === null ? '' : esc(value)}">`;
  }

  function row(label, control, hint = '') {
    return `<label class="param-row"><span>${esc(label)}</span>${control}</label>${
      hint ? `<p class="hint">${esc(hint)}</p>` : ''}`;
  }

  /* What the reader still has to enter, named one by one. "Incomplete" on its
     own would send them hunting through four inputs. */
  function contractState() {
    const missing = contractMissing();
    if (!missing.length) {
      return `<div class="callout">${esc(L(
        'Đã đủ thông số: mã phái sinh VN30F/VN100F sẽ chạy theo mô hình hợp đồng.',
        'Complete: VN30F/VN100F symbols will run on the contract model.'))}</div>`;
    }
    const names = {
      initial_margin_rate: L('tỷ lệ ký quỹ ban đầu', 'initial margin rate'),
      maintenance_threshold: L('ngưỡng buộc đóng', 'forced-close threshold'),
      fee_per_contract: L('phí mỗi hợp đồng', 'fee per contract'),
      fee_rate: L('phí theo giá trị danh nghĩa', 'fee on notional'),
    };
    const list = missing.map((key) => names[key]).join(', ');
    return `<div class="callout warn">${esc(L(
      `Còn thiếu ${list}. Tới khi nhập đủ, mã phái sinh vẫn tính tuyến tính và kết quả ghi rõ điều đó.`,
      `Still missing: ${list}. Until these are set, futures run linearly and the results say so.`))}</div>`;
  }

  function html() {
    const c = data.trading.contract;
    const perContract = c.fee_mode === 'per_contract';
    return `
      <section class="set-group">
        <h3>${esc(L('Lợi nhuận', 'Profit'))}</h3>
        ${row(L('Hiển thị lợi nhuận bằng', 'Show profit as'),
              options('display.profit', [
                ['money', L('Tiền', 'Money')],
                ['percent', L('Phần trăm', 'Percent')],
                ['points', L('Điểm giá', 'Price points')],
              ]),
              L('Điểm giá chỉ có nghĩa với một mã; ở bảng gộp nhiều mã, con số hiện bằng tiền.',
                'Points only mean something for a single instrument; where several are pooled, the figure is shown as money.'))}
      </section>
      <section class="set-group">
        <h3>${esc(L('Định dạng số', 'Number format'))}</h3>
        ${row(L('Dấu phân cách', 'Separators'), options('display.locale', [
          ['en-US', L('1,234.56 (Anh - Mỹ)', '1,234.56 (English)')],
          ['vi-VN', L('1.234,56 (Việt Nam)', '1.234,56 (Vietnamese)')],
        ]))}
        ${row(L('Số chữ số thập phân', 'Decimal places'),
              options('display.decimals',
                      [['0', '0'], ['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']], 'int'))}
      </section>
      <section class="set-group">
        <h3>${esc(L('Múi giờ', 'Timezone'))}</h3>
        ${row(L('Hiển thị thời gian theo', 'Show times in'), options('display.timezone', [
          ['vn', L('Giờ Việt Nam (GMT+7)', 'Vietnam time (GMT+7)')],
          ['utc', 'UTC'],
        ]), L('Chỉ đổi cách hiển thị. Mọi thứ lưu, so sánh và gửi đi vẫn là UTC.',
              'Display only. Everything stored, compared and sent stays UTC.'))}
      </section>
      <section class="set-group">
        <h3>${esc(L('Mặc định giao dịch — hợp đồng phái sinh',
                    'Trading defaults — index futures'))}</h3>
        <p class="hint">${esc(L(
          'Áp cho VN30F/VN100F. Tỷ lệ ký quỹ, ngưỡng buộc đóng và phí do sở giao dịch và công ty chứng khoán quy định, nên nền tảng không đoán thay.',
          'Applies to VN30F/VN100F. The margin rate, the forced-close threshold and the fee are set by the exchange and the broker, so the platform does not guess them.'))}</p>
        ${row(L('Hệ số nhân (đ/điểm)', 'Multiplier (VND per point)'),
              field('trading.contract.multiplier', 'min="1" step="1000"'))}
        ${row(L('Tỷ lệ ký quỹ ban đầu', 'Initial margin rate'),
              field('trading.contract.initial_margin_rate', 'min="0.01" max="1" step="0.01"'))}
        ${row(L('Ngưỡng buộc đóng', 'Forced-close threshold'),
              field('trading.contract.maintenance_threshold', 'min="0" max="0.99" step="0.05"'))}
        ${row(L('Số hợp đồng', 'Contract count'), options('trading.contract.sizing', [
          ['margin', L('Theo vốn và ký quỹ', 'From equity and margin')],
          ['fixed', L('Cố định', 'Fixed')],
        ]))}
        ${c.sizing === 'fixed'
          ? row(L('Số hợp đồng cố định', 'Fixed number of contracts'),
                field('trading.contract.contracts', 'min="1" step="1"'))
          : ''}
        ${row(L('Cách tính phí', 'Fee basis'), options('trading.contract.fee_mode', [
          ['per_contract', L('Đồng/hợp đồng/chiều', 'VND per contract per side')],
          ['notional', L('Tỷ lệ trên giá trị danh nghĩa', 'Share of notional')],
        ]))}
        ${perContract
          ? row(L('Phí mỗi hợp đồng mỗi chiều (đ)', 'Fee per contract per side (VND)'),
                field('trading.contract.fee_per_contract', 'min="0" step="1000"'))
          : row(L('Phí trên danh nghĩa (tỷ lệ)', 'Fee on notional (rate)'),
                field('trading.contract.fee_rate', 'min="0" max="0.01" step="0.0001"'))}
        ${row(L('Trượt giá (điểm)', 'Slippage (points)'),
              field('trading.contract.slippage_points', 'min="0" step="0.1"'))}
        ${contractState()}
      </section>
      <section class="set-group">
        <h3>${esc(L('Biểu đồ', 'Chart'))}</h3>
        ${row(L('Lưới nền', 'Background grid'), options('chart.grid', [
          ['false', L('Tắt', 'Off')], ['true', L('Bật', 'On')],
        ], 'bool'))}
        ${row(L('Số nến hiện khi vào chế độ làm việc',
                'Bars shown when entering the working view'),
              field('chart.bars', 'min="40" max="1000" step="10"'))}
      </section>`;
  }

  function coerce(input) {
    const kind = input.dataset.type;
    if (kind === 'bool') return input.value === 'true';
    if (kind === 'int') return parseInt(input.value, 10);
    if (kind === 'number') return input.value === '' ? null : Number(input.value);
    return input.value;
  }

  /* Written through on change: a settings box with an unsaved state is a way
     to lose a change, and every control here is an independent choice. */
  function panel(root) {
    if (!root) return;
    root.innerHTML = html();
    if (root.dataset.wired) return;
    root.dataset.wired = '1';
    root.addEventListener('change', (event) => {
      const input = event.target.closest('[data-setting]');
      if (!input) return;
      const path = input.dataset.setting.split('.');
      const part = {};
      let node = part;
      path.forEach((key, index) => {
        node[key] = index === path.length - 1 ? coerce(input) : {};
        node = node[key];
      });
      patch(part);
      /* The shape of this panel depends on its own values — a fixed contract
         count, which fee field applies, what is still missing — so it redraws
         itself rather than leaving a stale control on screen. */
      panel(root);
    });
  }

  return {
    all, patch, subscribe, reset, panel,
    contractPayload, contractMissing, tzOffsetSeconds, timezoneLabel,
  };
})();

/* The one formatter. Callers pass the quantities they hold; this decides which
   one the reader asked to see, and how it is written. */
const Fmt = (() => {
  const display = () => Settings.all().display;

  function number(value, digits) {
    if (!Number.isFinite(value)) return '—';
    const d = display();
    return value.toLocaleString(d.locale, {
      maximumFractionDigits: digits === undefined ? d.decimals : digits,
      minimumFractionDigits: 0,
    });
  }

  const money = (value, { unit, digits } = {}) => {
    const text = number(value, digits);
    return unit ? `${text} ${unit}` : text;
  };

  const signed = (value, digits) =>
    (Number.isFinite(value) && value >= 0 ? `+${number(value, digits)}` : number(value, digits));

  const pct = (value, digits = 2) =>
    (Number.isFinite(value) ? `${signed(value, digits)}%` : '—');

  const points = (value, digits) => signed(value, digits);

  /* Profit in the mode the reader chose. A caller passes every quantity it can
     compute, because only the caller knows how; where it cannot compute one
     (points across a basket of symbols) it passes null, and the figure falls
     back to money — one honest quantity beats a dash. */
  function profit({ money: amount, pct: percent, points: pts, unit } = {}) {
    const mode = display().profit;
    if (mode === 'points' && Number.isFinite(pts)) return points(pts);
    if (mode === 'percent' && Number.isFinite(percent)) return pct(percent);
    return money(amount, { unit });
  }

  return { number, money, pct, points, profit };
})();
