"""Ripeness interface (Section 7 M6, Section 14.2).

``RipenessModel`` is the seam between the backend and any ripeness estimator.
Two implementations satisfy it:

* :class:`~ml.ripeness.colour_texture.ColourTextureRipenessModel` - the real,
  documented MVP implementation ("a lightweight color/texture health module").
  Pure OpenCV; no weights required.
* :class:`~ml.ripeness.mock.MockRipenessModel` - deterministic, clearly
  labelled stand-in used when ``MOCK_SERVICES=true``.

Every result is a normalised score in ``[0.0, 1.0]`` and carries its own
confidence, because Section 9.1 reality 2 warns that colour-based ripeness is
variety-dependent: "some mangoes stay green when ripe".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import numpy as np

from ml.fruit_detection.base import FruitDetectionResult


@dataclass(frozen=True)
class RipenessResult:
    """Normalised ripeness estimate plus the evidence behind it."""

    score: float  # 0.0 (unripe) .. 1.0 (ripe / over-ripe)
    confidence: float  # 0.0 .. 1.0 - how much to trust this score
    provider: str
    model_version: str
    is_mock: bool
    indicators: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(float(self.score), 4),
            "confidence": round(float(self.confidence), 4),
            "provider": self.provider,
            "model_version": self.model_version,
            "is_mock": self.is_mock,
            "indicators": self.indicators,
            "notes": list(self.notes),
        }


@runtime_checkable
class RipenessModel(Protocol):
    name: str
    is_mock: bool

    def score(
        self, image: np.ndarray, detection: FruitDetectionResult | None = None
    ) -> RipenessResult: ...


__all__ = ["RipenessModel", "RipenessResult"]
