"""GeoJSON feature construction (RFC 7946).

Thin, explicit builders. The backend emits GeoJSON and nothing else - it has no
opinion about how the frontend renders it (Section 7 M10, Section 12.6).
"""

from __future__ import annotations

from typing import Any, Sequence


def make_feature(
    geometry: dict[str, Any],
    properties: dict[str, Any],
    *,
    feature_id: str | None = None,
) -> dict[str, Any]:
    """A single GeoJSON Feature."""
    feature: dict[str, Any] = {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }
    if feature_id is not None:
        feature["id"] = feature_id
    return feature


def make_feature_collection(
    features: Sequence[dict[str, Any]], **collection_properties: Any
) -> dict[str, Any]:
    """A FeatureCollection. Non-``features`` kwargs become top-level members."""
    collection: dict[str, Any] = {
        "type": "FeatureCollection",
        "features": list(features),
    }
    collection.update(collection_properties)
    return collection


def bbox_of_features(features: Sequence[dict[str, Any]]) -> list[float] | None:
    """``[west, south, east, north]`` over every feature geometry."""
    coordinates: list[Sequence[float]] = []

    def _walk(node: Any) -> None:
        if isinstance(node, (list, tuple)):
            if node and all(isinstance(item, (int, float)) for item in node[:2]):
                coordinates.append(node)
            else:
                for child in node:
                    _walk(child)

    for feature in features:
        geometry = feature.get("geometry") or {}
        _walk(geometry.get("coordinates", []))

    if not coordinates:
        return None
    lngs = [position[0] for position in coordinates]
    lats = [position[1] for position in coordinates]
    return [round(min(lngs), 7), round(min(lats), 7), round(max(lngs), 7), round(max(lats), 7)]


def is_valid_feature_collection(value: Any) -> bool:
    """Structural check used by tests and by the harvest-map builder."""
    if not isinstance(value, dict):
        return False
    if value.get("type") != "FeatureCollection":
        return False
    features = value.get("features")
    if not isinstance(features, list):
        return False
    return all(
        isinstance(feature, dict)
        and feature.get("type") == "Feature"
        and isinstance(feature.get("geometry"), dict)
        and "coordinates" in (feature.get("geometry") or {})
        for feature in features
    )


__all__ = [
    "bbox_of_features",
    "is_valid_feature_collection",
    "make_feature",
    "make_feature_collection",
]
