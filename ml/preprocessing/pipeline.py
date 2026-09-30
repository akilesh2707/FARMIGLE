"""Image preprocessing pipeline (Section 7 M3).

Documented order, implemented literally::

    Image
     -> Quality check   (evaluate_quality, incl. Laplacian blur detection)
     -> Blur detection  (part of the quality gate; measured and reported)
     -> CLAHE lighting normalization
     -> Gray-world color constancy
     -> Inference

Each stage is independently callable, so a test can exercise CLAHE without the
quality gate, or the blur metric without decoding a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from backend.core.errors import ImageQualityError, ImageUnreadableError
from ml.preprocessing.color import gray_world
from ml.preprocessing.lighting import apply_clahe
from ml.preprocessing.quality import QualityReport, evaluate_quality

DEFAULT_PREPROCESSING: dict[str, Any] = {
    "clahe_enabled": True,
    "clahe_clip_limit": 2.0,
    "clahe_grid_size": 8,
    "gray_world_enabled": True,
    "gray_world_target_luma": 128.0,
    "max_dimension_px": 1280,
}


@dataclass
class PreprocessResult:
    """Decoded, normalised image plus a full audit trail of what was done."""

    image: np.ndarray
    quality: QualityReport
    steps: list[dict[str, Any]] = field(default_factory=list)
    input_bytes: int = 0
    decoded_width: int = 0
    decoded_height: int = 0

    @property
    def width(self) -> int:
        return int(self.image.shape[1])

    @property
    def height(self) -> int:
        return int(self.image.shape[0])

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_bytes": self.input_bytes,
            "decoded_width": self.decoded_width,
            "decoded_height": self.decoded_height,
            "processed_width": self.width,
            "processed_height": self.height,
            "quality": self.quality.to_dict(),
            "steps": self.steps,
        }


def decode_image(data: bytes) -> np.ndarray:
    """Decode JPEG/PNG/WebP/BMP bytes into a BGR OpenCV image."""
    import cv2

    if not data:
        raise ImageUnreadableError("The uploaded file is empty.")
    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ImageUnreadableError(
            "The uploaded file could not be decoded as an image. "
            "Supported formats: JPEG, PNG, WebP, BMP."
        )
    return image


def resize_for_inference(
    image: np.ndarray, *, max_dimension_px: int = 1280, enabled: bool = True
) -> tuple[np.ndarray, dict[str, Any]]:
    """Downscale so the longest side is at most ``max_dimension_px``.

    Section 10.5: keep single-image inference cheap on an always-CPU Cloud Run
    instance. Aspect ratio is preserved and INTER_AREA is used so no aliasing
    is introduced that could soften the blur metric.
    """
    import cv2

    height, width = image.shape[:2]
    longest = max(width, height)
    if not enabled or max_dimension_px <= 0 or longest <= max_dimension_px:
        return image, {"step": "resize", "applied": False, "reason": "already_small_enough"}

    scale = max_dimension_px / float(longest)
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    resized = cv2.resize(image, target, interpolation=cv2.INTER_AREA)
    return resized, {
        "step": "resize",
        "applied": True,
        "from": [width, height],
        "to": [resized.shape[1], resized.shape[0]],
        "scale": round(scale, 6),
    }


class Preprocessor:
    """The full quality-gate + normalisation pipeline."""

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        merged = dict(DEFAULT_PREPROCESSING)
        for key, value in (config or {}).items():
            if key in merged:
                merged[key] = value
        self.config = merged

    def preprocess(
        self,
        data: bytes,
        *,
        quality_config: Mapping[str, Any] | None = None,
        enforce_quality: bool = True,
    ) -> PreprocessResult:
        """Decode, gate, normalise.

        Raises :class:`ImageQualityError` when the gate fails and
        ``enforce_quality`` is true, with the failing reason, a farmer-friendly
        remedy and the raw metrics.
        """
        image = decode_image(data)
        decoded_height, decoded_width = image.shape[:2]
        report = evaluate_quality(image, quality_config)

        if enforce_quality and not report.passed:
            raise ImageQualityError(
                report.remedy or "The image quality is too low to analyse.",
                reason=report.primary_reason or "quality_check_failed",
                remedy=report.remedy or "Please retake the photo.",
                metrics=report.metrics.to_dict(),
            )

        steps: list[dict[str, Any]] = [
            {"step": "decode", "input_bytes": len(data), "width": decoded_width, "height": decoded_height},
            {"step": "quality_check", **report.to_dict()},
        ]

        resized, resize_info = resize_for_inference(
            image, max_dimension_px=int(self.config["max_dimension_px"])
        )
        steps.append(resize_info)

        lit, clahe_info = apply_clahe(
            resized,
            clip_limit=float(self.config["clahe_clip_limit"]),
            grid_size=int(self.config["clahe_grid_size"]),
            enabled=bool(self.config["clahe_enabled"]),
        )
        steps.append(clahe_info)

        colour, gray_info = gray_world(
            lit,
            target_luma=float(self.config["gray_world_target_luma"]),
            enabled=bool(self.config["gray_world_enabled"]),
        )
        steps.append(gray_info)

        return PreprocessResult(
            image=colour,
            quality=report,
            steps=steps,
            input_bytes=len(data),
            decoded_width=decoded_width,
            decoded_height=decoded_height,
        )


def preprocess_bytes(
    data: bytes,
    *,
    preprocessing_config: Mapping[str, Any] | None = None,
    quality_config: Mapping[str, Any] | None = None,
    enforce_quality: bool = True,
) -> PreprocessResult:
    """Convenience one-shot wrapper around :class:`Preprocessor`."""
    return Preprocessor(preprocessing_config).preprocess(
        data, quality_config=quality_config, enforce_quality=enforce_quality
    )


__all__ = [
    "DEFAULT_PREPROCESSING",
    "PreprocessResult",
    "Preprocessor",
    "decode_image",
    "preprocess_bytes",
    "resize_for_inference",
]
