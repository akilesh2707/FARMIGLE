"""API routers (Section 12.6)."""

from backend.api.analysis import router as analysis_router
from backend.api.district import router as district_router
from backend.api.farms import router as farms_router
from backend.api.intelligence import router as intelligence_router
from backend.api.observations import router as observations_router

__all__ = [
    "analysis_router",
    "district_router",
    "farms_router",
    "intelligence_router",
    "observations_router",
]
