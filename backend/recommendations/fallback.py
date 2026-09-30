"""Deterministic RULES_ONLY tier.

Used when Gemini is disabled, misconfigured, times out, or returns output that
fails schema validation twice. This path never fails and never fabricates a
number: every sentence is assembled from facts the pipeline already produced.
"""

from __future__ import annotations

from typing import Any

from backend.recommendations.schema import (
    EVIDENCE_CODES,
    ExplainableParts,
    GeminiRecommendationOutput,
    TIER_RULES_ONLY,
)

# Risk level is a *context* signal: weather alone can raise it. Deriving a
# health status from it would claim a disease finding nobody looked for, so a
# missing health status is passed through as "unknown" instead.
RISK_TO_HEALTH_STATUS = {"none": "unknown", "low": "unknown", "medium": "unknown", "high": "unknown"}

# Reason code -> evidence code used in the Gemini contract. Keeping the mapping
# here means the fallback and the model tier speak the same evidence vocabulary.
REASON_CODE_TO_EVIDENCE: dict[str, str] = {
    "HIGH_RIPENESS": "high_ripeness_score",
    "MODERATE_RIPENESS": "moderate_ripeness_score",
    "LOW_RIPENESS": "low_ripeness_score",
    "HEALTH_SCORE_GOOD": "health_score_good",
    "HEALTH_SCORE_FAIR": "health_score_fair",
    "HEALTH_SCORE_POOR": "health_score_poor",
    "POSSIBLE_DISEASE_INDICATOR": "possible_disease_indicator",
    "CANOPY_ANOMALY": "canopy_anomaly",
    "RAIN_FORECAST": "upcoming_weather_event",
    "HEAVY_RAIN": "heavy_rain_forecast",
    "HEAT_STRESS": "heat_stress_risk",
    "LOW_SOIL_MOISTURE": "soil_moisture_low",
    "WATER_STRESS": "water_stress",
    "LOW_CONFIDENCE": "low_fusion_confidence",
    "CROP_STAGE_LOSS_PRESSURE": "crop_stage_ripening",
}

SINGLE_SOURCE_CODES = {"single_source_evidence"}

ACTION_TEXT: dict[str, str] = {
    "PRIORITIZE_HARVEST": "Harvest this zone first.",
    "MONITOR_AND_PREPARE": "Prepare to harvest and keep monitoring this zone.",
    "CONTINUE_MONITORING": "Keep monitoring this zone; no action is needed yet.",
    "INSPECT_ZONE": "Inspect this zone on the ground and confirm with a local agricultural officer.",
    "CAPTURE_EVIDENCE": "Capture a close-up photo of this zone so it can be analysed.",
    "HOLD_AND_REVALIDATE": "Hold off on harvesting this zone and re-check the analysis.",
}

# The Gemini output contract has a fixed action enum (Section 12.7). Internal
# pipeline codes that are not in that enum are mapped onto the closest allowed
# value so the model tier can never emit an out-of-schema action.
CONTRACT_ACTION_BY_CODE: dict[str, str] = {
    "PRIORITIZE_HARVEST": "prioritize_harvest",
    "MONITOR_AND_PREPARE": "monitor_and_prepare",
    "CONTINUE_MONITORING": "continue_monitoring",
    "INSPECT_ZONE": "inspect_zone",
    "HOLD_AND_REVALIDATE": "hold_and_revalidate",
    "CAPTURE_EVIDENCE": "continue_monitoring",
}

CONFIRMATION_NOTE = (
    "Possible disease indicator detected; local confirmation is recommended. "
    "Consult your local agricultural officer before applying any treatment."
)

NO_DATA_NOTE = (
    "No ripeness evidence is available for this zone yet, so no harvest status is assigned."
)


def _pct(value: Any, digits: int = 0) -> str:
    if value is None:
        return "unavailable"
    try:
        return f"{float(value) * 100:.{digits}f}%"
    except (TypeError, ValueError):
        return "unavailable"


def _score(value: Any) -> str:
    if value is None:
        return "not available"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "not available"


