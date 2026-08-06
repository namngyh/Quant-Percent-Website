"""Kiểm tra sức khỏe pipeline. Chạy từ máy host:

    pip install "psycopg[binary]"
    python scripts/check_pipeline.py

Đọc PG_DSN từ biến môi trường; không có thì dừng và hướng dẫn cách đặt.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

import psycopg

# Scripts here run under several different virtualenvs, so the shared
# helper is imported by path rather than as a package.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _db import dsn_from_env  # noqa: E402

PG_DSN = None  # resolved lazily by dsn_from_env()

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# Giờ giao dịch phái sinh: 9:00–11:30, 13:00–14:45 (giờ VN)
SESSIONS = [(dtime(9, 0), dtime(11, 30)), (dtime(13, 0), dtime(14, 45))]


def in_trading_hours(now_vn: datetime) -> bool:
    if now_vn.weekday() >= 5:  # T7, CN
        return False
    t = now_vn.time()
    return any(a <= t <= b for a, b in SESSIONS)


def main() -> None:
    now_vn = datetime.now(VN_TZ)
    trading = in_trading_hours(now_vn)
    print(f"Bay gio (VN): {now_vn:%Y-%m-%d %H:%M:%S} — "
          f"{'TRONG' if trading else 'NGOAI'} gio giao dich")
    print("=" * 70)

    with psycopg.connect(dsn_from_env()) as conn, conn.cursor() as cur:
        # 1) Tick 5 phút gần nhất
        cur.execute("""
            SELECT symbol, count(*), max(ts)
            FROM ticks
            WHERE ts > now() - interval '5 minutes'
            GROUP BY symbol ORDER BY symbol
        """)
        rows = cur.fetchall()
        print("\n[1] Pseudo-tick trong 5 phut gan nhat:")
        if not rows:
            if trading:
                print("  !! KHONG co tick trong gio giao dich — KIEM TRA INGESTION !!")
            else:
                print("  (khong co — binh thuong vi ngoai gio giao dich)")
        for sym, n, last in rows:
            print(f"  {sym}: {n} tick, moi nhat {last.astimezone(VN_TZ):%H:%M:%S}")

        # 2) Gap hôm nay (theo ngày VN)
        cur.execute("""
            SELECT id, symbol, disconnect_ts, reconnect_ts, note
            FROM gap_log
            WHERE (disconnect_ts AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
                  = (now() AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            ORDER BY disconnect_ts
        """)
        gaps = cur.fetchall()
        print(f"\n[2] Gap hom nay: {len(gaps)}")
        for gid, sym, d, r, note in gaps:
            d_vn = d.astimezone(VN_TZ).strftime("%H:%M:%S")
            r_vn = r.astimezone(VN_TZ).strftime("%H:%M:%S") if r else "CHUA RECONNECT"
            dur = f"{(r - d).total_seconds():.0f}s" if r else "?"
            print(f"  #{gid} {sym}: {d_vn} -> {r_vn} ({dur}) | {note[:60] if note else ''}")

        # 3) 10 bar chính thức gần nhất (bars_1m từ DataPro)
        cur.execute("""
            SELECT symbol, ts, open, high, low, close, volume,
                   buy_vol, sell_vol, is_final
            FROM bars_1m ORDER BY ts DESC LIMIT 10
        """)
        bars = cur.fetchall()
        print("\n[3] 10 bar bars_1m (chinh thuc tu DataPro) gan nhat:")
        if not bars:
            print("  (chua co bar nao)")
        for sym, b, o, h, l, c, v, bv, sv, fin in bars:
            flag = "FINAL" if fin else "dang chay"
            print(f"  {b.astimezone(VN_TZ):%Y-%m-%d %H:%M} {sym}: "
                  f"O={o} H={h} L={l} C={c} V={v} buy={bv} sell={sv} [{flag}]")

        # 4) Đối chiếu chéo ohlc_1m (tự tính từ tick) vs bars_1m (chính thức)
        cur.execute("""
            SELECT o.bucket, o.close AS tick_close, b.close AS bar_close
            FROM ohlc_1m o
            JOIN bars_1m b ON b.symbol = o.symbol AND b.ts = o.bucket
            ORDER BY o.bucket DESC LIMIT 5
        """)
        cmp_rows = cur.fetchall()
        print("\n[4] Doi chieu close: ohlc_1m (tu tick) vs bars_1m (DataPro):")
        if not cmp_rows:
            print("  (chua co bar trung khop de doi chieu)")
        for b, tc, bc in cmp_rows:
            match = "OK" if tc == bc else f"LECH {tc} vs {bc}"
            print(f"  {b.astimezone(VN_TZ):%H:%M}: {match}")


if __name__ == "__main__":
    main()
