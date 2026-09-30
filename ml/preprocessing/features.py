"""Colour and texture features extracted from a preprocessed image.

These are *features*, not model outputs. Both the documented colour/texture
implementations (Section 7 M6: "a lightweight color/texture health module") and
the deterministic mock providers consume them, so a mock result is at least
image-dependent rather than a fixed constant.

The hue bands below are a mango-specific convention, not a universal truth
(Section 9.1 reality 2: "some mangoes stay green when ripe"). The band edges
are therefore exported as named constants so they can be tuned per variety.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np

# OpenCV hue is 0-179 (degrees/2). Bands expressed in OpenCV units.
HUE_RED = (0, 9)
HUE_ORANGE = (10, 22)
HUE_YELLOW = (23, 34)
HUE_GREEN = (35, 85)
HUE_BLUE = (86, 130)
HUE_MAGENTA = (131, 179)

# Minimum saturation/value for a pixel to count as "coloured fruit surface"
# rather than shadow, sky or soil.
COLOUR_MIN_SATURATION = 60
COLOUR_MIN_VALUE = 40


@dataclass(frozen=True)
class ImageFeatures:
    """Colour/texture summary of one image."""

    mean_hue: float
    mean_saturation: float
    mean_value: float
    green_ratio: float
    yellow_ratio: float
    orange_ratio: float
    red_ratio: float
    dark_ratio: float
    browning_ratio: float
    chlorosis_ratio: float
    texture_variance: float
    edge_density: float
    width: int
    height: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_hue": round(self.mean_hue, 3),
            "mean_saturation": round(self.mean_saturation, 3),
            "mean_value": round(self.mean_value, 3),
            "green_ratio": round(self.green_ratio, 4),
            "yellow_ratio": round(self.yellow_ratio, 4),
            "orange_ratio": round(self.orange_ratio, 4),
            "red_ratio": round(self.red_ratio, 4),
            "dark_ratio": round(self.dark_ratio, 4),
            "browning_ratio": round(self.browning_ratio, 4),
            "chlorosis_ratio": round(self.chlorosis_ratio, 4),
            "texture_variance": round(self.texture_variance, 3),
            "edge_density": round(self.edge_density, 5),
            "width": self.width,
            "height": self.height,
        }


def extract_features(image: np.ndarray) -> ImageFeatures:
    """Compute :class:`ImageFeatures` from a BGR image."""
    import cv2

    if image is None or image.size == 0:
        raise ValueError("Cannot extract features from an empty image.")

    if image.ndim == 2:
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        bgr = image[:, :, :3]
    height, width = bgr.shape[:2]

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int32)
    saturation = hsv[:, :, 1].astype(np.int32)
    value = hsv[:, :, 2].astype(np.int32)

    coloured = (saturation >= COLOUR_MIN_SATURATION) & (value >= COLOUR_MIN_VALUE)
    coloured_count = int(coloured.sum())
    total = max(1, height * width)
    coloured_denominator = max(1, coloured_count)

    def _band_ratio(band: tuple[int, int]) -> float:
        selector = coloured & (hue >= band[0]) & (hue <= band[1])
        return float(selector.sum()) / coloured_denominator

    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)

    # Browning / necrosis proxy: a noticeable fraction of low-saturation,
    # low-value, warm-hued area. Section 13.1 wording discipline applies - this
    # is an *indicator*, never a diagnosis.
    browning = (
        (saturation < 120)
        & (value < 140)
        & ((hue <= HUE_ORANGE[1]) | (hue >= HUE_MAGENTA[0]))
    )
    # Chlorosis proxy: yellowing without the orange shift of ripening.
    chlorosis = coloured & (hue >= HUE_YELLOW[0]) & (hue <= HUE_GREEN[1])
    dark = value < 45
    edges = cv2.Canny(gray, 60, 160)

    return ImageFeatures(
        mean_hue=float(hue.mean()),
        mean_saturation=float(saturation.mean()),
        mean_value=float(value.mean()),
        green_ratio=_band_ratio(HUE_GREEN),
        yellow_ratio=_band_ratio(HUE_YELLOW),
        orange_ratio=_band_ratio(HUE_ORANGE),
        red_ratio=_band_ratio(HUE_RED),
        dark_ratio=float(dark.sum()) / total,
        browning_ratio=float(browning.sum()) / total,
        chlorosis_ratio=float(chlorosis.sum()) / total,
        texture_variance=float(laplacian.var()),
        edge_density=float(edges.mean()) / 255.0,
        width=width,
        height=height,
    )


def ripeness_colour_index(features: ImageFeatures) -> float:
    """Map the colour bands onto a 0-1 ripeness proxy.

    ``(orange + yellow) / (orange + yellow + green)`` with a small weight for
    red (over-ripe). Returns 0.5 when no coloured fruit surface is visible,
    which is the "no evidence" midpoint rather than a fake confident answer.
    """
    warm = features.orange_ratio + features.yellow_ratio + 0.5 * features.red_ratio
    green = features.green_ratio
    denominator = warm + green
    if denominator <= 1e-6:
        return 0.5
    return float(np.clip(warm / denominator, 0.0, 1.0))


def image_digest(image: np.ndarray, size: int = 64) -> str:
    """Stable SHA-256 of a normalised thumbnail.

    Used to seed deterministic mock providers: the same photo always yields the
    same mock result, which is what makes the demo and the tests reproducible.
    """
    import cv2

    if image is None or image.size == 0:
        return hashlib.sha256(b"empty").hexdigest()
    gray = image if image.ndim == 2 else cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    thumbnail = cv2.resize(gray, (size, size), interpolation=cv2.INTER_AREA)
    return hashlib.sha256(np.ascontiguousarray(thumbnail).tobytes()).hexdigest()


def digest_seed(digest: str) -> int:
    return int(digest[:16], 16)


__all__ = [
    "COLOUR_MIN_SATURATION",
    "COLOUR_MIN_VALUE",
    "HUE_BLUE",
    "HUE_GREEN",
    "HUE_MAGENTA",
    "HUE_ORANGE",
    "HUE_RED",
    "HUE_YELLOW",
    "ImageFeatures",
    "digest_seed",
    "extract_features",
    "image_digest",
    "ripeness_colour_index",
]
