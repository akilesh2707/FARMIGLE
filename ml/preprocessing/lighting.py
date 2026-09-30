"""Lighting normalisation: CLAHE on the LAB L-channel (Section 7 M3 step 3).

Contrast Limited Adaptive Histogram Equalisation equalises local contrast
without blowing out highlights, which makes downstream colour-based ripeness
scoring far less sensitive to shade versus full sun. Toggleable via
``preprocessing.clahe_enabled``.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def apply_clahe(
    image: np.ndarray,
    *,
    clip_limit: float = 2.0,
    grid_size: int = 8,
    enabled: bool = True,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return ``(image, info)``.

    CLAHE is applied to the L channel in LAB space so the a/b (colour) channels
    that ripeness scoring depends on are left untouched.
    """
    info: dict[str, Any] = {"step": "clahe", "applied": False}
    if not enabled:
        info["reason"] = "disabled_by_config"
        return image, info
    if image is None or image.size == 0:
        info["reason"] = "empty_image"
        return image, info

    import cv2

    grid = max(1, int(grid_size))
    clahe = cv2.createCLAHE(clipLimit=float(clip_limit), tileGridSize=(grid, grid))

    if image.ndim == 2:
        result = clahe.apply(image)
    else:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        equalised = clahe.apply(l_channel)
        result = cv2.cvtColor(cv2.merge([equalised, a_channel, b_channel]), cv2.COLOR_LAB2BGR)

    info.update(
        {
            "applied": True,
            "clip_limit": float(clip_limit),
            "grid_size": grid,
            "mean_luma_before": round(float(_mean_luma(image)), 3),
            "mean_luma_after": round(float(_mean_luma(result)), 3),
        }
    )
    return result, info


def _mean_luma(image: np.ndarray) -> float:
    import cv2

    gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(np.asarray(gray, dtype=np.float64).mean())


__all__ = ["apply_clahe"]
