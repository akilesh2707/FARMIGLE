"""Voice/text query orchestration (M12).

Tamil-first path::

    speech bytes -> STT -> intent -> analysis -> recommendation
                 -> translation -> TTS -> {text, audio_uri}

Every step degrades instead of failing: an STT error returns a clarifying
question, a translation error returns the English text, a TTS error returns
text with ``audio_uri = null``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from backend.multilingual.intent import (
    CLARIFYING_QUESTIONS,
    INTENT_HARVEST_MAP,
    INTENT_HEALTH,
    INTENT_RECOMMENDATION,
    INTENT_STATUS,
    FALLBACK_LANGUAGE,
    IntentResult,
    normalize_language,
    parse_intent,
)
from backend.multilingual.providers import (
    SpeechSynthesisResult,
    TranscriptionResult,
    TranslationResult,
    build_speech_to_text,
    build_text_to_speech,
    build_translation,
)

logger = logging.getLogger(__name__)

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB, matches Cloud Speech v1 sync limit


@dataclass
class VoiceQueryResult:
    transcript: str
    language: str
    intent: IntentResult
    answer_text: str
    answer_language: str
    audio_uri: str | None = None
    zone_id: str | None = None
    zone_label: str | None = None
    translation: dict[str, Any] | None = None
    speech: dict[str, Any] | None = None
    clarification: str | None = None
    warnings: list[str] = field(default_factory=list)
    is_mock: bool = False
    degraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "transcript": self.transcript,
            "language": self.language,
            "intent": self.intent.to_dict(),
            "answer_text": self.answer_text,
            "answer_language": self.answer_language,
            "audio_uri": self.audio_uri,
            "zone_id": self.zone_id,
            "zone_label": self.zone_label,
            "translation": self.translation,
            "speech": self.speech,
            "clarification": self.clarification,
            "warnings": list(self.warnings),
            "is_mock": self.is_mock,
            "degraded": self.degraded,
        }


class MultilingualService:
    """Speech-to-text, translation and text-to-speech in one place."""

    def __init__(
        self,
        *,
        speech_to_text: Any | None = None,
        translation: Any | None = None,
        text_to_speech: Any | None = None,
    ) -> None:
        self._stt = speech_to_text
        self._translate = translation
        self._tts = text_to_speech

    @property
    def speech_to_text(self) -> Any:
        if self._stt is None:
            self._stt = build_speech_to_text()
        return self._stt

    @property
    def translation(self) -> Any:
        if self._translate is None:
            self._translate = build_translation()
        return self._translate

    @property
    def text_to_speech(self) -> Any:
        if self._tts is None:
            self._tts = build_text_to_speech()
        return self._tts

    # -- text path ---------------------------------------------------------
    def handle_text_query(self, text: str, *, language: str | None = None) -> VoiceQueryResult:
        """Non-voice entry point: same downstream behaviour, no STT."""
        return self._answer_from_transcript(
            TranscriptionResult(
                text=(text or "").strip(),
                language=normalize_language(language),
                confidence=1.0,
            )
        )

    # -- voice path --------------------------------------------------------
    def handle_voice_query(
        self,
        audio_bytes: bytes,
        *,
        language: str | None = None,
        mime_type: str = "audio/webm",
        synthesize: bool = True,
    ) -> VoiceQueryResult:
        if not audio_bytes:
            transcription = TranscriptionResult(
                text="", language=normalize_language(language), error="empty_audio"
            )
        elif len(audio_bytes) > MAX_AUDIO_BYTES:
            transcription = TranscriptionResult(
                text="",
                language=normalize_language(language),
                error="audio_too_large",
            )
        else:
            transcription = _safe_call(
                self.speech_to_text.transcribe,
                audio_bytes,
                default=TranscriptionResult(
                    text="", language=normalize_language(language), error="stt_unavailable"
                ),
                language=normalize_language(language),
                mime_type=mime_type,
            )

        result = self._answer_from_transcript(transcription)
        if synthesize and result.answer_text:
            self._attach_speech(result)
        return result

    # -- helpers -----------------------------------------------------------
    def _answer_from_transcript(self, transcription: TranscriptionResult) -> VoiceQueryResult:
        language = normalize_language(transcription.language)
        warnings: list[str] = []
        degraded = False

        if transcription.error:
            degraded = True
            warnings.append(transcription.error)
            intent = IntentResult(
                intent="unknown",
                language=language,
                needs_clarification=True,
                clarification_question=CLARIFYING_QUESTIONS[language],
                raw_text="",
            )
            answer = CLARIFYING_QUESTIONS[language]
            return VoiceQueryResult(
                transcript=transcription.text,
                language=language,
                intent=intent,
                answer_text=answer,
                answer_language=language,
                clarification=answer,
                warnings=warnings,
                degraded=True,
                is_mock=bool(transcription.is_mock),
            )

        intent = parse_intent(transcription.text, language=language)
        if intent.needs_clarification:
            answer = intent.clarification_question or CLARIFYING_QUESTIONS[language]
            return VoiceQueryResult(
                transcript=transcription.text,
                language=language,
                intent=intent,
                answer_text=answer,
                answer_language=language,
                clarification=answer,
                warnings=warnings,
                degraded=False,
                is_mock=bool(transcription.is_mock),
            )

        return VoiceQueryResult(
            transcript=transcription.text,
            language=language,
            intent=intent,
            answer_text="",  # filled in by the analysis layer via `build_answer`
            answer_language=language,
            zone_id=intent.zone_id,
            zone_label=intent.zone_label,
            warnings=warnings,
            degraded=degraded,
            is_mock=bool(transcription.is_mock),
        )

    def localize(self, result: VoiceQueryResult, text: str, *, target_language: str | None = None) -> VoiceQueryResult:
        """Attach a localized answer (and audio) to a resolved query."""
        target = normalize_language(target_language or result.language)
        english = text
        result.answer_text = english
        result.answer_language = FALLBACK_LANGUAGE
        result.warnings = list(result.warnings)

        if target != FALLBACK_LANGUAGE:
            translation: TranslationResult = _safe_call(
                self.translation.translate,
                english,
                default=TranslationResult(
                    text="",
                    source_language=FALLBACK_LANGUAGE,
                    target_language=target,
                    error="translation_unavailable",
                ),
                target_language=target,
                source_language=FALLBACK_LANGUAGE,
            )
            result.translation = translation.to_dict()
            if translation.ok:
                result.answer_text = translation.text
                result.answer_language = target
            else:
                result.degraded = True
                if translation.error:
                    result.warnings.append(translation.error)

        self._attach_speech(result)
        return result

    def _attach_speech(self, result: VoiceQueryResult) -> None:
        if not result.answer_text or result.speech is not None:
            return
        synthesis: SpeechSynthesisResult = _safe_call(
            self.text_to_speech.synthesize,
            result.answer_text,
            default=SpeechSynthesisResult(
                audio_uri=None,
                language=result.answer_language,
                voice="",
                error="tts_unavailable",
            ),
            language=result.answer_language,
        )
        result.speech = synthesis.to_dict()
        result.audio_uri = synthesis.audio_uri
        if synthesis.is_mock:
            result.is_mock = True
        if synthesis.error and not synthesis.is_mock:
            result.degraded = True
        if synthesis.error:
            result.warnings.append(synthesis.error)


def _safe_call(func: Any, *args: Any, default: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except Exception as exc:  # providers must never break the request
        logger.warning("multilingual_provider_raised", extra={"error": str(exc)})
        return default


# Re-exported so API modules can import intents from one place.
INTENTS = (
    INTENT_STATUS,
    INTENT_RECOMMENDATION,
    INTENT_HEALTH,
    INTENT_HARVEST_MAP,
)

__all__ = ["INTENTS", "MAX_AUDIO_BYTES", "MultilingualService", "VoiceQueryResult"]
