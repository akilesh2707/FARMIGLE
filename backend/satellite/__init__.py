"""M4 - Satellite context.

Anomaly layer only: "where should we look?", never "is it ripe?".
"""

from backend.satellite.base import (
    ANOMALY_REASON,
    NOT_RIPENESS,
    SatelliteContext,
    SatelliteProvider,
    ZoneSatelliteObservation,
)
from backend.satellite.earth_engine import EarthEngineSatelliteProvider
from backend.satellite.providers import SeededSatelliteProvider, build_satellite_provider

__all__ = [
    "ANOMALY_REASON",
    "NOT_RIPENESS",
    "EarthEngineSatelliteProvider",
    "SatelliteContext",
    "SatelliteProvider",
    "SeededSatelliteProvider",
    "ZoneSatelliteObservation",
    "build_satellite_provider",
]
