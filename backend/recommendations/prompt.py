"""Prompt construction for the Gemini recommendation tier.

The system prompt and enums live in ``configs/prompts/recommendation.yaml`` so
prompt edits do not require a code change and so the guardrails are reviewable
in one place.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from backend.core.config import get_settings
from backend.recommendations.schema import (
    TIER_GEMINI,
    TIER_GEMINI_SIMPLIFIED,
    ALLOWED_ACTIONS,
    HEALTH_STATUSES,
    RISK_LEVELS,
    RIPENESS_STATUSES,
    json_schema_for_prompt,
)

logger = logging.getLogger(__name__)

PROMPT_FILENAME = "recommendation.yaml"
DEFAULT_PROMPT_ID = "harvest_recommendation_v1"

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "ta": "Tamil",
    "hi": "Hindi",
    "ml": "Malayalam",
    "kn": "Kannada",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
}

SIMPLIFIED_SUFFIX = (
    "\nWrite for a listener with no technical vocabulary. Use short sentences, "
    "avoid numbers where a plain phrase will do, and name the zone in words."
)

LANGUAGES_BY_TIER = {
    TIER_GEMINI: ("ta", "hi", "en", "ml", "kn", "te"),
    TIER_GEMINI_SIMPLIFIED: ("ta", "hi", "en", "ml", "kn", "te"),
}

_FALLBACK_PROMPT: dict[str, Any] = {
    "id": DEFAULT_PROMPT_ID,
    "system_prompt": (
        "You are the explanation layer of an agricultural decision support system. "
        "Explain only the facts provided. Never invent measurements or diagnoses."
    ),
    "user_prompt_template": (
        "Crop: {crop}\nOutput language: {language} ({language_name})\n"
        "FACTS (already computed, do not recompute):\n{facts_json}\n"
        "Return one JSON object with exactly these keys:\n{schema}\n"
        "The `recommended_action` MUST be one of: {allowed_actions}.\n"
        "The `health_status` MUST be one of: {allowed_health_statuses}.\n"
        "The `ripeness_status` MUST be one of: {allowed_ripeness_statuses}.\n"
        "The `risk_level` MUST be one of: {allowed_risk_levels}.\n"
        "`confidence` MUST be a number between 0.0 and 1.0 and MUST NOT be higher\n"
        "than the confidence present in the input facts."
    ),
    "enums": {},
}


@lru_cache(maxsize=1)
def _prompt_file() -> Path:
    return Path(get_settings().prompts_dir) / PROMPT_FILENAME


@lru_cache(maxsize=1)
def load_prompt_config() -> dict[str, Any]:
    """Read the YAML prompt config once, falling back to a safe default."""
    path = _prompt_file()
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("recommendation_prompt_unreadable", extra={"path": str(path), "error": str(exc)})
        return dict(_FALLBACK_PROMPT)
    if not isinstance(data, dict):
        return dict(_FALLBACK_PROMPT)
    return {**data, "enums": data.get("enums") or {}}


def language_name(language: str) -> str:
    return LANGUAGE_NAMES.get(language, language)


def build_messages(
    facts: dict[str, Any],
    *,
    language: str = "en",
    crop: str = "mango",
    tier: str = TIER_GEMINI,
    heuristic_version: str = "heuristic-v0",
) -> list[dict[str, str]]:
    """Build Gemini ``contents`` for one recommendation request."""
    config = load_prompt_config()
    system_prompt = str(config.get("system_prompt") or _FALLBACK_PROMPT["system_prompt"])
    if tier == TIER_GEMINI_SIMPLIFIED:
        system_prompt += SIMPLIFIED_SUFFIX

    template = str(
        config.get("user_prompt_template") or _FALLBACK_PROMPT["user_prompt_template"]
    )
    facts_json = json.dumps(facts, ensure_ascii=False, sort_keys=True, default=str)
    user_prompt = template.format(
        crop=crop,
        language=language,
        language_name=language_name(language),
        heuristic_version=heuristic_version,
        facts_json=facts_json,
        schema=json_schema_for_prompt(),
        allowed_actions=", ".join(ALLOWED_ACTIONS),
        allowed_health_statuses=", ".join(HEALTH_STATUSES),
        allowed_ripeness_statuses=", ".join(RIPENESS_STATUSES),
        allowed_risk_levels=", ".join(RISK_LEVELS),
    )
    return [
        {"role": "system", "parts": [{"text": system_prompt}]},
        {"role": "user", "parts": [{"text": user_prompt}]},
    ]


def resolve_tier(tier: str | None) -> str:
    """Pick the richest tier the model can serve for this language."""
    from backend.recommendations.schema import TIER_RULES_ONLY

    candidate = (tier or TIER_GEMINI).upper()
    if candidate == TIER_RULES_ONLY:
        return TIER_RULES_ONLY
    supported = LANGUAGES_BY_TIER.get(candidate)
    if supported and candidate in (TIER_GEMINI, TIER_GEMINI_SIMPLIFIED):
        return candidate
    if candidate == TIER_GEMINI_SIMPLIFIED:
        return TIER_GEMINI_SIMPLIFIED
    return TIER_GEMINI


def reset_caches() -> None:
    """Test hook so prompt edits are picked up."""
    load_prompt_config.cache_clear()
    _prompt_file.cache_clear()


__all__ = [
    "DEFAULT_PROMPT_ID",
    "LANGUAGES_BY_TIER",
    "LANGUAGE_NAMES",
    "PROMPT_FILENAME",
    "SIMPLIFIED_SUFFIX",
    "build_messages",
    "language_name",
    "load_prompt_config",
    "reset_caches",
    "resolve_tier",
]
