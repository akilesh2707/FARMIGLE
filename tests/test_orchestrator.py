"""End-to-end pipeline: the analysis contract and its degradation paths."""

from __future__ import annotations

import pytest

from backend.harvest.engine import HarvestEngine
from backend.recommendations.schema import GeminiRecommendationOutput

from tests.conftest import make_png


def test_full_mock_run_covers_every_zone_and_persists(container, farm) -> None:
    run = container.orchestrator.analyze_farm(farm, language="en")
    assert len(run.zones) == 20
    assert run.is_mock is True
    assert all(zone.result["heuristic_version"] == "heuristic-v0" for zone in run.zones)

    # Nothing was observed, so every zone is honestly NO_DATA - never a guess.
    assert set(run.status_counts()) == {"NO_DATA"}
    assert all(zone.result["ripeness_score"] is None for zone in run.zones)
    assert all(zone.result["evidence_insufficient"] is True for zone in run.zones)

    stored = container.repository.latest_zone_results(farm["farm_id"])
    assert len(stored) == 20
    assert run.harvest_map["type"] == "FeatureCollection"
    assert run.harvest_map_uri and run.harvest_map_uri.startswith("local://")
    assert len(container.repository.list_recommendations(farm["farm_id"])) == 20


def test_zone_results_carry_the_full_disclosure_block(container, farm) -> None:
    run = container.orchestrator.analyze_farm(farm, zone_ids=["zone_01"])
    result = run.zones[0].result
    for key in (
        "zone_id",
        "zone_label",
        "status",
        "ripeness_score",
        "health_score",
        "risk_level",
        "risk_codes",
        "confidence",
        "estimated_harvest_window",
        "sources_used",
        "missing_sources",
        "evidence_insufficient",
        "reason_codes",
        "recommended_action",
        "needs_local_confirmation",
        "heuristic_version",
        "heuristic_validated",
        "is_mock",
    ):
        assert key in result, key
    assert result["heuristic_validated"] is False


def test_observed_zone_produces_a_valid_recommendation(container, farm) -> None:
    import base64

    container.observations.create_observation(
        farm["farm_id"],
        {
            "source": "phone",
            "zone_id": "zone_07",
            "image_base64": base64.b64encode(make_png()).decode(),
        },
        owner_uid="u",
    )
    run = container.orchestrator.analyze_farm(farm, zone_ids=["zone_07"], language="en")
    outcome = run.zones[0]
    # Only image evidence may appear in sources_used. Satellite/weather are
    # context: they can move confidence and risk, never the ripeness score.
    assert outcome.result["sources_used"] == ["phone"]
    assert set(outcome.result["context_sources_used"]) >= {"satellite", "weather"}
    assert outcome.result["missing_sources"] == ["drone"]
    assert outcome.result["ripeness_score"] is not None
    assert outcome.result["ripeness_status"] in {"HARVEST_READY", "NEAR_READY", "NOT_READY"}
    assert outcome.result["health_status"] in {"healthy", "watch", "poor"}

    recommendation = outcome.recommendation
    assert recommendation is not None
    assert recommendation["action"] == outcome.result["recommended_action"]  # rules own it
    assert recommendation["risk_disclaimer"]
    assert recommendation["zone_id"] == "zone_07"
    GeminiRecommendationOutput.model_validate(
        {
            "crop": recommendation["crop"],
            "zone": recommendation["zone_id"],
            "health_status": outcome.result["health_status"],
            "ripeness_status": (outcome.result["ripeness_status"] or "not_ready").lower(),
            "risk_level": outcome.result["risk_level"],
            "evidence": recommendation["evidence"],
            "recommended_action": recommendation["action"].lower(),
            "explanation": recommendation["parts"]["explanation"],
            "confidence": recommendation["confidence"],
        }
    )


def test_one_bad_zone_does_not_abort_the_run(container, farm) -> None:
    class Exploding:
        def decide(self, **kwargs):
            raise RuntimeError("harvest engine unavailable")

    container.orchestrator.harvest = Exploding()
    run = container.orchestrator.analyze_farm(
        farm, zone_ids=["zone_01", "zone_02"], persist=True
    )
    assert len(run.zones) == 2
    for outcome in run.zones:
        assert outcome.result["degraded"] is True
        assert outcome.result["status"] == "NO_DATA"
        assert outcome.result["zone_result_id"]
    # Degraded zones are still persisted: the failure is visible, not hidden.
    assert len(container.repository.latest_zone_results(farm["farm_id"])) == 2


def test_persist_false_writes_nothing(container, farm) -> None:
    run = container.orchestrator.analyze_farm(farm, zone_ids=["zone_01"], persist=False)
    assert run.harvest_map_uri is None
    assert run.harvest_map["type"] == "FeatureCollection"
    assert container.repository.latest_zone_results(farm["farm_id"]) == {}
    assert container.repository.list_recommendations(farm["farm_id"]) == []


