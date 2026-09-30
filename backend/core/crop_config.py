"""YAML configuration loading (crop profiles + thresholds).

``configs/crops/mango.yaml`` and ``configs/thresholds/mango.yaml`` are the only
place crop-specific numbers live. Python modules read them through
:class:`ThresholdConfig` / :class:`CropConfig`.

Loading is cached per (crop, file mtime) so tests can rewrite a YAML file and
pick the change up without a process restart.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.core.config import get_settings
from backend.core.errors import BadRequestError, NotFoundError

_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML file, returning {} when absent (so optional configs work)."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise BadRequestError(f"Config file {path.name} must contain a mapping at the top level.")
    return data


def _cached(path: Path, key: str) -> dict[str, Any]:
    resolved = path.resolve()
    mtime = resolved.stat().st_mtime if resolved.exists() else 0.0
    with _lock:
        hit = _cache.get((str(resolved), key))
        if hit is not None and hit[0] == mtime:
            return hit[1]
    data = _load_yaml(resolved)
    with _lock:
        _cache[(str(resolved), key)] = (mtime, data)
    return data


def clear_config_cache() -> None:
    """Test helper."""
    with _lock:
        _cache.clear()


def _section(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    value = data.get(name)
    if value is None:
        raise NotFoundError(f"Config section '{name}' missing from {path.name}.")
    if not isinstance(value, dict):
        raise BadRequestError(f"Config section '{name}' in {path.name} must be a mapping.")
    return value


@dataclass(frozen=True)
class ThresholdConfig:
    """All tunable heuristics for one crop, straight from YAML.

    Exposes ``raw`` so callers can read optional keys without a dedicated
    accessor, plus typed properties for the values used on hot paths.
    """

    crop: str
    heuristic_version: str
    validated: bool
    disclaimer: str
    raw: dict[str, Any]

    # -- convenience accessors ---------------------------------------------
    @property
    def zones(self) -> dict[str, Any]:
        return self.raw["zones"]

    @property
    def quality_gate(self) -> dict[str, Any]:
        return self.raw["quality_gate"]

    @property
    def preprocessing(self) -> dict[str, Any]:
        return self.raw["preprocessing"]

    @property
    def fruit_detection(self) -> dict[str, Any]:
        return self.raw["fruit_detection"]

    @property
    def fusion(self) -> dict[str, Any]:
        return self.raw["fusion"]

    @property
    def harvest(self) -> dict[str, Any]:
        return self.raw["harvest"]

    @property
    def risk(self) -> dict[str, Any]:
        return self.raw["risk"]

    @property
    def actions(self) -> dict[str, str]:
        return self.raw["actions"]

    @property
    def hotspots(self) -> dict[str, Any]:
        return self.raw["hotspots"]

    @property
    def gemini(self) -> dict[str, Any]:
        return self.raw["gemini"]


@dataclass(frozen=True)
class CropConfig:
    crop: str
    raw: dict[str, Any]

    @property
    def display_name(self) -> str:
        return self.raw.get("display_name", self.crop.title())

    @property
    def varieties(self) -> dict[str, dict[str, Any]]:
        return {item["id"]: item for item in self.raw.get("varieties", [])}

    @property
    def default_variety(self) -> str:
        return self.raw.get("default_variety", "unknown")

    @property
    def sources(self) -> dict[str, dict[str, Any]]:
        return self.raw.get("sources", {})

    @property
    def crop_stages(self) -> list[dict[str, Any]]:
        return self.raw.get("crop_stages", [])

    @property
    def default_crop_stage(self) -> str:
        return self.raw.get("default_crop_stage", "fruit_development")

    @property
    def stage_ids(self) -> list[str]:
        return [stage["id"] for stage in self.crop_stages]

    @property
    def languages(self) -> dict[str, Any]:
        return self.raw.get("languages", {})

    @property
    def primary_language(self) -> str:
        return self.languages.get("primary", "ta")

    @property
    def supported_languages(self) -> list[str]:
        return list(self.languages.get("supported", ["ta", "en"]))

    def variety(self, variety_id: str | None) -> dict[str, Any]:
        varieties = self.varieties
        if variety_id and variety_id in varieties:
            return varieties[variety_id]
        return varieties.get(self.default_variety, {"id": "unknown", "confidence_multiplier": 1.0})

    def is_valid_stage(self, stage_id: str) -> bool:
        return stage_id in self.stage_ids

    def is_valid_source(self, source: str) -> bool:
        return source in self.sources

    def source_carries_image(self, source: str) -> bool:
        return bool(self.sources.get(source, {}).get("image", False))


def thresholds_path(crop: str) -> Path:
    return get_settings().config_dir / "thresholds" / f"{crop}.yaml"


def crop_path(crop: str) -> Path:
    return get_settings().config_dir / "crops" / f"{crop}.yaml"


def load_thresholds(crop: str) -> ThresholdConfig:
    path = thresholds_path(crop)
    data = _cached(path, "thresholds")
    if not data:
        raise NotFoundError(
            f"No threshold configuration for crop '{crop}'. "
            f"Expected {path.name} under configs/thresholds/."
        )
    return ThresholdConfig(
        crop=data.get("crop", crop),
        heuristic_version=data.get("heuristic_version", "heuristic-v0"),
        validated=bool(data.get("validated", False)),
        disclaimer=data.get("disclaimer", ""),
        raw=data,
    )


def load_crop_config(crop: str) -> CropConfig:
    path = crop_path(crop)
    data = _cached(path, "crop")
    if not data:
        raise NotFoundError(
            f"No crop configuration for crop '{crop}'. "
            f"Expected {path.name} under configs/crops/."
        )
    return CropConfig(crop=data.get("crop", crop), raw=data)


def list_available_crops() -> list[str]:
    directory = get_settings().config_dir / "crops"
    if not directory.exists():
        return []
    return sorted(path.stem for path in directory.glob("*.yaml"))
