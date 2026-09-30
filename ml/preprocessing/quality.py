"""Image quality gate + metrics (Section 7 M3, Section 8.3).

This is the step that makes the honest behaviour possible: a blurry, dark or
blank photo is rejected with a retake prompt **before** any inference runs, so
the system never returns a confident prediction from unusable input.

Every check is a pure function of a decoded image and a threshold mapping, so
the whole gate is unit-testable with synthetic fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np

from ml.preprocessing.blur import laplacian_variance, tenengrad_score

# Stable check identifiers; also the `reason` value returned to the client.
CHECK_DIMENSIONS = "image_too_small"
CHECK_ASPECT = "extreme_aspect_ratio"
CHECK_BLUR = "too_blurry"
CHECK_DARK = "too_dark"
CHECK_BRIGHT = "too_bright"
CHECK_CONTRAST = "low_contrast"
CHECK_SATURATION = "low_colour_information"

# Farmer-facing remedies, one per failing check (Section 8.3 "retake prompt").
REMEDIES: dict[str, str] = {
    CHECK_DIMENSIONS: (
        "The photo is too small to analyse. Please retake it with the phone's "
        "main camera, without zooming."
    ),
    CHECK_ASPECT: (
        "The photo is unusually wide or tall. Please retake it as a normal "
        "close-up of the fruit or leaves."
    ),
    CHECK_BLUR: (
        "The image is too blurry. Please hold the camera steady, tap to focus "
        "on the fruit, and retake the photo."
    ),
    CHECK_DARK: (
        "The image is too dark. Please move to better light, or turn on the "
        "flash, and retake the photo."
    ),
    CHECK_BRIGHT: (
        "The image is overexposed or washed out. Please retake the photo "
        "without pointing directly at the sun or a strong light."
    ),
    CHECK_CONTRAST: (
        "The image has very little detail and may be a blank or covered shot. "
        "Please retake the photo with the fruit clearly in frame."
    ),
    CHECK_SATURATION: (
        "The image has almost no colour information. Please check that the "
        "camera lens is clean and retake the photo in daylight."
    ),
}

DEFAULT_QUALITY_GATE: dict[str, float] = {
    "min_width_px": 160,
    "min_height_px": 160,
    "max_aspect_ratio": 3.0,
    "min_laplacian_variance": 40.0,
    "min_mean_luma": 30.0,
    "max_mean_luma": 235.0,
    "min_dynamic_range": 15.0,
    "min_mean_saturation": 10.0,
}


@dataclass(frozen=True)
class QualityMetrics:
    """Raw measurements, always returned even when the gate passes."""

    width: int
    height: int
    aspect_ratio: float
    laplacian_variance: float
    tenengrad: float
    mean_luma: float
    p01_luma: float
    p99_luma: float
    dynamic_range: float
    mean_saturation: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "aspect_ratio": round(self.aspect_ratio, 4),
            "blur_score": round(self.laplacian_variance, 3),
            "laplacian_variance": round(self.laplacian_variance, 3),
            "tenengrad": round(self.tenengrad, 3),
            "mean_luma": round(self.mean_luma, 3),
            "luma_p01": round(self.p01_luma, 3),
            "luma_p99": round(self.p99_luma, 3),
            "dynamic_range": round(self.dynamic_range, 3),
            "mean_saturation": round(self.mean_saturation, 3),
        }


@dataclass(frozen=True)
class QualityReport:
    passed: bool
    metrics: QualityMetrics
    failed_checks: list[str] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    primary_reason: str | None = None
    remedy: str | None = None

    @property
    def blur_score(self) -> float:
        return self.metrics.laplacian_variance

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "primary_reason": self.primary_reason,
            "remedy": self.remedy,
            "failed_checks": list(self.failed_checks),
            "metrics": self.metrics.to_dict(),
            "thresholds": self.thresholds,
        }


def measure(image: np.ndarray) -> QualityMetrics:
    """Compute every quality metric for a decoded BGR (or gray) image."""
    import cv2

    if image is None or image.size == 0:
        raise ValueError("Cannot measure an empty image.")

    height, width = image.shape[:2]
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray_f = np.asarray(gray, dtype=np.float64)

    if image.ndim == 3 and image.shape[2] >= 3:
        hsv = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2HSV)
        mean_saturation = float(hsv[:, :, 1].astype(np.float64).mean())
    else:
        mean_saturation = 0.0

    p01, p99 = (float(value) for value in np.percentile(gray_f, [1, 99]))

    return QualityMetrics(
        width=int(width),
        height=int(height),
        aspect_ratio=(max(width, height) / max(1, min(width, height))),
        laplacian_variance=laplacian_variance(gray),
        tenengrad=tenengrad_score(gray),
        mean_luma=float(gray_f.mean()),
        p01_luma=p01,
        p99_luma=p99,
        dynamic_range=p99 - p01,
        mean_saturation=mean_saturation,
    )


def resolve_thresholds(config: Mapping[str, Any] | None) -> dict[str, float]:
    thresholds = dict(DEFAULT_QUALITY_GATE)
    for key, value in (config or {}).items():
        if key in thresholds and isinstance(value, (int, float)):
            thresholds[key] = float(value)
    return thresholds


def evaluate_quality(
    image: np.ndarray, config: Mapping[str, Any] | None = None
) -> QualityReport:
    """Run every quality check and report the result.

    All failing checks are collected; ``primary_reason`` is the first failure in
    priority order (size, aspect, blur, exposure, contrast, colour) because that
    is the most actionable one for the farmer to fix.
    """
    thresholds = resolve_thresholds(config)
    metrics = measure(image)
    failed: list[str] = []

    if metrics.width < thresholds["min_width_px"] or metrics.height < thresholds["min_height_px"]:
        failed.append(CHECK_DIMENSIONS)
    if metrics.aspect_ratio > thresholds["max_aspect_ratio"]:
        failed.append(CHECK_ASPECT)
    if metrics.laplacian_variance < thresholds["min_laplacian_variance"]:
        failed.append(CHECK_BLUR)
    if metrics.mean_luma < thresholds["min_mean_luma"]:
        failed.append(CHECK_DARK)
    elif metrics.mean_luma > thresholds["max_mean_luma"]:
        failed.append(CHECK_BRIGHT)
    if metrics.dynamic_range < thresholds["min_dynamic_range"]:
        failed.append(CHECK_CONTRAST)
    if metrics.mean_saturation < thresholds["min_mean_saturation"]:
        failed.append(CHECK_SATURATION)

    priority = [
        CHECK_DIMENSIONS,
        CHECK_ASPECT,
        CHECK_BLUR,
        CHECK_DARK,
        CHECK_BRIGHT,
        CHECK_CONTRAST,
        CHECK_SATURATION,
    ]
    primary = next((check for check in priority if check in failed), None)
    return QualityReport(
        passed=not failed,
        metrics=metrics,
        failed_checks=failed,
        thresholds=thresholds,
        primary_reason=primary,
        remedy=REMEDIES.get(primary) if primary else None,
    )


__all__ = [
    "CHECK_ASPECT",
    "CHECK_BLUR",
    "CHECK_BRIGHT",
    "CHECK_CONTRAST",
    "CHECK_DARK",
    "CHECK_DIMENSIONS",
    "CHECK_SATURATION",
    "DEFAULT_QUALITY_GATE",
    "QualityMetrics",
    "QualityReport",
    "REMEDIES",
    "evaluate_quality",
    "measure",
    "resolve_thresholds",
]