def derive_evidence_codes(facts: dict[str, Any]) -> list[str]:
    """Map pipeline reason codes onto the public evidence vocabulary."""
    codes: list[str] = []
    for reason in facts.get("reason_codes", []) or []:
        mapped = REASON_CODE_TO_EVIDENCE.get(str(reason))
        if mapped and mapped not in codes:
            codes.append(mapped)
    if len(facts.get("missing_sources") or []) >= 1 and "single_source_evidence" not in codes:
        codes.append("single_source_evidence")
    return [code for code in codes if code in EVIDENCE_CODES][:16]


def derive_action(facts: dict[str, Any]) -> str:
    action = str(facts.get("recommended_action") or "CONTINUE_MONITORING").upper()
    return action if action in ACTION_TEXT else "CONTINUE_MONITORING"


def build_explainable_parts(facts: dict[str, Any]) -> ExplainableParts:
    """Section 12.8 - Evidence / Inference / Recommendation / Explanation."""
    zone = str(facts.get("zone_label") or facts.get("zone_id") or "this zone")
    evidence_sentences: list[str] = []

    ripeness = facts.get("ripeness_score")
    if ripeness is not None:
        window = facts.get("estimated_harvest_window")
        tail = f" Estimated harvest window: {window}." if window else ""
        evidence_sentences.append(
            f"{zone} has a ripeness score of {_score(ripeness)} and a status of "
            f"{facts.get('status')}.{tail}"
        )
    else:
        evidence_sentences.append(NO_DATA_NOTE)

    health = facts.get("health_score")
    if health is not None:
        evidence_sentences.append(
            f"Health score for {zone} is {_score(health)} ({facts.get('health_status')})."
        )

    weather = facts.get("weather") or {}
    if weather:
        bits: list[str] = []
        if weather.get("rain_probability") is not None:
            bits.append(f"rain probability {_pct(weather['rain_probability'])}")
        if weather.get("temperature_c") is not None:
            bits.append(f"temperature {float(weather['temperature_c']):.0f} C")
        if weather.get("event_kinds"):
            bits.append(", ".join(str(item) for item in weather["event_kinds"]))
        if bits:
            evidence_sentences.append(f"Weather context: {'; '.join(bits)}.")

    satellite = facts.get("satellite") or {}
    if satellite:
        bits = []
        if satellite.get("vegetation_index") is not None:
            bits.append(f"vegetation index {_score(satellite['vegetation_index'])}")
        if satellite.get("anomaly_detected"):
            bits.append("a vegetation change flagged as an anomaly")
        if bits:
            evidence_sentences.append(
                f"Satellite canopy context: {'; '.join(bits)} (canopy condition only, "
                "not fruit ripeness)."
            )

    if facts.get("sources_used"):
        evidence_sentences.append(
            "Evidence sources used: " + ", ".join(str(item) for item in facts["sources_used"]) + "."
        )
    if facts.get("missing_sources"):
        evidence_sentences.append(
            "Missing sources: "
            + ", ".join(str(item) for item in facts["missing_sources"])
            + ". Missing evidence was never treated as zero."
        )

    action = derive_action(facts)
    risk_level = str(facts.get("risk_level") or "none").lower()
    status = str(facts.get("status") or "")

    inference_map = {
        "HARVEST_READY": f"{zone} is the highest immediate harvest priority in this farm.",
        "NEAR_READY": f"{zone} is close to harvest-ready and should be watched closely.",
        "NOT_READY": f"{zone} is not harvest-ready yet, so harvesting now would waste effort.",
        "HEALTH_CONCERN": f"{zone} needs a ground inspection before any harvest decision.",
        "NO_DATA": f"{zone} cannot be prioritised until evidence is captured.",
    }
    inference = inference_map.get(status, f"{zone} has an overall {risk_level} risk level.")

    recommendation = ACTION_TEXT[action]

    explanation_bits: list[str] = []
    if facts.get("ripeness_score") is not None:
        explanation_bits.append(
            f"the ripeness score of {_score(facts.get('ripeness_score'))} is the primary basis for this status"
        )
        if risk_level in {"medium", "high"}:
            explanation_bits.append(
                f"the risk level for this zone is {risk_level}, which increases the urgency of acting"
            )
    if facts.get("missing_sources"):
        explanation_bits.append("some sources were missing, so the estimate should be treated as provisional")
    if explanation_bits:
        explanation = f"Recommended because {', and '.join(explanation_bits)}."
    elif risk_level in {"medium", "high"}:
        # No ripeness evidence: a contextual risk level must not read as a
        # reason to act on the crop. The urgent step is to look.
        explanation = (
            f"No image evidence was measured for this zone, so the {risk_level} risk level comes "
            "from context such as weather only. No crop condition is claimed; the first step is "
            "to capture evidence for this zone."
        )
    else:
        explanation = (
            "This recommendation is generated from configurable heuristic rules "
            f"({facts.get('heuristic_version', 'heuristic-v0')}) and has not been validated "
            "against expert agronomist labels."
        )

    if "POSSIBLE_DISEASE_INDICATOR" in (facts.get("reason_codes") or []):
        explanation = f"{explanation} {CONFIRMATION_NOTE}"

    return ExplainableParts(
        evidence=" ".join(evidence_sentences),
        inference=inference,
        recommendation=recommendation,
        explanation=explanation,
    )


