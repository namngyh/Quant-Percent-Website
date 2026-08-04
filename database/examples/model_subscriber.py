"""Mẫu cách model subscribe dữ liệu realtime từ pipeline (thay cho gọi API trực tiếp).

Chạy:  pip install redis   rồi   python examples/model_subscriber.py

Hai kênh:
- ticks:{symbol} : pseudo-tick ~1s (giá khớp + bid/ask) — độ trễ thấp nhất
- bars:{symbol}  : bar 1 phút chính thức (OHLC + buy/sell + khối ngoại);
                   bar được cập nhật liên tục khi đang hình thành (final=false),
                   và phát bản CHỐT với final=true khi bar đóng.

Để forward-test khớp backtest: chỉ act trên bar khi final=true —
bản đó trùng khớp 1:1 với dòng trong bảng bars_1m của DB.
"""
import json
import os

import redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def on_tick(tick: dict) -> None:
    # === Feature tick-level của model đặt tại đây ===
    print(f"TICK [{tick['ts']}] {tick['symbol']} price={tick['price']} "
          f"dV={tick['volume']} bid={tick['bid_px']}x{tick['bid_vol']} "
          f"ask={tick['ask_px']}x{tick['ask_vol']}")


def on_bar(bar: dict) -> None:
    # === Chỉ dự báo khi bar chốt ===
    if not bar["final"]:
        return  # bar đang hình thành — bỏ qua hoặc dùng cho feature riêng
    print(f"BAR  [{bar['ts']}] {bar['symbol']} "
          f"O={bar['open']} H={bar['high']} L={bar['low']} C={bar['close']} "
          f"V={bar['volume']} buy={bar['buy_vol']} sell={bar['sell_vol']} FINAL")


def main() -> None:
    r = redis.from_url(REDIS_URL, decode_responses=True)
    ps = r.pubsub(ignore_subscribe_messages=True)
    ps.psubscribe("ticks:*", "bars:*")
    print(f"Subscribed ticks:* + bars:* tren {REDIS_URL} — Ctrl+C de dung")
    for msg in ps.listen():
        data = json.loads(msg["data"])
        if msg["channel"].startswith("ticks:"):
            on_tick(data)
        else:
            on_bar(data)


if __name__ == "__main__":
    main()
