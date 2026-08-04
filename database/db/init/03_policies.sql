-- Nén chunk ticks cũ hơn 7 ngày (tick lịch sử chỉ đọc, nén tiết kiệm ~90% dung lượng).
ALTER TABLE ticks SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby   = 'ts DESC, seq DESC'
);
SELECT add_compression_policy('ticks', INTERVAL '7 days');

-- bars_1m: nén sau 30 ngày (bar còn được upsert tới khi final, để dư an toàn).
ALTER TABLE bars_1m SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol',
    timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('bars_1m', INTERVAL '30 days');
