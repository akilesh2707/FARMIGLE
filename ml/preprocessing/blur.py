"""Blur detection (Section 7 M3 pipeline step 2).

Variance of the Laplacian: the standard cheap sharpness proxy. A sharp image
has strong second derivatives at edges, so the variance is high; a blurry image
has almost none. Thresholds are per-crop (``configs/thresholds/<crop>.yaml``).
"""

from __future__ import annotations

import numpy as np


def laplacian_variance(image: np.ndarray) -> float:
    """Variance of the Laplacian, computed on the grayscale image.

    Independent of daylight/colour cast, which is why it is used instead of a
    raw gradient or edge count.
    """
    import cv2

    if image is None or image.size == 0:
        return 0.0
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)
    return float(laplacian.var())


def tenengrad_score(image: np.ndarray) -> float:
    """Sobel-gradient energy - a second, independent sharpness signal.

    Reported alongside the Laplacian variance so a downstream consumer can tell
    "uniformly soft" from "has some structure".
    """
    import cv2

    if image is None or image.size == 0:
        return 0.0
    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    magnitude = np.sqrt(gx * gx + gy * gy)
    return float(magnitude.mean())


__all__ = ["laplacian_variance", "tenengrad_score"]
