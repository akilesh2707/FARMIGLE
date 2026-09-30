"""Colour constancy: gray-world normalisation (Section 7 M3 step 4).

The gray-world assumption is that, averaged over a whole scene, the channels
should be roughly equal. Scaling each channel so its mean equals the overall
luma removes the warm/cool cast introduced by sunlight colour temperature and
camera white balance.

Caveat (Section 9.1 reality 2): colour is a weaker ripeness signal for mangoes
than for many fruit, so the output of this step is one input among several and
the ripeness provider reports its own confidence. Toggleable via
``preprocessing.gray_world_enabled``.
"""

from __future__ import annotations

from typing import Any

import numpy as np


def gray_world(
    image: np.ndarray,
    *,
    target_luma: float = 128.0,
    enabled: bool = True,
    max_gain: float = 3.0,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Return ``(image, info)``. Gains are clamped to ``[1/max_gain, max_gain]``.

    Clamping prevents a genuinely yellow (ripe mango) scene from being
    "corrected" into a neutral one; that would destroy the very signal the
    ripeness model needs.
    """
    info: dict[str, Any] = {"step": "gray_world", "applied": False}
    if not enabled:
        info["reason"] = "disabled_by_config"
        return image, info
    if image is None or image.size == 0:
        info["reason"] = "empty_image"
        return image, info
    if image.ndim != 3 or image.shape[2] < 3:
        info["reason"] = "grayscale_image"
        return image, info

    data = image[:, :, :3].astype(np.float64)
    channel_means = data.reshape(-1, 3).mean(axis=0)
    gray_mean = float(channel_means.mean())
    if gray_mean < 1e-6 or any(mean < 1e-6 for mean in channel_means):
        info["reason"] = "degenerate_channel"
        return image, info

    target = max(1.0, float(target_luma))
    gains = (gray_mean / channel_means) * (target / gray_mean)
    lower, upper = 1.0 / max_gain, max_gain
    clamped = np.clip(gains, lower, upper)
    corrected = np.clip(data * clamped, 0, 255).astype(np.uint8)
    if image.shape[2] > 3:
        corrected = np.dstack([corrected, image[:, :, 3:]])

    info.update(
        {
            "applied": True,
            "channel_means_before": [round(float(mean), 3) for mean in channel_means],
            "gains": [round(float(gain), 4) for gain in clamped],
            "gains_clamped": bool(np.any(np.abs(np.clip(gains, lower, upper) - gains) > 1e-9)),
        }
    )
    return corrected, info


__all__ = ["gray_world"]
