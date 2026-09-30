"""Small shared helpers: server-generated IDs, timestamps, clamping."""

from __future__ import annotations

import re
import secrets
import zlib
from datetime import datetime, timezone
from typing import Any, Iterable, TypeVar

T = TypeVar("T")

# Zone ids are used as Firestore-independent identifiers and as keys in API
# payloads, so keep them to a strict, predictable pattern.
ZONE_ID_PATTERN = re.compile(r"^zone_[0-9]{2,}$")
FARM_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{3,64}$")


def utc_now() -> datetime:
    """Timezone-aware now. Every timestamp in the system comes from here."""
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    """RFC 3339 / ISO-8601 UTC string, e.g. ``2026-01-31T09:15:00.123456Z``."""
    return utc_now().isoformat().replace("+00:00", "Z")


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 timestamp, assuming UTC when no offset is present."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def new_id(prefix: str) -> str:
    """Server-generated identifier, e.g. ``farm_k3n8x1q9z``.

    Clients never supply document ids.
    """
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    body = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"{prefix}_{body}"


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def round_score(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(clamp(float(value)), digits)


def weighted_mean(pairs: Iterable[tuple[float, float]]) -> float:
    """Weighted mean of (value, weight) pairs; 0.0 when no weight is present."""
    total = 0.0
    weight_sum = 0.0
    for value, weight in pairs:
        if weight <= 0:
            continue
        total += value * weight
        weight_sum += weight
    if weight_sum <= 0:
        return 0.0
    return total / weight_sum


def without_none(data: dict[str, Any]) -> dict[str, Any]:
    """Drop ``None`` values so Firestore documents stay tidy."""
    return {key: value for key, value in data.items() if value is not None}


def stable_seed(value: str) -> int:
    """Process-independent 32-bit seed for a string.

    ``hash()`` is salted per process in Python, so anything that must produce
    the same id across restarts (recommendation ids, cache keys) uses this.
    """
    return zlib.crc32(value.encode("utf-8")) & 0xFFFFFFFF
