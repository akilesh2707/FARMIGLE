"""Farms router: create, read, update, delete, zones."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status

from backend.api.deps import assert_farm_access
from backend.container import Container, get_container
from backend.core.auth import require_farmer
from backend.schemas import FarmCreate, FarmDetail, FarmListResponse, FarmUpdate

router = APIRouter(prefix="/farms", tags=["farms"])

ContainerDep = Annotated[Container, Depends(get_container)]


def _as_detail(farm: dict[str, Any]) -> FarmDetail:
    return FarmDetail.model_validate(
        {
            **farm,
            "zone_count": len(farm.get("zones") or []),
        }
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=FarmDetail)
def create_farm(
    payload: FarmCreate,
    response: Response,
    request: Request,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> FarmDetail:
    """Create a farm and its deterministic zone grid."""
    farm = container.farms.create_farm(
        payload.model_dump(exclude_none=True),
        owner_uid=user.uid,
        district_id=getattr(user, "district_id", None),
    )
    response.headers["Location"] = f"/farms/{farm['farm_id']}"
    return _as_detail(farm)


@router.get("", response_model=FarmListResponse)
def list_farms(
    request: Request,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
    limit: int = Query(default=200, ge=1, le=500),
) -> FarmListResponse:
    """Farms the caller may see: their own, or the whole set for officers."""
    owner_uid = None if user.is_officer else user.uid
    farms = container.farms.list_farms(owner_uid=owner_uid, limit=limit)
    return FarmListResponse(
        farms=[_as_detail(farm) for farm in farms], count=len(farms)
    )


@router.get("/{farm_id}", response_model=FarmDetail)
def get_farm(
    farm_id: str,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> FarmDetail:
    return _as_detail(_assert_access(container, farm_id, user))


@router.patch("/{farm_id}", response_model=FarmDetail)
def update_farm(
    farm_id: str,
    payload: FarmUpdate,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> FarmDetail:
    _assert_access(container, farm_id, user)
    farm = container.farms.update_farm(farm_id, payload.model_dump(exclude_none=True))
    return _as_detail(farm)


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_farm(
    farm_id: str,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> Response:
    _assert_access(container, farm_id, user)
    container.farms.delete_farm(farm_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{farm_id}/zones")
def list_zones(
    farm_id: str,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> dict[str, Any]:
    farm = _assert_access(container, farm_id, user)
    zones = farm.get("zones") or []
    return {
        "farm_id": farm_id,
        "zone_grid": farm.get("zone_grid"),
        "zones": [
            {
                "zone_id": zone.get("zone_id"),
                "label": zone.get("label"),
                "row": zone.get("row"),
                "col": zone.get("col"),
                "centroid": zone.get("centroid"),
                "area_hectares": zone.get("area_hectares"),
                "geometry": zone.get("geometry"),
            }
            for zone in zones
        ],
        "count": len(zones),
    }


@router.get("/{farm_id}/zones/{zone_id}")
def get_zone(
    farm_id: str,
    zone_id: str,
    container: ContainerDep,
    user: Annotated[Any, Depends(require_farmer)],
) -> dict[str, Any]:
    _assert_access(container, farm_id, user)
    return container.farms.get_zone(farm_id, zone_id)


# Ownership enforcement lives in one place so no farm-scoped route can skip it.
_assert_access = assert_farm_access


__all__ = ["router"]