def test_runs_are_deterministic_for_the_same_inputs(container, farm) -> None:
    import base64

    container.observations.create_observation(
        farm["farm_id"],
        {"source": "phone", "zone_id": "zone_03", "image_base64": base64.b64encode(make_png()).decode()},
        owner_uid="u",
    )
    first = container.orchestrator.analyze_farm(farm, zone_ids=["zone_03"], persist=False)
    second = container.orchestrator.analyze_farm(farm, zone_ids=["zone_03"], persist=False)
    assert first.zones[0].result["ripeness_score"] == second.zones[0].result["ripeness_score"]
    assert first.zones[0].result["status"] == second.zones[0].result["status"]


def test_harvest_map_never_claims_ripeness_from_satellite(container, farm) -> None:
    import base64

    container.observations.create_observation(
        farm["farm_id"],
        {"source": "phone", "zone_id": "zone_01", "image_base64": base64.b64encode(make_png()).decode()},
        owner_uid="u",
    )
    run = container.orchestrator.analyze_farm(farm, zone_ids=["zone_01"])
    with_context = run.zones[0].result

    # The score is traceable to the phone image, and satellite/weather are
    # reported as context rather than as ripeness evidence.
    assert with_context["sources_used"] == ["phone"]
    assert "satellite" not in with_context["sources_used"]
    assert set(with_context["context_sources_used"]) >= {"satellite", "weather"}

    # Proof of independence: with the context providers disabled the fused
    # ripeness score must be identical, because satellite/weather cannot
    # change a fruit-ripeness measurement.
    from backend.risk.weather import unavailable as no_weather
    from backend.satellite.base import SatelliteContext

    class Dead:
        """A provider that fails the way a misconfigured one does."""

        name = "dead"
        is_mock = False

        def fetch(self, *args, **kwargs):
            raise RuntimeError("provider disabled for this test")

    # The orchestrator catches a raising provider and drops the context; the
    # weather path additionally tolerates a well-formed "unavailable" context.
    container.orchestrator.satellite = Dead()
    container.orchestrator.weather = type(
        "DeadWeather", (Dead,), {"fetch": lambda self, *a, **k: no_weather("dead", "off")}
    )()
    assert SatelliteContext is not None
    without_context = container.orchestrator.analyze_farm(
        farm, zone_ids=["zone_01"], persist=False
    ).zones[0].result
    assert without_context["ripeness_score"] == with_context["ripeness_score"]
    assert without_context["context_sources_used"] == []

    # The satellite summary says so in words too.
    notes = " ".join(run.satellite.get("notes", [])).lower()
    assert "not a measurement of fruit ripeness" in notes
    assert run.satellite.get("ripeness_score") is None

    for feature in run.harvest_map["features"]:
        properties = feature.get("properties", {})
        if properties.get("feature_type") == "farm_boundary":
            continue
        assert properties.get("status") in {"NO_DATA", "NEAR_READY", "HARVEST_READY", "NOT_READY"}


def test_requested_zones_only(container, farm) -> None:
    run = container.orchestrator.analyze_farm(farm, zone_ids=["zone_05", "zone_11"])
    assert [zone.zone_id for zone in run.zones] == ["zone_05", "zone_11"]


def test_unknown_zone_is_reported_not_faked(container, farm) -> None:
    from backend.core.errors import ZoneNotFoundError

    with pytest.raises((ZoneNotFoundError, ValueError)):
        container.orchestrator.analyze_farm(farm, zone_ids=["zone_99"])


def test_health_override_is_applied_by_the_decision_layer(container, farm) -> None:
    engine = HarvestEngine.from_thresholds(container.orchestrator.thresholds)
    assert engine.decide(ripeness_score=0.9, health_score=0.2, risk_level="high").status == "HEALTH_CONCERN"


def test_weather_alone_never_creates_a_health_concern(container, farm) -> None:
    """Context data may raise risk, but must not fake a health finding.

    A heavy-rain forecast with zero images once produced `HEALTH_CONCERN` and
    `INSPECT_ZONE` for all 20 zones: a farmer would have been told to go
    inspect for disease that was never looked for.
    """
    run = container.orchestrator.analyze_farm(farm, language="ta")
    assert run.status_counts() == {"NO_DATA": 20}

    outcome = run.zones[0]
    assert outcome.result["ripeness_score"] is None
    assert outcome.result["health_score"] is None
    assert outcome.status == "NO_DATA"
    assert outcome.result["recommended_action"] == "CAPTURE_EVIDENCE"
    assert "HEALTH_RISK_HIGH" not in outcome.result["reason_codes"]

    # The forecast is still reported, as context rather than as a finding.
    assert set(outcome.result["context_sources_used"]) >= {"weather", "satellite"}
    weather_codes = [
        code
        for code in outcome.result["risk_codes"]
        if "RAIN" in code or "WEATHER" in code or "WIND" in code
    ]
    if weather_codes:
        assert any("weather" in note.lower() for note in outcome.result["notes"])
