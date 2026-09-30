"""Recommendation contract: schema, tiers, fallback, and the rules-owns-action rule."""

from __future__ import annotations

import json

import pytest

from backend.recommendations.fallback import ACTION_TEXT, build_fallback, build_fallback_output
from backend.recommendations.prompt import load_prompt_config, resolve_tier
from backend.recommendations.schema import (
    GEMINI_RESPONSE_SCHEMA,
    TIER_GEMINI,
    TIER_GEMINI_SIMPLIFIED,
    TIER_RULES_ONLY,
    GeminiRecommendationOutput,
    validate_gemini_output,
)

from backend.fusion.models import ZoneFusionResult
from backend.harvest.engine import HarvestDecision
from backend.risk.engine import RiskAssessment

FACTS = {
    "crop": "mango",
    "zone_id": "zone_07",
    "zone_label": "G",
    "crop_stage": "fruit_development",
    "ripeness_score": 0.78,
    "health_score": 0.86,
    "status": "HARVEST_READY",
    "ripeness_status": "HARVEST_READY",
    "health_status": "healthy",
    "risk_level": "none",
    "estimated_harvest_window": "1-3 days",
    "days_to_harvest_min": 1,
    "days_to_harvest_max": 3,
    "sources_used": ["phone", "drone"],
    "missing_sources": [],
    "fusion_confidence": 0.82,
    "recommended_action": "PRIORITIZE_HARVEST",
    "reason_codes": ["HIGH_RIPENESS"],
    "language": "en",
}


def test_section_12_7_contract_is_exact() -> None:
    model, error = validate_gemini_output(
        {
            "crop": "mango",
            "zone": "zone_07",
            "health_status": "healthy",
            "ripeness_status": "harvest_ready",
            "risk_level": "medium",
            "evidence": ["high_ripeness_score", "upcoming_weather_event"],
            "recommended_action": "prioritize_harvest",
            "explanation": "Zone 7 has the highest ripeness signal and rain is forecast soon.",
            "confidence": 0.84,
        }
    )
    assert error is None
    assert isinstance(model, GeminiRecommendationOutput)
    assert model.zone == "zone_07"
    assert model.confidence == pytest.approx(0.84)


@pytest.mark.parametrize(
    "mutation",
    [
        {"health_status": "excellent"},          # not in the enum
        {"ripeness_status": "ripe"},             # not in the enum
        {"risk_level": "catastrophic"},
        {"recommended_action": "spray_everything"},  # free-form intervention
        {"evidence": ["made_up_evidence_code"]},
        {"confidence": 1.4},
        {"extra_field": "surprise"},              # extra="forbid"
    ],
)
def test_contract_violations_are_rejected(mutation: dict) -> None:
    payload = {
        "crop": "mango",
        "zone": "zone_07",
        "health_status": "healthy",
        "ripeness_status": "harvest_ready",
        "risk_level": "none",
        "evidence": [],
        "recommended_action": "continue_monitoring",
        "explanation": "Looks fine.",
        "confidence": 0.6,
    }
    payload.update(mutation)
    model, error = validate_gemini_output(payload)
    assert model is None
    assert error


def test_json_string_output_is_parsed() -> None:
    model, error = validate_gemini_output(
        json.dumps(
            {
                "crop": "mango",
                "zone": "zone_01",
                "health_status": "watch",
                "ripeness_status": "near_ready",
                "risk_level": "low",
                "evidence": ["moderate_ripeness_score"],
                "recommended_action": "monitor_and_prepare",
                "explanation": "Close to ready.",
                "confidence": 0.55,
            }
        )
    )
    assert error is None and model is not None


def test_tiers_are_resolved_from_the_configuration() -> None:
    assert resolve_tier(TIER_RULES_ONLY) == TIER_RULES_ONLY
    assert resolve_tier(TIER_GEMINI) == TIER_GEMINI
    # A simplified request never silently escalates to the full tier.
    assert resolve_tier(TIER_GEMINI_SIMPLIFIED) == TIER_GEMINI_SIMPLIFIED
    # An unknown tier falls back to the richest one, never to an invented tier.
    assert resolve_tier("NOT_A_TIER") == TIER_GEMINI
    assert resolve_tier(None) == TIER_GEMINI


def test_fallback_never_invents_an_action() -> None:
    output = build_fallback_output(FACTS)
    # The fallback speaks the Section 12.7 contract vocabulary, which is
    # lowercase and closed; the pipeline's own codes are mapped onto it.
    assert output.recommended_action == "prioritize_harvest"
    assert output.zone == "zone_07"
    assert output.explanation


