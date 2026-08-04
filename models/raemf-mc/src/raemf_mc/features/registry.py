"""Feature registry."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    group: str
    lookback: int
    source_columns: str
    available_at: str
    requires_volume: bool = False
    requires_ohlc: bool = False


class FeatureRegistry:
    """Collect feature metadata for reporting and leakage review."""

    def __init__(self) -> None:
        self._items: list[FeatureSpec] = []

    def add(
        self,
        name: str,
        group: str,
        lookback: int,
        source_columns: str,
        requires_volume: bool = False,
        requires_ohlc: bool = False,
    ) -> None:
        self._items.append(
            FeatureSpec(
                name=name,
                group=group,
                lookback=lookback,
                source_columns=source_columns,
                available_at="close_t",
                requires_volume=requires_volume,
                requires_ohlc=requires_ohlc,
            )
        )

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(x) for x in self._items])
