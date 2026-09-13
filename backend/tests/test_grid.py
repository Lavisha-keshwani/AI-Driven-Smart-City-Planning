"""Unit tests for the common geospatial grid."""

from __future__ import annotations

import math

import pytest

from app.core import grid
from app.core.config import GRID_CELL_SIZE_M
from app.core.errors import GridNotFoundError, InvalidInputError
from tests.conftest import requires_models


@requires_models
def test_grid_metadata_has_required_columns():
    df = grid.grid_metadata()
    for column in ("grid_id", "city", "state", "lat", "lon", "is_core"):
        assert column in df.columns
    assert len(df) > 0
    assert df["grid_id"].is_unique


@requires_models
def test_cities_summary_counts_match_metadata():
    summary = grid.cities_summary()
    total = sum(c["grid_cells"] for c in summary)
    assert total == len(grid.grid_metadata())
    assert len(summary) == len(grid.city_names())


@requires_models
def test_get_cell_roundtrips(grid_cell):
    cell = grid.get_cell(grid_cell["grid_id"])
    assert cell["grid_id"] == grid_cell["grid_id"]
    assert cell["city"] == grid_cell["city"]
    assert -90 <= cell["lat"] <= 90
    assert -180 <= cell["lon"] <= 180


def test_get_cell_rejects_unknown_id():
    with pytest.raises(GridNotFoundError):
        grid.get_cell("NotACity_00000000")


@requires_models
def test_nearest_cell_finds_the_containing_cell(grid_cell):
    """A cell's own centroid must resolve back to that cell."""
    found = grid.nearest_cell(grid_cell["lat"], grid_cell["lon"])
    assert found["grid_id"] == grid_cell["grid_id"]
    assert found["distance_km"] < 0.01


@requires_models
def test_nearest_cell_rejects_locations_outside_coverage():
    """A point in the mid-Pacific must fail, not snap to an Indian city."""
    with pytest.raises(GridNotFoundError) as exc:
        grid.nearest_cell(0.0, -160.0)
    assert "outside the cities covered" in exc.value.message


@pytest.mark.parametrize("lat,lon", [(91, 0), (-91, 0), (0, 181), (0, -181)])
def test_validate_coordinates_rejects_out_of_range(lat, lon):
    with pytest.raises(InvalidInputError):
        grid.validate_coordinates(lat, lon)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_validate_coordinates_rejects_non_finite(bad):
    with pytest.raises(InvalidInputError):
        grid.validate_coordinates(bad, 0.0)


def test_cell_polygon_is_a_closed_ring():
    ring = grid.cell_polygon(13.0, 80.0)
    assert len(ring) == 5
    assert ring[0] == ring[-1], "GeoJSON linear rings must close"


@pytest.mark.parametrize("lat", [0.0, 13.0, 31.6])
def test_cell_polygon_is_about_one_kilometre_at_any_latitude(lat):
    """Longitude extent must widen with latitude so cells stay ~1 km across."""
    ring = grid.cell_polygon(lat, 80.0)
    lons = [p[0] for p in ring]
    lats = [p[1] for p in ring]

    width_km = (max(lons) - min(lons)) * 111.32 * math.cos(math.radians(lat))
    height_km = (max(lats) - min(lats)) * 110.57
    expected = GRID_CELL_SIZE_M / 1000

    assert width_km == pytest.approx(expected, rel=0.02)
    assert height_km == pytest.approx(expected, rel=0.02)


def test_to_feature_collection_shape():
    records = [
        {"grid_id": "A_1", "lat": 13.0, "lon": 80.0, "score": 0.5},
        {"grid_id": "A_2", "lat": 13.01, "lon": 80.01, "score": 0.9},
    ]
    fc = grid.to_feature_collection(records)

    assert fc["type"] == "FeatureCollection"
    assert fc["crs"]["properties"]["name"] == "EPSG:4326"
    assert len(fc["features"]) == 2

    feature = fc["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    assert feature["id"] == "A_1"
    assert feature["properties"]["score"] == 0.5
    assert feature["properties"]["lat"] == 13.0


def test_to_feature_collection_skips_records_without_coordinates():
    fc = grid.to_feature_collection([{"grid_id": "A_1", "score": 0.5}])
    assert fc["features"] == []
