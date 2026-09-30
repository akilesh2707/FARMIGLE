"""Speech and translation providers (Cloud Speech, Translation, TTS).

Google clients are imported lazily. In mock mode the providers return obviously
synthetic output and set ``is_mock`` so a demo can never be mistaken for a real
recognition or a real translation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from backend.core.config import get_settings
from backend.multilingual.intent import GOOGLE_LANGUAGE_CODES, normalize_language

logger = logging.getLogger(__name__)

MOCK_TRANSCRIPT_PREFIX = "[mock transcript] "
MOCK_TRANSLATION_SUFFIX = " [mock translation]"

# Google TTS voice names per language (BCP-47 + voice). Tamil uses the
# documented Chennai/Tamil voice family.
DEFAULT_TTS_VOICES: dict[str, dict[str, str]] = {
    "ta": {"name": "ta-IN-ChitraNeural", "ssml_voice": "ta-IN-ChitraNeural"},
    "hi": {"name": "hi-IN-NeerjaNeural", "ssml_voice": "hi-IN-NeerjaNeural"},
    "en": {"name": "en-IN-Neural2-A", "ssml_voice": "en-IN-Neural2-A"},
    "ml": {"name": "ml-IN-IndraNeural", "ssml_voice": "ml-IN-IndraNeural"},
    "kn": {"name": "kn-IN-ChitraNeural", "ssml_voice": "kn-IN-ChitraNeural"},
    "te": {"name": "te-IN-ChitraNeural", "ssml_voice": "te-IN-ChitraNeural"},
}


@dataclass
class TranscriptionResult:
    text: str
    language: str
    confidence: float = 0.0
    is_mock: bool = False
    error: str | None = None
    alternative_languages: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "language": self.language,
            "confidence": round(float(self.confidence), 4),
            "is_mock": self.is_mock,
            "error": self.error,
            "alternative_languages": list(self.alternative_languages),
        }


@dataclass
class TranslationResult:
    text: str
    source_language: str
    target_language: str
    is_mock: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and bool(self.text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "is_mock": self.is_mock,
            "error": self.error,
        }


@dataclass
class SpeechSynthesisResult:
    audio_uri: str | None
    language: str
    voice: str
    is_mock: bool = False
    error: str | None = None
    ssml: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_uri": self.audio_uri,
            "language": self.language,
            "voice": self.voice,
            "is_mock": self.is_mock,
            "error": self.error,
        }


@runtime_checkable
class SpeechToTextProvider(Protocol):
    is_mock: bool

    def transcribe(
        self, audio_bytes: bytes, *, language: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult: ...


@runtime_checkable
class TranslationProvider(Protocol):
    is_mock: bool

    def translate(self, text: str, *, target_language: str, source_language: str = "en") -> TranslationResult: ...


@runtime_checkable
class TextToSpeechProvider(Protocol):
    is_mock: bool

    def synthesize(
        self, text: str, *, language: str, upload: bool = True
    ) -> SpeechSynthesisResult: ...


# --------------------------------------------------------------------------
# Real Google implementations
# --------------------------------------------------------------------------
class GoogleSpeechToTextProvider:
    is_mock = False

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import speech
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("google-cloud-speech is not installed") from exc
        settings = get_settings()
        if not settings.google_application_credentials:
            raise RuntimeError("GOOGLE_APPLICATION_CREDENTIALS is not configured")
        self._client = speech.SpeechClient()
        return self._client

    def transcribe(
        self, audio_bytes: bytes, *, language: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        target = normalize_language(language)
        try:
            from google.cloud import speech

            client = self._get_client()
            config = speech.RecognitionConfig(
                encoding=_encoding_for(mime_type),
                sample_rate_hertz=16000,
                language_code=GOOGLE_LANGUAGE_CODES.get(target, target),
                enable_automatic_punctuation=True,
            )
            audio = speech.RecognitionAudio(content=audio_bytes)
            response = client.recognize(config=config, audio=audio)
        except Exception as exc:
            logger.warning("stt_failed", extra={"language": target, "error": str(exc)})
            return TranscriptionResult(
                text="", language=target, confidence=0.0, error=f"stt_error: {exc}"
            )

        results = list(getattr(response, "results", []) or [])
        if not results:
            return TranscriptionResult(
                text="",
                language=target,
                confidence=0.0,
                error="stt_no_speech_or_unrecognisable",
                alternative_languages=[target],
            )
        best = results[0]
        alternatives = list(getattr(best, "alternatives", []) or [])
        if not alternatives:
            return TranscriptionResult(
                text="", language=target, confidence=0.0, error="stt_no_alternatives"
            )
        top = alternatives[0]
        return TranscriptionResult(
            text=str(getattr(top, "transcript", "") or ""),
            language=target,
            confidence=float(getattr(top, "confidence", 0.0) or 0.0),
            alternative_languages=[
                str(getattr(alt, "language_code", target) or target) for alt in alternatives[1:]
            ],
        )


class GoogleTranslationProvider:
    is_mock = False

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import translate
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("google-cloud-translate is not installed") from exc
        self._client = translate.TranslationServiceClient()
        return self._client

    def translate(self, text: str, *, target_language: str, source_language: str = "en") -> TranslationResult:
        target = normalize_language(target_language)
        if not text:
            return TranslationResult(
                text="", source_language=source_language, target_language=target, error="empty_text"
            )
        if target == source_language:
            return TranslationResult(
                text=text, source_language=source_language, target_language=target
            )
        parent = f"projects/{get_settings().google_project_id}/locations/global"
        try:
            client = self._get_client()
            response = client.translate_text(
                request={
                    "parent": parent,
                    "contents": [text],
                    "mime_type": "text/plain",
                    "source_language_code": GOOGLE_LANGUAGE_CODES.get(
                        normalize_language(source_language), "en"
                    ),
                    "target_language_code": GOOGLE_LANGUAGE_CODES.get(target, target),
                }
            )
            translations = list(getattr(response, "translations", []) or [])
            translated = str(getattr(translations[0], "translated_text", "") or "") if translations else ""
        except Exception as exc:
            logger.warning("translation_failed", extra={"target": target, "error": str(exc)})
            return TranslationResult(
                text="",
                source_language=source_language,
                target_language=target,
                error=f"translation_error: {exc}",
            )
        if not translated:
            return TranslationResult(
                text="",
                source_language=source_language,
                target_language=target,
                error="translation_empty",
            )
        return TranslationResult(
            text=translated,
            source_language=source_language,
            target_language=target,
        )


class GoogleTextToSpeechProvider:
    is_mock = False

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from google.cloud import texttospeech
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("google-cloud-texttospeech is not installed") from exc
        self._client = texttospeech.TextToSpeechClient()
        return self._client

    def synthesize(
        self, text: str, *, language: str, upload: bool = True
    ) -> SpeechSynthesisResult:
        target = normalize_language(language)
        voice = DEFAULT_TTS_VOICES.get(target, DEFAULT_TTS_VOICES["en"])
        ssml = build_ssml(text, voice=voice["ssml_voice"], language=target)
        try:
            from google.cloud import texttospeech

            client = self._get_client()
            response = client.synthesize_speech(
                input=texttospeech.SynthesisInput(ssml=ssml),
                voice=texttospeech.VoiceSelectionParams(
                    language_code=GOOGLE_LANGUAGE_CODES.get(target, target),
                    name=voice["name"],
                ),
                audio_config=texttospeech.AudioConfig(audio_encoding="MP3"),
            )
            audio_content = getattr(response, "audio_content", None)
        except Exception as exc:
            logger.warning("tts_failed", extra={"language": target, "error": str(exc)})
            return SpeechSynthesisResult(
                audio_uri=None, language=target, voice=voice["name"], error=f"tts_error: {exc}"
            )

        if not audio_content:
            return SpeechSynthesisResult(
                audio_uri=None, language=target, voice=voice["name"], error="tts_empty_audio"
            )

        if not upload:
            return SpeechSynthesisResult(
                audio_uri=f"data:audio/mp3;base64,{_b64(audio_content)}",
                language=target,
                voice=voice["name"],
                ssml=ssml,
            )

        from backend.core.config import get_settings as _get_settings
        from backend.core.storage import build_storage, build_object_path

        settings = _get_settings()
        try:
            storage = build_storage(settings)
            object_name = build_object_path(
                farm_id="voice",
                kind="tts",
                source=target,
                identifier=stable_audio_name(),
                extension="mp3",
            )
            stored = storage.save(
                audio_content, object_name=object_name, content_type="audio/mpeg"
            )
        except Exception as exc:
            logger.warning("tts_upload_failed", extra={"error": str(exc)})
            return SpeechSynthesisResult(
                audio_uri=None,
                language=target,
                voice=voice["name"],
                error=f"tts_upload_error: {exc}",
                ssml=ssml,
            )
        if not stored or not stored.uri:
            return SpeechSynthesisResult(
                audio_uri=None,
                language=target,
                voice=voice["name"],
                error=f"tts_storage_unavailable: {settings.storage_provider}",
                ssml=ssml,
            )
        return SpeechSynthesisResult(
            audio_uri=stored.uri, language=target, voice=voice["name"], ssml=ssml
        )


# --------------------------------------------------------------------------
# Mock implementations
# --------------------------------------------------------------------------
class MockSpeechToTextProvider:
    """Returns a fixed Tamil query so the offline demo path is exercisable.

    Real deployments must set ``MOCK_SERVICES=false``; the prefix makes any
    leaked mock transcript obvious in logs and in the API response.
    """

    is_mock = True

    def __init__(self, transcript: str = "மண்டலம் 7 எப்படி உள்ளது?", language: str = "ta") -> None:
        self.transcript = transcript
        self.language = normalize_language(language)

    def transcribe(
        self, audio_bytes: bytes, *, language: str | None = None, mime_type: str = "audio/webm"
    ) -> TranscriptionResult:
        target = normalize_language(language, default=self.language)
        return TranscriptionResult(
            text=f"{MOCK_TRANSCRIPT_PREFIX}{self.transcript}",
            language=target,
            confidence=0.0,
            is_mock=True,
            alternative_languages=[target],
        )


class MockTranslationProvider:
    """Pass-through with a loud marker. It is not a translation engine."""

    is_mock = True

    def translate(self, text: str, *, target_language: str, source_language: str = "en") -> TranslationResult:
        target = normalize_language(target_language)
        if target == source_language:
            return TranslationResult(
                text=text, source_language=source_language, target_language=target, is_mock=True
            )
        return TranslationResult(
            text=f"{text}{MOCK_TRANSLATION_SUFFIX}",
            source_language=source_language,
            target_language=target,
            is_mock=True,
        )


class MockTextToSpeechProvider:
    """No audio is generated. ``audio_uri`` stays ``None`` and mock is flagged."""

    is_mock = True

    def synthesize(self, text: str, *, language: str, upload: bool = True) -> SpeechSynthesisResult:
        target = normalize_language(language)
        voice = DEFAULT_TTS_VOICES.get(target, DEFAULT_TTS_VOICES["en"])
        return SpeechSynthesisResult(
            audio_uri=None,
            language=target,
            voice=voice["name"],
            is_mock=True,
            error="tts_mock_no_audio_generated",
            ssml=build_ssml(text, voice=voice["ssml_voice"], language=target),
        )


# --------------------------------------------------------------------------
# Factories and helpers
# --------------------------------------------------------------------------
def build_ssml(text: str, *, voice: str, language: str) -> str:
    escaped = (
        str(text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        f'<speak xml:lang="{language}">'
        f'<voice name="{voice}">{escaped}</voice>'
        "</speak>"
    )


def _encoding_for(mime_type: str) -> Any:
    from google.cloud import speech

    mapping = {
        "audio/webm": speech.RecognitionConfig.AudioEncoding.WEBM_OPUS,
        "audio/ogg": speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
        "audio/wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        "audio/x-wav": speech.RecognitionConfig.AudioEncoding.LINEAR16,
        "audio/mp3": speech.RecognitionConfig.AudioEncoding.MP3,
        "audio/mpeg": speech.RecognitionConfig.AudioEncoding.MP3,
        "audio/flac": speech.RecognitionConfig.AudioEncoding.FLAC,
        "audio/mp4": speech.RecognitionConfig.AudioEncoding.MP4,
    }
    return mapping.get(str(mime_type).lower(), speech.RecognitionConfig.AudioEncoding.WEBM_OPUS)


def _b64(payload: bytes) -> str:
    import base64

    return base64.b64encode(payload).decode("ascii")


def stable_audio_name() -> str:
    from backend.core.utils import new_id

    return new_id("voice")


def build_speech_to_text() -> SpeechToTextProvider:
    settings = get_settings()
    if settings.mock_services:
        return MockSpeechToTextProvider()
    return GoogleSpeechToTextProvider()


def build_translation() -> TranslationProvider:
    settings = get_settings()
    if settings.mock_services:
        return MockTranslationProvider()
    return GoogleTranslationProvider()


def build_text_to_speech() -> TextToSpeechProvider:
    settings = get_settings()
    if settings.mock_services:
        return MockTextToSpeechProvider()
    return GoogleTextToSpeechProvider()


__all__ = [
    "DEFAULT_TTS_VOICES",
    "GoogleSpeechToTextProvider",
    "GoogleTextToSpeechProvider",
    "GoogleTranslationProvider",
    "MOCK_TRANSCRIPT_PREFIX",
    "MOCK_TRANSLATION_SUFFIX",
    "MockSpeechToTextProvider",
    "MockTextToSpeechProvider",
    "MockTranslationProvider",
    "SpeechSynthesisResult",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "TranscriptionResult",
    "TranslationProvider",
    "TranslationResult",
    "build_speech_to_text",
    "build_ssml",
    "build_text_to_speech",
    "build_translation",
]
