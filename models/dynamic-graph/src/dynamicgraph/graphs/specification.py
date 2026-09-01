"""Immutable provenance for graph choices fitted on the training period."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FittedGraphSpecification:
    """The graph hyperparameters frozen before any OOS evaluation."""

    selected_alpha: float
    selection_method: str
    estimator: str
    training_start: str
    training_end: str
    validation_start: str | None
    validation_end: str | None
    universe_definition: dict[str, Any]
    feature_specification: dict[str, Any]
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    convergence_diagnostics: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path
