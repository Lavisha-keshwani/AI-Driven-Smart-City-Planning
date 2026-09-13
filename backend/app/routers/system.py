"""Health, model status and grid discovery endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from app.agents import llm
from app.agents.graph import graph_topology
from app.core import config, grid
from app.schemas.responses import (
    CitiesResponse,
    GeoJsonResponse,
    GridCellsResponse,
    HealthResponse,
    ModelStatusResponse,
)
from app.services.building_planner import nasa_power
from app.services.models import explain, registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health():
    """Liveness plus a one-line readiness summary.

    Reports `degraded` rather than failing when a model or dataset is missing, so an
    operator can tell the difference between a dead service and an incomplete one.
    """
    status = registry.models_status()
    models_loaded = sum(m["loaded"] for m in status["models"].values())
    datasets_present = sum(status["datasets"].values())
    healthy = status["all_models_loaded"] and status["all_datasets_present"]

    return HealthResponse(
        status="healthy" if healthy else "degraded",
        service="SmartCityAI API",
        version="3.0.0",
        models_loaded=f"{models_loaded}/{len(status['models'])}",
        datasets_present=f"{datasets_present}/{len(status['datasets'])}",
        llm=llm.llm_status(),
    )


@router.get("/api/models/status", response_model=ModelStatusResponse)
def models_status():
    """Detailed load state of every model, dataset and external dependency."""
    status = registry.models_status()

    grid_info: dict = {"cell_size_m": config.GRID_CELL_SIZE_M, "crs": config.GRID_CRS}
    try:
        metadata = grid.grid_metadata()
        grid_info.update(
            {"available": True, "cells": len(metadata), "cities": metadata["city"].nunique()}
        )
    except Exception as exc:  # noqa: BLE001 - status must never fail
        grid_info.update({"available": False, "error": str(exc)})

    return ModelStatusResponse(
        **status,
        llm=llm.llm_status(),
        grid=grid_info,
        nasa_power_cache=nasa_power.cache_info(),
        explainability={
            "shap_available": explain.shap_available(),
            "supported_models": [
                "model1_surface_water", "model2_urban_expansion", "model3_flood_risk"
            ],
            "note": (
                "Attributions are computed per prediction with SHAP TreeExplainer. "
                "When shap is not installed, attributions are reported as null rather "
                "than approximated."
            ),
        },
    )


@router.get("/api/agents/graph", tags=["agents"])
def agent_graph():
    """The agent graph topology and the LLM configuration driving it."""
    return {"topology": graph_topology(), "llm": llm.llm_status()}


@router.get("/api/grid/cities", response_model=CitiesResponse)
def list_cities():
    """Every city covered by the 1 km analysis grid."""
    cities = grid.cities_summary()
    return CitiesResponse(count=len(cities), cities=cities)


@router.get("/api/grid/cities/{city}/cells", response_model=GridCellsResponse)
def list_city_cells(city: str):
    """Grid cell ids for one city."""
    grid_ids = grid.grid_ids_for_city(city)
    return GridCellsResponse(city=city, count=len(grid_ids), grid_ids=grid_ids)


@router.get("/api/grid/cell/{grid_id}")
def get_grid_cell(grid_id: str):
    """Registry record and polygon for one grid cell."""
    cell = grid.get_cell(grid_id)
    return {
        **cell,
        "geometry": {
            "type": "Polygon",
            "coordinates": [grid.cell_polygon(cell["lat"], cell["lon"])],
        },
        "crs": config.GRID_CRS,
        "cell_size_m": config.GRID_CELL_SIZE_M,
    }


@router.get("/api/grid/nearest")
def nearest_grid_cell(
    lat: float = Query(ge=-90, le=90),
    lon: float = Query(ge=-180, le=180),
):
    """The grid cell nearest a point, with the snapping distance."""
    return grid.nearest_cell(lat, lon)


@router.get("/api/grid/cities/{city}/geojson", response_model=GeoJsonResponse)
def city_grid_geojson(city: str, limit: int | None = Query(default=None, ge=1, le=20000)):
    """The bare grid geometry for a city, without predictions."""
    metadata = grid.grid_metadata()
    subset = metadata[metadata["city"].str.lower() == city.strip().lower()]
    if subset.empty:
        grid.grid_ids_for_city(city)  # raises GridNotFoundError with the city list
    if limit:
        subset = subset.head(limit)
    return grid.to_feature_collection(subset.to_dict(orient="records"))
