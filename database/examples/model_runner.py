"""Khung nối MODEL THỐNG KÊ của anh/chị vào pipeline — thay cho việc
cập nhật data thủ công:

    pip install redis "psycopg[binary]" pandas
    python examples/model_runner.py

Vòng đời:
1. Khởi động: nạp lịch sử bar phút từ bars_1m (bao nhiêu tùy WARMUP_BARS)
2. Nghe Redis bars:VN30F1M — mỗi khi bar CHỐT (final=true):
     -> gọi predict() với DataFrame lịch sử mới nhất
     -> ghi các xác suất vào bảng predictions (website sẽ đọc từ đây)
3. Chạy mãi; ngoài giờ giao dịch tự im lặng vì không có bar mới.

Chỉ cần thay thân hàm predict() bằng model thật.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import pandas as pd
import psycopg
import redis

PG_DSN = os.environ.get(
    "PG_DSN", "postgresql://quant:qp_local_dev_2026@localhost:5432/market")
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

MODEL_NAME = "demo_model_v1"        # đổi theo tên model của anh/chị
SYMBOL = "VN30F1M"
HORIZON = "5m"                      # dự báo cho 5 phút tới
WARMUP_BARS = 2000                  # số bar lịch sử nạp lúc khởi động


# ============================================================================
# THAY THÂN HÀM NÀY BẰNG MODEL THẬT
# Input : DataFrame bar phút (cột: ts, open, high, low, close, volume,
#         buy_vol, sell_vol...), dòng cuối là bar vừa chốt.
# Output: dict {label: xác suất}, ví dụ {"p_bull": 0.62, "p_bear": 0.30,
#         "p_neutral": 0.08} — hoặc None nếu chưa đủ dữ liệu.
# ============================================================================
def predict(df: pd.DataFrame) -> dict | None:
    if len(df) < 20:
        return None
    # --- demo: momentum thô 20 phút, CHỈ để minh họa đường ống ---
    ret20 = df["close"].iloc[-1] / df["close"].iloc[-20] - 1
    p_bull = min(max(0.5 + ret20 * 30, 0.05), 0.95)
    return {"p_bull": round(p_bull, 4), "p_bear": round(1 - p_bull, 4)}


def load_history(conn) -> pd.DataFrame:
    return pd.read_sql(
        """SELECT ts, open, high, low, close, volume, buy_vol, sell_vol
           FROM bars_1m WHERE symbol = %s AND is_final
           ORDER BY ts DESC LIMIT %s""",
        conn, params=(SYMBOL, WARMUP_BARS)).iloc[::-1].reset_index(drop=True)


def save_prediction(conn, ts: str, probs: dict) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """INSERT INTO predictions (model_name, ts, symbol, horizon, label, value)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (model_name, symbol, ts, horizon, label)
               DO UPDATE SET value = EXCLUDED.value, created_at = now()""",
            [(MODEL_NAME, ts, SYMBOL, HORIZON, k, v) for k, v in probs.items()])
    conn.commit()


def main() -> None:
    conn = psycopg.connect(PG_DSN)
    df = load_history(conn)
    print(f"Nap {len(df)} bar lich su. Cho bar mới tren Redis...")

    r = redis.from_url(REDIS_URL, decode_responses=True)
    ps = r.pubsub(ignore_subscribe_messages=True)
    ps.subscribe(f"bars:{SYMBOL}")
    for msg in ps.listen():
        bar = json.loads(msg["data"])
        if not bar["final"]:
            continue                      # chỉ dự báo trên bar đã chốt
        row = {k: bar[k] for k in ("ts", "open", "high", "low", "close",
                                   "volume", "buy_vol", "sell_vol")}
        row["ts"] = pd.Timestamp(row["ts"])
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True).tail(WARMUP_BARS)

        probs = predict(df)
        if probs is None:
            continue
        save_prediction(conn, bar["ts"], probs)
        print(f"[{datetime.now():%H:%M:%S}] bar {bar['ts']} close={bar['close']}"
              f" -> {probs}  (da ghi vao predictions)")


if __name__ == "__main__":
    main()
