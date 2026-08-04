"""Data access layer: discovery, read-only connectors, normalisation, validation."""

from __future__ import annotations

from dynamicgraph.data.discovery import DataSourceCandidate, discover_data_sources, rank_candidates
from dynamicgraph.data.loader import load_panel
from dynamicgraph.data.normalizer import normalize_panel
from dynamicgraph.data.validator import ValidationReport, validate_panel

__all__ = [
    "DataSourceCandidate",
    "discover_data_sources",
    "rank_candidates",
    "load_panel",
    "normalize_panel",
    "validate_panel",
    "ValidationReport",
]
