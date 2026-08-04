"""Entrypoint ingestion service.

    python main.py            # mode theo env DATAPRO_MODE (mock | datapro)
    python main.py --mock     # ép mode mock (tick + bar giả lập)

Hai runner song song (snapshot->tick, minute->bar), mỗi runner có
reconnect exponential backoff 1s->60s + ghi gap_log riêng.
Service KHÔNG BAO GIỜ tự thoát.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from config import load_config
from records import Tick
from sources import make_sources
from validate import validate_bar, validate_tick
from writer import PipelineWriter

log = logging.getLogger("main")


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,  # docker logs đọc stdout
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)  # bớt ồn


async def run(cfg) -> None:
    writer = PipelineWriter(cfg)
    # DB/Redis chưa sẵn sàng lúc khởi động -> retry, không crash
    delay = cfg.backoff_initial
    while True:
        try:
            await writer.start()
            break
        except Exception as e:
            log.error("khoi tao Redis/DB loi, thu lai sau %.0fs: %s", delay, e)
            await asyncio.sleep(delay)
            delay = min(delay * 2, cfg.backoff_max)

    stop = asyncio.Event()

    def _request_stop(*_):
        log.info("nhan tin hieu dung, dang flush...")
        stop.set()

    # SIGTERM cho docker stop; add_signal_handler không có trên Windows
    if sys.platform != "win32":
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, _request_stop)

    runners = [
        asyncio.create_task(_ingest_forever(cfg, writer, stop, name))
        for name, _ in make_sources(cfg)
    ]
    stopper = asyncio.create_task(stop.wait())
    try:
        await asyncio.wait([*runners, stopper], return_when=asyncio.FIRST_COMPLETED)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        stop.set()
        for r in runners:
            r.cancel()
        await asyncio.gather(*runners, return_exceptions=True)
        await writer.close()


async def _ingest_forever(cfg, writer: PipelineWriter, stop: asyncio.Event,
                          runner_name: str) -> None:
    """Stream 1 source + reconnect exponential backoff + gap_log."""
    delay = cfg.backoff_initial
    gap_id: int | None = None
    n = 0
    while not stop.is_set():
        try:
            source = dict(make_sources(cfg))[runner_name]
            async for event in source.stream():
                if gap_id is not None:
                    await writer.log_reconnect(gap_id)
                    log.info("[%s] reconnected, gap_log id=%s da cap nhat",
                             runner_name, gap_id)
                    gap_id = None
                delay = cfg.backoff_initial  # có dữ liệu -> reset backoff
                if isinstance(event, Tick):
                    ev = validate_tick(event)
                else:
                    ev = validate_bar(event)
                if ev is None:
                    continue
                await writer.handle(ev)
                n += 1
                if n % 500 == 0:
                    log.info("[%s] da xu ly %d record", runner_name, n)
                if stop.is_set():
                    return
            raise ConnectionError("stream ket thuc bat thuong (EOF)")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if stop.is_set():
                return
            log.error("[%s] mat ket noi nguon du lieu: %s", runner_name, e)
            if gap_id is None:
                gap_id = await writer.log_disconnect(f"[{runner_name}] {e}")
            log.info("[%s] reconnect sau %.0fs...", runner_name, delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, cfg.backoff_max)


def main() -> None:
    parser = argparse.ArgumentParser(description="QuantPercent ingestion service")
    parser.add_argument("--mock", action="store_true",
                        help="ep dung nguon mock (du lieu gia lap)")
    args = parser.parse_args()

    cfg = load_config()
    if args.mock:
        cfg.mode = "mock"
    setup_logging(cfg.log_level)
    log.info("ingestion start: mode=%s symbols=%s datapro=%s",
             cfg.mode, cfg.symbols, cfg.datapro_rest_url)

    # psycopg async cần SelectorEventLoop trên Windows
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        log.info("dung boi Ctrl+C")


if __name__ == "__main__":
    main()
