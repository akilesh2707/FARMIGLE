"""Geospatial: boundary validation, zone grid, measurements, harvest map."""

from __future__ import annotations

import pytest

from geospatial.geojson.geometry import (
    InvalidBoundaryError,
    area_hectares_of,
    normalize_boundary,
    to_shapely,
    validate_boundary,
)
from geospatial.geojson.harvest_map import build_harvest_map
from geospatial.maps.grid import find_zone_for_point, generate_zone_grid

from tests.conftest import BOUNDARY


def test_boundary_is_normalized_and_validated() -> None:
    boundary = validate_boundary(BOUNDARY)
    assert boundary["type"] == "Polygon"
    assert boundary["coordinates"][0][0] == boundary["coordinates"][0][-1]


def test_boundary_accepts_lat_lng_ring_convenience() -> None:
    ring = [
        {"lat": 13.03, "lng": 77.59},
        {"lat": 13.03, "lng": 77.60},
        {"lat": 13.04, "lng": 77.60},
        {"lat": 13.04, "lng": 77.59},
    ]
    assert validate_boundary(ring)["type"] == "Polygon"


@pytest.mark.parametrize(
    "boundary",
    [
        {"type": "Polygon", "coordinates": []},
        {"type": "Polygon", "coordinates": [[[77.59, 13.03], [77.60, 13.03]]]},  # < 3 points
        {"type": "Polygon", "coordinates": [[[200.0, 91.0], [200.1, 91.0], [200.1, 91.1], [200.0, 91.0]]]},
        {"type": "Point", "coordinates": [77.59, 13.03]},
        {"type": "FeatureCollection", "features": []},
    ],
)
def test_invalid_boundaries_are_rejected(boundary: dict) -> None:
    with pytest.raises(InvalidBoundaryError):
        validate_boundary(boundary)


def test_default_grid_is_twenty_zones_row_major() -> None:
    zones = generate_zone_grid(normalize_boundary(BOUNDARY), rows=4, cols=5)
    assert len(zones) == 20
    assert [zone["zone_id"] for zone in zones[:3]] == ["zone_01", "zone_02", "zone_03"]
    assert [zone["zone_id"] for zone in zones[-2:]] == ["zone_19", "zone_20"]
    assert [zone["label"] for zone in zones[:5]] == ["A", "B", "C", "D", "E"]
    assert zones[-1]["label"] == "T"
    # Row-major: zone_06 opens the second row.
    assert (zones[5]["row"], zones[5]["col"]) == (1, 0)
    assert (zones[0]["row"], zones[0]["col"]) == (0, 0)


def test_zone_areas_sum_close_to_farm_area() -> None:
    boundary = normalize_boundary(BOUNDARY)
    zones = generate_zone_grid(boundary, rows=4, cols=5)
    total = sum(float(zone["area_hectares"]) for zone in zones)
    assert total == pytest.approx(area_hectares_of(to_shapely(boundary)), rel=0.06)


def test_hectares_for_a_one_by_one_tenth_degree_box() -> None:
    """Equirectangular projection: 0.01 deg x 0.01 deg at ~13 deg north."""
    from math import cos, radians

    ring = [[77.59, 13.03], [77.60, 13.03], [77.60, 13.04], [77.59, 13.04], [77.59, 13.03]]
    hectares = area_hectares_of(to_shapely({"type": "Polygon", "coordinates": [ring]}))
    km_per_deg = 111.32
    expected = 0.01 * km_per_deg * (0.01 * km_per_deg * cos(radians(13.035))) * 100
    assert hectares == pytest.approx(expected, rel=1e-6)
    assert hectares == pytest.approx(120.7, rel=0.01)


def test_point_lookup_finds_the_containing_zone() -> None:
    zones = generate_zone_grid(normalize_boundary(BOUNDARY), rows=4, cols=5)
    zone = find_zone_for_point(zones, 13.035, 77.595)
    assert zone is not None
    assert zone["zone_id"] in {item["zone_id"] for item in zones}
    assert find_zone_for_point(zones, 20.0, 90.0) is None


def test_harvest_map_emits_boundary_plus_every_zone() -> None:
    boundary = normalize_boundary(BOUNDARY)
    farm = {
        "farm_id": "farm_1",
        "name": "Test",
        "crop": "mango",
        "boundary": boundary,
        "zones": generate_zone_grid(boundary, rows=4, cols=5),
    }
    collection = build_harvest_map(farm, {})
    assert collection["type"] == "FeatureCollection"
    assert len(collection["features"]) == 21  # 20 zones + the farm outline
    zone_features = [
        feature
        for feature in collection["features"]
        if feature["properties"].get("feature_type") != "farm_boundary"
    ]
    assert len(zone_features) == 20
    # No evidence at all must still read as NO_DATA, never as a real status.
    assert {feature["properties"].get("status") for feature in zone_features} == {"NO_DATA"}
