"""Provider factories: one place that decides mock vs real implementations.

Every factory takes the resolved :class:`~backend.core.config.Settings` and the
crop configuration, so the API and the analysis orchestrator never branch on
"are we in mock mode?" themselves.

Nothing here fabricates a real model: the ``yolo`` path raises
:class:`~backend.core.errors.ProviderUnavailableError` when weights are absent.
"""

from __future__ import annotations

from typing import Any

from backend.core.config import Settings, get_settings
from backend.core.errors import ProviderUnavailableError
from backend.core.logging import get_logger
from ml.fruit_detection.base import FruitDetector
from ml.fruit_detection.mock import MockFruitDetector
from ml.health.base import HealthModel
from ml.health.colour_texture import ColourTextureHealthModel
from ml.health.mock import MockHealthModel
from ml.ripeness.base import RipenessModel
from ml.ripeness.colour_texture import ColourTextureRipenessModel
from ml.ripeness.mock import MockRipenessModel

logger = get_logger(__name__)


def _variety_multiplier(crop_config: Any | None, variety_id: str | None) -> float:
    """Section 9.1 reality 2: reduce confidence for green-ripening varieties."""
    if crop_config is None:
        return 1.0
    try:
        variety = crop_config.variety(variety_id)
    except Exception:  # pragma: no cover - defensive
        return 1.0
    multiplier = float(variety.get("confidence_multiplier", 1.0))
    if not variety.get("ripeness_uses_color", True):
        multiplier = min(multiplier, 0.6)
    return multiplier


def selected_ml_provider(settings: Settings, field: str) -> str:
    """Resolve a per-model provider switch, defaulting to the shared one.

    ``ML_RIPENESS_PROVIDER``/``ML_HEALTH_PROVIDER`` override ``ML_PROVIDER``;
    a value left at its default falls back to the global switch so existing
    deployments keep working.
    """
    specific = getattr(settings, field, None)
    if specific and specific != "mock":
        return str(specific)
    return str(settings.ml_provider)


def build_fruit_detector(
    settings: Settings | None = None,
    *,
    thresholds: Any | None = None,
    crop_config: Any | None = None,
) -> FruitDetector:
    resolved = settings or get_settings()
    config = (thresholds.fruit_detection if thresholds is not None else {}) or {}
    classes = ["mango"]
    if crop_config is not None:
        classes = [crop_config.crop]

    if resolved.ml_provider == "yolo":
        if not resolved.fruit_detector_weights:
            raise ProviderUnavailableError(
                "ML_PROVIDER=yolo requires FRUIT_DETECTOR_WEIGHTS pointing at a "
                "trained model file. None is bundled with this repository."
            )
        from ml.fruit_detection.yolo import YOLOFruitDetector

        return YOLOFruitDetector(
            resolved.fruit_detector_weights,
            classes=classes,
            confidence_threshold=float(config.get("confidence_threshold", 0.35)),
            iou_threshold=float(config.get("iou_threshold", 0.45)),
            max_detections=int(config.get("max_detections", 400)),
            device=resolved.ml_device,
        )

    if resolved.ml_provider == "heuristic":
        logger.info(
            "fruit_detection_heuristic_selected",
            extra={"note": "no heuristic detector exists; falling back to mock detector"},
        )

    return MockFruitDetector(
        classes=classes,
        max_detections=int(config.get("max_detections", 400)),
    )


def build_ripeness_model(
    settings: Settings | None = None,
    *,
    crop_config: Any | None = None,
    variety_id: str | None = None,
) -> RipenessModel:
    resolved = settings or get_settings()
    # Ripeness and health have their own switches: a deployment can run the
    # real detector with one colour model and a mock for the other.
    if selected_ml_provider(resolved, "ml_ripeness_provider") == "heuristic":
        return ColourTextureRipenessModel(
            variety_confidence_multiplier=_variety_multiplier(crop_config, variety_id)
        )
    return MockRipenessModel()


def build_health_model(
    settings: Settings | None = None,
    *,
    crop_config: Any | None = None,
    variety_id: str | None = None,
) -> HealthModel:
    resolved = settings or get_settings()
    if selected_ml_provider(resolved, "ml_health_provider") == "heuristic":
        return ColourTextureHealthModel(
            variety_confidence_multiplier=_variety_multiplier(crop_config, variety_id)
        )
    return MockHealthModel()


__all__ = [
    "build_fruit_detector",
    "selected_ml_provider",
    "build_health_model",
    "build_ripeness_model",
]
