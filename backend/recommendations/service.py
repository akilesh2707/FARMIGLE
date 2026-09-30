"""Recommendation service: the three-tier Gemini pipeline.

Flow documented in Section 12.7:

    facts -> Gemini (JSON schema) -> validate -> retry once -> RULES_ONLY

The service never raises: a recommendation document is always returned so a
Gemini outage degrades quality instead of breaking the farmer's request.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from backend.core.crop_config import ThresholdConfig, load_thresholds
from backend.core.utils import stable_seed, utc_now_iso
from backend.fusion.models import ZoneFusionResult
from backend.harvest.engine import HarvestDecision
from backend.recommendations.fallback import (
    ACTION_TEXT,
    build_explainable_parts,
    build_fallback_output,
    build_fallback_text,
)
from backend.recommendations.providers import (
    build_recommendation_provider,
    parse_raw_output,
)
from backend.recommendations.prompt import resolve_tier
from backend.recommendations.schema import (
    ExplainableParts,
    GeminiRecommendationOutput,
    Recommendation,
    TIER_GEMINI,
    TIER_GEMINI_SIMPLIFIED,
    TIER_RULES_ONLY,
    validate_gemini_output,
)
from backend.risk.engine import RiskAssessment

logger = logging.getLogger(__name__)

MAX_VALIDATION_RETRIES = 1
CORRECTION_HINT = (
    "Your previous reply was rejected by schema validation. Return ONLY a single JSON "
    "object with exactly the required keys, no markdown, no code fences, and no extra text."
)


def build_facts(
    *,
    crop: str,
    farm_id: str,
    zone_id: str,
    zone_label: str | None,
    fusion: ZoneFusionResult,
    risk: RiskAssessment,
    harvest: HarvestDecision,
    weather: dict[str, Any] | None = None,
    satellite: dict[str, Any] | None = None,
    crop_stage: str | None = None,
    heuristic_version: str = "heuristic-v0",
) -> dict[str, Any]:
    """The only thing a language model is ever shown."""
    status = harvest.status
    reason_codes = list(harvest.reason_codes) + list(risk.risk_codes)
    reason_codes = list(dict.fromkeys(reason_codes))
    return {
        "crop": crop,
        "farm_id": farm_id,
        "zone_id": zone_id,
        "zone_label": zone_label or zone_id,
        "status": status,
        "ripeness_status": harvest.ripeness_status,
        "ripeness_score": fusion.ripeness_score,
        "health_score": fusion.health_score,
        "health_status": risk.health_status,
        "risk_level": risk.risk_level,
        "confidence": fusion.confidence,
        "recommended_action": harvest.recommended_action,
        "reason_codes": reason_codes,
        "estimated_harvest_window": harvest.estimated_harvest_window,
        "days_to_harvest_min": harvest.days_to_harvest_min,
        "days_to_harvest_max": harvest.days_to_harvest_max,
        "estimated_yield_kg": None,
        "sources_used": list(fusion.sources_used),
        "missing_sources": list(fusion.missing_sources),
        "evidence_insufficient": fusion.evidence_insufficient,
        "crop_stage": crop_stage,
        "weather": weather or None,
        "satellite": satellite or None,
        "needs_local_confirmation": risk.needs_local_confirmation,
        "heuristic_version": heuristic_version,
        "heuristic_validated": False,
        "is_mock": bool(fusion.is_mock),
    }


class RecommendationService:
    """Generates one explainable recommendation for a zone."""

    def __init__(
        self,
        provider: Any | None = None,
        *,
        crop: str = "mango",
        heuristic_version: str = "heuristic-v0",
        translator: Callable[[str, str], str] | None = None,
        thresholds: ThresholdConfig | None = None,
    ) -> None:
        self._provider = provider
        self.crop = crop
        self.heuristic_version = heuristic_version
        self._translator = translator
        self._thresholds: ThresholdConfig = (
            thresholds if thresholds is not None else load_thresholds(crop)
        )

    @property
    def provider(self) -> Any:
        if self._provider is None:
            self._provider = build_recommendation_provider()
        return self._provider

    # -- public API --------------------------------------------------------
    def generate(
        self,
        *,
        farm_id: str,
        zone_id: str,
        zone_label: str | None,
        fusion: ZoneFusionResult,
        risk: RiskAssessment,
        harvest: HarvestDecision,
        weather: dict[str, Any] | None = None,
        satellite: dict[str, Any] | None = None,
        crop_stage: str | None = None,
        language: str = "en",
        tier: str | None = None,
    ) -> Recommendation:
        facts = build_facts(
            crop=self.crop,
            farm_id=farm_id,
            zone_id=zone_id,
            zone_label=zone_label,
            fusion=fusion,
            risk=risk,
            harvest=harvest,
            weather=weather,
            satellite=satellite,
            crop_stage=crop_stage,
            heuristic_version=self.heuristic_version,
        )
        return self.recommend_from_facts(
            facts, language=language, tier=tier, farm_id=farm_id, zone_id=zone_id
        )

    def recommend_from_facts(
        self,
        facts: dict[str, Any],
        *,
        language: str = "en",
        tier: str | None = None,
        farm_id: str | None = None,
        zone_id: str | None = None,
    ) -> Recommendation:
        facts = {**facts, "crop": facts.get("crop") or self.crop}
        farm_id = farm_id or str(facts.get("farm_id") or "unknown_farm")
        zone_id = zone_id or str(facts.get("zone_id") or "unknown_zone")

        requested_tier = resolve_tier(tier)
        degradation_reason: str | None = None
        output: GeminiRecommendationOutput | None = None
        parts: ExplainableParts | None = None
        used_tier = requested_tier

        if requested_tier != TIER_RULES_ONLY:
            output, parts, degradation_reason = self._call_model(
                facts, language=language, tier=requested_tier
            )
            if output is None:
                used_tier = TIER_RULES_ONLY
                logger.info(
                    "recommendation_degraded",
                    extra={
                        "farm_id": farm_id,
                        "zone_id": zone_id,
                        "language": language,
                        "requested_tier": requested_tier,
                        "reason": degradation_reason,
                    },
                )

        if output is None or parts is None:
            output = build_fallback_output(facts)
            parts = build_explainable_parts(facts)
            used_tier = TIER_RULES_ONLY
            degradation_reason = degradation_reason or "model_tier_unavailable"

        action = _action_code(output.recommended_action)
        # The rules layer owns the decision. If the model proposed a different
        # action, the rule decision wins and the difference is recorded.
        pipeline_action = facts.get("recommended_action")
        if pipeline_action:
            resolved_action = _action_code(str(pipeline_action))
            if resolved_action != action:
                notes = getattr(parts, "explanation", "")
                parts = parts.model_copy(
                    update={
                        "explanation": (
                            f"{notes} The model suggested {action} but the configured rules "
                            f"decide {resolved_action}, so {resolved_action} is reported."
                        )
                    }
                )
            action = resolved_action
        reason_codes = [str(item) for item in (facts.get("reason_codes") or [])]
        text = _text_from_parts(parts, language=language)
        translated = False

        if language and language != "en" and self._translator is not None:
            translated_text = self._safe_translate(text, language)
            if translated_text:
                text = translated_text
                translated = True
                parts = ExplainableParts(
                    evidence=self._safe_translate(parts.evidence, language) or parts.evidence,
                    inference=self._safe_translate(parts.inference, language) or parts.inference,
                    recommendation=(
                        self._safe_translate(parts.recommendation, language)
                        or parts.recommendation
                    ),
                    explanation=(
                        self._safe_translate(parts.explanation, language) or parts.explanation
                    ),
                )

        return Recommendation(
            recommendation_id=recommendation_id(farm_id, zone_id, language, facts),
            farm_id=farm_id,
            zone_id=zone_id,
            action=action,
            reason_codes=reason_codes,
            language=language,
            text=text,
            audio_uri=None,
            tier=used_tier,
            crop=str(facts.get("crop") or self.crop),
            parts=parts,
            evidence=list(output.evidence),
            confidence=output.confidence,
            language_translated=translated,
            risk_disclaimer=self._risk_disclaimer(facts),
            heuristic_version=self.heuristic_version,
            is_mock=bool(getattr(self.provider, "is_mock", False)) or bool(facts.get("is_mock")),
            is_fallback=used_tier == TIER_RULES_ONLY,
            degradation_reason=degradation_reason,
            model=str(getattr(self.provider, "name", "unknown")),
            created_at=utc_now_iso(),
        )

    def _risk_disclaimer(self, facts: dict[str, Any]) -> str:
        """Section 13.1: every recommendation carries its own guardrail text."""
        configured = str(self._thresholds.disclaimer or "").strip()
        if configured:
            return configured
        return (
            "Decision aid from heuristic v0 rules that are not yet validated against "
            "agronomist labels. Possible disease indicators require local confirmation."
        )

    # -- internals ---------------------------------------------------------
    def _call_model(
        self, facts: dict[str, Any], *, language: str, tier: str
    ) -> tuple[GeminiRecommendationOutput | None, ExplainableParts | None, str | None]:
        """Call the provider, validating the schema with one retry."""
        raw, error = _safe_generate(self.provider, facts, language=language, tier=tier)
        if error:
            return None, None, error
        output, validation_error = validate_gemini_output(parse_raw_output(raw))
        if output is not None:
            parts = build_explainable_parts(facts)
            parts = parts.model_copy(
                update={"explanation": output.explanation or parts.explanation}
            )
            return output, parts, None

        for _ in range(MAX_VALIDATION_RETRIES):
            retry_facts = {**facts, "_correction": CORRECTION_HINT}
            raw, error = _safe_generate(self.provider, retry_facts, language=language, tier=tier)
            if error:
                return None, None, f"schema_violation_then_{error}"
            output, validation_error = validate_gemini_output(parse_raw_output(raw))
            if output is not None:
                parts = build_explainable_parts(facts)
                parts = parts.model_copy(
                    update={"explanation": output.explanation or parts.explanation}
                )
                return output, parts, "schema_violation_recovered"

        return None, None, f"schema_violation_after_retries: {validation_error}"

    def _safe_translate(self, text: str, language: str) -> str:
        if not text or not self._translator:
            return ""
        try:
            return self._translator(text, language) or ""
        except Exception as exc:  # translation must never break a request
            logger.warning("recommendation_translation_failed", extra={"error": str(exc)})
            return ""


def _safe_generate(
    provider: Any, facts: dict[str, Any], *, language: str, tier: str
) -> tuple[Any, str | None]:
    try:
        return provider.generate(facts, language=language, tier=tier)
    except Exception as exc:  # provider bugs must not surface to farmers
        logger.error("recommendation_provider_raised", extra={"error": str(exc)})
        return None, f"provider_error: {exc}"


def _action_code(recommended_action: str) -> str:
    value = str(recommended_action or "").strip()
    if value.upper() in ACTION_TEXT:
        return value.upper()
    return {
        "prioritize_harvest": "PRIORITIZE_HARVEST",
        "monitor_and_prepare": "MONITOR_AND_PREPARE",
        "continue_monitoring": "CONTINUE_MONITORING",
        "inspect_zone": "INSPECT_ZONE",
        "hold_and_revalidate": "HOLD_AND_REVALIDATE",
    }.get(value.lower(), "CONTINUE_MONITORING")


def _text_from_parts(parts: ExplainableParts, *, language: str) -> str:
    return build_fallback_text(parts, language=language)


def recommendation_id(
    farm_id: str, zone_id: str, language: str, facts: dict[str, Any]
) -> str:
    """Stable id so re-running the analysis does not duplicate documents."""
    seed = stable_seed(f"{farm_id}|{zone_id}|{language}|{json.dumps(facts, sort_keys=True, default=str)}")
    return f"rec_{zone_id}_{seed & 0xFFFFFFFF:08x}"


__all__ = [
    "CORRECTION_HINT",
    "MAX_VALIDATION_RETRIES",
    "RecommendationService",
    "build_facts",
    "recommendation_id",
]
