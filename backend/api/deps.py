"""Shared router dependencies.

Every farm-scoped route funnels through :func:`assert_farm_access`. Route-level
role checks alone are not enough: a farmer who knows another farmer's
``farm_id`` must not read their observations, zones or recommendations.
"""

from __future__ import annotations

from typing import Any

from backend.container import Container
from backend.core.errors import ForbiddenError


def assert_farm_access(container: Container, farm_id: str, user: Any) -> dict[str, Any]:
    """Load a farm and enforce ownership, or raise :class:`ForbiddenError`.

    Officers may read any farm (district oversight); farmers may only reach
    farms they own.
    """
    farm = container.farms.get_farm(farm_id)
    if user.is_officer:
        return farm
    owner = farm.get("owner_uid")
    if owner and owner != user.uid:
        raise ForbiddenError("You do not have access to this farm.")
    return farm


__all__ = ["assert_farm_access"]
