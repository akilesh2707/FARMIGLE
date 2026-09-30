"""Seeded / cached satellite provider.

Implements the MVP requirement (Section 4.1, D6): "Satellite: Precomputed
anomaly layer for the demo orchard", "Precompute heavy geospatial; demo on
curated data".

Two sources of truth, in order:

1. A per-farm JSON file under ``data/satellite/`` (keyed by farm id, then zone
   id). This is where real precomputed Earth Engine output is dropped in; each
   file declares its own ``provenance`` so simulated and real data are never
   confused.
2. A deterministic spatial gradient derived from the zone's grid position and a
   hash of (farm_id, zone_id). This is always labelled ``is_simulated=True``.

Nothing here claims to be live satellite data.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.logging import get_logger
from backend.satellite.base import (
    ANOMALY_REASON,
    SatelliteContext,
    ZoneSatelliteObservation,
)

logger = get_logger(__name__)

NOTE = (
    "Seeded/cached satellite layer. This is contextual anomaly evidence, not a "
    "live Earth Engine call and not a measurement of fruit ripeness."
)


def _stable_unit(*parts: str) -> float:
    """Deterministic float in [0, 1) from stable string inputs."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16 ** 12)


class SeededSatelliteProvider:
    """Reads precomputed per-farm satellite results, or simulates them."""

    name = "seeded_satellite"
    is_mock = True

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir or get_settings().satellite_data_dir)

    # -- public API --------------------------------------------------------
    def fetch(self, farm: dict[str, Any], *, thresholds: Any | None = None) -> SatelliteContext:
        farm_id = str(farm.get("farm_id", "unknown"))
        thresholds = _satellite_config(thresholds)
        payload = self._load_precomputed(farm_id)

        zones_config = farm.get("zones") or []
        if not zones_config:
            return SatelliteContext(
                provider=self.name,
                is_mock=True,
                is_simulated=True,
                notes=[NOTE, "Farm has no zones; nothing to fetch."],
            )

        if payload is not None:
            return self._from_precomputed(farm_id, payload, zones_config, thresholds)

        return self._simulate(farm_id, zones_config, thresholds)

    # -- precomputed files -------------------------------------------------
    def _precomputed_paths(self, farm_id: str) -> list[Path]:
        candidates = [
            self.data_dir / f"{farm_id}.json",
            self.data_dir / f"{farm_id}.geojson",
            self.data_dir / "demo_orchard.json",
        ]
        return [path for path in candidates if path.exists()]

    def _load_precomputed(self, farm_id: str) -> dict[str, Any] | None:
        for path in self._precomputed_paths(farm_id):
            try:
                with path.open("r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "satellite_seed_unreadable",
                    extra={"path": path.name, "error_type": type(exc).__name__},
                )
                continue
            if isinstance(payload, dict):
                payload.setdefault("provenance", "unknown")
                return payload
        return None

    def _from_precomputed(
        self,
        farm_id: str,
        payload: dict[str, Any],
        zones_config: list[dict[str, Any]],
        thresholds: Any,
    ) -> SatelliteContext:
        provenance = str(payload.get("provenance", "unknown")).lower()
        is_simulated = provenance != "earth_engine_cached"
        drop_threshold = float(thresholds["anomaly_drop_threshold"])
        healthy_floor = float(thresholds["healthy_index_floor"])

        raw_zones = payload.get("zones") or {}
        observations: dict[str, ZoneSatelliteObservation] = {}
        for zone in zones_config:
            zone_id = str(zone.get("zone_id", ""))
            entry = raw_zones.get(zone_id)
            if entry is None:
                # A precomputed file may cover only flagged zones; fall back to
                # the deterministic simulation for the rest.
                observations[zone_id] = self._simulate_zone(farm_id, zone, thresholds)
                continue
            current = float(entry.get("vegetation_index", entry.get("ndvi", 0.5)))
            previous = entry.get("vegetation_index_previous", entry.get("ndvi_previous"))
            previous_value = None if previous is None else float(previous)
            change = None if previous_value is None else current - previous_value
            anomaly = bool(entry.get("anomaly_flag", False)) or (
                change is not None and change <= -drop_threshold
            ) or current < healthy_floor
            observations[zone_id] = ZoneSatelliteObservation(
                zone_id=zone_id,
                vegetation_index=current,
                vegetation_index_previous=previous_value,
                change_from_previous_period=change,
                anomaly_flag=anomaly,
                moisture_index=entry.get("moisture_index"),
                anomaly_reason=ANOMALY_REASON if anomaly else None,
                capture_date=entry.get("capture_date") or payload.get("capture_date"),
                confidence=float(entry.get("confidence", 0.7 if not is_simulated else 0.5)),
                cloud_cover=entry.get("cloud_cover"),
            )

        return SatelliteContext(
            provider=f"{self.name}:precomputed",
            is_mock=is_simulated,
            is_simulated=is_simulated,
            zones=observations,
            indices_used=list(payload.get("indices_used", ["ndvi"])),
            capture_date=payload.get("capture_date"),
            cached=True,
            notes=[
                f"Loaded precomputed satellite result '{payload.get('source_file', farm_id)}' "
                f"(provenance={provenance}).",
                NOTE,
            ],
        )

    # -- deterministic simulation -----------------------------------------
    def _simulate(
        self, farm_id: str, zones_config: list[dict[str, Any]], thresholds: Any
    ) -> SatelliteContext:
        observations = {
            str(zone.get("zone_id", "")): self._simulate_zone(farm_id, zone, thresholds)
            for zone in zones_config
        }
        capture = (date.today() - timedelta(days=3)).isoformat()
        return SatelliteContext(
            provider=f"{self.name}:simulated",
            is_mock=True,
            is_simulated=True,
            zones=observations,
            indices_used=["ndvi_simulated", "moisture_simulated"],
            capture_date=capture,
            cached=False,
            notes=[
                "SIMULATED satellite context: no precomputed Earth Engine result exists "
                f"for farm '{farm_id}'. Values are a deterministic function of farm and "
                "zone identifiers, generated for demo and test purposes only.",
                NOTE,
            ],
        )

    def _simulate_zone(
        self, farm_id: str, zone: dict[str, Any], thresholds: Any
    ) -> ZoneSatelliteObservation:
        zone_id = str(zone.get("zone_id", ""))
        row = int(zone.get("row", 0))
        col = int(zone.get("col", 0))

        # Give the demo a visible spatial pattern: a mild north-west to
        # south-east gradient plus per-zone jitter, all deterministic.
        gradient = 0.10 * (0.35 * row - 0.30 * col)
        jitter = (_stable_unit(farm_id, zone_id) - 0.5) * 0.14
        current = _clamp(0.62 + gradient + jitter, 0.05, 0.95)
        previous_change = (_stable_unit(farm_id, zone_id, "prev") - 0.5) * 0.20
        previous = _clamp(current - previous_change, 0.05, 0.95)
        change = current - previous

        anomaly = (
            change <= -float(thresholds["anomaly_drop_threshold"])
            or current < float(thresholds["healthy_index_floor"])
        )
        moisture = _clamp(0.45 + jitter * 2.0, 0.05, 0.95)
        return ZoneSatelliteObservation(
            zone_id=zone_id,
            vegetation_index=current,
            vegetation_index_previous=previous,
            change_from_previous_period=change,
            anomaly_flag=anomaly,
            moisture_index=moisture,
            anomaly_reason=ANOMALY_REASON if anomaly else None,
            capture_date=(date.today() - timedelta(days=3)).isoformat(),
            confidence=0.45,
            cloud_cover=round(_stable_unit(farm_id, zone_id, "cloud") * 0.25, 3),
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _satellite_config(thresholds: Any | None) -> dict[str, float]:
    """Normalise the satellite section of a threshold config.

    Accepts a :class:`ThresholdConfig`, a plain mapping, or ``None`` so the
    providers stay usable from scripts and tests.
    """
    defaults = {"anomaly_drop_threshold": 0.08, "healthy_index_floor": 0.35}
    section: Any = thresholds
    if thresholds is None:
        section = None
    elif hasattr(thresholds, "risk"):
        section = dict(thresholds.risk).get("satellite") or {}
    elif isinstance(thresholds, dict):
        section = thresholds.get("satellite", thresholds)
    if not isinstance(section, dict):
        section = {}
    resolved = {**defaults}
    for key in defaults:
        if section.get(key) is not None:
            resolved[key] = float(section[key])
    return resolved


def build_satellite_provider(
    settings: Any | None = None, *, thresholds: Any | None = None
) -> Any:
    """Provider factory.

    ``MOCK_SERVICES=true`` always yields the seeded provider. In production the
    cached-first Earth Engine provider is used, and it is constructed with
    ``allow_live`` left off by default so a missing project id can never turn
    into a live Earth Engine call that silently fails.
    """
    from backend.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.mock_services:
        return SeededSatelliteProvider()
    from backend.satellite.earth_engine import EarthEngineSatelliteProvider

    return EarthEngineSatelliteProvider(
        cache_provider=SeededSatelliteProvider(),
        allow_live=bool(getattr(resolved, "earth_engine_allow_live", False)),
        project_id=resolved.google_project_id,
    )


__all__ = ["NOTE", "SeededSatelliteProvider", "build_satellite_provider"]
