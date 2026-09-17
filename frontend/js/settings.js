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

  /* Contract terms for VN30F/VN100F.

     The margin defaults are DNSE's published rates, chosen by Nam on
     2026-09-17: initial margin 18.48% and force sell 17.35%, both as a share
     of the contract's value, and both editable here. The fee is the broker's
     and stays the user's to enter; 0 means no fee is charged, and the panel
     says so rather than letting a free trade pass unnoticed. */
  const defaults = () => ({
    display: { profit: 'money', locale: 'en-US', decimals: 2, timezone: 'vn' },
    chart: { grid: false, bars: 180 },
    data: { adjustSplits: true },
    trading: {
      contract: {
        sizing: 'margin',
        contracts: 1,
        multiplier: 100000,
        initial_margin_pct: 18.48,
        force_sell_pct: 17.35,
        fee_mode: 'per_contract',
        fee_per_contract: 0,
        fee_rate: 0,
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
      } else if (value === undefined || (value === null && fallback !== null)) {
        // A null stored by an older build, where the field had no default,
        // must not blank a default that now exists.
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
    if (!(c.initial_margin_pct > 0 && c.initial_margin_pct <= 100)) missing.push('initial_margin_pct');
    // Force sell sits below the initial rate: at or above it a position would
    // be closed the moment it opened.
    if (!(c.force_sell_pct >= 0 && c.force_sell_pct < c.initial_margin_pct)) missing.push('force_sell_pct');
    if (c[feeField()] === null || !(c[feeField()] >= 0)) missing.push(feeField());
    return missing;
  }

  /* The engine's two numbers from the broker's two percentages.

     The engine closes a position when its remaining margin falls to
     `maintenance_threshold` × the initial margin. DNSE quotes both rates as a
     share of the contract value, so the threshold is their ratio: at 18.48% and
     17.35% a position is closed after an adverse move of 1.13% of its value,
     which at 1 978 points is 22.4 points. */
  function contractRates(c = data.trading.contract) {
    return {
      initial_margin_rate: c.initial_margin_pct / 100,
      maintenance_threshold: c.force_sell_pct / c.initial_margin_pct,
    };
  }

  /** Margin one contract needs at `price`, in VND. */
  function marginPerContract(price, c = data.trading.contract) {
    return price * c.multiplier * c.initial_margin_pct / 100;
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
      ...contractRates(c),
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
      const c = data.trading.contract;
      const move = c.initial_margin_pct - c.force_sell_pct;
      const free = c[feeField()] === 0;
      return `<div class="callout">${esc(L(
        `Mã phái sinh VN30F/VN100F chạy theo mô hình hợp đồng. Vị thế bị buộc đóng khi giá đi ngược ${move.toFixed(2)}% giá trị hợp đồng. Nên có vốn lớn hơn ký quỹ một hợp đồng (giá × hệ số nhân × ${c.initial_margin_pct}%) để kết quả sát thực tế nhất.${free ? ' Phí đang là 0: lệnh chưa bị trừ phí.' : ''}`,
        `VN30F/VN100F symbols run on the contract model. A position is force-closed after an adverse move of ${move.toFixed(2)}% of the contract value. Hold more capital than one contract's margin (price × multiplier × ${c.initial_margin_pct}%) for the most accurate result.${free ? ' The fee is 0: orders are not charged.' : ''}`))}</div>`;
    }
    const names = {
      initial_margin_pct: L('tỷ lệ ký quỹ ban đầu (0–100%)', 'initial margin rate (0–100%)'),
      force_sell_pct: L('tỷ lệ force sell (phải nhỏ hơn ký quỹ ban đầu)', 'force-sell rate (below the initial margin)'),
      fee_per_contract: L('phí mỗi hợp đồng', 'fee per contract'),
      fee_rate: L('phí theo giá trị danh nghĩa', 'fee on notional'),
    };
    const list = missing.map((key) => names[key]).join(', ');
    return `<div class="callout warn">${esc(L(
      `Còn thiếu ${list}. Tới khi nhập đủ, mã phái sinh vẫn tính tuyến tính và kết quả ghi rõ điều đó.`,
      `Still missing: ${list}. Until these are set, futures run linearly and the results say so.`))}</div>`;
  }

  /* The box is split into sections (Nam, 2026-09-17): one long scroll put the
     timezone next to the futures margin, and the contract terms alone ran past
     the fold. The list on the left names the sections; the right side holds
     only the chosen one. The choice lasts for the page, not across reloads —
     the box should open where the reader left it a moment ago, and at the
     top next time. */
  const SECTIONS = [
    ['display', () => L('Hiển thị', 'Display')],
    ['trading', () => L('Giao dịch', 'Trading')],
    ['data', () => L('Dữ liệu', 'Data')],
    ['chart', () => L('Biểu đồ', 'Chart')],
  ];
  let section = 'display';

  function nav() {
    return `<nav class="set-nav" role="tablist" aria-orientation="vertical">${SECTIONS.map(([key, label]) =>
      `<button type="button" role="tab" class="set-nav-item${key === section ? ' active' : ''}"
               data-set-section="${key}" aria-selected="${key === section}"
               aria-controls="set-section-${key}">${esc(label())}</button>`).join('')}</nav>`;
  }

  const open = (key) => `<div class="set-section" id="set-section-${key}" role="tabpanel"${
    key === section ? '' : ' hidden'}>`;

  function html() {
    const c = data.trading.contract;
    const perContract = c.fee_mode === 'per_contract';
    return `${nav()}<div class="set-sections">
      ${open('display')}
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
      </div>
      ${open('trading')}
      <section class="set-group">
        <h3>${esc(L('Hợp đồng phái sinh', 'Index futures'))}</h3>
        <p class="hint">${esc(L(
          'Áp cho VN30F/VN100F. Mặc định theo DNSE: ký quỹ ban đầu 18,48%, force sell 17,35% giá trị hợp đồng. Phí do công ty chứng khoán của bạn quy định.',
          'Applies to VN30F/VN100F. Defaults follow DNSE: initial margin 18.48% and force sell 17.35% of the contract value. The fee is set by your broker.'))}</p>
        ${row(L('Hệ số nhân (đ/điểm)', 'Multiplier (VND per point)'),
              field('trading.contract.multiplier', 'min="1" step="1000"'))}
        ${row(L('Tỷ lệ ký quỹ ban đầu (%)', 'Initial margin rate (%)'),
              field('trading.contract.initial_margin_pct', 'min="0.01" max="100" step="0.01"'))}
        ${row(L('Tỷ lệ force sell (%)', 'Force-sell rate (%)'),
              field('trading.contract.force_sell_pct', 'min="0" max="100" step="0.01"'),
              L('Theo giá trị hợp đồng. Vị thế bị đóng khi ký quỹ còn lại xuống dưới mức này.',
                'Of the contract value. A position is closed when its remaining margin falls below this.'))}
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
      </div>
      ${open('data')}
      <section class="set-group">
        <h3>${esc(L('Giá cổ phiếu Việt Nam', 'Vietnamese equity prices'))}</h3>
        ${row(L('Điều chỉnh chia tách / cổ tức cổ phiếu', 'Adjust for splits and stock dividends'),
              options('data.adjustSplits', [
                ['true', L('Bật', 'On')], ['false', L('Tắt', 'Off')],
              ], 'bool'),
              L('Giá cổ phiếu VN được lưu ở dạng thô. Một lần chia tách in ra phiên giảm 50% chưa từng xảy ra, và một backtest đi qua đó sẽ bán, dừng lỗ hoặc bị thanh lý trên một cú sập không có thật. Nền tảng suy ra sự kiện từ bước nhảy vượt biên độ và đưa chuỗi về một thang. Tắt để xem đúng giá database trả về.',
                'Vietnamese equity prices are stored raw. A split prints as a −50% session that never happened, and a backtest running through it sells, stops out or is liquidated on a crash that does not exist. The platform infers the event from a step past the price band and puts the series back on one scale. Turn this off to see the database\'s own prices.'))}
      </section>
      </div>
      ${open('chart')}
      <section class="set-group">
        <h3>${esc(L('Hiển thị biểu đồ', 'Chart display'))}</h3>
        ${row(L('Lưới nền', 'Background grid'), options('chart.grid', [
          ['false', L('Tắt', 'Off')], ['true', L('Bật', 'On')],
        ], 'bool'))}
        ${row(L('Số nến hiện khi vào chế độ làm việc',
                'Bars shown when entering the working view'),
              field('chart.bars', 'min="40" max="1000" step="10"'))}
      </section>
      </div>
    </div>`;
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
    root.addEventListener('click', (event) => {
      const tab = event.target.closest('[data-set-section]');
      if (!tab || tab.dataset.setSection === section) return;
      section = tab.dataset.setSection;
      panel(root);
      root.querySelector(`[data-set-section="${section}"]`)?.focus();
    });
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
    contractPayload, contractMissing, marginPerContract, tzOffsetSeconds, timezoneLabel,
  };
})();

