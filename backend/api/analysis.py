"""Analysis, health and harvest-map endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from backend.api.deps import assert_farm_access
from backend.container import Container, get_container
from backend.core.auth import require_farmer
from geospatial.geojson.harvest_map import STATUS_COLORS
from backend.schemas import AnalyzeRequest, AnalyzeResponse, HealthSummary, HarvestMapResponse

router = APIRouter(prefix="/farms/{farm_id}", tags=["analysis"])

ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[Any, Depends(require_farmer)]

LEGEND = [
    {"status": status_value, "color": color, "label": status_value.replace("_", " ").title()}
    for status_value, color in STATUS_COLORS.items()
]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_farm(
    farm_id: str,
    container: ContainerDep,
    user: UserDep,
    payload: AnalyzeRequest | None = None,
) -> AnalyzeResponse:
    """Run the full pipeline: perception, fusion, risk, harvest, recommendation.

    The run is also persisted, so ``GET /harvest-map`` and
    ``GET /recommendations`` reflect it immediately.
    """
    request_body = payload or AnalyzeRequest()
    farm = assert_farm_access(container, farm_id, user)

    run = container.orchestrator.analyze_farm(
        farm,
        crop_stage=request_body.crop_stage,
        language=request_body.language,
        zone_ids=request_body.zone_ids,
        tier=request_body.tier,
        include_recommendations=request_body.include_recommendations,
        include_weather=request_body.include_weather,
        include_satellite=request_body.include_satellite,
    )
    payload_out = run.to_dict(include_map=False)
    return AnalyzeResponse(
        farm_id=run.farm_id,
        run_id=run.run_id,
        crop=run.crop,
        crop_stage=run.crop_stage,
        analyzed_at=run.analyzed_at,
        language=run.language,
        zones=[zone.result for zone in run.zones],
        status_counts=run.status_counts(),
        risk_counts=run.risk_counts(),
        recommendations=payload_out["recommendations"],
        health=HealthSummary(
            farm_id=run.farm_id,
            crop=run.crop,
            crop_stage=run.crop_stage,
            analyzed_at=run.analyzed_at,
            zones_analyzed=len(run.zones),
            zones_total=len(farm.get("zones") or []),
            status_counts=run.status_counts(),
            risk_counts=run.risk_counts(),
            zones=[zone.result for zone in run.zones],
            risks=_risk_payloads(run),
            weather=run.weather,
            satellite=run.satellite,
            evidence_summary=_evidence_summary(run),
            heuristic_version="heuristic-v0",
            heuristic_validated=False,
            is_mock=run.is_mock,
            notes=run.notes,
        ),
        harvest_map_uri=run.harvest_map_uri,
        is_mock=run.is_mock,
        duration_ms=run.duration_ms,
    )


@router.get("/health", response_model=HealthSummary)
def get_health(
    farm_id: str,
    container: ContainerDep,
    user: UserDep,
) -> HealthSummary:
    """Farm-level health roll-up from the most recent analysis.

    Runs the analysis when no result exists yet so the endpoint is useful
    immediately after farm creation.
    """
    farm = assert_farm_access(container, farm_id, user)

    results = container.repository.latest_zone_results(farm_id)
    if results:
        zones = list(results.values())
        risks: list[dict[str, Any]] = []
        status_counts: dict[str, int] = {}
        risk_counts: dict[str, int] = {}
        for zone in zones:
            status_counts[zone.get("status", "NO_DATA")] = (
                status_counts.get(zone.get("status", "NO_DATA"), 0) + 1
            )
            level = str(zone.get("risk_level", "none"))
            risk_counts[level] = risk_counts.get(level, 0) + 1
        analyzed_at = max(str(zone.get("analyzed_at", "")) for zone in zones)
        return HealthSummary(
            farm_id=farm_id,
            crop=str(farm.get("crop") or container.settings.default_crop),
            crop_stage=str(zone.get("crop_stage") or farm.get("crop_stage") or ""),
            analyzed_at=analyzed_at,
            zones_analyzed=len(zones),
            zones_total=len(farm.get("zones") or []),
            status_counts=status_counts,
            risk_counts=risk_counts,
            zones=zones,
            risks=risks,
            evidence_summary={"source": "latest_persisted_zone_results"},
            heuristic_version="heuristic-v0",
            heuristic_validated=False,
            notes=["Served from the latest persisted analysis; POST /analyze to refresh."],
        )

    run = container.orchestrator.analyze_farm(farm, language=str(farm.get("language") or "en"))
    return HealthSummary(
        farm_id=farm_id,
        crop=run.crop,
        crop_stage=run.crop_stage,
        analyzed_at=run.analyzed_at,
        zones_analyzed=len(run.zones),
        zones_total=len(farm.get("zones") or []),
        status_counts=run.status_counts(),
        risk_counts=run.risk_counts(),
        zones=[zone.result for zone in run.zones],
        risks=_risk_payloads(run),
        weather=run.weather,
        satellite=run.satellite,
        evidence_summary=_evidence_summary(run),
        heuristic_version="heuristic-v0",
        heuristic_validated=False,
        is_mock=run.is_mock,
        notes=run.notes,
    )


@router.get("/harvest-map", response_model=HarvestMapResponse)
def get_harvest_map(
    farm_id: str,
    container: ContainerDep,
    user: UserDep,
    refresh: bool = Query(default=False, description="Re-run the analysis first"),
) -> HarvestMapResponse:
    """GeoJSON FeatureCollection, zones colored by status."""
    farm = assert_farm_access(container, farm_id, user)

    if refresh:
        run = container.orchestrator.analyze_farm(farm, language=str(farm.get("language") or "en"))
        collection = run.harvest_map
        asset_uri = run.harvest_map_uri
        generated_at = run.analyzed_at
    else:
        collection = container.orchestrator.harvest_map(farm)
        latest = farm.get("latest_analysis") or {}
        # The stored GeoJSON asset from the last persisted run, so a client can
        # fetch the file the map was rendered from.
        asset_uri = latest.get("harvest_map_uri")
        generated_at = str(latest.get("analyzed_at") or "")

    return HarvestMapResponse(
        farm_id=farm_id,
        generated_at=generated_at,
        feature_collection=collection or {"type": "FeatureCollection", "features": []},
        asset_uri=asset_uri,
        legend=LEGEND,
        is_mock=any(
            bool(feature.get("properties", {}).get("simulated")) for feature in collection.get("features", [])
        ),
    )



def _risk_payloads(run: Any) -> list[dict[str, Any]]:
    """Risk assessments carry their zone id so clients can join them to zones."""
    return [
        {**zone.risk, "zone_id": zone.result.get("zone_id")}
        for zone in run.zones
    ]


def _evidence_summary(run: Any) -> dict[str, Any]:
    sources: dict[str, int] = {}
    with_data = 0
    for zone in run.zones:
        for source in zone.result.get("sources_used") or []:
            sources[source] = sources.get(source, 0) + 1
        if zone.result.get("ripeness_score") is not None:
            with_data += 1
    return {
        "sources_used": sources,
        "zones_with_ripeness": with_data,
        "zones_without_ripeness": len(run.zones) - with_data,
    }


__all__ = ["LEGEND", "router"]
