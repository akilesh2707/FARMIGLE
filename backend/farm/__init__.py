"""Farm and zone CRUD plus deterministic zone-grid generation."""

from backend.farm.service import (
    DEFAULT_ZONE_COLS,
    DEFAULT_ZONE_ROWS,
    FarmService,
    zone_summary,
)

__all__ = [
    "DEFAULT_ZONE_COLS",
    "DEFAULT_ZONE_ROWS",
    "FarmService",
    "zone_summary",
]
