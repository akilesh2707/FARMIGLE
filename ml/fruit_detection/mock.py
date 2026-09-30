"""Deterministic mock fruit detector.

Used whenever no trained detector is available (``MOCK_SERVICES=true``, the
default). It:

* seeds a pseudo-random generator from a SHA-256 digest of the image, so the
  same photo always produces the same boxes in the same places;
* derives the ripening tint of each synthetic box from the image's own colour
  statistics, so a photo of yellow-orange fruit really does score higher than a
  photo of green fruit;
* reports ``is_mock=True`` and an explicit note, so no downstream consumer can
  mistake the output for a real model result.
"""

from __future__ import annotations

import random
from typing import Any

import numpy as np

from backend.core.errors import ProviderError
from ml.fruit_detection.base import (
    FruitDetection,
    FruitDetectionResult,
    detection_confidence,
)
from ml.preprocessing.features import (
    digest_seed,
    extract_features,
    image_digest,
    ripeness_colour_index,
)

NOTE = (
    "MOCK DETECTOR: no trained fruit-detection weights are bundled with this "
    "project. Counts and boxes are synthetic, derived deterministically from "
    "the image digest. Do not present as a model prediction."
)


class MockFruitDetector:
    """Deterministic, clearly-labelled stand-in for a trained YOLO detector."""

    name = "mock_fruit_detector"
    is_mock = True
    model_version = "mock-v0"

    def __init__(
        self,
        *,
        min_fruit: int = 4,
        max_fruit: int = 26,
        classes: list[str] | None = None,
        max_detections: int = 400,
        **_: Any,
    ) -> None:
        self.min_fruit = max(1, int(min_fruit))
        self.max_fruit = max(self.min_fruit, int(max_fruit))
        self.classes = classes or ["mango"]
        self.max_detections = max_detections

    def detect(self, image: np.ndarray) -> FruitDetectionResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot run detection on an empty image.")

        height, width = image.shape[:2]
        digest = image_digest(image)
        rng = random.Random(digest_seed(digest))
        features = extract_features(image)
        tint = ripeness_colour_index(features)

        count = rng.randint(self.min_fruit, self.max_fruit)
        count = min(count, self.max_detections)

        image_area = float(max(1, width * height))
        detections: list[FruitDetection] = []
        for _ in range(count):
            # Keep boxes inside the frame with a small margin.
            box_width = rng.uniform(0.05, 0.20) * width
            box_height = rng.uniform(0.05, 0.20) * height
            x_min = rng.uniform(0, max(1.0, width - box_width))
            y_min = rng.uniform(0, max(1.0, height - box_height))
            x_max = min(width, x_min + box_width)
            y_max = min(height, y_min + box_height)

            # Per-fruit tint jitter around the scene tint, clamped to [0, 1].
            per_fruit = float(np.clip(tint + rng.uniform(-0.12, 0.12), 0.0, 1.0))
            detections.append(
                FruitDetection(
                    label=rng.choice(self.classes),
                    confidence=round(rng.uniform(0.42, 0.94), 4),
                    bbox=(int(x_min), int(y_min), int(x_max), int(y_max)),
                    area_ratio=((x_max - x_min) * (y_max - y_min)) / image_area,
                    ripeness_score=round(per_fruit, 4),
                )
            )

        return FruitDetectionResult(
            provider=self.name,
            model_version=self.model_version,
            is_mock=True,
            detections=detections,
            image_width=width,
            image_height=height,
            confidence=detection_confidence(detections),
            fruit_coverage_ratio=min(1.0, sum(item.area_ratio for item in detections)),
            notes=[
                NOTE,
                f"image_digest={digest[:16]}",
                f"scene_colour_ripeness_index={tint:.4f}",
            ],
        )


__all__: list[str] = ["MockFruitDetector", "NOTE"]
