"""Model 3 — Urban Flood Risk endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core import config, grid
from app.schemas.requests import GridQuery
from app.schemas.responses import CityLayer, FloodPrediction, GeoJsonResponse, MetricsResponse
from app.services.models import flood_risk

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flood-risk", tags=["flood-risk"])


def _resolve(query: GridQuery) -> str:
    if query.grid_id:
        grid.get_cell(query.grid_id)
        return query.grid_id
    return grid.nearest_cell(query.lat, query.lon)["grid_id"]


@router.post("", response_model=FloodPrediction)
def predict_flood(query: GridQuery):
    """Predict flood susceptibility for a grid cell.

    Returns the flood probability, its LOW / MODERATE / HIGH band, the measured
    physical drivers behind it, and feature attributions.
    """
    return flood_risk.predict(_resolve(query), explain_prediction=query.include_attribution)


@router.get("/cell/{grid_id}", response_model=FloodPrediction)
def predict_flood_by_id(grid_id: str, include_attribution: bool = True):
    """Convenience GET form of the single-cell prediction."""
    grid.get_cell(grid_id)
    return flood_risk.predict(grid_id, explain_prediction=include_attribution)


@router.get("/city/{city}", response_model=CityLayer)
def predict_flood_city(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """Predict flood risk for every cell in a city."""
    cells = flood_risk.predict_city(city, limit=limit)
    return CityLayer(city=city, count=len(cells), cells=cells)


@router.get("/city/{city}/geojson", response_model=GeoJsonResponse)
def flood_geojson(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """The flood-risk layer for a city as GeoJSON, for map rendering."""
    return grid.to_feature_collection(flood_risk.predict_city(city, limit=limit))


@router.get("/thresholds")
def flood_thresholds():
    """The risk bands in force, their rationale, and how to change them."""
    return {
        "decision_threshold": flood_risk.operating_threshold(),
        "threshold_basis": (
            "Tuned during training by maximising a composite validation score on the "
            "validation cities."
        ),
        "risk_bands": {
            "high_at_or_above": config.FLOOD_RISK_HIGH_THRESHOLD,
            "moderate_at_or_above": config.FLOOD_RISK_MODERATE_THRESHOLD,
            "low_below": config.FLOOD_RISK_MODERATE_THRESHOLD,
        },
        "rationale": (
            "Bands bracket the tuned operating threshold, so MODERATE spans the region "
            "around the decision boundary where the model is least certain."
        ),
        "configurable_via": [
            "FLOOD_RISK_HIGH_THRESHOLD",
            "FLOOD_RISK_MODERATE_THRESHOLD",
        ],
        "risk_meaning": flood_risk.RISK_MEANING,
    }


@router.get("/metrics", response_model=MetricsResponse)
def flood_metrics():
    """Validation evidence and documented limitations for Model 3."""
    return flood_risk.metrics()