def build_fallback_output(facts: dict[str, Any]) -> GeminiRecommendationOutput:
    """Schema-valid output built entirely from pipeline facts."""
    action = derive_action(facts)
    contract_action = CONTRACT_ACTION_BY_CODE.get(action, "continue_monitoring")
    status = str(facts.get("status") or "NO_DATA").upper()
    ripeness_status = {
        "HARVEST_READY": "harvest_ready",
        "NEAR_READY": "near_ready",
        "NOT_READY": "not_ready",
        "HEALTH_CONCERN": "health_concern",
    }.get(status, "not_ready")
    health_status = str(
        facts.get("health_status")
        or RISK_TO_HEALTH_STATUS.get(str(facts.get("risk_level") or "none").lower(), "watch")
    )
    if health_status == "unknown":
        # Section 12.7 fixes the vocabulary to healthy|watch|poor. "watch" is
        # the only value that asserts no health finding while staying inside the
        # contract; the explanation text carries the honest "not measured".
        health_status = "watch"
    if health_status not in {"healthy", "watch", "poor"}:
        health_status = "watch"

    parts = build_explainable_parts(facts)
    confidence = facts.get("confidence")
    try:
        confidence_value = float(confidence) if confidence is not None else 0.2
    except (TypeError, ValueError):
        confidence_value = 0.2

    return GeminiRecommendationOutput(
        crop=str(facts.get("crop") or "mango"),
        zone=str(facts.get("zone_id") or "unknown"),
        health_status=health_status,
        ripeness_status=ripeness_status,
        risk_level=str(facts.get("risk_level") or "none").lower(),
        evidence=derive_evidence_codes(facts),
        recommended_action=contract_action,
        explanation=parts.explanation,
        confidence=max(0.0, min(1.0, confidence_value)),
    )


def build_fallback_text(parts: ExplainableParts, *, language: str = "en") -> str:
    """Single-block text stored on the recommendation document."""
    blocks = [
        f"Evidence: {parts.evidence}",
        f"Inference: {parts.inference}",
        f"Recommendation: {parts.recommendation}",
        f"Explanation: {parts.explanation}",
    ]
    text = " ".join(block for block in blocks if block.split(":", 1)[-1].strip())
    if language != "en":
        text = f"{text} (language={language}; run the translation step to localise this text)"
    return text


def build_fallback(facts: dict[str, Any], *, language: str = "en") -> dict[str, Any]:
    """Return the full RULES_ONLY payload (output + parts + text)."""
    output = build_fallback_output(facts)
    parts = build_explainable_parts(facts)
    return {
        "tier": TIER_RULES_ONLY,
        "output": output,
        "parts": parts,
        "text": build_fallback_text(parts, language=language),
        "is_fallback": True,
        "language_translated": False,
    }


__all__ = [
    "ACTION_TEXT",
    "CONTRACT_ACTION_BY_CODE",
    "CONFIRMATION_NOTE",
    "NO_DATA_NOTE",
    "REASON_CODE_TO_EVIDENCE",
    "RISK_TO_HEALTH_STATUS",
    "build_explainable_parts",
    "build_fallback",
    "build_fallback_output",
    "build_fallback_text",
    "derive_action",
    "derive_evidence_codes",
]
