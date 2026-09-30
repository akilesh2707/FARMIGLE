"""M11 - Gemini recommendation engine.

Three documented tiers: ``GEMINI`` -> ``GEMINI_SIMPLIFIED`` -> ``RULES_ONLY``.
"""

from backend.recommendations.fallback import (
    build_explainable_parts,
    build_fallback,
    build_fallback_output,
    build_fallback_text,
)
from backend.recommendations.prompt import build_messages, load_prompt_config
from backend.recommendations.providers import (
    GeminiProvider,
    MockGeminiProvider,
    RecommendationProvider,
    build_recommendation_provider,
)
from backend.recommendations.schema import (
    ALLOWED_ACTIONS,
    EVIDENCE_CODES,
    ExplainableParts,
    GeminiRecommendationOutput,
    Recommendation,
    RecommendationTier,
    TIER_GEMINI,
    TIER_GEMINI_SIMPLIFIED,
    TIER_RULES_ONLY,
    validate_gemini_output,
)
from backend.recommendations.service import RecommendationService, build_facts

__all__ = [
    "ALLOWED_ACTIONS",
    "EVIDENCE_CODES",
    "ExplainableParts",
    "GeminiProvider",
    "GeminiRecommendationOutput",
    "MockGeminiProvider",
    "Recommendation",
    "RecommendationProvider",
    "RecommendationService",
    "RecommendationTier",
    "TIER_GEMINI",
    "TIER_GEMINI_SIMPLIFIED",
    "TIER_RULES_ONLY",
    "build_explainable_parts",
    "build_facts",
    "build_fallback",
    "build_fallback_output",
    "build_fallback_text",
    "build_messages",
    "build_recommendation_provider",
    "load_prompt_config",
    "validate_gemini_output",
]
