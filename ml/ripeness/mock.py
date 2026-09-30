"""Deterministic mock ripeness model.

Used when ``MOCK_SERVICES=true`` (the default). The score is a deterministic
function of the image digest and the image's own colour statistics, so it is
reproducible for tests yet still visibly responds to a green versus a yellow
photograph.

It is always labelled ``is_mock=True`` and carries an explicit note.
"""

from __future__ import annotations

import random

import numpy as np

from backend.core.errors import ProviderError
from ml.fruit_detection.base import FruitDetectionResult
from ml.preprocessing.features import (
    digest_seed,
    extract_features,
    image_digest,
    ripeness_colour_index,
)
from ml.ripeness.base import RipenessResult

NOTE = (
    "MOCK RIPENESS MODEL: no trained ripeness weights are bundled. The score "
    "is derived deterministically from the image digest and colour statistics. "
    "Do not present as a model prediction."
)


class MockRipenessModel:
    name = "mock_ripeness"
    model_version = "mock-v0"
    is_mock = True

    def score(
        self, image: np.ndarray, detection: FruitDetectionResult | None = None
    ) -> RipenessResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot score ripeness on an empty image.")

        digest = image_digest(image)
        rng = random.Random(digest_seed(digest) ^ 0x5EED)
        features = extract_features(image)
        colour_index = ripeness_colour_index(features)

        per_fruit = detection.ripeness_by_detection() if detection else []
        detector_mean = float(np.mean(per_fruit)) if per_fruit else None

        # Anchor to the real colour index, then add a small deterministic jitter
        # so the value is not simply a copy of the heuristic.
        base = detector_mean if detector_mean is not None else colour_index
        score = float(np.clip(base + rng.uniform(-0.06, 0.06), 0.0, 1.0))
        confidence = float(np.clip(rng.uniform(0.45, 0.85), 0.05, 0.95))

        return RipenessResult(
            score=score,
            confidence=confidence,
            provider=self.name,
            model_version=self.model_version,
            is_mock=True,
            indicators={
                "image_digest": digest[:16],
                "colour_ripeness_index": round(colour_index, 4),
                "detector_ripeness_mean": None if detector_mean is None else round(detector_mean, 4),
                "fruit_count": detection.fruit_count if detection else 0,
            },
            notes=[NOTE, "Deterministic for a given image: identical input yields identical output."],
        )


__all__ = ["MockRipenessModel", "NOTE"]
