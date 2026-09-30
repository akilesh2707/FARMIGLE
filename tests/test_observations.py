"""Ingestion guardrails: base64, declared type, magic bytes, size, source."""

from __future__ import annotations

import base64

import pytest

from backend.core.errors import (
    InvalidSourceError,
    PayloadTooLargeError,
    UnsupportedMediaTypeError,
)
from backend.core.media import (
    sniff_audio_content_type,
    sniff_image_content_type,
)
from backend.observations.service import ObservationService

from tests.conftest import make_png, make_tiny_png


def _encode(payload: bytes) -> str:
    return base64.b64encode(payload).decode()


def test_png_bytes_are_detected_even_with_a_wrong_declared_type(container, farm) -> None:
    observation = container.observations.create_observation(
        farm["farm_id"],
        {
            "source": "phone",
            "zone_id": "zone_07",
            # Declared as JPEG on purpose: the bytes win.
            "image_base64": _encode(make_png()),
            "mime_type": "image/jpeg",
        },
        owner_uid="u",
    )
    assert observation["content_type"] == "image/png"
    assert observation["asset_uri"].endswith(".png")


def test_pdf_bytes_are_rejected_even_when_declared_as_jpeg(container, farm) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        container.observations.create_observation(
            farm["farm_id"],
            {
                "source": "drone",
                "zone_id": "zone_01",
                "image_base64": _encode(b"%PDF-1.7\n%not-an-image"),
                "mime_type": "image/jpeg",
            },
            owner_uid="u",
        )


def test_arbitrary_bytes_are_rejected(container, farm) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        container.observations.create_observation(
            farm["farm_id"],
            {"source": "phone", "zone_id": "zone_01", "image_base64": _encode(b"hello world" * 20)},
            owner_uid="u",
        )


def test_invalid_base64_is_rejected(container, farm) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        container.observations.create_observation(
            farm["farm_id"],
            {"source": "phone", "zone_id": "zone_01", "image_base64": "not base64 !!!"},
            owner_uid="u",
        )


def test_oversized_image_is_rejected(container, farm, monkeypatch) -> None:
    monkeypatch.setattr(container.observations, "max_image_bytes", 512)
    with pytest.raises(PayloadTooLargeError):
        container.observations.create_observation(
            farm["farm_id"],
            {"source": "phone", "zone_id": "zone_01", "image_base64": _encode(make_png())},
            owner_uid="u",
        )


def test_every_documented_source_is_accepted(container, farm) -> None:
    for source in ("satellite", "weather", "soil", "farmer_report"):
        observation = container.observations.create_observation(
            farm["farm_id"], {"source": source, "zone_id": "zone_01", "metrics": {"x": 1}}, owner_uid="u"
        )
        assert observation["source"] == source


def test_unknown_source_is_rejected(container, farm) -> None:
    with pytest.raises(InvalidSourceError):
        container.observations.create_observation(
            farm["farm_id"],
            {"source": "drone_img", "zone_id": "zone_01", "image_base64": _encode(make_png())},
            owner_uid="u",
        )


def test_observations_require_a_known_zone(container, farm) -> None:
    with pytest.raises(Exception):
        container.observations.create_observation(
            farm["farm_id"],
            {"source": "phone", "zone_id": "zone_99", "image_base64": _encode(make_png())},
            owner_uid="u",
        )


def test_tiny_image_is_stored_but_fails_the_quality_gate(container, farm) -> None:
    """Storage accepts it; the vision layer refuses to score it (Section 8.3)."""
    observation = container.observations.create_observation(
        farm["farm_id"],
        {"source": "phone", "zone_id": "zone_01", "image_base64": _encode(make_tiny_png())},
        owner_uid="u",
    )
    payload = container.orchestrator.perceive(farm, observation)
    assert payload["accepted"] is False
    assert payload["rejection_reason"] == "IMAGE_QUALITY_FAILED"
    assert payload["rejection_details"]["retake_required"] is True
    assert payload["rejection_details"]["remedy"]


def test_audio_bytes_are_sniffed_and_text_is_rejected(container, farm) -> None:
    webm_header = b"\x1a\x45\xdf\xa3" + b"\x00" * 512
    observation = container.observations.create_audio_observation(
        farm["farm_id"],
        _encode(webm_header),
        mime_type="audio/webm",
        language="ta",
        zone_id="zone_03",
    )
    assert observation["source"] == "farmer_report"
    assert observation["content_type"] == "audio/webm"

    with pytest.raises(Exception):
        container.observations.create_audio_observation(
            farm["farm_id"], _encode(b"just text, not audio"), mime_type="audio/webm"
        )


def test_sniffer_recognises_the_documented_formats() -> None:
    assert sniff_image_content_type(make_png()) == "image/png"
    assert sniff_image_content_type(b"\xff\xd8\xff\xe0" + b"\x00" * 8) == "image/jpeg"
    assert sniff_image_content_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_content_type(b"\x00\x00\x00\x18ftypheic") == "image/heic"
    assert sniff_image_content_type(b"%PDF-1.4") is None
    assert sniff_image_content_type(b"") is None
    assert sniff_audio_content_type(b"ID3\x04\x00") == "audio/mpeg"
    assert sniff_audio_content_type(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "audio/wav"
    assert sniff_audio_content_type(b"nope") is None


def test_storage_round_trip_returns_the_same_bytes(container, farm) -> None:
    observation = container.observations.create_observation(
        farm["farm_id"],
        {"source": "phone", "zone_id": "zone_02", "image_base64": _encode(make_png(200, 200))},
        owner_uid="u",
    )
    loaded = container.observations.load_image_bytes(observation)
    assert loaded is not None
    assert loaded[:8] == b"\x89PNG\r\n\x1a\n"


def test_remote_reference_is_rejected(container, farm) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        ObservationService._validate_reference("ftp://example.com/a.jpg")
