"""Asset storage.

One interface, two implementations:

* :class:`GcsStorageService`  - Cloud Storage (``gs://bucket/...``)
* :class:`LocalStorageService` - a directory on disk, used when
  ``MOCK_SERVICES=true`` so ingestion works with no GCP project.

Object paths are built by :func:`build_object_path` and are deterministic given
(farm, source, zone, observation id), which keeps tests reproducible.
"""

from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from backend.core.config import Settings, get_settings
from backend.core.errors import NotFoundError, PayloadTooLargeError, ProviderUnavailableError
from backend.core.logging import get_logger
from backend.core.utils import parse_iso, utc_now

logger = get_logger(__name__)

IMAGE_CONTENT_TYPES = ("image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp")
AUDIO_CONTENT_TYPES = ("audio/webm", "audio/ogg", "audio/mpeg", "audio/wav", "audio/mp4", "audio/x-m4a")

_SAFE_TOKEN = str.maketrans({c: "_" for c in " !@#$%^&*()+=[]{};':\",./<>?\\|`~"})


def safe_component(value: str) -> str:
    """Make a string safe to embed in an object path."""
    cleaned = value.translate(_SAFE_TOKEN).strip("_")
    return cleaned or "unknown"


def build_object_path(
    *,
    farm_id: str,
    kind: str,
    source: str,
    identifier: str,
    zone_id: str | None = None,
    timestamp: datetime | None = None,
    extension: str = "bin",
) -> str:
    """``farms/{farm_id}/{kind}/{source}/{zone}/{YYYY}/{MM}/{id}.{ext}``.

    Deterministic: the same inputs always produce the same path.
    """
    moment = timestamp or utc_now()
    parts = [
        "farms",
        safe_component(farm_id),
        safe_component(kind),
        safe_component(source),
    ]
    if zone_id:
        parts.append(safe_component(zone_id))
    parts.append(moment.strftime("%Y"))
    parts.append(moment.strftime("%m"))
    filename = f"{safe_component(identifier)}.{extension.lstrip('.')}"
    parts.append(filename)
    return "/".join(parts)


def guess_extension(content_type: str | None, filename: str | None = None) -> str:
    if filename:
        suffix = Path(filename).suffix.lstrip(".")
        if suffix and len(suffix) <= 5:
            return suffix.lower()
    if content_type:
        guessed = mimetypes.guess_extension(content_type)
        if guessed:
            return "jpg" if guessed == ".jpe" else guessed.lstrip(".")
    return "bin"


def validate_payload(
    data: bytes,
    *,
    content_type: str | None,
    settings: Settings,
    allowed: tuple[str, ...] = IMAGE_CONTENT_TYPES,
) -> None:
    """Reject oversized or unsupported uploads before touching any storage."""
    if not data:
        raise PayloadTooLargeError("Uploaded file is empty.")
    if len(data) > settings.max_upload_bytes:
        raise PayloadTooLargeError(
            f"File is larger than the {settings.max_upload_bytes // (1024 * 1024)} MB limit.",
            details={"max_bytes": settings.max_upload_bytes, "received_bytes": len(data)},
        )
    if content_type and content_type.split(";")[0].strip().lower() not in allowed:
        raise PayloadTooLargeError(
            f"Unsupported content type '{content_type}'.",
            code="UNSUPPORTED_MEDIA_TYPE",
            details={"allowed": list(allowed)},
        )


@dataclass(frozen=True)
class StoredObject:
    uri: str
    object_name: str
    size_bytes: int
    content_type: str
    simulated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "object_name": self.object_name,
            "size_bytes": self.size_bytes,
            "content_type": self.content_type,
            "simulated": self.simulated,
        }


