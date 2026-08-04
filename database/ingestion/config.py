"""Cấu hình ingestion — đọc toàn bộ từ biến môi trường, không hardcode."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class Config:
    datapro_api_key: str
    datapro_rest_url: str           # ví dụ http://host.docker.internal:6789
    mode: str                       # mock | datapro
    symbols: list[str]              # mã ƯU TIÊN (VN30F1M) — bar poll dày
    stock_symbols: list[str]        # mã theo dõi thêm (rổ VN30...) — bar round-robin
    pg_dsn: str
    redis_url: str
    log_level: str
    parquet_dir: str
    # Poll DataPro (rate limit ~2 req/s cho toàn bộ):
    snapshot_interval: float = 1.0  # /api/symbols (bulk, 1 request cho MỌI mã)
    bar_spacing: float = 1.5        # giãn cách giữa 2 request bar phút
                                    # (xen kẽ: ưu tiên, cổ phiếu, ưu tiên, ...)
    # Batch DB ticks: flush khi đủ batch_size tick hoặc quá flush_interval giây
    batch_size: int = 100
    flush_interval: float = 0.5
    # Parquet: ghi row group khi đủ số dòng hoặc quá số giây
    parquet_batch_rows: int = 500
    parquet_flush_interval: float = 30.0
    # Reconnect backoff
    backoff_initial: float = 1.0
    backoff_max: float = 60.0


def load_config() -> Config:
    return Config(
        datapro_api_key=os.environ.get("DATAPRO_API_KEY", ""),
        datapro_rest_url=os.environ.get(
            "DATAPRO_REST_URL", "http://host.docker.internal:6789").rstrip("/"),
        mode=os.environ.get("DATAPRO_MODE", "mock").lower(),
        symbols=[s.strip() for s in os.environ.get("SYMBOLS", "VN30F1M").split(",") if s.strip()],
        stock_symbols=[s.strip() for s in os.environ.get("STOCK_SYMBOLS", "").split(",") if s.strip()],
        pg_dsn=os.environ.get(
            "PG_DSN", "postgresql://quant:qp_local_dev_2026@localhost:5432/market"),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
        parquet_dir=os.environ.get("PARQUET_DIR", "data/raw"),
        snapshot_interval=float(os.environ.get("SNAPSHOT_INTERVAL", "1.0")),
        bar_spacing=float(os.environ.get("BAR_SPACING", "1.5")),
    )
