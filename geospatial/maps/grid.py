"""Zone grid generation (Section 7 M1, Section 5.2 step 1).

The farm's boundary bounding box is divided into ``rows x cols`` cells; each
cell is clipped against the boundary polygon so a non-rectangular farm still
produces zones that tile it exactly. Zones are numbered row-major from the
north-west corner: ``zone_01`` is (row 0, col 0).

The generator is pure and deterministic: the same boundary and the same config
always produce byte-identical geometry (coordinates are rounded to
``configs/thresholds/<crop>.yaml -> zones.coordinate_precision``).
"""

from __future__ import annotations

import string
from typing import Any

from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from geospatial.geojson.geometry import area_hectares_of, bbox_of, centroid_of, round_ring

NORTH, SOUTH, EAST, WEST = "north", "south", "east", "west"


def zone_label(index: int) -> str:
    """0 -> A, 1 -> B, ... 25 -> Z, 26 -> AA.

    The demo script (Section 16) refers to "Zone A/B/C"; ``label`` preserves
    that vocabulary while ``zone_id`` stays the documented ``zone_NN`` form.
    """
    letters = ""
    value = index
    while True:
        letters = string.ascii_uppercase[value % 26] + letters
        value = value // 26 - 1
        if value < 0:
            break
    return letters


def zone_id_for(index: int, prefix: str = "zone_", width: int = 2) -> str:
    return f"{prefix}{index + 1:0{width}d}"


def _cell_polygon(
    min_lng: float, min_lat: float, max_lng: float, max_lat: float
) -> Polygon:
    return Polygon(
        [
            (min_lng, min_lat),
            (max_lng, min_lat),
            (max_lng, max_lat),
            (min_lng, max_lat),
        ]
    )


def _polygon_coordinates(geometry: BaseGeometry, precision: int) -> list[list[list[float]]]:
    if geometry.geom_type == "Polygon":
        return [round_ring(list(geometry.exterior.coords), precision)]
    if geometry.geom_type == "MultiPolygon":
        return [
            round_ring(list(part.exterior.coords), precision) for part in geometry.geoms
        ]
    return []


def generate_zone_grid(
    boundary: dict[str, Any],
    *,
    rows: int = 4,
    cols: int = 5,
    id_prefix: str = "zone_",
    coordinate_precision: int = 7,
    min_coverage_ratio: float = 0.02,
) -> list[dict[str, Any]]:
    """Split a farm boundary into a deterministic ``rows x cols`` grid.

    Returns a list of zone documents::

        {
          "zone_id": "zone_01", "label": "A", "index": 1,
          "row": 0, "col": 0,
          "area_hectares": 0.31, "centroid": {"lat": .., "lng": ..},
          "geometry": {"type": "Polygon", "coordinates": [[[lng, lat], ...]]},
          "edges": {"north": .., "south": .., "east": .., "west": ..}
        }
    """
    if rows < 1 or cols < 1:
        raise ValueError("Zone grid must have at least one row and one column.")

    farm_polygon = shape(boundary)
    bounds = bbox_of(farm_polygon)
    cell_width = (bounds["max_lng"] - bounds["min_lng"]) / cols
    cell_height = (bounds["max_lat"] - bounds["min_lat"]) / rows
    cell_area = abs(cell_width * cell_height)
    if cell_area == 0:
        raise ValueError("Farm boundary has zero extent; cannot build a zone grid.")

    zones: list[dict[str, Any]] = []
    for row in range(rows):
        # Row 0 is the northernmost strip so that zone_01 is the NW cell.
        south = bounds["max_lat"] - (row + 1) * cell_height
        north = south + cell_height
        for col in range(cols):
            west = bounds["min_lng"] + col * cell_width
            east = west + cell_width
            cell = _cell_polygon(west, south, east, north)
            clipped = farm_polygon.intersection(cell)

            if clipped.is_empty:
                continue
            if clipped.area < cell_area * min_coverage_ratio:
                # Drop slivers that would produce unusable one-pixel zones.
                continue

            index = len(zones)
            geometry_dict = {
                "type": "Polygon" if clipped.geom_type == "Polygon" else "MultiPolygon",
                "coordinates": _polygon_coordinates(clipped, coordinate_precision),
            }
            zones.append(
                {
                    "zone_id": zone_id_for(index, prefix=id_prefix),
                    "label": zone_label(index),
                    "index": index + 1,
                    "row": row,
                    "col": col,
                    "area_hectares": round(area_hectares_of(clipped), 4),
                    "centroid": centroid_of(clipped),
                    "geometry": geometry_dict,
                    "edges": {
                        NORTH: round(north, coordinate_precision),
                        SOUTH: round(south, coordinate_precision),
                        EAST: round(east, coordinate_precision),
                        WEST: round(west, coordinate_precision),
                    },
                }
            )
    return zones


def zone_lookup(zones: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {zone["zone_id"]: zone for zone in zones}


def find_zone_for_point(
    zones: list[dict[str, Any]], lat: float, lng: float
) -> dict[str, Any] | None:
    """Locate the zone containing a coordinate (used when EXIF GPS is present).

    Section 9.1 reality 6: phone photos have no reliable geo-footprint, so this
    is a best-effort convenience and the farmer can still tag the zone manually.
    """
    point = Point(float(lng), float(lat))
    for zone in zones:
        if shape(zone["geometry"]).covers(point):
            return zone
    return None


def zones_geometry_collection(zones: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "GeometryCollection",
        "geometries": [zone["geometry"] for zone in zones],
    }


__all__ = [
    "EAST",
    "NORTH",
    "SOUTH",
    "WEST",
    "find_zone_for_point",
    "generate_zone_grid",
    "mapping",
    "zone_id_for",
    "zone_label",
    "zone_lookup",
    "zones_geometry_collection",
]
