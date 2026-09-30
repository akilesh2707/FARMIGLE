"""Analysis orchestrator: the Farm Digital Twin update cycle.

This is the only place that knows the full pipeline order:

    observations -> perception (CV) -> fusion -> risk -> harvest
                 -> recommendation -> persistence -> harvest map

Design rules that come straight from the documentation:

* Gemini is not in this chain as a decision maker. It is called from the
  recommendation tier, which only receives facts.
* A failure in one zone never aborts the other zones; the zone is reported as
  degraded and the run continues.
* Every emitted document carries ``heuristic_version`` and
  ``heuristic_validated: false`` so a demo can never be read as agronomic truth.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.core.crop_config import CropConfig, ThresholdConfig, load_crop_config, load_thresholds
from backend.core.errors import ImageQualityError, ObservationNotFoundError
from backend.core.firestore import Repository
from backend.core.logging import get_logger
from backend.core.utils import new_id, utc_now_iso
from backend.drone.service import DroneAnalysisService
from backend.fusion.engine import FusionEngine
from backend.fusion.models import SourceEvidence, ZoneFusionInput
from backend.ground.service import GroundAnalysisService
from backend.harvest.engine import STATUS_NO_DATA, HarvestDecision, HarvestEngine
from backend.multilingual.service import MultilingualService
from backend.observations.service import ObservationService
from backend.recommendations.service import RecommendationService
from backend.risk.engine import RiskEngine, RiskInput
from backend.risk.weather import WeatherContext, WeatherProvider, build_weather_provider
from backend.satellite.base import SatelliteContext, SatelliteProvider
from backend.satellite.providers import build_satellite_provider
from geospatial.geojson.harvest_map import build_harvest_map

logger = get_logger(__name__)
logging.getLogger(__name__)

MAX_IMAGE_OBSERVATIONS = 60


@dataclass
class ZoneOutcome:
    """Everything produced for a single zone in one run."""

    zone_id: str
    zone_label: str | None
    status: str
    result: dict[str, Any]
    risk: dict[str, Any]
    recommendation: dict[str, Any] | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "zone_id": self.zone_id,
            "zone_label": self.zone_label,
            "status": self.status,
            "result": self.result,
            "risk": self.risk,
            "recommendation": self.recommendation,
            "errors": list(self.errors),
        }


@dataclass
class AnalysisRun:
    run_id: str
    farm_id: str
    crop: str
    crop_stage: str
    language: str
    analyzed_at: str
    zones: list[ZoneOutcome] = field(default_factory=list)
    weather: dict[str, Any] | None = None
    satellite: dict[str, Any] | None = None
    harvest_map: dict[str, Any] | None = None
    harvest_map_uri: str | None = None
    duration_ms: int = 0
    is_mock: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self, *, include_map: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": self.run_id,
            "farm_id": self.farm_id,
            "crop": self.crop,
            "crop_stage": self.crop_stage,
            "language": self.language,
            "analyzed_at": self.analyzed_at,
            "zones": [zone.result for zone in self.zones],
            "zone_details": [zone.to_dict() for zone in self.zones],
            "status_counts": self.status_counts(),
            "risk_counts": self.risk_counts(),
            "weather": self.weather,
            "satellite": self.satellite,
            "recommendations": [
                zone.recommendation for zone in self.zones if zone.recommendation
            ],
            "harvest_map_uri": self.harvest_map_uri,
            "duration_ms": self.duration_ms,
            "is_mock": self.is_mock,
            "notes": list(self.notes),
            "heuristic_version": "heuristic-v0",
            "heuristic_validated": False,
        }
        if include_map:
            payload["harvest_map"] = self.harvest_map
        return payload

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for zone in self.zones:
            counts[zone.status] = counts.get(zone.status, 0) + 1
        return counts

    def risk_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for zone in self.zones:
            level = str(zone.risk.get("risk_level", "none"))
            counts[level] = counts.get(level, 0) + 1
        return counts

    def zone_documents(self) -> list[dict[str, Any]]:
        return [
            {**zone.result, "farm_id": self.farm_id, "run_id": self.run_id}
            for zone in self.zones
        ]


class AnalysisOrchestrator:
    """Runs the full deterministic pipeline for one farm."""

    def __init__(
        self,
        *,
        repository: Repository,
        observations: ObservationService,
        ground: GroundAnalysisService | None = None,
        drone: DroneAnalysisService | None = None,
        fusion: FusionEngine | None = None,
        risk: RiskEngine | None = None,
        harvest: HarvestEngine | None = None,
        recommendations: RecommendationService | None = None,
        satellite: SatelliteProvider | None = None,
        weather: WeatherProvider | None = None,
        storage: Any | None = None,
        multilingual: MultilingualService | None = None,
        crop: str | None = None,
    ) -> None:
        self.repository = repository
        self.observations = observations
        self.crop = crop or "mango"
        self.thresholds: ThresholdConfig = load_thresholds(self.crop)
        self.crop_config: CropConfig = load_crop_config(self.crop)
        self.ground = ground or GroundAnalysisService.from_config(
            crop_config=self.crop_config, thresholds=self.thresholds
        )
        self.drone = drone or DroneAnalysisService(self.ground)
        self.fusion = fusion or FusionEngine.from_thresholds(self.thresholds)
        self.risk = risk or RiskEngine.from_thresholds(self.thresholds)
        self.harvest = harvest or HarvestEngine.from_thresholds(self.thresholds)
        self.multilingual = multilingual or MultilingualService()
        self.satellite = satellite or build_satellite_provider()
        self.weather = weather or build_weather_provider()
        self.storage = storage
        self.recommendations = recommendations or RecommendationService(
            crop=self.crop,
            heuristic_version=self._heuristic_version(),
            translator=self._translate,
            thresholds=self.thresholds,
        )

    # -- public API --------------------------------------------------------
    def analyze_farm(
        self,
        farm: dict[str, Any],
        *,
        crop_stage: str | None = None,
        language: str | None = None,
        zone_ids: list[str] | None = None,
        tier: str | None = None,
        include_recommendations: bool = True,
        include_weather: bool = True,
        include_satellite: bool = True,
        persist: bool = True,
    ) -> AnalysisRun:
        started = time.perf_counter()
        run_id = new_id("run")
        resolved_stage = crop_stage or str(farm.get("crop_stage") or self.crop_config.default_crop_stage)
        resolved_language = language or str(farm.get("language") or "en")
        notes: list[str] = []

        weather_context = self._fetch_weather(farm, include_weather, notes)
        satellite_context = self._fetch_satellite(farm, include_satellite, notes)

        evidence = self._collect_evidence(farm, notes)
        zones = self._select_zones(farm, zone_ids)

        outcomes: list[ZoneOutcome] = []
        for zone in zones:
            zone_id = str(zone.get("zone_id"))
            try:
                outcomes.append(
                    self._analyze_zone(
                        farm=farm,
                        zone=zone,
                        run_id=run_id,
                        crop_stage=resolved_stage,
                        language=resolved_language,
                        tier=tier,
                        evidence=evidence,
                        weather=weather_context,
                        satellite=satellite_context,
                        include_recommendation=include_recommendations,
                    )
                )
            except Exception as exc:  # one bad zone must not kill the run
                logger.exception("zone_analysis_failed", extra={"zone_id": zone_id})
                notes.append(f"zone {zone_id} failed: {exc}")
                outcomes.append(
                    self._degraded_zone(
                        zone_id,
                        zone,
                        resolved_stage,
                        str(exc),
                        farm_id=str(farm.get("farm_id")),
                    )
                )

        run = AnalysisRun(
            run_id=run_id,
            farm_id=str(farm.get("farm_id")),
            crop=str(farm.get("crop") or self.crop),
            crop_stage=resolved_stage,
            language=resolved_language,
            analyzed_at=utc_now_iso(),
            zones=outcomes,
            weather=weather_context.to_dict() if weather_context else None,
            satellite=_satellite_summary(satellite_context),
            duration_ms=int((time.perf_counter() - started) * 1000),
            is_mock=bool(
                getattr(self.satellite, "is_mock", True)
                or getattr(self.weather, "is_mock", True)
                or getattr(self.ground, "is_mock", True)
            ),
            notes=notes,
        )
        run.harvest_map = build_harvest_map(
            farm, {zone.zone_id: zone.result for zone in run.zones}
        )
        if persist:
            run.harvest_map_uri = self._persist_map(farm, run)
            self._persist_run(run)

        logger.info(
            "farm_analyzed",
            extra={
                "farm_id": run.farm_id,
                "run_id": run.run_id,
                "zones": len(run.zones),
                "duration_ms": run.duration_ms,
            },
        )
        return run

    def analyze_observation(
        self, farm: dict[str, Any], observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Run the vision pipeline for a single stored observation.

        Returns the perception payload plus, when the observation is tied to a
        zone, the recommendation for that zone.
        """
        observation_id = str(observation.get("observation_id", ""))
        if not observation_id:
            raise ObservationNotFoundError(str(observation.get("farm_id")))

        source = str(observation.get("source") or "phone")
        payload = self.perceive(farm, observation)
        result: dict[str, Any] = {
            "farm_id": observation.get("farm_id"),
            "observation_id": observation_id,
            "zone_id": observation.get("zone_id"),
            "source": source,
            **payload,
        }

        zone_id = observation.get("zone_id")
        if zone_id:
            outcome = self._analyze_zone(
                farm=farm,
                zone=self._zone_or_stub(farm, str(zone_id)),
                run_id=new_id("run"),
                crop_stage=str(farm.get("crop_stage") or self.crop_config.default_crop_stage),
                language=str(farm.get("language") or "en"),
                tier=None,
                evidence={str(zone_id): {source: _require_evidence(source, payload)}},
                weather=None,
                satellite=None,
                include_recommendation=True,
            )
            result["zone_result"] = outcome.result
            result["risk"] = outcome.risk
            result["recommendation"] = outcome.recommendation
            result["status"] = outcome.status
        return result

    def perceive(self, farm: dict[str, Any], observation: dict[str, Any]) -> dict[str, Any]:
        """Perception only (no fusion/risk/harvest), for the image endpoint."""
        source = str(observation.get("source") or "phone")
        image_bytes = self.observations.load_image_bytes(observation)
        if not image_bytes:
            return {
                "accepted": False,
                "rejection_reason": "image_asset_unavailable",
                "is_mock": True,
            }
        try:
            if source == "drone":
                assignment, evidence = self.drone.analyze(
                    farm, image_bytes, zone_id=observation.get("zone_id")
                )
                payload = evidence.to_dict()
                payload["zone_assignment"] = assignment.to_dict()
            else:
                evidence = self.ground.analyze(image_bytes, source=source)
                payload = evidence.to_dict()
        except ImageQualityError as error:
            return {
                "accepted": False,
                "rejection_reason": error.code,
                "rejection_message": error.message,
                "rejection_details": dict(error.details),
                "is_mock": False,
            }
        return _perception_payload(payload, source=source, thresholds=self.thresholds)

    @staticmethod
    def _zone_or_stub(farm: dict[str, Any], zone_id: str) -> dict[str, Any]:
        for zone in farm.get("zones") or []:
            if str(zone.get("zone_id")) == zone_id:
                return zone
        return {"zone_id": zone_id, "label": None}

    def latest_results(self, farm_id: str) -> dict[str, dict[str, Any]]:
        return self.repository.latest_zone_results(farm_id)

    def harvest_map(self, farm: dict[str, Any], *, persist: bool = False) -> dict[str, Any]:
        results = self.repository.latest_zone_results(str(farm.get("farm_id")))
        collection = build_harvest_map(farm, results)
        if persist and self.storage is not None:
            self._save_map(farm, collection, "latest")
        return collection

    # -- zone pipeline -----------------------------------------------------
    def _analyze_zone(
        self,
        *,
        farm: dict[str, Any],
        zone: dict[str, Any],
        run_id: str,
        crop_stage: str,
        language: str,
        tier: str | None,
        evidence: dict[str, dict[str, SourceEvidence]],
        weather: WeatherContext | None,
        satellite: SatelliteContext | None,
        include_recommendation: bool,
    ) -> ZoneOutcome:
        zone_id = str(zone.get("zone_id"))
        zone_label = zone.get("label")
        errors: list[str] = []

        fusion_input = ZoneFusionInput(
            zone_id=zone_id,
            zone_label=zone_label,
            crop_stage=crop_stage,
        )
        for source, item in (evidence.get(zone_id) or {}).items():
            fusion_input = fusion_input.with_evidence(item)

        zone_satellite = satellite.zones.get(zone_id) if satellite else None
        if zone_satellite is not None:
            fusion_input = ZoneFusionInput(
                zone_id=fusion_input.zone_id,
                zone_label=fusion_input.zone_label,
                crop_stage=fusion_input.crop_stage,
                evidence=fusion_input.evidence,
                context={**fusion_input.context, "satellite": zone_satellite.to_dict()},
            )
        if weather is not None:
            fusion_input = ZoneFusionInput(
                zone_id=fusion_input.zone_id,
                zone_label=fusion_input.zone_label,
                crop_stage=fusion_input.crop_stage,
                evidence=fusion_input.evidence,
                context={**fusion_input.context, "weather": weather.to_dict()},
            )

        fusion_result = self.fusion.fuse(fusion_input)

        indicators: list[str] = []
        has_image_evidence = bool(fusion_input.evidence)
        for item in fusion_input.evidence.values():
            indicators.extend(item.detail.get("possible_indicators") or [])

        risk_assessment = self.risk.assess(
            RiskInput(
                zone_id=zone_id,
                health_score=fusion_result.health_score,
                fusion_confidence=fusion_result.confidence,
                weather=weather,
                satellite=zone_satellite,
                crop_stage=crop_stage,
                possible_health_indicators=_dedupe(indicators),
                has_image_evidence=has_image_evidence,
            )
        )

        harvest_decision = self.harvest.decide(
            ripeness_score=fusion_result.ripeness_score,
            health_score=fusion_result.health_score,
            risk_level=risk_assessment.risk_level,
            confidence=fusion_result.confidence,
            risk_codes=risk_assessment.risk_codes,
        )

        recommendation: dict[str, Any] | None = None
        if include_recommendation:
            try:
                recommendation = self.recommendations.generate(
                    farm_id=str(farm.get("farm_id")),
                    zone_id=zone_id,
                    zone_label=zone_label,
                    fusion=fusion_result,
                    risk=risk_assessment,
                    harvest=harvest_decision,
                    weather=weather.to_dict() if weather else None,
                    satellite=zone_satellite.to_dict() if zone_satellite else None,
                    crop_stage=crop_stage,
                    language=language,
                    tier=tier,
                ).model_dump()
            except Exception as exc:
                errors.append(f"recommendation_failed: {exc}")
                logger.exception("recommendation_failed", extra={"zone_id": zone_id})

        result = {
            **fusion_result.to_dict(),
            "zone_result_id": new_id("zr"),
            "farm_id": farm.get("farm_id"),
            "run_id": run_id,
            "status": harvest_decision.status,
            "status_label": harvest_decision.status_label,
            "ripeness_status": harvest_decision.ripeness_status,
            "health_concern": harvest_decision.health_concern,
            "health_status": risk_assessment.health_status,
            "risk_level": risk_assessment.risk_level,
            "risk_codes": list(risk_assessment.risk_codes),
            "estimated_harvest_window": harvest_decision.estimated_harvest_window,
            "days_to_harvest_min": harvest_decision.days_to_harvest_min,
            "days_to_harvest_max": harvest_decision.days_to_harvest_max,
            "recommended_action": harvest_decision.recommended_action,
            "reason_codes": list(harvest_decision.reason_codes),
            "needs_local_confirmation": risk_assessment.needs_local_confirmation,
            "notes": _dedupe(list(harvest_decision.notes) + list(fusion_result.notes) + errors),
            "analyzed_at": utc_now_iso(),
            "heuristic_version": harvest_decision.heuristic_version,
            "heuristic_validated": False,
            "crop_stage": crop_stage,
            "language": language,
        }

        return ZoneOutcome(
            zone_id=zone_id,
            zone_label=zone_label,
            status=harvest_decision.status,
            result=result,
            risk=risk_assessment.to_dict(),
            recommendation=recommendation,
            errors=errors,
        )

    def _degraded_zone(
        self,
        zone_id: str,
        zone: dict[str, Any],
        crop_stage: str,
        error: str,
        *,
        farm_id: str = "",
    ) -> ZoneOutcome:
        """A zone whose pipeline raised: reported honestly, never faked."""
        decision = self._safe_no_data_decision(error)
        result = {
            "zone_result_id": new_id("zr"),
            "farm_id": farm_id,
            "zone_id": zone_id,
            "zone_label": zone.get("label"),
            "run_id": None,
            "ripeness_score": None,
            "health_score": None,
            "status": decision.status,
            "status_label": decision.status_label,
            "ripeness_status": decision.ripeness_status,
            "health_concern": decision.health_concern,
            "health_status": "unknown",
            "risk_level": "none",
            "risk_codes": [],
            "risk_evidence": [],
            "confidence": 0.0,
            "estimated_harvest_window": decision.estimated_harvest_window,
            "days_to_harvest_min": decision.days_to_harvest_min,
            "days_to_harvest_max": decision.days_to_harvest_max,
            "contributions": {},
            "context": {},
            "is_mock": True,
            "sources_used": [],
            "missing_sources": sorted(self.fusion.config["weights"]),
            "evidence_insufficient": True,
            "reason_codes": ["NO_RIPENESS_EVIDENCE"],
            "recommended_action": "CAPTURE_EVIDENCE",
            "notes": [f"analysis_failed: {error}"] + list(decision.notes),
            "needs_local_confirmation": False,
            "analyzed_at": utc_now_iso(),
            "crop_stage": crop_stage,
            "heuristic_version": decision.heuristic_version,
            "heuristic_validated": False,
            "degraded": True,
        }
        return ZoneOutcome(
            zone_id=zone_id,
            zone_label=zone.get("label"),
            status=decision.status,
            result=result,
            risk={"risk_level": "none", "risk_codes": [], "confidence": 0.0, "evidence": []},
            errors=[error],
        )

    def _safe_no_data_decision(self, error: str) -> Any:
        """NO_DATA decision for a failed zone.

        The harvest engine may be the component that just raised, so the
        fallback is derived from the config rather than from that engine, and a
        static decision is used if even that fails.
        """
        try:
            return self.harvest.decide(
                ripeness_score=None, health_score=None, risk_level="none"
            )
        except Exception:  # pragma: no cover - defence in depth
            logger.exception("harvest_fallback_failed", extra={"detail": error})
            return HarvestDecision(
                status=STATUS_NO_DATA,
                ripeness_status=None,
                health_concern=False,
                estimated_harvest_window=None,
                days_to_harvest_min=None,
                days_to_harvest_max=None,
                recommended_action="CAPTURE_EVIDENCE",
                reason_codes=["NO_RIPENESS_EVIDENCE"],
                notes=[
                    "The analysis pipeline failed for this zone, so no status was "
                    "assigned. Please capture a close-up photo of this zone."
                ],
                status_label="No data",
                heuristic_version=self._heuristic_version(),
            )

    # -- evidence ----------------------------------------------------------
    def _collect_evidence(
        self, farm: dict[str, Any], notes: list[str]
    ) -> dict[str, dict[str, SourceEvidence]]:
        """Run the CV pipeline on the latest observation per zone and source.

        One image per (zone, role): the highest-confidence one, which is what
        the fusion engine expects. Roles are ``ground`` (phone/rover) and
        ``drone``.
        """
        farm_id = str(farm.get("farm_id"))
        observations = self.observations.image_observations(farm_id, limit=MAX_IMAGE_OBSERVATIONS)
        if not observations:
            notes.append(
                "No image observations were available, so every zone is reported as NO_DATA."
            )
            return {}

        evidence: dict[str, dict[str, SourceEvidence]] = {}
        used_roles: dict[tuple[str, str], float] = {}

        for observation in observations:
            zone_id = observation.get("zone_id")
            source = str(observation.get("source"))
            if not zone_id:
                continue
            payload = self.perceive(farm, observation)
            if not payload.get("accepted", False):
                notes.append(
                    f"observation {observation.get('observation_id')} for zone {zone_id} was "
                    f"rejected: {payload.get('rejection_reason')}"
                )
                continue
            evidence_item = _require_evidence(source, payload)
            key = (str(zone_id), evidence_item.role)
            previous = used_roles.get(key)
            if previous is not None and previous >= evidence_item.confidence:
                continue
            used_roles[key] = evidence_item.confidence
            evidence.setdefault(str(zone_id), {})[source] = evidence_item

        return evidence

    @staticmethod
    def _select_zones(farm: dict[str, Any], zone_ids: list[str] | None) -> list[dict[str, Any]]:
        zones = list(farm.get("zones") or [])
        if not zone_ids:
            return zones
        wanted = {str(zone_id) for zone_id in zone_ids}
        selected = [zone for zone in zones if str(zone.get("zone_id")) in wanted]
        if not selected:
            from backend.core.errors import ZoneNotFoundError

            raise ZoneNotFoundError(",".join(sorted(wanted)))
        return selected

    # -- context providers -------------------------------------------------
    def _fetch_weather(
        self, farm: dict[str, Any], enabled: bool, notes: list[str]
    ) -> WeatherContext | None:
        if not enabled:
            return None
        center = farm.get("center") or farm.get("centroid") or {}
        try:
            context = self.weather.fetch(center, thresholds=self.thresholds)
        except Exception as exc:
            logger.warning("weather_unavailable", extra={"error": str(exc)})
            notes.append(f"weather unavailable: {exc}")
            return None
        if not context.available:
            notes.append(
                "Weather context is unavailable, so no weather reason codes are reported."
            )
        return context

    def _fetch_satellite(
        self, farm: dict[str, Any], enabled: bool, notes: list[str]
    ) -> SatelliteContext | None:
        if not enabled:
            return None
        try:
            context = self.satellite.fetch(farm, thresholds=self.thresholds)
        except Exception as exc:
            logger.warning("satellite_unavailable", extra={"error": str(exc)})
            notes.append(f"satellite context unavailable: {exc}")
            return None
        if context.anomalous_zone_ids:
            notes.append(
                "Satellite canopy anomalies in: " + ", ".join(context.anomalous_zone_ids) + "."
            )
        return context

    # -- persistence -------------------------------------------------------
    def _persist_run(self, run: AnalysisRun) -> None:
        for zone in run.zones:
            try:
                self.repository.save_zone_result(run.farm_id, zone.result)
            except Exception as exc:
                logger.warning("zone_result_persist_failed", extra={"error": str(exc)})
        for zone in run.zones:
            if not zone.recommendation:
                continue
            try:
                self.repository.create_recommendation(run.farm_id, zone.recommendation)
            except Exception as exc:
                logger.warning("recommendation_persist_failed", extra={"error": str(exc)})
        try:
            self.repository.update_farm(
                run.farm_id,
                {
                    "latest_analysis": {
                        "run_id": run.run_id,
                        "analyzed_at": run.analyzed_at,
                        "harvest_map_uri": run.harvest_map_uri,
                        "zones_analyzed": len(run.zones),
                        "status_counts": run.status_counts(),
                        "risk_counts": run.risk_counts(),
                        "crop_stage": run.crop_stage,
                        "is_mock": run.is_mock,
                    },
                    "updated_at": utc_now_iso(),
                },
            )
        except Exception as exc:
            logger.warning("farm_update_failed", extra={"error": str(exc)})

    def _persist_map(self, farm: dict[str, Any], run: AnalysisRun) -> str | None:
        return self._save_map(farm, run.harvest_map, run.run_id)

    def _save_map(
        self, farm: dict[str, Any], collection: dict[str, Any] | None, run_id: str
    ) -> str | None:
        if not collection or self.storage is None:
            return None
        import json

        from backend.core.storage import build_object_path

        payload = json.dumps(collection, default=str).encode("utf-8")
        object_name = build_object_path(
            farm_id=str(farm.get("farm_id")),
            kind="maps",
            source="harvest",
            identifier=run_id,
            extension="geojson",
        )
        try:
            stored = self.storage.save(
                payload, object_name=object_name, content_type="application/geo+json"
            )
        except Exception as exc:
            logger.warning("harvest_map_persist_failed", extra={"error": str(exc)})
            return None
        return stored.uri

    # -- helpers -----------------------------------------------------------
    def _translate(self, text: str, language: str) -> str:
        result = self.multilingual.translation.translate(
            text, target_language=language, source_language="en"
        )
        return result.text if result.ok else ""

    def _heuristic_version(self) -> str:
        return str(getattr(self.thresholds, "heuristic_version", "heuristic-v0"))


