"""M10 - Spatial mapping.

Zone grid generation and GeoJSON export. The backend emits GeoJSON only; it
has no dependency on any frontend rendering technology.
"""

from geospatial.geojson import (
    build_harvest_map,
    is_valid_feature_collection,
    make_feature,
    make_feature_collection,
    validate_boundary,
)
from geospatial.maps import (
    find_zone_for_point,
    generate_zone_grid,
    zone_lookup,
)

__all__ = [
    "build_harvest_map",
    "find_zone_for_point",
    "generate_zone_grid",
    "is_valid_feature_collection",
    "make_feature",
    "make_feature_collection",
    "validate_boundary",
    "zone_lookup",
]
