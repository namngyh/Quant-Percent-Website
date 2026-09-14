/* Vietnamese and English, switchable without a reload.
 *
 * Three kinds of text have to be handled, and they are handled differently:
 *
 * 1. **Static markup.** Anything in index.html carries `data-i18n="key"` (or
 *    `data-i18n-title`, `data-i18n-placeholder`). `I18n.apply()` walks the
 *    document and rewrites them.
 * 2. **Text built in JavaScript.** Modules call `t('key')`, or `t('key', {n})`
 *    for a substitution. Re-rendering is what switches them, so every panel
 *    registers a redraw with `I18n.onChange`.
 * 3. **Prose computed by the backend.** Statistical conclusions, assumptions,
 *    portfolio notes. Those arrive as `{vi, en}` pairs and are unwrapped by
 *    `I18n.pick`, so switching language re-renders from data already in hand
 *    rather than refetching.
 *
 * Vietnamese is the default: it is the language the platform was built in and
 * the one its owner works in. English is the alternative, not the base.
 *
 * A missing key renders the key itself rather than an empty string. A blank
 * label is invisible in review; `strategy.runBacktest` is not.
 */

const I18n = (() => {
  const KEY = 'qp.lang.v1';
  const LANGS = ['vi', 'en'];

  let lang = 'vi';
  const listeners = new Set();

  const DICT = {
    // ---------------- top bar
    'top.starSymbol':     { vi: 'Đánh dấu mã này', en: 'Star this symbol' },
    'top.symbol':         { vi: 'Mã', en: 'Symbol' },
    'top.timeframes':     { vi: 'Khung thời gian', en: 'Timeframe' },
    'top.bars':           { vi: 'Số nến hiển thị', en: 'Bars shown' },
    'top.tz':             { vi: 'Mọi giờ trên biểu đồ là giờ Việt Nam', en: 'All chart times are Vietnam time' },
    'top.live':           { vi: 'Realtime', en: 'Realtime' },
    'top.liveToggle':     { vi: 'Bật/tắt nến realtime', en: 'Turn realtime candles on or off' },
    'top.backfill':       { vi: 'Cập nhật dữ liệu', en: 'Update data' },
    'top.lang':           { vi: 'Ngôn ngữ', en: 'Language' },

    'live.watching':      { vi: 'Đang theo dõi', en: 'Watching' },
    'live.running':       { vi: 'Đang chạy', en: 'Streaming' },
    'live.connecting':    { vi: 'Đang nối…', en: 'Connecting…' },
    'live.offline':       { vi: 'Mất kết nối', en: 'Disconnected' },
    'live.error':         { vi: 'Lỗi', en: 'Error' },

    'status.bars':        { vi: '{n} nến', en: '{n} bars' },
    'status.noData':      { vi: 'Chưa có dữ liệu cho khung này', en: 'No data for this timeframe' },
    'status.loading':     { vi: 'Đang tải dữ liệu từ Binance…', en: 'Downloading from Binance…' },
    'status.catchUp':     { vi: 'Đang bù {n} nến còn thiếu…', en: 'Backfilling {n} missing bars…' },
    'status.vnDown':      { vi: 'Thị trường VN không khả dụng: {msg}', en: 'Vietnam market unavailable: {msg}' },
    'status.noBackend':   { vi: 'Không kết nối được backend: {msg}', en: 'Cannot reach the backend: {msg}' },

    // ---------------- rail
    'rail.indicators':    { vi: 'Chỉ báo', en: 'Indicators' },
    'rail.strategy':      { vi: 'Chiến lược', en: 'Strategies' },
    'rail.results':       { vi: 'Kết quả', en: 'Results' },
    'rail.portfolio':     { vi: 'Danh mục', en: 'Portfolio' },
    'rail.paper':         { vi: 'Paper', en: 'Paper' },
    'rail.panels':        { vi: 'Bảng điều khiển', en: 'Panels' },

    // ---------------- chart tools
    'chart.markers':      { vi: '{n} dấu lệnh', en: '{n} trade marks' },
    'chart.hideMarkers':  { vi: 'Ẩn dấu ra vào lệnh khỏi biểu đồ', en: 'Hide entry and exit marks' },
    'chart.showMarkers':  { vi: 'Hiện lại dấu ra vào lệnh', en: 'Show entry and exit marks again' },
    'chart.clearMarkers': { vi: 'Xoá hẳn dấu lệnh khỏi biểu đồ', en: 'Remove trade marks from the chart' },
    'chart.markersShown': { vi: 'Đã hiện dấu lệnh', en: 'Trade marks shown' },
    'chart.markersHidden':{ vi: 'Đã ẩn dấu lệnh', en: 'Trade marks hidden' },
    'chart.markersGone':  { vi: 'Đã xoá dấu lệnh khỏi biểu đồ', en: 'Trade marks removed' },

    // ---------------- indicators panel
    'ind.title':          { vi: 'Chỉ báo', en: 'Indicators' },
    'ind.search':         { vi: 'Tìm chỉ báo (ema, rsi, macd…)', en: 'Search indicators (ema, rsi, macd…)' },
    'ind.import':         { vi: 'Nhập .py', en: 'Import .py' },
    'ind.format':         { vi: 'Xem định dạng file .py', en: 'See the .py file format' },
    'ind.active':         { vi: 'Đang bật', en: 'Active' },
    'ind.clearAll':       { vi: 'Xóa hết', en: 'Clear all' },
    'ind.none':           { vi: 'Chưa có chỉ báo nào.', en: 'No indicators yet.' },
    'ind.explain':        { vi: 'Giải thích chỉ báo', en: 'Explain this indicator' },

    // ---------------- strategy panel
    'st.title':           { vi: 'Chiến lược', en: 'Strategies' },
    'st.star':            { vi: 'Đánh dấu chiến lược này', en: 'Star this strategy' },
    'st.explain':         { vi: 'Giải thích chiến lược', en: 'Explain this strategy' },
    'st.tabRun':          { vi: 'Chạy', en: 'Run' },
    'st.tabOpt':          { vi: 'Tối ưu', en: 'Optimise' },
    'st.tabCheck':        { vi: 'Kiểm định', en: 'Validate' },
    'st.params':          { vi: 'Tham số', en: 'Parameters' },
    'st.costs':           { vi: 'Chi phí & vốn', en: 'Costs & capital' },
    'st.capital':         { vi: 'Vốn ban đầu', en: 'Initial capital' },
    'st.size':            { vi: '% vốn/lệnh', en: '% equity per trade' },
    'st.leverage':        { vi: 'Đòn bẩy', en: 'Leverage' },
    'st.fee':             { vi: 'Phí (%)', en: 'Fee (%)' },
    'st.slippage':        { vi: 'Trượt giá (%)', en: 'Slippage (%)' },
    'st.runBacktest':     { vi: 'Chạy backtest', en: 'Run backtest' },
    'st.startPaper':      { vi: 'Chạy paper trading', en: 'Start paper trading' },
    'st.sweepHint':       { vi: 'Tích tham số cần quét và đặt dải giá trị.', en: 'Tick the parameters to sweep and set their ranges.' },
    'st.sweepMode':       { vi: 'Cách quét', en: 'Search' },
    'st.sweepGrid':       { vi: 'Quét cạn', en: 'Exhaustive grid' },
    'st.sweepRandom':     { vi: 'Ngẫu nhiên', en: 'Random' },
    'st.samples':         { vi: 'Số mẫu', en: 'Samples' },
    'st.rankBy':          { vi: 'Xếp hạng theo', en: 'Rank by' },
    'st.runOptimize':     { vi: 'Chạy tối ưu', en: 'Run optimisation' },

    'wf.title':           { vi: 'Walk-forward', en: 'Walk-forward' },
    'wf.train':           { vi: 'Cửa sổ huấn luyện', en: 'Training window' },
    'wf.test':            { vi: 'Cửa sổ kiểm tra', en: 'Test window' },
    'wf.purge':           { vi: 'Nến cách ly', en: 'Purged bars' },
    'wf.foldMode':        { vi: 'Kiểu cửa sổ', en: 'Window type' },
    'wf.rolling':         { vi: 'Trượt', en: 'Rolling' },
    'wf.anchored':        { vi: 'Neo gốc', en: 'Anchored' },
    'wf.run':             { vi: 'Chạy walk-forward', en: 'Run walk-forward' },
    'mc.title':           { vi: 'Monte Carlo', en: 'Monte Carlo' },
    'mc.sims':            { vi: 'Số mô phỏng', en: 'Simulations' },
    'mc.run':             { vi: 'Chạy Monte Carlo', en: 'Run Monte Carlo' },
    'stat.title':         { vi: 'Kiểm định thống kê', en: 'Statistical tests' },
    'stat.series':        { vi: 'Phân tích chuỗi giá', en: 'Analyse the price series' },
    'stat.strategy':      { vi: 'Kiểm định chiến lược', en: 'Test this strategy' },
    'cmp.title':          { vi: 'So sánh chiến lược', en: 'Compare strategies' },
    'cmp.hint':           { vi: 'Chạy nhiều chiến lược trên cùng dữ liệu, cùng chi phí.', en: 'Run several strategies over the same data and the same costs.' },
    'cmp.run':            { vi: 'So sánh', en: 'Compare' },

    // ---------------- results panel
    'res.title':          { vi: 'Kết quả', en: 'Results' },
    'res.summary':        { vi: 'Tổng quan', en: 'Overview' },
    'res.trades':         { vi: 'Lệnh', en: 'Trades' },
    'res.optimize':       { vi: 'Tối ưu', en: 'Optimise' },
    'res.validation':     { vi: 'Kiểm định', en: 'Validation' },
    'res.stats':          { vi: 'Thống kê', en: 'Statistics' },
    'res.report':         { vi: 'Báo cáo', en: 'Report' },
    'res.reportTitle':    { vi: 'Mở báo cáo backtest đầy đủ', en: 'Open the full backtest report' },
    'res.csv':            { vi: 'Tải danh sách lệnh ra CSV', en: 'Download the trade list as CSV' },
    'res.png':            { vi: 'Tải biểu đồ ra ảnh PNG', en: 'Download the chart as a PNG' },
    'res.equity':         { vi: 'Đường vốn', en: 'Equity curve' },
    'res.runFirst':       { vi: 'Chạy một backtest để xem kết quả.', en: 'Run a backtest to see results.' },
    'res.noTrades':       { vi: 'Chưa có lệnh nào.', en: 'No trades yet.' },
    'res.noOpt':          { vi: 'Chưa chạy tối ưu.', en: 'No optimisation run yet.' },
    'res.noValidation':   { vi: 'Chạy walk-forward, Monte Carlo hoặc so sánh ở tab Chiến lược → Kiểm định.', en: 'Run walk-forward, Monte Carlo or a comparison from Strategies → Validate.' },
    'res.noStats':        { vi: 'Chạy kiểm định thống kê ở tab Chiến lược → Kiểm định.', en: 'Run the statistical tests from Strategies → Validate.' },

    // ---------------- portfolio panel
    'pf.title':           { vi: 'Danh mục', en: 'Portfolio' },
    'pf.about':           { vi: 'Trang này đo cái gì', en: 'What this page measures' },
    'pf.lead':            { vi: 'Nhập vị thế cổ phiếu Việt Nam của bạn. Mọi con số đo từ chính lịch sử giá mà database của team có, không có lợi suất hay tương quan giả định. Không có gì được lưu lại.', en: 'Enter your Vietnamese equity positions. Every number is measured from the price history the team database holds: no assumed returns, no assumed correlations. Nothing is stored.' },
    'pf.add':             { vi: '+ Thêm mã', en: '+ Add a symbol' },
    'pf.quickAdd':        { vi: 'Thêm nhanh:', en: 'Quick add:' },
    'pf.cash':            { vi: 'Tiền mặt (đồng)', en: 'Cash (VND)' },
    'pf.lookback':        { vi: 'Cửa sổ đo', en: 'Measurement window' },
    'pf.horizon':         { vi: 'Kỳ dự phóng', en: 'Projection horizon' },
    'pf.run':             { vi: 'Phân tích danh mục', en: 'Analyse portfolio' },
    'pf.symbolCount':     { vi: '{n} mã', en: '{n} symbols' },
    'pf.ready':           { vi: '{n} mã trên sàn, sẵn sàng.', en: '{n} listed symbols loaded.' },
    'pf.quantity':        { vi: 'Số lượng', en: 'Quantity' },
    'pf.costBasis':       { vi: 'Giá vốn/cổ', en: 'Cost per share' },
    'pf.optional':        { vi: 'không bắt buộc', en: 'optional' },
    'pf.remove':          { vi: 'Bỏ mã này', en: 'Remove this symbol' },
    'pf.unknown':         { vi: 'không có mã này trên sàn', en: 'not a listed symbol' },
    'pf.badQuantity':     { vi: '{sym}: thiếu số lượng, hoặc số lượng không hợp lệ.', en: '{sym}: missing or invalid quantity.' },
    'pf.duplicate':       { vi: '{sym} bị nhập hai lần.', en: '{sym} was entered twice.' },
    'pf.empty':           { vi: 'Chưa nhập mã nào.', en: 'No symbols entered.' },
    'pf.m6':              { vi: '6 tháng', en: '6 months' },
    'pf.y1':              { vi: '1 năm', en: '1 year' },
    'pf.y2':              { vi: '2 năm', en: '2 years' },
    'pf.m1':              { vi: '1 tháng', en: '1 month' },
    'pf.m3':              { vi: '3 tháng', en: '3 months' },

    // ---------------- paper panel
    'paper.title':        { vi: 'Paper trading', en: 'Paper trading' },
    'paper.refresh':      { vi: 'Làm mới', en: 'Refresh' },
    'paper.lead':         { vi: 'Chạy chiến lược tiến về phía trước trên dữ liệu thật, tiền ảo. Dùng đúng luật khớp lệnh của backtest: tín hiệu ở nến đóng, khớp ở giá mở nến kế tiếp. Phiên vẫn chạy khi bạn đóng trình duyệt.', en: 'Run a strategy forward on live data with imaginary money. Same fill rules as the backtest: the signal comes from a closed bar and fills at the next bar’s open. Sessions keep running when you close the browser.' },
    'tg.title':           { vi: 'Thông báo Telegram', en: 'Telegram notifications' },
    'tg.help':            { vi: 'Cách lấy token và chat id', en: 'How to get a token and chat id' },
    'tg.token':           { vi: 'Bot token', en: 'Bot token' },
    'tg.chat':            { vi: 'Chat id', en: 'Chat id' },
    'tg.save':            { vi: 'Lưu', en: 'Save' },
    'tg.test':            { vi: 'Gửi tin thử', en: 'Send a test' },
    'tg.clear':           { vi: 'Xoá', en: 'Clear' },
    'tg.clearTitle':      { vi: 'Xoá token khỏi máy', en: 'Remove the token from this machine' },
    'tg.checking':        { vi: 'Đang kiểm tra…', en: 'Checking…' },
    'tg.privacy':         { vi: 'Token được ghi vào file .env trên máy bạn (file này đã nằm trong .gitignore nên không bao giờ lên git. Trang này chỉ hiển thị lại token đã che.', en: 'The token is written to .env on this machine (that file is gitignored, so it never reaches git. This page only ever shows it back masked.' },
    'tg.on':              { vi: 'Đang bật qua <strong>@{bot}</strong>. Mỗi lần phiên paper vào hoặc đóng lệnh sẽ có tin nhắn.', en: 'Active via <strong>@{bot}</strong>. You get a message whenever a paper session opens or closes a trade.' },
    'tg.off':             { vi: 'Chưa bật.', en: 'Not configured.' },
    'tg.needToken':       { vi: 'Dán bot token vào ô phía trên.', en: 'Paste the bot token into the field above.' },
    'tg.needChat':        { vi: 'Thiếu chat id.', en: 'Chat id is missing.' },
    'tg.saved':           { vi: 'Đã lưu. Bấm "Gửi tin thử" để chắc chắn chat id đúng.', en: 'Saved. Press “Send a test” to confirm the chat id is right.' },
    'tg.sent':            { vi: 'Đã gửi tin thử: kiểm tra Telegram', en: 'Test sent: check Telegram' },
    'tg.cleared':         { vi: 'Đã xoá token khỏi máy.', en: 'Token removed from this machine.' },
    'tg.saving':          { vi: 'Đang kiểm tra…', en: 'Verifying…' },
    'tg.sending':         { vi: 'Đang gửi…', en: 'Sending…' },
    'tg.clearing':        { vi: 'Đang xoá…', en: 'Clearing…' },

    // ---------------- report window
    'rp.overview':        { vi: 'Tổng quan', en: 'Overview' },
    'rp.trades':          { vi: 'Lệnh', en: 'Trades' },
    'rp.risk':            { vi: 'Rủi ro', en: 'Risk' },
    'rp.riskTools':       { vi: 'Quản trị rủi ro', en: 'Risk management' },
    'ps.title':           { vi: 'Cài đặt Paper Trading', en: 'Paper trading settings' },
    'ps.hint':            { vi: 'Phiên paper sẽ khoá các thông số này lúc bắt đầu. Đổi ở đây không ảnh hưởng tới phiên đang chạy, và cũng không ảnh hưởng tới backtest.',
                            en: 'A paper session freezes these when it starts. Changing them here does not affect a running session, and does not affect the backtest.' },
    'ps.preset':          { vi: 'Sàn', en: 'Venue' },
    'ps.custom':          { vi: 'Tự đặt', en: 'Custom' },
    'ps.copy':            { vi: 'Lấy từ backtest', en: 'Copy from backtest' },
    'ps.start':           { vi: 'Bắt đầu phiên', en: 'Start session' },
    'ps.manual':          { vi: 'Giao dịch tay', en: 'Manual trading' },
    'ps.manualOn':        { vi: 'Giao dịch tay trên {symbol}',
                            en: 'Trade {symbol} by hand' },
    'ps.pickMarket':      { vi: 'Chọn một mã ở thanh trên rồi bấm vào đây.',
                            en: 'Pick a symbol in the bar above, then press here.' },
    'top.trade':          { vi: 'Giao dịch', en: 'Trade' },
    'top.overview':       { vi: 'Tổng quan', en: 'Overview' },
    'chart.type':         { vi: 'Kiểu biểu đồ', en: 'Chart type' },
    'paper.account':      { vi: 'Tài khoản', en: 'Account' },
    'pf.paper':           { vi: 'Paper trading cả danh mục',
                            en: 'Paper trade the whole portfolio' },
    'draw.undo':          { vi: 'Hoàn tác hình vừa vẽ', en: 'Undo the last shape' },
    'draw.clear':         { vi: 'Xoá hết hình vẽ', en: 'Remove all drawings' },
    'draw.remove':        { vi: 'Xoá hình đang chọn (phím Delete)',
                            en: 'Delete the selected shape (Delete key)' },
    'draw.pick':          { vi: 'Bấm vào một hình để chọn, rồi bấm Delete',
                            en: 'Click a shape to select it, then press Delete' },
    'draw.magnet':        { vi: 'Nam châm: bám vào giá O/H/L/C của nến',
                            en: 'Magnet: snap to the bar’s O/H/L/C' },
    'draw.lock':          { vi: 'Khoá, không kéo được hình', en: 'Lock: shapes cannot be moved' },
    'draw.hide':          { vi: 'Ẩn/hiện toàn bộ hình vẽ', en: 'Show or hide all drawings' },
    'splash.charting':    { vi: 'Biểu đồ bởi', en: 'Charting powered by' },
    'st.period':          { vi: 'Khoảng thời gian', en: 'Date range' },
    'st.periodHint':      { vi: 'Bỏ trống là dùng số nến gần nhất.',
                            en: 'Leave empty to use the most recent bars.' },
    'st.from':            { vi: 'Từ ngày', en: 'From' },
    'st.to':              { vi: 'Đến ngày', en: 'To' },

    // Hints and dialog chrome that were left as bare Vietnamese in index.html.
    'wf.hint':            { vi: 'Tối ưu trên một cửa sổ rồi áp <em>nguyên tham số đó</em> lên cửa sổ kế tiếp. Đây là phép thử trung thực nhất có ở đây, và cũng là phép thử khắt khe nhất: kết quả thường tệ hơn <strong>Tối ưu</strong> rất nhiều.',
                            en: 'Optimise on one window, then apply <em>those exact parameters</em> to the next one. It is the most honest test here and also the harshest: results are usually far worse than <strong>Optimise</strong> suggests.' },
    'wf.bars':            { vi: 'Cần nhiều nến: với cửa sổ mặc định, hãy đặt số nến từ 5&nbsp;000 trở lên để có đủ 3–5 vòng.',
                            en: 'Needs plenty of bars: at the default windows, set 5,000 or more so there are 3–5 folds.' },
    'mc.hint':            { vi: 'Xáo lại thứ tự các lệnh nhiều lần để biết kết quả thật nằm ở đâu trong vùng hợp lý.',
                            en: 'Reshuffle the trade order many times to see where the real result sits within the plausible range.' },
    'stats.hint':         { vi: 'Dữ liệu có gì để khai thác không, và lợi thế quan sát được có khác 0 một cách có ý nghĩa thống kê không.',
                            en: 'Whether the data has anything to exploit, and whether the observed edge differs from zero in a statistically meaningful way.' },
    'dlg.format':         { vi: 'Định dạng file', en: 'File format' },
    'dlg.sample':         { vi: 'Tải file mẫu', en: 'Download a sample' },
    'dlg.copy':           { vi: 'Sao chép mã', en: 'Copy the code' },
    'a11y.close':         { vi: 'Đóng', en: 'Close' },
    'a11y.explain':       { vi: 'Giải thích', en: 'Explain' },

    // Hints and dialog chrome that were left as bare Vietnamese in index.html.
    'wf.hint':            { vi: 'Tối ưu trên một cửa sổ rồi áp <em>nguyên tham số đó</em> lên cửa sổ kế tiếp. Đây là phép thử trung thực nhất có ở đây, và cũng là phép thử khắt khe nhất: kết quả thường tệ hơn <strong>Tối ưu</strong> rất nhiều.',
                            en: 'Optimise on one window, then apply <em>those exact parameters</em> to the next one. It is the most honest test here and also the harshest: results are usually far worse than <strong>Optimise</strong> suggests.' },
    'wf.bars':            { vi: 'Cần nhiều nến: với cửa sổ mặc định, hãy đặt số nến từ 5&nbsp;000 trở lên để có đủ 3–5 vòng.',
                            en: 'Needs plenty of bars: at the default windows, set 5,000 or more so there are 3–5 folds.' },
    'mc.hint':            { vi: 'Xáo lại thứ tự các lệnh nhiều lần để biết kết quả thật nằm ở đâu trong vùng hợp lý.',
                            en: 'Reshuffle the trade order many times to see where the real result sits within the plausible range.' },
    'stats.hint':         { vi: 'Dữ liệu có gì để khai thác không, và lợi thế quan sát được có khác 0 một cách có ý nghĩa thống kê không.',
                            en: 'Whether the data has anything to exploit, and whether the observed edge differs from zero in a statistically meaningful way.' },
    'dlg.format':         { vi: 'Định dạng file', en: 'File format' },
    'dlg.sample':         { vi: 'Tải file mẫu', en: 'Download a sample' },
    'dlg.copy':           { vi: 'Sao chép mã', en: 'Copy the code' },
    'a11y.close':         { vi: 'Đóng', en: 'Close' },
    'a11y.explain':       { vi: 'Giải thích', en: 'Explain' },
    'rp.period':          { vi: 'Theo kỳ', en: 'By period' },
    'rp.dist':            { vi: 'Phân phối', en: 'Distribution' },
    'rp.ml':              { vi: 'Học máy', en: 'Machine learning' },
    'mm.title':           { vi: 'Nhiều thị trường', en: 'Many markets' },
    'mm.tab':             { vi: 'Thị trường', en: 'Markets' },
    'mm.add':             { vi: 'Thêm một thị trường', en: 'Add a market' },
    'mm.addCurrent':      { vi: 'Thêm mã đang xem', en: 'Add the charted symbol' },
    'mm.run':             { vi: 'Chạy trên {n} thị trường', en: 'Run across {n} markets' },
    'mm.running':         { vi: 'Đang chạy {n} thị trường…', en: 'Running {n} markets…' },
    'mm.none':            { vi: 'Chọn vài thị trường ở tab Chiến lược → Chạy, rồi bấm chạy.', en: 'Pick a few markets under Strategy → Run, then run them.' },
    'mm.usingTimeframe':  { vi: 'Dùng khung {tf} — theo đúng biểu đồ đang mở.', en: 'Using the {tf} timeframe — whatever the chart is showing.' },
    'mm.remove':          { vi: 'Bỏ khỏi danh sách', en: 'Remove from the list' },
    'mm.profitable':      { vi: 'Thị trường có lãi', en: 'Profitable markets' },
    'mm.medianReturn':    { vi: 'Lợi nhuận trung vị', en: 'Median return' },
    'mm.medianSharpe':    { vi: 'Sharpe trung vị', en: 'Median Sharpe' },
    'mm.best':            { vi: 'Tốt nhất', en: 'Best' },
    'mm.failedMarkets':   { vi: 'Không chạy được', en: 'Did not run' },
    'rp.building':        { vi: 'Đang dựng…', en: 'Building…' },
    'rp.close':           { vi: 'Đóng', en: 'Close' },
    'rp.bars':            { vi: '{n} nến', en: '{n} bars' },
    'rp.tradeCount':      { vi: '{n} lệnh', en: '{n} trades' },
    'rp.pickStrategy':    { vi: 'Chọn một chiến lược ở tab Chiến lược trước.', en: 'Pick a strategy under Strategies first.' },

    // ---------------- portfolio result window
    'pfr.overview':       { vi: 'Tổng quan', en: 'Overview' },
    'pfr.positions':      { vi: 'Từng mã', en: 'Positions' },
    'pfr.diversification':{ vi: 'Đa dạng hoá', en: 'Diversification' },
    'pfr.forward':        { vi: 'Dự phóng', en: 'Projection' },
    'pfr.analysing':      { vi: 'Đang phân tích…', en: 'Analysing…' },

    'resize.panel':       { vi: 'Kéo để đổi bề rộng · nhấn đúp để về mặc định', en: 'Drag to resize · double-click to reset' },
    'resize.panes':       { vi: 'Kéo để đổi chiều cao khung chỉ báo · nhấn đúp để về mặc định', en: 'Drag to resize the indicator panes · double-click to reset' },

    // ---------------- shared
    'common.notAvailable':{ vi: 'không có', en: 'not available' },
    'common.sessions':    { vi: '{n} phiên chung ({from} → {to})', en: '{n} shared sessions ({from} → {to})' },
  };

  // ---------- core ----------

  /** Look up a key, substituting `{name}` placeholders from `vars`. */
  function t(key, vars) {
    const entry = DICT[key];
    if (!entry) {
      console.warn(`I18n: missing key "${key}"`);
      return key;
    }
    const text = entry[lang] ?? entry.vi;
    if (!vars) return text;
    return text.replace(/\{(\w+)\}/g, (match, name) =>
      (name in vars ? String(vars[name]) : match));
  }

  /** Unwrap a `{vi, en}` pair from the backend. Plain strings pass through. */
  function pick(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    return value[lang] ?? value.vi ?? value.en ?? '';
  }

  /** The locale to hand `toLocaleString`, so numbers group the right way. */
  const locale = () => (lang === 'vi' ? 'vi-VN' : 'en-US');

  function apply(root = document) {
    for (const node of root.querySelectorAll('[data-i18n]')) {
      node.textContent = t(node.dataset.i18n);
    }
    for (const node of root.querySelectorAll('[data-i18n-html]')) {
      node.innerHTML = t(node.dataset.i18nHtml);
    }
    for (const node of root.querySelectorAll('[data-i18n-title]')) {
      node.title = t(node.dataset.i18nTitle);
    }
    for (const node of root.querySelectorAll('[data-i18n-placeholder]')) {
      node.placeholder = t(node.dataset.i18nPlaceholder);
    }
    for (const node of root.querySelectorAll('[data-i18n-aria]')) {
      node.setAttribute('aria-label', t(node.dataset.i18nAria));
    }
    document.documentElement.lang = lang;
  }

  function set(next) {
    if (!LANGS.includes(next) || next === lang) return;
    lang = next;
    try {
      localStorage.setItem(KEY, lang);
    } catch {
      // A locked-down browser just means the choice lasts this session.
    }
    apply();
    // Panels re-render themselves; nothing here knows what they are showing.
    for (const fn of listeners) {
      try {
        fn(lang);
      } catch (err) {
        console.error('I18n listener failed', err);
      }
    }
  }

  const onChange = (fn) => listeners.add(fn);

  function init() {
    try {
      const saved = localStorage.getItem(KEY);
      if (LANGS.includes(saved)) lang = saved;
    } catch {
      // Defaults stand.
    }
    apply();
  }

  return {
    init, apply, set, onChange, t, pick, locale,
    get lang() { return lang; },
    get languages() { return [...LANGS]; },
  };
})();

/* Short aliases. These are used on nearly every line of the render functions,
   and `I18n.t(...)` at that density is noise rather than clarity. */
const t = (key, vars) => I18n.t(key, vars);
const tp = (value) => I18n.pick(value);

/* Inline pair, for prose that appears exactly once.
 *
 * The dictionary above is for anything said in more than one place: a label
 * that has to match between a rail button and a panel heading, say. The report
 * and portfolio windows are the opposite case: several hundred sentences, each
 * used once, most of them a full explanation rather than a label. Routing
 * those through keys would mean a dictionary the size of the render code with
 * a key for every sentence, and the two halves would drift the first time
 * someone edited one without the other.
 *
 * Keeping the pair at the point of use means a reader sees both languages
 * together and cannot change one without seeing the other.
 */
const L = (vi, en) => (I18n.lang === 'en' ? en : vi);
