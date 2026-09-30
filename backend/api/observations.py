"""Observations router: image, voice and text ingestion."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, status

from backend.api.deps import assert_farm_access
from backend.container import Container, get_container
from backend.core.auth import require_farmer
from backend.schemas import ObservationCreate, ObservationListResponse

router = APIRouter(prefix="/farms/{farm_id}/observations", tags=["observations"])

ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[Any, Depends(require_farmer)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ObservationListResponse)
def create_observation(
    farm_id: str,
    payload: ObservationCreate,
    container: ContainerDep,
    user: UserDep,
) -> ObservationListResponse:
    assert_farm_access(container, farm_id, user)
    observation = container.observations.create_observation(
        farm_id, payload.model_dump(exclude_none=True), owner_uid=user.uid
    )
    return ObservationListResponse(observations=[observation], count=1)


@router.get("", response_model=ObservationListResponse)
def list_observations(
    farm_id: str,
    container: ContainerDep,
    user: UserDep,
    zone_id: str | None = Query(default=None, pattern=r"^zone_\d{2,}$"),
    source: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=200, ge=1, le=500),
) -> ObservationListResponse:
    assert_farm_access(container, farm_id, user)
    observations = container.observations.list_observations(
        farm_id, zone_id=zone_id, source=source, limit=limit
    )
    return ObservationListResponse(observations=observations, count=len(observations))


@router.get("/{observation_id}")
def get_observation(
    farm_id: str,
    observation_id: str,
    container: ContainerDep,
    user: UserDep,
) -> dict[str, Any]:
    assert_farm_access(container, farm_id, user)
    observation = container.repository.get_observation(farm_id, observation_id)
    if observation is None:
        from backend.core.errors import ObservationNotFoundError

        raise ObservationNotFoundError(f"{farm_id}/{observation_id}")
    return observation


@router.delete("/{observation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_observation(
    farm_id: str,
    observation_id: str,
    container: ContainerDep,
    user: UserDep,
) -> None:
    from fastapi import Response

    assert_farm_access(container, farm_id, user)
    if not container.repository.delete_observation(farm_id, observation_id):
        from backend.core.errors import ObservationNotFoundError

        raise ObservationNotFoundError(f"{farm_id}/{observation_id}")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
