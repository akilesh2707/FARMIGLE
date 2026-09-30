"""Vision and ML layer.

Perception only. Section 3.3: perception is done by CV models and OpenCV, never
by Gemini. Each sub-package exposes an interface plus a mock provider so the
backend runs before datasets or weights exist.
"""

from ml import fruit_detection, health, preprocessing, ripeness
from ml.providers import build_fruit_detector, build_health_model, build_ripeness_model

__all__ = [
    "build_fruit_detector",
    "build_health_model",
    "build_ripeness_model",
    "fruit_detection",
    "health",
    "preprocessing",
    "ripeness",
]
