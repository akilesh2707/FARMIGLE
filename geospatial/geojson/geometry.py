"""Boundary validation and measurement (GeoJSON in, WGS84 metrics out).

A farm boundary is stored exactly as the client sent it (normalised to a
GeoJSON ``Polygon`` or ``MultiPolygon``) so the frontend can round-trip it
without re-projection surprises. Shapely is used for the geometric checks
(self-intersection, area, centroid) and the computed values are stored
alongside the boundary.
"""

from __future__ import annotations

from math import cos, radians
from typing import Any, Iterable, Sequence

from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import explain_validity

from backend.core.errors import InvalidBoundaryError

EARTH_RADIUS_M = 6_371_008.8
M2_PER_HECTARE = 10_000.0
KM_PER_DEGREE = 111.32


def normalize_boundary(boundary: Any) -> dict[str, Any]:
    """Coerce the accepted client shapes into a GeoJSON geometry dict.

    Accepted
    --------
    * ``{"type": "Polygon", "coordinates": [[[lng, lat], ...]]}``
    * ``{"type": "MultiPolygon", "coordinates": [[[[lng, lat], ...]], ...]}``
    * ``{"type": "Feature", "geometry": {...}}``  (unwrapped)
    * ``[{"lat": .., "lng": ..}, ...]``  (convenience ring)

    Raises :class:`InvalidBoundaryError` for anything else.
    """
    if boundary is None:
        raise InvalidBoundaryError("Boundary is required.", reason="missing")

    if isinstance(boundary, (list, tuple)):
        if not boundary:
            raise InvalidBoundaryError("Boundary ring is empty.", reason="empty")
        if all(isinstance(item, dict) and {"lat", "lng"} <= set(item) for item in boundary):
            ring = [[float(item["lng"]), float(item["lat"])] for item in boundary]
            return {"type": "Polygon", "coordinates": [ring]}
        raise InvalidBoundaryError(
            "Boundary given as a list must be a ring of {'lat', 'lng'} objects.",
            reason="unrecognized_shape",
        )

    if not isinstance(boundary, dict):
        raise InvalidBoundaryError(
            "Boundary must be a GeoJSON geometry object.", reason="unrecognized_shape"
        )

    geometry = boundary
    geometry_type = str(boundary.get("type", "")).lower()
    if geometry_type == "feature":
        geometry = boundary.get("geometry") or {}
        geometry_type = str(geometry.get("type", "")).lower() if isinstance(geometry, dict) else ""
    elif geometry_type in ("featurecollection",):
        raise InvalidBoundaryError(
            "Send a single Polygon or MultiPolygon, not a FeatureCollection.",
            reason="unsupported_type",
        )

    if geometry_type not in ("polygon", "multipolygon"):
        raise InvalidBoundaryError(
            f"Boundary geometry type '{geometry_type or 'missing'}' is not supported. "
            "Use GeoJSON Polygon or MultiPolygon.",
            reason="unsupported_type",
        )
    if not isinstance(geometry.get("coordinates"), list) or not geometry["coordinates"]:
        raise InvalidBoundaryError("Boundary coordinates are missing or empty.", reason="empty")
    return {"type": "Polygon" if geometry_type == "polygon" else "MultiPolygon",
            "coordinates": geometry["coordinates"]}


def to_shapely(boundary: Any) -> BaseGeometry:
    """Build a Shapely geometry from an already-normalized boundary."""
    try:
        return shape(normalize_boundary(boundary))
    except InvalidBoundaryError:
        raise
    except Exception as exc:
        raise InvalidBoundaryError(
            "Boundary geometry could not be parsed.", reason="unparseable"
        ) from exc


def _iter_rings(geometry: BaseGeometry) -> Iterable[list[Sequence[float]]]:
    """Yield every ring (exterior and interior) of a Polygon / MultiPolygon."""
    polygons: list[Polygon] = []
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    for polygon in polygons:
        yield list(polygon.exterior.coords)
        for interior in polygon.interiors:
            yield list(interior.coords)


