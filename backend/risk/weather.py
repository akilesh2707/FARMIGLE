"""M8 - Weather context.

Weather is *context*, never a measurement of the crop (Section 3.3). It is used
by the risk engine (rain risk, heat stress) and by the recommendation
explanation ("upcoming_weather_event").

Providers
---------
* :class:`SeededWeatherProvider`     - deterministic, offline, default.
* :class:`OpenMeteoWeatherProvider`  - real, free, keyless HTTP API.
* :class:`GoogleWeatherProvider`     - Google Maps Platform Weather API
  integration point; requires an API key.

The whole analysis pipeline works when weather is unavailable, so a provider
failure degrades gracefully rather than raising.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable

from backend.core.errors import ProviderUnavailableError
from backend.core.logging import get_logger

logger = get_logger(__name__)

STATE_FORECAST = "forecast"
STATE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class WeatherEvent:
    """A single forecast event relevant to harvest timing."""

    kind: str  # heavy_rain | rain | heat | strong_wind | dry_spell
    day_offset: int
    severity: str  # low | medium | high
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "day_offset": self.day_offset,
            "severity": self.severity,
            "description": self.description,
        }


@dataclass(frozen=True)
class WeatherContext:
    """Structured weather context for a farm location."""

    provider: str
    is_mock: bool
    is_simulated: bool
    state: str = STATE_FORECAST
    temperature_c: float | None = None
    temperature_max_c: float | None = None
    rain_probability: float | None = None
    precipitation_mm: float | None = None
    humidity: float | None = None
    wind_kph: float | None = None
    forecast_window_days: int = 0
    weather_events: list[WeatherEvent] = field(default_factory=list)
    location: dict[str, float] | None = None
    observed_at: str | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return self.state == STATE_FORECAST

    @property
    def event_kinds(self) -> list[str]:
        return [event.kind for event in self.weather_events]

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "is_mock": self.is_mock,
            "is_simulated": self.is_simulated,
            "state": self.state,
            "available": self.available,
            "temperature_c": None if self.temperature_c is None else round(self.temperature_c, 2),
            "temperature_max_c": None
            if self.temperature_max_c is None
            else round(self.temperature_max_c, 2),
            "rain_probability": None if self.rain_probability is None else round(self.rain_probability, 4),
            "precipitation_mm": None
            if self.precipitation_mm is None
            else round(self.precipitation_mm, 2),
            "humidity": None if self.humidity is None else round(self.humidity, 2),
            "wind_kph": None if self.wind_kph is None else round(self.wind_kph, 2),
            "forecast_window_days": self.forecast_window_days,
            "weather_events": [event.to_dict() for event in self.weather_events],
            "location": self.location,
            "observed_at": self.observed_at,
            "notes": list(self.notes),
        }


@runtime_checkable
class WeatherProvider(Protocol):
    name: str
    is_mock: bool

    def fetch(
        self, location: dict[str, float] | None, *, thresholds: Any | None = None
    ) -> WeatherContext: ...


class SeededWeatherProvider:
    """Deterministic offline weather context.

    Keyed on the farm's rounded location and today's date, so repeated calls on
    the same day return identical values (required for reproducible tests and a
    stable demo) while still differing between farms.
    """

    name = "seeded_weather"
    is_mock = True

    def fetch(
        self, location: dict[str, float] | None, *, thresholds: Any | None = None
    ) -> WeatherContext:
        config = _resolve_thresholds(thresholds)
        lat = float((location or {}).get("lat", 11.5))
        lng = float((location or {}).get("lng", 78.1))
        seed = _unit(f"{lat:.4f},{lng:.4f},{date.today().isoformat()}")

        # A stable window of 7 days, but only some farms get rain.
        rain_probability = round(0.15 + 0.75 * _unit(f"rain:{lat:.3f}:{lng:.3f}"), 4)
        temperature = 26.0 + 9.0 * _unit(f"temp:{lat:.3f}:{lng:.3f}")
        wind = 5.0 + 22.0 * _unit(f"wind:{lat:.3f}:{lng:.3f}")

        events: list[WeatherEvent] = []
        if rain_probability >= float(config["heavy_rain_probability"]):
            day = 1 + int(_unit(f"rainday:{lat:.3f}:{lng:.3f}") * 3)
            events.append(
                WeatherEvent(
                    kind="heavy_rain",
                    day_offset=day,
                    severity="high",
                    description=f"High chance of heavy rain in about {day} day(s).",
                )
            )
        elif rain_probability >= 0.35:
            events.append(
                WeatherEvent(
                    kind="rain",
                    day_offset=2,
                    severity="medium",
                    description="Scattered rain likely within the forecast window.",
                )
            )
        if temperature >= float(config["heat_risk_temperature_c"]):
            events.append(
                WeatherEvent(
                    kind="heat",
                    day_offset=1,
                    severity="high",
                    description="High daytime temperature expected.",
                )
            )
        if wind >= float(config["strong_wind_kph"]):
            events.append(
                WeatherEvent(
                    kind="strong_wind",
                    day_offset=1,
                    severity="medium",
                    description="Strong wind expected; secure loose fruit and equipment.",
                )
            )

        return WeatherContext(
            provider=f"{self.name}:simulated",
            is_mock=True,
            is_simulated=True,
            state=STATE_FORECAST,
            temperature_c=temperature,
            temperature_max_c=temperature + 3.5,
            rain_probability=rain_probability,
            precipitation_mm=round(rain_probability * 22.0, 2),
            humidity=round(45.0 + 40.0 * seed, 2),
            wind_kph=wind,
            forecast_window_days=int(config["heavy_rain_window_days"]),
            weather_events=events,
            location={"lat": lat, "lng": lng},
            observed_at=date.today().isoformat(),
            notes=[
                "SIMULATED weather context: no live weather provider is configured. "
                "Values are a deterministic function of location and date.",
            ],
        )


class OpenMeteoWeatherProvider:
    """Real, keyless free fallback (documented in Section 7 M8)."""

    name = "open_meteo"
    is_mock = False
    endpoint = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout_seconds: float = 8.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch(
        self, location: dict[str, float] | None, *, thresholds: Any | None = None
    ) -> WeatherContext:
        if not location or "lat" not in location or "lng" not in location:
            return unavailable(self.name, "Farm has no location, so weather cannot be fetched.")

        try:
            import httpx

            response = httpx.get(
                self.endpoint,
                params={
                    "latitude": location["lat"],
                    "longitude": location["lng"],
                    "daily": "temperature_2m_max,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
                    "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
                    "forecast_days": 7,
                    "timezone": "auto",
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("open_meteo_fetch_failed", extra={"error_type": type(exc).__name__})
            return unavailable(self.name, "Weather provider request failed.")

        try:
            current = payload.get("current") or {}
            daily = payload.get("daily") or {}
            probabilities = daily.get("precipitation_probability_max") or []
            rain_probability = (
                max(float(value) for value in probabilities if value is not None) / 100.0
                if probabilities
                else None
            )
            config = _resolve_thresholds(thresholds)
            events: list[WeatherEvent] = []
            if rain_probability is not None and rain_probability >= float(config["heavy_rain_probability"]):
                events.append(
                    WeatherEvent(
                        kind="heavy_rain",
                        day_offset=1,
                        severity="high",
                        description="High probability of rain within the forecast window.",
                    )
                )
            return WeatherContext(
                provider=self.name,
                is_mock=False,
                is_simulated=False,
                temperature_c=_as_float(current.get("temperature_2m")),
                temperature_max_c=_as_float((daily.get("temperature_2m_max") or [None])[0]),
                rain_probability=rain_probability,
                precipitation_mm=_as_float((daily.get("precipitation_sum") or [None])[0]),
                humidity=_as_float(current.get("relative_humidity_2m")),
                wind_kph=_as_float(current.get("wind_speed_10m")),
                forecast_window_days=len(daily.get("time") or []) or 7,
                weather_events=events,
                location={"lat": float(location["lat"]), "lng": float(location["lng"])},
                observed_at=current.get("time"),
                notes=["Live weather from Open-Meteo (free fallback provider)."],
            )
        except (TypeError, ValueError, KeyError) as exc:
            logger.warning("open_meteo_parse_failed", extra={"error_type": type(exc).__name__})
            return unavailable(self.name, "Weather provider returned an unexpected payload.")


class GoogleWeatherProvider:
    """Google Maps Platform Weather API integration point.

    Requires ``WEATHER_API_KEY``. No key is committed to the repository, and the
    documented fallback is Open-Meteo, so this class refuses to run unconfigured
    rather than pretending to return live data.
    """

    name = "google_weather"
    is_mock = False

    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key

    def fetch(
        self, location: dict[str, float] | None, *, thresholds: Any | None = None
    ) -> WeatherContext:
        if not self.api_key:
            raise ProviderUnavailableError(
                "WEATHER_API_KEY is not configured. Use WEATHER_PROVIDER=open_meteo "
                "or WEATHER_PROVIDER=seeded."
            )
        raise ProviderUnavailableError(
            "The Google Maps Platform Weather API adapter is not implemented in this "
            "MVP milestone. WEATHER_PROVIDER=open_meteo provides the documented "
            "free fallback."
        )


def build_weather_provider(settings: Any | None = None) -> WeatherProvider:
    """Provider factory honouring ``MOCK_SERVICES`` and ``WEATHER_PROVIDER``.

    The orchestrator never raises when a provider is misconfigured: it receives
    the provider and the provider itself degrades to :func:`unavailable`.
    """
    from backend.core.config import get_settings

    resolved = settings or get_settings()
    if resolved.mock_services:
        return SeededWeatherProvider()
    choice = str(getattr(resolved, "weather_provider", "open_meteo") or "open_meteo").lower()
    if choice in ("seeded", "mock", "simulated"):
        return SeededWeatherProvider()
    if choice in ("google", "google_maps"):
        return GoogleWeatherProvider(api_key=resolved.weather_api_key)
    return OpenMeteoWeatherProvider()


def unavailable(provider: str, reason: str) -> WeatherContext:
    """A well-formed 'no weather' context. The pipeline must tolerate this."""
    return WeatherContext(
        provider=provider,
        is_mock=False,
        is_simulated=False,
        state=STATE_UNAVAILABLE,
        notes=[reason, "Analysis continues without weather context."],
    )


def _unit(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(16 ** 12)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _resolve_thresholds(thresholds: Any | None) -> dict[str, float]:
    defaults = {
        "heavy_rain_probability": 0.60,
        "heavy_rain_window_days": 3,
        "heat_risk_temperature_c": 38.0,
        "strong_wind_kph": 30.0,
    }
    if thresholds is None:
        return defaults
    weather = getattr(thresholds, "risk", {}).get("weather", {}) if hasattr(thresholds, "risk") else {}
    merged = dict(defaults)
    for key, value in (weather or {}).items():
        if key in merged and isinstance(value, (int, float)):
            merged[key] = float(value)
    return merged


__all__ = [
    "GoogleWeatherProvider",
    "build_weather_provider",
    "OpenMeteoWeatherProvider",
    "STATE_FORECAST",
    "STATE_UNAVAILABLE",
    "SeededWeatherProvider",
    "WeatherContext",
    "WeatherEvent",
    "WeatherProvider",
    "unavailable",
]
