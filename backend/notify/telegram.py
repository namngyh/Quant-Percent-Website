"""Gửi thông báo qua Telegram.

Dùng Bot API, chỉ cần một token và một chat id — không cần thư viện nào ngoài
`httpx` đã có sẵn. WhatsApp thì khác: nó đòi tài khoản Business, xét duyệt mẫu
tin nhắn và một nhà cung cấp trung gian, nên Telegram là lựa chọn thực tế hơn
nhiều cho một công cụ chạy trên máy cá nhân.

Nguyên tắc:

* **Không cấu hình thì không gửi gì.** Thiếu token hoặc chat id thì mọi lời gọi
  lặng lẽ bỏ qua, không báo lỗi và không chặn giao dịch.
* **Không bao giờ chặn.** Telegram chậm hay hỏng cũng không được làm phiên
  paper trading dừng lại, nên lỗi gửi tin chỉ được ghi log.
* **Không lặp lại.** Mỗi sự kiện gửi một lần; nếu Telegram từ chối, ta không
  thử lại vô hạn để rồi dội một loạt tin cũ khi mạng trở lại.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
API_BASE = "https://api.telegram.org"
TIMEOUT = 10.0

# Telegram giới hạn khoảng 30 tin/giây cho bot; ta không đến gần mức đó, nhưng
# một chiến lược lỗi có thể sinh sự kiện liên tục nên vẫn cần chặn trên.
MIN_INTERVAL = 1.0
_last_sent = 0.0
_lock = asyncio.Lock()


def _load_env() -> None:
    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)
        except ImportError:
            pass


def credentials() -> tuple[str | None, str | None]:
    if not os.environ.get("TELEGRAM_BOT_TOKEN"):
        _load_env()
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def configured() -> bool:
    token, chat_id = credentials()
    return bool(token and chat_id)


async def send(text: str, *, silent: bool = False) -> dict:
    """Gửi một tin nhắn. Trả về {sent, ...}; không bao giờ ném ngoại lệ."""
    token, chat_id = credentials()
    if not token or not chat_id:
        return {"sent": False, "reason": "chưa cấu hình"}

    global _last_sent
    async with _lock:
        gap = time.monotonic() - _last_sent
        if gap < MIN_INTERVAL:
            await asyncio.sleep(MIN_INTERVAL - gap)
        _last_sent = time.monotonic()

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(
                f"{API_BASE}/bot{token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_notification": silent,
                },
            )
        payload = response.json()
        if not payload.get("ok"):
            log.warning("Telegram từ chối: %s", payload.get("description"))
            return {"sent": False, "reason": payload.get("description", "bị từ chối")}
        return {"sent": True}
    except Exception as exc:
        # Một phiên paper trading không được dừng vì Telegram hỏng.
        log.warning("không gửi được tin Telegram: %s", exc)
        return {"sent": False, "reason": f"{type(exc).__name__}: {exc}"}


async def check() -> dict:
    """Xác minh token và chat id mà không gửi tin cho người dùng."""
    token, chat_id = credentials()
    if not token or not chat_id:
        return {
            "configured": False,
            "reachable": False,
            "message": "Chưa có TELEGRAM_BOT_TOKEN hoặc TELEGRAM_CHAT_ID trong .env",
        }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.get(f"{API_BASE}/bot{token}/getMe")
        payload = response.json()
        if not payload.get("ok"):
            return {
                "configured": True,
                "reachable": False,
                "message": f"Token không hợp lệ: {payload.get('description')}",
            }
        bot = payload.get("result", {})
        return {
            "configured": True,
            "reachable": True,
            "bot_username": bot.get("username"),
            "chat_id": chat_id,
        }
    except Exception as exc:
        return {
            "configured": True,
            "reachable": False,
            "message": f"Không kết nối được Telegram: {exc}",
        }


# ------------------------------------------------------- tin nhắn sự kiện

def _money(value: float) -> str:
    return f"{value:,.2f}"


def format_paper_event(session: dict, event: dict) -> str | None:
    """Soạn tin cho một sự kiện paper trading. None nghĩa là không đáng gửi."""
    head = f"<b>{session.get('strategy_id', '?')}</b> · {session.get('symbol')} {session.get('timeframe')}"

    kind = event.get("type")
    if kind == "entry":
        side = "MUA" if event.get("side") == "long" else "BÁN"
        return (
            f"🟢 {head}\n"
            f"Vào lệnh <b>{side}</b> @ {_money(event.get('price', 0))}\n"
            f"Khối lượng {event.get('quantity', 0):.6f}"
        )

    if kind in ("exit", "liquidation"):
        trade = event.get("trade", {})
        pnl = trade.get("pnl", 0.0)
        icon = "🔴" if kind == "liquidation" else ("🔵" if pnl >= 0 else "🟠")
        label = "BỊ THANH LÝ" if kind == "liquidation" else "Đóng lệnh"
        return (
            f"{icon} {head}\n"
            f"{label} {trade.get('side', '').upper()} "
            f"@ {_money(trade.get('exit_price', 0))}\n"
            f"Lãi/lỗ <b>{_money(pnl)}</b> ({trade.get('return_pct', 0):+.2f}%)\n"
            f"Vốn hiện tại {_money(session.get('equity', 0))}"
        )

    return None
