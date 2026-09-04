"""Configuration loading for QP-TRACKING.

Reads ``config.yaml`` from the project root once and exposes it as typed
settings objects. Everything downstream imports ``settings`` from here rather
than reaching for the YAML directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


@dataclass(frozen=True)
class DataSettings:
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT"])
    timeframes: list[str] = field(default_factory=lambda: ["1h"])
    start_date: str = "2017-01-01"
    store_dir: str = "data_store"

    @property
    def store_path(self) -> Path:
        path = PROJECT_ROOT / self.store_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


@dataclass(frozen=True)
class ServerSettings:
    host: str = "127.0.0.1"
    port: int = 8000


@dataclass(frozen=True)
class ChartSettings:
    max_candles: int = 20000
    default_symbol: str = "BTCUSDT"
    default_timeframe: str = "1h"


@dataclass(frozen=True)
class Settings:
    data: DataSettings
    server: ServerSettings
    chart: ChartSettings

    @property
    def project_root(self) -> Path:
        return PROJECT_ROOT

    @property
    def plugin_indicator_dir(self) -> Path:
        path = PROJECT_ROOT / "plugins" / "indicators"
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    raw: dict = {}
    if CONFIG_PATH.exists():
        raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}

    return Settings(
        data=DataSettings(**(raw.get("data") or {})),
        server=ServerSettings(**(raw.get("server") or {})),
        chart=ChartSettings(**(raw.get("chart") or {})),
    )


settings = get_settings()
