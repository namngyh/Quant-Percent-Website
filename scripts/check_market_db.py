"""Kiểm tra kết nối tới database thị trường Việt Nam của team.

    .venv\\Scripts\\python.exe scripts/check_market_db.py
    .venv\\Scripts\\python.exe scripts/check_market_db.py --symbol VN30F1M --limit 20

Database chỉ nghe trong VPN của team (Tailscale), không mở ra Internet — đó là
chủ ý. Nên script dùng timeout ngắn và, khi lỗi giống mất mạng, nói thẳng là
hãy kiểm tra VPN thay vì để bạn đoán.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

# Đủ ngắn để biết ngay là VPN chưa bật, thay vì ngồi chờ.
CONNECT_TIMEOUT = 8

# Team giới hạn 60 giây; đặt thấp hơn để script tự dừng trước khi bị server ngắt.
STATEMENT_TIMEOUT_MS = 30_000


def dsn() -> str:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    value = os.environ.get("MARKET_DSN")
    if not value:
        sys.exit(
            "Thiếu MARKET_DSN.\n"
            "  Copy .env.example thành .env rồi điền mật khẩu."
        )
    return value


def redact(value: str) -> str:
    """Che mật khẩu trước khi in bất cứ thứ gì ra màn hình."""
    if "://" not in value or "@" not in value:
        return value
    scheme, rest = value.split("://", 1)
    creds, host = rest.rsplit("@", 1)
    user = creds.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host}"


def explain(exc: Exception) -> str:
    """Đổi lỗi của psycopg thành câu tiếng Việt nói đúng việc cần làm."""
    text = str(exc).lower()

    vpn_signs = (
        "timeout", "timed out", "could not translate host name",
        "name or service not known", "no route to host",
        "network is unreachable", "connection refused", "host unreachable",
    )
    if any(sign in text for sign in vpn_signs):
        return (
            "Không tới được máy chủ.\n"
            "  → Gần như chắc chắn VPN của team (Tailscale) chưa bật.\n"
            "     Bật VPN rồi chạy lại. Database không nghe trên Internet,\n"
            "     nên đây là hành vi đúng chứ không phải lỗi cấu hình.\n"
            "  → Nếu team dùng Tailscale, kiểm tra host có phải địa chỉ 100.x\n"
            "     của VPS không (chạy `tailscale status` để xem)."
        )

    if "password authentication failed" in text or "authentication" in text:
        return (
            "Sai mật khẩu hoặc sai tên đăng nhập.\n"
            "  → Kiểm tra lại MARKET_DSN trong .env, hoặc hỏi người quản trị."
        )

    if "permission denied" in text:
        return (
            "Bị từ chối quyền.\n"
            "  → Tài khoản chỉ đọc được schema `api`. Hãy báo người quản trị,\n"
            "     đừng tìm đường vòng."
        )

    if "does not exist" in text:
        return f"Đối tượng không tồn tại: {exc}"

    return str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kiểm tra kết nối database thị trường")
    parser.add_argument("--symbol", default="VN30F1M")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()

    url = dsn()
    print(f"Kết nối : {redact(url)}")
    print(f"Timeout : {CONNECT_TIMEOUT}s\n")

    try:
        with psycopg.connect(url, connect_timeout=CONNECT_TIMEOUT) as conn:
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {STATEMENT_TIMEOUT_MS}")

                cur.execute("SELECT current_user, current_database(), version()")
                user, database, version = cur.fetchone()
                print(f"  user     : {user}")
                print(f"  database : {database}")
                print(f"  server   : {version.split(',')[0]}")

                # Kiểu của cột ts quyết định cách lọc nến chưa đóng, nên hỏi
                # thẳng schema thay vì đoán.
                cur.execute(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = 'api' AND table_name = 'v_history_1m'
                    ORDER BY ordinal_position
                    """
                )
                columns = cur.fetchall()
                print("\n  api.v_history_1m:")
                for name, dtype in columns:
                    print(f"    {name:<16} {dtype}")

                has_is_final = any(c[0] == "is_final" for c in columns)
                print(f"\n  có cột is_final: {has_is_final}  (tài liệu nói: không)")

                # Nến cuối cùng có thể đang hình thành. Bỏ mọi nến thuộc phút
                # hiện tại — an toàn hơn là bỏ đúng một dòng, vì nếu thị trường
                # đang nghỉ thì dòng cuối đã đóng và không nên vứt đi.
                cur.execute(
                    """
                    SELECT symbol, ts, open, high, low, close, volume
                    FROM api.v_history_1m
                    WHERE symbol = %s
                      AND ts < date_trunc('minute', now())
                    ORDER BY ts DESC
                    LIMIT %s
                    """,
                    (args.symbol, args.limit),
                )
                rows = cur.fetchall()

    except psycopg.OperationalError as exc:
        print("\nLỖI KẾT NỐI\n")
        print(explain(exc))
        return 1
    except psycopg.Error as exc:
        print("\nLỖI TRUY VẤN\n")
        print(explain(exc))
        return 1

    if not rows:
        print(f"\nKhông có nến nào cho {args.symbol}.")
        print("  → Kiểm tra lại mã, hoặc xem api.v_data_freshness.")
        return 1

    print(f"\n{len(rows)} nến 1 phút gần nhất của {args.symbol} (đã bỏ nến đang chạy):\n")
    print(f"  {'giờ VN':<17}{'giờ UTC':<17}{'open':>10}{'high':>10}{'low':>10}{'close':>10}{'volume':>12}")
    print("  " + "-" * 86)

    # ts lưu theo UTC; phiên VN 09:00-15:00 là 02:00-08:00 UTC. In cả hai để
    # thấy ngay là đang đọc đúng múi giờ.
    for symbol, ts, o, h, low, c, v in reversed(rows):
        vn = ts.tz_convert("Asia/Ho_Chi_Minh") if hasattr(ts, "tz_convert") else None
        if vn is None:
            import zoneinfo
            stamped = ts if ts.tzinfo else ts.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
            vn = stamped.astimezone(zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh"))
            utc = stamped
        else:
            utc = ts
        print(
            f"  {vn:%Y-%m-%d %H:%M}  {utc:%Y-%m-%d %H:%M}  "
            f"{float(o):>10,.2f}{float(h):>10,.2f}{float(low):>10,.2f}{float(c):>10,.2f}"
            f"{float(v):>12,.0f}"
        )

    print("\nKết nối OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
