"""Fusion engine: configurable, missing-source-safe weighted combination."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from backend.core.crop_config import ThresholdConfig
from backend.fusion.models import (
    CONTEXT_ROLES,
    ROLE_GROUND,
    ZoneFusionInput,
    ZoneFusionResult,
)

DEFAULT_FUSION_CONFIG: dict[str, Any] = {
    "weights": {"drone": 0.40, ROLE_GROUND: 0.60},
    "health_weights": {"drone": 0.45, ROLE_GROUND: 0.55},
    "confidence": {
        "base_per_source": {ROLE_GROUND: 0.78, "drone": 0.72},
        "penalty_per_missing_source": 0.08,
        "context_bonus": 0.04,
        "max_context_bonus_sources": 2,
        "min": 0.20,
        "max": 0.95,
    },
    "min_evidence_ratio": 0.50,
    "score_clamp": {"min": 0.0, "max": 1.0},
}


def resolve_fusion_config(config: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge a YAML fusion section over the documented defaults."""
    resolved: dict[str, Any] = {
        "weights": dict(DEFAULT_FUSION_CONFIG["weights"]),
        "health_weights": dict(DEFAULT_FUSION_CONFIG["health_weights"]),
        "confidence": dict(DEFAULT_FUSION_CONFIG["confidence"]),
        "min_evidence_ratio": DEFAULT_FUSION_CONFIG["min_evidence_ratio"],
        "score_clamp": dict(DEFAULT_FUSION_CONFIG["score_clamp"]),
    }
    for key, value in (config or {}).items():
        if key == "confidence" and isinstance(value, Mapping):
            merged = dict(resolved["confidence"])
            for sub_key, sub_value in value.items():
                if sub_key == "base_per_source" and isinstance(sub_value, Mapping):
                    merged["base_per_source"] = {
                        **merged.get("base_per_source", {}),
                        **sub_value,
                    }
                else:
                    merged[sub_key] = sub_value
            resolved["confidence"] = merged
        elif key in ("weights", "health_weights", "score_clamp") and isinstance(value, Mapping):
            resolved[key] = {**resolved[key], **value}
        elif key in resolved:
            resolved[key] = value
    return resolved


def _context_is_usable(role: str, zone_input: Any) -> bool:
    """True only when a context layer actually returned usable data.

    A provider that reported itself unavailable must not be counted: claiming
    "weather was used" when it was not would overstate the evidence behind a
    status the farmer acts on.
    """
    value: Any = None
    if role in zone_input.context:
        value = zone_input.context[role]
    elif role in zone_input.evidence:
        value = zone_input.evidence[role]
    else:
        return False
    if value is None:
        return False
    if isinstance(value, dict):
        if value.get("available") is False or value.get("state") == "unavailable":
            return False
        return True
    available = getattr(value, "available", None)
    if available is not None:
        return bool(available)
    return not bool(getattr(value, "is_unavailable", False))


