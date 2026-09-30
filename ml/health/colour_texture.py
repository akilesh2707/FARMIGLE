"""Colour/texture health anomaly module - the real MVP implementation.

Section 7 M6: "a lightweight color/texture anomaly module" and Section 4.2:
diseases are reported as a generic "possible health indicator", never as a
diagnosis.

Signals used
------------
* browning/necrosis proxy  - share of low-saturation, low-value warm pixels
* chlorosis proxy          - share of yellow-without-orange leaf area
* lesion contrast           - local texture energy inside dark regions
* dark/underexposed area    - photographs in deep shade are flagged as
  low-confidence rather than as unhealthy

Every indicator is returned with a ``possible_`` prefix and the result carries
``requires local confirmation``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.core.errors import ProviderError
from ml.fruit_detection.base import FruitDetectionResult
from ml.health.base import REQUIRES_CONFIRMATION, HealthResult
from ml.preprocessing.features import extract_features

# Indicator weights for the health score (sum to 1.0).
WEIGHT_BROWNING = 0.45
WEIGHT_CHLOROSIS = 0.20
WEIGHT_DARK = 0.15
WEIGHT_LESION = 0.20

# Thresholds above which a proxy becomes an explicit "possible indicator".
BROWNING_INDICATOR_THRESHOLD = 0.12
CHLOROSIS_INDICATOR_THRESHOLD = 0.30
DARK_INDICATOR_THRESHOLD = 0.35


class ColourTextureHealthModel:
    """OpenCV colour/texture health anomaly detector. Not a trained model."""

    name = "colour_texture_health"
    model_version = "colour-texture-v0"
    is_mock = False

    def __init__(self, *, variety_confidence_multiplier: float = 1.0) -> None:
        self.variety_confidence_multiplier = float(np.clip(variety_confidence_multiplier, 0.1, 1.0))

    def assess(
        self, image: np.ndarray, detection: FruitDetectionResult | None = None
    ) -> HealthResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot assess health on an empty image.")

        features = extract_features(image)

        browning = _clamp01(features.browning_ratio / 0.35)
        chlorosis = _clamp01(features.chlorosis_ratio / 0.60)
        dark = _clamp01(features.dark_ratio / 0.50)
        # Low texture energy inside the scene suggests smeared/lesion-like
        # regions or simply an out-of-focus frame; treated as a weak signal.
        lesion = _clamp01(1.0 - features.texture_variance / 600.0)

        penalty = (
            WEIGHT_BROWNING * browning
            + WEIGHT_CHLOROSIS * chlorosis
            + WEIGHT_DARK * dark
            + WEIGHT_LESION * lesion
        )
        health_score = float(np.clip(1.0 - penalty, 0.0, 1.0))

        possible_indicators: list[str] = []
        if features.browning_ratio >= BROWNING_INDICATOR_THRESHOLD:
            possible_indicators.append(
                "possible disease indicator: brown or necrotic surface patches"
            )
        if features.chlorosis_ratio >= CHLOROSIS_INDICATOR_THRESHOLD:
            possible_indicators.append(
                "possible nutrient or water stress indicator: widespread yellowing"
            )
        if features.dark_ratio >= DARK_INDICATOR_THRESHOLD:
            possible_indicators.append(
                "image is largely underexposed; health assessment is unreliable"
            )

        # Confidence drops when the scene is dark or flat.
        confidence = float(
            np.clip(
                (0.55 + 0.35 * _clamp01(features.texture_variance / 700.0))
                * (1.0 - 0.6 * dark)
                * self.variety_confidence_multiplier,
                0.05,
                0.90,
            )
        )

        notes = [
            "Colour/texture heuristic, not a trained disease classifier.",
            f"Any indicator listed is a possible signal only and {REQUIRES_CONFIRMATION} by a local agricultural officer.",
        ]
        if detection and detection.fruit_count == 0:
            notes.append("No fruit detections; assessment used whole-scene statistics.")

        return HealthResult(
            health_score=health_score,
            confidence=confidence,
            provider=self.name,
            model_version=self.model_version,
            is_mock=False,
            indicators={
                "browning_ratio": round(features.browning_ratio, 4),
                "chlorosis_ratio": round(features.chlorosis_ratio, 4),
                "dark_ratio": round(features.dark_ratio, 4),
                "texture_variance": round(features.texture_variance, 3),
                "penalty": round(penalty, 4),
                "components": {
                    "browning": round(browning, 4),
                    "chlorosis": round(chlorosis, 4),
                    "dark": round(dark, 4),
                    "lesion": round(lesion, 4),
                },
            },
            possible_indicators=possible_indicators,
            notes=notes,
        )


def _clamp01(value: float) -> float:
    return float(np.clip(value, 0.0, 1.0))


__all__ = [
    "BROWNING_INDICATOR_THRESHOLD",
    "CHLOROSIS_INDICATOR_THRESHOLD",
    "ColourTextureHealthModel",
    "DARK_INDICATOR_THRESHOLD",
]
