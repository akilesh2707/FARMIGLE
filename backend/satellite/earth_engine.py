"""Real Earth Engine satellite provider - integration point.

Kept deliberately small and never required for local development (D6,
Section 11.1 "Live Earth Engine calls in the demo: latency and quota risk;
precompute").

Two supported modes:

* **cached** - an Earth Engine result previously exported to
  ``data/satellite/<farm_id>.json`` (or a GCS object) is read through the same
  parser as the seeded provider. This is the documented MVP path.
* **live** - a Sentinel-2 composite is requested through the Earth Engine
  Python API. Requires ``earthengine-api`` plus an authenticated service
  account; raises :class:`ProviderUnavailableError` otherwise.

This module does not import Earth Engine at module import time, so the service
starts fine without the optional dependency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.errors import ProviderUnavailableError
from backend.core.logging import get_logger
from backend.satellite.base import SatelliteContext
from backend.satellite.providers import SeededSatelliteProvider

logger = get_logger(__name__)


class EarthEngineSatelliteProvider:
    """Cached-first Earth Engine provider.

    ``allow_live`` gates the live path. When false (the default) the provider
    only serves precomputed results.
    """

    name = "earth_engine"
    is_mock = False

    def __init__(
        self,
        *,
        cache_provider: SeededSatelliteProvider | None = None,
        allow_live: bool = False,
        service_account: str | None = None,
        project_id: str | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self._cache_provider = cache_provider or SeededSatelliteProvider()
        self._allow_live = allow_live
        self._service_account = service_account
        self._project_id = project_id
        self._cache_path = cache_path

    def fetch(self, farm: dict[str, Any], *, thresholds: Any | None = None) -> SatelliteContext:
        context = self._cache_provider.fetch(farm, thresholds=thresholds)
        # Only trust precomputed results on this path; simulated fallbacks are
        # relabelled so a caller can tell they are not Earth Engine output.
        if context.cached:
            return SatelliteContext(
                provider=f"{self.name}:cached",
                is_mock=False,
                is_simulated=context.is_simulated,
                zones=context.zones,
                indices_used=context.indices_used,
                capture_date=context.capture_date,
                cached=True,
                notes=[*context.notes, "Served from a cached Earth Engine export."],
            )

        if not self._allow_live:
            raise ProviderUnavailableError(
                "No cached satellite result is available for this farm and live "
                "Earth Engine calls are disabled (SAT_SATELLITE_ALLOW_LIVE=false). "
                "Export a precomputed result to data/satellite/ or run with "
                "MOCK_SERVICES=true."
            )

        return self._fetch_live(farm, thresholds=thresholds)

    def _fetch_live(self, farm: dict[str, Any], *, thresholds: Any | None = None) -> SatelliteContext:
        try:
            import ee  # noqa: PLC0415 - optional dependency, intentionally lazy
        except ImportError as exc:
            raise ProviderUnavailableError(
                "earthengine-api is not installed. Install it and authenticate a "
                "service account to enable live satellite context."
            ) from exc

        if not (self._service_account and self._project_id):
            raise ProviderUnavailableError(
                "Live Earth Engine requires both a service account and a project id."
            )

        try:
            from google.oauth2 import service_account

            credentials = service_account.Credentials.from_service_account_file(
                self._service_account,
                scopes=["https://www.googleapis.com/auth/earthengine"],
            )
            ee.Initialize(credentials=credentials, project=self._project_id)
        except Exception as exc:  # pragma: no cover - requires real credentials
            logger.error("earth_engine_init_failed", extra={"error_type": type(exc).__name__})
            raise ProviderUnavailableError("Live Earth Engine initialisation failed.") from exc

        raise ProviderUnavailableError(
            "Live Earth Engine compositing is not implemented in this MVP milestone. "
            "The documented MVP scope is a precomputed, cached anomaly layer."
        )


__all__ = ["EarthEngineSatelliteProvider"]
