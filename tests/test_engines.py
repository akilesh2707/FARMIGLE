"""Fusion, risk and harvest: the decision layer stays deterministic and honest."""

from __future__ import annotations

import pytest

from backend.core.crop_config import load_thresholds
from backend.fusion.engine import FusionEngine
from backend.fusion.models import SourceEvidence, ZoneFusionInput
from backend.harvest.engine import HarvestEngine
from backend.risk.engine import RiskEngine, RiskInput
from backend.risk.weather import WeatherContext, WeatherEvent

THRESHOLDS = load_thresholds("mango")


def _evidence(source: str, *, ripeness: float, health: float, confidence: float = 0.8) -> SourceEvidence:
    return SourceEvidence(
        source=source,
        ripeness_score=ripeness,
        health_score=health,
        confidence=confidence,
        is_mock=True,
    )


def _fuse(**evidence: SourceEvidence) -> object:
    engine = FusionEngine.from_thresholds(THRESHOLDS)
    return engine.fuse(
        ZoneFusionInput(
            zone_id="zone_01",
            crop_stage="fruit_development",
            evidence=dict(evidence),
        )
    )


def test_fusion_uses_ground_and_drone_roles() -> None:
    result = _fuse(
        phone=_evidence("phone", ripeness=0.8, health=0.9),
        drone=_evidence("drone", ripeness=0.4, health=0.5),
    )
    # fusion.weights: ground 0.60, drone 0.40 (configs/thresholds/mango.yaml)
    assert result.ripeness_score == pytest.approx(0.8 * 0.60 + 0.4 * 0.40)
    assert result.health_score == pytest.approx(0.9 * 0.55 + 0.5 * 0.45)
    assert set(result.sources_used) == {"phone", "drone"}
    assert result.missing_sources == []


def test_fusion_renormalizes_missing_roles_instead_of_zeroing() -> None:
    """One missing source must not drag the score toward zero."""
    both = _fuse(
        phone=_evidence("phone", ripeness=0.8, health=0.9),
        drone=_evidence("drone", ripeness=0.6, health=0.8),
    )
    ground_only = _fuse(phone=_evidence("phone", ripeness=0.8, health=0.9))
    assert ground_only.ripeness_score == pytest.approx(0.8)
    assert ground_only.ripeness_score > both.ripeness_score
    assert ground_only.missing_sources == ["drone"]
    # Missing evidence lowers confidence; it never becomes a zero score. The
    # ground role alone carries 0.60 of the weight, which is above the
    # configured 0.50 evidence ratio, so the zone is not flagged insufficient.
    assert ground_only.confidence < both.confidence
    assert ground_only.evidence_insufficient is False
    assert both.evidence_insufficient is False


def test_fusion_without_any_evidence_is_no_data() -> None:
    result = _fuse()
    assert result.ripeness_score is None
    assert result.health_score is None
    assert result.evidence_insufficient is True
    assert sorted(result.missing_sources) == ["drone", "ground"]


def test_partial_evidence_does_not_borrow_the_other_score() -> None:
    result = _fuse(phone=_evidence("phone", ripeness=0.8, health=None))
    assert result.ripeness_score == pytest.approx(0.8)
    assert result.health_score is None


# --- risk ------------------------------------------------------------------


def _risk(**overrides) -> RiskInput:
    base = {
        "zone_id": "zone_01",
        "health_score": 0.9,
        "fusion_confidence": 0.8,
        "has_image_evidence": True,
        "crop_stage": "fruit_development",
    }
    base.update(overrides)
    return RiskInput(**base)


def test_risk_levels_come_from_configured_bands() -> None:
    engine = RiskEngine.from_thresholds(THRESHOLDS)
    assert engine.assess(_risk()).risk_level == "none"
    assert engine.assess(_risk(health_score=0.6)).risk_level in {"low", "medium"}
    high = engine.assess(_risk(health_score=0.2))
    assert high.risk_level == "high"
    assert high.health_status == "poor"
    assert engine.assess(_risk(health_score=0.9)).health_status == "healthy"
    # An unmeasured zone reports no health status at all, rather than defaulting
    # to "watch" and implying a crop problem that was never looked for.
    assert engine.assess(_risk(health_score=None)).health_status == "unknown"


def test_heavy_rain_forecast_raises_risk() -> None:
    engine = RiskEngine.from_thresholds(THRESHOLDS)
    assessment = engine.assess(
        _risk(
            weather=WeatherContext(
                provider="seeded-mock",
                is_mock=True,
                is_simulated=True,
                rain_probability=0.85,
                precipitation_mm=40.0,
                forecast_window_days=2,
                weather_events=[
                    WeatherEvent(
                        kind="heavy_rain",
                        day_offset=1,
                        severity="high",
                        description="Heavy rain expected",
                    )
                ],
            )
        )
    )
    assert assessment.risk_level in {"medium", "high"}
    assert any("RAIN" in code for code in assessment.risk_codes)


def test_no_image_evidence_is_flagged_and_lowers_confidence() -> None:
    engine = RiskEngine.from_thresholds(THRESHOLDS)
    assessment = engine.assess(
        _risk(health_score=None, fusion_confidence=0.0, has_image_evidence=False)
    )
    assert assessment.confidence < 0.5
    # It is surfaced as evidence with a "none" level, so it never inflates risk.
    codes = [item["code"] for item in assessment.evidence]
    assert "NO_IMAGE_EVIDENCE" in codes
    assert assessment.risk_level == "none"


