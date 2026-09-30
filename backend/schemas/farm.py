"""Pydantic request/response models for the documented API surface."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.utils import ZONE_ID_PATTERN, utc_now_iso

# Sources listed in Section 12.1.
OBSERVATION_SOURCES = (
    "satellite",
    "drone",
    "phone",
    "rover",
    "farmer_report",
    "weather",
    "soil",
)
HARVEST_STATUSES = (
    "HARVEST_READY",
    "NEAR_READY",
    "NOT_READY",
    "HEALTH_CONCERN",
    "NO_DATA",
)
RISK_LEVELS = ("none", "low", "medium", "high")
LANGUAGES = ("ta", "hi", "en", "ml", "kn", "te")
TIERS = ("GEMINI", "GEMINI_SIMPLIFIED", "RULES_ONLY")


def _validate_zone_id(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not ZONE_ID_PATTERN.match(text):
        raise ValueError("zone_id must look like 'zone_07'")
    return text


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------
class ErrorResponse(BaseModel):
    error: str
    message: str
    details: Any | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    crop: str
    mock_services: bool
    providers: dict[str, Any] = Field(default_factory=dict)
    time: str = Field(default_factory=utc_now_iso)


# ---------------------------------------------------------------------------
# Farms
# ---------------------------------------------------------------------------
class ZoneSpec(BaseModel):
    """Optional client-supplied zone geometry. The server generates a grid when
    the client only supplies a boundary."""

    model_config = ConfigDict(extra="forbid")

    zone_id: str
    label: str | None = None
    row: int = Field(ge=0)
    col: int = Field(ge=0)
    geometry: dict[str, Any] | None = None

    @field_validator("zone_id")
    @classmethod
    def _zone_id(cls, value: str) -> str:
        return _validate_zone_id(value)  # type: ignore[return-value]


class FarmCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    crop: str = Field(default="mango", min_length=1, max_length=32)
    crop_stage: str = Field(default="fruit_development", min_length=1, max_length=48)
    boundary: dict[str, Any] = Field(description="GeoJSON Polygon geometry (EPSG:4326)")
    language: str = Field(default="en", min_length=2, max_length=8)
    center: dict[str, float] | None = None
    zones: list[ZoneSpec] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FarmUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=160)
    crop_stage: str | None = Field(default=None, min_length=1, max_length=48)
    language: str | None = Field(default=None, min_length=2, max_length=8)
    crop: str | None = Field(default=None, min_length=1, max_length=32)
    center: dict[str, float] | None = None
    zones: list[ZoneSpec] | None = None
    metadata: dict[str, Any] | None = None


class FarmSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    name: str
    crop: str
    crop_stage: str
    created_at: str
    updated_at: str | None = None
    zone_count: int = 0
    owner_uid: str | None = None


class FarmDetail(FarmSummary):
    boundary: dict[str, Any] | None = None
    center: dict[str, float] | None = None
    language: str = "en"
    zones: list[dict[str, Any]] = Field(default_factory=list)
    area_hectares: float | None = None
    centroid: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FarmListResponse(BaseModel):
    farms: list[FarmSummary]
    count: int


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------
class ObservationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    zone_id: str | None = None
    image_reference: str | None = None
    image_base64: str | None = None
    location: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = Field(default=None, max_length=2000)
    recorded_at: str | None = None
    farmer_report: dict[str, Any] | None = None
    transcript: str | None = None
    language: str = Field(default="en", min_length=2, max_length=8)

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        text = str(value).strip().lower()
        if text not in OBSERVATION_SOURCES:
            raise ValueError(f"source must be one of {OBSERVATION_SOURCES}")
        return text

    @field_validator("zone_id")
    @classmethod
    def _zone_id(cls, value: str | None) -> str | None:
        return _validate_zone_id(value)

    @field_validator("image_base64")
    @classmethod
    def _image_base64(cls, value: str | None) -> str | None:
        if value and len(value) > 12 * 1024 * 1024:
            raise ValueError("image_base64 is too large (max ~9 MB decoded)")
        return value


class Observation(BaseModel):
    model_config = ConfigDict(extra="allow")

    observation_id: str
    farm_id: str
    source: str
    zone_id: str | None = None
    timestamp: str
    location: dict[str, Any] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    image_reference: str | None = None
    notes: str | None = None
    language: str = "en"
    asset_uri: str | None = None


class ObservationListResponse(BaseModel):
    observations: list[Observation]
    count: int


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------
class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    crop_stage: str | None = Field(default=None, min_length=1, max_length=48)
    language: str = Field(default="en", min_length=2, max_length=8)
    zone_ids: list[str] | None = None
    tier: str | None = None
    include_recommendations: bool = True
    include_weather: bool = True
    include_satellite: bool = True

    @field_validator("tier")
    @classmethod
    def _tier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).upper()
        if text not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        return text


class ZoneResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    zone_id: str
    zone_label: str | None = None
    ripeness_score: float | None = None
    status: str
    health_score: float | None = None
    health_status: str = "unknown"
    risk_level: str = "none"
    estimated_harvest_window: str | None = None
    days_to_harvest_min: int | None = None
    days_to_harvest_max: int | None = None
    sources_used: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    evidence_insufficient: bool = True
    confidence: float = 0.0
    reason_codes: list[str] = Field(default_factory=list)
    recommended_action: str = "CONTINUE_MONITORING"
    notes: list[str] = Field(default_factory=list)
    heuristic_version: str = "heuristic-v0"
    heuristic_validated: bool = False
    is_mock: bool = False


class RiskDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    zone_id: str
    risk_level: str
    health_status: str = "unknown"
    risk_codes: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    needs_local_confirmation: bool = False
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)
    disclaimer: str | None = None


class HealthSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    crop: str
    crop_stage: str
    analyzed_at: str
    zones_analyzed: int
    zones_total: int
    status_counts: dict[str, int] = Field(default_factory=dict)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    zones: list[ZoneResult] = Field(default_factory=list)
    risks: list[RiskDetail] = Field(default_factory=list)
    weather: dict[str, Any] | None = None
    satellite: dict[str, Any] | None = None
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    heuristic_version: str = "heuristic-v0"
    heuristic_validated: bool = False
    is_mock: bool = False
    notes: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    run_id: str | None = None
    crop: str
    crop_stage: str
    analyzed_at: str
    language: str
    zones: list[ZoneResult] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    risk_counts: dict[str, int] = Field(default_factory=dict)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    health: HealthSummary | None = None
    harvest_map_uri: str | None = None
    is_mock: bool = False
    duration_ms: int | None = None


# ---------------------------------------------------------------------------
# Image analysis
# ---------------------------------------------------------------------------
class ImageAnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str | None = None
    source: str = Field(default="phone")
    image_base64: str | None = None
    image_reference: str | None = None
    mime_type: str = Field(default="image/jpeg", max_length=64)
    language: str = Field(default="en", min_length=2, max_length=8)
    save: bool = True
    tier: str | None = None

    @field_validator("zone_id")
    @classmethod
    def _zone_id(cls, value: str | None) -> str | None:
        return _validate_zone_id(value)

    @field_validator("source")
    @classmethod
    def _source(cls, value: str) -> str:
        text = str(value).strip().lower()
        if text not in {"phone", "rover", "drone", "ground"}:
            raise ValueError("source must be one of phone, rover, drone, ground")
        return text


class ImageAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    observation_id: str | None = None
    zone_id: str | None = None
    source: str
    fruit_count: int = 0
    detection_confidence: float = 0.0
    ripeness_score: float | None = None
    ripeness_label: str | None = None
    health_score: float | None = None
    health_label: str | None = None
    possible_health_indicators: list[str] = Field(default_factory=list)
    image_quality: dict[str, Any] = Field(default_factory=dict)
    accepted: bool = True
    rejection_reason: str | None = None
    recommendation: dict[str, Any] | None = None
    is_mock: bool = False
    providers: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Voice
# ---------------------------------------------------------------------------
class VoiceQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audio_base64: str | None = None
    audio_reference: str | None = None
    mime_type: str = Field(default="audio/webm", max_length=64)
    text: str | None = Field(default=None, max_length=4000)
    language: str = Field(default="ta", min_length=2, max_length=8)
    zone_id: str | None = None
    synthesize: bool = True
    tier: str | None = None

    @field_validator("zone_id")
    @classmethod
    def _zone_id(cls, value: str | None) -> str | None:
        return _validate_zone_id(value)


class VoiceQueryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    transcript: str
    language: str
    intent: dict[str, Any]
    answer_text: str
    answer_language: str
    audio_uri: str | None = None
    zone_id: str | None = None
    zone_label: str | None = None
    translation: dict[str, Any] | None = None
    speech: dict[str, Any] | None = None
    clarification: str | None = None
    zone_result: ZoneResult | None = None
    recommendation: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    is_mock: bool = False
    degraded: bool = False


# ---------------------------------------------------------------------------
# Maps, recommendations, hotspots
# ---------------------------------------------------------------------------
class HarvestMapResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    generated_at: str
    feature_collection: dict[str, Any]
    asset_uri: str | None = None
    legend: list[dict[str, str]] = Field(default_factory=list)
    is_mock: bool = False


class RecommendationSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    recommendation_id: str
    farm_id: str
    zone_id: str
    action: str
    reason_codes: list[str] = Field(default_factory=list)
    language: str = "en"
    text: str
    audio_uri: str | None = None


class RecommendationListResponse(BaseModel):
    recommendations: list[RecommendationSummary]
    count: int


class Hotspot(BaseModel):
    model_config = ConfigDict(extra="allow")

    farm_id: str
    district: str | None = None
    zone_ids: list[str] = Field(default_factory=list)
    hotspot_score: float = 0.0
    risk_level: str = "low"
    reason_codes: list[str] = Field(default_factory=list)
    status_counts: dict[str, int] = Field(default_factory=dict)
    validation_status: str = "potential_requires_validation"


class HotspotResponse(BaseModel):
    hotspots: list[Hotspot]
    count: int
    district: str | None = None
    generated_at: str
    aggregation: str = "farm_level_aggregate_no_farmer_identity"
    disclaimer: str = (
        "Potential hotspots only. These are rule-based indicators, not confirmed disease "
        "outbreaks, and require local validation."
    )
    is_mock: bool = False


__all__ = [
    "AnalyzeRequest",
    "AnalyzeResponse",
    "ErrorResponse",
    "FarmCreate",
    "FarmDetail",
    "FarmListResponse",
    "FarmSummary",
    "FarmUpdate",
    "HARVEST_STATUSES",
    "HealthResponse",
    "HealthSummary",
    "Hotspot",
    "HotspotResponse",
    "ImageAnalysisRequest",
    "ImageAnalysisResponse",
    "LANGUAGES",
    "OBSERVATION_SOURCES",
    "Observation",
    "ObservationCreate",
    "ObservationListResponse",
    "RISK_LEVELS",
    "RecommendationListResponse",
    "RecommendationSummary",
    "RiskDetail",
    "TIERS",
    "VoiceQueryRequest",
    "VoiceQueryResponse",
    "ZoneResult",
    "ZoneSpec",
]
