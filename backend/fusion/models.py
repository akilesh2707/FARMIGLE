"""M7 - Multi-source fusion.

Documented formula (Section 7 M7)::

    ripeness_zone = w_drone * drone_score + w_ground * ground_score
    defaults: w_drone = 0.40, w_ground = 0.60   (configurable heuristic v0)
    missing source -> renormalize weights (never silently treat as zero)

That rule is implemented literally. Notes on the design:

* A missing source never contributes ``0``. Weights are renormalised over the
  sources actually present, and the set of missing sources is reported.
* Satellite / weather / soil never contribute to the ripeness number. They
  adjust confidence and feed the risk engine only (Section 3.3, D1).
* If too little evidence is present, the result is marked
  ``evidence_insufficient`` rather than reported as a confident score.
* No score at all is reported as ``None``, never as a fabricated ``0.0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ml.fruit_detection.base import FruitDetectionResult
from ml.health.base import HealthResult
from ml.ripeness.base import RipenessResult

# Fusion role names, as they appear in configs/crops/mango.yaml `fusion_sources`.
ROLE_DRONE = "drone"
ROLE_GROUND = "ground"
CONTEXT_ROLES = ("satellite", "weather", "farmer_report", "soil")

# Raw observation sources mapped onto fusion roles. drone/rover/phone all sit
# on the same pipeline (Section 4.3); only the role differs.
SOURCE_TO_ROLE = {
    "drone": ROLE_DRONE,
    "phone": ROLE_GROUND,
    "rover": ROLE_GROUND,
    "ground": ROLE_GROUND,
}


@dataclass(frozen=True)
class SourceEvidence:
    """Normalised evidence contributed by one observation source."""

    source: str
    ripeness_score: float | None = None
    health_score: float | None = None
    confidence: float = 0.0
    is_mock: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def role(self) -> str:
        return SOURCE_TO_ROLE.get(self.source, self.source)

    @classmethod
    def from_visual(
        cls,
        *,
        source: str,
        detection: FruitDetectionResult,
        ripeness: RipenessResult,
        health: HealthResult,
        detail: dict[str, Any] | None = None,
    ) -> "SourceEvidence":
        return cls(
            source=source,
            ripeness_score=float(ripeness.score),
            health_score=float(health.health_score),
            confidence=float(np.mean([detection.confidence, ripeness.confidence, health.confidence])),
            is_mock=bool(detection.is_mock or ripeness.is_mock or health.is_mock),
            detail={
                "fruit_count": detection.fruit_count,
                "detection_confidence": round(detection.confidence, 4),
                "ripeness_confidence": round(ripeness.confidence, 4),
                "health_confidence": round(health.confidence, 4),
                "possible_indicators": list(health.possible_indicators),
                **(detail or {}),
            },
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "role": self.role,
            "ripeness_score": None if self.ripeness_score is None else round(self.ripeness_score, 4),
            "health_score": None if self.health_score is None else round(self.health_score, 4),
            "confidence": round(float(self.confidence), 4),
            "is_mock": self.is_mock,
            "detail": self.detail,
        }


@dataclass
class ZoneFusionInput:
    """Everything fusion is allowed to look at for one zone."""

    zone_id: str
    evidence: dict[str, SourceEvidence] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    crop_stage: str | None = None
    zone_label: str | None = None

    def with_evidence(self, item: SourceEvidence) -> "ZoneFusionInput":
        merged = dict(self.evidence)
        merged[item.source] = item
        return ZoneFusionInput(
            zone_id=self.zone_id,
            evidence=merged,
            context=dict(self.context),
            crop_stage=self.crop_stage,
            zone_label=self.zone_label,
        )


@dataclass
class ZoneFusionResult:
    """Fused per-zone result (Section 12.4)."""

    zone_id: str
    ripeness_score: float | None
    health_score: float | None
    confidence: float
    sources_used: list[str]
    context_sources_used: list[str]
    missing_sources: list[str]
    evidence_insufficient: bool
    contributions: dict[str, Any]
    context: dict[str, Any] = field(default_factory=dict)
    is_mock: bool = False
    notes: list[str] = field(default_factory=list)
    zone_label: str | None = None

    @property
    def has_ripeness(self) -> bool:
        return self.ripeness_score is not None

    @property
    def has_health(self) -> bool:
        return self.health_score is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_label": self.zone_label,
            "ripeness_score": None if self.ripeness_score is None else round(self.ripeness_score, 4),
            "health_score": None if self.health_score is None else round(self.health_score, 4),
            "confidence": round(float(self.confidence), 4),
            "sources_used": list(self.sources_used),
            "context_sources_used": list(self.context_sources_used),
            "missing_sources": list(self.missing_sources),
            "evidence_insufficient": self.evidence_insufficient,
            "contributions": self.contributions,
            "context": self.context,
            "is_mock": self.is_mock,
            "notes": list(self.notes),
        }
