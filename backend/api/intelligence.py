"""Image analysis, voice query and recommendation endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status

from backend.api.deps import assert_farm_access
from backend.container import Container, get_container
from backend.core.auth import require_farmer
from backend.multilingual.intent import normalize_language, parse_intent
from backend.observations.service import decode_base64
from backend.schemas import (
    ImageAnalysisRequest,
    ImageAnalysisResponse,
    RecommendationListResponse,
    VoiceQueryRequest,
    VoiceQueryResponse,
    ZoneResult,
)

router = APIRouter(prefix="/farms/{farm_id}", tags=["intelligence"])

ContainerDep = Annotated[Container, Depends(get_container)]
UserDep = Annotated[Any, Depends(require_farmer)]


@router.post("/image-analysis", response_model=ImageAnalysisResponse)
def image_analysis(
    farm_id: str,
    payload: ImageAnalysisRequest,
    container: ContainerDep,
    user: UserDep,
) -> ImageAnalysisResponse:
    """Perception for one image, optionally saved as an observation.

    The image is scored by the CV models only. No Gemini call happens here:
    perception is never delegated to a language model.
    """
    farm = assert_farm_access(container, farm_id, user)
    zone_id = payload.zone_id
    if zone_id:
        container.farms.get_zone(farm_id, zone_id)

    observation: dict[str, Any] | None = None
    if payload.image_base64 or payload.image_reference:
        observation = container.observations.create_observation(
            farm_id,
            {
                "source": payload.source,
                "zone_id": zone_id,
                "image_base64": payload.image_base64,
                "image_reference": payload.image_reference,
                "mime_type": payload.mime_type,
            },
            owner_uid=user.uid,
            persist=payload.save,
        )

    if observation is None and not payload.image_reference:
        raise ValueError("Provide image_base64 or image_reference.")

    result = container.orchestrator.analyze_observation(farm, observation)
    if not result.get("accepted", True):
        # Section 8.3: a photo that cannot be used evidence is a 422 with an
        # explicit retake instruction, not a 200 with empty scores.
        _raise_rejection(result)
    return ImageAnalysisResponse(
        observation_id=result.get("observation_id") if payload.save else None,
        zone_id=result.get("zone_id"),
        source=result.get("source", payload.source),
        fruit_count=int(result.get("fruit_count") or 0),
        detection_confidence=float(result.get("detection_confidence") or 0.0),
        ripeness_score=result.get("ripeness_score"),
        ripeness_label=result.get("ripeness_label"),
        health_score=result.get("health_score"),
        health_label=result.get("health_label"),
        possible_health_indicators=list(result.get("possible_health_indicators") or []),
        image_quality=result.get("image_quality") or {},
        accepted=bool(result.get("accepted", False)),
        rejection_reason=result.get("rejection_reason"),
        recommendation=result.get("recommendation"),
        is_mock=bool(result.get("is_mock", False)),
        notes=list(result.get("notes") or []),
    )


@router.post("/voice-query", response_model=VoiceQueryResponse)
def voice_query(
    farm_id: str,
    payload: VoiceQueryRequest,
    container: ContainerDep,
    user: UserDep,
) -> VoiceQueryResponse:
    """Tamil-first voice path: STT -> intent -> analysis -> translation -> TTS.

    Accepts raw ``audio_base64`` or plain ``text``. Every step degrades
    gracefully, so a mock STT or a missing TTS key still returns an answer.
    """
    farm = assert_farm_access(container, farm_id, user)
    language = normalize_language(payload.language)

    if payload.audio_base64:
        result = container.multilingual.handle_voice_query(
            decode_base64(payload.audio_base64),
            language=language,
            mime_type=payload.mime_type,
            synthesize=payload.synthesize,
        )
    elif payload.text:
        result = container.multilingual.handle_text_query(payload.text, language=language)
    else:
        raise ValueError("Provide audio_base64 or text.")

    zone_result: dict[str, Any] | None = None
    recommendation: dict[str, Any] | None = None

    zone_id = payload.zone_id or result.zone_id
    if zone_id is None and result.intent.zone_label:
        try:
            zone = container.farms.resolve_zone(farm_id, zone_label=result.intent.zone_label)
            zone_id = str(zone["zone_id"])
        except Exception:  # unknown label: fall through to clarification
            zone_id = None
    elif zone_id is None and result.intent.zone_id:
        try:
            container.farms.get_zone(farm_id, result.intent.zone_id)
            zone_id = result.intent.zone_id
        except Exception:
            zone_id = None

    if zone_id and result.intent.intent != "unknown" and not result.clarification:
        run = container.orchestrator.analyze_farm(
            farm, zone_ids=[zone_id], language=language, tier=payload.tier
        )
        if run.zones:
            zone_result = run.zones[0].result
            recommendation = run.zones[0].recommendation

    answer = _answer_text(zone_result, result.clarification)
    localized = container.multilingual.localize(result, answer, target_language=language)

    return VoiceQueryResponse(
        transcript=localized.transcript,
        language=localized.language,
        intent=localized.intent.to_dict(),
        answer_text=localized.answer_text,
        answer_language=localized.answer_language,
        audio_uri=localized.audio_uri,
        zone_id=zone_result.get("zone_id") if zone_result else localized.zone_id,
        zone_label=zone_result.get("zone_label") if zone_result else localized.zone_label,
        translation=localized.translation,
        speech=localized.speech,
        clarification=localized.clarification,
        zone_result=ZoneResult.model_validate(zone_result) if zone_result else None,
        recommendation=recommendation,
        warnings=list(localized.warnings),
        is_mock=bool(localized.is_mock or (zone_result or {}).get("is_mock", False)),
        degraded=bool(localized.degraded),
    )


@router.get("/recommendations", response_model=RecommendationListResponse)
def list_recommendations(
    farm_id: str,
    container: ContainerDep,
    user: UserDep,
    zone_id: str | None = Query(default=None, pattern=r"^zone_\d{2,}$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> RecommendationListResponse:
    assert_farm_access(container, farm_id, user)
    recommendations = container.repository.list_recommendations(
        farm_id, zone_id=zone_id, limit=limit
    )
    return RecommendationListResponse(
        recommendations=recommendations, count=len(recommendations)
    )


def _raise_rejection(result: dict[str, Any]) -> None:
    """Turn a structured perception rejection into the documented 422."""
    from backend.core.errors import ErrorCode, ImageQualityError, ImageUnreadableError

    reason = str(result.get("rejection_reason") or "unusable_image")
    message = str(result.get("rejection_message") or "The image could not be used.")
    if reason == ErrorCode.IMAGE_QUALITY_FAILED:
        details = result.get("rejection_details") or {}
        raise ImageQualityError(
            message,
            reason=str(details.get("reason") or reason.lower()),
            remedy=str(
                details.get("remedy")
                or "Please retake the photo: hold the phone steady, fill the frame with fruit, and avoid harsh backlight."
            ),
            metrics=details.get("metrics") or {},
        )
    raise ImageUnreadableError(
        f"{message} Please retake the photo or upload a different image."
    )


def _answer_text(zone_result: dict[str, Any] | None, clarification: str | None) -> str:
    if clarification:
        return clarification
    if not zone_result:
        return "I could not match that to a zone. Please say the zone name or number."
    label = zone_result.get("zone_label") or zone_result.get("zone_id")
    status_value = str(zone_result.get("status", "NO_DATA")).replace("_", " ").lower()
    window = zone_result.get("estimated_harvest_window")
    parts = [f"Zone {label} is {status_value}"]
    if window:
        parts.append(f"the estimated harvest window is {window}")
    if zone_result.get("risk_level") in {"medium", "high"}:
        parts.append(
            "the risk level is "
            f"{zone_result['risk_level']}, so please inspect the zone on the ground"
        )
    if zone_result.get("ripeness_score") is None:
        parts.append("no ripeness evidence is available yet, so please send a close-up photo")
    parts.append("this is a decision aid from heuristic rules, not an agronomic guarantee")
    return ", ".join(parts) + "."


__all__ = ["router"]