@runtime_checkable
class StorageService(Protocol):
    is_mock: bool

    def save(
        self,
        data: bytes,
        *,
        object_name: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...

    def load(self, object_name: str) -> bytes: ...

    def exists(self, object_name: str) -> bool: ...

    def delete(self, object_name: str) -> bool: ...

    def public_uri(self, object_name: str) -> str: ...


class LocalStorageService:
    """Filesystem-backed storage for local development.

    URIs are ``local://<object_name>``; the same object name can later be
    written to ``gs://<bucket>/<object_name>`` unchanged.
    """

    is_mock = True

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root or get_settings().local_storage_dir)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _path(self, object_name: str) -> Path:
        target = (self._root / object_name).resolve()
        # Defend against path traversal from a client-supplied name.
        if not str(target).startswith(str(self._root.resolve())):
            raise NotFoundError("Invalid storage object name.")
        return target

    def save(
        self,
        data: bytes,
        *,
        object_name: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        path = self._path(object_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        logger.info("local_object_saved", extra={"object_name": object_name, "bytes": len(data)})
        return StoredObject(
            uri=f"local://{object_name}",
            object_name=object_name,
            size_bytes=len(data),
            content_type=content_type,
            simulated=True,
        )

    def load(self, object_name: str) -> bytes:
        path = self._path(object_name)
        if not path.exists():
            raise NotFoundError(f"Stored object '{object_name}' not found.")
        return path.read_bytes()

    def exists(self, object_name: str) -> bool:
        return self._path(object_name).exists()

    def delete(self, object_name: str) -> bool:
        path = self._path(object_name)
        if not path.exists():
            return False
        path.unlink()
        return True

    def public_uri(self, object_name: str) -> str:
        return f"local://{object_name}"

    def clear(self) -> None:
        if self._root.exists():
            shutil.rmtree(self._root)
        self._root.mkdir(parents=True, exist_ok=True)


class GcsStorageService:
    """Cloud Storage implementation (Section 7 M2)."""

    is_mock = False

    def __init__(self, bucket_name: str | None = None, client: Any | None = None) -> None:
        self._bucket_name = bucket_name or get_settings().gcs_bucket
        self._client = client

    @property
    def bucket(self) -> Any:
        if not self._bucket_name:
            raise ProviderUnavailableError("GCS_BUCKET is not configured.")
        if self._client is None:
            from google.cloud import storage

            self._client = storage.Client(project=get_settings().effective_project_id)
        return self._client.bucket(self._bucket_name)

    def save(
        self,
        data: bytes,
        *,
        object_name: str,
        content_type: str,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        blob = self.bucket.blob(object_name)
        blob.upload_from_string(data, content_type=content_type)
        if metadata:
            blob.metadata = {k: str(v) for k, v in metadata.items()}
            blob.patch()
        return StoredObject(
            uri=f"gs://{self._bucket_name}/{object_name}",
            object_name=object_name,
            size_bytes=len(data),
            content_type=content_type,
            simulated=False,
        )

    def load(self, object_name: str) -> bytes:
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            raise NotFoundError(f"Stored object '{object_name}' not found.")
        return blob.download_as_bytes()

    def exists(self, object_name: str) -> bool:
        return bool(self.bucket.blob(object_name).exists())

    def delete(self, object_name: str) -> bool:
        blob = self.bucket.blob(object_name)
        if not blob.exists():
            return False
        blob.delete()
        return True

    def public_uri(self, object_name: str) -> str:
        return f"gs://{self._bucket_name}/{object_name}"


def build_storage(settings: Settings | None = None) -> StorageService:
    resolved = settings or get_settings()
    if resolved.mock_services:
        return LocalStorageService()
    return GcsStorageService()


def build_signed_url(storage: StorageService, object_name: str, minutes: int = 60) -> str | None:
    """Return a V4 signed URL for GCS objects, or None for local storage.

    Signed URLs are how the frontend uploads directly (Section 7 M2); the
    backend path used in this MVP streams bytes through the API instead.
    """
    if not isinstance(storage, GcsStorageService):
        return None
    from datetime import timedelta

    blob = storage.bucket.blob(object_name)
    return blob.generate_signed_url(version="v4", expiration=timedelta(minutes=minutes))


def load_bytes(storage: StorageService, uri: str) -> bytes:
    """Read bytes back from either a ``local://`` or ``gs://`` URI."""
    if uri.startswith("local://"):
        return storage.load(uri[len("local://") :])
    if uri.startswith("gs://"):
        _, _, remainder = uri.partition("gs://")[2].partition("/")
        return storage.load(remainder)
    # A bare object name is also accepted.
    return storage.load(uri)


def uri_timestamp(uri: str) -> datetime | None:
    """Best-effort timestamp encoded in a storage path (``/YYYY/MM/``)."""
    parts = uri.split("/")
    if len(parts) >= 2:
        try:
            year, month = int(parts[-3]), int(parts[-2])
            return datetime(year, month, 1)
        except (ValueError, IndexError):
            return None
    return None


__all__ = [
    "AUDIO_CONTENT_TYPES",
    "GcsStorageService",
    "IMAGE_CONTENT_TYPES",
    "LocalStorageService",
    "StorageService",
    "StoredObject",
    "build_object_path",
    "build_signed_url",
    "build_storage",
    "guess_extension",
    "load_bytes",
    "parse_iso",
    "safe_component",
    "validate_payload",
]
