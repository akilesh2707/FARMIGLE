"""M9 - Harvest readiness rules (Section 8).

Every number here comes from ``configs/thresholds/<crop>.yaml``; nothing is
hard-coded in Python. The values are **configurable heuristic v0** and are
labelled as such in every response.

Documented rules::

    score >= 0.70           -> HARVEST_READY
    0.40 <= score < 0.70    -> NEAR_READY
    score < 0.40            -> NOT_READY
    health risk high        -> HEALTH_CONCERN (overrides or annotates)

    score >= 0.85 -> 0-1 days      score >= 0.70 -> 1-3 days
    score >= 0.40 -> 4-7 days      score < 0.40 -> 8-14 days
    health-risk adjustment: move earlier if waiting increases crop loss
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Sequence
from typing import Any

from backend.core.crop_config import ThresholdConfig

STATUS_HARVEST_READY = "HARVEST_READY"
STATUS_NEAR_READY = "NEAR_READY"
STATUS_NOT_READY = "NOT_READY"
STATUS_HEALTH_CONCERN = "HEALTH_CONCERN"
STATUS_NO_DATA = "NO_DATA"

RIPENESS_STATUSES = (STATUS_HARVEST_READY, STATUS_NEAR_READY, STATUS_NOT_READY)
ALL_STATUSES = (*RIPENESS_STATUSES, STATUS_HEALTH_CONCERN, STATUS_NO_DATA)

CODE_HIGH_RIPENESS = "HIGH_RIPENESS"
CODE_MODERATE_RIPENESS = "MODERATE_RIPENESS"
CODE_LOW_RIPENESS = "LOW_RIPENESS"
CODE_NO_RIPENESS_EVIDENCE = "NO_RIPENESS_EVIDENCE"
CODE_HEALTH_RISK_HIGH = "HEALTH_RISK_HIGH"
CODE_HEALTH_SCORE_LOW = "HEALTH_SCORE_LOW"
CODE_LOW_CONFIDENCE = "LOW_FUSION_CONFIDENCE"
CODE_EARLY_HARVEST_ADJUSTMENT = "HEALTH_RISK_EARLIER_HARVEST"

DEFAULT_HARVEST_CONFIG: dict[str, Any] = {
    "status_thresholds": {"harvest_ready": 0.70, "near_ready": 0.40},
    "status_labels": {
        STATUS_HARVEST_READY: "Harvest ready",
        STATUS_NEAR_READY: "Near ready",
        STATUS_NOT_READY: "Not ready",
        STATUS_HEALTH_CONCERN: "Health concern - inspect",
        STATUS_NO_DATA: "No data yet",
    },
    "health_concern": {
        "mode": "override",
        "triggering_risk_levels": ["high"],
        "health_score_below": 0.45,
    },
    "days_to_harvest_bands": [
        {"min_score": 0.85, "label": "0-1 days", "min_days": 0, "max_days": 1},
        {"min_score": 0.70, "label": "1-3 days", "min_days": 1, "max_days": 3},
        {"min_score": 0.40, "label": "4-7 days", "min_days": 4, "max_days": 7},
        {"min_score": 0.00, "label": "8-14 days", "min_days": 8, "max_days": 14},
    ],
    "health_risk_adjustment": {
        "enabled": True,
        "risk_levels": ["high"],
        "shift_bands_earlier_by": 1,
    },
}

DEFAULT_ACTIONS: dict[str, str] = {
    STATUS_HARVEST_READY: "PRIORITIZE_HARVEST",
    STATUS_NEAR_READY: "MONITOR_AND_PREPARE",
    STATUS_NOT_READY: "CONTINUE_MONITORING",
    STATUS_HEALTH_CONCERN: "INSPECT_ZONE",
    STATUS_NO_DATA: "CAPTURE_EVIDENCE",
}


def resolve_harvest_config(config: Any) -> dict[str, Any]:
    """Merge a YAML ``harvest`` section over the documented defaults."""
    resolved: dict[str, Any] = {
        "status_thresholds": dict(DEFAULT_HARVEST_CONFIG["status_thresholds"]),
        "status_labels": dict(DEFAULT_HARVEST_CONFIG["status_labels"]),
        "health_concern": dict(DEFAULT_HARVEST_CONFIG["health_concern"]),
        "days_to_harvest_bands": [
            dict(band) for band in DEFAULT_HARVEST_CONFIG["days_to_harvest_bands"]
        ],
        "health_risk_adjustment": dict(DEFAULT_HARVEST_CONFIG["health_risk_adjustment"]),
    }
    for key, value in (config or {}).items():
        if key == "days_to_harvest_bands":
            if isinstance(value, list) and value:
                resolved[key] = [dict(band) for band in value]
        elif key in resolved and isinstance(value, dict):
            resolved[key] = {**resolved[key], **value}
        elif key in resolved:
            resolved[key] = value
    return resolved


@dataclass
class HarvestDecision:
    """Outcome of the decision layer for one zone."""

    status: str
    ripeness_status: str | None
    health_concern: bool
    estimated_harvest_window: str | None
    days_to_harvest_min: int | None
    days_to_harvest_max: int | None
    recommended_action: str
    reason_codes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    status_label: str = ""
    heuristic_version: str = "heuristic-v0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "status_label": self.status_label,
            "ripeness_status": self.ripeness_status,
            "health_concern": self.health_concern,
            "estimated_harvest_window": self.estimated_harvest_window,
            "days_to_harvest_min": self.days_to_harvest_min,
            "days_to_harvest_max": self.days_to_harvest_max,
            "recommended_action": self.recommended_action,
            "reason_codes": list(self.reason_codes),
            "notes": list(self.notes),
            "heuristic_version": self.heuristic_version,
            "heuristic_validated": False,
        }


class HarvestEngine:
    """Configurable status + days-to-harvest decision rules."""

    def __init__(
        self,
        harvest_config: Any = None,
        *,
        actions: dict[str, str] | None = None,
        heuristic_version: str = "heuristic-v0",
    ) -> None:
        self.config = resolve_harvest_config(harvest_config)
        self.actions = {**DEFAULT_ACTIONS, **(actions or {})}
        self.heuristic_version = heuristic_version

    @classmethod
    def from_thresholds(cls, thresholds: ThresholdConfig | None) -> "HarvestEngine":
        return cls(
            getattr(thresholds, "harvest", None),
            actions=dict(getattr(thresholds, "actions", {}) or {}),
            heuristic_version=getattr(thresholds, "heuristic_version", "heuristic-v0"),
        )

    # -- public API --------------------------------------------------------
    def decide(
        self,
        *,
        ripeness_score: float | None,
        health_score: float | None = None,
        risk_level: str = "none",
        confidence: float | None = None,
        risk_codes: Sequence[str] | None = None,
    ) -> HarvestDecision:
        notes: list[str] = []
        reason_codes: list[str] = []

        if ripeness_score is None:
            reason_codes.append(CODE_NO_RIPENESS_EVIDENCE)
            notes.append(
                "No ripeness evidence is available for this zone, so no harvest status is "
                "assigned. Capture a close-up photo or load drone imagery for this zone."
            )
            health_concern = self._is_health_concern(
                health_score, risk_level, notes, reason_codes, risk_codes
            )
            status = (
                STATUS_HEALTH_CONCERN if health_concern else STATUS_NO_DATA
            )
            return self._build(
                status=status,
                ripeness_status=None,
                health_concern=health_concern,
                band=None,
                reason_codes=reason_codes,
                notes=notes,
            )

        score = float(ripeness_score)
        ripeness_status = self.ripeness_status(score)
        reason_codes.extend(self._ripeness_codes(ripeness_status))

        band_index, band = self._resolve_band(score)
        health_concern = self._is_health_concern(
            health_score, risk_level, notes, reason_codes, risk_codes
        )

        adjustment = self.config["health_risk_adjustment"]
        if (
            health_concern
            and adjustment.get("enabled", True)
            and risk_level in list(adjustment.get("risk_levels", ["high"]))
            and band_index is not None
        ):
            shift = int(adjustment.get("shift_bands_earlier_by", 1))
            new_index = max(0, band_index - shift)
            if new_index != band_index:
                notes.append(
                    f"Days-to-harvest window moved earlier by {shift} band(s) because waiting "
                    "increases the risk of crop loss."
                )
                reason_codes.append(CODE_EARLY_HARVEST_ADJUSTMENT)
                band_index = new_index
                band = self.config["days_to_harvest_bands"][band_index]

        if confidence is not None and confidence < 0.5:
            reason_codes.append(CODE_LOW_CONFIDENCE)
            notes.append(
                f"Evidence confidence is {confidence:.2f}; treat this zone's status as provisional."
            )

        concern_mode = str(self.config["health_concern"].get("mode", "override")).lower()
        if health_concern and concern_mode == "override":
            status = STATUS_HEALTH_CONCERN
            notes.append(
                "Status overridden to HEALTH_CONCERN by a high health risk; the ripeness status "
                f"({ripeness_status}) is preserved in `ripeness_status`."
            )
        else:
            status = ripeness_status
            if health_concern and concern_mode == "annotate":
                notes.append(
                    "Health concern annotated without overriding the ripeness status "
                    "(health_concern.mode = annotate)."
                )

        return self._build(
            status=status,
            ripeness_status=ripeness_status,
            health_concern=health_concern,
            band=band,
            reason_codes=reason_codes,
            notes=notes,
        )

    # -- helpers -----------------------------------------------------------
    def ripeness_status(self, score: float) -> str:
        thresholds = self.config["status_thresholds"]
        if score >= float(thresholds["harvest_ready"]):
            return STATUS_HARVEST_READY
        if score >= float(thresholds["near_ready"]):
            return STATUS_NEAR_READY
        return STATUS_NOT_READY

    def _resolve_band(self, score: float) -> tuple[int | None, dict[str, Any] | None]:
        bands = self.config["days_to_harvest_bands"]
        for index, band in enumerate(bands):
            if score >= float(band.get("min_score", 0.0)):
                return index, band
        return (len(bands) - 1, bands[-1]) if bands else (None, None)

    def _is_health_concern(
        self,
        health_score: float | None,
        risk_level: str,
        notes: list[str],
        reason_codes: list[str],
        risk_codes: Sequence[str] | None = None,
    ) -> bool:
        concern = self.config["health_concern"]
        triggering = [str(level) for level in concern.get("triggering_risk_levels", ["high"])]
        if str(risk_level) in triggering:
            if not _risk_includes_health(risk_codes):
                # The risk is contextual (weather, canopy, soil). A forecast is
                # not a crop disease, so it may annotate the status but must not
                # override a measured ripeness result with a health concern.
                notes.append(
                    f"Context data raised the risk level to {risk_level} for this zone, but no "
                    "health problem was identified, so the measured status is unchanged."
                )
                return False
            if health_score is None:
                # Context (weather, canopy) can raise risk without any health
                # measurement. Claiming a health concern here would alarm a
                # farmer about a disease that was never looked for, so the risk
                # is reported as context and the zone stays unassessed.
                notes.append(
                    "Context data (for example a weather forecast) raised the risk level for "
                    "this zone, but no image evidence of crop health exists yet, so no health "
                    "concern is claimed and no action is recommended from it."
                )
                return False
            reason_codes.append(CODE_HEALTH_RISK_HIGH)
            notes.append(
                "Overall risk for this zone is high, so harvest status carries a health concern."
            )
            return True
        threshold = concern.get("health_score_below")
        if threshold is not None and health_score is not None and health_score < float(threshold):
            reason_codes.append(CODE_HEALTH_SCORE_LOW)
            notes.append(
                f"Health score {health_score:.2f} is below the configured concern threshold "
                f"{threshold}."
            )
            return True
        return False

    @staticmethod
    def _ripeness_codes(status: str) -> list[str]:
        return {
            STATUS_HARVEST_READY: [CODE_HIGH_RIPENESS],
            STATUS_NEAR_READY: [CODE_MODERATE_RIPENESS],
            STATUS_NOT_READY: [CODE_LOW_RIPENESS],
        }.get(status, [])

    def _build(
        self,
        *,
        status: str,
        ripeness_status: str | None,
        health_concern: bool,
        band: dict[str, Any] | None,
        reason_codes: list[str],
        notes: list[str],
    ) -> HarvestDecision:
        return HarvestDecision(
            status=status,
            ripeness_status=ripeness_status,
            health_concern=health_concern,
            estimated_harvest_window=None if band is None else str(band.get("label")),
            days_to_harvest_min=None if band is None else band.get("min_days"),
            days_to_harvest_max=None if band is None else band.get("max_days"),
            recommended_action=self.actions.get(status, "CONTINUE_MONITORING"),
            reason_codes=list(dict.fromkeys(reason_codes)),
            notes=notes,
            status_label=str(
                self.config["status_labels"].get(status, status.replace("_", " ").title())
            ),
            heuristic_version=self.heuristic_version,
        )


__all__ = [
    "ALL_STATUSES",
    "DEFAULT_ACTIONS",
    "DEFAULT_HARVEST_CONFIG",
    "HarvestDecision",
    "HarvestEngine",
    "RIPENESS_STATUSES",
    "STATUS_HARVEST_READY",
    "STATUS_HEALTH_CONCERN",
    "STATUS_NEAR_READY",
    "STATUS_NO_DATA",
    "STATUS_NOT_READY",
    "resolve_harvest_config",
]


# Risk codes that mean a crop-health problem was actually detected. A zone can
# also be high risk purely from weather or canopy context, and that must not be
# reported as a health concern.
HEALTH_RISK_CODES = frozenset(
    {
        "POOR_HEALTH",
        "FAIR_HEALTH",
        "POSSIBLE_DISEASE",
        "POSSIBLE_DISEASE_INDICATOR",
        "NO_IMAGE_EVIDENCE",
    }
)


def _risk_includes_health(risk_codes: Sequence[str] | None) -> bool:
    if not risk_codes:
        # No codes supplied: fall back to the pre-existing behaviour, which the
        # risk engine's callers relied on before codes were threaded through.
        return True
    return any(str(code) in HEALTH_RISK_CODES for code in risk_codes)
