-- Chạy tự động khi container TimescaleDB khởi tạo lần đầu (volume rỗng).
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ===========================================================================
-- Pseudo-tick từ snapshot DataPro /api/symbols/{symbol} (poll ~1s).
-- Emit khi (price, vol, bid, ask) thay đổi. ts = thời điểm quan sát (UTC).
-- volume = delta VOL giữa 2 lần poll; total_vol = VOL lũy kế phiên.
-- Chống trùng ở tầng DB bằng PRIMARY KEY (symbol, ts, seq).
-- ===========================================================================
CREATE TABLE ticks (
    symbol    text        NOT NULL,
    ts        timestamptz NOT NULL,          -- luôn UTC
    price     numeric     NOT NULL,          -- CLOSE_PX (giá khớp cuối)
    volume    bigint,                        -- delta VOL so với lần poll trước
    bid_px    numeric,
    bid_vol   bigint,
    ask_px    numeric,
    ask_vol   bigint,
    total_vol bigint,                        -- VOL lũy kế phiên
    ref_px    numeric,                       -- giá tham chiếu
    seq       bigint DEFAULT 0 NOT NULL,
    PRIMARY KEY (symbol, ts, seq)
);

SELECT create_hypertable('ticks', 'ts');
CREATE INDEX idx_ticks_symbol_ts ON ticks (symbol, ts DESC);

-- ===========================================================================
-- Bar 1 phút CHÍNH THỨC từ DataPro /api/data/minute (poll ~10s).
-- ts = thời điểm bắt đầu bar, đã chuẩn hóa về UTC
-- (DataPro trả TRADING_TIME là giờ VN encode dạng epoch — ingestion tự quy đổi).
-- Bar đang hình thành được upsert liên tục; is_final = true khi bar đã đóng.
-- ===========================================================================
CREATE TABLE bars_1m (
    symbol       text        NOT NULL,
    ts           timestamptz NOT NULL,       -- bar start, UTC
    open         numeric,
    high         numeric,
    low          numeric,
    close        numeric,
    ref_px       numeric,
    volume       bigint,
    value        numeric,
    buy_vol      bigint,                     -- KL mua chủ động (từ sàn)
    buy_val      numeric,
    sell_vol     bigint,                     -- KL bán chủ động
    sell_val     numeric,
    frn_buy_vol  bigint,                     -- khối ngoại mua
    frn_buy_val  numeric,
    frn_sell_vol bigint,
    frn_sell_val numeric,
    adj_rate     numeric,                    -- hệ số điều chỉnh giá (cổ phiếu)
    is_final     boolean     NOT NULL DEFAULT false,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, ts)
);

SELECT create_hypertable('bars_1m', 'ts');

-- ===========================================================================
-- Bar NGÀY từ DataPro /api/data/daily — lịch sử dài (từ 2017 với VN30F1M,
-- xa hơn với cổ phiếu), kèm OI/tự doanh/khối ngoại. Nạp bằng
-- scripts backfill (idempotent, chạy lại bất kỳ lúc nào để cập nhật).
-- ===========================================================================
CREATE TABLE bars_1d (
    symbol       text    NOT NULL,
    trading_date date    NOT NULL,
    open         numeric,
    high         numeric,
    low          numeric,
    close        numeric,
    ref_px       numeric,
    volume       bigint,
    value        numeric,
    oi           bigint,                     -- hợp đồng mở (phái sinh)
    pt_vol       bigint,                     -- khớp thỏa thuận
    pt_val       numeric,
    buy_vol      bigint,
    buy_val      numeric,
    sell_vol     bigint,
    sell_val     numeric,
    port_buy_vol  bigint,                    -- tự doanh
    port_buy_val  numeric,
    port_sell_vol bigint,
    port_sell_val numeric,
    frn_buy_vol  bigint,                     -- khối ngoại
    frn_buy_val  numeric,
    frn_sell_vol bigint,
    frn_sell_val numeric,
    adj_rate     numeric,
    PRIMARY KEY (symbol, trading_date)
);

-- ===========================================================================
-- Ghi nhận mỗi lần ingestion mất kết nối tới DataPro.
-- ===========================================================================
CREATE TABLE gap_log (
    id            bigserial   PRIMARY KEY,
    symbol        text,
    disconnect_ts timestamptz NOT NULL,
    reconnect_ts  timestamptz,
    note          text
);

CREATE INDEX idx_gap_log_disconnect ON gap_log (disconnect_ts DESC);

-- ===========================================================================
-- Model ghi dự báo vào đây (forward-test đối chiếu backtest).
-- ===========================================================================
CREATE TABLE predictions (
    model_name text        NOT NULL,
    ts         timestamptz NOT NULL,          -- thời điểm dữ liệu dùng để dự báo
    symbol     text        NOT NULL,
    horizon    text        NOT NULL,          -- ví dụ '1m', '5m'
    label      text        NOT NULL DEFAULT '',  -- 'p_bull', 'p_bear'... cho model đa lớp
    value      numeric     NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (model_name, symbol, ts, horizon, label)
);
