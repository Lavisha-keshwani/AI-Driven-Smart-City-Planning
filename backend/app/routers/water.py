"""Model 1 — Surface Water Monitoring endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core import grid
from app.schemas.requests import GridQuery
from app.schemas.responses import CityLayer, GeoJsonResponse, MetricsResponse, WaterPrediction
from app.services.models import surface_water

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/water", tags=["water"])


def _resolve(query: GridQuery) -> str:
    if query.grid_id:
        grid.get_cell(query.grid_id)          # validates membership
        return query.grid_id
    return grid.nearest_cell(query.lat, query.lon)["grid_id"]


@router.post("", response_model=WaterPrediction)
def predict_water(query: GridQuery):
    """Classify a grid cell as a surface-water body.

    Returns the model probability and classification, the observed Global Surface
    Water statistics (measured, kept separate from the prediction), and the top
    contributing features.
    """
    return surface_water.predict(
        _resolve(query), explain_prediction=query.include_attribution
    )


@router.get("/cell/{grid_id}", response_model=WaterPrediction)
def predict_water_by_id(grid_id: str, include_attribution: bool = True):
    """Convenience GET form of the single-cell prediction."""
    grid.get_cell(grid_id)
    return surface_water.predict(grid_id, explain_prediction=include_attribution)


@router.get("/city/{city}", response_model=CityLayer)
def predict_water_city(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """Classify every cell in a city."""
    cells = surface_water.predict_city(city, limit=limit)
    return CityLayer(city=city, count=len(cells), cells=cells)


@router.get("/city/{city}/geojson", response_model=GeoJsonResponse)
def water_geojson(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """The surface-water layer for a city as GeoJSON, for map rendering."""
    return grid.to_feature_collection(surface_water.predict_city(city, limit=limit))


@router.get("/monitoring/{city}")
def water_body_monitoring(city: str):
    """Multi-year water-body monitoring summary for a city.

    Produced by the training run from the Global Surface Water record: the count of
    water cells, the share that are permanent, and the share whose extent is stable.
    These are measurements, not predictions.
    """
    summary = surface_water.city_water_body_summary(city)
    return {
        "city": city,
        "available": bool(summary),
        "summary": summary,
        "basis": (
            "Global Surface Water (JRC GSW) observations aggregated per city during "
            "model training. Measured, not predicted."
        ),
        "note": (
            None if summary else
            "No monitoring summary is available for this city in the training outputs."
        ),
    }


@router.get("/metrics", response_model=MetricsResponse)
def water_metrics():
    """Validation evidence and documented limitations for Model 1."""
    return surface_water.metrics()