/* The one formatter. Callers pass the quantities they hold; this decides which
   one the reader asked to see, and how it is written. */
const Fmt = (() => {
  const display = () => Settings.all().display;

  function number(value, digits, min = 0) {
    if (!Number.isFinite(value)) return '—';
    const d = display();
    const max = digits === undefined ? d.decimals : digits;
    return value.toLocaleString(d.locale, {
      maximumFractionDigits: max,
      minimumFractionDigits: Math.min(min, max),
    });
  }

  const money = (value, { unit, digits, min } = {}) => {
    const text = number(value, digits, min);
    return unit ? `${text} ${unit}` : text;
  };

  const signed = (value, digits, min) =>
    (Number.isFinite(value) && value >= 0
      ? `+${number(value, digits, min)}` : number(value, digits, min));

  /* A ratio keeps its trailing zeros: 3.7% and 3.70% are the same number, but
     a column where some rows show two decimals and others one is harder to
     read down than one that does not move. */
  const pct = (value, digits = 2) =>
    (Number.isFinite(value) ? `${signed(value, digits, digits)}%` : '—');

  const upct = (value, digits = 2) =>
    (Number.isFinite(value) ? `${number(value, digits, digits)}%` : '—');

  const points = (value, digits, min) => signed(value, digits, min);

  /* Profit in the mode the reader chose. A caller passes every quantity it can
     compute, because only the caller knows how; where it cannot compute one
     (points across a basket of symbols) it passes null, and the figure falls
     back to money — one honest quantity beats a dash.

     Signed in every mode: a profit figure without its direction is the one
     thing about it nobody can infer. `money()` on its own stays unsigned,
     because a balance is not a direction. */
  function profit({ money: amount, pct: percent, points: pts, unit, digits, min } = {}) {
    const mode = display().profit;
    if (mode === 'points' && Number.isFinite(pts)) return points(pts, digits, min);
    if (mode === 'percent' && Number.isFinite(percent)) return pct(percent);
    if (!Number.isFinite(amount)) return '—';
    return `${signed(amount, digits, min)}${unit ? ` ${unit}` : ''}`;
  }

  return { number, money, pct, upct, points, profit, mode: () => display().profit };
})();
