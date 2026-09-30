"""Health interface (Section 7 M6, Section 13.1).

``HealthModel`` returns a normalised health score plus health-risk indicators.

Wording discipline is enforced at the type level: indicators are named
``possible_*`` and every result carries the "requires local confirmation"
caveat. An image classifier must never be presented as a definitive diagnosis
(Section 13.1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

REQUIRES_CONFIRMATION = "requires local confirmation"


@dataclass(frozen=True)
class HealthResult:
    """Normalised health estimate plus possible (never confirmed) indicators."""

    health_score: float  # 1.0 healthy .. 0.0 severe visible anomaly
    confidence: float
    provider: str
    model_version: str
    is_mock: bool
    indicators: dict[str, Any] = field(default_factory=dict)
    possible_indicators: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def requires_local_confirmation(self) -> bool:
        return bool(self.possible_indicators)

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_score": round(float(self.health_score), 4),
            "confidence": round(float(self.confidence), 4),
            "provider": self.provider,
            "model_version": self.model_version,
            "is_mock": self.is_mock,
            "indicators": self.indicators,
            "possible_indicators": list(self.possible_indicators),
            "requires_local_confirmation": self.requires_local_confirmation,
            "notes": list(self.notes),
        }


@runtime_checkable
class HealthModel(Protocol):
    name: str
    is_mock: bool

    def assess(
        self, image: np.ndarray, detection: Any | None = None
    ) -> HealthResult: ...


__all__ = ["HealthModel", "HealthResult", "REQUIRES_CONFIRMATION"]
