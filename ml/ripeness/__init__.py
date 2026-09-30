"""M6 - Fruit ripeness scoring.

``RipenessModel`` is the interface; every score is normalised to ``[0, 1]``.
"""

from ml.ripeness.base import RipenessModel, RipenessResult
from ml.ripeness.colour_texture import ColourTextureRipenessModel
from ml.ripeness.mock import MockRipenessModel

__all__ = [
    "ColourTextureRipenessModel",
    "MockRipenessModel",
    "RipenessModel",
    "RipenessResult",
]
