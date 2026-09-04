/* The (i) buttons, and the one popover they all share.
 *
 * Before this there were three separate explanation mechanisms: a modal for
 * plugin file formats, a modal for indicator help, and a scattering of `title`
 * attributes that never appeared on touch and could not hold a paragraph. A
 * metric on the results panel had no way to explain itself at all, which is
 * exactly backwards — the numbers that need explaining most are the ones a
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

  const get = (id) => registry.get(id);

  /** Markup for an (i) button. `title` is the tooltip for pointer users. */
  function button(id, { title = 'Giải thích', extraClass = '' } = {}) {
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
      rows.push([test.statistic_label || 'Thống kê', fmt(test.statistic)]);
    }
    if (test.df !== null && test.df !== undefined) rows.push(['Bậc tự do', test.df]);
    if (test.p_value !== null && test.p_value !== undefined) {
      rows.push(['p thô', pFormat(test.p_value)]);
    }
    if (test.p_adjusted !== null && test.p_adjusted !== undefined) {
      rows.push(['p hiệu chỉnh (BH)', pFormat(test.p_adjusted)]);
    }
    if (test.alpha !== undefined) rows.push(['Mức ý nghĩa α', test.alpha]);
    if (test.critical_value !== undefined) {
      rows.push(['Giá trị tới hạn', fmt(test.critical_value)]);
    }
    return {
      title: test.name,
      null: test.null,
      alternative: test.alternative,
      rows,
      how: test.conclusion,
      assumptions: test.assumptions,
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
     rather than actually being zero — no test can rule a hypothesis out
     completely — so it is shown as a bound. Printing "0.0e+0" would be a
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
      <p class="xp-text">${esc(text)}</p></div>`;
  }

  function render(entry) {
    let html = `<div class="xp-head">
      <strong>${esc(entry.title || 'Giải thích')}</strong>
      <button type="button" class="xp-close" aria-label="Đóng">✕</button></div>
      <div class="xp-body">`;

    html += section('Là gì', entry.what);
    html += section('Giả thuyết H₀', entry.null);
    html += section('Đối thuyết H₁', entry.alternative);

    if (entry.formula) {
      html += `<div class="xp-section"><div class="xp-label">Công thức</div>
        <code class="xp-formula">${esc(entry.formula)}</code></div>`;
    }

    if (entry.rows?.length) {
      html += '<table class="xp-table"><tbody>' + entry.rows.map(
        ([label, value]) => `<tr><td>${esc(label)}</td><td>${esc(value)}</td></tr>`,
      ).join('') + '</tbody></table>';
    }

    html += section(entry.null ? 'Kết luận' : 'Đọc thế nào', entry.how);
    html += section('Giả định — đọc kỹ phần này', entry.assumptions, 'assume');
    html += section('Cần lưu ý', entry.watch, 'watch');

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
    const entry = registry.get(id);
    // A missing entry is a bug in the caller, not something to show the user
    // an empty box about.
    if (!entry) {
      console.warn(`Explain: chưa có nội dung cho "${id}"`);
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

    defineAll(GLOSSARY);
  }

  // ==================== Glossary ====================
  //
  // Written once, used by the results panel, the AmiBroker report, the
  // portfolio panel and the statistics panel. Where a metric has a well-known
  // failure mode, `watch` says what it is — a metric explained without its
  // failure mode is worse than one left unexplained, because it invites
  // confidence.

  const GLOSSARY = {
    // ---------- execution ----------
    'exec.capital': {
      title: 'Vốn ban đầu',
      what: 'Số tiền phiên backtest bắt đầu với.',
      how: 'Mọi lãi lỗ được tính trên số này, và cỡ vị thế co giãn theo vốn hiện tại chứ không cố định theo vốn ban đầu.',
    },
    'exec.size': {
      title: '% vốn mỗi lệnh',
      what: 'Phần vốn hiện tại đặt làm ký quỹ cho mỗi lệnh.',
      how: '100% nghĩa là dồn toàn bộ vốn vào một lệnh. Kết hợp với đòn bẩy, đây là biến quyết định việc tài khoản có bị thanh lý hay không.',
      watch: 'Đặt 100% với đòn bẩy > 1 nghĩa là một cây nến ngược chiều đủ sâu sẽ xoá sạch tài khoản. Engine mô phỏng đúng điều đó chứ không bỏ qua.',
    },
    'exec.leverage': {
      title: 'Đòn bẩy',
      what: 'Số lần khuếch đại giá trị danh nghĩa so với ký quỹ.',
      how: 'Ký quỹ × đòn bẩy = giá trị vị thế. Lãi và lỗ đều nhân lên bấy nhiêu lần.',
      watch: 'Vị thế bị thanh lý trong nến khi lỗ chạm mức ký quỹ đã đặt — kiểm tra theo giá thấp nhất (lệnh mua) hoặc cao nhất (lệnh bán) của nến, nên một cái râu nến cũng đủ.',
    },
    'exec.fee': {
      title: 'Phí giao dịch',
      what: 'Phí mỗi chiều, tính trên giá trị danh nghĩa.',
      how: 'Mặc định 0.04% là phí taker của Binance futures. Một lệnh trọn vẹn trả phí hai lần.',
      watch: 'Chiến lược tần suất cao rất nhạy với con số này. Nếu chỉ báo lãi khi phí = 0 mà lỗ khi phí = 0.04% thì nó không có lợi thế thật.',
    },
    'exec.slippage': {
      title: 'Trượt giá',
      what: 'Mức giá xấu đi so với giá khớp lý thuyết, mỗi chiều.',
      how: 'Luôn theo hướng bất lợi: lệnh mua khớp cao hơn, lệnh bán khớp thấp hơn.',
      watch: 'Trượt giá thật phụ thuộc thanh khoản và cỡ lệnh, không phải hằng số. Con số cố định ở đây là xấp xỉ lạc quan cho lệnh lớn.',
    },

    // ---------- backtest metrics ----------
    'm.total_return': {
      title: 'Tổng lợi nhuận',
      what: 'Phần trăm thay đổi của vốn từ đầu tới cuối giai đoạn.',
      watch: 'Tự nó không nói gì về rủi ro. Luôn đọc kèm sụt giảm tối đa và so với mua-và-giữ.',
    },
    'm.buy_hold': {
      title: 'Mua và giữ',
      what: 'Lợi nhuận nếu chỉ mua ở nến đầu và giữ tới nến cuối, trên đúng giai đoạn đó.',
      how: 'Đây là mốc so sánh đúng. Một chiến lược lãi 40% trong giai đoạn mua-và-giữ lãi 120% đã thua, dù con số 40% trông đẹp.',
    },
    'm.cagr': {
      title: 'CAGR — tăng trưởng kép hằng năm',
      what: 'Tốc độ tăng trưởng đều tương đương, quy về một năm.',
      formula: '(vốn cuối / vốn đầu)^(1/số năm) − 1',
      watch: 'Trên giai đoạn ngắn hơn một năm, CAGR ngoại suy mạnh và có thể ra con số vô lý. Kiểm tra số năm thực tế trước khi trích dẫn nó.',
    },
    'm.max_dd': {
      title: 'Sụt giảm tối đa',
      what: 'Mức rơi sâu nhất từ một đỉnh vốn xuống đáy kế tiếp.',
      how: 'Đây là con số quyết định bạn có giữ được chiến lược hay không. Một hệ thống lãi 200%/năm với sụt giảm 70% là thứ hầu hết mọi người sẽ bỏ giữa chừng.',
      watch: 'Sụt giảm quá khứ là cận dưới, không phải cận trên. Sụt giảm tương lai gần như luôn sâu hơn mức tệ nhất trong backtest.',
    },
    'm.sharpe': {
      title: 'Sharpe',
      what: 'Lợi suất trung bình chia độ lệch chuẩn, quy về năm. Lãi suất phi rủi ro coi bằng 0.',
      formula: '√(số nến/năm) × trung bình(lợi suất) / độ lệch chuẩn(lợi suất)',
      watch: 'Giả định lợi suất phân phối chuẩn. Kiểm định Jarque–Bera ở tab Thống kê hầu như luôn bác bỏ điều đó, nên Sharpe đánh giá thấp rủi ro đuôi. Với chiến lược được chọn ra từ một lần quét tham số, hãy đọc Sharpe khử phồng (DSR) thay vì Sharpe thô.',
    },
    'm.sortino': {
      title: 'Sortino',
      what: 'Như Sharpe nhưng chỉ phạt biến động theo chiều xuống.',
      how: 'Cao hơn Sharpe nghĩa là phần lớn biến động của chiến lược là biến động có lợi.',
    },
    'm.profit_factor': {
      title: 'Hệ số lợi nhuận',
      what: 'Tổng lãi của các lệnh thắng chia tổng lỗ của các lệnh thua.',
      how: '1.0 là hoà vốn trước phí. Trên 1.5 là đáng chú ý; trên 3.0 với ít lệnh thì gần như chắc chắn là khớp nhiễu.',
      watch: 'Nhạy cực mạnh với một lệnh lãi lớn duy nhất. Kiểm tra lệnh tốt nhất chiếm bao nhiêu phần trăm tổng lãi trước khi tin con số này.',
    },
    'm.win_rate': {
      title: 'Tỷ lệ thắng',
      what: 'Phần trăm lệnh có lãi.',
      watch: 'Tự nó vô nghĩa. Một hệ thống thắng 30% với tỷ lệ lãi/lỗ 4:1 lãi nhiều hơn hệ thống thắng 70% với tỷ lệ 1:3. Luôn đọc kèm hệ số lợi nhuận.',
    },
    'm.expectancy': {
      title: 'Kỳ vọng mỗi lệnh',
      what: 'Lãi lỗ trung bình của một lệnh, tính bằng tiền.',
      formula: '(tỷ lệ thắng × lãi TB) − (tỷ lệ thua × lỗ TB)',
      how: 'Đây là con số nhân với số lệnh sẽ ra lợi nhuận kỳ vọng. Âm nghĩa là càng giao dịch nhiều càng lỗ.',
    },
    'm.payoff': {
      title: 'Tỷ lệ lãi/lỗ',
      what: 'Lãi trung bình của lệnh thắng chia lỗ trung bình của lệnh thua.',
      how: 'Cùng với tỷ lệ thắng, hai số này quyết định hệ thống có kỳ vọng dương hay không.',
    },
    'm.exposure': {
      title: 'Thời gian nắm giữ',
      what: 'Phần trăm số nến có vị thế mở.',
      how: 'Phơi nhiễm thấp mà lợi nhuận tương đương mua-và-giữ nghĩa là vốn rảnh phần lớn thời gian — có thể dùng cho việc khác.',
      watch: 'Phơi nhiễm rất thấp (dưới 5%) thường đi kèm rất ít lệnh, và mọi thống kê trên đó đều thiếu tin cậy.',
    },
    'm.ulcer': {
      title: 'Chỉ số Ulcer',
      what: 'Căn bậc hai trung bình bình phương của mức sụt giảm, đo qua toàn bộ đường vốn.',
      how: 'Khác sụt giảm tối đa ở chỗ nó phạt cả độ sâu lẫn độ dài. Hai chiến lược cùng sụt 30% nhưng một cái hồi trong một tháng, một cái hồi trong hai năm — Ulcer phân biệt được, sụt giảm tối đa thì không.',
      formula: '√( trung bình( sụt giảm² ) )',
    },
    'm.upi': {
      title: 'UPI — chỉ số hiệu quả Ulcer',
      what: 'CAGR chia chỉ số Ulcer.',
      how: 'Cùng ý tưởng với Sharpe nhưng mẫu số là nỗi đau thực tế của việc nắm giữ, không phải độ lệch chuẩn.',
    },
    'm.car_mdd': {
      title: 'CAR/MDD',
      what: 'Tăng trưởng hằng năm chia sụt giảm tối đa. Còn gọi là hệ số MAR hoặc Calmar.',
      how: 'Trả lời trực tiếp: mỗi phần trăm sụt giảm phải chịu đổi lấy bao nhiêu phần trăm lợi nhuận. Trên 1.0 là tốt với hệ thống dài hạn.',
    },
    'm.recovery': {
      title: 'Hệ số phục hồi',
      what: 'Tổng lợi nhuận chia sụt giảm tối đa.',
      how: 'Giống CAR/MDD nhưng dùng lợi nhuận tuyệt đối thay vì tăng trưởng hằng năm, nên nó thiên vị giai đoạn dài.',
    },
    'm.k_ratio': {
      title: 'Hệ số K',
      what: 'Độ dốc của đường vốn (thang log) chia sai số chuẩn của độ dốc đó.',
      how: 'Đo tính *đều đặn* của tăng trưởng, chứ không chỉ độ lớn. Đường vốn đi lên thẳng cho hệ số K cao; đường lên bằng đúng một cú nhảy cho hệ số K thấp dù tổng lợi nhuận như nhau.',
    },
    'm.consecutive': {
      title: 'Chuỗi thắng / thua dài nhất',
      what: 'Số lệnh thắng liên tiếp nhiều nhất, và số lệnh thua liên tiếp nhiều nhất.',
      how: 'Chuỗi thua dài nhất là thứ cần biết trước khi chạy thật: đây là số lệnh liên tiếp bạn phải chịu đựng mà không mất niềm tin vào hệ thống.',
      watch: 'Chuỗi thua tương lai gần như chắc chắn dài hơn chuỗi dài nhất trong backtest — đơn giản vì tương lai có nhiều lệnh hơn.',
    },
    'm.mae': {
      title: 'MAE — mức lỗ tạm thời sâu nhất',
      what: 'Với mỗi lệnh, mức lỗ sâu nhất từng chạm trước khi lệnh đóng.',
      how: 'MAE của các lệnh *thắng* cho biết dừng lỗ nên đặt ở đâu: đặt chặt hơn MAE của lệnh thắng nghĩa là cắt mất chính những lệnh sẽ có lãi.',
    },
    'm.mfe': {
      title: 'MFE — mức lãi tạm thời cao nhất',
      what: 'Với mỗi lệnh, mức lãi cao nhất từng chạm trước khi lệnh đóng.',
      how: 'MFE của các lệnh *thua* cho biết đã bỏ lỡ bao nhiêu: nếu lệnh thua thường xanh 3% trước khi đỏ, một mức chốt lãi có thể cứu chúng.',
    },
    'm.liquidation': {
      title: 'Số lần thanh lý',
      what: 'Số lệnh bị đóng cưỡng chế vì lỗ chạm mức ký quỹ.',
      watch: 'Bất kỳ con số nào lớn hơn 0 nghĩa là đòn bẩy đang quá cao so với biến động của thị trường này. Kết quả vẫn được tính đúng, nhưng chiến lược đang chơi ở vùng mà một cây nến xấu là mất trắng.',
    },

    // ---------- ML ----------
    'ml.accuracy': {
      title: 'Độ chính xác',
      what: 'Phần trăm nến mà tín hiệu đoán đúng hướng của nến kế tiếp.',
      watch: 'Con số gây hiểu lầm nhiều nhất trong đánh giá ML tài chính. Nếu thị trường tăng 55% số nến thì đoán "tăng" mọi lúc đã đạt 55%. Luôn so với đường cơ sở, không so với 50%.',
    },
    'ml.baseline': {
      title: 'Đường cơ sở',
      what: 'Độ chính xác của quy tắc ngây thơ nhất: luôn đoán lớp phổ biến nhất.',
      how: 'Mô hình chỉ có giá trị khi vượt được con số này. Vượt 1–2 điểm phần trăm trên vài nghìn nến thường nằm trong sai số lấy mẫu.',
    },
    'ml.precision': {
      title: 'Precision',
      what: 'Trong các nến mô hình báo "tăng", bao nhiêu phần trăm thật sự tăng.',
      how: 'Đây là con số gắn trực tiếp với tiền: mỗi tín hiệu sai là một lệnh thua có phí.',
    },
    'ml.recall': {
      title: 'Recall',
      what: 'Trong các nến thật sự tăng, mô hình bắt được bao nhiêu phần trăm.',
      how: 'Recall thấp nghĩa là bỏ lỡ cơ hội — ít tốn kém hơn precision thấp, vì bỏ lỡ không mất phí.',
    },
    'ml.f1': {
      title: 'F1',
      what: 'Trung bình điều hoà của precision và recall.',
      how: 'Một con số duy nhất khi cần cân bằng hai thứ. Không thay thế được việc nhìn cả hai riêng rẽ, vì chi phí của hai loại sai là khác nhau.',
    },
    'ml.mcc': {
      title: 'Hệ số tương quan Matthews',
      what: 'Tương quan giữa dự đoán và thực tế, trong khoảng −1 tới +1.',
      how: '0 là đoán mò. Đây là thước đo đáng tin nhất khi hai lớp lệch nhau, vì nó dùng cả bốn ô của ma trận nhầm lẫn.',
    },
    'ml.auc': {
      title: 'ROC-AUC',
      what: 'Xác suất mô hình chấm điểm một nến tăng cao hơn một nến giảm, khi lấy ngẫu nhiên mỗi loại một cái.',
      how: '0.5 là vô dụng. Với dữ liệu tài chính, 0.55 đã là đáng kể và 0.70 gần như chắc chắn là rò rỉ dữ liệu tương lai.',
      watch: 'AUC không quan tâm ngưỡng, nên AUC tốt không đảm bảo chiến lược có lãi ở ngưỡng đang dùng.',
    },
    'ml.brier': {
      title: 'Điểm Brier',
      what: 'Sai số bình phương trung bình giữa xác suất dự báo và kết quả thực tế.',
      how: 'Càng nhỏ càng tốt. Đo *hiệu chuẩn*: một mô hình nói "70%" nên đúng khoảng 70% số lần đó.',
      watch: 'Một mô hình luôn báo 50% có điểm Brier khá tốt mà hoàn toàn vô dụng. Đọc kèm AUC.',
    },
    'ml.logloss': {
      title: 'Log-loss',
      what: 'Phạt theo logarit cho xác suất dự báo sai.',
      how: 'Phạt rất nặng những dự báo tự tin mà sai — đúng thứ cần phạt khi tín hiệu điều khiển cỡ vị thế.',
    },
    'ml.confusion': {
      title: 'Ma trận nhầm lẫn',
      what: 'Bảng đếm bốn trường hợp: đoán tăng/thật tăng, đoán tăng/thật giảm, và hai ô còn lại.',
      how: 'Mọi chỉ số phân loại đều tính ra từ bảng này. Khi một chỉ số trông lạ, bảng này cho biết vì sao.',
    },

    // ---------- portfolio ----------
    'p.risk_contribution': {
      title: 'Đóng góp rủi ro',
      what: 'Phần rủi ro toàn danh mục đến từ một vị thế, sau khi tính cả cách nó di chuyển cùng các vị thế khác.',
      formula: 'wᵢ × (Σw)ᵢ / (wᵀΣw)',
      how: 'Đây là con số quan trọng nhất của trang này. Bạn đã biết mỗi mã chiếm bao nhiêu phần trăm *tiền*; điều bạn không thấy là một mã chiếm 25% tiền có thể chiếm 45% rủi ro vì nó đi cùng chiều với phần còn lại.',
    },
    'p.effective_bets': {
      title: 'Số cược độc lập hiệu dụng',
      what: 'Số vị thế thực sự độc lập, sau khi trừ đi phần tương quan.',
      formula: 'N / (1 + (N − 1) × tương quan trung bình)',
      how: 'Mười mã cùng ngành với tương quan trung bình 0.7 hành xử như khoảng ba cược, không phải mười. Đây là con số nói ra điều đó.',
    },
    'p.herfindahl': {
      title: 'Chỉ số Herfindahl',
      what: 'Tổng bình phương tỷ trọng.',
      how: 'Nghịch đảo của nó là "số mã hiệu dụng" theo tiền: danh mục 10 mã đều nhau cho 10, còn 10 mã mà một mã chiếm 80% thì chỉ cho khoảng 1.5.',
    },
    'p.beta': {
      title: 'Beta so với VN-Index',
      what: 'Danh mục nhận bao nhiêu phần trăm mức dao động của chỉ số.',
      how: 'Beta 1.2 nghĩa là chỉ số giảm 10% thì danh mục có xu hướng giảm 12%.',
      watch: 'Beta ước lượng từ quá khứ và không ổn định qua các chế độ thị trường. Nó cũng chỉ giải thích phần rủi ro đi cùng thị trường, không phải toàn bộ.',
    },
    'p.var': {
      title: 'VaR 95% (một phiên)',
      what: 'Mức lỗ mà 5% số phiên tệ nhất vượt qua, đo bằng mô phỏng lịch sử.',
      watch: 'VaR không nói gì về mức lỗ *khi* đã vượt ngưỡng. Đó là việc của CVaR ngay bên cạnh.',
    },
    'p.cvar': {
      title: 'CVaR 95% (một phiên)',
      what: 'Mức lỗ trung bình trong đúng 5% số phiên tệ nhất.',
      how: 'Đây mới là con số mô tả một ngày xấu thật sự. Luôn sâu hơn VaR.',
    },
    'p.correlation': {
      title: 'Tương quan trung bình',
      what: 'Trung bình hệ số tương quan giữa mọi cặp mã trong danh mục.',
      watch: 'Tương quan tăng vọt đúng lúc thị trường sụp. Đa dạng hoá đo trong giai đoạn yên bình luôn lạc quan hơn thực tế lúc cần nó nhất.',
    },
    'p.shrinkage': {
      title: 'Co rút Ledoit–Wolf',
      what: 'Ma trận hiệp phương sai mẫu được kéo về một mục tiêu tương quan hằng số.',
      how: 'Với khoảng 250 phiên và 10–30 mã, hiệp phương sai mẫu ước lượng rất tệ và mọi thứ tính từ nó còn tệ hơn. Co rút là cách xử lý tiêu chuẩn, không phải một tuỳ chọn nâng cao.',
    },
  };

  return { init, define, defineAll, get, button, inline, fromTest, fmt, pFormat };
})();
