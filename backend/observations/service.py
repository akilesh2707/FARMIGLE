"""Observation ingestion and asset storage.

Sources come from Section 12.1. Image bytes are validated by size and content
type before they touch storage, and the stored URI is what the rest of the
pipeline references - nothing re-uploads the same file twice.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from backend.core.errors import (
    FarmNotFoundError,
    InvalidAudioError,
    InvalidSourceError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
    ZoneNotFoundError,
)
from backend.core.config import get_settings
from backend.core.firestore import Repository
from backend.core.logging import get_logger
from backend.core.media import sniff_audio_content_type, sniff_image_content_type
from backend.core.storage import StorageService, build_object_path, validate_payload
from backend.core.utils import new_id, parse_iso, utc_now_iso

logger = get_logger(__name__)

IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/x-dng": ".dng",
}
AUDIO_CONTENT_TYPES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp3": ".mp3",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/flac": ".flac",
}

IMAGE_SOURCES = ("phone", "rover", "drone")
# Section 12.1 - the closed set of observation sources.
OBSERVATION_SOURCES = (
    "satellite",
    "drone",
    "phone",
    "rover",
    "farmer_report",
    "weather",
    "soil",
)
MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_AUDIO_BYTES = 10 * 1024 * 1024


def decode_base64(value: str) -> bytes:
    """Strict base64 decode with a clear error instead of a stack trace."""
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid base64 payload: {exc}") from exc


class ObservationService:
    """Creates observation documents and stores their assets."""

    def __init__(
        self,
        repository: Repository,
        storage: StorageService,
        *,
        max_image_bytes: int = MAX_IMAGE_BYTES,
        max_audio_bytes: int = MAX_AUDIO_BYTES,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.max_image_bytes = max_image_bytes
        self.max_audio_bytes = max_audio_bytes

    # -- create ------------------------------------------------------------
    def create_observation(
        self,
        farm_id: str,
        payload: dict[str, Any],
        *,
        owner_uid: str | None = None,
        content_type: str | None = None,
        size_bytes: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        """Validate, decode and record an observation.

        ``persist=False`` runs the same validation and stores nothing: the
        returned record carries its bytes inline so the vision pipeline can
        still score it, which is what ``image-analysis`` needs for a
        read-only preview.
        """
        if self.repository.get_farm(farm_id) is None:
            raise FarmNotFoundError(farm_id)

        source = str(payload.get("source", "")).strip().lower()
        if source not in OBSERVATION_SOURCES:
            raise InvalidSourceError(
                f"source must be one of {sorted(OBSERVATION_SOURCES)}",
                details={"allowed": sorted(OBSERVATION_SOURCES), "received": source or None},
            )

        zone_id = self._validate_zone(farm_id, payload.get("zone_id"))
        asset_uri: str | None = None
        image_bytes: bytes | None = None

        if payload.get("image_base64"):
            image_bytes, content_type = self._decode_image(
                str(payload["image_base64"]), str(payload.get("mime_type") or "").lower()
            )
            if persist:
                asset_uri = self._store_image(
                    farm_id, source, image_bytes, content_type, zone_id=payload.get("zone_id")
                )
        elif payload.get("image_reference"):
            asset_uri = self._validate_reference(str(payload["image_reference"]))

        recorded_at = payload.get("recorded_at")
        timestamp = self._timestamp(recorded_at)

        observation = {
            "observation_id": new_id("obs"),
            "farm_id": farm_id,
            "source": source,
            "zone_id": zone_id,
            "timestamp": timestamp,
            "recorded_at": recorded_at,
            "location": payload.get("location"),
            "metrics": payload.get("metrics") or {},
            "notes": payload.get("notes"),
            "language": str(payload.get("language") or "en"),
            "asset_uri": asset_uri,
            "image_reference": asset_uri or payload.get("image_reference"),
            "farmer_report": payload.get("farmer_report"),
            "transcript": payload.get("transcript"),
            "owner_uid": owner_uid,
            "content_type": content_type,
            "size_bytes": len(image_bytes) if image_bytes else size_bytes,
            "created_at": utc_now_iso(),
        }
        if not persist:
            observation["_image_bytes"] = image_bytes
            observation["persisted"] = False
            return observation
        created = self.repository.create_observation(farm_id, observation)
        logger.info(
            "observation_created",
            extra={
                "farm_id": farm_id,
                "observation_id": created.get("observation_id"),
                "source": source,
                "zone_id": zone_id,
                "has_asset": asset_uri is not None,
            },
        )
        return created

    def create_audio_observation(
        self,
        farm_id: str,
        audio_base64: str,
        *,
        mime_type: str = "audio/webm",
        language: str = "ta",
        zone_id: str | None = None,
        transcript: str | None = None,
        metrics: dict[str, Any] | None = None,
        owner_uid: str | None = None,
    ) -> dict[str, Any]:
        content_type = str(mime_type or "audio/webm").lower()
        try:
            payload = decode_base64(audio_base64)
        except ValueError as exc:
            raise InvalidAudioError(str(exc)) from exc
        if len(payload) > self.max_audio_bytes:
            raise PayloadTooLargeError(
                "audio is too large", details={"max_bytes": self.max_audio_bytes}
            )
        if content_type not in AUDIO_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(
                f"unsupported audio type: {content_type}",
                details={"allowed": sorted(AUDIO_CONTENT_TYPES)},
            )
        sniffed = sniff_audio_content_type(payload)
        if sniffed is None:
            raise InvalidAudioError(
                "the uploaded bytes are not recognised audio "
                "(expected webm, ogg, mpeg, wav or mp4)"
            )
        if sniffed != content_type:
            logger.info(
                "declared_content_type_mismatch",
                extra={"declared": content_type, "detected": sniffed, "kind": "audio"},
            )
            content_type = sniffed if sniffed in AUDIO_CONTENT_TYPES else content_type
        asset_uri = self._store_audio(farm_id, payload, content_type, zone_id=zone_id)
        # The nested call only sniffs content types for image payloads, so the
        # resolved audio type and size are passed in explicitly.
        return self.create_observation(
            farm_id,
            {
                "source": "farmer_report",
                "zone_id": zone_id,
                "language": language,
                "image_reference": asset_uri,
                "transcript": transcript,
                "metrics": metrics or {},
            },
            owner_uid=owner_uid,
            content_type=content_type,
            size_bytes=len(payload),
        )

    # -- read --------------------------------------------------------------
    def list_observations(
        self,
        farm_id: str,
        *,
        zone_id: str | None = None,
        source: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if self.repository.get_farm(farm_id) is None:
            raise FarmNotFoundError(farm_id)
        return self.repository.list_observations(
            farm_id, zone_id=zone_id, source=source, limit=limit
        )

    def latest_by_zone(
        self, farm_id: str, *, source: str | None = None, limit: int = 500
    ) -> dict[str, dict[str, Any]]:
        """Most recent observation per zone, keyed by ``zone_id``."""
        observations = self.repository.list_observations(
            farm_id, source=source, limit=limit
        )
        latest: dict[str, dict[str, Any]] = {}
        for observation in observations:
            zone_id = observation.get("zone_id")
            if not zone_id:
                continue
            current = latest.get(zone_id)
            if current is None or str(observation.get("timestamp", "")) >= str(
                current.get("timestamp", "")
            ):
                latest[zone_id] = observation
        return latest

    def image_observations(self, farm_id: str, *, limit: int = 500) -> list[dict[str, Any]]:
        """Observations that carry an asset the vision pipeline can read."""
        observations = self.repository.list_observations(farm_id, limit=limit)
        return [
            observation
            for observation in observations
            if observation.get("source") in IMAGE_SOURCES and observation.get("asset_uri")
        ]

    def load_image_bytes(self, observation: dict[str, Any]) -> bytes | None:
        inline = observation.get("_image_bytes")
        if inline:
            return bytes(inline)
        uri = observation.get("asset_uri") or observation.get("image_reference")
        if not uri or not str(uri).startswith(("local://", "gs://")):
            return None
        from backend.core.storage import load_bytes

        return load_bytes(self.storage, str(uri))

    def _validate_zone(self, farm_id: str, zone_id: Any) -> str | None:
        """An observation must point at a zone that actually exists on the farm.

        A dangling ``zone_id`` would never show up in any analysis, so it is
        rejected at write time instead of being silently dropped later.
        """
        if zone_id in (None, ""):
            return None
        farm = self.repository.get_farm(farm_id) or {}
        known = {
            str(zone.get("zone_id"))
            for zone in (farm.get("zones") or [])
            if zone.get("zone_id")
        }
        if not known:
            return None
        value = str(zone_id)
        if value not in known:
            raise ZoneNotFoundError(f"{farm_id}/{value}")
        return value

    # -- internals ---------------------------------------------------------
    def _decode_image(self, encoded: str, declared_type: str) -> tuple[bytes, str]:
        """Decode base64, then trust the bytes over the declared type."""
        try:
            payload = decode_base64(encoded)
        except ValueError as exc:
            raise UnsupportedMediaTypeError(str(exc)) from exc
        if not payload:
            raise UnsupportedMediaTypeError("image_base64 decoded to an empty payload")
        if len(payload) > self.max_image_bytes:
            raise PayloadTooLargeError(
                "image is too large", details={"max_bytes": self.max_image_bytes}
            )

        sniffed = sniff_image_content_type(payload)
        if sniffed is None or sniffed not in IMAGE_CONTENT_TYPES:
            raise UnsupportedMediaTypeError(
                "the uploaded bytes are not a supported image "
                f"({sniffed or 'unrecognised format'})",
                details={"allowed": sorted(IMAGE_CONTENT_TYPES)},
            )
        if declared_type and declared_type != sniffed:
            logger.info(
                "declared_content_type_mismatch",
                extra={"declared": declared_type, "detected": sniffed},
            )
        validate_payload(payload, content_type=sniffed, settings=get_settings())
        return payload, sniffed

    @staticmethod
    def _validate_reference(reference: str) -> str:
        if reference.startswith(("local://", "gs://", "http://", "https://")):
            return reference
        raise UnsupportedMediaTypeError(
            "image_reference must be a local://, gs:// or https:// URI",
        )

    def _store_image(
        self,
        farm_id: str,
        source: str,
        payload: bytes,
        content_type: str,
        *,
        zone_id: str | None = None,
    ) -> str:
        object_name = build_object_path(
            farm_id=farm_id,
            kind="image",
            source=source,
            identifier=new_id("img"),
            zone_id=zone_id,
            extension=IMAGE_CONTENT_TYPES.get(content_type, ".jpg"),
        )
        stored = self.storage.save(payload, object_name=object_name, content_type=content_type)
        if not stored or not stored.uri:
            raise UnsupportedMediaTypeError(
                "image could not be stored", details={"provider": type(self.storage).__name__}
            )
        return stored.uri

    def _store_audio(
        self, farm_id: str, payload: bytes, content_type: str, *, zone_id: str | None = None
    ) -> str:
        object_name = build_object_path(
            farm_id=farm_id,
            kind="audio",
            source="farmer_report",
            identifier=new_id("aud"),
            zone_id=zone_id,
            extension=AUDIO_CONTENT_TYPES.get(content_type, ".webm"),
        )
        stored = self.storage.save(payload, object_name=object_name, content_type=content_type)
        if not stored or not stored.uri:
            raise UnsupportedMediaTypeError(
                "audio could not be stored", details={"provider": type(self.storage).__name__}
            )
        return stored.uri

    @staticmethod
    def _timestamp(recorded_at: str | None) -> str:
        if not recorded_at:
            return utc_now_iso()
        try:
            return parse_iso(str(recorded_at)).isoformat().replace("+00:00", "Z")
        except ValueError as exc:
            raise ValueError(f"recorded_at is not a valid ISO-8601 timestamp: {exc}") from exc


__all__ = [
    "AUDIO_CONTENT_TYPES",
    "IMAGE_CONTENT_TYPES",
    "OBSERVATION_SOURCES",
    "IMAGE_SOURCES",
    "MAX_AUDIO_BYTES",
    "MAX_IMAGE_BYTES",
    "ObservationService",
    "decode_base64",
]
