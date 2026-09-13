"""
Common 1 km analysis grid.

Every environmental model in this project is indexed by the same `grid_id`, so
this module owns the single authoritative grid registry:

    grid_id | city | state | lat | lon | is_core | geometry

All coordinates are geographic degrees in EPSG:4326 — the CRS the upstream
Earth Engine exports use. No transformation happens anywhere in the backend, so
there is no opportunity to silently mix coordinate systems. Cell geometry is
reconstructed as the axis-aligned lat/lon envelope of a 1 km cell centred on the
exported centroid, which is how the source grid was generated.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from app.core.config import GRID_CELL_SIZE_M, GRID_CRS, GRID_METADATA_CSV
from app.core.errors import DatasetUnavailableError, GridNotFoundError, InvalidInputError

logger = logging.getLogger(__name__)

_EARTH_RADIUS_M = 6_371_008.8
_META_COLUMNS = ["grid_id", "city", "state", "lat", "lon", "is_core"]


@lru_cache(maxsize=1)
def grid_metadata() -> pd.DataFrame:
    """The grid registry, loaded once and cached for the process lifetime."""
    if not GRID_METADATA_CSV.exists():
        raise DatasetUnavailableError(
            "Grid metadata not found. The 1 km grid registry is required for every "
            "spatial query.",
            detail={"expected_file": GRID_METADATA_CSV.name, "config_key": "GRID_METADATA_CSV"},
        )

    df = pd.read_csv(GRID_METADATA_CSV)
    missing = [c for c in _META_COLUMNS if c not in df.columns]
    if missing:
        raise DatasetUnavailableError(
            "Grid metadata is missing required columns.",
            detail={"missing_columns": missing, "file": GRID_METADATA_CSV.name},
        )

    df = df[_META_COLUMNS].drop_duplicates("grid_id").reset_index(drop=True)
    df["city"] = df["city"].astype(str)
    df["state"] = df["state"].astype(str)
    logger.info(
        "Grid registry loaded: %d cells across %d cities (%s, %d m)",
        len(df), df["city"].nunique(), GRID_CRS, GRID_CELL_SIZE_M,
    )
    return df


@lru_cache(maxsize=1)
def _grid_index() -> dict[str, int]:
    return {gid: i for i, gid in enumerate(grid_metadata()["grid_id"])}


def city_names() -> list[str]:
    """Sorted list of cities covered by the grid."""
    return sorted(grid_metadata()["city"].unique().tolist())


def cities_summary() -> list[dict]:
    """Per-city cell counts and centroids, for populating a city selector."""
    df = grid_metadata()
    out = (
        df.groupby(["city", "state"])
        .agg(grid_cells=("grid_id", "size"), lat=("lat", "mean"), lon=("lon", "mean"))
        .reset_index()
        .sort_values("city")
    )
    return [
        {
            "city": r.city,
            "state": r.state,
            "grid_cells": int(r.grid_cells),
            "lat": round(float(r.lat), 6),
            "lon": round(float(r.lon), 6),
        }
        for r in out.itertuples()
    ]


def grid_ids_for_city(city: str) -> list[str]:
    """Every grid_id belonging to a city (case-insensitive match)."""
    df = grid_metadata()
    hit = df[df["city"].str.lower() == city.strip().lower()]
    if hit.empty:
        raise GridNotFoundError(
            f"No grid cells found for city '{city}'.",
            detail={"available_cities": city_names()},
        )
    return hit["grid_id"].tolist()


def get_cell(grid_id: str) -> dict:
    """Registry record for one grid cell."""
    idx = _grid_index().get(grid_id)
    if idx is None:
        raise GridNotFoundError(
            f"grid_id '{grid_id}' is not part of the 1 km analysis grid.",
            detail={"hint": "List valid ids with GET /api/grid/cities/{city}/cells"},
        )
    row = grid_metadata().iloc[idx]
    return {
        "grid_id": str(row["grid_id"]),
        "city": str(row["city"]),
        "state": str(row["state"]),
        "lat": float(row["lat"]),
        "lon": float(row["lon"]),
        "is_core": int(row["is_core"]),
    }


def validate_coordinates(lat: float, lon: float) -> None:
    """Reject coordinates outside the valid geographic domain."""
    if not (math.isfinite(lat) and math.isfinite(lon)):
        raise InvalidInputError("Latitude and longitude must be finite numbers.")
    if not -90 <= lat <= 90:
        raise InvalidInputError(
            f"Latitude {lat} is out of range; expected -90 to 90.", detail={"latitude": lat}
        )
    if not -180 <= lon <= 180:
        raise InvalidInputError(
            f"Longitude {lon} is out of range; expected -180 to 180.", detail={"longitude": lon}
        )


def nearest_cell(lat: float, lon: float, *, max_distance_km: float = 25.0) -> dict:
    """Find the grid cell whose centroid is closest to a point.

    Uses the haversine great-circle distance so the match is correct at any
    latitude. Raises if the point lies outside the covered cities rather than
    snapping it to an arbitrarily distant cell.
    """
    validate_coordinates(lat, lon)
    df = grid_metadata()

    lat1, lon1 = math.radians(lat), math.radians(lon)
    lat2 = np.radians(df["lat"].to_numpy(dtype=float))
    lon2 = np.radians(df["lon"].to_numpy(dtype=float))
    h = (
        np.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    distances_km = 2 * _EARTH_RADIUS_M * np.arcsin(np.sqrt(h)) / 1000.0

    idx = int(np.argmin(distances_km))
    distance_km = float(distances_km[idx])
    if distance_km > max_distance_km:
        raise GridNotFoundError(
            f"Location ({lat:.4f}, {lon:.4f}) is {distance_km:.1f} km from the nearest "
            f"analysed grid cell, beyond the {max_distance_km:.0f} km limit. This "
            f"location is outside the cities covered by the trained models.",
            detail={
                "nearest_city": str(df.iloc[idx]["city"]),
                "distance_km": round(distance_km, 2),
                "covered_cities": city_names(),
            },
        )

    cell = get_cell(str(df.iloc[idx]["grid_id"]))
    cell["distance_km"] = round(distance_km, 3)
    return cell


def cell_polygon(lat: float, lon: float) -> list[list[float]]:
    """GeoJSON linear ring for the cell centred on (lat, lon).

    Half-extents are converted from metres to degrees at the cell's own latitude,
    so cells stay ~1 km wide rather than narrowing towards the poles.
    """
    half_m = GRID_CELL_SIZE_M / 2.0
    dlat = math.degrees(half_m / _EARTH_RADIUS_M)
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    dlon = math.degrees(half_m / (_EARTH_RADIUS_M * cos_lat))
    return [
        [lon - dlon, lat - dlat],
        [lon + dlon, lat - dlat],
        [lon + dlon, lat + dlat],
        [lon - dlon, lat + dlat],
        [lon - dlon, lat - dlat],
    ]


def to_feature_collection(records: list[dict]) -> dict:
    """Wrap grid records as a GeoJSON FeatureCollection.

    Each record must carry `lat`/`lon`; every other key becomes a feature
    property, so the same helper serves the water, urban and flood layers.
    """
    features = []
    for rec in records:
        lat, lon = rec.get("lat"), rec.get("lon")
        if lat is None or lon is None:
            continue
        props = {k: v for k, v in rec.items() if k not in {"lat", "lon"}}
        features.append(
            {
                "type": "Feature",
                "id": rec.get("grid_id"),
                "geometry": {"type": "Polygon", "coordinates": [cell_polygon(lat, lon)]},
                "properties": {**props, "lat": lat, "lon": lon},
            }
        )
    return {
        "type": "FeatureCollection",
        "crs": {"type": "name", "properties": {"name": GRID_CRS}},
        "features": features,
    }
