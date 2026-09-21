/* The (i) buttons, and the one popover they all share.
 *
 * Before this there were three separate explanation mechanisms: a modal for
 * plugin file formats, a modal for indicator help, and a scattering of `title`
 * attributes that never appeared on touch and could not hold a paragraph. A
 * metric on the results panel had no way to explain itself at all, which is
 * exactly backwards: the numbers that need explaining most are the ones a
 * reader has never seen before.
 *
 * So: one control, one popover, one registry.
 *
 *   Explain.button('sharpe')        -> markup for an (i) next to anything
 *   Explain.define(id, entry)       -> register content computed at runtime
 *   [data-explain="id"]             -> any element opens the popover on click
 *
 * Entries are plain objects. Every field is optional, so a two-line entry and
 * a full statistical annotation use the same shape:
 *
 *   { title, what, how, watch, formula, source,
 *     null, alternative, assumptions, rows: [[label, value], ...] }
 *
 * `watch` renders as a warning block, because the caveat on a metric is the
 * part people skip and the part that costs money.
 */

const Explain = (() => {
  const registry = new Map();
  let popover = null;
  let anchor = null;

  const esc = (value) =>
    String(value ?? '').replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
    ));

  // ---------- registry ----------

  function define(id, entry) {
    registry.set(id, entry);
    return id;
  }

  function defineAll(entries) {
    for (const [id, entry] of Object.entries(entries)) define(id, entry);
  }

  /* An entry may be registered as a function, in which case it is called when
     the popover opens. Entries registered at start-up as plain objects freeze
     whatever language was active then, and the language switch comes later. */
  const resolve = (entry) => (typeof entry === 'function' ? entry() : entry);
  const get = (id) => resolve(registry.get(id));

  /** Markup for an (i) button. `title` is the tooltip for pointer users. */
  function button(id, { title = L('Giải thích', 'Explain'), extraClass = '' } = {}) {
    return `<button type="button" class="info-btn ${extraClass}" data-explain="${esc(id)}"
      aria-label="${esc(title)}" title="${esc(title)}">i</button>`;
  }

  /** Register an entry under a generated id and return its button markup. */
  let counter = 0;
  function inline(entry, options) {
    const id = `x${++counter}`;
    define(id, entry);
    return button(id, options);
  }

  // ---------- statistical test entries ----------

  /* A test object from `backend/analysis/stats.py` already carries every field
     a reader needs; this turns it into an entry rather than making each caller
     rebuild the same layout. Keeping the mapping in one place is also what
     keeps the wording consistent between the price-series panel and the
     strategy panel. */
  function fromTest(test) {
    if (!test) return null;
    const rows = [];
    if (test.statistic !== null && test.statistic !== undefined) {
      rows.push([tp(test.statistic_label) || L('Thống kê', 'Statistic'),
                 fmt(test.statistic)]);
    }
    if (test.df !== null && test.df !== undefined) {
      rows.push([L('Bậc tự do', 'Degrees of freedom'), test.df]);
    }
    if (test.p_value !== null && test.p_value !== undefined) {
      rows.push([L('p thô', 'raw p'), pFormat(test.p_value)]);
    }
    if (test.p_adjusted !== null && test.p_adjusted !== undefined) {
      rows.push([L('p hiệu chỉnh (BH)', 'adjusted p (BH)'), pFormat(test.p_adjusted)]);
    }
    if (test.alpha !== undefined) rows.push([L('Mức ý nghĩa α', 'Significance α'), test.alpha]);
    if (test.critical_value !== undefined) {
      rows.push([L('Giá trị tới hạn', 'Critical value'), fmt(test.critical_value)]);
    }
    // Narrative fields arrive from the backend as {vi, en} pairs where they
    // have been translated, and as plain strings where they have not; `tp`
    // handles both.
    return {
      title: tp(test.name),
      null: tp(test.null),
      alternative: tp(test.alternative),
      rows,
      how: tp(test.conclusion),
      assumptions: tp(test.assumptions),
    };
  }

  const fmt = (value) => {
    if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
    const magnitude = Math.abs(value);
    if (magnitude !== 0 && (magnitude < 0.001 || magnitude >= 1e6)) {
      return value.toExponential(2);
    }
    return value.toFixed(magnitude >= 100 ? 1 : 3);
  };

  /* p-values below 1e-4 are printed in exponential form rather than as
     "0.0000", which reads as an exact zero and is never true.
     A p-value that arrives as exactly 0 has underflowed double precision
     rather than actually being zero, no test can rule a hypothesis out
     completely, so it is shown as a bound. Printing "0.0e+0" would be a
     claim the arithmetic cannot support. */
  const pFormat = (p) => {
    if (typeof p !== 'number' || !Number.isFinite(p)) return '—';
    if (p <= 0) return '< 1e-300';
    if (p < 1e-4) return p.toExponential(1);
    return p.toFixed(4);
  };

  // ---------- popover ----------

  function section(label, text, cls = '') {
    if (!text) return '';
    return `<div class="xp-section ${cls}">
      <div class="xp-label">${esc(label)}</div>
      <p class="xp-text">${emph(esc(text))}</p></div>`;
  }

  function render(entry) {
    let html = `<div class="xp-head">
      <strong>${esc(entry.title || L('Giải thích', 'Explanation'))}</strong>
      <button type="button" class="xp-close"
              aria-label="${esc(t('rp.close'))}">✕</button></div>
      <div class="xp-body">`;

    html += section(L('Là gì', 'What it is'), entry.what);
    html += section(L('Giả thuyết H₀', 'Null hypothesis H₀'), entry.null);
    html += section(L('Đối thuyết H₁', 'Alternative H₁'), entry.alternative);

    if (entry.formula) {
      html += `<div class="xp-section"><div class="xp-label">${esc(L('Công thức', 'Formula'))}</div>
        <code class="xp-formula">${esc(entry.formula)}</code></div>`;
    }

    if (entry.rows?.length) {
      html += '<table class="xp-table"><tbody>' + entry.rows.map(
        ([label, value]) => `<tr><td>${esc(label)}</td><td>${esc(value)}</td></tr>`,
      ).join('') + '</tbody></table>';
    }

    html += section(entry.null ? L('Kết luận', 'Conclusion') : L('Đọc thế nào', 'How to read it'), entry.how);
    html += section(L('Giả định: đọc kỹ phần này', 'Assumptions: read this part'),
                    entry.assumptions, 'assume');
    html += section(L('Cần lưu ý', 'Watch out'), entry.watch, 'watch');

    if (entry.source) {
      html += `<div class="xp-source">${esc(entry.source)}</div>`;
    }
    return html + '</div>';
  }

  function close() {
    if (!popover) return;
    popover.remove();
    popover = null;
    anchor = null;
    document.removeEventListener('keydown', onKey, true);
  }

  function onKey(event) {
    if (event.key === 'Escape') {
      event.stopPropagation();
      const button = anchor;
      close();
      button?.focus();
    }
  }

  function place(element, target) {
    const rect = target.getBoundingClientRect();
    const width = element.offsetWidth;
    const height = element.offsetHeight;
    const margin = 10;

    // Prefer to the right of the button; flip left when it would overflow,
    // and clamp rather than letting it hang off either edge.
    let left = rect.right + 8;
    if (left + width > window.innerWidth - margin) left = rect.left - width - 8;
    left = Math.max(margin, Math.min(left, window.innerWidth - width - margin));

    let top = rect.top + rect.height / 2 - height / 2;
    top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));

    element.style.left = `${Math.round(left)}px`;
    element.style.top = `${Math.round(top)}px`;
  }

  function open(target, id) {
    const entry = get(id);
    // A missing entry is a bug in the caller, not something to show the user
    // an empty box about.
    if (!entry) {
      console.warn(`Explain: no entry for "${id}"`);
      return;
    }

    const reopening = anchor === target;
    close();
    if (reopening) return;

    popover = document.createElement('div');
    popover.className = 'explain-pop';
    popover.setAttribute('role', 'dialog');
    popover.innerHTML = render(entry);
    document.body.appendChild(popover);
    anchor = target;

    place(popover, target);
    popover.querySelector('.xp-close')?.addEventListener('click', () => {
      close();
      target.focus();
    });
    document.addEventListener('keydown', onKey, true);
  }

  function init() {
    document.addEventListener('click', (event) => {
      const trigger = event.target.closest('[data-explain]');
      if (trigger) {
        event.preventDefault();
        // Catalogue rows and table rows are themselves clickable; an (i)
        // inside one must not also toggle the row it sits in.
        event.stopPropagation();
        open(trigger, trigger.dataset.explain);
        return;
      }
      if (popover && !event.target.closest('.explain-pop')) close();
    }, true);

    // The popover is absolutely positioned against the viewport, so anything
    // that moves the anchor invalidates it. Closing is less jarring than a
    // box that drifts away from what it explains.
    for (const type of ['scroll', 'resize']) {
      window.addEventListener(type, () => close(), true);
    }

    defineAll(glossary());
    // Entries built with L() capture the language at build time, so the whole
    // glossary is rebuilt when it changes. Entries registered by panels are
    // rebuilt by those panels' own redraw.
    I18n.onChange(() => defineAll(glossary()));
  }

  // ==================== Glossary ====================
  //
  // Written once, used by the results panel, the AmiBroker report, the
  // portfolio panel and the statistics panel. Where a metric has a well-known
  // failure mode, `watch` says what it is: a metric explained without its
  // failure mode is worse than one left unexplained, because it invites
  // confidence.
  //
  // A function rather than a constant so it is rebuilt when the language
  // changes: `L()` reads the current language at call time, and a static
  // object would freeze whatever was selected when the file loaded.

  const glossary = () => ({
    // ---------- execution ----------
    'exec.capital': {
      title: L('Vốn ban đầu', 'Initial capital'),
      what: L('Số tiền phiên backtest bắt đầu với.',
              'The money the backtest starts with.'),
      how: L('Mọi lãi lỗ được tính trên số này, và cỡ vị thế co giãn theo vốn hiện tại chứ không cố định theo vốn ban đầu.',
             'Every profit and loss is measured against it, and position size scales with current equity rather than staying fixed to the starting figure.'),
    },
    'exec.size': {
      title: L('% vốn mỗi lệnh', '% of equity per trade'),
      what: L('Phần vốn hiện tại đặt làm ký quỹ cho mỗi lệnh.',
              'The share of current equity committed as margin on each trade.'),
      how: L('100% nghĩa là dồn toàn bộ vốn vào một lệnh. Kết hợp với đòn bẩy, đây là biến quyết định việc tài khoản có bị thanh lý hay không.',
             'At 100% the whole account rides on one trade. Together with leverage, this is the setting that decides whether the account can be liquidated.'),
      watch: L('Đặt 100% với đòn bẩy > 1 nghĩa là một cây nến ngược chiều đủ sâu sẽ xoá sạch tài khoản. Engine mô phỏng đúng điều đó chứ không bỏ qua.',
               'At 100% with leverage above 1, one deep enough adverse bar wipes the account out. The engine simulates exactly that rather than skipping over it.'),
    },
    'exec.leverage': {
      title: L('Đòn bẩy', 'Leverage'),
      what: L('Số lần khuếch đại giá trị danh nghĩa so với ký quỹ.',
              'How far notional value is multiplied above the margin posted.'),
      how: L('Ký quỹ × đòn bẩy = giá trị vị thế. Lãi và lỗ đều nhân lên bấy nhiêu lần.',
             'Margin × leverage = position value. Gains and losses are both multiplied by the same factor.'),
      watch: L('Vị thế bị thanh lý trong nến khi lỗ chạm mức ký quỹ đã đặt, kiểm tra theo giá thấp nhất (lệnh mua) hoặc cao nhất (lệnh bán) của nến, nên một cái râu nến cũng đủ.',
               'A position is liquidated intrabar when the loss reaches the posted margin, checked against the bar’s low for a long or its high for a short, so a wick is enough.'),
    },
    'exec.fee': {
      title: L('Phí giao dịch', 'Trading fee'),
      what: L('Phí mỗi chiều, tính trên giá trị danh nghĩa.',
              'Fee per side, charged on notional value.'),
      how: L('Mặc định 0.04% là phí taker của Binance futures. Một lệnh trọn vẹn trả phí hai lần.',
             'The 0.04% default is Binance futures’ taker fee. A round trip pays it twice.'),
      watch: L('Chiến lược tần suất cao rất nhạy với con số này. Nếu chỉ báo lãi khi phí = 0 mà lỗ khi phí = 0.04% thì nó không có lợi thế thật.',
               'High-frequency strategies are acutely sensitive to it. If an indicator profits at zero fees and loses at 0.04%, it has no real edge.'),
    },
    'exec.slippage': {
      title: L('Trượt giá', 'Slippage'),
      what: L('Mức giá xấu đi so với giá khớp lý thuyết, mỗi chiều.',
              'How far each fill is worsened against the theoretical price.'),
      how: L('Luôn theo hướng bất lợi: lệnh mua khớp cao hơn, lệnh bán khớp thấp hơn.',
             'Always adverse: buys fill higher, sells fill lower.'),
      watch: L('Trượt giá thật phụ thuộc thanh khoản và cỡ lệnh, không phải hằng số. Con số cố định ở đây là xấp xỉ lạc quan cho lệnh lớn.',
               'Real slippage depends on liquidity and order size rather than being a constant. The fixed figure here is an optimistic approximation for large orders.'),
    },

    // ---------- backtest metrics ----------
    'm.total_return': {
      title: L('Tổng lợi nhuận', 'Total return'),
      what: L('Phần trăm thay đổi của vốn từ đầu tới cuối giai đoạn.',
              'The percentage change in equity from the start of the period to the end.'),
      watch: L('Tự nó không nói gì về rủi ro. Luôn đọc kèm sụt giảm tối đa và so với mua-và-giữ.',
               'On its own it says nothing about risk. Always read it beside max drawdown and buy-and-hold.'),
    },
    'm.buy_hold': {
      title: L('Mua và giữ', 'Buy and hold'),
      what: L('Lợi nhuận nếu chỉ mua ở nến đầu và giữ tới nến cuối, trên đúng giai đoạn đó.',
              'The return from buying at the first bar and holding to the last, over the identical period.'),
      how: L('Đây là mốc so sánh đúng. Một chiến lược lãi 40% trong giai đoạn mua-và-giữ lãi 120% đã thua, dù con số 40% trông đẹp.',
             'This is the right benchmark. A strategy that returns 40% over a stretch where holding returned 120% has lost, however good 40% looks.'),
    },
    'm.cagr': {
      title: L('CAGR: tăng trưởng kép hằng năm', 'CAGR: compound annual growth'),
      what: L('Tốc độ tăng trưởng đều tương đương, quy về một năm.',
              'The equivalent steady growth rate, expressed per year.'),
      formula: L('(vốn cuối / vốn đầu)^(1/số năm) − 1',
                 '(final equity / initial equity)^(1/years) − 1'),
      watch: L('Trên giai đoạn ngắn hơn một năm, CAGR ngoại suy mạnh và có thể ra con số vô lý. Kiểm tra số năm thực tế trước khi trích dẫn nó.',
               'Over a period under a year CAGR extrapolates hard and can produce an absurd figure. Check the actual span before quoting it.'),
    },
    'm.max_dd': {
      title: L('Sụt giảm tối đa', 'Maximum drawdown'),
      what: L('Mức rơi sâu nhất từ một đỉnh vốn xuống đáy kế tiếp.',
              'The deepest fall from an equity peak to the trough that follows it.'),
      how: L('Đây là con số quyết định bạn có giữ được chiến lược hay không. Một hệ thống lãi 200%/năm với sụt giảm 70% là thứ hầu hết mọi người sẽ bỏ giữa chừng.',
             'This is the number that decides whether you can stay with a strategy. A system returning 200% a year with a 70% drawdown is one most people abandon halfway down.'),
      watch: L('Sụt giảm quá khứ là cận dưới, không phải cận trên. Sụt giảm tương lai gần như luôn sâu hơn mức tệ nhất trong backtest.',
               'Past drawdown is a floor, not a ceiling. Future drawdown is almost always deeper than the worst in a backtest.'),
    },
    'm.sharpe': {
      title: 'Sharpe',
      what: L('Lợi suất trung bình chia độ lệch chuẩn, quy về năm. Lãi suất phi rủi ro coi bằng 0.',
              'Mean return divided by standard deviation, annualised. The risk-free rate is taken as zero.'),
      formula: L('√(số nến/năm) × trung bình(lợi suất) / độ lệch chuẩn(lợi suất)',
                 '√(bars per year) × mean(returns) / stdev(returns)'),
      watch: L('Giả định lợi suất phân phối chuẩn. Kiểm định Jarque–Bera ở tab Thống kê hầu như luôn bác bỏ điều đó, nên Sharpe đánh giá thấp rủi ro đuôi. Với chiến lược được chọn ra từ một lần quét tham số, hãy đọc Sharpe khử phồng (DSR) thay vì Sharpe thô.',
               'It assumes normally distributed returns. The Jarque–Bera test under Statistics almost always rejects that, so Sharpe understates tail risk. For a strategy picked out of a parameter sweep, read the deflated Sharpe ratio instead of the raw one.'),
    },
    'm.sortino': {
      title: 'Sortino',
      what: L('Như Sharpe nhưng chỉ phạt biến động theo chiều xuống.',
              'Like Sharpe, but only downside volatility is penalised.'),
      how: L('Cao hơn Sharpe nghĩa là phần lớn biến động của chiến lược là biến động có lợi.',
             'Higher than Sharpe means most of the strategy’s volatility is the helpful kind.'),
    },
    'm.profit_factor': {
      title: L('Hệ số lợi nhuận', 'Profit factor'),
      what: L('Tổng lãi của các lệnh thắng chia tổng lỗ của các lệnh thua.',
              'Gross profit from winners divided by gross loss from losers.'),
      how: L('1.0 là hoà vốn trước phí. Trên 1.5 là đáng chú ý; trên 3.0 với ít lệnh thì gần như chắc chắn là khớp nhiễu.',
             '1.0 is break-even before costs. Above 1.5 is notable; above 3.0 on few trades is almost certainly curve fitting.'),
      watch: L('Nhạy cực mạnh với một lệnh lãi lớn duy nhất. Kiểm tra lệnh tốt nhất chiếm bao nhiêu phần trăm tổng lãi trước khi tin con số này.',
               'Acutely sensitive to a single large winner. Check what share of gross profit the best trade holds before trusting it.'),
    },
    'm.win_rate': {
      title: L('Tỷ lệ thắng', 'Win rate'),
      what: L('Phần trăm lệnh có lãi.', 'The percentage of trades that made money.'),
      watch: L('Tự nó vô nghĩa. Một hệ thống thắng 30% với tỷ lệ lãi/lỗ 4:1 lãi nhiều hơn hệ thống thắng 70% với tỷ lệ 1:3. Luôn đọc kèm hệ số lợi nhuận.',
               'Meaningless alone. A system winning 30% at a 4:1 payoff beats one winning 70% at 1:3. Always read it with the profit factor.'),
    },
    'm.expectancy': {
      title: L('Kỳ vọng mỗi lệnh', 'Expectancy per trade'),
      what: L('Lãi lỗ trung bình của một lệnh, tính bằng tiền.',
              'Average profit or loss of one trade, in money.'),
      formula: L('(tỷ lệ thắng × lãi TB) − (tỷ lệ thua × lỗ TB)',
                 '(win rate × average win) − (loss rate × average loss)'),
      how: L('Đây là con số nhân với số lệnh sẽ ra lợi nhuận kỳ vọng. Âm nghĩa là càng giao dịch nhiều càng lỗ.',
             'Multiply it by the number of trades to get expected profit. Negative means more trading loses more money.'),
    },
    'm.payoff': {
      title: L('Tỷ lệ lãi/lỗ', 'Payoff ratio'),
      what: L('Lãi trung bình của lệnh thắng chia lỗ trung bình của lệnh thua.',
              'Average win divided by average loss.'),
      how: L('Cùng với tỷ lệ thắng, hai số này quyết định hệ thống có kỳ vọng dương hay không.',
             'Together with the win rate, these two decide whether the system has positive expectancy.'),
    },
    'm.exposure': {
      title: L('Thời gian nắm giữ', 'Exposure'),
      what: L('Phần trăm số nến có vị thế mở.',
              'The percentage of bars with a position open.'),
      how: L('Phơi nhiễm thấp mà lợi nhuận tương đương mua-và-giữ nghĩa là vốn rảnh phần lớn thời gian, có thể dùng cho việc khác.',
             'Low exposure with buy-and-hold returns means the capital is idle most of the time, free to work elsewhere.'),
      watch: L('Phơi nhiễm rất thấp (dưới 5%) thường đi kèm rất ít lệnh, và mọi thống kê trên đó đều thiếu tin cậy.',
               'Very low exposure (under 5%) usually comes with very few trades, and every statistic on them is unreliable.'),
    },
    'm.ulcer': {
      title: L('Chỉ số Ulcer', 'Ulcer index'),
      what: L('Căn bậc hai trung bình bình phương của mức sụt giảm, đo qua toàn bộ đường vốn.',
              'The root mean square of drawdown, measured across the whole equity curve.'),
      how: L('Khác sụt giảm tối đa ở chỗ nó phạt cả độ sâu lẫn độ dài. Hai chiến lược cùng sụt 30% nhưng một cái hồi trong một tháng, một cái hồi trong hai năm, Ulcer phân biệt được, sụt giảm tối đa thì không.',
             'Unlike max drawdown it penalises both depth and duration. Two strategies both fall 30%, one recovering in a month and one in two years, Ulcer can tell them apart, max drawdown cannot.'),
      formula: L('√( trung bình( sụt giảm² ) )', '√( mean( drawdown² ) )'),
    },
    'm.upi': {
      title: L('UPI: chỉ số hiệu quả Ulcer', 'UPI: Ulcer performance index'),
      what: L('CAGR chia chỉ số Ulcer.', 'CAGR divided by the Ulcer index.'),
      how: L('Cùng ý tưởng với Sharpe nhưng mẫu số là nỗi đau thực tế của việc nắm giữ, không phải độ lệch chuẩn.',
             'The same idea as Sharpe, but the denominator is the actual pain of holding rather than a standard deviation.'),
    },
    'm.car_mdd': {
      title: 'CAR/MDD',
      what: L('Tăng trưởng hằng năm chia sụt giảm tối đa. Còn gọi là hệ số MAR hoặc Calmar.',
              'Annual growth divided by max drawdown. Also called the MAR or Calmar ratio.'),
      how: L('Trả lời trực tiếp: mỗi phần trăm sụt giảm phải chịu đổi lấy bao nhiêu phần trăm lợi nhuận. Trên 1.0 là tốt với hệ thống dài hạn.',
             'It answers directly: how much return each point of drawdown buys. Above 1.0 is good for a long-horizon system.'),
    },
    'm.recovery': {
      title: L('Hệ số phục hồi', 'Recovery factor'),
      what: L('Tổng lợi nhuận chia sụt giảm tối đa.',
              'Total return divided by max drawdown.'),
      how: L('Giống CAR/MDD nhưng dùng lợi nhuận tuyệt đối thay vì tăng trưởng hằng năm, nên nó thiên vị giai đoạn dài.',
             'Like CAR/MDD but using absolute return rather than annual growth, so it favours longer periods.'),
    },
    'm.k_ratio': {
      title: L('Hệ số K', 'K-ratio'),
      what: L('Độ dốc của đường vốn (thang log) chia sai số chuẩn của độ dốc đó.',
              'The slope of the log equity curve divided by that slope’s standard error.'),
      how: L('Đo tính *đều đặn* của tăng trưởng, chứ không chỉ độ lớn. Đường vốn đi lên thẳng cho hệ số K cao; đường lên bằng đúng một cú nhảy cho hệ số K thấp dù tổng lợi nhuận như nhau.',
             'It measures the consistency of growth, not just its size. A straight climb scores high; the same total return arriving in one jump scores low.'),
    },
    'm.consecutive': {
      title: L('Chuỗi thắng / thua dài nhất', 'Longest winning / losing streak'),
      what: L('Số lệnh thắng liên tiếp nhiều nhất, và số lệnh thua liên tiếp nhiều nhất.',
              'The most consecutive winners, and the most consecutive losers.'),
      how: L('Chuỗi thua dài nhất là thứ cần biết trước khi chạy thật: đây là số lệnh liên tiếp bạn phải chịu đựng mà không mất niềm tin vào hệ thống.',
             'The losing streak is what to know before going live: it is how many losses in a row you must sit through without losing faith in the system.'),
      watch: L('Chuỗi thua tương lai gần như chắc chắn dài hơn chuỗi dài nhất trong backtest, đơn giản vì tương lai có nhiều lệnh hơn.',
               'The future losing streak is almost certainly longer than the backtest’s worst, simply because the future holds more trades.'),
    },
    'm.mae': {
      title: L('MAE: mức lỗ tạm thời sâu nhất', 'MAE: maximum adverse excursion'),
      what: L('Với mỗi lệnh, mức lỗ sâu nhất từng chạm trước khi lệnh đóng.',
              'For each trade, the deepest unrealised loss reached before it closed.'),
      how: L('MAE của các lệnh *thắng* cho biết dừng lỗ nên đặt ở đâu: đặt chặt hơn MAE của lệnh thắng nghĩa là cắt mất chính những lệnh sẽ có lãi.',
             'The MAE of the winners is where a stop can go: tighter than that, and you cut the very trades that would have paid.'),
    },
    'm.mfe': {
      title: L('MFE: mức lãi tạm thời cao nhất', 'MFE: maximum favourable excursion'),
      what: L('Với mỗi lệnh, mức lãi cao nhất từng chạm trước khi lệnh đóng.',
              'For each trade, the highest unrealised profit reached before it closed.'),
      how: L('MFE của các lệnh *thua* cho biết đã bỏ lỡ bao nhiêu: nếu lệnh thua thường xanh 3% trước khi đỏ, một mức chốt lãi có thể cứu chúng.',
             'The MFE of the losers is what was left on the table: if losing trades are routinely 3% up before turning, a profit target could rescue them.'),
    },
    'm.liquidation': {
      title: L('Số lần thanh lý', 'Liquidations'),
      what: L('Số lệnh bị đóng cưỡng chế vì lỗ chạm mức ký quỹ.',
              'Trades force-closed because the loss reached the posted margin.'),
      watch: L('Bất kỳ con số nào lớn hơn 0 nghĩa là đòn bẩy đang quá cao so với biến động của thị trường này. Kết quả vẫn được tính đúng, nhưng chiến lược đang chơi ở vùng mà một cây nến xấu là mất trắng.',
               'Anything above zero means leverage is too high for this market’s volatility. The results are still computed correctly, but the strategy is operating where one bad bar means total loss.'),
    },

    // ---------- ML ----------
    'ml.accuracy': {
      title: L('Độ chính xác', 'Accuracy'),
      what: L('Phần trăm nến mà tín hiệu đoán đúng hướng của nến kế tiếp.',
              'The percentage of bars where the signal called the next bar’s direction correctly.'),
      watch: L('Con số gây hiểu lầm nhiều nhất trong đánh giá ML tài chính. Nếu thị trường tăng 55% số nến thì đoán "tăng" mọi lúc đã đạt 55%. Luôn so với đường cơ sở, không so với 50%.',
               'The most misleading figure in financial ML. If the market rises on 55% of bars, always saying "up" already scores 55%. Compare against the baseline, never against 50%.'),
    },
    'ml.baseline': {
      title: L('Đường cơ sở', 'Baseline'),
      what: L('Độ chính xác của quy tắc ngây thơ nhất: luôn đoán lớp phổ biến nhất.',
              'The accuracy of the most naive rule: always predict the majority class.'),
      how: L('Mô hình chỉ có giá trị khi vượt được con số này. Vượt 1–2 điểm phần trăm trên vài nghìn nến thường nằm trong sai số lấy mẫu.',
             'A model is only worth anything if it beats this. One or two percentage points over a few thousand bars is usually inside sampling error.'),
    },
    'ml.precision': {
      title: 'Precision',
      what: L('Trong các nến mô hình báo "tăng", bao nhiêu phần trăm thật sự tăng.',
              'Of the bars the model called "up", what share actually rose.'),
      how: L('Đây là con số gắn trực tiếp với tiền: mỗi tín hiệu sai là một lệnh thua có phí.',
             'This is the figure tied directly to money: every wrong signal is a losing trade that still pays fees.'),
    },
    'ml.recall': {
      title: 'Recall',
      what: L('Trong các nến thật sự tăng, mô hình bắt được bao nhiêu phần trăm.',
              'Of the bars that actually rose, what share the model caught.'),
      how: L('Recall thấp nghĩa là bỏ lỡ cơ hội, ít tốn kém hơn precision thấp, vì bỏ lỡ không mất phí.',
             'Low recall means missed opportunity, cheaper than low precision, because a miss costs no fees.'),
    },
    'ml.f1': {
      title: 'F1',
      what: L('Trung bình điều hoà của precision và recall.',
              'The harmonic mean of precision and recall.'),
      how: L('Một con số duy nhất khi cần cân bằng hai thứ. Không thay thế được việc nhìn cả hai riêng rẽ, vì chi phí của hai loại sai là khác nhau.',
             'One figure when both matter. It does not replace reading them separately, because the two kinds of error cost different amounts.'),
    },
    'ml.mcc': {
      title: L('Hệ số tương quan Matthews', 'Matthews correlation coefficient'),
      what: L('Tương quan giữa dự đoán và thực tế, trong khoảng −1 tới +1.',
              'The correlation between prediction and outcome, from −1 to +1.'),
      how: L('0 là đoán mò. Đây là thước đo đáng tin nhất khi hai lớp lệch nhau, vì nó dùng cả bốn ô của ma trận nhầm lẫn.',
             'Zero is chance. It is the most trustworthy measure when the classes are imbalanced, because it uses all four cells of the confusion matrix.'),
    },
    'ml.auc': {
      title: 'ROC-AUC',
      what: L('Xác suất mô hình chấm điểm một nến tăng cao hơn một nến giảm, khi lấy ngẫu nhiên mỗi loại một cái.',
              'The probability the model scores a randomly chosen rising bar above a randomly chosen falling one.'),
      how: L('0.5 là vô dụng. Với dữ liệu tài chính, 0.55 đã là đáng kể và 0.70 gần như chắc chắn là rò rỉ dữ liệu tương lai.',
             '0.5 is useless. On financial data 0.55 is already meaningful, and 0.70 is almost certainly look-ahead leakage.'),
      watch: L('AUC không quan tâm ngưỡng, nên AUC tốt không đảm bảo chiến lược có lãi ở ngưỡng đang dùng.',
               'AUC ignores the threshold, so a good AUC does not guarantee profit at the threshold actually in use.'),
    },
    'ml.brier': {
      title: L('Điểm Brier', 'Brier score'),
      what: L('Sai số bình phương trung bình giữa xác suất dự báo và kết quả thực tế.',
              'The mean squared error between predicted probability and outcome.'),
      how: L('Càng nhỏ càng tốt. Đo *hiệu chuẩn*: một mô hình nói "70%" nên đúng khoảng 70% số lần đó.',
             'Lower is better. It measures calibration: a model saying "70%" should be right about 70% of the time.'),
      watch: L('Một mô hình luôn báo 50% có điểm Brier khá tốt mà hoàn toàn vô dụng. Đọc kèm AUC.',
               'A model that always says 50% scores a decent Brier and is completely useless. Read it with AUC.'),
    },
    'ml.logloss': {
      title: 'Log-loss',
      what: L('Phạt theo logarit cho xác suất dự báo sai.',
              'A logarithmic penalty on wrong probability forecasts.'),
      how: L('Phạt rất nặng những dự báo tự tin mà sai, đúng thứ cần phạt khi tín hiệu điều khiển cỡ vị thế.',
             'It punishes confident wrong calls hard, exactly what should be punished when a signal drives position size.'),
    },
    'ml.confusion': {
      title: L('Ma trận nhầm lẫn', 'Confusion matrix'),
      what: L('Bảng đếm bốn trường hợp: đoán tăng/thật tăng, đoán tăng/thật giảm, và hai ô còn lại.',
              'A four-cell count: called up and rose, called up and fell, and the other two.'),
      how: L('Mọi chỉ số phân loại đều tính ra từ bảng này. Khi một chỉ số trông lạ, bảng này cho biết vì sao.',
             'Every classification metric is computed from this table. When one of them looks strange, this is where the reason is.'),
    },

    // ---------- portfolio ----------
    'p.risk_contribution': {
      title: L('Đóng góp rủi ro', 'Risk contribution'),
      what: L('Phần rủi ro toàn danh mục đến từ một vị thế, sau khi tính cả cách nó di chuyển cùng các vị thế khác.',
              'The share of total portfolio risk coming from one position, after accounting for how it moves with the others.'),
      formula: 'wᵢ × (Σw)ᵢ / (wᵀΣw)',
      how: L('Đây là con số quan trọng nhất của trang này. Bạn đã biết mỗi mã chiếm bao nhiêu phần trăm *tiền*; điều bạn không thấy là một mã chiếm 25% tiền có thể chiếm 45% rủi ro vì nó đi cùng chiều với phần còn lại.',
             'The most important number on this page. You already know each name’s share of the money; what you cannot see is that 25% of the money can be 45% of the risk because it moves with everything else.'),
    },
    'p.effective_bets': {
      title: L('Số cược độc lập hiệu dụng', 'Effective bets'),
      what: L('Số vị thế thực sự độc lập, sau khi trừ đi phần tương quan.',
              'How many genuinely independent positions remain once correlation is removed.'),
      formula: L('N / (1 + (N − 1) × tương quan trung bình)',
                 'N / (1 + (N − 1) × average correlation)'),
      how: L('Mười mã cùng ngành với tương quan trung bình 0.7 hành xử như khoảng ba cược, không phải mười. Đây là con số nói ra điều đó.',
             'Ten names in one sector correlated at 0.7 behave like about three bets, not ten. This is the number that says so.'),
    },
    'p.herfindahl': {
      title: L('Chỉ số Herfindahl', 'Herfindahl index'),
      what: L('Tổng bình phương tỷ trọng.', 'The sum of squared weights.'),
      how: L('Nghịch đảo của nó là "số mã hiệu dụng" theo tiền: danh mục 10 mã đều nhau cho 10, còn 10 mã mà một mã chiếm 80% thì chỉ cho khoảng 1.5.',
             'Its reciprocal is the effective number of holdings by money: ten equal names give 10, ten names where one holds 80% give about 1.5.'),
    },
    'p.beta': {
      title: L('Beta so với VN-Index', 'Beta against the VN-Index'),
      what: L('Danh mục nhận bao nhiêu phần trăm mức dao động của chỉ số.',
              'How much of the index’s movement the portfolio takes on.'),
      how: L('Beta 1.2 nghĩa là chỉ số giảm 10% thì danh mục có xu hướng giảm 12%.',
             'A beta of 1.2 means a 10% fall in the index tends to take the portfolio down 12%.'),
      watch: L('Beta ước lượng từ quá khứ và không ổn định qua các chế độ thị trường. Nó cũng chỉ giải thích phần rủi ro đi cùng thị trường, không phải toàn bộ.',
               'Beta is estimated from the past and is not stable across regimes. It also explains only the market-linked part of the risk, not all of it.'),
    },
    'p.var': {
      title: L('VaR 95% (một phiên)', 'VaR 95% (one session)'),
      what: L('Mức lỗ mà 5% số phiên tệ nhất vượt qua, đo bằng mô phỏng lịch sử.',
              'The loss exceeded by the worst 5% of sessions, measured by historical simulation.'),
      watch: L('VaR không nói gì về mức lỗ *khi* đã vượt ngưỡng. Đó là việc của CVaR ngay bên cạnh.',
               'VaR says nothing about how bad it gets once the threshold is crossed. That is what CVaR beside it is for.'),
    },
    'p.cvar': {
      title: L('CVaR 95% (một phiên)', 'CVaR 95% (one session)'),
      what: L('Mức lỗ trung bình trong đúng 5% số phiên tệ nhất.',
              'The average loss across exactly the worst 5% of sessions.'),
      how: L('Đây mới là con số mô tả một ngày xấu thật sự. Luôn sâu hơn VaR.',
             'This is the figure that describes a genuinely bad day. It is always deeper than VaR.'),
    },
    'p.correlation': {
      title: L('Tương quan trung bình', 'Average correlation'),
      what: L('Trung bình hệ số tương quan giữa mọi cặp mã trong danh mục.',
              'The mean correlation across every pair of holdings.'),
      watch: L('Tương quan tăng vọt đúng lúc thị trường sụp. Đa dạng hoá đo trong giai đoạn yên bình luôn lạc quan hơn thực tế lúc cần nó nhất.',
               'Correlations spike exactly when markets fall. Diversification measured in calm conditions is always more flattering than what you get when you need it.'),
    },
    'p.shrinkage': {
      title: L('Co rút Ledoit–Wolf', 'Ledoit–Wolf shrinkage'),
      what: L('Ma trận hiệp phương sai mẫu được kéo về một mục tiêu tương quan hằng số.',
              'The sample covariance matrix pulled towards a constant-correlation target.'),
      how: L('Với khoảng 250 phiên và 10–30 mã, hiệp phương sai mẫu ước lượng rất tệ và mọi thứ tính từ nó còn tệ hơn. Co rút là cách xử lý tiêu chuẩn, không phải một tuỳ chọn nâng cao.',
             'With around 250 sessions and 10–30 names the sample covariance is badly estimated and everything derived from it is worse. Shrinkage is the standard fix, not an advanced option.'),
    },
  });

  return { init, define, defineAll, get, button, inline, fromTest, fmt, pFormat };
})();
