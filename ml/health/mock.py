"""Deterministic mock health model.

Used when ``MOCK_SERVICES=true`` (the default). Anchored to the real
colour/texture proxies so the mock tracks the image, with a deterministic
jitter seeded from the image digest. Always labelled ``is_mock=True``.
"""

from __future__ import annotations

import random

import numpy as np

from backend.core.errors import ProviderError
from ml.fruit_detection.base import FruitDetectionResult
from ml.health.base import REQUIRES_CONFIRMATION, HealthResult
from ml.preprocessing.features import digest_seed, extract_features, image_digest

NOTE = (
    "MOCK HEALTH MODEL: no trained health/disease weights are bundled. The "
    "score is derived deterministically from the image digest and colour "
    "statistics. Do not present as a model prediction."
)


class MockHealthModel:
    name = "mock_health"
    model_version = "mock-v0"
    is_mock = True

    def assess(
        self, image: np.ndarray, detection: FruitDetectionResult | None = None
    ) -> HealthResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot assess health on an empty image.")

        digest = image_digest(image)
        rng = random.Random(digest_seed(digest) ^ 0x0EA1)
        detections = detection.fruit_count if detection else 0
        features = extract_features(image)

        penalty = min(
            1.0,
            0.9 * features.browning_ratio
            + 0.35 * features.chlorosis_ratio
            + 0.25 * features.dark_ratio,
        )
        health_score = float(np.clip(1.0 - penalty + rng.uniform(-0.05, 0.05), 0.0, 1.0))
        confidence = float(np.clip(rng.uniform(0.45, 0.85), 0.05, 0.95))

        possible: list[str] = []
        if health_score < 0.55:
            possible.append(
                "possible disease indicator: colour/texture anomaly in the frame"
            )

        return HealthResult(
            health_score=health_score,
            confidence=confidence,
            provider=self.name,
            model_version=self.model_version,
            is_mock=True,
            indicators={
                "image_digest": digest[:16],
                "browning_ratio": round(features.browning_ratio, 4),
                "chlorosis_ratio": round(features.chlorosis_ratio, 4),
                "dark_ratio": round(features.dark_ratio, 4),
                "fruit_count": detections,
            },
            possible_indicators=possible,
            notes=[
                NOTE,
                f"Any indicator listed is a possible signal only and {REQUIRES_CONFIRMATION}.",
            ],
        )


__all__ = ["MockHealthModel", "NOTE"]
