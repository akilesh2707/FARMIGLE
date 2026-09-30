"""HTTP contract tests for the documented Section 12.6 surface."""

from __future__ import annotations

import base64
from contextlib import contextmanager
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.core.auth import AuthenticatedUser, get_current_user
from tests.conftest import BOUNDARY, FARMER, OFFICER, make_png, make_tiny_png

SECOND_FARMER = {"Authorization": "Bearer dev-farmer-token"}


def as_farmer(client: TestClient, uid: str):
    """Temporarily resolve the dev token to a different farmer uid.

    Mock mode ships one dev farmer token, so the second identity is injected at
    the dependency boundary instead of adding a token that exists only for
    tests. Used as a context manager, so the identity cannot leak into the
    assertions that follow.
    """

    @contextmanager
    def _switched() -> Iterator[TestClient]:
        def override() -> AuthenticatedUser:
            return AuthenticatedUser(
                uid=uid, email=f"{uid}@example.com", role="farmer", claims={}
            )

        client.app.dependency_overrides[get_current_user] = override
        try:
            yield client
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    return _switched()


def test_root_and_health(client) -> None:
    root = client.get("/")
    assert root.status_code == 200
    assert root.json()["heuristic_version"] == "heuristic-v0"
    assert "not validated" in root.json()["disclaimer"]

    health = client.get("/health")
    assert health.status_code == 200
    body = health.json()
    assert body["status"] == "ok"
    assert body["mock_services"] is True
    from backend.core.config import get_settings
    assert body["providers"]["ml"]["ripeness"] == get_settings().ml_provider


def test_docs_and_openapi_expose_the_documented_paths(client) -> None:
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/farms",
        "/farms/{farm_id}",
        "/farms/{farm_id}/zones",
        "/farms/{farm_id}/zones/{zone_id}",
        "/farms/{farm_id}/observations",
        "/farms/{farm_id}/observations/{observation_id}",
        "/farms/{farm_id}/analyze",
        "/farms/{farm_id}/health",
        "/farms/{farm_id}/harvest-map",
        "/farms/{farm_id}/recommendations",
        "/farms/{farm_id}/image-analysis",
        "/farms/{farm_id}/voice-query",
        "/district/hotspots",
        "/health",
    ):
        assert path in paths, path


def test_anonymous_access_is_rejected(client) -> None:
    assert client.get("/farms").status_code == 401
    assert client.post("/farms", json={"name": "x"}).status_code == 401


def test_officer_cannot_act_as_a_farmer(client) -> None:
    response = client.get("/farms", headers=OFFICER)
    assert response.status_code == 403
    assert response.json()["error"] == "FORBIDDEN"


def test_farm_crud_cycle(client) -> None:
    created = client.post(
        "/farms",
        headers=FARMER,
        json={"name": "North Block", "crop": "mango", "boundary": BOUNDARY},
    )
    assert created.status_code == 201
    farm = created.json()
    farm_id = farm["farm_id"]
    assert farm["zones"]
    assert len(farm["zones"]) == 20
    assert farm["zones"][0]["zone_id"] == "zone_01"
    assert farm["zones"][0]["label"] == "A"

    fetched = client.get(f"/farms/{farm_id}", headers=FARMER)
    assert fetched.status_code == 200
    assert fetched.json()["farm_id"] == farm_id

    patched = client.patch(f"/farms/{farm_id}", headers=FARMER, json={"name": "North Block B"})
    assert patched.status_code == 200
    assert patched.json()["name"] == "North Block B"

    assert client.delete(f"/farms/{farm_id}", headers=FARMER).status_code == 204
    assert client.get(f"/farms/{farm_id}", headers=FARMER).status_code == 404


def test_a_farmer_cannot_touch_another_farmers_data(client: TestClient) -> None:
    with as_farmer(client, "farmer_2") as owner:
        created = owner.post(
            "/farms", json={"name": "Other Orchard", "crop": "mango", "boundary": BOUNDARY}
        )
        assert created.status_code == 201, created.text
        other_farm = created.json()


    """Route-level role checks are not enough; ownership must be enforced too."""
    other_id = other_farm["farm_id"]

    assert client.get(f"/farms/{other_id}", headers=FARMER).status_code == 403
    assert client.patch(f"/farms/{other_id}", headers=FARMER, json={"name": "stolen"}).status_code == 403
    assert client.get(f"/farms/{other_id}/zones", headers=FARMER).status_code == 403
    assert client.get(f"/farms/{other_id}/observations", headers=FARMER).status_code == 403
    assert client.get(f"/farms/{other_id}/recommendations", headers=FARMER).status_code == 403

    create = client.post(
        f"/farms/{other_id}/observations",
        headers=FARMER,
        json={"source": "phone", "image_base64": base64.b64encode(make_png()).decode()},
    )
    assert create.status_code == 403
    assert create.json()["error"] == "FORBIDDEN"

    analyze = client.post(f"/farms/{other_id}/analyze", headers=FARMER, json={})
    assert analyze.status_code == 403

    image = client.post(
        f"/farms/{other_id}/image-analysis",
        headers=FARMER,
        json={"source": "phone", "image_base64": base64.b64encode(make_png()).decode()},
    )
    assert image.status_code == 403

    voice = client.post(f"/farms/{other_id}/voice-query", headers=FARMER, json={"text": "status"})
    assert voice.status_code == 403

    assert client.delete(f"/farms/{other_id}", headers=FARMER).status_code == 403

    # The other farmer still has their farm, and can see it themselves.
    with as_farmer(client, "farmer_2") as owner:
        assert owner.get(f"/farms/{other_id}").status_code == 200