def validate_boundary(
    boundary: Any,
    *,
    min_vertices: int = 4,
    require_closed_ring: bool = True,
    allow_multipolygon: bool = True,
    lon_range: tuple[float, float] = (-180.0, 180.0),
    lat_range: tuple[float, float] = (-90.0, 90.0),
    min_area_hectares: float = 0.0,
    max_area_hectares: float = float("inf"),
) -> dict[str, Any]:
    """Validate a farm boundary and return the normalized geometry.

    Checks, in order: geometry type, ring closure, coordinate count, coordinate
    ranges, self-intersection, and area bounds. The error ``reason`` field is a
    stable code the client can branch on.
    """
    normalized = normalize_boundary(boundary)
    geometry = to_shapely(normalized)

    if normalized["type"] == "MultiPolygon" and not allow_multipolygon:
        raise InvalidBoundaryError("MultiPolygon boundaries are not supported.", reason="unsupported_type")

    for ring in _iter_rings(geometry):
        if len(ring) < min_vertices:
            raise InvalidBoundaryError(
                f"A boundary ring needs at least {min_vertices} positions, got {len(ring)}.",
                reason="too_few_vertices",
            )
        if require_closed_ring and ring[0] != ring[-1]:
            raise InvalidBoundaryError(
                "Boundary ring must be closed (first position must repeat the last).",
                reason="unclosed_ring",
            )
        for position in ring:
            if len(position) < 2:
                raise InvalidBoundaryError(
                    "Each position needs at least [longitude, latitude].", reason="bad_position"
                )
            lng, lat = float(position[0]), float(position[1])
            if not (lon_range[0] <= lng <= lon_range[1]):
                raise InvalidBoundaryError(
                    f"Longitude {lng} is outside [{lon_range[0]}, {lon_range[1]}].",
                    reason="longitude_out_of_range",
                )
            if not (lat_range[0] <= lat <= lat_range[1]):
                raise InvalidBoundaryError(
                    f"Latitude {lat} is outside [{lat_range[0]}, {lat_range[1]}].",
                    reason="latitude_out_of_range",
                )

    if not geometry.is_valid:
        raise InvalidBoundaryError(
            f"Boundary is not a valid polygon: {explain_validity(geometry)}.",
            reason="self_intersection",
        )
    if geometry.is_empty:
        raise InvalidBoundaryError("Boundary encloses no area.", reason="empty")
    if geometry.geom_type not in ("Polygon", "MultiPolygon"):
        raise InvalidBoundaryError(
            f"Boundary resolved to a {geometry.geom_type}, which is not supported.",
            reason="unsupported_type",
        )

    area = area_hectares_of(geometry)
    if area < min_area_hectares:
        raise InvalidBoundaryError(
            f"Boundary area {area:.4f} ha is below the minimum of {min_area_hectares} ha.",
            reason="area_too_small",
            details={"area_hectares": round(area, 6), "min_area_hectares": min_area_hectares},
        )
    if area > max_area_hectares:
        raise InvalidBoundaryError(
            f"Boundary area {area:.4f} ha exceeds the maximum of {max_area_hectares} ha.",
            reason="area_too_large",
            details={"area_hectares": round(area, 6), "max_area_heptares": max_area_hectares},
        )

    normalized["centroid"] = centroid_of(normalized)
    normalized["area_hectares"] = round(area, 4)
    return normalized


# ---------------------------------------------------------------------------
# Measurement
# ---------------------------------------------------------------------------


def area_hectares_of(geometry: BaseGeometry) -> float:
    """Geodesic-ish area in hectares.

    Uses an equirectangular scaling of the degree-space area: 1 degree of
    latitude is ~111.32 km, and 1 degree of longitude is that value scaled by
    cos(latitude). For orchard plots - well under a degree across - this is
    accurate to far better than the precision these heuristic scores need, and
    it is deterministic and dependency-free.
    """
    if geometry.is_empty:
        return 0.0
    min_lng, min_lat, max_lng, max_lat = geometry.bounds
    if (max_lng - min_lng) > 1.0 or (max_lat - min_lat) > 1.0:
        # Too large for a local projection to be meaningful; report the raw
        # degree-space area so the caller can decide (a farm this size is
        # rejected by the area bounds in `validate_boundary` anyway).
        return geometry.area * (KM_PER_DEGREE ** 2) / 10_000.0

    mean_lat_deg = 0.5 * (min_lat + max_lat)
    km_per_deg_lng = KM_PER_DEGREE * abs(cos(radians(mean_lat_deg)))
    km2 = geometry.area * km_per_deg_lng * KM_PER_DEGREE
    return km2 * 100.0


def centroid_of(boundary: Any) -> dict[str, float]:
    """Area-weighted centroid as ``{"lat": .., "lng": ..}``."""
    geometry = to_shapely(boundary) if not isinstance(boundary, BaseGeometry) else boundary
    centroid = geometry.centroid
    return {"lat": round(float(centroid.y), 7), "lng": round(float(centroid.x), 7)}


def bbox_of(boundary: Any) -> dict[str, float]:
    geometry = to_shapely(boundary) if not isinstance(boundary, BaseGeometry) else boundary
    min_lng, min_lat, max_lng, max_lat = geometry.bounds
    return {
        "min_lng": min_lng,
        "min_lat": min_lat,
        "max_lng": max_lng,
        "max_lat": max_lat,
    }


def round_ring(ring: Sequence[Sequence[float]], precision: int) -> list[list[float]]:
    """Round a ring and force closure - keeps emitted GeoJSON deterministic."""
    rounded = [[round(float(x), precision), round(float(y), precision)] for x, y in ring]
    if rounded[0] != rounded[-1]:
        rounded.append(list(rounded[0]))
    return rounded


def ring_area_deg2(ring: Sequence[Sequence[float]]) -> float:
    """Absolute shoelace area of a ring in square degrees."""
    total = 0.0
    for index in range(len(ring) - 1):
        x1, y1 = ring[index][0], ring[index][1]
        x2, y2 = ring[index + 1][0], ring[index + 1][1]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0