def test_satellite_anomaly_never_reports_a_ripeness_score() -> None:
    """Section 7 M4: canopy context may change risk, never ripeness."""
    from backend.satellite.base import ZoneSatelliteObservation

    engine = RiskEngine.from_thresholds(THRESHOLDS)
    assessment = engine.assess(
        _risk(
            satellite=ZoneSatelliteObservation(
                zone_id="zone_01",
                vegetation_index=0.12,
                vegetation_index_previous=0.55,
                change_from_previous_period=-0.43,
                anomaly_flag=True,
            )
        )
    )
    codes = [item["code"] for item in assessment.evidence]
    assert "CANOPY_CONDITION_ANOMALY" in codes
    assert assessment.risk_level in {"low", "medium", "high"}
    # The risk assessment carries no ripeness field at all: canopy context can
    # only change risk, never the fruit-ripeness number.
    assert not hasattr(assessment, "ripeness_score")
    assert "ripeness" not in assessment.to_dict()


# --- harvest ---------------------------------------------------------------


def test_harvest_status_bands() -> None:
    engine = HarvestEngine.from_thresholds(THRESHOLDS)
    assert engine.decide(ripeness_score=0.85, health_score=0.9, risk_level="none").status == "HARVEST_READY"
    assert engine.decide(ripeness_score=0.50, health_score=0.9, risk_level="none").status == "NEAR_READY"
    assert engine.decide(ripeness_score=0.10, health_score=0.9, risk_level="none").status == "NOT_READY"
    assert engine.decide(ripeness_score=None, health_score=None, risk_level="none").status == "NO_DATA"


def test_high_risk_shifts_the_window_earlier() -> None:
    engine = HarvestEngine.from_thresholds(THRESHOLDS)
    calm = engine.decide(ripeness_score=0.75, health_score=0.9, risk_level="none")
    risky = engine.decide(ripeness_score=0.75, health_score=0.9, risk_level="high")
    assert (risky.days_to_harvest_min or 0) < (calm.days_to_harvest_min or 0)


def test_high_risk_can_override_status_to_health_concern() -> None:
    engine = HarvestEngine.from_thresholds(THRESHOLDS)
    decision = engine.decide(ripeness_score=0.95, health_score=0.9, risk_level="high")
    assert decision.status == "HEALTH_CONCERN"
    assert decision.ripeness_status == "HARVEST_READY"  # un-overridden value is kept


def test_every_decision_is_labelled_heuristic_v0_and_unvalidated() -> None:
    engine = HarvestEngine.from_thresholds(THRESHOLDS)
    payload = engine.decide(ripeness_score=0.8, health_score=0.8, risk_level="none").to_dict()
    assert payload["heuristic_version"] == "heuristic-v0"
    assert payload["heuristic_validated"] is False


def test_context_risk_alone_never_claims_a_health_finding() -> None:
    """Weather can raise risk; it cannot assert that a crop is unhealthy."""
    engine = RiskEngine.from_thresholds(THRESHOLDS)
    assessment = engine.assess(
        _risk(
            health_score=None,
            weather=WeatherContext(
                provider="seeded-mock",
                is_mock=True,
                is_simulated=True,
                rain_probability=0.9,
                precipitation_mm=55.0,
                forecast_window_days=2,
                weather_events=[
                    WeatherEvent(
                        kind="heavy_rain",
                        day_offset=1,
                        severity="high",
                        description="Heavy rain expected",
                    )
                ],
            ),
        )
    )
    assert assessment.risk_level == "high"
    assert assessment.health_status == "unknown"
    assert "HEAVY_RAIN_FORECAST" in assessment.risk_codes

    decision = HarvestEngine.from_thresholds(THRESHOLDS).decide(
        ripeness_score=None,
        health_score=None,
        risk_level=assessment.risk_level,
        confidence=assessment.confidence,
    )
    assert decision.status == "NO_DATA"
    assert decision.health_concern is False
    assert decision.recommended_action == "CAPTURE_EVIDENCE"


def test_weather_risk_does_not_override_a_measured_ripeness_status() -> None:
    """A rain forecast may annotate a zone, never relabel it as unhealthy.

    Before this rule a heavy-rain forecast plus a healthy health score still
    produced `HEALTH_CONCERN` and `INSPECT_ZONE`, hiding the real ripeness
    priority behind a mislabelled health problem.
    """
    engine = HarvestEngine.from_thresholds(THRESHOLDS)
    decision = engine.decide(
        ripeness_score=0.78,
        health_score=0.88,
        risk_level="high",
        confidence=0.7,
        risk_codes=["HEAVY_RAIN_FORECAST"],
    )
    assert decision.health_concern is False
    # 0.78 is HARVEST_READY in the configured bands; the point is that the
    # measured status survives the contextual risk.
    assert decision.status == "HARVEST_READY"
    assert decision.recommended_action != "INSPECT_ZONE"
    assert any("Context data raised the risk level" in note for note in decision.notes)

    # A genuine health signal still overrides, per Section 8.1.
    health_decision = engine.decide(
        ripeness_score=0.78,
        health_score=0.2,
        risk_level="high",
        confidence=0.7,
        risk_codes=["POOR_HEALTH", "HEAVY_RAIN_FORECAST"],
    )
    assert health_decision.health_concern is True
    assert health_decision.status == "HEALTH_CONCERN"
