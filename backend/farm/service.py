"""Farm and zone management.

The zone grid is generated server-side and deterministically, so the same
boundary always produces the same zones (Section 5.3). Clients may also send
their own zone polygons, which are validated the same way as a boundary.
"""

from __future__ import annotations

from typing import Any

from geospatial.geojson.geometry import (
    area_hectares_of,
    centroid_of,
    normalize_boundary,
    to_shapely,
    validate_boundary,
)
from geospatial.maps.grid import generate_zone_grid, zone_lookup
from backend.core.errors import FarmNotFoundError, ZoneNotFoundError
from backend.core.firestore import Repository
from backend.core.logging import get_logger
from backend.core.utils import new_id, utc_now_iso

logger = get_logger(__name__)

DEFAULT_ZONE_ROWS = 4
DEFAULT_ZONE_COLS = 5
MAX_FARMS_PER_OWNER = 200


class FarmService:
    """CRUD for farms plus zone-grid generation."""

    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    # -- create ------------------------------------------------------------
    def create_farm(
        self,
        payload: dict[str, Any],
        *,
        owner_uid: str | None = None,
        district_id: str | None = None,
        zone_rows: int = DEFAULT_ZONE_ROWS,
        zone_cols: int = DEFAULT_ZONE_COLS,
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("name is required")

        boundary = validate_boundary(payload.get("boundary"))
        geometry = to_shapely(boundary)

        farm_id = new_id("farm")
        zones = self._build_zones(
            payload, boundary=boundary, zone_rows=zone_rows, zone_cols=zone_cols
        )

        farm = {
            "farm_id": farm_id,
            "name": name,
            "crop": str(payload.get("crop") or "mango").lower(),
            "crop_stage": str(payload.get("crop_stage") or "fruit_development"),
            "language": str(payload.get("language") or "en"),
            "boundary": boundary,
            "centroid": centroid_of(geometry),
            "center": payload.get("center") or centroid_of(geometry),
            "area_hectares": round(area_hectares_of(geometry), 4),
            "zones": zones,
            "zone_grid": {"rows": zone_rows, "cols": zone_cols, "generated": True},
            "owner_uid": owner_uid,
            "district_id": district_id,
            "metadata": payload.get("metadata") or {},
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
            "latest_analysis": None,
        }
        created = self.repository.create_farm(farm)
        logger.info(
            "farm_created",
            extra={"farm_id": created.get("farm_id"), "zone_count": len(created.get("zones", []))},
        )
        return created

    # -- read --------------------------------------------------------------
    def get_farm(self, farm_id: str) -> dict[str, Any]:
        farm = self.repository.get_farm(farm_id)
        if farm is None:
            raise FarmNotFoundError(farm_id)
        return farm

    def list_farms(
        self,
        *,
        owner_uid: str | None = None,
        district_id: str | None = None,
        limit: int = MAX_FARMS_PER_OWNER,
    ) -> list[dict[str, Any]]:
        return self.repository.list_farms(
            owner_uid=owner_uid, district_id=district_id, limit=limit
        )

    # -- update ------------------------------------------------------------
    def update_farm(self, farm_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_farm(farm_id)
        payload: dict[str, Any] = {}

        for field in ("name", "crop", "crop_stage", "language", "center", "metadata"):
            if updates.get(field) is not None:
                payload[field] = updates[field]

        if updates.get("boundary") is not None:
            boundary = validate_boundary(updates["boundary"])
            geometry = to_shapely(boundary)
            payload["boundary"] = boundary
            payload["centroid"] = centroid_of(geometry)
            payload["area_hectares"] = round(area_hectares_of(geometry), 4)
            # A new boundary invalidates the old zones; regenerate them.
            payload["zones"] = self._build_zones(
                {"boundary": boundary},
                boundary=boundary,
                zone_rows=int((existing.get("zone_grid") or {}).get("rows", DEFAULT_ZONE_ROWS)),
                zone_cols=int((existing.get("zone_grid") or {}).get("cols", DEFAULT_ZONE_COLS)),
            )
            payload["zone_grid"] = {**(existing.get("zone_grid") or {}), "generated": True}

        if updates.get("zones") is not None:
            payload["zones"] = self._validate_client_zones(updates["zones"])

        payload["updated_at"] = utc_now_iso()
        updated = self.repository.update_farm(farm_id, payload)
        if updated is None:
            raise FarmNotFoundError(farm_id)
        return updated

    def delete_farm(self, farm_id: str) -> bool:
        self.get_farm(farm_id)
        return self.repository.delete_farm(farm_id)

    # -- zones -------------------------------------------------------------
    def get_zone(self, farm_id: str, zone_id: str) -> dict[str, Any]:
        farm = self.get_farm(farm_id)
        zone = zone_lookup(farm.get("zones") or []).get(zone_id)
        if zone is None:
            raise ZoneNotFoundError(f"{farm_id}/{zone_id}")
        return zone

    def list_zones(self, farm_id: str) -> list[dict[str, Any]]:
        return list(self.get_farm(farm_id).get("zones") or [])

    def resolve_zone(
        self, farm_id: str, *, zone_id: str | None = None, zone_label: str | None = None
    ) -> dict[str, Any]:
        """Resolve a zone by id or by human label (A..T)."""
        farm = self.get_farm(farm_id)
        zones = farm.get("zones") or []
        if zone_id:
            zone = zone_lookup(zones).get(zone_id)
            if zone is None:
                raise ZoneNotFoundError(f"{farm_id}/{zone_id}")
            return zone
        if zone_label:
            wanted = str(zone_label).strip().upper()
            for zone in zones:
                if str(zone.get("label", "")).upper() == wanted:
                    return zone
            raise ZoneNotFoundError(f"{farm_id}/label:{zone_label}")
        raise ZoneNotFoundError(f"{farm_id}/<unspecified>")

    # -- internals ---------------------------------------------------------
    def _build_zones(
        self,
        payload: dict[str, Any],
        *,
        boundary: dict[str, Any],
        zone_rows: int,
        zone_cols: int,
    ) -> list[dict[str, Any]]:
        client_zones = payload.get("zones")
        if client_zones:
            return self._validate_client_zones(client_zones)
        return generate_zone_grid(boundary, rows=zone_rows, cols=zone_cols)

    @staticmethod
    def _validate_client_zones(zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
        validated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for zone in zones:
            zone_id = str(zone.get("zone_id", "")).strip()
            if not zone_id or zone_id in seen:
                continue
            geometry = normalize_boundary(zone.get("geometry")) if zone.get("geometry") else None
            if geometry is not None:
                validate_boundary(geometry)
            seen.add(zone_id)
            validated.append(
                {
                    "zone_id": zone_id,
                    "label": zone.get("label"),
                    "row": int(zone.get("row", 0)),
                    "col": int(zone.get("col", 0)),
                    "geometry": geometry,
                    "centroid": zone.get("centroid"),
                    "area_hectares": zone.get("area_hectares"),
                    "source": "client",
                }
            )
        return validated


def zone_summary(farm: dict[str, Any]) -> list[dict[str, Any]]:
    """Lightweight zone list for map bootstrapping."""
    return [
        {
            "zone_id": zone.get("zone_id"),
            "label": zone.get("label"),
            "row": zone.get("row"),
            "col": zone.get("col"),
            "centroid": zone.get("centroid"),
            "area_hectares": zone.get("area_hectares"),
        }
        for zone in farm.get("zones", [])
    ]


__all__ = [
    "DEFAULT_ZONE_COLS",
    "DEFAULT_ZONE_ROWS",
    "FarmService",
    "MAX_FARMS_PER_OWNER",
    "zone_summary",
]
