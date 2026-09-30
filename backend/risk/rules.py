"""M8 - Farm risk engine (rule-based).

Combines health evidence, weather context, crop stage, satellite anomaly and
available observations into one risk level with reason codes and the evidence
behind it.

Wording discipline (Section 13.1) is enforced here:

* Disease is never a diagnosis. A health anomaly produces the reason code
  ``POSSIBLE_DISEASE_INDICATOR`` and the message
  "possible disease indicator ... requires local confirmation".
* A rule reports the evidence it used, so the level is auditable.
"""

from __future__ import annotations

import numpy as np

RISK_NONE = "none"
RISK_LOW = "low"
RISK_MEDIUM = "medium"
RISK_HIGH = "high"
RISK_LEVELS = (RISK_NONE, RISK_LOW, RISK_MEDIUM, RISK_HIGH)

# Reason codes. Stable identifiers used by the recommendation layer.
CODE_POSSIBLE_DISEASE = "POSSIBLE_DISEASE_INDICATOR"
CODE_POOR_HEALTH = "POOR_HEALTH_SCORE"
CODE_FAIR_HEALTH = "FAIR_HEALTH_SCORE"
CODE_HEAVY_RAIN = "HEAVY_RAIN_FORECAST"
CODE_RAIN = "RAIN_FORECAST"
CODE_HEAT_STRESS = "HEAT_STRESS_RISK"
CODE_STRONG_WIND = "STRONG_WIND_RISK"
CODE_CANOPY_ANOMALY = "CANOPY_CONDITION_ANOMALY"
CODE_LOW_SOIL_MOISTURE = "LOW_SOIL_MOISTURE"
CODE_LOSS_PRESSURE = "HIGH_LOSS_PRESSURE_CROP_STAGE"
CODE_LOW_CONFIDENCE = "LOW_EVIDENCE_CONFIDENCE"
CODE_NO_IMAGE_EVIDENCE = "NO_IMAGE_EVIDENCE"

CONFIRMATION_NOTE = "requires local confirmation"

DEFAULT_RISK_CONFIG: dict = {
    "health_score_levels": {"high_below": 0.45, "medium_below": 0.70},
    "weather": {
        "heavy_rain_probability": 0.60,
        "heavy_rain_window_days": 3,
        "heat_risk_temperature_c": 38.0,
        "heat_risk_window_days": 3,
        "strong_wind_kph": 30.0,
    },
    "satellite": {"anomaly_drop_threshold": 0.08, "healthy_index_floor": 0.35},
    "soil": {"moisture_below": 0.20, "ph_min": 5.0, "ph_max": 8.5},
    "crop_stage": {
        "loss_pressure_high": ["ripening", "harvest"],
        "loss_pressure_low": ["flowering", "fruit_set"],
    },
    "confidence": {
        "min_confidence_to_escalate": 0.40,
        "min": 0.10,
        "max": 0.95,
    },
    "levels": list(RISK_LEVELS),
}


def resolve_risk_config(config: dict | None) -> dict:
    resolved = {
        "health_score_levels": dict(DEFAULT_RISK_CONFIG["health_score_levels"]),
        "weather": dict(DEFAULT_RISK_CONFIG["weather"]),
        "satellite": dict(DEFAULT_RISK_CONFIG["satellite"]),
        "soil": dict(DEFAULT_RISK_CONFIG["soil"]),
        "crop_stage": dict(DEFAULT_RISK_CONFIG["crop_stage"]),
        "confidence": dict(DEFAULT_RISK_CONFIG["confidence"]),
        "levels": list(DEFAULT_RISK_CONFIG["levels"]),
    }
    for key, value in (config or {}).items():
        if key in resolved and isinstance(value, dict):
            resolved[key] = {**resolved[key], **value}
        elif key in resolved:
            resolved[key] = value
    return resolved
