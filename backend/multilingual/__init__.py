"""M12 - Multilingual voice interface.

Tamil-first path::

    Tamil speech -> STT -> intent parse -> analysis -> recommendation
                -> translation -> TTS -> Tamil audio

Every Google client is imported lazily so ``MOCK_SERVICES=true`` runs fully
offline. Mock providers return clearly-labelled stand-ins, never a fake
transcript that looks like a real recognition result.
"""

from backend.multilingual.intent import (
    FALLBACK_LANGUAGE,
    IntentResult,
    SUPPORTED_LANGUAGES,
    normalize_language,
    parse_intent,
)
from backend.multilingual.providers import (
    MockSpeechToTextProvider,
    MockTextToSpeechProvider,
    MockTranslationProvider,
    SpeechToTextProvider,
    TextToSpeechProvider,
    TranslationProvider,
    build_speech_to_text,
    build_text_to_speech,
    build_translation,
)
from backend.multilingual.service import MultilingualService, VoiceQueryResult

__all__ = [
    "FALLBACK_LANGUAGE",
    "IntentResult",
    "MockSpeechToTextProvider",
    "MockTextToSpeechProvider",
    "MockTranslationProvider",
    "MultilingualService",
    "SUPPORTED_LANGUAGES",
    "SpeechToTextProvider",
    "TextToSpeechProvider",
    "TranslationProvider",
    "VoiceQueryResult",
    "build_speech_to_text",
    "build_text_to_speech",
    "build_translation",
    "normalize_language",
    "parse_intent",
]
