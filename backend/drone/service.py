"""M5 - Drone / aerial analysis.

MVP scope (Section 4.1): "Accept pre-captured drone images for a flagged zone".
No physical drone control, no automated survey flights - those are explicitly
out of scope (Section 4.2).

A drone tile is analysed through exactly the same perception pipeline as a
phone photo; the only additions here are (a) mapping a tile to a zone by
coordinate, and (b) labelling the evidence source as ``drone``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.core.config import Settings
from backend.core.logging import get_logger
from backend.ground.service import GroundAnalysisService, VisualEvidence
from geospatial.maps.grid import find_zone_for_point

logger = get_logger(__name__)


@dataclass(frozen=True)
class DroneTileAssignment:
    zone_id: str
    matched_by: str  # "explicit" | "geotag" | "unmatched"
    distance_m: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "matched_by": self.matched_by,
            "distance_m": self.distance_m,
        }


class DroneAnalysisService:
    """Analyse a supplied drone tile and attribute it to a zone."""

    def __init__(self, ground_service: GroundAnalysisService) -> None:
        self.ground = ground_service

    @classmethod
    def from_config(cls, **kwargs: Any) -> "DroneAnalysisService":
        return cls(GroundAnalysisService.from_config(**kwargs))

    def assign_tile(
        self,
        farm: dict[str, Any],
        *,
        zone_id: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
    ) -> DroneTileAssignment:
        """Resolve which zone a tile belongs to.

        An explicit zone id (how the frontend tags a flagged zone) wins. A
        coordinate is used when present. Otherwise the tile is left unmatched
        rather than being silently attributed to an arbitrary zone.
        """
        zones = farm.get("zones") or []
        if zone_id:
            if any(str(zone.get("zone_id")) == zone_id for zone in zones):
                return DroneTileAssignment(zone_id=zone_id, matched_by="explicit")
            return DroneTileAssignment(zone_id=zone_id, matched_by="unmatched")

        if lat is not None and lng is not None:
            match = find_zone_for_point(zones, float(lat), float(lng))
            if match is not None:
                return DroneTileAssignment(
                    zone_id=str(match["zone_id"]), matched_by="geotag"
                )

        return DroneTileAssignment(zone_id="", matched_by="unmatched")

    def analyze(
        self,
        farm: dict[str, Any],
        image_bytes: bytes,
        *,
        zone_id: str | None = None,
        lat: float | None = None,
        lng: float | None = None,
    ) -> tuple[DroneTileAssignment, VisualEvidence]:
        assignment = self.assign_tile(farm, zone_id=zone_id, lat=lat, lng=lng)
        evidence = self.ground.analyze(image_bytes, source="drone")
        return assignment, evidence


__all__ = ["DroneAnalysisService", "DroneTileAssignment"]
