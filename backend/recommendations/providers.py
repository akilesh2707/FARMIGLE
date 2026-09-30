"""Gemini provider for the recommendation tier.

Per Section 3.3 of the documentation Gemini only ever *narrates* facts that
the deterministic pipeline produced. It is never asked to perceive, never
asked to decide, and never allowed to invent a number.

The real provider is imported lazily so a local ``MOCK_SERVICES=true`` run
never needs Google credentials.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Protocol, runtime_checkable

from backend.core.config import get_settings
from backend.recommendations.fallback import build_fallback_output
from backend.recommendations.prompt import build_messages
from backend.recommendations.schema import (
    GEMINI_RESPONSE_SCHEMA,
    TIER_GEMINI,
    TIER_GEMINI_SIMPLIFIED,
)

logger = logging.getLogger(__name__)

MOCK_MODEL_NAME = "mock-gemini-2.5-flash"


@runtime_checkable
class RecommendationProvider(Protocol):
    """Anything that can turn facts into a schema-valid recommendation."""

    name: str
    is_mock: bool

    def generate(
        self, facts: dict[str, Any], *, language: str, tier: str
    ) -> tuple[dict[str, Any] | str | None, str | None]:
        """Return ``(raw_output, error)``; never raises."""


class MockGeminiProvider:
    """Deterministic stand-in for Gemini.

    It produces schema-valid JSON with the same vocabulary the real model is
    given, so the three-tier degradation can be demonstrated offline. The
    wording is assembled from facts only - it is not a language model.
    """

    name = MOCK_MODEL_NAME
    is_mock = True

    def __init__(self, *, model: str = MOCK_MODEL_NAME) -> None:
        self.model = model

    def generate(
        self, facts: dict[str, Any], *, language: str = "en", tier: str = TIER_GEMINI
    ) -> tuple[dict[str, Any], None]:
        payload = build_fallback_output(facts)
        data = payload.model_dump()
        status = str(facts.get("status") or "NO_DATA").upper()
        if tier == TIER_GEMINI_SIMPLIFIED or status == "NO_DATA":
            data["explanation"] = self._simplify(data["explanation"], facts, language)
        else:
            data["explanation"] = self._narrate(data["explanation"], facts, language)
        return data, None

    @staticmethod
    def _narrate(explanation: str, facts: dict[str, Any], language: str) -> str:
        sources = ", ".join(str(item) for item in facts.get("sources_used") or []) or "no sources"
        return (
            f"{explanation} This status is based on evidence from {sources} and on the "
            f"{facts.get('heuristic_version', 'heuristic-v0')} rules, which are not yet "
            "validated by agronomists."
        )

    @staticmethod
    def _simplify(explanation: str, facts: dict[str, Any], language: str) -> str:
        zone = str(facts.get("zone_label") or facts.get("zone_id") or "this area")
        status = str(facts.get("status") or "NO_DATA").replace("_", " ").lower()
        return (
            f"{zone} is {status}. {explanation} "
            "Please ask an agricultural officer before using any spray or medicine."
        )


class GeminiProvider:
    """Real Gemini call via ``google-genai`` with JSON-schema output."""

    is_mock = False

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 20.0,
        max_output_tokens: int = 800,
    ) -> None:
        settings = get_settings()
        self.name = model or settings.gemini_model
        self.model = self.name
        self._api_key = api_key or settings.gemini_api_key
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        try:
            from google import genai
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("google-genai is not installed") from exc
        self._client = genai.Client(api_key=self._api_key)
        return self._client

    def generate(
        self, facts: dict[str, Any], *, language: str = "en", tier: str = TIER_GEMINI
    ) -> tuple[Any, str | None]:
        try:
            client = self._get_client()
        except RuntimeError as exc:
            return None, f"gemini_unavailable: {exc}"

        messages = build_messages(
            facts,
            language=language,
            crop=str(facts.get("crop") or "mango"),
            tier=tier,
            heuristic_version=str(facts.get("heuristic_version") or "heuristic-v0"),
        )
        system_instruction = messages[0]["parts"][0]["text"]
        user_text = messages[1]["parts"][0]["text"]

        try:
            from google.genai import types
        except ImportError as exc:  # pragma: no cover - dependency guard
            return None, f"gemini_unavailable: {exc}"

        try:
            response = client.models.generate_content(
                model=self.model,
                contents=user_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    # Section 12.7 asks for schema-constrained JSON, not prose.
                    # The schema is sent so the model is constrained at decode
                    # time; the result is still validated on the way in, because
                    # a schema hint is not a guarantee.
                    response_schema=GEMINI_RESPONSE_SCHEMA,
                    max_output_tokens=self.max_output_tokens,
                ),
            )
        except Exception as exc:  # network, auth, quota, safety filters
            logger.warning(
                "gemini_call_failed",
                extra={"model": self.model, "tier": tier, "language": language, "error": str(exc)},
            )
            return None, f"gemini_error: {exc}"

        text = getattr(response, "text", None)
        if not text:
            candidates = getattr(response, "candidates", None) or []
            parts_text = ""
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                for part in getattr(content, "parts", None) or []:
                    parts_text += getattr(part, "text", "") or ""
            text = parts_text or None
        if not text:
            return None, "gemini_empty_response"
        return text, None


def build_recommendation_provider() -> RecommendationProvider:
    """Factory honouring ``MOCK_SERVICES`` and ``GEMINI_API_KEY``."""
    settings = get_settings()
    if settings.mock_services:
        return MockGeminiProvider()
    if not settings.gemini_api_key:
        logger.warning("gemini_key_missing_using_mock_provider")
        return MockGeminiProvider()
    return GeminiProvider()


def parse_raw_output(raw: Any) -> Any:
    """Best-effort extraction of a JSON object from raw model text."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except (ValueError, TypeError):
                return text
        return text


__all__ = [
    "GeminiProvider",
    "MOCK_MODEL_NAME",
    "MockGeminiProvider",
    "RecommendationProvider",
    "build_recommendation_provider",
    "parse_raw_output",
]
