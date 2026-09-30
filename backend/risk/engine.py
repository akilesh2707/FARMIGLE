"""Rule-based risk assessment."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.core.crop_config import ThresholdConfig
from backend.risk.rules import (
    CODE_CANOPY_ANOMALY,
    CODE_FAIR_HEALTH,
    CODE_HEAT_STRESS,
    CODE_HEAVY_RAIN,
    CODE_LOSS_PRESSURE,
    CODE_LOW_CONFIDENCE,
    CODE_LOW_SOIL_MOISTURE,
    CODE_NO_IMAGE_EVIDENCE,
    CODE_POOR_HEALTH,
    CODE_POSSIBLE_DISEASE,
    CODE_RAIN,
    CODE_STRONG_WIND,
    CONFIRMATION_NOTE,
    DEFAULT_RISK_CONFIG,
    RISK_HIGH,
    RISK_LEVELS,
    RISK_LOW,
    RISK_MEDIUM,
    RISK_NONE,
    resolve_risk_config,
)
from backend.risk.weather import WeatherContext
from backend.satellite.base import ZoneSatelliteObservation

# Health is only asserted where an image measured it.
HEALTH_UNKNOWN = "unknown"

_DOWNGRADE = {RISK_HIGH: RISK_MEDIUM, RISK_MEDIUM: RISK_LOW, RISK_LOW: RISK_NONE, RISK_NONE: RISK_NONE}


@dataclass
class RiskInput:
    """Everything the risk engine is allowed to consider for one zone."""

    zone_id: str
    health_score: float | None = None
    fusion_confidence: float = 0.5
    satellite: ZoneSatelliteObservation | None = None
    weather: WeatherContext | None = None
    crop_stage: str | None = None
    soil: dict[str, Any] | None = None
    possible_health_indicators: list[str] = field(default_factory=list)
    has_image_evidence: bool = False


@dataclass
class RiskAssessment:
    risk_level: str
    risk_codes: list[str]
    evidence: list[dict[str, Any]]
    confidence: float
    health_status: str = HEALTH_UNKNOWN
    messages: list[str] = field(default_factory=list)
    needs_local_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "risk_level": self.risk_level,
            "health_status": self.health_status,
            "risk_codes": list(self.risk_codes),
            "evidence": self.evidence,
            "confidence": round(float(self.confidence), 4),
            "messages": list(self.messages),
            "needs_local_confirmation": self.needs_local_confirmation,
            "disclaimer": (
                "Rule-based risk indicators only. Disease-like signals are possible "
                f"indicators and {CONFIRMATION_NOTE}."
            ),
        }


def _level_index(level: str, levels: list[str]) -> int:
    try:
        return levels.index(level)
    except ValueError:
        return 0


def _max_level(current: str, candidate: str, levels: list[str]) -> str:
    return candidate if _level_index(candidate, levels) > _level_index(current, levels) else current


class RiskEngine:
    """Transparent rule engine. Every rule emits the evidence it used."""

    def __init__(self, config: dict | None = None) -> None:
        self.config = resolve_risk_config(config)

    @classmethod
    def from_thresholds(cls, thresholds: ThresholdConfig | None) -> "RiskEngine":
        return cls(getattr(thresholds, "risk", None))

    @property
    def levels(self) -> list[str]:
        return list(self.config.get("levels", list(RISK_LEVELS)))

    def assess(self, risk_input: RiskInput) -> RiskAssessment:
        rules: list[dict[str, Any]] = []
        messages: list[str] = []
        needs_confirmation = False
        min_confidence = float(
            self.config["confidence"].get("min_confidence_to_escalate", 0.40)
        )

        # --- 1. Health evidence ------------------------------------------
        health_levels = self.config["health_score_levels"]
        if risk_input.health_score is not None:
            if risk_input.health_score < float(health_levels["high_below"]):
                rules.append(
                    self._rule(
                        CODE_POOR_HEALTH,
                        RISK_HIGH,
                        risk_input.fusion_confidence,
                        f"health score {risk_input.health_score:.2f} is below "
                        f"{health_levels['high_below']}",
                    )
                )
            elif risk_input.health_score < float(health_levels["medium_below"]):
                rules.append(
                    self._rule(
                        CODE_FAIR_HEALTH,
                        RISK_MEDIUM,
                        risk_input.fusion_confidence,
                        f"health score {risk_input.health_score:.2f} is below "
                        f"{health_levels['medium_below']}",
                    )
                )

        # --- 2. Possible disease indicator (never a diagnosis) ------------
        if risk_input.possible_health_indicators:
            level = (
                RISK_HIGH
                if (risk_input.health_score is not None and risk_input.health_score < 0.45)
                else RISK_MEDIUM
            )
            rules.append(
                self._rule(
                    CODE_POSSIBLE_DISEASE,
                    level,
                    max(risk_input.fusion_confidence, 0.35),
                    "; ".join(risk_input.possible_health_indicators),
                )
            )
            messages.append(
                "Possible disease indicator detected from image evidence; "
                f"{CONFIRMATION_NOTE} by a local agricultural officer."
            )
            needs_confirmation = True

        # --- 3. Weather context ------------------------------------------
        weather = risk_input.weather
        if weather is not None and weather.available:
            weather_config = self.config["weather"]
            weather_confidence = 0.5 if weather.is_simulated else 0.8
            rain_probability = weather.rain_probability or 0.0
            heavy_threshold = float(weather_config["heavy_rain_probability"])
            if rain_probability >= heavy_threshold or "heavy_rain" in weather.event_kinds:
                rules.append(
                    self._rule(
                        CODE_HEAVY_RAIN,
                        RISK_HIGH,
                        weather_confidence,
                        f"rain probability {rain_probability:.0%} within "
                        f"{weather_config['heavy_rain_window_days']} days",
                    )
                )
                messages.append(
                    "Heavy rain is forecast soon; mature fruit may be lost if harvest is delayed."
                )
            elif rain_probability >= 0.35 or "rain" in weather.event_kinds:
                rules.append(
                    self._rule(
                        CODE_RAIN,
                        RISK_MEDIUM,
                        weather_confidence,
                        f"rain probability {rain_probability:.0%}",
                    )
                )

            temperature = weather.temperature_max_c or weather.temperature_c or 0.0
            if temperature >= float(weather_config["heat_risk_temperature_c"]) or "heat" in weather.event_kinds:
                rules.append(
                    self._rule(
                        CODE_HEAT_STRESS,
                        RISK_MEDIUM,
                        weather_confidence,
                        f"forecast maximum temperature {temperature:.1f} C",
                    )
                )
                messages.append("High temperature expected; watch for heat stress.")

            wind = weather.wind_kph or 0.0
            if wind >= float(weather_config["strong_wind_kph"]) or "strong_wind" in weather.event_kinds:
                rules.append(
                    self._rule(
                        CODE_STRONG_WIND,
                        RISK_MEDIUM,
                        weather_confidence,
                        f"forecast wind {wind:.1f} kph",
                    )
                )

        # --- 4. Satellite canopy anomaly (contextual, never ripeness) -----
        satellite = risk_input.satellite
        if satellite is not None and satellite.anomaly_flag:
            rules.append(
                self._rule(
                    CODE_CANOPY_ANOMALY,
                    RISK_MEDIUM if (risk_input.health_score or 1.0) < 0.70 else RISK_LOW,
                    satellite.confidence,
                    "vegetation index changed beyond the configured anomaly threshold"
                    + (
                        f" ({satellite.change_from_previous_period:+.3f})"
                        if satellite.change_from_previous_period is not None
                        else ""
                    ),
                )
            )
            messages.append(
                "A canopy condition anomaly was flagged from satellite context; "
                "this indicates where to inspect, not what the fruit condition is."
            )

        # --- 5. Soil context ---------------------------------------------
        soil = risk_input.soil or {}
        moisture = soil.get("moisture")
        if moisture is not None and float(moisture) < float(
            self.config["soil"]["moisture_below"]
        ):
            rules.append(
                self._rule(
                    CODE_LOW_SOIL_MOISTURE,
                    RISK_MEDIUM,
                    0.5 if soil.get("simulated", True) else 0.75,
                    f"soil moisture {float(moisture):.2f} is below "
                    f"{self.config['soil']['moisture_below']}",
                )
            )

        # --- 6. Crop-stage loss pressure ---------------------------------
        loss_pressure = self.config["crop_stage"].get("loss_pressure_high", [])
        if risk_input.crop_stage in loss_pressure and rules:
            rules.append(
                self._rule(
                    CODE_LOSS_PRESSURE,
                    RISK_MEDIUM,
                    0.6,
                    f"crop stage '{risk_input.crop_stage}' increases the cost of waiting",
                )
            )

        # --- 7. Low-evidence and no-image annotations (never escalate) ----
        if not risk_input.has_image_evidence:
            rules.append(
                self._rule(
                    CODE_NO_IMAGE_EVIDENCE,
                    RISK_NONE,
                    0.3,
                    "no drone or ground image evidence for this zone",
                )
            )
            messages.append(
                "No close-up image evidence is available for this zone; upload a photo to "
                "improve the assessment."
            )
        if risk_input.fusion_confidence < min_confidence:
            rules.append(
                self._rule(
                    CODE_LOW_CONFIDENCE,
                    RISK_NONE,
                    risk_input.fusion_confidence,
                    f"fusion confidence {risk_input.fusion_confidence:.2f} below "
                    f"escalation floor {min_confidence}",
                )
            )

        # --- Aggregate ----------------------------------------------------
        level = RISK_NONE
        for rule in rules:
            candidate = rule["level"]
            if rule["confidence"] < min_confidence and candidate != RISK_NONE:
                original = candidate
                candidate = _DOWNGRADE[candidate]
                rule["level"] = candidate
                rule["downgraded_from"] = original
                rule["downgraded_reason"] = "rule confidence below escalation floor"
            level = _max_level(level, candidate, self.levels)

        confidences = [float(rule["confidence"]) for rule in rules] or [0.2]
        confidence = float(
            np.clip(
                np.mean(confidences),
                float(self.config["confidence"].get("min", 0.10)),
                float(self.config["confidence"].get("max", 0.95)),
            )
        )

        codes = _ordered_unique(rule["code"] for rule in rules if rule["level"] != RISK_NONE)
        return RiskAssessment(
            risk_level=level,
            risk_codes=codes,
            evidence=rules,
            confidence=confidence,
            health_status=self.health_status(risk_input),
            messages=_ordered_unique(messages),
            needs_local_confirmation=needs_confirmation,
        )

    def health_status(self, risk_input: RiskInput) -> str:
        """unknown | healthy | watch | poor, from the configured health bands.

        Used by the recommendation tier, which must not have to re-derive it.
        An unmeasured zone reports ``unknown``: defaulting to ``watch`` would
        assert a health finding for a zone nobody has looked at.
        """
        levels = self.config["health_score_levels"]
        if risk_input.health_score is None:
            return HEALTH_UNKNOWN
        if risk_input.health_score < float(levels["high_below"]):
            return "poor"
        if risk_input.health_score < float(levels["medium_below"]):
            return "watch"
        return "healthy"

    @staticmethod
    def _rule(code: str, level: str, confidence: float, detail: str) -> dict[str, Any]:
        return {
            "code": code,
            "level": level,
            "confidence": round(float(np.clip(confidence, 0.0, 1.0)), 4),
            "detail": detail,
        }


def _ordered_unique(values: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


__all__ = ["DEFAULT_RISK_CONFIG", "RiskAssessment", "RiskEngine", "RiskInput"]
