"""M4 - Satellite context (anomaly layer only).

Critical framing from the documentation (D1, Section 9.1 reality 1):

    Satellite is an anomaly detector only. At roughly 10 m per pixel it cannot
    see fruit. It answers "where should we look?", never "is this ripe?".

The output type therefore has no ripeness field at all. Anomalies are worded as
``canopy_condition_anomaly``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

ANOMALY_REASON = "canopy condition anomaly"
NOT_RIPENESS = "Satellite indicators describe canopy condition only and must never be read as fruit ripeness."


@dataclass(frozen=True)
class ZoneSatelliteObservation:
    """Per-zone satellite indicators."""

    zone_id: str
    vegetation_index: float  # e.g. NDVI-like, roughly -1..1
    vegetation_index_previous: float | None
    change_from_previous_period: float | None
    anomaly_flag: bool
    moisture_index: float | None = None
    anomaly_reason: str | None = None
    capture_date: str | None = None
    confidence: float = 0.5
    cloud_cover: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "vegetation_index": round(float(self.vegetation_index), 4),
            "vegetation_index_previous": None
            if self.vegetation_index_previous is None
            else round(float(self.vegetation_index_previous), 4),
            "change_from_previous_period": None
            if self.change_from_previous_period is None
            else round(float(self.change_from_previous_period), 4),
            "anomaly_flag": bool(self.anomaly_flag),
            "moisture_index": None if self.moisture_index is None else round(float(self.moisture_index), 4),
            "anomaly_reason": self.anomaly_reason,
            "capture_date": self.capture_date,
            "confidence": round(float(self.confidence), 4),
            "cloud_cover": None if self.cloud_cover is None else round(float(self.cloud_cover), 4),
        }


@dataclass(frozen=True)
class SatelliteContext:
    """Satellite evidence for a whole farm."""

    provider: str
    is_mock: bool
    is_simulated: bool
    zones: dict[str, ZoneSatelliteObservation] = field(default_factory=dict)
    indices_used: list[str] = field(default_factory=list)
    capture_date: str | None = None
    cached: bool = False
    notes: list[str] = field(default_factory=list)
    disclaimer: str = NOT_RIPENESS

    def for_zone(self, zone_id: str) -> ZoneSatelliteObservation | None:
        return self.zones.get(zone_id)

    @property
    def anomalous_zone_ids(self) -> list[str]:
        return [zone_id for zone_id, item in self.zones.items() if item.anomaly_flag]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "is_mock": self.is_mock,
            "is_simulated": self.is_simulated,
            "capture_date": self.capture_date,
            "cached": self.cached,
            "indices_used": list(self.indices_used),
            "anomalous_zone_ids": self.anomalous_zone_ids,
            "zones": {zone_id: item.to_dict() for zone_id, item in self.zones.items()},
            "notes": list(self.notes),
            "disclaimer": self.disclaimer,
        }


@runtime_checkable
class SatelliteProvider(Protocol):
    name: str
    is_mock: bool

    def fetch(self, farm: dict[str, Any], *, thresholds: Any | None = None) -> SatelliteContext: ...


__all__ = [
    "ANOMALY_REASON",
    "NOT_RIPENESS",
    "SatelliteContext",
    "SatelliteProvider",
    "ZoneSatelliteObservation",
]
