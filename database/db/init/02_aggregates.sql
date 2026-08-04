-- Bar 1 phút TỰ TÍNH từ pseudo-tick — dùng đối chiếu chéo với bars_1m
-- chính thức của DataPro (lệch lớn = pipeline có vấn đề).
CREATE MATERIALIZED VIEW ohlc_1m
WITH (timescaledb.continuous) AS
SELECT
    symbol,
    time_bucket('1 minute', ts) AS bucket,
    first(price, ts)            AS open,
    max(price)                  AS high,
    min(price)                  AS low,
    last(price, ts)             AS close,
    sum(volume)                 AS volume
FROM ticks
GROUP BY symbol, bucket
WITH NO DATA;

-- Bật real-time aggregation: bar phút đang chạy query được ngay,
-- không phải chờ refresh policy (TimescaleDB >= 2.13 mặc định tắt).
ALTER MATERIALIZED VIEW ohlc_1m SET (timescaledb.materialized_only = false);

-- Refresh mỗi phút; materialize tới bar đã đóng (trễ 1 phút).
SELECT add_continuous_aggregate_policy('ohlc_1m',
    start_offset      => INTERVAL '1 hour',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute');
