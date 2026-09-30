"""M7 - Multi-source fusion.

Configurable weights, missing-source-safe. Weights come from
``configs/thresholds/<crop>.yaml`` (heuristic v0, not agricultural truth).
"""

from backend.fusion.engine import DEFAULT_FUSION_CONFIG, FusionEngine, resolve_fusion_config
from backend.fusion.models import (
    CONTEXT_ROLES,
    ROLE_DRONE,
    ROLE_GROUND,
    SourceEvidence,
    ZoneFusionInput,
    ZoneFusionResult,
)

__all__ = [
    "CONTEXT_ROLES",
    "DEFAULT_FUSION_CONFIG",
    "FusionEngine",
    "ROLE_DRONE",
    "ROLE_GROUND",
    "SourceEvidence",
    "ZoneFusionInput",
    "ZoneFusionResult",
    "resolve_fusion_config",
]
