"""District hotspot router (officer only).

Aggregated farm-level indicators. No farmer identity is returned, and every
hotspot is labelled as a potential signal requiring validation.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query

from backend.container import Container, get_container
from backend.core.auth import require_officer
from backend.core.crop_config import load_thresholds
from backend.core.utils import utc_now_iso
from backend.schemas import Hotspot, HotspotResponse

router = APIRouter(prefix="/district", tags=["district"])

ContainerDep = Annotated[Container, Depends(get_container)]
OfficerDep = Annotated[Any, Depends(require_officer)]

HOTSPOT_DISCLAIMER = (
    "Potential hotspots only. These are rule-based indicators, not confirmed disease "
    "outbreaks, and require local validation."
)


@router.get("/hotspots", response_model=HotspotResponse)
def list_hotspots(
    container: ContainerDep,
    officer: OfficerDep,
    district: str | None = Query(default=None, max_length=64),
    limit: int = Query(default=50, ge=1, le=200),
) -> HotspotResponse:
    """Hotspots derived from the latest analysis of each farm.

    Aggregation happens here: only farm id, district and agricultural signals
    leave the backend, never a farmer's name, phone number or voice note.
    """
    thresholds = load_thresholds(container.settings.default_crop)
    config = thresholds.hotspots
    min_zones = int(config.get("min_zones_to_flag", 1))
    medium_score = float(config.get("medium_score", 0.4))
    high_score = float(config.get("high_score", 0.6))
    high_risk_codes = set(config.get("high_risk_codes", []))

    farms = container.repository.list_farms(district_id=district, limit=limit)
    hotspots: list[Hotspot] = []
    is_mock = True

    for farm in farms:
        farm_id = str(farm.get("farm_id"))
        results = container.repository.latest_zone_results(farm_id)
        if not results:
            continue
        zone_ids = sorted(results)
        if len(zone_ids) < min_zones:
            continue

        status_counts: dict[str, int] = {}
        risk_counts: dict[str, int] = {}
        reason_codes: list[str] = []
        concerned: list[str] = []
        for zone_id, zone in results.items():
            status_value = str(zone.get("status", "NO_DATA"))
            status_counts[status_value] = status_counts.get(status_value, 0) + 1
            level = str(zone.get("risk_level", "none"))
            risk_counts[level] = risk_counts.get(level, 0) + 1
            for code in zone.get("risk_codes") or []:
                if code not in reason_codes:
                    reason_codes.append(str(code))
            if status_value == "HEALTH_CONCERN" or level in {"medium", "high"}:
                concerned.append(zone_id)
            is_mock = is_mock or bool(zone.get("is_mock"))

        if not concerned and not high_risk_codes.intersection(reason_codes):
            continue

        score = _hotspot_score(
            concerned=len(concerned),
            total=len(zone_ids),
            reason_codes=reason_codes,
            high_risk_codes=high_risk_codes,
            weight=high_score - medium_score,
        )
        risk_level = "high" if score >= high_score else "medium"
        hotspots.append(
            Hotspot(
                farm_id=farm_id,
                district=farm.get("district_id"),
                zone_ids=sorted(concerned),
                hotspot_score=round(score, 4),
                risk_level=risk_level,
                reason_codes=reason_codes,
                status_counts=status_counts,
                risk_counts=risk_counts,
                validation_status="potential_requires_validation",
                zones_analyzed=len(zone_ids),
                analyzed_at=max(str(zone.get("analyzed_at", "")) for zone in results.values()),
                disclaimer=HOTSPOT_DISCLAIMER,
            )
        )

    hotspots.sort(key=lambda item: item.hotspot_score, reverse=True)
    return HotspotResponse(
        hotspots=hotspots,
        count=len(hotspots),
        district=district,
        generated_at=utc_now_iso(),
        aggregation="farm_level_aggregate_no_farmer_identity",
        disclaimer=HOTSPOT_DISCLAIMER,
        is_mock=is_mock,
    )


def _hotspot_score(
    *,
    concerned: int,
    total: int,
    reason_codes: list[str],
    high_risk_codes: set[str],
    weight: float,
) -> float:
    share = (concerned / total) if total else 0.0
    score = share
    if high_risk_codes.intersection(reason_codes):
        score = min(1.0, score + weight)
    return score


__all__ = ["HOTSPOT_DISCLAIMER", "router"]