def _perception_payload(
    evidence: dict[str, Any], *, source: str, thresholds: Any | None = None
) -> dict[str, Any]:
    """Flatten :meth:`VisualEvidence.to_dict` into the API image payload.

    The models return scores, never decisions, so the human-readable labels are
    derived here from the same config bands the risk and harvest engines use.
    """
    detection = evidence.get("detection") or {}
    ripeness = evidence.get("ripeness") or {}
    health = evidence.get("health") or {}
    return {
        "accepted": True,
        "source": evidence.get("source", source),
        "is_mock": bool(evidence.get("is_mock")),
        "confidence": evidence.get("confidence", 0.0),
        "fruit_count": detection.get("fruit_count", 0),
        "detection_confidence": detection.get("confidence", 0.0),
        "detections": detection.get("detections", []),
        "ripeness_score": ripeness.get("score"),
        "ripeness_label": ripeness.get("label")
        or _ripeness_label(ripeness.get("score"), thresholds),
        "ripeness_confidence": ripeness.get("confidence"),
        "health_score": health.get("health_score"),
        "health_label": health.get("label")
        or _health_label(health.get("health_score"), thresholds),
        "health_confidence": health.get("confidence"),
        "possible_health_indicators": list(health.get("possible_indicators") or []),
        "image_quality": (evidence.get("preprocessing") or {}).get("quality", {}),
        "preprocessing": evidence.get("preprocessing", {}),
        "notes": list(evidence.get("notes") or []),
    }


