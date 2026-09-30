"""Structured output contract for the recommendation layer (Section 12.7).

Gemini is constrained to produce schema-valid JSON, the app validates it,
retries once on violation and finally falls back to a deterministic template.
The enums here are the single source of truth for that validation.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

HEALTH_STATUSES = ("healthy", "watch", "poor")
RIPENESS_STATUSES = ("harvest_ready", "near_ready", "not_ready", "health_concern")
RISK_LEVELS = ("none", "low", "medium", "high")
ALLOWED_ACTIONS = (
    "prioritize_harvest",
    "monitor_and_prepare",
    "continue_monitoring",
    "inspect_zone",
    "hold_and_revalidate",
)
EVIDENCE_CODES = (
    "high_ripeness_score",
    "moderate_ripeness_score",
    "low_ripeness_score",
    "health_score_good",
    "health_score_fair",
    "health_score_poor",
    "possible_disease_indicator",
    "canopy_anomaly",
    "upcoming_weather_event",
    "heavy_rain_forecast",
    "heat_stress_risk",
    "soil_moisture_low",
    "water_stress",
    "low_fusion_confidence",
    "single_source_evidence",
    "crop_stage_ripening",
)

TIER_GEMINI = "GEMINI"
TIER_GEMINI_SIMPLIFIED = "GEMINI_SIMPLIFIED"
TIER_RULES_ONLY = "RULES_ONLY"
TIERS = (TIER_GEMINI, TIER_GEMINI_SIMPLIFIED, TIER_RULES_ONLY)


class RecommendationTier(str, Enum):
    """Three-tier degradation documented for M11."""

    GEMINI = TIER_GEMINI
    GEMINI_SIMPLIFIED = TIER_GEMINI_SIMPLIFIED
    RULES_ONLY = TIER_RULES_ONLY


class GeminiRecommendationOutput(BaseModel):
    """Exactly the object described in Section 12.7."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    crop: str = Field(min_length=1, max_length=64)
    zone: str = Field(min_length=1, max_length=64)
    health_status: str
    ripeness_status: str
    risk_level: str
    evidence: list[str] = Field(default_factory=list, max_length=16)
    recommended_action: str
    explanation: str = Field(min_length=1, max_length=1200)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("health_status")
    @classmethod
    def _health_status(cls, value: str) -> str:
        if value not in HEALTH_STATUSES:
            raise ValueError(f"health_status must be one of {HEALTH_STATUSES}, got {value!r}")
        return value

    @field_validator("ripeness_status")
    @classmethod
    def _ripeness_status(cls, value: str) -> str:
        if value not in RIPENESS_STATUSES:
            raise ValueError(
                f"ripeness_status must be one of {RIPENESS_STATUSES}, got {value!r}"
            )
        return value

    @field_validator("risk_level")
    @classmethod
    def _risk_level(cls, value: str) -> str:
        if value not in RISK_LEVELS:
            raise ValueError(f"risk_level must be one of {RISK_LEVELS}, got {value!r}")
        return value

    @field_validator("recommended_action")
    @classmethod
    def _recommended_action(cls, value: str) -> str:
        if value not in ALLOWED_ACTIONS:
            raise ValueError(
                f"recommended_action must be one of {ALLOWED_ACTIONS}, got {value!r}"
            )
        return value

    @field_validator("evidence")
    @classmethod
    def _evidence(cls, value: list[str]) -> list[str]:
        unknown = [item for item in value if item not in EVIDENCE_CODES]
        if unknown:
            raise ValueError(f"unknown evidence codes: {unknown}")
        return value


def _gemini_response_schema() -> dict[str, Any]:
    """JSON Schema for Section 12.7, derived from the validating model.

    Built from :class:`GeminiRecommendationOutput` so the schema Gemini is
    constrained by can never drift from the schema the pipeline validates
    against. The string enums are inlined as ``enum`` lists, which the Gemini
    API accepts; the descriptive field descriptions are dropped.
    """
    schema = GeminiRecommendationOutput.model_json_schema()
    schema.pop("$defs", None)
    schema.pop("title", None)
    schema.pop("description", None)
    properties = schema.get("properties", {})
    for name, field_schema in properties.items():
        field_schema.pop("title", None)
        field_schema.pop("default", None)
        constraints = {
            "health_status": list(HEALTH_STATUSES),
            "ripeness_status": list(RIPENESS_STATUSES),
            "risk_level": list(RISK_LEVELS),
        }
        if name in constraints:
            field_schema.clear()
            field_schema.update({"type": "string", "enum": constraints[name]})
    schema["required"] = [
        "crop",
        "zone",
        "health_status",
        "ripeness_status",
        "risk_level",
        "recommended_action",
        "explanation",
        "confidence",
    ]
    return schema


GEMINI_RESPONSE_SCHEMA: dict[str, Any] = _gemini_response_schema()


class ExplainableParts(BaseModel):
    """Section 12.8 - never let free text look like sensor data."""

    model_config = ConfigDict(extra="forbid")

    evidence: str = ""
    inference: str = ""
    recommendation: str = ""
    explanation: str = ""


class Recommendation(BaseModel):
    """Persisted recommendation document (Section 12.5 + text/tier fields)."""

    model_config = ConfigDict(extra="forbid")

    recommendation_id: str
    farm_id: str
    zone_id: str
    action: str
    reason_codes: list[str] = Field(default_factory=list)
    language: str = "en"
    text: str
    audio_uri: str | None = None
    tier: str = TIER_RULES_ONLY
    crop: str = "mango"
    parts: ExplainableParts = Field(default_factory=ExplainableParts)
    evidence: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    language_translated: bool = False
    risk_disclaimer: str = ""
    heuristic_version: str = "heuristic-v0"
    is_mock: bool = False
    is_fallback: bool = False
    degradation_reason: str | None = None
    model: str | None = None
    created_at: str


def json_schema_for_prompt() -> str:
    """Compact schema description embedded in the user prompt."""
    return (
        '{"crop": string, "zone": string, "health_status": "healthy|watch|poor", '
        '"ripeness_status": "harvest_ready|near_ready|not_ready|health_concern", '
        '"risk_level": "none|low|medium|high", "evidence": [string], '
        '"recommended_action": "prioritize_harvest|monitor_and_prepare|'
        'continue_monitoring|inspect_zone|hold_and_revalidate", '
        '"explanation": string, "confidence": number}'
    )


def validate_gemini_output(payload: Any) -> tuple[GeminiRecommendationOutput | None, str | None]:
    """Validate raw model output. Returns ``(model, error_message)``."""
    if isinstance(payload, GeminiRecommendationOutput):
        return payload, None
    if isinstance(payload, str):
        try:
            import json

            payload = json.loads(payload)
        except (ValueError, TypeError) as exc:
            return None, f"not valid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"expected a JSON object, got {type(payload).__name__}"
    try:
        return GeminiRecommendationOutput.model_validate(payload), None
    except Exception as exc:  # pydantic ValidationError and friends
        return None, str(exc)


__all__ = [
    "ALLOWED_ACTIONS",
    "EVIDENCE_CODES",
    "ExplainableParts",
    "GeminiRecommendationOutput",
    "HEALTH_STATUSES",
    "RIPENESS_STATUSES",
    "RISK_LEVELS",
    "Recommendation",
    "RecommendationTier",
    "TIER_GEMINI",
    "TIER_GEMINI_SIMPLIFIED",
    "TIER_RULES_ONLY",
    "TIERS",
    "json_schema_for_prompt",
    "validate_gemini_output",
]
