"""Real YOLO fruit detector (Ultralytics) - integration point.

This class is the *only* place Ultralytics is imported. It is deliberately
never constructed unless a weights file is actually available
(``FRUIT_DETECTOR_WEIGHTS``), so the repository runs with no model present.

No trained weights ship with this project. Until a mango detector is
fine-tuned (Section 14.2), the mock provider
(:mod:`ml.fruit_detection.mock`) is what the API uses. Calling this class
without weights raises :class:`ProviderUnavailableError` rather than silently
returning fabricated detections.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.core.errors import ProviderError, ProviderUnavailableError
from backend.core.logging import get_logger
from ml.fruit_detection.base import (
    FruitDetection,
    FruitDetectionResult,
    detection_confidence,
)
from ml.preprocessing.features import extract_features, ripeness_colour_index

logger = get_logger(__name__)


class YOLOFruitDetector:
    """Thin, synchronised wrapper around an Ultralytics YOLO model."""

    is_mock = False

    def __init__(
        self,
        weights_path: str | Path,
        *,
        classes: list[str] | None = None,
        confidence_threshold: float = 0.35,
        iou_threshold: float = 0.45,
        max_detections: int = 400,
        device: str = "cpu",
        imgsz: int = 640,
    ) -> None:
        self.weights_path = Path(weights_path)
        if not self.weights_path.exists():
            raise ProviderUnavailableError(
                f"YOLO weights not found at '{self.weights_path}'. "
                "Provide FRUIT_DETECTOR_WEIGHTS or run with MOCK_SERVICES=true."
            )
        try:
            from ultralytics import YOLO  # noqa: PLC0415 - intentional lazy import
        except ImportError as exc:
            raise ProviderUnavailableError(
                "ultralytics is not installed. Install the 'ml' extra "
                "(pip install ultralytics) and provide weights to enable the "
                "real detector."
            ) from exc

        self._model = YOLO(str(self.weights_path))
        self.name = f"yolo:{self.weights_path.name}"
        self.model_version = self.weights_path.stem
        self.classes = classes or []
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self.device = device
        self.imgsz = imgsz

    def _label(self, class_index: int) -> str:
        names = getattr(self._model, "names", None) or {}
        if isinstance(names, dict) and class_index in names:
            return str(names[class_index])
        if isinstance(names, (list, tuple)) and 0 <= class_index < len(names):
            return str(names[class_index])
        if self.classes and 0 <= class_index < len(self.classes):
            return self.classes[class_index]
        return f"class_{class_index}"

    def detect(self, image: np.ndarray) -> FruitDetectionResult:
        if image is None or image.size == 0:
            raise ProviderError("Cannot run detection on an empty image.")
        height, width = image.shape[:2]
        try:
            predictions = self._model.predict(
                source=image,
                conf=self.confidence_threshold,
                iou=self.iou_threshold,
                max_det=self.max_detections,
                device=self.device,
                imgsz=self.imgsz,
                verbose=False,
            )
        except Exception as exc:  # pragma: no cover - requires weights
            logger.error("yolo_inference_failed", extra={"error_type": type(exc).__name__})
            raise ProviderError("Fruit detection provider failed.") from exc

        detections: list[FruitDetection] = []
        image_area = float(max(1, width * height))
        for prediction in predictions or []:
            boxes = getattr(prediction, "boxes", None)
            if boxes is None:
                continue
            for box in boxes:
                x_min, y_min, x_max, y_max = (int(value) for value in box.xyxy[0].tolist())
                confidence = float(box.conf[0])
                class_index = int(box.cls[0]) if box.cls is not None else 0
                crop = image[max(0, y_min) : max(0, y_max), max(0, x_min) : max(0, x_max)]
                ripeness: float | None = None
                if crop.size:
                    try:
                        ripeness = ripeness_colour_index(extract_features(crop))
                    except ValueError:
                        ripeness = None
                detections.append(
                    FruitDetection(
                        label=self._label(class_index),
                        confidence=confidence,
                        bbox=(x_min, y_min, x_max, y_max),
                        area_ratio=(max(0, x_max - x_min) * max(0, y_max - y_min)) / image_area,
                        ripeness_score=ripeness,
                    )
                )

        coverage = sum(detection.area_ratio for detection in detections)
        return FruitDetectionResult(
            provider=self.name,
            model_version=self.model_version,
            is_mock=False,
            detections=detections,
            image_width=width,
            image_height=height,
            confidence=detection_confidence(detections),
            fruit_coverage_ratio=min(1.0, coverage),
            notes=[],
        )


__all__: list[str] = ["YOLOFruitDetector"]
