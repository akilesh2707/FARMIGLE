"""Composition root.

One container owns every long-lived service. Routers receive the container from
``request.app.state.container`` so nothing is built per request and tests can
swap the whole object for an in-memory one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from fastapi import Depends, Request

from backend.analysis.orchestrator import AnalysisOrchestrator
from backend.core.config import Settings, get_settings
from backend.core.firestore import (
    FirestoreRepository,
    InMemoryRepository,
    Repository,
)
from backend.core.logging import get_logger
from backend.core.storage import StorageService, build_storage
from backend.farm.service import FarmService
from backend.multilingual.service import MultilingualService
from backend.observations.service import ObservationService
from ml.providers import selected_ml_provider

logger = get_logger(__name__)


@dataclass
class Container:
    """Application services, built once per process."""

    settings: Settings
    repository: Repository
    storage: StorageService
    farms: FarmService
    observations: ObservationService
    orchestrator: AnalysisOrchestrator
    multilingual: MultilingualService = field(default_factory=MultilingualService)

    @classmethod
    def build(cls, settings: Settings | None = None) -> "Container":
        resolved = settings or get_settings()

        repository: Repository
        if resolved.mock_services:
            repository = InMemoryRepository()
        else:
            repository = FirestoreRepository()
        storage = build_storage(resolved)

        farms = FarmService(repository)
        observations = ObservationService(repository, storage)
        multilingual = MultilingualService()
        orchestrator = AnalysisOrchestrator(
            repository=repository,
            observations=observations,
            storage=storage,
            multilingual=multilingual,
            crop=resolved.default_crop,
        )

        container = cls(
            settings=resolved,
            repository=repository,
            storage=storage,
            farms=farms,
            observations=observations,
            orchestrator=orchestrator,
            multilingual=multilingual,
        )
        logger.info(
            "container_built",
            extra={
                "mock_services": resolved.mock_services,
                "repository": type(repository).__name__,
                "storage": type(storage).__name__,
                "crop": resolved.default_crop,
            },
        )
        return container

    # -- reporting ---------------------------------------------------------
    def provider_status(self) -> dict[str, Any]:
        """Provider inventory for ``GET /health``; no secrets, no credentials."""
        settings = self.settings
        orchestrator = self.orchestrator
        return {
            "persistence": type(self.repository).__name__,
            "storage": type(self.storage).__name__,
            "ml": {
                "fruit_detection": settings.ml_provider,
                "ripeness": selected_ml_provider(settings, "ml_ripeness_provider"),
                "health": selected_ml_provider(settings, "ml_health_provider"),
            },
            "satellite": {
                "provider": getattr(orchestrator.satellite, "name", "unknown"),
                "is_mock": bool(getattr(orchestrator.satellite, "is_mock", True)),
            },
            "weather": {
                "provider": getattr(orchestrator.weather, "name", "unknown"),
                "is_mock": bool(getattr(orchestrator.weather, "is_mock", True)),
            },
            "recommendations": {
                "provider": str(
                    getattr(orchestrator.recommendations.provider, "name", "unknown")
                ),
                "is_mock": bool(
                    getattr(orchestrator.recommendations.provider, "is_mock", True)
                ),
            },
            "speech": {
                "is_mock": bool(getattr(self.multilingual.speech_to_text, "is_mock", True)),
                "translation_is_mock": bool(
                    getattr(self.multilingual.translation, "is_mock", True)
                ),
                "tts_is_mock": bool(getattr(self.multilingual.text_to_speech, "is_mock", True)),
            },
        }

    def readiness(self) -> tuple[bool, list[str]]:
        """True when the service can answer requests it claims to support."""
        problems: list[str] = []
        settings = self.settings
        if not settings.mock_services and not settings.gemini_api_key:
            problems.append(
                "MOCK_SERVICES=false but GEMINI_API_KEY is unset; the recommendation tier "
                "will degrade to RULES_ONLY."
            )
        if not settings.mock_services and not settings.gcs_bucket:
            problems.append(
                "MOCK_SERVICES=false but GCS_BUCKET is unset; asset storage will fall back to "
                "local disk, which does not survive a restart."
            )
        return (not problems), problems


def get_container(request: Request) -> Container:
    """FastAPI dependency: fetch the container off app state."""
    container = getattr(request.app.state, "container", None)
    if container is None:  # pragma: no cover - only if startup was skipped
        raise RuntimeError("Application container is not initialised")
    return container


__all__ = ["Container", "get_container"]
