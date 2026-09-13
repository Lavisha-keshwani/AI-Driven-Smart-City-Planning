"""Model 2 — Urban Expansion Suitability endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.core import config, grid
from app.schemas.requests import GridQuery
from app.schemas.responses import CityLayer, GeoJsonResponse, MetricsResponse, UrbanPrediction
from app.services.models import urban_expansion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/urban-expansion", tags=["urban-expansion"])


def _resolve(query: GridQuery) -> str:
    if query.grid_id:
        grid.get_cell(query.grid_id)
        return query.grid_id
    return grid.nearest_cell(query.lat, query.lon)["grid_id"]


@router.post("", response_model=UrbanPrediction)
def predict_urban(query: GridQuery):
    """Score a grid cell for urban expansion suitability.

    Returns a continuous suitability score in [0, 1], the GREEN / YELLOW / RED class,
    the class probabilities, deterministic site constraints, and feature attributions.
    """
    return urban_expansion.predict(
        _resolve(query), explain_prediction=query.include_attribution
    )


@router.get("/cell/{grid_id}", response_model=UrbanPrediction)
def predict_urban_by_id(grid_id: str, include_attribution: bool = True):
    """Convenience GET form of the single-cell prediction."""
    grid.get_cell(grid_id)
    return urban_expansion.predict(grid_id, explain_prediction=include_attribution)


@router.get("/city/{city}", response_model=CityLayer)
def predict_urban_city(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """Score every cell in a city."""
    cells = urban_expansion.predict_city(city, limit=limit)
    return CityLayer(city=city, count=len(cells), cells=cells)


@router.get("/city/{city}/geojson", response_model=GeoJsonResponse)
def urban_geojson(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """The suitability layer for a city as GeoJSON — the GREEN/YELLOW/RED map."""
    return grid.to_feature_collection(urban_expansion.predict_city(city, limit=limit))


@router.get("/thresholds")
def urban_thresholds():
    """The classification rule currently in force, and how to change it."""
    return {
        "score_definition": "P(YELLOW) * 0.5 + P(GREEN) * 1.0, bounded to [0, 1]",
        "classification_rule": (
            "score thresholds" if config.URBAN_CLASS_FROM_SCORE
            else "argmax of class probabilities (the rule the model was validated under)"
        ),
        "class_from_score": config.URBAN_CLASS_FROM_SCORE,
        "score_thresholds": {
            "green_at_or_above": config.URBAN_SCORE_GREEN_THRESHOLD,
            "yellow_at_or_above": config.URBAN_SCORE_YELLOW_THRESHOLD,
        },
        "configurable_via": [
            "URBAN_CLASS_FROM_SCORE",
            "URBAN_SCORE_GREEN_THRESHOLD",
            "URBAN_SCORE_YELLOW_THRESHOLD",
        ],
        "class_meaning": urban_expansion.CLASS_MEANING,
    }


@router.get("/metrics", response_model=MetricsResponse)
def urban_metrics():
    """Validation evidence and documented limitations for Model 2."""
    return urban_expansion.metrics()