def _ripeness_label(score: Any, thresholds: Any | None) -> str | None:
    """Map a ripeness score onto the configured status bands (Section 8.1)."""
    value = _optional_float(score)
    if value is None:
        return None
    harvest = getattr(thresholds, "harvest", None) or {}
    bands = dict(harvest.get("status_thresholds") or {})
    if value >= float(bands.get("harvest_ready", 0.70)):
        return "HARVEST_READY"
    if value >= float(bands.get("near_ready", 0.40)):
        return "NEAR_READY"
    return "NOT_READY"


def _health_label(score: Any, thresholds: Any | None) -> str | None:
    """Map a health score onto healthy | watch | poor (Section 7 M8 bands)."""
    value = _optional_float(score)
    if value is None:
        return None
    risk = getattr(thresholds, "risk", None) or {}
    levels = dict(risk.get("health_score_levels") or {})
    if value < float(levels.get("high_below", 0.45)):
        return "poor"
    if value < float(levels.get("medium_below", 0.70)):
        return "watch"
    return "healthy"


def _require_evidence(source: str, payload: dict[str, Any]) -> SourceEvidence:
    """Convert an accepted perception payload into fusion evidence."""
    return SourceEvidence(
        source=source,
        ripeness_score=_optional_float(payload.get("ripeness_score")),
        health_score=_optional_float(payload.get("health_score")),
        confidence=_optional_float(payload.get("confidence")) or 0.0,
        is_mock=bool(payload.get("is_mock")),
        detail={
            "fruit_count": payload.get("fruit_count", 0),
            "ripeness_label": payload.get("ripeness_label"),
            "health_label": payload.get("health_label"),
            "possible_indicators": list(payload.get("possible_health_indicators") or []),
            "image_quality": payload.get("image_quality") or {},
        },
    )


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def _satellite_summary(context: SatelliteContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        "provider": context.provider,
        "is_simulated": context.is_simulated,
        "is_mock": context.is_mock,
        "indices_used": list(context.indices_used),
        "capture_date": context.capture_date,
        "cached": context.cached,
        "disclaimer": context.disclaimer,
        "zone_count": len(context.zones),
        "anomalous_zone_ids": list(context.anomalous_zone_ids),
        "notes": list(context.notes),
    }


__all__ = ["AnalysisOrchestrator", "AnalysisRun", "MAX_IMAGE_OBSERVATIONS", "ZoneOutcome"]