class FusionEngine:
    """Combines per-source evidence into one result per zone.

    Section 7 M7 wording is preserved in the emitted ``contributions`` block, so
    a reviewer can see exactly which weights were applied and which were
    renormalised because a source was missing.
    """

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = resolve_fusion_config(config)

    @classmethod
    def from_thresholds(cls, thresholds: ThresholdConfig | None) -> "FusionEngine":
        return cls(getattr(thresholds, "fusion", None))

    # -- public API --------------------------------------------------------
    def fuse(self, zone_input: ZoneFusionInput) -> ZoneFusionResult:
        role_evidence = self._resolve_roles(zone_input.evidence)

        ripeness, ripeness_detail = self._combine(
            role_evidence, score_field="ripeness_score", weights=self.config["weights"]
        )
        health, health_detail = self._combine(
            role_evidence, score_field="health_score", weights=self.config["health_weights"]
        )

        # A role counts as present only when it actually carried a ripeness
        # score; a drone image with no ripeness output is missing evidence.
        present_ripeness = [
            role
            for role in self.config["weights"]
            if role in role_evidence and role_evidence[role].ripeness_score is not None
        ]
        missing_ripeness = sorted(set(self.config["weights"]) - set(present_ripeness))

        configured_weight = sum(float(weight) for weight in self.config["weights"].values())
        present_weight = sum(float(self.config["weights"][role]) for role in present_ripeness)
        evidence_ratio = (present_weight / configured_weight) if configured_weight else 0.0

        confidence = self._confidence(
            zone_input=zone_input,
            role_evidence=role_evidence,
            present_sources=present_ripeness,
            missing_sources=missing_ripeness,
        )

        context_sources = sorted(
            key for key in CONTEXT_ROLES if _context_is_usable(key, zone_input)
        )
        # `sources_used` lists only the image evidence behind the ripeness score.
        # Context layers are reported separately so a farmer can never read
        # "satellite" as a fruit-ripeness measurement.
        sources_used = sorted(
            {source for source, item in zone_input.evidence.items() if item.role in present_ripeness}
        )

        notes: list[str] = []
        evidence_insufficient = evidence_ratio < float(self.config["min_evidence_ratio"])
        if not present_ripeness:
            notes.append(
                "No image-based source (drone/ground) contributed a ripeness score; "
                "ripeness is unreported rather than assumed."
            )
        elif evidence_insufficient:
            notes.append(
                f"Only {evidence_ratio:.0%} of the configured ripeness evidence was available; "
                "the fused score is low-evidence."
            )
        if missing_ripeness:
            notes.append(
                "Missing sources were renormalised, never treated as zero: "
                + ", ".join(missing_ripeness)
            )
        if any(item.is_mock for item in zone_input.evidence.values()):
            notes.append("One or more contributing providers are MOCK providers.")
        if len(zone_input.evidence) > len({item.role for item in zone_input.evidence.values()}):
            notes.append(
                "Several observations mapped to the same fusion role; the highest-confidence "
                "one was used for that role."
            )

        return ZoneFusionResult(
            zone_id=zone_input.zone_id,
            ripeness_score=ripeness,
            health_score=health,
            confidence=confidence,
            sources_used=sources_used,
            context_sources_used=context_sources,
            missing_sources=missing_ripeness,
            evidence_insufficient=evidence_insufficient,
            contributions={
                "ripeness": ripeness_detail,
                "health": health_detail,
                "evidence_ratio": round(float(evidence_ratio), 4),
                "config_source": "configs/thresholds/<crop>.yaml#fusion (heuristic v0)",
                "weights_config": dict(self.config["weights"]),
            },
            context=dict(zone_input.context),
            is_mock=any(item.is_mock for item in zone_input.evidence.values()),
            notes=notes,
            zone_label=zone_input.zone_label,
        )

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _resolve_roles(evidence: Mapping[str, Any]) -> dict[str, Any]:
        """Map each fusion role to the single best observation for that role.

        ``phone`` and ``rover`` both fill the ``ground`` role. When two
        observations would fill the same role, the highest-confidence one wins
        (ties broken by source name, so the choice is deterministic).
        """
        role_evidence: dict[str, Any] = {}
        for source in sorted(evidence):
            item = evidence[source]
            role = item.role
            if role not in role_evidence or item.confidence > role_evidence[role].confidence:
                role_evidence[role] = item
        return role_evidence

    def _combine(
        self,
        role_evidence: Mapping[str, Any],
        *,
        score_field: str,
        weights: Mapping[str, float],
    ) -> tuple[float | None, dict[str, Any]]:
        """Weighted mean over present sources with weight renormalisation."""
        present: list[tuple[str, float, float]] = []  # (role, score, weight)
        for role, configured_weight in weights.items():
            item = role_evidence.get(role)
            if item is None:
                continue
            score = getattr(item, score_field)
            if score is None:
                continue
            present.append((role, float(score), float(configured_weight)))

        detail: dict[str, Any] = {
            "method": "weighted_mean_renormalized_over_present_sources",
            "present": [
                {
                    "role": role,
                    "source": role_evidence[role].source,
                    "score": round(score, 4),
                    "configured_weight": weight,
                }
                for role, score, weight in present
            ],
            "missing": sorted(set(weights) - {role for role, _, _ in present}),
        }

        if not present:
            detail["effective_weights"] = {}
            detail["total_weight"] = 0.0
            detail["value"] = None
            return None, detail

        total_weight = sum(weight for _, _, weight in present)
        detail["effective_weights"] = [
            {
                "role": role,
                "source": role_evidence[role].source,
                "score": round(score, 4),
                "configured_weight": weight,
                "effective_weight": round(weight / total_weight, 6),
            }
            for role, score, weight in present
        ]
        value = sum(score * (weight / total_weight) for _, score, weight in present)
        low, high = self._score_bounds()
        value = float(np.clip(value, low, high))

        detail["total_weight"] = round(total_weight, 4)
        detail["value"] = round(value, 4)
        return value, detail

    def _confidence(
        self,
        *,
        zone_input: ZoneFusionInput,
        role_evidence: Mapping[str, Any],
        present_sources: list[str],
        missing_sources: list[str],
    ) -> float:
        confidence_config = self.config["confidence"]
        base_per_source: Mapping[str, float] = confidence_config.get("base_per_source", {})
        weights: Mapping[str, float] = self.config["weights"]

        if present_sources:
            total_weight = sum(float(weights[source]) for source in present_sources)
            weighted_base = sum(
                float(base_per_source.get(source, 0.6)) * float(weights[source])
                for source in present_sources
            )
            base = weighted_base / total_weight if total_weight else 0.0
            # Blend in how confident the providers themselves were.
            provider_confidences = [
                float(role_evidence[source].confidence)
                for source in present_sources
                if source in role_evidence
            ]
            if provider_confidences:
                base = 0.55 * base + 0.45 * float(np.mean(provider_confidences))
        else:
            base = 0.0

        base -= float(confidence_config.get("penalty_per_missing_source", 0.08)) * len(
            missing_sources
        )

        context_present = [role for role in CONTEXT_ROLES if _context_is_usable(role, zone_input)]
        context_bonus = min(
            len(context_present),
            int(confidence_config.get("max_context_bonus_sources", 2)),
        ) * float(confidence_config.get("context_bonus", 0.04))
        base += context_bonus

        if not present_sources:
            # Context only: keep confidence low but non-zero so the risk engine
            # can still act on an anomaly. Context never contributes a score.
            base = min(base, 0.35)

        return float(
            np.clip(
                base,
                float(confidence_config.get("min", 0.20)),
                float(confidence_config.get("max", 0.95)),
            )
        )

    def _score_bounds(self) -> tuple[float, float]:
        clamp = self.config.get("score_clamp", {})
        return float(clamp.get("min", 0.0)), float(clamp.get("max", 1.0))


__all__ = ["DEFAULT_FUSION_CONFIG", "FusionEngine", "resolve_fusion_config"]
