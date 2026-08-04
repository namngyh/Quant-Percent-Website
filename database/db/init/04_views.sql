-- View giá ĐÃ ĐIỀU CHỈNH (cổ tức/chia tách) — dùng khi so sánh với chart
-- công cộng hoặc tính return dài hạn cho cổ phiếu.
-- Quy ước DataPro: gia_dieu_chinh = gia_tho / adj_rate.
-- Lưu ý: adj_rate là hệ số TẠI THỜI ĐIỂM tải dữ liệu — sau mỗi đợt cổ tức mới
-- cần chạy lại backfill.py để làm tươi. volume giữ nguyên không điều chỉnh.
-- VN30F1M / chỉ số không bị ảnh hưởng (adj_rate = 1).

CREATE OR REPLACE VIEW bars_1d_adj AS
SELECT symbol, trading_date,
       open  / NULLIF(adj_rate, 0) AS open,
       high  / NULLIF(adj_rate, 0) AS high,
       low   / NULLIF(adj_rate, 0) AS low,
       close / NULLIF(adj_rate, 0) AS close,
       volume, value, oi,
       buy_vol, buy_val, sell_vol, sell_val,
       frn_buy_vol, frn_buy_val, frn_sell_vol, frn_sell_val,
       adj_rate
FROM bars_1d;

CREATE OR REPLACE VIEW bars_1m_adj AS
SELECT symbol, ts,
       open  / NULLIF(adj_rate, 0) AS open,
       high  / NULLIF(adj_rate, 0) AS high,
       low   / NULLIF(adj_rate, 0) AS low,
       close / NULLIF(adj_rate, 0) AS close,
       volume, value,
       buy_vol, buy_val, sell_vol, sell_val,
       adj_rate, is_final
FROM bars_1m;
