"""FastAPI application entry point.

Run locally with::

    uvicorn backend.main:app --reload

The whole system is a single modular monolith: one process, one container, one
dependency graph. See ``README.md``.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.api import (
    analysis_router,
    district_router,
    farms_router,
    intelligence_router,
    observations_router,
)
from backend.container import Container
from backend.core.config import Settings, get_settings
from backend.core.errors import ApiError, ErrorCode
from backend.core.logging import configure_logging, get_logger
from backend.schemas import HealthResponse

logger = get_logger(__name__)

DESCRIPTION = """
AI Farm Intelligence Network - harvest intelligence for mango orchards.

**Boundaries that hold in this API**

* Perception (fruit detection, ripeness, health) is computer vision only.
  Gemini is never asked to look at an image.
* Decision (status, days to harvest, risk, action) comes from configurable
  rules in `configs/thresholds/`. Gemini is never asked to decide.
* Gemini only *explains* structured facts, in the farmer's language.
* Satellite vegetation indices are canopy context. They never claim ripeness.
* Disease wording is always "possible indicator ... requires local confirmation".
* Every zone status carries `heuristic_version` and `heuristic_validated: false`.
  These thresholds have not been validated against agronomist labels.

**Mock mode** is on by default: `MOCK_SERVICES=true` runs the entire system
with no Google credentials. `GET /health` reports which providers are in use.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The settings the app was built with, not a re-read of the environment:
    # otherwise `create_app(settings)` would configure routes from one Settings
    # object and its dependencies from another.
    settings: Settings = getattr(app.state, "settings", None) or get_settings()
    configure_logging(settings.log_level, as_json=settings.log_json)
    container = Container.build(settings)
    app.state.container = container

    ready, problems = container.readiness()
    
    if settings.mock_services:
        existing = container.farms.list_farms(owner_uid="dev_farmer_001")
        if not any(f.get("name") == "FARMIGLE Demo Farm" for f in existing):
            container.farms.create_farm(
                {
                    "name": "FARMIGLE Demo Farm",
                    "crop": "mango",
                    "language": "ta",
                    "boundary": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [77.10, 11.90],
                                [77.11, 11.90],
                                [77.11, 11.91],
                                [77.10, 11.91],
                                [77.10, 11.90]
                            ]
                        ]
                    }
                },
                owner_uid="dev_farmer_001"
            )
            logger.info("demo_farm_seeded")
    if problems:
        for problem in problems:
            logger.warning("readiness_problem", extra={"detail": problem})
    logger.info(
        "startup_complete",
        extra={
            "environment": settings.environment,
            "mock_services": settings.mock_services,
            "ready": ready,
        },
    )
    yield
    logger.info("shutdown_complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level, as_json=resolved.log_json)

    app = FastAPI(
        title=resolved.app_name,
        version=resolved.app_version,
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = resolved

    if resolved.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=resolved.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.exception_handler(ApiError)
    async def _api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content={**exc.to_payload(), "path": request.url.path},
        )

    @app.exception_handler(ValueError)
    async def _value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": ErrorCode.VALIDATION_ERROR,
                "message": str(exc),
                "path": request.url.path,
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Log the detail server-side, return a generic body to the client.
        logger.error(
            "unhandled_error",
            extra={"detail": str(exc), "error_type": type(exc).__name__},
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": ErrorCode.INTERNAL_ERROR,
                "message": "An unexpected error occurred. Please try again.",
                "path": request.url.path,
            },
        )

    prefix = resolved.api_prefix.rstrip("/")
    app.include_router(farms_router, prefix=prefix)
    app.include_router(observations_router, prefix=prefix)
    app.include_router(analysis_router, prefix=prefix)
    app.include_router(intelligence_router, prefix=prefix)
    app.include_router(district_router, prefix=prefix)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    @app.get("/api/health", response_model=HealthResponse, include_in_schema=False)
    def health(request: Request) -> HealthResponse:
        container: Container = request.app.state.container
        settings_used: Settings = container.settings
        ready, _ = container.readiness()
        return HealthResponse(
            status="ok" if ready else "degraded",
            service=settings_used.app_name,
            version=settings_used.app_version,
            environment=str(settings_used.environment),
            crop=settings_used.default_crop,
            mock_services=settings_used.mock_services,
            providers=container.provider_status(),
        )

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, Any]:
        return {
            "service": resolved.app_name,
            "version": resolved.app_version,
            "docs": "/docs",
            "health": "/health",
            "crop": resolved.default_crop,
            "mock_services": resolved.mock_services,
            "heuristic_version": "heuristic-v0",
            "disclaimer": (
                "Decision aid for harvest prioritisation. Thresholds are heuristic and "
                "not validated against agronomist labels. Disease-like signals are "
                "possible indicators requiring local confirmation."
            ),
        }

    return app


app = create_app()


__all__ = ["app", "create_app", "lifespan"]
