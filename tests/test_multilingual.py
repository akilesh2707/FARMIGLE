"""Multilingual: Tamil-first intent, and honest degradation of STT/TTS/translation."""

from __future__ import annotations

import base64

import pytest

from backend.multilingual.intent import (
    INTENT_HARVEST_MAP,
    INTENT_HEALTH,
    INTENT_RECOMMENDATION,
    INTENT_STATUS,
    INTENT_UNKNOWN,
    normalize_language,
    parse_intent,
)
from backend.multilingual.providers import build_speech_to_text


@pytest.mark.parametrize(
    ("text", "intent", "zone_id", "zone_label"),
    [
        ("மண்டலம் 7 எப்படி உள்ளது?", INTENT_STATUS, "zone_07", None),
        ("மண்டலம் G நிலை என்ன", INTENT_STATUS, None, "G"),
        ("எனது பயிருக்கு அறிவுரை தேவை", INTENT_RECOMMENDATION, None, None),
        ("ஆரோக்கியம் எப்படி இருக்கு", INTENT_HEALTH, None, None),
        ("asdkjhasd", INTENT_UNKNOWN, None, None),
    ],
)
def test_tamil_intent_parsing(
    text: str, intent: str, zone_id: str | None, zone_label: str | None
) -> None:
    parsed = parse_intent(text, language="ta")
    assert parsed.intent == intent
    assert parsed.zone_id == zone_id
    assert parsed.zone_label == zone_label


def test_english_and_transliterated_tamil_both_resolve_a_zone() -> None:
    assert parse_intent("zone 7 status", language="en").zone_id == "zone_07"
    # Tanglish: Tamil typed in Latin script is a normal way to type in the field.
    assert parse_intent("mandalam 7 eppadi ullathu", language="ta").zone_id == "zone_07"
    assert parse_intent("mandalam A varaipadam engu", language="ta").intent == INTENT_HARVEST_MAP
    assert parse_intent("zone A arogiyam", language="hi").intent == INTENT_HEALTH


def test_language_normalization_falls_back_to_english() -> None:
    assert normalize_language("ta") == "ta"
    assert normalize_language("TA") == "ta"
    assert normalize_language("xx") == "en"
    assert normalize_language(None) == "en"


def test_ambiguous_question_asks_for_clarification() -> None:
    parsed = parse_intent("எப்படி உள்ளது?", language="ta")
    assert parsed.needs_clarification is True
    assert parsed.clarification_question  # never a guessed zone
    assert parsed.zone_id is None and parsed.zone_label is None


def test_mock_stt_is_labelled_and_never_claims_real_transcription() -> None:
    provider = build_speech_to_text()
    assert provider.is_mock is True
    result = provider.transcribe(b"\x1a\x45\xdf\xa3" + b"\x00" * 128, language="ta")
    assert result.is_mock is True
    assert "mock" in result.text.lower()
    assert result.confidence < 1.0


def test_localize_degrades_instead_of_failing(container) -> None:
    from backend.multilingual.service import VoiceQueryResult

    result = container.multilingual.handle_text_query(
        "மண்டலம் 7 எப்படி உள்ளது?", language="ta"
    )
    assert isinstance(result, VoiceQueryResult)
    localized = container.multilingual.localize(result, "Zone G is near ready.", target_language="ta")
    assert localized.answer_text
    assert localized.language == "ta"
    # No real audio is produced in mock mode, and that is reported, not hidden.
    assert localized.audio_uri is None
    assert any("tts" in warning.lower() for warning in localized.warnings)
    # Mock providers are working as designed, so this is `is_mock` rather than
    # `degraded`; `degraded` is reserved for a real provider failing.
    assert localized.is_mock is True
    assert localized.translation["is_mock"] is True


def test_english_answer_passes_through_untranslated(container) -> None:
    result = container.multilingual.handle_text_query("zone 7 status", language="en")
    localized = container.multilingual.localize(result, "Zone G is near ready.", target_language="en")
    assert localized.answer_text == "Zone G is near ready."
    assert localized.answer_language == "en"
    assert localized.translation is None  # no translation needed for English


def test_voice_query_accepts_audio_and_degrades_to_text_only(container, farm) -> None:
    audio = base64.b64encode(b"\x1a\x45\xdf\xa3" + b"\x00" * 256).decode()
    result = container.multilingual.handle_voice_query(
        base64.b64decode(audio), language="ta", mime_type="audio/webm", synthesize=True
    )
    assert result.transcript
    assert result.is_mock is True
    assert result.clarification or result.zone_id or result.intent.intent != INTENT_UNKNOWN


def test_stt_provider_failure_degrades_without_leaking_details(container) -> None:
    """The request survives, and the provider's own message never reaches it."""
    class Broken:
        name = "broken"
        is_mock = False

        def transcribe(self, audio_bytes, *, language="en", mime_type="audio/webm"):
            raise RuntimeError("credentials are invalid: sk-live-123")

    service = type(container.multilingual)(
        speech_to_text=Broken(), translation=None, text_to_speech=None
    )
    result = service.handle_voice_query(b"\x00" * 64, language="ta", synthesize=False)
    payload = result.to_dict()
    assert "sk-live-123" not in str(payload)
    assert "credentials" not in str(payload).lower()
    assert "stt_unavailable" in result.warnings
