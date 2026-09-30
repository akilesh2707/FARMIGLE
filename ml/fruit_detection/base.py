"""Fruit detection interface (Section 7 M5/M6, Section 14.2).

``FruitDetector`` is the single seam between the backend and any object
detector. Two implementations satisfy it:

* :class:`~ml.fruit_detection.yolo.YOLOFruitDetector` - real Ultralytics YOLO
  weights. Requires a weights file; raises
  :class:`~backend.core.errors.ProviderUnavailableError` when they are absent.
  No weights are bundled with this repository.
* :class:`~ml.fruit_detection.mock.MockFruitDetector` - deterministic mock used
  in ``MOCK_SERVICES=true`` mode and in tests. It is labelled ``is_mock=True``
  everywhere it surfaces and never claims to be a trained model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence, runtime_checkable

import numpy as np


@dataclass(frozen=True)
class FruitDetection:
    """One detected fruit."""

    label: str
    confidence: float
    bbox: tuple[int, int, int, int]  # x_min, y_min, x_max, y_max in pixels
    area_ratio: float
    ripeness_score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "confidence": round(float(self.confidence), 4),
            "bbox": list(self.bbox),
            "area_ratio": round(float(self.area_ratio), 5),
            "ripeness_score": None if self.ripeness_score is None else round(float(self.ripeness_score), 4),
        }


@dataclass(frozen=True)
class FruitDetectionResult:
    """Aggregate detection output for one image."""

    provider: str
    model_version: str
    is_mock: bool
    detections: list[FruitDetection] = field(default_factory=list)
    image_width: int = 0
    image_height: int = 0
    confidence: float = 0.0
    fruit_coverage_ratio: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def fruit_count(self) -> int:
        return len(self.detections)

    def ripeness_by_detection(self) -> list[float]:
        return [
            float(detection.ripeness_score)
            for detection in self.detections
            if detection.ripeness_score is not None
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_version": self.model_version,
            "is_mock": self.is_mock,
            "fruit_count": self.fruit_count,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "confidence": round(float(self.confidence), 4),
            "fruit_coverage_ratio": round(float(self.fruit_coverage_ratio), 5),
            "notes": list(self.notes),
            "detections": [detection.to_dict() for detection in self.detections],
        }


@runtime_checkable
class FruitDetector(Protocol):
    name: str
    is_mock: bool

    def detect(self, image: np.ndarray) -> FruitDetectionResult: ...


def detection_confidence(detections: Sequence[FruitDetection]) -> float:
    """Overall detection confidence, tempered by how many fruit were found.

    A single low-confidence box should not be treated as strong evidence.
    """
    if not detections:
        return 0.0
    mean_confidence = float(np.mean([detection.confidence for detection in detections]))
    count_factor = min(1.0, len(detections) / 5.0)
    return float(np.clip(0.5 * mean_confidence + 0.5 * mean_confidence * count_factor, 0.0, 1.0))


__all__ = [
    "FruitDetection",
    "FruitDetectionResult",
    "FruitDetector",
    "detection_confidence",
]
