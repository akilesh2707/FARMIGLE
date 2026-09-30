"""Harvest map: zone polygons + zone results as a GeoJSON FeatureCollection.

Serves ``GET /farms/{farm_id}/harvest-map``.

Status colours in the demo script (Section 16 scene 7) are a **frontend**
concern: this module only emits the status code plus the scores, and the
client decides how to draw it with the Maps JS Data layer.
"""

from __future__ import annotations

from typing import Any

from geospatial.geojson.feature import bbox_of_features, make_feature, make_feature_collection

# Section 16: A ready, B near-ready, C health concern. Emitted as a hint so the
# frontend does not have to hard-code the mapping, but the backend stays
# rendering-agnostic.
STATUS_COLORS = {
    "HARVEST_READY": "#22c55e",
    "NEAR_READY": "#eab308",
    "NOT_READY": "#ef4444",
    "HEALTH_CONCERN": "#a855f7",
}

STATUS_ORDER = ("HARVEST_READY", "HEALTH_CONCERN", "NEAR_READY", "NOT_READY", "NO_DATA")


def zone_feature(zone: dict[str, Any], zone_result: dict[str, Any] | None) -> dict[str, Any]:
    """One zone Feature. ``zone_result`` may be None for never-analysed zones."""
    result = zone_result or {}
    status = str(result.get("status", "NO_DATA"))
    properties: dict[str, Any] = {
        "zone_id": zone.get("zone_id"),
        "label": zone.get("label"),
        "row": zone.get("row"),
        "col": zone.get("col"),
        "area_hectares": zone.get("area_hectares"),
        "centroid": zone.get("centroid"),
        "status": status,
        "status_color_hint": STATUS_COLORS.get(status, "#94a3b8"),
        "ripeness_score": result.get("ripeness_score"),
        "health_score": result.get("health_score"),
        "risk_level": result.get("risk_level"),
        "confidence": result.get("confidence"),
        "estimated_harvest_window": result.get("estimated_harvest_window"),
        "days_to_harvest_min": result.get("days_to_harvest_min"),
        "days_to_harvest_max": result.get("days_to_harvest_max"),
        "sources_used": result.get("sources_used", []),
        "evidence_insufficient": result.get("evidence_insufficient", False),
        "analyzed_at": result.get("analyzed_at"),
        "has_result": zone_result is not None,
        "simulated": bool(result.get("simulated", False)),
        "disclaimer": (
            "Ripeness thresholds, fusion weights and days-to-harvest bands are "
            "configurable heuristic v0 values, not validated agronomy."
        ),
    }
    return make_feature(zone.get("geometry", {}), properties, feature_id=zone.get("zone_id"))


def build_harvest_map(
    farm: dict[str, Any],
    zone_results: dict[str, dict[str, Any]],
    *,
    boundary_feature: bool = True,
) -> dict[str, Any]:
    """Assemble the FeatureCollection for a farm.

    ``zone_results`` maps zone_id -> latest zone result document. Zones with no
    result are still emitted with ``status: "NO_DATA"`` so the map always shows
    the full grid.
    """
    features: list[dict[str, Any]] = []
    for zone in farm.get("zones", []):
        features.append(zone_feature(zone, zone_results.get(zone.get("zone_id", ""))))

    if boundary_feature and farm.get("boundary"):
        centroid = farm.get("centroid") or (farm.get("boundary") or {}).get("centroid")
        features.insert(
            0,
            make_feature(
                farm["boundary"],
                {
                    "zone_id": None,
                    "feature_type": "farm_boundary",
                    "farm_id": farm.get("farm_id"),
                    "farm_name": farm.get("name"),
                    "crop": farm.get("crop"),
                    "centroid": centroid,
                    "area_hectares": farm.get("area_hectares"),
                    "status": None,
                },
                feature_id=farm.get("farm_id"),
            ),
        )

    summary = _summarize(zone_results)
    generated_at = max(
        (str(result.get("analyzed_at", "")) for result in zone_results.values()),
        default="",
    ) or None
    collection = make_feature_collection(
        features,
        farm_id=farm.get("farm_id"),
        crop=farm.get("crop"),
        crop_stage=farm.get("crop_stage"),
        generated_at=generated_at,
        zone_count=len(farm.get("zones", [])),
        analysed_zone_count=summary["analysed_zone_count"],
        summary=summary,
        heuristic_version="heuristic-v0",
        simulated=any(bool(result.get("simulated")) for result in zone_results.values()),
        disclaimer=(
            "Zone statuses come from configurable heuristic v0 rules. They are a "
            "decision aid, not an agronomic guarantee. Disease-like signals are "
            "reported as possible indicators requiring local confirmation."
        ),
    )
    collection["bbox"] = bbox_of_features(features)
    return collection


def _summarize(zone_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in STATUS_ORDER}
    areas: dict[str, float] = {status: 0.0 for status in STATUS_ORDER}
    for result in zone_results.values():
        status = str(result.get("status", "NO_DATA"))
        counts[status] = counts.get(status, 0) + 1
        areas[status] = round(areas.get(status, 0.0) + float(result.get("area_hectares") or 0.0), 4)
    return {
        "status_counts": {key: value for key, value in counts.items() if value},
        "area_hectares_by_status": {key: value for key, value in areas.items() if value},
        "analysed_zone_count": len(zone_results),
        "priority_zone_ids": [
            result.get("zone_id")
            for result in sorted(
                zone_results.values(),
                key=lambda item: (-float(item.get("ripeness_score") or 0.0), str(item.get("zone_id"))),
            )[:3]
            if result.get("zone_id")
        ],
    }


__all__ = ["STATUS_COLORS", "build_harvest_map", "zone_feature"]
