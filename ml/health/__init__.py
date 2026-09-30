"""M6 - Crop health anomaly indicators.

``HealthModel`` returns a normalised health score plus *possible* indicators.
It never returns a diagnosis (Section 13.1).
"""

from ml.health.base import REQUIRES_CONFIRMATION, HealthModel, HealthResult
from ml.health.colour_texture import ColourTextureHealthModel
from ml.health.mock import MockHealthModel

__all__ = [
    "ColourTextureHealthModel",
    "HealthModel",
    "HealthResult",
    "MockHealthModel",
    "REQUIRES_CONFIRMATION",
]
