"""Shared fixtures.

Every test runs in mock mode against temporary directories: no Google project,
no network, no real bucket, no trained weights.
"""

from __future__ import annotations

import base64
import struct
import zlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.container import Container
from backend.core.config import Settings, get_settings

FARMER = {"Authorization": "Bearer dev-farmer-token"}
OFFICER = {"Authorization": "Bearer dev-officer-token"}
NO_AUTH: dict[str, str] = {}

BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [
            [77.5900, 13.0300],
            [77.6000, 13.0300],
            [77.6000, 13.0400],
            [77.5900, 13.0400],
            [77.5900, 13.0300],
        ]
    ],
}


def make_png(width: int = 480, height: int = 360) -> bytes:
    """A real, decodable PNG with texture and three fruit-like blobs.

    Built by hand so the suite needs no image fixture files and no extra
    dependency, and it comfortably clears the Section 8.3 quality gate.
    """
    rows: list[bytes] = []
    state = 12345
    blobs = (
        (width * 0.3, height * 0.4),
        (width * 0.7, height * 0.35),
        (width * 0.5, height * 0.75),
    )
    radius_sq = (min(width, height) / 6) ** 2
    for y in range(height):
        row = bytearray([0])  # PNG filter type 0
        for x in range(width):
            state = (1103515245 * state + 12345) % (1 << 31)
            noise = ((state >> 16) & 0x1F) - 16
            pixel = (46 + noise, 92 + noise, 38 + noise)
            for cx, cy in blobs:
                if (x - cx) ** 2 + (y - cy) ** 2 < radius_sq:
                    pixel = (168 + noise // 2, 150 + noise // 2, 30 + noise)
                    break
            row += bytes(pixel)
        rows.append(bytes(row))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
        + chunk(b"IEND", b"")
    )


def make_tiny_png(width: int = 64, height: int = 64) -> bytes:
    """A valid but undersized PNG: decodes, then fails the resolution gate."""
    return make_png(width=width, height=height)


@pytest.fixture()
def png_b64() -> str:
    return base64.b64encode(make_png()).decode()


@pytest.fixture()
def settings(tmp_path) -> Settings:
    resolved = Settings(
        environment="local",
        mock_services=True,
        local_storage_dir=tmp_path / "assets",
        firestore_emulator_host="",
    )
    get_settings.cache_clear()
    return resolved


@pytest.fixture()
def container(settings: Settings) -> Container:
    return Container.build(settings)


@pytest.fixture()
def farm(container: Container) -> dict[str, Any]:
    return container.farms.create_farm(
        {"name": "Test Orchard", "crop": "mango", "boundary": BOUNDARY}, owner_uid="dev_farmer_001"
    )


@pytest.fixture()
def client(settings: Settings) -> Iterator[TestClient]:
    from backend.main import create_app

    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.settings = settings  # type: ignore[attr-defined]
        yield test_client


@pytest.fixture()
def api_farm(client: TestClient) -> dict[str, Any]:
    response = client.post("/farms", headers=FARMER, json={"name": "API Orchard", "boundary": BOUNDARY})
    assert response.status_code == 201, response.text
    return response.json()


__all__ = [
    "BOUNDARY",
    "FARMER",
    "NO_AUTH",
    "OFFICER",
    "make_png",
    "make_tiny_png",
]
