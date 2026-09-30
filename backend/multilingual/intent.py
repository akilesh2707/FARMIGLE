"""Tamil-first intent parsing for voice and text queries.

The intent layer is deterministic. Gemini may be used to *phrase* the answer,
never to decide which farm or zone is being asked about: a wrong zone label in
a response is far more damaging than a clumsy sentence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Languages the UI exposes. Tamil is the documented MVP path.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("ta", "hi", "en", "ml", "kn", "te")
FALLBACK_LANGUAGE = "en"

# Keys are BCP-47-ish codes, values are the Gemini Translation target codes.
GOOGLE_LANGUAGE_CODES: dict[str, str] = {
    "ta": "ta",
    "hi": "hi",
    "en": "en",
    "ml": "ml",
    "kn": "kn",
    "te": "te",
    "mr": "mr",
    "bn": "bn",
    "gu": "gu",
    "or": "or",
    "kn-IN": "kn",
}

INTENT_STATUS = "zone_status"
INTENT_HARVEST_MAP = "harvest_map"
INTENT_RECOMMENDATION = "recommendation"
INTENT_HEALTH = "health"
INTENT_UNKNOWN = "unknown"

# Multilingual cue words. Deliberately small and reviewable: an unknown phrase
# degrades to a clarifying question instead of a guess.
CUE_WORDS: dict[str, tuple[str, ...]] = {
    INTENT_STATUS: (
        "status", "harvest ready", "ready", "ripeness", "ripen", "maturity", "pacha",
        "எப்படி", "உள்ளது", "மாற்றம்", "நிலை", "பழுத்த", "அனை",
        "स्थिति", "कैसा", "पका", "तैयार",
        # Tanglish: Tamil is frequently typed in Latin script.
        "sthaathi", "paka", "taiyaar", "enthu", "eppadi", "ullathu", "eppadi ullathu",
    ),
    INTENT_HARVEST_MAP: (
        "map", "harvest map", "which zone", "where",
        "வரைபடம்", "எங்கு", "varaipadam", "engu",
        "zain", "kidhar", "map",
    ),
    INTENT_RECOMMENDATION: (
        "recommend", "recommendation", "advice", "what should i do", "action", "next step",
        "அறிவுரை", "என்ன செய்வது", "பரிந்துரை",
        "arivu urai", "arivuurai", "parindhurai", "enna seyvathu", "enna seyvanum",
        "सलाह", "kya karna", "salāha",
        "നിർദ്ദേശം",
    ),
    INTENT_HEALTH: (
        "health", "disease", "sick", "pest", "infection", "leaf", "damage",
        "ஆரோக்கியம்", "நோய்", "பூச்சி", "நலம்",
        "arogiyam", "arokiya", "noi", "noy", "puchchi", "nalam",
        "सेहत", "रोग", "कीट",
        "sehat", "rog", "keeda",
        "ആരോഗ്യം",
    ),
}

# "zone" appears in its native scripts and in the Latin transliterations that
# Tamil and Hindi speakers actually type.
_ZONE_WORD = r"(?:zone|zones|மண்டலம்|mandalam|mandala|ज़ोन|जोन|sonie|സോണി|ವಲಯ|జోన్)"
ZONE_LABEL_PATTERN = re.compile(rf"\b{_ZONE_WORD}\s*([a-t])\b", re.IGNORECASE)
ZONE_ID_PATTERN = re.compile(rf"\b{_ZONE_WORD}\s*[-_]?\s*(\d{{1,2}})\b", re.IGNORECASE)


def normalize_language(language: str | None, *, default: str = FALLBACK_LANGUAGE) -> str:
    """Map any user-supplied language tag onto a supported code."""
    if not language:
        return default
    code = str(language).strip().lower().replace("_", "-")
    if code in SUPPORTED_LANGUAGES:
        return code
    base = code.split("-", 1)[0]
    if base in SUPPORTED_LANGUAGES:
        return base
    return default


@dataclass
class IntentResult:
    intent: str
    language: str
    zone_id: str | None = None
    zone_label: str | None = None
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: str | None = None
    matched_cues: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent,
            "language": self.language,
            "zone_id": self.zone_id,
            "zone_label": self.zone_label,
            "confidence": round(float(self.confidence), 4),
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "matched_cues": list(self.matched_cues),
        }


def _extract_zone(text: str) -> tuple[str | None, str | None]:
    match = ZONE_ID_PATTERN.search(text)
    if match:
        number = int(match.group(1))
        return f"zone_{number:02d}", None
    match = ZONE_LABEL_PATTERN.search(text)
    if match:
        label = match.group(1).upper()
        return None, label
    return None, None


def parse_intent(text: str, *, language: str | None = None) -> IntentResult:
    """Map a transcript to a supported intent and zone reference."""
    raw = (text or "").strip()
    normalized_language = normalize_language(language)
    lowered = raw.lower()

    if not raw:
        return IntentResult(
            intent=INTENT_UNKNOWN,
            language=normalized_language,
            needs_clarification=True,
            clarification_question=CLARIFYING_QUESTIONS[normalized_language],
            raw_text=raw,
        )

    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for intent, cues in CUE_WORDS.items():
        hits = [cue for cue in cues if cue in lowered]
        if hits:
            scores[intent] = len(hits)
            matched[intent] = hits

    if not scores:
        zone_id, zone_label = _extract_zone(lowered)
        return IntentResult(
            intent=INTENT_UNKNOWN,
            language=normalized_language,
            zone_id=zone_id,
            zone_label=zone_label,
            confidence=0.2,
            needs_clarification=True,
            clarification_question=CLARIFYING_QUESTIONS[normalized_language],
            raw_text=raw,
        )

    intent = max(sorted(scores), key=lambda key: scores[key])
    zone_id, zone_label = _extract_zone(lowered)
    strength = min(1.0, 0.55 + 0.15 * scores[intent] + (0.1 if zone_id or zone_label else 0.0))

    return IntentResult(
        intent=intent,
        language=normalized_language,
        zone_id=zone_id,
        zone_label=zone_label,
        confidence=strength,
        needs_clarification=not (zone_id or zone_label),
        clarification_question=(
            CLARIFYING_QUESTIONS[normalized_language] if not (zone_id or zone_label) else None
        ),
        matched_cues=matched[intent],
        raw_text=raw,
    )


CLARIFYING_QUESTIONS: dict[str, str] = {
    "en": "Which zone do you mean? For example: Zone A, or Zone 7.",
    "ta": "எந்த மண்டலத்தைக் குறிக்கிறீர்கள்? எடுத்துக்காட்டு: மண்டலம் A அல்லது மண்டலம் 7.",
    "hi": "आप किस ज़ोन के बारे में बात कर रहे हैं? उदाहरण: ज़ोन A या ज़ोन 7।",
    "ml": "ഏത് സോണിസെയാണ് പറയുന്നത്? ഉദാഹരണം: സോണി A അല്ലെങ്കിൽ സോണി 7.",
    "kn": "ಯಾವ ವಲಯದ ಬಗ್ಗೆ ಹೇಳುತ್ತಿದ್ದೀರಿ? ಉದಾಹರಣೆ: ವಲಯ A ಅಥವಾ ವಲಯ 7.",
    "te": "మీరు ఏ జోన్ గురించి మాట్లాడుతున్నారు? ఉదాహరణ: జోన్ A లేదా జోన్ 7.",
}


__all__ = [
    "CLARIFYING_QUESTIONS",
    "CUE_WORDS",
    "FALLBACK_LANGUAGE",
    "GOOGLE_LANGUAGE_CODES",
    "INTENT_HARVEST_MAP",
    "INTENT_HEALTH",
    "INTENT_RECOMMENDATION",
    "INTENT_STATUS",
    "INTENT_UNKNOWN",
    "IntentResult",
    "SUPPORTED_LANGUAGES",
    "ZONE_ID_PATTERN",
    "ZONE_LABEL_PATTERN",
    "normalize_language",
    "parse_intent",
]
