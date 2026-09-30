"""M6 - Ground / close-up analysis orchestration.

Ties the documented perception pipeline together for one image::

    quality gate -> preprocess -> fruit detection -> ripeness -> health

This is the single implementation used by phone photos, rover images and
(uniformly) drone tiles - Section 4.3: "Drone, rover and phone are all just
input sources into the same ingestion and fusion pipeline." Only the ``source``
label differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.core.config import Settings, get_settings
from backend.core.errors import ImageQualityError
from backend.core.logging import get_logger
from ml.fruit_detection.base import FruitDetectionResult
from ml.health.base import HealthResult
from ml.preprocessing.pipeline import PreprocessResult, Preprocessor
from ml.providers import build_fruit_detector, build_health_model, build_ripeness_model
from ml.ripeness.base import RipenessResult

logger = get_logger(__name__)

IMAGE_SOURCES = ("phone", "drone", "rover")


@dataclass
class VisualEvidence:
    """Perception evidence extracted from one image."""

    source: str
    preprocessing: dict[str, Any]
    detection: FruitDetectionResult
    ripeness: RipenessResult
    health: HealthResult
    notes: list[str] = field(default_factory=list)

    @property
    def is_mock(self) -> bool:
        return bool(
            self.detection.is_mock or self.ripeness.is_mock or self.health.is_mock
        )

    @property
    def confidence(self) -> float:
        """Combined perception confidence: detection, ripeness and health."""
        parts = [self.detection.confidence, self.ripeness.confidence, self.health.confidence]
        return round(float(np.mean(parts)), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "is_mock": self.is_mock,
            "confidence": self.confidence,
            "preprocessing": self.preprocessing,
            "detection": self.detection.to_dict(),
            "ripeness": self.ripeness.to_dict(),
            "health": self.health.to_dict(),
            "notes": list(self.notes),
        }


class GroundAnalysisService:
    """Runs the perception pipeline for a single image."""

    def __init__(
        self,
        *,
        detector: Any,
        ripeness_model: Any,
        health_model: Any,
        preprocessing_config: dict[str, Any] | None = None,
        quality_config: dict[str, Any] | None = None,
    ) -> None:
        self.detector = detector
        self.ripeness_model = ripeness_model
        self.health_model = health_model
        self.preprocessor = Preprocessor(preprocessing_config)
        self.quality_config = quality_config or {}

    @classmethod
    def from_config(
        cls,
        *,
        settings: Settings | None = None,
        crop_config: Any | None = None,
        thresholds: Any | None = None,
        variety_id: str | None = None,
    ) -> "GroundAnalysisService":
        resolved = settings or get_settings()
        return cls(
            detector=build_fruit_detector(resolved, thresholds=thresholds, crop_config=crop_config),
            ripeness_model=build_ripeness_model(
                resolved, crop_config=crop_config, variety_id=variety_id
            ),
            health_model=build_health_model(
                resolved, crop_config=crop_config, variety_id=variety_id
            ),
            preprocessing_config=getattr(thresholds, "preprocessing", None),
            quality_config=getattr(thresholds, "quality_gate", None),
        )

    def analyze(
        self,
        image_bytes: bytes,
        *,
        source: str = "phone",
        enforce_quality: bool = True,
    ) -> VisualEvidence:
        """Preprocess then infer.

        Raises :class:`~backend.core.errors.ImageQualityError` when the quality
        gate fails and ``enforce_quality`` is true. No inference is performed on
        a rejected image.
        """
        if source not in IMAGE_SOURCES:
            # `farmer_report` etc. never reach here; guard anyway.
            raise ValueError(f"Source '{source}' does not carry an image.")

        preprocessed: PreprocessResult = self.preprocessor.preprocess(
            image_bytes,
            quality_config=self.quality_config,
            enforce_quality=enforce_quality,
        )

        detection = self.detector.detect(preprocessed.image)
        ripeness = self.ripeness_model.score(preprocessed.image, detection)
        health = self.health_model.assess(preprocessed.image, detection)

        notes: list[str] = []
        if self.quality_config:
            notes.append("Quality gate passed; inference ran on the normalised image.")
        if preprocessed.quality.metrics.laplacian_variance < 2 * float(
            self.quality_config.get("min_laplacian_variance", 40.0)
        ):
            notes.append("Sharpness is only just above the gate; treat the ripeness score with caution.")

        return VisualEvidence(
            source=source,
            preprocessing=preprocessed.to_dict(),
            detection=detection,
            ripeness=ripeness,
            health=health,
            notes=notes,
        )

    def analyze_or_reject(
        self, image_bytes: bytes, *, source: str = "phone"
    ) -> tuple[VisualEvidence | None, ImageQualityError | None]:
        """Non-raising variant used where a structured rejection is preferred."""
        try:
            return self.analyze(image_bytes, source=source), None
        except ImageQualityError as error:
            return None, error


__all__ = ["GroundAnalysisService", "IMAGE_SOURCES", "VisualEvidence"]
