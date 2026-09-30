"""M5/M6 - Fruit detection providers.

``FruitDetector`` is the interface. ``MockFruitDetector`` is the default;
``YOLOFruitDetector`` is the real integration point and requires weights that
are not bundled with this repository.
"""

from ml.fruit_detection.base import (
    FruitDetection,
    FruitDetectionResult,
    FruitDetector,
    detection_confidence,
)
from ml.fruit_detection.mock import MockFruitDetector

__all__ = [
    "FruitDetection",
    "FruitDetectionResult",
    "FruitDetector",
    "MockFruitDetector",
    "detection_confidence",
]