def test_contract_actions_map_onto_the_pipeline_codes() -> None:
    from backend.recommendations.fallback import CONTRACT_ACTION_BY_CODE

    assert CONTRACT_ACTION_BY_CODE["PRIORITIZE_HARVEST"] == "prioritize_harvest"
    # CAPTURE_EVIDENCE is not in the contract enum, so it degrades to the
    # closest allowed value; the farmer-facing text still asks for a photo.
    assert CONTRACT_ACTION_BY_CODE["CAPTURE_EVIDENCE"] == "continue_monitoring"
    assert "photo" in ACTION_TEXT["CAPTURE_EVIDENCE"].lower()


def test_fallback_explains_a_missing_ripeness_score() -> None:
    facts = dict(
        FACTS,
        ripeness_score=None,
        status="NO_DATA",
        ripeness_status=None,
        recommended_action="CAPTURE_EVIDENCE",
        reason_codes=["NO_RIPENESS_EVIDENCE"],
    )
    output = build_fallback_output(facts)
    assert output.recommended_action == "continue_monitoring"
    assert output.ripeness_status is None or output.ripeness_status == "not_ready"
    payload = build_fallback(facts)
    text = payload["text"].lower()
    assert "evidence" in text or "photo" in text
    assert payload["parts"].recommendation == ACTION_TEXT["CAPTURE_EVIDENCE"]


def test_disease_wording_is_never_a_diagnosis() -> None:
    facts = dict(
        FACTS,
        health_score=0.30,
        health_status="poor",
        risk_level="high",
        status="HEALTH_CONCERN",
        reason_codes=["POSSIBLE_DISEASE_INDICATOR"],
        recommended_action="INSPECT_ZONE",
    )
    output = build_fallback_output(facts)
    text = output.explanation.lower()
    assert "possible" in text
    assert "confirm" in text or "inspection" in text or "inspect" in text
    for forbidden in ("diagnosed", "diagnosis of", "confirmed disease", "has disease"):
        assert forbidden not in text


def test_prompt_never_delegates_perception_or_decisions() -> None:
    rendered = (load_prompt_config()["system_prompt"] or "").lower()
    assert "ripeness" in rendered
    # Perception is CV-only and decisions are rules-only; the prompt has to say so.
    assert "perception system" in rendered and "decision system" in rendered
    assert "rules" in rendered
    for forbidden in ("you are an image", "look at the image", "decide the status"):
        assert forbidden not in rendered


def test_service_returns_a_valid_recommendation_in_mock_mode(container, farm) -> None:
    fusion = ZoneFusionResult(
        zone_id="zone_07",
        ripeness_score=0.78,
        health_score=0.86,
        confidence=0.82,
        sources_used=["phone"],
        context_sources_used=["satellite"],
        missing_sources=["drone"],
        evidence_insufficient=False,
        contributions={},
        is_mock=True,
    )
    risk = RiskAssessment(
        risk_level="none",
        risk_codes=[],
        evidence=[],
        confidence=0.7,
        health_status="healthy",
    )
    decision = HarvestDecision(
        status="HARVEST_READY",
        ripeness_status="HARVEST_READY",
        health_concern=False,
        estimated_harvest_window="1-3 days",
        days_to_harvest_min=1,
        days_to_harvest_max=3,
        recommended_action="PRIORITIZE_HARVEST",
        reason_codes=["HIGH_RIPENESS"],
        status_label="Harvest ready",
    )
    recommendation = container.orchestrator.recommendations.generate(
        farm_id=farm["farm_id"],
        zone_id="zone_07",
        zone_label="G",
        fusion=fusion,
        risk=risk,
        harvest=decision,
        language="en",
    )
    assert recommendation.action == "PRIORITIZE_HARVEST"  # the rules own the action
    assert recommendation.risk_disclaimer
    assert recommendation.parts.evidence and recommendation.parts.recommendation
    assert recommendation.zone_id == "zone_07"
    # The recommendation never claims ripeness came from satellite.
    assert "satellite" not in recommendation.text.lower()


def test_gemini_is_constrained_by_the_section_12_7_schema() -> None:
    """The schema sent to Gemini is derived from the validating model.

    A hand-maintained copy would drift, and the model would then be asked for a
    shape the pipeline rejects.
    """
    assert GEMINI_RESPONSE_SCHEMA["additionalProperties"] is False
    properties = GEMINI_RESPONSE_SCHEMA["properties"]
    assert set(properties) == set(GeminiRecommendationOutput.model_fields)
    for field in ("health_status", "ripeness_status", "risk_level"):
        assert "enum" in properties[field], field
    assert properties["confidence"]["type"] == "number"
    for required in ("crop", "zone", "explanation", "confidence", "recommended_action"):
        assert required in GEMINI_RESPONSE_SCHEMA["required"]
    # Optional in the model, so optional in the contract too.
    assert "evidence" not in GEMINI_RESPONSE_SCHEMA["required"]
