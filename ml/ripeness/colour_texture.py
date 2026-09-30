"""Colour/texture ripeness estimator - the real MVP implementation.

Section 7 M6: "YOLO fine-tuned on a Mango + Banana dataset, plus a lightweight
color/texture health module." This module is that lightweight colour/texture
part. It is a real image-analysis implementation (no learned weights), and it
reports its own confidence so a variety that ripens green (Section 9.1 reality
2) is not silently mis-scored.

Method
------
1. Scene colour progression: the share of coloured fruit surface that has moved
   from the green band into the yellow/orange/red bands.
2. Per-fruit scores from the detector, when available, are averaged in.
3. Texture/contrast sharpness of the fruit region acts as a light quality
   weighting, because colour statistics are unreliable in flat lighting.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from backend.core.errors import ProviderError
from ml.fruit_detection.base import FruitDetectionResult
from ml.preprocessing.features import (
    extract_features,
    image_digest,
    ripeness_colour_index,
)
from ml.ripeness.base import RipenessResult

DETECTOR_WEIGHT = 0.55
SCENE_WEIGHT = 0.45


class ColourTextureRipenessModel:
    """OpenCV colour/texture ripeness estimator. Not a trained model."""

    name = "colour_texture_ripeness"
    model_version = "colour-texture-v0"
    is_mock = False

    def __init__(self, *, variety_confidence_multiplier: float = 1.0) -> None:
        self.variety_confidence_multiplier = float(
            np.clip(variety_confidence_multiplier, 0.1, 1.0)
        )

    def score(
        self, image: np.ndarray, detection: FruitDetectionResult | None = None
    ) -> RipenessResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot score ripeness on an empty image.")

        features = extract_features(image)
        scene_index = ripeness_colour_index(features)

        per_fruit = detection.ripeness_by_detection() if detection else []
        if per_fruit:
            detector_score = float(np.mean(per_fruit))
            detector_spread = float(np.std(per_fruit))
            effective_detector_weight = DETECTOR_WEIGHT * min(
                1.0, len(per_fruit) / 5.0
            )  # thin evidence counts for less
            blend_denominator = effective_detector_weight + SCENE_WEIGHT
            score = (
                detector_score * effective_detector_weight + scene_index * SCENE_WEIGHT
            ) / blend_denominator
        else:
            detector_score = None
            detector_spread = 0.0
            score = scene_index

        # Colour evidence is weak in dark, flat or washed-out scenes.
        quality_factor = float(
            np.clip(
                0.45
                + 0.30 * _normalised(features.texture_variance, 30.0, 900.0)
                + 0.25 * _normalised(features.mean_saturation, 40.0, 180.0),
                0.0,
                1.0,
            )
        )
        confidence = float(
            np.clip(
                quality_factor
                * (1.0 - 0.5 * min(1.0, detector_spread))
                * self.variety_confidence_multiplier,
                0.05,
                0.95,
            )
        )

        indicators: dict[str, Any] = {
            "ripeness_colour_index": round(scene_index, 4),
            "detector_ripeness_mean": None if detector_score is None else round(detector_score, 4),
            "detector_ripeness_spread": round(detector_spread, 4),
            "colour_bands": {
                "green": round(features.green_ratio, 4),
                "yellow": round(features.yellow_ratio, 4),
                "orange": round(features.orange_ratio, 4),
                "red": round(features.red_ratio, 4),
            },
            "quality_factor": round(quality_factor, 4),
            "fruit_count": detection.fruit_count if detection else 0,
        }
        notes = [
            "Colour/texture heuristic, not a trained ripeness classifier.",
            "Green-ripening mango varieties may be under-scored; confidence is reduced accordingly.",
        ]
        if detection is None or not detection.fruit_count:
            notes.append("No fruit detections available; score falls back to whole-scene colour.")

        return RipenessResult(
            score=float(np.clip(score, 0.0, 1.0)),
            confidence=confidence,
            provider=self.name,
            model_version=self.model_version,
            is_mock=False,
            indicators=indicators,
            notes=notes,
        )


def _normalised(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return float(np.clip((value - low) / (high - low), 0.0, 1.0))


__all__ = ["ColourTextureRipenessModel", "DETECTOR_WEIGHT", "SCENE_WEIGHT", "image_digest"]
