"""Application settings.

All environment-specific values are read here and nowhere else. Modules take
their configuration through constructor arguments or through
:mod:`backend.core.config`, never by calling ``os.environ`` directly, so the
mock/local and production paths stay swappable and testable.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# <repo_root>/backend/core/config.py -> parents[2] == <repo_root>
REPO_ROOT = Path(__file__).resolve().parents[2]

Environment = Literal["local", "dev", "staging", "prod"]


class Settings(BaseSettings):
    """Runtime configuration, populated from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---------------------------------------------------------------
    app_name: str = "AI Farm Intelligence Network"
    app_version: str = "0.1.0"
    environment: Environment = "local"
    debug: bool = False
    api_prefix: str = ""

    # When true every Google-backed service is replaced by its local mock.
    # The production code paths are unchanged; only the provider binding in
    # backend.core.container differs. See README "Mock / demo mode".
    mock_services: bool = True

    # --- Google Cloud ------------------------------------------------------
    gcp_project_id: str | None = None
    google_application_credentials: str | None = None
    firebase_project_id: str | None = None
    gcs_bucket: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    google_cloud_location: str = "us-central1"

    # --- Secrets (never logged, never returned by /health) -----------------
    gemini_api_key: str | None = None
    weather_api_key: str | None = None

    # --- ML providers ------------------------------------------------------
    # mock      -> deterministic clearly-labelled stand-ins (default)
    # heuristic -> the real OpenCV colour/texture modules (no weights needed)
    # yolo      -> real Ultralytics weights; requires FRUIT_DETECTOR_WEIGHTS
    ml_provider: Literal["mock", "heuristic", "yolo"] = "mock"
    ml_ripeness_provider: Literal["mock", "heuristic"] = "mock"
    ml_health_provider: Literal["mock", "heuristic"] = "mock"
    fruit_detector_weights: str | None = None
    ml_device: str = "cpu"

    # --- External services -------------------------------------------------
    # "mock" keeps the backend startable with zero cloud configuration.
    gemini_provider: Literal["mock", "vertex"] = "mock"
    satellite_provider: Literal["seeded", "earth_engine"] = "seeded"
    weather_provider: Literal["seeded", "google", "open_meteo"] = "seeded"
    speech_provider: Literal["mock", "google"] = "mock"
    # Earth Engine live calls stay off until credentials and a project are set.
    earth_engine_allow_live: bool = False

    # --- Local development substitutes -------------------------------------
    local_storage_dir: Path = Field(default=REPO_ROOT / ".local_data" / "storage")
    seed_data_dir: Path = Field(default=REPO_ROOT / "data" / "seed")
    satellite_data_dir: Path = Field(default=REPO_ROOT / "data" / "satellite")
    config_dir: Path = Field(default=REPO_ROOT / "configs")

    @property
    def prompts_dir(self) -> Path:
        return self.config_dir / "prompts"

    @property
    def google_project_id(self) -> str | None:
        """Project id used by the Google clients (Speech, Translate, TTS)."""
        return self.effective_project_id

    # --- Domain defaults ---------------------------------------------------
    default_crop: str = "mango"
    default_language: str = "ta"

    # --- CORS --------------------------------------------------------------
    # Only needed by the browser client; empty means "same origin only".
    cors_origins: list[str] = Field(default_factory=list)

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = False

    # --- Uploads -----------------------------------------------------------
    max_upload_bytes: int = 12 * 1024 * 1024
    allowed_image_content_types: list[str] = Field(
        default_factory=lambda: [
            "image/jpeg",
            "image/jpg",
            "image/png",
            "image/webp",
            "image/bmp",
        ]
    )

    @field_validator("cors_origins", "allowed_image_content_types", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Allow ``A,B`` in .env as well as a JSON list."""
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @field_validator("local_storage_dir", "seed_data_dir", "satellite_data_dir", "config_dir", mode="before")
    @classmethod
    def _resolve_path(cls, value: object) -> object:
        if isinstance(value, str) and value and not value.startswith("/"):
            return (REPO_ROOT / value).resolve()
        return value

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    @property
    def effective_project_id(self) -> str:
        """Firestore / Storage / Gemini all need a project; prefer explicit."""
        return self.gcp_project_id or self.firebase_project_id or "local-demo-project"

    def missing_production_services(self) -> list[str]:
        """Names of Google services not configured, for /health diagnostics.

        Never returns secret values, only the variable names that are unset.
        """
        if self.mock_services:
            return []
        missing: list[str] = []
        required = {
            "GCP_PROJECT_ID": self.gcp_project_id,
            "FIREBASE_PROJECT_ID": self.firebase_project_id,
            "GCS_BUCKET": self.gcs_bucket,
        }
        for name, value in required.items():
            if not value:
                missing.append(name)
        return missing


@functools.lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton (FastAPI dependency + module-level default)."""
    return Settings()


def reset_settings_cache() -> None:
    """Used by tests after mutating the environment."""
    get_settings.cache_clear()