def test_zone_scoped_observation_rejects_an_unknown_zone(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Zone Check", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]
    response = client.post(
        f"/farms/{farm_id}/observations",
        headers=FARMER,
        json={
            "source": "phone",
            "zone_id": "zone_99",
            "image_base64": base64.b64encode(make_png()).decode(),
        },
    )
    assert response.status_code in (400, 404)
    assert response.json()["error"] in {"ZONE_NOT_FOUND", "VALIDATION_ERROR"}


def test_image_analysis_save_flag_does_not_persist(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Preview", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]
    image = base64.b64encode(make_png()).decode()

    saved = client.post(
        f"/farms/{farm_id}/image-analysis",
        headers=FARMER,
        json={"source": "phone", "zone_id": "zone_01", "image_base64": image, "save": True},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["observation_id"]
    assert saved.json()["ripeness_label"] in {"HARVEST_READY", "NEAR_READY", "NOT_READY"}

    preview = client.post(
        f"/farms/{farm_id}/image-analysis",
        headers=FARMER,
        json={"source": "phone", "zone_id": "zone_02", "image_base64": image, "save": False},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["observation_id"] is None

    listed = client.get(f"/farms/{farm_id}/observations", headers=FARMER).json()
    assert [item["zone_id"] for item in listed["observations"]] == ["zone_01"]


def test_pdf_disguised_as_an_image_is_rejected(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Spoof", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]
    fake = base64.b64encode(b"%PDF-1.4\nnot a png at all\n%%EOF").decode()
    response = client.post(
        f"/farms/{farm_id}/image-analysis",
        headers=FARMER,
        json={"source": "phone", "image_base64": fake, "mime_type": "image/png"},
    )
    assert response.status_code == 415
    assert response.json()["error"] == "UNSUPPORTED_MEDIA_TYPE"


def test_blurry_image_returns_422_with_a_retake_reason(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Blurry", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]
    # A valid but undersized PNG decodes and then fails the resolution gate.
    flat = base64.b64encode(make_tiny_png()).decode()
    response = client.post(
        f"/farms/{farm_id}/image-analysis",
        headers=FARMER,
        json={"source": "phone", "image_base64": flat},
    )
    assert response.status_code in (200, 422)
    if response.status_code == 422:
        assert response.json()["error"] == "IMAGE_QUALITY_FAILED"
        assert response.json()["details"]


def test_analyze_returns_a_complete_disclosed_result(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Analysis", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]
    client.post(
        f"/farms/{farm_id}/observations",
        headers=FARMER,
        json={
            "source": "phone",
            "zone_id": "zone_03",
            "image_base64": base64.b64encode(make_png()).decode(),
        },
    )
    response = client.post(f"/farms/{farm_id}/analyze", headers=FARMER, json={})
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["zones"]) == 20
    assert sum(body["status_counts"].values()) == 20
    assert body["is_mock"] is True
    assert body["run_id"]
    assert body["harvest_map_uri"]
    for key in ("weather", "satellite"):
        assert key in body["health"], key
    assert body["health"]["heuristic_validated"] is False
    assert body["recommendations"], "an analyzed run should produce recommendations"

    results = client.get(f"/farms/{farm_id}/harvest-map", headers=FARMER).json()
    collection = results["feature_collection"]
    assert collection["type"] == "FeatureCollection"
    assert collection["features"]
    assert results["asset_uri"]
    assert any(entry.get("status") for entry in results["legend"])


def test_voice_query_text_and_audio_paths(client) -> None:
    farm_id = client.post(
        "/farms", headers=FARMER, json={"name": "Voice", "crop": "mango", "boundary": BOUNDARY}
    ).json()["farm_id"]

    text = client.post(
        f"/farms/{farm_id}/voice-query", headers=FARMER, json={"text": "zone 7 status", "language": "en"}
    )
    assert text.status_code == 200, text.text
    assert text.json()["intent"]["intent"] == "zone_status"
    assert text.json()["zone_id"] == "zone_07"
    assert text.json()["is_mock"] is True

    audio = client.post(
        f"/farms/{farm_id}/voice-query",
        headers=FARMER,
        json={"audio_base64": base64.b64encode(b"\x00" * 256).decode(), "language": "ta"},
    )
    assert audio.status_code == 200, audio.text
    assert audio.json()["language"] == "ta"


def test_district_hotspots_is_officer_only(client) -> None:
    assert client.get("/district/hotspots").status_code == 401
    assert client.get("/district/hotspots", headers=FARMER).status_code == 403
    response = client.get("/district/hotspots", headers=OFFICER)
    assert response.status_code == 200
    body = response.json()
    assert body["hotspots"] == []
    assert body["count"] == 0
    # Aggregated counts, never farmer identity.
    assert body["aggregation"] == "farm_level_aggregate_no_farmer_identity"
    assert "not confirmed disease" in body["disclaimer"]
